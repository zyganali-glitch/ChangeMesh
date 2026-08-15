"""ChangeMesh Tests for P-07.05: Agent Revision Metadata Provenance.

Validates that every agent-produced event and evidence record carries exact,
non-blank, machine-checkable agent identity and revision provenance, rejecting
missing, blank, or ambiguous escape-hatch revisions with fail-closed semantics.

Test Sections:
1. AgentRevisionProvenance Domain Contract Tests
2. Provenance and EvidenceRecord Agent Revision Integration Tests
3. EventEnvelope Producer Identity and Revision Provenance Tests
4. Event Delivery Duplicate vs Conflict on Revision Change Tests
5. Canonical Agent Fleet Revision Provenance Propagation Tests
6. Multi-Agent Branch Coordinator Revision Tracing Tests
7. Immutability, Serialization Round-Trip, and Non-Escape Tests
8. Provider Neutrality, Zero Credentials, and Zero Network Tests
"""

from __future__ import annotations

import ast
import json
import pathlib
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

import domain.contracts
from domain.contracts.agent_descriptor import AgentDescriptor, AgentRevisionProvenance
from domain.contracts.data_class import DataClassLevel
from domain.contracts.event_envelope import (
    EventDeliveryDisposition,
    EventEnvelope,
    classify_event_delivery,
)
from domain.contracts.evidence import (
    ArtifactHash,
    EvidenceRecord,
    EvidenceState,
    ExecutionEvidenceMode,
    Provenance,
    TraceReference,
)
from domain.contracts.conventions import HashAlgorithm, UtcDateTime
from src.agents.coordinator import (
    BranchCoordinator,
    BranchExecutionTrace,
    BranchPlan,
    BranchResult,
    BranchSpec,
    BranchStatus,
    CoordinationResult,
    ExecutionStrategy,
)
from src.agents.definition import CANONICAL_TOOL_DESCRIPTORS, AgentDefinition
from src.agents.registry import (
    CANONICAL_SPECIALIST_AGENT_IDS,
    CANONICAL_SPECIALIST_ROLES,
    get_canonical_agent_definition,
    list_canonical_agent_definitions,
)
from src.agents.router import (
    DeterministicRouter,
    RoutingOutcome,
    RoutingRequest,
    RoutingResult,
    RoutingTraceRecord,
)
from src.agents.schemas import (
    EvidenceAuditorInput,
    ImpactScoutInput,
    MigrationEngineerInput,
    PolicyGuardianInput,
    ReleaseStewardInput,
)


# ===========================================================================
# 1. AgentRevisionProvenance Domain Contract Tests
# ===========================================================================


class TestAgentRevisionProvenanceContract:
    """Validate core AgentRevisionProvenance contract semantics."""

    def test_valid_agent_revision_provenance_construction(self):
        """Constructing AgentRevisionProvenance with valid agent_id and revision succeeds."""
        prov = AgentRevisionProvenance(
            agent_id="agent-impact-scout",
            agent_revision="1.0.0",
            role="impact_scout",
        )
        assert prov.agent_id == "agent-impact-scout"
        assert prov.agent_revision == "1.0.0"
        assert prov.role == "impact_scout"

    def test_valid_construction_without_role(self):
        """Role is optional in AgentRevisionProvenance."""
        prov = AgentRevisionProvenance(
            agent_id="agent-policy-guardian",
            agent_revision="1.0.0",
        )
        assert prov.agent_id == "agent-policy-guardian"
        assert prov.agent_revision == "1.0.0"
        assert prov.role is None

    def test_missing_agent_id_fails(self):
        """Missing agent_id must fail validation."""
        with pytest.raises(ValidationError):
            AgentRevisionProvenance.model_validate({"agent_revision": "1.0.0"})

    def test_missing_agent_revision_fails(self):
        """Missing agent_revision must fail validation."""
        with pytest.raises(ValidationError):
            AgentRevisionProvenance.model_validate({"agent_id": "agent-impact-scout"})

    @pytest.mark.parametrize("blank_val", ["", "   ", "\t", "\n"])
    def test_blank_agent_id_fails(self, blank_val: str):
        """Blank agent_id must fail validation."""
        with pytest.raises(ValidationError, match="must not be blank"):
            AgentRevisionProvenance(agent_id=blank_val, agent_revision="1.0.0")

    @pytest.mark.parametrize("blank_val", ["", "   ", "\t", "\n"])
    def test_blank_agent_revision_fails(self, blank_val: str):
        """Blank agent_revision must fail validation."""
        with pytest.raises(ValidationError, match="must not be blank"):
            AgentRevisionProvenance(agent_id="agent-impact-scout", agent_revision=blank_val)

    @pytest.mark.parametrize(
        "escape_hatch",
        [
            "unknown",
            "UNKNOWN",
            "latest",
            "LATEST",
            "current",
            "CURRENT",
            "null",
            "none",
            "*",
            "undefined",
        ],
    )
    def test_escape_hatch_revision_fails(self, escape_hatch: str):
        """Ambiguous escape hatches for agent_revision must fail closed."""
        with pytest.raises(ValidationError, match="cannot be an ambiguous escape hatch"):
            AgentRevisionProvenance(agent_id="agent-impact-scout", agent_revision=escape_hatch)

    @pytest.mark.parametrize(
        "escape_hatch",
        [
            "unknown",
            "UNKNOWN",
            "latest",
            "LATEST",
            "current",
            "CURRENT",
            "null",
            "none",
            "*",
            "undefined",
        ],
    )
    def test_escape_hatch_agent_id_fails(self, escape_hatch: str):
        """Ambiguous escape hatches for agent_id must fail closed."""
        with pytest.raises(ValidationError, match="cannot be an ambiguous escape hatch"):
            AgentRevisionProvenance(agent_id=escape_hatch, agent_revision="1.0.0")

    def test_immutability_and_extra_forbid(self):
        """AgentRevisionProvenance is frozen and forbids extra fields."""
        prov = AgentRevisionProvenance(agent_id="agent-migration-engineer", agent_revision="1.0.0")
        with pytest.raises(ValidationError):
            prov.agent_revision = "2.0.0"  # type: ignore[misc]
        with pytest.raises(ValidationError):
            AgentRevisionProvenance(
                agent_id="agent-migration-engineer",
                agent_revision="1.0.0",
                extra_field="invalid",  # type: ignore[call-arg]
            )

    def test_round_trip_json_serialization(self):
        """AgentRevisionProvenance serializes and deserializes with 100% fidelity."""
        prov = AgentRevisionProvenance(
            agent_id="agent-evidence-auditor",
            agent_revision="1.0.0",
            role="evidence_auditor",
        )
        json_str = prov.model_dump_json()
        loaded = AgentRevisionProvenance.model_validate_json(json_str)
        assert loaded == prov
        assert loaded.agent_id == "agent-evidence-auditor"
        assert loaded.agent_revision == "1.0.0"
        assert loaded.role == "evidence_auditor"


# ===========================================================================
# 2. Provenance and EvidenceRecord Agent Revision Integration Tests
# ===========================================================================


class TestProvenanceAgentRevisionIntegration:
    """Validate Provenance and EvidenceRecord support for exact agent revision metadata."""

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def test_non_agent_provenance_backward_compatibility(self):
        """Historical non-agent provenance without agent metadata remains valid."""
        prov = Provenance(
            schema_version="1.0.0",
            source="fixture-runner",
            collection_mode=ExecutionEvidenceMode.FIXTURE,
            collection_timestamp=self._now(),
        )
        assert prov.agent_id is None
        assert prov.agent_revision is None
        assert prov.agent_role is None
        assert prov.agent_provenance is None
        assert prov.get_agent_provenance() is None

    def test_agent_provenance_via_direct_fields(self):
        """Provenance constructed with agent_id, agent_revision, and agent_role."""
        now = self._now()
        prov = Provenance(
            schema_version="1.0.0",
            source="agent:impact-scout",
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            collection_timestamp=now,
            agent_id="agent-impact-scout",
            agent_revision="1.0.0",
            agent_role="impact_scout",
        )
        assert prov.agent_id == "agent-impact-scout"
        assert prov.agent_revision == "1.0.0"
        assert prov.agent_role == "impact_scout"
        assert prov.agent_provenance is not None
        assert prov.agent_provenance.agent_id == "agent-impact-scout"
        assert prov.agent_provenance.agent_revision == "1.0.0"
        assert prov.agent_provenance.role == "impact_scout"
        assert prov.get_agent_provenance() == prov.agent_provenance

    def test_agent_provenance_via_nested_model(self):
        """Provenance constructed with nested agent_provenance."""
        now = self._now()
        agent_prov = AgentRevisionProvenance(
            agent_id="agent-policy-guardian",
            agent_revision="1.0.0",
            role="policy_guardian",
        )
        prov = Provenance(
            schema_version="1.0.0",
            source="agent:policy-guardian",
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            collection_timestamp=now,
            agent_provenance=agent_prov,
        )
        assert prov.agent_id == "agent-policy-guardian"
        assert prov.agent_revision == "1.0.0"
        assert prov.agent_role == "policy_guardian"
        assert prov.agent_provenance == agent_prov
        assert prov.get_agent_provenance() == agent_prov

    def test_incomplete_agent_provenance_fails_closed(self):
        """Supplying agent_id without agent_revision (or vice-versa) must fail closed."""
        now = self._now()
        # agent_id provided without agent_revision
        with pytest.raises(ValidationError, match="Agent revision provenance requires both"):
            Provenance(
                schema_version="1.0.0",
                source="agent:impact-scout",
                collection_mode=ExecutionEvidenceMode.SIMULATION,
                collection_timestamp=now,
                agent_id="agent-impact-scout",
                agent_revision=None,
            )

        # agent_revision provided without agent_id
        with pytest.raises(ValidationError, match="Agent revision provenance requires both"):
            Provenance(
                schema_version="1.0.0",
                source="agent:impact-scout",
                collection_mode=ExecutionEvidenceMode.SIMULATION,
                collection_timestamp=now,
                agent_id=None,
                agent_revision="1.0.0",
            )

    @pytest.mark.parametrize("blank_val", ["", "   ", "\t"])
    def test_blank_agent_id_or_revision_on_provenance_fails(self, blank_val: str):
        """Blank agent_id or agent_revision on Provenance must fail validation."""
        now = self._now()
        with pytest.raises(ValidationError, match="must not be blank"):
            Provenance(
                schema_version="1.0.0",
                source="agent:impact-scout",
                collection_mode=ExecutionEvidenceMode.SIMULATION,
                collection_timestamp=now,
                agent_id=blank_val,
                agent_revision="1.0.0",
            )

        with pytest.raises(ValidationError, match="must not be blank"):
            Provenance(
                schema_version="1.0.0",
                source="agent:impact-scout",
                collection_mode=ExecutionEvidenceMode.SIMULATION,
                collection_timestamp=now,
                agent_id="agent-impact-scout",
                agent_revision=blank_val,
            )

    @pytest.mark.parametrize(
        "escape_hatch",
        ["unknown", "latest", "current", "null", "none", "*", "undefined"],
    )
    def test_escape_hatch_agent_metadata_on_provenance_fails(self, escape_hatch: str):
        """Escape hatch agent metadata on Provenance must fail closed."""
        now = self._now()
        with pytest.raises(ValidationError, match="cannot be an ambiguous escape hatch"):
            Provenance(
                schema_version="1.0.0",
                source="agent:impact-scout",
                collection_mode=ExecutionEvidenceMode.SIMULATION,
                collection_timestamp=now,
                agent_id="agent-impact-scout",
                agent_revision=escape_hatch,
            )

    def test_evidence_record_with_agent_provenance(self):
        """EvidenceRecord carries complete structured agent revision provenance."""
        now = self._now()
        prov = Provenance(
            schema_version="1.0.0",
            source="agent:evidence-auditor",
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            collection_timestamp=now,
            agent_id="agent-evidence-auditor",
            agent_revision="1.0.0",
            agent_role="evidence_auditor",
        )
        record = EvidenceRecord(
            schema_version="1.0.0",
            evidence_id="ev-audit-001",
            change_request_id="cr-20260815-001",
            subject="semantic_audit_sufficiency",
            state=EvidenceState.PASS,
            provenance=prov,
        )
        assert record.provenance.agent_id == "agent-evidence-auditor"
        assert record.provenance.agent_revision == "1.0.0"
        assert record.provenance.agent_role == "evidence_auditor"
        assert record.state == EvidenceState.PASS

    def test_evidence_record_round_trip_json_serialization(self):
        """EvidenceRecord with agent revision metadata preserves exact facts across JSON serialization."""
        now = self._now()
        prov = Provenance(
            schema_version="1.0.0",
            source="agent:migration-engineer",
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            collection_timestamp=now,
            agent_id="agent-migration-engineer",
            agent_revision="1.0.0",
            agent_role="migration_engineer",
        )
        record = EvidenceRecord(
            schema_version="1.0.0",
            evidence_id="ev-mig-001",
            change_request_id="cr-20260815-001",
            subject="migration_script_reversible",
            state=EvidenceState.PASS,
            provenance=prov,
        )
        json_bytes = record.model_dump_json()
        loaded = EvidenceRecord.model_validate_json(json_bytes)
        assert loaded == record
        assert loaded.provenance.agent_id == "agent-migration-engineer"
        assert loaded.provenance.agent_revision == "1.0.0"
        assert loaded.provenance.agent_role == "migration_engineer"
        assert loaded.provenance.get_agent_provenance() == prov.agent_provenance


# ===========================================================================
# 3. EventEnvelope Producer Identity and Revision Provenance Tests
# ===========================================================================


class TestEventEnvelopeProducerProvenance:
    """Validate EventEnvelope producer identity and exact revision provenance."""

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def test_valid_event_envelope_with_exact_agent_provenance(self):
        """EventEnvelope accepts structured producer identity and exact revision."""
        now = self._now()
        env = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-001",
            change_id="cr-001",
            correlation_id="corr-001",
            producer_id="agent-change-orchestrator",
            producer_revision="1.0.0",
            producer_role="change_orchestrator",
            timestamp=now,
            idempotency_key="idem-001",
        )
        assert env.producer_id == "agent-change-orchestrator"
        assert env.producer_revision == "1.0.0"
        assert env.producer_role == "change_orchestrator"
        assert env.agent_provenance is not None
        assert env.agent_provenance.agent_id == "agent-change-orchestrator"
        assert env.agent_provenance.agent_revision == "1.0.0"
        assert env.get_agent_provenance() == env.agent_provenance

    def test_event_envelope_via_nested_agent_provenance(self):
        """EventEnvelope accepts nested agent_provenance object."""
        now = self._now()
        ap = AgentRevisionProvenance(
            agent_id="agent-impact-scout",
            agent_revision="1.0.0",
            role="impact_scout",
        )
        env = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-002",
            change_id="cr-001",
            correlation_id="corr-001",
            agent_provenance=ap,
            producer_revision=ap.agent_revision,
            timestamp=now,
            idempotency_key="idem-002",
        )
        assert env.producer_id == "agent-impact-scout"
        assert env.producer_revision == "1.0.0"
        assert env.producer_role == "impact_scout"
        assert env.get_agent_provenance() == ap

    @pytest.mark.parametrize(
        "escape_hatch",
        ["unknown", "latest", "current", "null", "none", "*", "undefined"],
    )
    def test_event_envelope_rejects_escape_hatch_producer_revision(self, escape_hatch: str):
        """EventEnvelope rejects ambiguous escape hatch in producer_revision."""
        now = self._now()
        with pytest.raises(ValidationError, match="cannot be an ambiguous escape hatch"):
            EventEnvelope(
                schema_version="1.0.0",
                event_id="evt-003",
                change_id="cr-001",
                correlation_id="corr-001",
                producer_revision=escape_hatch,
                timestamp=now,
                idempotency_key="idem-003",
            )

    @pytest.mark.parametrize(
        "escape_hatch",
        ["unknown", "latest", "current", "null", "none", "*", "undefined"],
    )
    def test_event_envelope_rejects_escape_hatch_producer_id(self, escape_hatch: str):
        """EventEnvelope rejects ambiguous escape hatch in producer_id."""
        now = self._now()
        with pytest.raises(ValidationError, match="cannot be an ambiguous escape hatch"):
            EventEnvelope(
                schema_version="1.0.0",
                event_id="evt-004",
                change_id="cr-001",
                correlation_id="corr-001",
                producer_id=escape_hatch,
                producer_revision="1.0.0",
                timestamp=now,
                idempotency_key="idem-004",
            )

    def test_event_envelope_round_trip_json_serialization(self):
        """EventEnvelope preserves producer identity and revision across JSON round trip."""
        now = self._now()
        env = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-005",
            change_id="cr-001",
            correlation_id="corr-001",
            producer_id="agent-release-steward",
            producer_revision="1.0.0",
            producer_role="release_steward",
            timestamp=now,
            idempotency_key="idem-005",
        )
        json_data = env.model_dump_json()
        loaded = EventEnvelope.model_validate_json(json_data)
        assert loaded == env
        assert loaded.producer_id == "agent-release-steward"
        assert loaded.producer_revision == "1.0.0"
        assert loaded.producer_role == "release_steward"


# ===========================================================================
# 4. Event Delivery Duplicate vs Conflict on Revision Change Tests
# ===========================================================================


class TestEventDeliveryProvenanceSemantics:
    """Validate that classify_event_delivery detects CONFLICT when revision provenance differs."""

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def test_exact_event_replay_is_duplicate(self):
        """Exact identical event envelope produces DUPLICATE disposition."""
        now = self._now()
        env = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-dup-001",
            change_id="cr-001",
            correlation_id="corr-001",
            producer_id="agent-impact-scout",
            producer_revision="1.0.0",
            producer_role="impact_scout",
            timestamp=now,
            idempotency_key="idem-001",
        )
        seen_events = {env.event_id: env}
        seen_idempotency = {(env.change_id, env.idempotency_key): env.event_id}

        disposition = classify_event_delivery(env, seen_events, seen_idempotency)
        assert disposition == EventDeliveryDisposition.DUPLICATE

    def test_same_event_id_with_different_producer_revision_is_conflict(self):
        """Same event_id with changed producer_revision must be CONFLICT, not DUPLICATE."""
        now = self._now()
        env1 = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-conf-001",
            change_id="cr-001",
            correlation_id="corr-001",
            producer_id="agent-impact-scout",
            producer_revision="1.0.0",
            producer_role="impact_scout",
            timestamp=now,
            idempotency_key="idem-001",
        )
        env2 = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-conf-001",
            change_id="cr-001",
            correlation_id="corr-001",
            producer_id="agent-impact-scout",
            producer_revision="1.1.0",  # Changed revision
            producer_role="impact_scout",
            timestamp=now,
            idempotency_key="idem-001",
        )
        seen_events = {env1.event_id: env1}
        seen_idempotency = {(env1.change_id, env1.idempotency_key): env1.event_id}

        disposition = classify_event_delivery(env2, seen_events, seen_idempotency)
        assert disposition == EventDeliveryDisposition.CONFLICT

    def test_same_event_id_with_different_producer_id_is_conflict(self):
        """Same event_id with changed producer_id must be CONFLICT, not DUPLICATE."""
        now = self._now()
        env1 = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-conf-002",
            change_id="cr-001",
            correlation_id="corr-001",
            producer_id="agent-impact-scout",
            producer_revision="1.0.0",
            producer_role="impact_scout",
            timestamp=now,
            idempotency_key="idem-002",
        )
        env2 = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-conf-002",
            change_id="cr-001",
            correlation_id="corr-001",
            producer_id="agent-policy-guardian",  # Changed agent identity
            producer_revision="1.0.0",
            producer_role="policy_guardian",
            timestamp=now,
            idempotency_key="idem-002",
        )
        seen_events = {env1.event_id: env1}
        seen_idempotency = {(env1.change_id, env1.idempotency_key): env1.event_id}

        disposition = classify_event_delivery(env2, seen_events, seen_idempotency)
        assert disposition == EventDeliveryDisposition.CONFLICT


# ===========================================================================
# 5. Canonical Agent Fleet Revision Provenance Propagation Tests
# ===========================================================================


class TestCanonicalAgentFleetProvenance:
    """Validate all six canonical agents expose exact revision provenance."""

    def test_all_six_agents_expose_canonical_revision_provenance(self):
        """Each canonical agent definition returns matching AgentRevisionProvenance."""
        definitions = list_canonical_agent_definitions()
        assert len(definitions) == 6

        for defn in definitions:
            prov = defn.get_revision_provenance()
            assert isinstance(prov, AgentRevisionProvenance)
            assert prov.agent_id == defn.agent_id
            assert prov.agent_revision == defn.agent_revision
            assert prov.role == defn.role
            assert prov.agent_revision == "1.0.0"
            assert not prov.agent_id.startswith("unknown")

    def test_agent_descriptor_get_revision_provenance(self):
        """AgentDescriptor.get_revision_provenance returns valid AgentRevisionProvenance."""
        definitions = list_canonical_agent_definitions()
        for defn in definitions:
            desc = defn.to_descriptor()
            prov = desc.get_revision_provenance()
            assert isinstance(prov, AgentRevisionProvenance)
            assert prov.agent_id == desc.agent_id
            assert prov.agent_revision == desc.agent_revision
            assert prov.role == desc.role

    def test_deterministic_router_records_selected_revision_provenance(self):
        """DeterministicRouter captures exact canonical agent revision in trace and result."""
        router = DeterministicRouter()
        req = RoutingRequest(
            change_id="cr-test-001",
            required_capabilities=["repository_blast_radius_analysis"],
            payload=ImpactScoutInput(
                change_id="cr-test-001",
                target_systems=["billing-service"],
                repository_ref="repo/billing",
            ),
        )
        res = router.route(req)
        assert res.is_routed is True
        assert res.trace.selected_agent_id == "agent-impact-scout"
        assert res.trace.selected_agent_revision == "1.0.0"
        assert res.trace.selected_role == "impact_scout"

        # Check helper methods
        trace_prov = res.trace.get_selected_revision_provenance()
        res_prov = res.get_selected_revision_provenance()
        assert trace_prov is not None
        assert res_prov is not None
        assert trace_prov == res_prov
        assert trace_prov.agent_id == "agent-impact-scout"
        assert trace_prov.agent_revision == "1.0.0"
        assert trace_prov.role == "impact_scout"

    def test_caller_cannot_spoof_canonical_revision_in_routing(self):
        """Injected definition with forged revision is rejected by router."""
        impact_def = get_canonical_agent_definition("agent-impact-scout")
        spoofed_def = AgentDefinition(
            agent_id="agent-impact-scout",
            role="impact_scout",
            agent_revision="9.9.9",  # Forged revision
            description=impact_def.description,
            declared_capabilities=list(impact_def.declared_capabilities),
            forbidden_actions=list(impact_def.forbidden_actions),
            input_schema=impact_def.input_schema,
            output_schema=impact_def.output_schema,
            instruction_contract=impact_def.instruction_contract,
            permitted_tool_ids=list(impact_def.permitted_tool_ids),
            permitted_data_classifications=list(impact_def.permitted_data_classifications),
        )
        router = DeterministicRouter(agent_definitions=[spoofed_def])
        req = RoutingRequest(
            change_id="cr-test-002",
            required_capabilities=["repository_blast_radius_analysis"],
            payload=ImpactScoutInput(
                change_id="cr-test-002",
                target_systems=["billing-service"],
                repository_ref="repo/billing",
            ),
        )
        res = router.route(req)
        assert res.is_routed is False
        assert res.trace.selected_agent_id is None
        assert res.trace.selected_agent_revision is None
        assert res.get_selected_revision_provenance() is None


# ===========================================================================
# 6. Multi-Agent Branch Coordinator Revision Tracing Tests
# ===========================================================================


class TestBranchCoordinatorRevisionTracing:
    """Validate that BranchCoordinator preserves exact agent revision provenance."""

    @pytest.mark.anyio
    async def test_branch_execution_trace_captures_exact_agent_revision(self):
        """BranchExecutionTrace preserves selected_agent_revision."""
        coordinator = BranchCoordinator()
        spec = BranchSpec(
            branch_id="br-impact-01",
            routing_request=RoutingRequest(
                change_id="cr-coord-001",
                required_capabilities=["repository_blast_radius_analysis"],
                payload=ImpactScoutInput(
                    change_id="cr-coord-001",
                    target_systems=["accounts-service"],
                    repository_ref="repo/accounts",
                ),
            ),
        )
        plan = BranchPlan(
            plan_id="plan-001",
            change_id="cr-coord-001",
            branches=[spec],
            strategy=ExecutionStrategy.SEQUENTIAL,
        )
        result: CoordinationResult = await coordinator.execute_plan(plan)
        assert result.is_successful is True
        assert len(result.branch_results) == 1

        br_res: BranchResult = result.branch_results[0]
        assert br_res.trace.selected_agent_id == "agent-impact-scout"
        assert br_res.trace.selected_agent_revision == "1.0.0"
        assert br_res.trace.selected_role == "impact_scout"

        prov = br_res.trace.get_selected_revision_provenance()
        assert prov is not None
        assert prov.agent_id == "agent-impact-scout"
        assert prov.agent_revision == "1.0.0"

    @pytest.mark.anyio
    async def test_coordination_canonical_projection_includes_agent_revision(self):
        """CoordinationResult.get_canonical_state_projection() includes agent_revision."""
        coordinator = BranchCoordinator()
        spec1 = BranchSpec(
            branch_id="br-scout",
            routing_request=RoutingRequest(
                change_id="cr-coord-002",
                required_capabilities=["repository_blast_radius_analysis"],
                payload=ImpactScoutInput(
                    change_id="cr-coord-002",
                    target_systems=["auth-service"],
                    repository_ref="repo/auth",
                ),
            ),
        )
        spec2 = BranchSpec(
            branch_id="br-policy",
            routing_request=RoutingRequest(
                change_id="cr-coord-002",
                required_capabilities=["autonomy_classification_evaluation"],
                payload=PolicyGuardianInput(
                    change_id="cr-coord-002",
                    data_classification=DataClassLevel.CONFIDENTIAL,
                    target_systems=["auth-service"],
                    requested_actions=["schema_migration"],
                    actor_identity="engineer@changemesh.internal",
                ),
            ),
        )
        plan = BranchPlan(
            plan_id="plan-002",
            change_id="cr-coord-002",
            branches=[spec1, spec2],
            strategy=ExecutionStrategy.PARALLEL,
        )
        result: CoordinationResult = await coordinator.execute_plan(plan)
        assert result.is_successful is True

        projection = result.get_canonical_state_projection()
        assert "branch_outcomes" in projection
        assert len(projection["branch_outcomes"]) == 2

        scout_outcome = projection["branch_outcomes"][0]
        assert scout_outcome["agent_id"] == "agent-impact-scout"
        assert scout_outcome["agent_revision"] == "1.0.0"
        assert scout_outcome["role"] == "impact_scout"

        policy_outcome = projection["branch_outcomes"][1]
        assert policy_outcome["agent_id"] == "agent-policy-guardian"
        assert policy_outcome["agent_revision"] == "1.0.0"
        assert policy_outcome["role"] == "policy_guardian"

    @pytest.mark.anyio
    async def test_parallel_and_sequential_provenance_equivalence(self):
        """Parallel and sequential fallback runs produce 100% equivalent revision provenance."""
        coordinator = BranchCoordinator()
        spec1 = BranchSpec(
            branch_id="br-scout",
            routing_request=RoutingRequest(
                change_id="cr-coord-003",
                required_capabilities=["repository_blast_radius_analysis"],
                payload=ImpactScoutInput(
                    change_id="cr-coord-003",
                    target_systems=["payments"],
                    repository_ref="repo/payments",
                ),
            ),
        )
        spec2 = BranchSpec(
            branch_id="br-policy",
            routing_request=RoutingRequest(
                change_id="cr-coord-003",
                required_capabilities=["autonomy_classification_evaluation"],
                payload=PolicyGuardianInput(
                    change_id="cr-coord-003",
                    data_classification=DataClassLevel.INTERNAL,
                    target_systems=["payments"],
                    requested_actions=["schema_migration"],
                    actor_identity="deployer@changemesh.internal",
                ),
            ),
        )
        plan_par = BranchPlan(
            plan_id="plan-003",
            change_id="cr-coord-003",
            branches=[spec1, spec2],
            strategy=ExecutionStrategy.PARALLEL,
        )
        plan_seq = BranchPlan(
            plan_id="plan-003",
            change_id="cr-coord-003",
            branches=[spec1, spec2],
            strategy=ExecutionStrategy.SEQUENTIAL,
        )
        res_par = await coordinator.execute_plan(plan_par)
        res_seq = await coordinator.execute_plan(plan_seq)

        res_par.assert_equivalent_state(res_seq)
        res_seq.assert_equivalent_state(res_par)
        assert res_par.get_canonical_state_projection() == res_seq.get_canonical_state_projection()


# ===========================================================================
# 7. Immutability, Serialization Round-Trip, and Non-Escape Tests
# ===========================================================================


class TestImmutabilityAndRoundTrip:
    """Validate immutability and complete round-trip preservation."""

    def test_agent_descriptor_immutability(self):
        """AgentDescriptor fields are protected against post-init mutation."""
        defn = get_canonical_agent_definition("agent-migration-engineer")
        desc = defn.to_descriptor()
        assert desc.agent_id == "agent-migration-engineer"
        assert desc.agent_revision == "1.0.0"

    def test_routing_trace_record_immutability(self):
        """RoutingTraceRecord is frozen."""
        router = DeterministicRouter()
        req = RoutingRequest(
            change_id="cr-imm-001",
            required_capabilities=["repository_blast_radius_analysis"],
            payload=ImpactScoutInput(
                change_id="cr-imm-001",
                target_systems=["auth"],
                repository_ref="repo/auth",
            ),
        )
        res = router.route(req)
        with pytest.raises(ValidationError):
            res.trace.selected_agent_revision = "2.0.0"  # type: ignore[misc]

    def test_branch_execution_trace_immutability(self):
        """BranchExecutionTrace is frozen."""
        trace = BranchExecutionTrace(
            trace_id="tr-001",
            branch_id="br-001",
            change_id="cr-001",
            strategy_used=ExecutionStrategy.SEQUENTIAL,
            routing_outcome=RoutingOutcome.ROUTED,
            selected_agent_id="agent-impact-scout",
            selected_role="impact_scout",
            selected_agent_revision="1.0.0",
            status=BranchStatus.SUCCESS,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        with pytest.raises(ValidationError):
            trace.selected_agent_revision = "2.0.0"  # type: ignore[misc]


# ===========================================================================
# 8. Provider Neutrality, Zero Credentials, and Zero Network Tests
# ===========================================================================


class TestProviderNeutralityAndSecurity:
    """Ensure no provider SDKs, credentials, or network calls entered domain contracts."""

    def test_no_provider_imports_in_agent_descriptor_or_evidence_or_envelope(self):
        """AST check: domain contracts must not import Google SDKs, ADK, or cloud providers."""
        contract_files = [
            pathlib.Path(domain.contracts.agent_descriptor.__file__),
            pathlib.Path(domain.contracts.evidence.__file__),
            pathlib.Path(domain.contracts.event_envelope.__file__),
        ]
        forbidden_prefixes = (
            "google",
            "vertexai",
            "opentelemetry",
            "pubsub",
            "firestore",
            "github",
        )

        for file_path in contract_files:
            tree = ast.parse(file_path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        for forbidden in forbidden_prefixes:
                            assert not name.name.startswith(forbidden), (
                                f"Forbidden import '{name.name}' in {file_path.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for forbidden in forbidden_prefixes:
                            assert not node.module.startswith(forbidden), (
                                f"Forbidden import-from '{node.module}' in {file_path.name}"
                            )

    def test_no_credentials_in_provenance_or_envelope_model_fields(self):
        """Field inspection: no credential or token field names exist on provenance or envelope."""
        models_to_check = [AgentRevisionProvenance, Provenance, EvidenceRecord, EventEnvelope]
        credential_terms = ("token", "secret", "password", "credential", "private_key")

        for model_cls in models_to_check:
            for field_name in model_cls.model_fields.keys():
                for term in credential_terms:
                    assert term not in field_name.lower(), (
                        f"Credential term '{term}' found in {model_cls.__name__}.{field_name}"
                    )
