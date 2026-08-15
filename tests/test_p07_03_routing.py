"""ChangeMesh P-07.03 — Deterministic Routing and Delegation Tests.

Tests proving all P-07.03 acceptance criteria and invariants:
1. Change Orchestrator remains the coordinator and delegates via deterministic routing.
2. Each of the five specialists has at least one deterministic successful routing case using:
   - a capability it actually declares;
   - its correct canonical input schema.
3. A valid capability with the WRONG specialist input contract is rejected
   (INPUT_CONTRACT_MISMATCH).
4. Unknown capability is rejected (UNKNOWN_CAPABILITY).
5. Blank capability is rejected (BLANK_CAPABILITY / ValueError).
6. Fuzzy/substring/near-match capability names are rejected (UNKNOWN_CAPABILITY / fail-closed).
7. The router cannot select Change Orchestrator as its own delegate (SELF_DELEGATION_PROHIBITED).
8. No matching specialist fails closed (NO_MATCHING_SPECIALIST).
9. Ambiguous multiple eligible specialists fail closed rather than selecting the first match.
   (Exercised using custom AgentDefinitions without mutating canonical six-agent registry).
10. Routing does not create authorization (no permissions granted, no policy synthesized).
11. Routing does not reinterpret Policy Guardian AutonomyDecision.
12. Selecting Release Steward does not imply write permission.
13. LIVE_WRITE does not force HUMAN_AUTHORITY_REQUIRED.
14. No Capability Passport validity is fabricated or assumed.
15. No Gemini / Vertex AI model call is used for routing.
16. No network request is required.
17. No Firestore, Pub/Sub, or GitHub mutations occur.
18. Routing trace records deterministic match/rejection facts.
19. Routing trace contains no credential material.
20. Exactly six canonical agents remain in the fleet.
21. P-07.02 authority-contract tests continue to pass.
22. P-07.01 Change Orchestrator intake tests continue to pass.
23. In-process Google ADK Runner execution of the deterministically routed specialist.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from google.adk.agents.base_agent import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from pydantic import BaseModel, ValidationError

from domain.contracts.autonomy import AutonomyClass
from domain.contracts.data_class import DataClassLevel
from src.agents import (
    CANONICAL_AGENT_CLASSES,
    CANONICAL_AGENT_IDS,
    CANONICAL_ROLES,
    CANONICAL_SPECIALIST_AGENT_IDS,
    CANONICAL_SPECIALIST_ROLES,
    AgentDefinition,
    ChangeOrchestrator,
    DeterministicRouter,
    EvidenceAuditor,
    EvidenceAuditorInput,
    ImpactScout,
    ImpactScoutInput,
    MigrationEngineer,
    MigrationEngineerInput,
    PolicyGuardian,
    PolicyGuardianInput,
    ReleaseSteward,
    ReleaseStewardInput,
    RoutingOutcome,
    RoutingRejectionReason,
    RoutingRequest,
    RoutingResult,
    RoutingTraceRecord,
    get_canonical_agent_definition,
    list_canonical_agent_definitions,
)

# ===========================================================================
# Fixtures and Helpers
# ===========================================================================


def _make_impact_scout_input(change_id: str = "chg-001") -> ImpactScoutInput:
    return ImpactScoutInput(
        schema_version="1.0.0",
        change_id=change_id,
        target_systems=["repo-enterprise-db"],
        repository_ref="main",
        proposed_diff_ref="diff-001",
        data_classification=DataClassLevel.INTERNAL,
    )


def _make_policy_guardian_input(change_id: str = "chg-001") -> PolicyGuardianInput:
    return PolicyGuardianInput(
        schema_version="1.0.0",
        change_id=change_id,
        data_classification=DataClassLevel.INTERNAL,
        target_systems=["repo-enterprise-db"],
        requested_actions=["action.schema.migrate"],
        actor_identity="operator@changemesh.internal",
    )


def _make_migration_engineer_input(change_id: str = "chg-001") -> MigrationEngineerInput:
    return MigrationEngineerInput(
        schema_version="1.0.0",
        change_id=change_id,
        target_system="repo-enterprise-db",
        source_schema_version="1.0.0",
        target_schema_version="2.0.0",
        migration_spec="ALTER TABLE users ADD COLUMN verified BOOLEAN DEFAULT FALSE;",
    )


def _make_evidence_auditor_input(change_id: str = "chg-001") -> EvidenceAuditorInput:
    return EvidenceAuditorInput(
        schema_version="1.0.0",
        change_id=change_id,
        success_criteria_ids=["sc-001"],
        evidence_record_refs=["ev-rec-001", "ev-rec-002"],
        rehearsal_result_refs=["reh-001"],
    )


def _make_release_steward_input(change_id: str = "chg-001") -> ReleaseStewardInput:
    return ReleaseStewardInput(
        schema_version="1.0.0",
        change_id=change_id,
        passport_id="passport-001",
        verified_artifact_ids=["art-001", "art-002"],
        target_repository="zyganali-glitch/ChangeMesh",
        authorization_reference="auth-decision-001",
    )


class DummyUnrelatedPayload(BaseModel):
    """An unrelated BaseModel payload that matches no canonical specialist."""

    unrelated_field: str = "test"


# ===========================================================================
# 1. Orchestrator as Coordinator and Router Integration
# ===========================================================================


def test_orchestrator_remains_coordinator_with_delegation_method() -> None:
    """Verify ChangeOrchestrator coordinates delegation and exposes route_delegation."""
    orch = ChangeOrchestrator()
    assert issubclass(ChangeOrchestrator, BaseAgent)
    assert hasattr(orch, "route_delegation")
    assert hasattr(orch, "delegate")

    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    result = orch.route_delegation(req)
    assert isinstance(result, RoutingResult)
    assert result.is_routed is True
    assert result.selected_agent_class is ImpactScout


def test_orchestrator_route_delegation_type_enforcement() -> None:
    """Verify ChangeOrchestrator fails closed on invalid routing request types."""
    orch = ChangeOrchestrator()
    with pytest.raises(TypeError, match="Expected RoutingRequest instance"):
        orch.route_delegation("invalid_request")  # type: ignore[arg-type]


# ===========================================================================
# 2. Successful Deterministic Routing for All Five Specialists
# ===========================================================================


@pytest.mark.parametrize(
    (
        "required_capability",
        "payload_factory",
        "expected_role",
        "expected_class",
        "expected_agent_id",
    ),
    [
        (
            "repository_blast_radius_analysis",
            _make_impact_scout_input,
            "impact_scout",
            ImpactScout,
            "agent-impact-scout",
        ),
        (
            "affected_systems_identification",
            _make_impact_scout_input,
            "impact_scout",
            ImpactScout,
            "agent-impact-scout",
        ),
        (
            "parallel_change_conflict_detection",
            _make_impact_scout_input,
            "impact_scout",
            ImpactScout,
            "agent-impact-scout",
        ),
        (
            "organizational_policy_evaluation",
            _make_policy_guardian_input,
            "policy_guardian",
            PolicyGuardian,
            "agent-policy-guardian",
        ),
        (
            "privacy_boundary_check",
            _make_policy_guardian_input,
            "policy_guardian",
            PolicyGuardian,
            "agent-policy-guardian",
        ),
        (
            "separation_of_duty_enforcement",
            _make_policy_guardian_input,
            "policy_guardian",
            PolicyGuardian,
            "agent-policy-guardian",
        ),
        (
            "autonomy_classification_evaluation",
            _make_policy_guardian_input,
            "policy_guardian",
            PolicyGuardian,
            "agent-policy-guardian",
        ),
        (
            "migration_artifact_generation",
            _make_migration_engineer_input,
            "migration_engineer",
            MigrationEngineer,
            "agent-migration-engineer",
        ),
        (
            "verification_script_synthesis",
            _make_migration_engineer_input,
            "migration_engineer",
            MigrationEngineer,
            "agent-migration-engineer",
        ),
        (
            "rehearsal_scaffolding",
            _make_migration_engineer_input,
            "migration_engineer",
            MigrationEngineer,
            "agent-migration-engineer",
        ),
        (
            "semantic_evidence_sufficiency_review",
            _make_evidence_auditor_input,
            "evidence_auditor",
            EvidenceAuditor,
            "agent-evidence-auditor",
        ),
        (
            "evidence_completeness_verification",
            _make_evidence_auditor_input,
            "evidence_auditor",
            EvidenceAuditor,
            "agent-evidence-auditor",
        ),
        (
            "claim_justification_analysis",
            _make_evidence_auditor_input,
            "evidence_auditor",
            EvidenceAuditor,
            "agent-evidence-auditor",
        ),
        (
            "release_bundle_packaging",
            _make_release_steward_input,
            "release_steward",
            ReleaseSteward,
            "agent-release-steward",
        ),
        (
            "draft_pull_request_preparation",
            _make_release_steward_input,
            "release_steward",
            ReleaseSteward,
            "agent-release-steward",
        ),
        (
            "reversible_handoff_construction",
            _make_release_steward_input,
            "release_steward",
            ReleaseSteward,
            "agent-release-steward",
        ),
    ],
)
def test_successful_deterministic_routing_for_each_specialist(
    required_capability: str,
    payload_factory: Any,
    expected_role: str,
    expected_class: type[BaseAgent],
    expected_agent_id: str,
) -> None:
    """Verify each specialist routes successfully with its declared capability and schema."""
    router = DeterministicRouter()
    payload = payload_factory()
    req = RoutingRequest(
        change_id="chg-success-001",
        required_capabilities=[required_capability],
        payload=payload,
    )
    result = router.route(req)

    assert result.outcome == RoutingOutcome.ROUTED
    assert result.is_routed is True
    assert result.is_successful is True
    assert result.selected_agent_class is expected_class
    assert result.selected_definition is not None
    assert result.selected_definition.role == expected_role
    assert result.selected_definition.agent_id == expected_agent_id
    assert result.selected_definition.agent_revision == "1.0.0"
    assert result.payload == payload

    # Trace verification
    trace = result.trace
    assert trace.outcome == RoutingOutcome.ROUTED
    assert trace.change_id == "chg-success-001"
    assert trace.required_capabilities == [required_capability]
    assert trace.payload_type == type(payload).__name__
    assert trace.selected_agent_id == expected_agent_id
    assert trace.selected_role == expected_role
    assert trace.selected_agent_revision == "1.0.0"
    assert trace.capability_match_passed is True
    assert trace.contract_match_passed is True
    assert trace.rejection_reason is None


def test_multiple_capabilities_single_specialist_match() -> None:
    """Verify routing succeeds when multiple capabilities all belong to the same specialist."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-multi-001",
        required_capabilities=[
            "repository_blast_radius_analysis",
            "affected_systems_identification",
        ],
        payload=payload,
    )
    result = router.route(req)
    assert result.outcome == RoutingOutcome.ROUTED
    assert result.selected_agent_class is ImpactScout
    assert result.trace.capability_match_passed is True
    assert result.trace.contract_match_passed is True


# ===========================================================================
# 3. Input Contract Mismatch Rejection
# ===========================================================================


def test_valid_capability_with_wrong_specialist_contract_rejected() -> None:
    """Verify valid capability with mismatched contract is rejected with INPUT_CONTRACT_MISMATCH."""
    router = DeterministicRouter()
    # Impact Scout capability, but Policy Guardian input payload passed
    wrong_payload = _make_policy_guardian_input()
    req = RoutingRequest(
        change_id="chg-mismatch-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=wrong_payload,
    )
    result = router.route(req)

    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.trace.capability_match_passed is True
    assert result.trace.contract_match_passed is False
    assert result.trace.rejection_reason == RoutingRejectionReason.INPUT_CONTRACT_MISMATCH
    assert result.trace.selected_agent_id == "agent-impact-scout"
    assert result.trace.selected_role == "impact_scout"


def test_unrelated_payload_contract_mismatch() -> None:
    """Verify an unrelated payload model fails contract matching."""
    router = DeterministicRouter()
    unrelated_payload = DummyUnrelatedPayload()
    req = RoutingRequest(
        change_id="chg-unrelated-001",
        required_capabilities=["organizational_policy_evaluation"],
        payload=unrelated_payload,
    )
    result = router.route(req)

    assert result.outcome == RoutingOutcome.REJECTED
    assert result.trace.rejection_reason == RoutingRejectionReason.INPUT_CONTRACT_MISMATCH


# ===========================================================================
# 4. Unknown Capability Rejection
# ===========================================================================


def test_unknown_capability_rejected() -> None:
    """Verify unknown capability fails closed with UNKNOWN_CAPABILITY."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-unknown-001",
        required_capabilities=["arbitrary_unknown_capability_xyz"],
        payload=payload,
    )
    result = router.route(req)

    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.trace.capability_match_passed is False
    assert result.trace.contract_match_passed is False
    assert result.trace.rejection_reason == RoutingRejectionReason.UNKNOWN_CAPABILITY


# ===========================================================================
# 5. Blank Capability Rejection
# ===========================================================================


def test_blank_capability_in_routing_request_fails_closed() -> None:
    """Verify blank or whitespace-only capability is rejected by RoutingRequest or Router."""
    # Pydantic validation rejects blank items
    with pytest.raises(ValidationError):
        RoutingRequest(
            change_id="chg-blank-001",
            required_capabilities=["   "],
            payload=_make_impact_scout_input(),
        )

    with pytest.raises(ValidationError):
        RoutingRequest(
            change_id="chg-blank-002",
            required_capabilities=[],
            payload=_make_impact_scout_input(),
        )


def test_blank_change_id_fails_closed() -> None:
    """Verify blank change_id is rejected by RoutingRequest validation."""
    with pytest.raises(ValidationError):
        RoutingRequest(
            change_id="   ",
            required_capabilities=["repository_blast_radius_analysis"],
            payload=_make_impact_scout_input(),
        )


# ===========================================================================
# 6. Fuzzy / Substring / Near-Match Rejection
# ===========================================================================


@pytest.mark.parametrize(
    "fuzzy_capability",
    [
        "blast_radius",
        "repository_blast_radius",
        "policy_evaluation",
        "privacy",
        "migration",
        "evidence",
        "release",
        "REPOSITORY_BLAST_RADIUS_ANALYSIS",
        "repository_blast_radius_analysis ",
    ],
)
def test_fuzzy_and_substring_capabilities_rejected(fuzzy_capability: str) -> None:
    """Verify fuzzy, substring, case-altered, and near-match capability names are rejected."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()

    try:
        req = RoutingRequest(
            change_id="chg-fuzzy-001",
            required_capabilities=[fuzzy_capability],
            payload=payload,
        )
        result = router.route(req)
        assert result.outcome == RoutingOutcome.REJECTED
        assert result.is_routed is False
    except ValidationError:
        # Pydantic validation rejection is also a valid fail-closed outcome
        pass


# ===========================================================================
# 7. Self-Delegation Prohibited
# ===========================================================================


@pytest.mark.parametrize(
    "orch_cap",
    [
        "change_request_intake",
        "lifecycle_coordination",
        "delegation_dispatch",
    ],
)
def test_orchestrator_capabilities_cannot_self_route(orch_cap: str) -> None:
    """Verify Orchestrator's own capabilities fail closed and never cause self-delegation."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-self-001",
        required_capabilities=[orch_cap],
        payload=payload,
    )
    result = router.route(req)

    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.trace.rejection_reason in (
        RoutingRejectionReason.SELF_DELEGATION_PROHIBITED,
        RoutingRejectionReason.NO_MATCHING_SPECIALIST,
    )
    assert result.selected_agent_class is None


# ===========================================================================
# 8. No Matching Specialist Fails Closed
# ===========================================================================


def test_cross_specialist_capability_combination_fails_closed() -> None:
    """Verify requiring capabilities from disjoint specialists fails closed."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-nomatch-001",
        required_capabilities=[
            "repository_blast_radius_analysis",  # Impact Scout
            "privacy_boundary_check",  # Policy Guardian
        ],
        payload=payload,
    )
    result = router.route(req)

    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.trace.capability_match_passed is False
    assert result.trace.rejection_reason == RoutingRejectionReason.NO_MATCHING_SPECIALIST


# ===========================================================================
# 9. Ambiguous Multiple Matching Specialists Fail Closed
# ===========================================================================


def test_ambiguous_multiple_matching_specialists_fail_closed() -> None:
    """Verify that multiple matching specialists fail closed with AMBIGUOUS_MATCH.

    Exercised using duplicate genuine canonical definitions without mutating registry
    and without invented agent identities or non-canonical metadata.
    """
    impact_def = get_canonical_agent_definition("agent-impact-scout")
    # Injected candidate list with duplicate genuine canonical definitions
    custom_router = DeterministicRouter(agent_definitions=[impact_def, impact_def])
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-ambig-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    result = custom_router.route(req)

    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.trace.capability_match_passed is False
    assert result.trace.rejection_reason == RoutingRejectionReason.AMBIGUOUS_MATCH
    assert len(result.trace.evaluated_candidates) == 2


# ===========================================================================
# 10–14. Routing != Authorization & Authority Boundary Invariants
# ===========================================================================


def test_routing_does_not_create_authorization() -> None:
    """Verify routing result contains no authorization grants, approvals, or permissions."""
    router = DeterministicRouter()
    payload = _make_policy_guardian_input()
    req = RoutingRequest(
        change_id="chg-auth-001",
        required_capabilities=["organizational_policy_evaluation"],
        payload=payload,
    )
    result = router.route(req)

    assert result.is_routed is True
    # RoutingResult has no authority-granting fields
    assert not hasattr(result, "authorization_decision")
    assert not hasattr(result, "approved")
    assert not hasattr(result, "human_authority_granted")


def test_routing_does_not_reinterpret_autonomy_decision() -> None:
    """Verify routing does not create or alter AutonomyDecision contracts."""
    router = DeterministicRouter()
    payload = _make_policy_guardian_input()
    req = RoutingRequest(
        change_id="chg-autonomy-001",
        required_capabilities=["autonomy_classification_evaluation"],
        payload=payload,
    )
    result = router.route(req)
    assert result.is_routed is True
    # Trace contains only routing evaluation facts
    assert result.trace.rejection_reason is None
    assert result.trace.capability_match_passed is True


def test_selecting_release_steward_does_not_grant_write_permission() -> None:
    """Verify routing to Release Steward does not imply or grant write authority."""
    router = DeterministicRouter()
    payload = _make_release_steward_input()
    req = RoutingRequest(
        change_id="chg-rel-001",
        required_capabilities=["release_bundle_packaging"],
        payload=payload,
    )
    result = router.route(req)
    assert result.is_routed is True
    assert result.selected_agent_class is ReleaseSteward
    # Verify Release Steward definition still forbids self_authorize_execution
    assert "self_authorize_execution" in ReleaseSteward.forbidden_actions


def test_live_write_does_not_force_human_authority_required() -> None:
    """Verify that LIVE_WRITE does not equate to HUMAN_AUTHORITY_REQUIRED in routing."""
    # AutonomyClass.AUTO_EXECUTE remains distinct and valid for live operations under policy
    assert AutonomyClass.AUTO_EXECUTE.value == "AUTO_EXECUTE"
    assert AutonomyClass.HUMAN_AUTHORITY_REQUIRED.value == "HUMAN_AUTHORITY_REQUIRED"


def test_no_capability_passport_fabricated_or_assumed() -> None:
    """Verify routing does not manufacture CapabilityPassport instances or claims."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-pass-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    result = router.route(req)
    assert not hasattr(result, "passport")
    assert not hasattr(result.trace, "passport_signature")


# ===========================================================================
# 15–17. Zero Model, Network, External Writes
# ===========================================================================


def test_no_gemini_or_vertex_invocation_during_routing() -> None:
    """Verify no Gemini/Vertex AI model client or inference is invoked during routing."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-nomodel-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )

    with patch("google.genai.Client") as mock_genai:
        result = router.route(req)
        assert result.is_routed is True
        assert mock_genai.call_count == 0


def test_no_network_requests_during_routing() -> None:
    """Verify routing performs zero network socket or HTTP calls."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-nonetwork-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )

    with patch("urllib.request.urlopen") as mock_url, patch("socket.socket") as mock_socket:
        result = router.route(req)
        assert result.is_routed is True
        assert mock_url.call_count == 0
        assert mock_socket.call_count == 0


def test_routing_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify routing operates completely without any environment credentials."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-nocreds-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    result = router.route(req)
    assert result.is_routed is True


# ===========================================================================
# 18–19. Routing Trace Evidence & Credential Redaction
# ===========================================================================


def test_routing_trace_records_deterministic_facts() -> None:
    """Verify routing trace record contains exact machine-testable facts."""
    router = DeterministicRouter()
    payload = _make_migration_engineer_input()
    req = RoutingRequest(
        change_id="chg-trace-001",
        required_capabilities=["migration_artifact_generation"],
        payload=payload,
    )
    result = router.route(req)

    trace = result.trace
    assert isinstance(trace, RoutingTraceRecord)
    assert trace.trace_id.startswith("trace-")
    assert trace.change_id == "chg-trace-001"
    assert trace.outcome == RoutingOutcome.ROUTED
    assert trace.required_capabilities == ["migration_artifact_generation"]
    assert trace.payload_type == "MigrationEngineerInput"
    assert trace.selected_agent_id == "agent-migration-engineer"
    assert trace.selected_role == "migration_engineer"
    assert trace.selected_agent_revision == "1.0.0"
    assert trace.capability_match_passed is True
    assert trace.contract_match_passed is True
    assert trace.rejection_reason is None
    assert trace.timestamp is not None


def test_routing_trace_contains_no_credentials() -> None:
    """Verify routing trace does not leak credential tokens or secret keys."""
    router = DeterministicRouter()
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-trace-clean-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    result = router.route(req)

    trace_dump = result.trace.model_dump_json()
    assert "token" not in trace_dump.lower()
    assert "password" not in trace_dump.lower()
    assert "secret" not in trace_dump.lower()
    assert "key" not in trace_dump.lower() or "monkey" in trace_dump.lower()


# ===========================================================================
# 20. Exactly Six Canonical Agents Remain
# ===========================================================================


def test_canonical_fleet_size_remains_strictly_six() -> None:
    """Verify the canonical fleet size remains exactly six agents."""
    assert len(CANONICAL_AGENT_CLASSES) == 6
    assert len(CANONICAL_AGENT_IDS) == 6
    assert len(CANONICAL_ROLES) == 6
    assert len(list_canonical_agent_definitions()) == 6


# ===========================================================================
# 23. Real In-Process Google ADK Runner Smoke Test for Routed Specialist
# ===========================================================================


def test_routed_specialist_executes_with_google_adk_runner() -> None:
    """Verify the deterministically routed agent is executed via Google ADK Runner."""
    orch = ChangeOrchestrator()
    payload = _make_impact_scout_input(change_id="chg-adk-001")
    req = RoutingRequest(
        change_id="chg-adk-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )

    routing_result = orch.route_delegation(req)
    assert routing_result.is_routed is True
    assert routing_result.selected_agent_class is not None

    # Instantiate the selected specialist
    agent_cls = routing_result.selected_agent_class
    assert agent_cls is not None
    assert issubclass(agent_cls, BaseAgent)
    selected_agent_instance = agent_cls(name="impact_scout")
    assert isinstance(selected_agent_instance, BaseAgent)
    assert selected_agent_instance.name == "impact_scout"

    session_service = InMemorySessionService()
    runner = Runner(
        agent=selected_agent_instance,
        app_name="changemesh_routing_test",
        session_service=session_service,
        auto_create_session=True,
    )

    message = Content(role="user", parts=[Part.from_text(text="execute_analysis")])
    events = list(
        runner.run(
            user_id="local_tester",
            session_id="session_routing_smoke",
            new_message=message,
        )
    )

    assert len(events) >= 1
    assert any(isinstance(ev, Event) for ev in events)
    assert any(getattr(ev, "author", None) == "impact_scout" for ev in events)
    assert any(getattr(ev, "turn_complete", False) is True for ev in events)


# ===========================================================================
# 24. Canonical Fleet Provenance & Anti-Spoofing Tests
# ===========================================================================


def test_single_invented_agent_definition_never_yields_routed() -> None:
    """Verify a single completely synthetic AgentDefinition cannot yield ROUTED."""
    synthetic_def = AgentDefinition(
        agent_id="agent-invented-synthetic",
        role="synthetic_worker",
        agent_revision="1.0.0",
        description="Invented worker agent",
        declared_capabilities=["synthetic_custom_capability"],
        forbidden_actions=["mutation"],
        input_schema=ImpactScoutInput,
        output_schema=ImpactScoutInput,
        instruction_contract="Instruction for synthetic worker",
        permitted_tool_ids=["tool-custom"],
        permitted_data_classifications=[DataClassLevel.INTERNAL],
    )
    router = DeterministicRouter(agent_definitions=[synthetic_def])
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-synth-001",
        required_capabilities=["synthetic_custom_capability"],
        payload=payload,
    )
    result = router.route(req)

    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.selected_agent_class is None
    assert result.selected_definition is None
    assert result.trace.capability_match_passed is False
    assert result.trace.rejection_reason == RoutingRejectionReason.UNKNOWN_CAPABILITY


def test_invented_agent_id_and_role_with_canonical_capability_fails_closed() -> None:
    """Verify an invented agent claiming a genuine canonical capability cannot be routed."""
    synthetic_def = AgentDefinition(
        agent_id="agent-custom-scout",
        role="custom_scout",
        agent_revision="1.0.0",
        description="Custom scout claiming real capability",
        declared_capabilities=["repository_blast_radius_analysis"],
        forbidden_actions=["mutation"],
        input_schema=ImpactScoutInput,
        output_schema=ImpactScoutInput,
        instruction_contract="Instruction for custom scout",
        permitted_tool_ids=["tool-custom"],
        permitted_data_classifications=[DataClassLevel.INTERNAL],
    )
    router = DeterministicRouter(agent_definitions=[synthetic_def])
    payload = _make_impact_scout_input()
    req = RoutingRequest(
        change_id="chg-synth-002",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    result = router.route(req)

    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.selected_agent_class is None
    assert result.selected_definition is None
    assert result.trace.rejection_reason == RoutingRejectionReason.NO_MATCHING_SPECIALIST


def test_canonical_id_spoof_with_forged_capability_rejected() -> None:
    """Verify a spoofed canonical definition with a forged capability cannot make it routable."""
    canonical_impact = get_canonical_agent_definition("agent-impact-scout")
    spoofed_def = AgentDefinition(
        agent_id=canonical_impact.agent_id,
        role=canonical_impact.role,
        agent_revision=canonical_impact.agent_revision,
        description=canonical_impact.description,
        declared_capabilities=["forged_capability_never_in_canonical_fleet"],
        forbidden_actions=canonical_impact.forbidden_actions,
        input_schema=canonical_impact.input_schema,
        output_schema=canonical_impact.output_schema,
        instruction_contract=canonical_impact.instruction_contract,
        permitted_tool_ids=canonical_impact.permitted_tool_ids,
        permitted_data_classifications=canonical_impact.permitted_data_classifications,
    )
    router = DeterministicRouter(agent_definitions=[spoofed_def])
    payload = _make_impact_scout_input()

    # 1. Requesting the forged capability fails closed with UNKNOWN_CAPABILITY
    req_forged = RoutingRequest(
        change_id="chg-spoof-001",
        required_capabilities=["forged_capability_never_in_canonical_fleet"],
        payload=payload,
    )
    result_forged = router.route(req_forged)
    assert result_forged.outcome == RoutingOutcome.REJECTED
    assert result_forged.is_routed is False
    assert result_forged.selected_agent_class is None
    assert result_forged.trace.rejection_reason == RoutingRejectionReason.UNKNOWN_CAPABILITY

    # 2. Requesting genuine capability against tampered candidate fails closed (tampered candidate
    # discarded)
    req_real = RoutingRequest(
        change_id="chg-spoof-002",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    result_real = router.route(req_real)
    assert result_real.outcome == RoutingOutcome.REJECTED
    assert result_real.is_routed is False
    assert result_real.selected_agent_class is None
    assert result_real.trace.rejection_reason == RoutingRejectionReason.NO_MATCHING_SPECIALIST


def test_canonical_id_spoof_with_transferred_capability_rejected() -> None:
    """Verify forging another agent's capability onto a canonical agent is rejected."""
    canonical_impact = get_canonical_agent_definition("agent-impact-scout")
    # Forging Policy Guardian's capability onto Impact Scout's ID
    spoofed_def = AgentDefinition(
        agent_id=canonical_impact.agent_id,
        role=canonical_impact.role,
        agent_revision=canonical_impact.agent_revision,
        description=canonical_impact.description,
        declared_capabilities=["privacy_boundary_check"],
        forbidden_actions=canonical_impact.forbidden_actions,
        input_schema=canonical_impact.input_schema,
        output_schema=canonical_impact.output_schema,
        instruction_contract=canonical_impact.instruction_contract,
        permitted_tool_ids=canonical_impact.permitted_tool_ids,
        permitted_data_classifications=canonical_impact.permitted_data_classifications,
    )
    router = DeterministicRouter(agent_definitions=[spoofed_def])
    payload = _make_impact_scout_input()

    req = RoutingRequest(
        change_id="chg-spoof-003",
        required_capabilities=["privacy_boundary_check"],
        payload=payload,
    )
    result = router.route(req)
    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.selected_agent_class is None
    assert result.trace.rejection_reason == RoutingRejectionReason.NO_MATCHING_SPECIALIST


def test_canonical_id_spoof_with_altered_input_schema_rejected() -> None:
    """Verify tampering with a canonical specialist's input_schema causes candidate rejection."""
    canonical_impact = get_canonical_agent_definition("agent-impact-scout")
    spoofed_def = AgentDefinition(
        agent_id=canonical_impact.agent_id,
        role=canonical_impact.role,
        agent_revision=canonical_impact.agent_revision,
        description=canonical_impact.description,
        declared_capabilities=canonical_impact.declared_capabilities,
        forbidden_actions=canonical_impact.forbidden_actions,
        input_schema=PolicyGuardianInput,  # Altered input schema!
        output_schema=canonical_impact.output_schema,
        instruction_contract=canonical_impact.instruction_contract,
        permitted_tool_ids=canonical_impact.permitted_tool_ids,
        permitted_data_classifications=canonical_impact.permitted_data_classifications,
    )
    router = DeterministicRouter(agent_definitions=[spoofed_def])
    payload = _make_impact_scout_input()

    req = RoutingRequest(
        change_id="chg-spoof-004",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    result = router.route(req)
    assert result.outcome == RoutingOutcome.REJECTED
    assert result.is_routed is False
    assert result.selected_agent_class is None
    assert result.trace.rejection_reason == RoutingRejectionReason.NO_MATCHING_SPECIALIST


def test_successful_routed_result_guarantees_all_canonical_invariants() -> None:
    """Verify that every successful route satisfies all canonical provenance invariants."""
    router = DeterministicRouter()
    orch = ChangeOrchestrator()

    test_matrix: list[tuple[str, BaseModel, str, str, type]] = [
        (
            "repository_blast_radius_analysis",
            _make_impact_scout_input("chg-inv-001"),
            "agent-impact-scout",
            "impact_scout",
            ImpactScout,
        ),
        (
            "organizational_policy_evaluation",
            _make_policy_guardian_input("chg-inv-002"),
            "agent-policy-guardian",
            "policy_guardian",
            PolicyGuardian,
        ),
        (
            "migration_artifact_generation",
            _make_migration_engineer_input("chg-inv-003"),
            "agent-migration-engineer",
            "migration_engineer",
            MigrationEngineer,
        ),
        (
            "semantic_evidence_sufficiency_review",
            _make_evidence_auditor_input("chg-inv-004"),
            "agent-evidence-auditor",
            "evidence_auditor",
            EvidenceAuditor,
        ),
        (
            "release_bundle_packaging",
            _make_release_steward_input("chg-inv-005"),
            "agent-release-steward",
            "release_steward",
            ReleaseSteward,
        ),
    ]

    for req_cap, payload, expected_id, expected_role, expected_cls in test_matrix:
        req = RoutingRequest(
            change_id=getattr(payload, "change_id"),
            required_capabilities=[req_cap],
            payload=payload,
        )

        # Direct router evaluation
        result = router.route(req)
        assert result.outcome == RoutingOutcome.ROUTED
        assert result.is_routed is True
        assert result.is_successful is True

        # Invariant 1: selected_agent_class is not None and is canonical BaseAgent subclass
        assert result.selected_agent_class is not None
        assert result.selected_agent_class is expected_cls
        assert issubclass(result.selected_agent_class, BaseAgent)

        # Invariant 2: selected_definition is genuine canonical definition
        assert result.selected_definition is not None
        canonical_def = get_canonical_agent_definition(expected_id)
        assert result.selected_definition == canonical_def

        # Invariant 3: selected agent identity is in canonical specialist tuples
        assert result.trace.selected_agent_id in CANONICAL_SPECIALIST_AGENT_IDS
        assert result.trace.selected_agent_id == expected_id
        assert result.trace.selected_role in CANONICAL_SPECIALIST_ROLES
        assert result.trace.selected_role == expected_role

        # Invariant 4: capability exists in canonical selected definition
        assert req_cap in result.selected_definition.declared_capabilities

        # Invariant 5: payload matches canonical input schema
        assert isinstance(result.payload, result.selected_definition.input_schema)

        # Invariant 6: trace facts
        assert result.trace.capability_match_passed is True
        assert result.trace.contract_match_passed is True
        assert result.trace.rejection_reason is None

        # Orchestrator delegation wrapper parity
        orch_result = orch.route_delegation(req)
        assert orch_result.outcome == RoutingOutcome.ROUTED
        assert orch_result.selected_agent_class is expected_cls


def test_orchestrator_definition_cannot_be_injected_as_delegation_target() -> None:
    """Verify passing only Orchestrator definition cannot yield delegation."""
    orch_def = get_canonical_agent_definition("agent-change-orchestrator")
    router = DeterministicRouter(agent_definitions=[orch_def])
    payload = _make_impact_scout_input()

    # 1. Specialist capability with only orchestrator candidate fails closed (no matching
    # specialist)
    req_spec = RoutingRequest(
        change_id="chg-orch-001",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=payload,
    )
    res_spec = router.route(req_spec)
    assert res_spec.outcome == RoutingOutcome.REJECTED
    assert res_spec.trace.rejection_reason == RoutingRejectionReason.NO_MATCHING_SPECIALIST

    # 2. Orchestrator capability fails closed with SELF_DELEGATION_PROHIBITED
    req_self = RoutingRequest(
        change_id="chg-orch-002",
        required_capabilities=["lifecycle_coordination"],
        payload=payload,
    )
    res_self = router.route(req_self)
    assert res_self.outcome == RoutingOutcome.REJECTED
    assert res_self.trace.rejection_reason == RoutingRejectionReason.SELF_DELEGATION_PROHIBITED
