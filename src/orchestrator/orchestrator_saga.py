"""ChangeMesh End-to-End Saga Orchestrator.

P-20.01: Implements the canonical end-to-end change lifecycle saga across:
1. Discover (DISCOVERING)
2. Qualify (QUALIFYING)
3. Rehearse (REHEARSING)
4. Ground (GROUNDED)
5. Authorize (AUTHORIZED or AWAITING_AUTHORITY or BLOCKED)
6. Execute (EXECUTING)
7. Verify (VERIFYING)
8. Certify (CERTIFYING -> COMPLETE)

Invariants:
- State transitions are strictly event-driven and persisted.
- Persisted ChangeRecord with optimistic concurrency is authoritative workflow state.
- Authoritative state is persisted in SagaStateRepository before EventEnvelope publishing.
- Every admitted lifecycle transition publishes an EventEnvelope with full causation chain.
- Policy Guardian Gate hard blockers transition to BLOCKED with zero approval cards.
- HUMAN_AUTHORITY_REQUIRED halts at AWAITING_AUTHORITY with a derived Approval Compression card.
- No downstream execution tasks or external mutations on BLOCKED or AWAITING_AUTHORITY.
- Execution evidence modes remain strictly truthful; local actions are never LIVE_WRITE.
- Credentials and secrets are minimized before wire message emission and state persistence.
- Release Steward and external actions are isolated and respect ExecutionEvidenceMode.
- Deterministic facts cannot be overwritten by semantic model outputs.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from domain.contracts.agent_descriptor import AgentRevisionProvenance
from domain.contracts.autonomy import ApprovalCompressionCard, AutonomyClass
from domain.contracts.change_lifecycle import (
    ChangeState,
    require_transition,
)
from domain.contracts.change_request import ChangeRequest
from domain.contracts.conventions import REDACTION_SENTINEL, redact_mapping
from domain.contracts.event_envelope import EventEnvelope
from domain.contracts.evidence import (
    EvidenceProducerKind,
    EvidenceState,
    ExecutionEvidenceMode,
)
from domain.contracts.memory import MemoryRecord
from events.local_bus import LocalEventBus
from events.publisher import EventPublisher
from events.topology import get_canonical_topology
from events.wire import EventWireMessage, scan_payload_for_secrets
from src.audit.audit_bundle import AuditBundleBuilder
from src.audit.claim_derivation import ClaimDerivationEngine
from src.audit.reconciliation import DeterministicReconciler
from src.audit.semantic_auditor import SemanticAuditor
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.gate.policy_guardian_gate import PolicyGuardianGate
from src.gate.reversibility import (
    DeterministicPolicyInputs,
    NoveltyTier,
    PrivilegeLevel,
    RehearsalStatus,
    ReversibilityClassifier,
)
from src.git.impact_scout import (
    BlastRadiusMerger,
    GraphTraverser,
    RepositoryScanner,
    build_synthetic_billing_graph,
)
from src.memory.trust_layer import EpistemicTrustClass, MemoryTrustEvaluator
from src.migration.manifest_generator import ManifestGenerator
from src.migration.plan_generator import MigrationPlanGenerator
from src.orchestrator.saga_checkpoint import SagaCheckpointManager
from src.orchestrator.state_repository import (
    CANONICAL_SCHEMA_VERSION,
    ApprovalRecord,
    ApprovalResolutionStatus,
    ChangeRecord,
    EvidenceRefRecord,
    SagaStateRepository,
    TaskRecord,
    TaskStatus,
    TenantRecord,
    validate_tenant_id,
)
from src.policy.policy_engine import DeterministicPolicyChecker
from src.registry.agent_registry import (
    AgentDescriptor,
    AgentRegistry,
    InMemoryAgentRegistry,
)
from src.registry.capabilities import (
    get_standard_demo_requirements,
)
from src.registry.evidence_verifier import (
    QualificationEvidenceRecord,
    QualificationEvidenceRegistry,
    QualificationEvidenceVerifier,
)
from src.registry.passport_issuer import (
    PassportIssuanceRequest,
    PassportIssuer,
    PassportVerifier,
)
from src.shadowlab.runner import ShadowLabRunner
from src.shadowlab.scenarios import (
    ShadowScenario,
    get_standard_shadow_scenarios,
)

logger = logging.getLogger(__name__)

_SECRET_REPLACEMENT_PATTERNS = [
    re.compile(
        r"-{5}BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-{5}"
        r".*?-{5}END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-{5}",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r"-{5}BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-{5}", re.IGNORECASE),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{15,}\b", re.IGNORECASE),
    re.compile(r"\b(?:sk-(?:proj-|svcacct-)?|AIza)[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(
        r"(?:api[_-]?key|apikey|secret[_-]?key|client[_-]?secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}['\"]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^'\"]{4,}['\"]?",
        re.IGNORECASE,
    ),
]


def sanitize_secrets_in_text(text: str) -> str:
    """Sanitize credential patterns from free-form text strings."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern in _SECRET_REPLACEMENT_PATTERNS:
        result = pattern.sub(REDACTION_SENTINEL, result)
    return result


def validate_supported_change_intent(request: ChangeRequest) -> tuple[bool, str]:
    """Validate that the incoming ChangeRequest matches the supported synthetic billing operation.

    If the request describes an unsupported, destructive, or unrelated operation (e.g. DROP TABLE),
    fails closed immediately to prevent executing an unrelated fixture (fact laundering).
    """
    allowed_targets = {"billing-db", "payment-service", "billing_db", "billing-api"}
    req_targets = set(request.target_systems)
    if not req_targets or not req_targets.intersection(allowed_targets):
        return False, "Target systems do not match supported synthetic billing targets"

    text = (request.title + " " + request.description).lower()

    # Reject destructive SQL commands explicitly
    destructive_keywords = [
        "drop table",
        "drop database",
        "drop column",
        "delete from",
        "truncate",
        "drop schema",
        "drop view",
    ]
    for kw in destructive_keywords:
        if kw in text:
            msg = (
                f"Destructive operation {kw.upper()!r} is not supported in additive billing fixture"
            )
            return False, msg

    # Check if it matches supported additive billing migration
    supported_indicators = [
        "payment_tier",
        "add column",
        "billing_accounts",
        "billing",
        "additive",
        "tier",
    ]
    if not any(ind in text for ind in supported_indicators):
        return (
            False,
            "Change request intent does not match supported synthetic billing migration fixture",
        )

    return True, ""


def build_standard_demo_registry(
    tenant_id: str,
    now: Optional[datetime] = None,
) -> InMemoryAgentRegistry:
    """Build an in-memory agent registry populated with valid passports for standard roles."""
    if now is None:
        now = datetime.now(timezone.utc)
    ev_reg = QualificationEvidenceRegistry()
    verifier = QualificationEvidenceVerifier(registry=ev_reg)
    registry = InMemoryAgentRegistry(evidence_verifier=verifier)

    roles = {
        "impact_scout": ("1.0.0", ("AST_STATIC_ANALYSIS", "BLAST_RADIUS_ESTIMATION")),
        "policy_guardian": ("1.0.0", ("POLICY_VERIFICATION", "REVERSIBILITY_ANALYSIS")),
        "migration_engineer": ("1.0.0", ("MIGRATION_SYNTHESIS_SQL",)),
        "release_steward": ("1.0.0", ("PR_GENERATION",)),
    }

    for role_id, (rev, caps) in roles.items():
        desc = AgentDescriptor(
            agent_id=f"agent-{role_id.replace('_', '-')}",
            agent_name=role_id.replace("_", " ").title(),
            agent_role=role_id,
            agent_revision=rev,
            description=f"Standard qualified {role_id} revision {rev}",
            declared_capabilities=caps,
        )
        registry.register_agent(desc)

        ev_ids = []
        for cap in caps:
            ev_id = f"ev-qual-{role_id}-{cap.lower()}"
            ev_ids.append(ev_id)
            ev_reg.register_evidence(
                QualificationEvidenceRecord(
                    evidence_id=ev_id,
                    agent_id=desc.agent_id,
                    agent_revision=rev,
                    qualified_capability=cap,
                    scenario_id="SCENARIO_NORMAL_MIGRATION",
                    passed=True,
                    evidence_state=EvidenceState.SIMULATED,
                    evidence_mode=ExecutionEvidenceMode.SIMULATION,
                    producer_kind=EvidenceProducerKind.SIMULATION,
                    evidence_digest="a" * 64,
                    collected_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )

        passport = PassportIssuer.issue_passport(
            PassportIssuanceRequest(
                agent_id=desc.agent_id,
                agent_revision=rev,
                qualified_capabilities=caps,
                qualification_evidence_ids=tuple(ev_ids),
                issuer="qualification_engine",
            ),
            evidence_verifier=verifier,
            now=now,
        )
        registry.register_passport(tenant_id, passport)

    return registry


class SagaExecutionResult(BaseModel):
    """Immutable result of a ChangeSaga run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    correlation_id: str
    initial_state: ChangeState
    final_state: ChangeState
    is_completed: bool
    autonomy_class: Optional[AutonomyClass] = None
    stopped_reason: Optional[str] = None
    events_emitted: int
    tasks_executed: int
    evidence_collected: int
    checkpoints_created: int
    timeline_digest: Optional[str] = None
    approval_card: Optional[ApprovalCompressionCard] = None


class ChangeSagaOrchestrator:
    """Stateful, event-driven, persisted saga orchestrator coordinating ChangeMesh lifecycle."""

    def __init__(
        self,
        repository: SagaStateRepository,
        event_bus: LocalEventBus | EventPublisher,
        *,
        orchestrator_id: str = "agent-change-orchestrator",
        orchestrator_revision: str = "1.0.0",
        timeline: Optional[CausalEventTimeline] = None,
        agent_registry: Optional[AgentRegistry] = None,
        policy_gate: Optional[PolicyGuardianGate] = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.orchestrator_id = orchestrator_id
        self.orchestrator_revision = orchestrator_revision
        self.timeline = timeline
        self.agent_registry = agent_registry
        self.policy_gate = policy_gate or PolicyGuardianGate()
        self._topology = get_canonical_topology()

    def run_saga(
        self,
        tenant_id: str,
        request: ChangeRequest,
        *,
        evidence_mode: ExecutionEvidenceMode = ExecutionEvidenceMode.SIMULATION,
        initial_memory_records: Sequence[MemoryRecord] = (),
        stop_at_state: Optional[ChangeState] = None,
        rehearsal_scenario: Optional[ShadowScenario] = None,
        now: Optional[datetime] = None,
    ) -> SagaExecutionResult:
        """Execute the end-to-end ChangeMesh lifecycle saga synchronously and deterministically."""
        if now is None:
            now = datetime.now(timezone.utc)
        tid = validate_tenant_id(tenant_id)

        # -------------------------------------------------------------------------
        # Pre-Persistence Intake Secret Boundary (Fail Closed on Credentials in Identity/Structure)
        # -------------------------------------------------------------------------
        for id_field_name, id_val in [
            ("request_id", request.request_id),
            ("requested_by", request.requested_by),
        ]:
            if any(pattern.search(id_val) for pattern in _SECRET_REPLACEMENT_PATTERNS):
                raise ValueError(
                    f"Secret/credential detected in structural identity field {id_field_name!r}; "
                    "refusing intake before state persistence"
                )

        for target_sys in request.target_systems:
            if any(pattern.search(target_sys) for pattern in _SECRET_REPLACEMENT_PATTERNS):
                raise ValueError(
                    "Secret/credential detected in target_systems field; "
                    "refusing intake before state persistence"
                )

        # Enforce Mode Honesty: Local saga operations cannot be LIVE_WRITE without provider write
        if evidence_mode == ExecutionEvidenceMode.LIVE_WRITE:
            raise ValueError(
                "LIVE_WRITE mode cannot be claimed for local saga execution without real "
                "credential-backed external provider mutation"
            )

        # -------------------------------------------------------------------------
        # Ensure Tenant Record Exists
        # -------------------------------------------------------------------------
        tenant = self.repository.get_tenant(tid)
        if tenant is None:
            tenant = TenantRecord(
                tenant_id=tid,
                name=f"Tenant {tid}",
                created_at=now,
                updated_at=now,
            )
            self.repository.create_tenant(tenant)

        # -------------------------------------------------------------------------
        # Initialize Workflow Identity and Timeline
        # -------------------------------------------------------------------------
        change_id = f"change-{uuid.uuid4().hex[:12]}"
        correlation_id = request.request_id

        if self.timeline is None:
            self.timeline = CausalEventTimeline(change_id)
        else:
            self.timeline.change_id = change_id

        # Sanitize free-form user input to guarantee zero secrets in state & wire payloads
        clean_title = sanitize_secrets_in_text(request.title)
        clean_description = sanitize_secrets_in_text(request.description)

        # State tracking
        current_state = ChangeState.RECEIVED
        last_event_id: Optional[str] = None
        event_seq = 0
        events_emitted = 0
        tasks_executed = 0
        evidence_collected = 0
        checkpoints_created = 0
        active_autonomy_class: Optional[AutonomyClass] = None
        active_approval_card: Optional[ApprovalCompressionCard] = None

        # -------------------------------------------------------------------------
        # Event Emission & State Persistence Helper (Persistence-Before-Publish)
        # -------------------------------------------------------------------------
        def transition_and_persist(
            target_state: ChangeState,
            reason: str,
            producer_id: str,
            producer_role: str,
            producer_revision: str,
            payload_summary: Mapping[str, Any],
        ) -> EventEnvelope:
            nonlocal current_state, last_event_id, event_seq, events_emitted

            # 1. Enforce lifecycle transition rules (strict enum type check)
            if current_state != target_state:
                require_transition(current_state, target_state)

            sanitized_reason = sanitize_secrets_in_text(reason)
            sanitized_payload = redact_mapping(payload_summary)
            # Ensure no raw secret strings remain in payload
            sanitized_payload = {
                k: sanitize_secrets_in_text(v) if isinstance(v, str) else v
                for k, v in sanitized_payload.items()
            }

            # 2. Persist authoritative state in repository FIRST (optimistic concurrency)
            existing_record = self.repository.get_change(tid, change_id)
            if existing_record is None:
                new_record = ChangeRecord(
                    tenant_id=tid,
                    change_id=change_id,
                    correlation_id=correlation_id,
                    title=clean_title,
                    description=clean_description,
                    target_systems=tuple(request.target_systems),
                    data_classification=request.data_classification,
                    requested_by=request.requested_by,
                    requested_at=now,
                    state=target_state,
                    state_updated_at=now,
                    state_reason=sanitized_reason,
                    assigned_orchestrator_revision=self.orchestrator_revision,
                    created_at=now,
                    updated_at=now,
                )
                self.repository.create_change(tid, new_record)
            else:
                updated_record = existing_record.model_copy(
                    update={
                        "state": target_state,
                        "state_updated_at": now,
                        "state_reason": sanitized_reason,
                        "autonomy_class": active_autonomy_class or existing_record.autonomy_class,
                        "updated_at": now,
                    }
                )
                self.repository.update_change(
                    tid, updated_record, expected_version=existing_record.version
                )

            # 3. Only after persistence succeeds, publish wire message & update timeline
            event_seq += 1
            event_id = f"evt-{change_id}-{event_seq:03d}-{target_state.value.lower()}"
            idempotency_key = f"idem_lc_{change_id}_{target_state.value.lower()}_{event_seq}"

            provenance = AgentRevisionProvenance(
                agent_id=producer_id,
                agent_revision=producer_revision,
                role=producer_role,
            )

            envelope = EventEnvelope(
                schema_version=CANONICAL_SCHEMA_VERSION,
                event_id=event_id,
                change_id=change_id,
                causation_id=last_event_id,
                correlation_id=correlation_id,
                producer_id=producer_id,
                producer_revision=producer_revision,
                producer_role=producer_role,
                agent_provenance=provenance,
                timestamp=now,
                idempotency_key=idempotency_key,
            )

            route = self._topology.get_route_for_state(target_state)
            topic_id = route.primary_topic_id if route else "changemesh-lifecycle-v1"

            # Pre-dispatch secret scanning fails closed on residual secrets
            scan_payload_for_secrets(sanitized_payload)

            wire_msg = EventWireMessage(
                topic_id=topic_id,
                envelope=envelope,
                payload=sanitized_payload,
                published_at=now,
            )

            if isinstance(self.event_bus, LocalEventBus):
                self.event_bus.publish_message(wire_msg)
            else:
                self.event_bus.publish(wire_msg)

            if self.timeline is not None:
                self.timeline.record_event(
                    envelope, topic_id=topic_id, payload=sanitized_payload, transport="LOCAL"
                )

            events_emitted += 1
            last_event_id = event_id
            current_state = target_state
            return envelope

        # -------------------------------------------------------------------------
        # STAGE 0: Intake & Initial State (RECEIVED)
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.RECEIVED,
            reason="Change request received and admitted",
            producer_id=self.orchestrator_id,
            producer_role="change_orchestrator",
            producer_revision=self.orchestrator_revision,
            payload_summary={
                "intent": clean_description,
                "targets": list(request.target_systems),
            },
        )

        if stop_at_state == ChangeState.RECEIVED:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state RECEIVED",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # Intent Binding Validation (Fail Closed for Unsupported / Destructive Operations)
        # -------------------------------------------------------------------------
        is_supported_intent, unsupported_reason = validate_supported_change_intent(request)
        if not is_supported_intent:
            transition_and_persist(
                target_state=ChangeState.BLOCKED,
                reason=f"UNSUPPORTED_OPERATION: {unsupported_reason}",
                producer_id=self.orchestrator_id,
                producer_role="change_orchestrator",
                producer_revision=self.orchestrator_revision,
                payload_summary={
                    "action": "unsupported_change_intent_blocked",
                    "reason": unsupported_reason,
                },
            )
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.BLOCKED,
                is_completed=False,
                autonomy_class=AutonomyClass.BLOCKED,
                stopped_reason=f"UNSUPPORTED_OPERATION: {unsupported_reason}",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 1: Discover (DISCOVERING) — Real P-15 Component Execution
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.DISCOVERING,
            reason="Beginning impact discovery and blast-radius analysis",
            producer_id="agent-impact-scout",
            producer_role="impact_scout",
            producer_revision="1.0.0",
            payload_summary={"action": "discover_blast_radius"},
        )

        # Execute Impact Scout Discovery via real RepositoryScanner and GraphTraverser
        scanner = RepositoryScanner()
        scan_findings = scanner.scan_files(
            changed_files=["migrations/001_add_billing_column.sql"],
            all_files=[
                "migrations/001_add_billing_column.sql",
                "src/billing/service.py",
                "schema/billing.sql",
            ],
        )

        graph = build_synthetic_billing_graph()
        traverser = GraphTraverser()
        impacted_assets = tuple(
            traverser.find_downstream_impact(
                graph, changed_node_ids={"billing-migration-001", "invoice-schema"}
            )
        )

        merger = BlastRadiusMerger()
        blast_radius_artifact = merger.merge(
            change_id=change_id,
            scan_findings=scan_findings,
            impacted_assets=impacted_assets,
            evidence_mode=evidence_mode.value,
        )

        # Persist Discover Task & Evidence
        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-discover-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-impact-scout",
                agent_role="impact_scout",
                agent_revision="1.0.0",
                action_class="BLAST_RADIUS_ANALYSIS",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=(
                    f"Blast radius calculated: {len(blast_radius_artifact.impacted_assets)} assets"
                ),
                artifact_hashes=({"blast_radius_digest": blast_radius_artifact.digest},),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-discover-{change_id}",
                subject="blast_radius",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id="agent-impact-scout",
                agent_revision="1.0.0",
                artifact_digests=(blast_radius_artifact.digest,),
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.DISCOVERING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state DISCOVERING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 2: Qualify (QUALIFYING) — Real P-12 Agent Registry / Capability Passport
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.QUALIFYING,
            reason="Verifying agent fleet qualifications and capability requirements",
            producer_id=self.orchestrator_id,
            producer_role="change_orchestrator",
            producer_revision=self.orchestrator_revision,
            payload_summary={"action": "verify_agent_capabilities"},
        )

        # Initialize registry if not supplied
        active_registry = self.agent_registry
        if active_registry is None:
            active_registry = build_standard_demo_registry(tid, now=now)
            self.agent_registry = active_registry

        # Verify Capability Requirements via AgentRegistry & CapabilityPassport
        std_reqs = get_standard_demo_requirements()
        qualification_failed = False
        qualification_failure_reason = ""
        verified_role_count = 0

        evidence_verifier = (
            getattr(active_registry, "_evidence_verifier", None) or QualificationEvidenceVerifier()
        )

        for role_id, req in std_reqs.items():
            agent_id = f"agent-{role_id.replace('_', '-')}"
            descriptor = active_registry.get_descriptor(agent_id, "1.0.0")
            passport = active_registry.get_active_passport(tid, agent_id, "1.0.0")

            if descriptor is None or passport is None:
                qualification_failed = True
                qualification_failure_reason = (
                    f"No active qualified passport found for required role {role_id!r}"
                )
                break

            val_res = PassportVerifier.verify(
                passport=passport,
                evidence_verifier=evidence_verifier,
                requirement=req,
                expected_revision="1.0.0",
                now=now,
            )
            if not val_res.is_valid:
                qualification_failed = True
                qualification_failure_reason = (
                    f"Passport validation failed for role {role_id!r}: {val_res.failure_reason}"
                )
                break

            verified_role_count += 1

        if qualification_failed:
            transition_and_persist(
                target_state=ChangeState.BLOCKED,
                reason=f"Agent qualification failed closed: {qualification_failure_reason}",
                producer_id=self.orchestrator_id,
                producer_role="change_orchestrator",
                producer_revision=self.orchestrator_revision,
                payload_summary={
                    "action": "agent_qualification_failed",
                    "reason": qualification_failure_reason,
                },
            )
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.BLOCKED,
                is_completed=False,
                autonomy_class=AutonomyClass.BLOCKED,
                stopped_reason=f"QUALIFICATION_FAILED: {qualification_failure_reason}",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-qualify-{change_id}",
                sequence_number=tasks_executed,
                agent_id=self.orchestrator_id,
                agent_role="qualifier",
                agent_revision=self.orchestrator_revision,
                action_class="CAPABILITY_QUALIFICATION",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=f"Verified qualifications for {verified_role_count} agent roles",
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-qualify-{change_id}",
                subject="capability_qualification",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id=self.orchestrator_id,
                agent_revision=self.orchestrator_revision,
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.QUALIFYING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state QUALIFYING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 3: Rehearse (REHEARSING) — Real P-13 ShadowLabRunner
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.REHEARSING,
            reason="Executing ShadowLab simulated twin rehearsal",
            producer_id="agent-shadowlab-runner",
            producer_role="shadowlab",
            producer_revision="1.0.0",
            payload_summary={
                "action": "shadowlab_rehearsal",
                "scenario": (
                    rehearsal_scenario.scenario_id
                    if rehearsal_scenario
                    else "SCENARIO_NORMAL_MIGRATION"
                ),
            },
        )

        # Execute Rehearsal Scenario using real ShadowLabRunner
        scenario = (
            rehearsal_scenario or get_standard_shadow_scenarios()["SCENARIO_NORMAL_MIGRATION"]
        )
        rehearsal_outcome = ShadowLabRunner.run_scenario(scenario)

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-rehearse-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-shadowlab-runner",
                agent_role="shadowlab",
                agent_revision="1.0.0",
                action_class="REHEARSAL_SIMULATION",
                status=TaskStatus.COMPLETED if rehearsal_outcome.passed else TaskStatus.FAILED,
                started_at=now,
                completed_at=now,
                output_summary=f"Rehearsal {scenario.scenario_id}: {rehearsal_outcome.details}",
                artifact_hashes=({"rehearsal_digest": rehearsal_outcome.evidence_digest},),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-rehearse-{change_id}",
                subject="shadowlab_rehearsal",
                state=rehearsal_outcome.evidence_state,
                collection_mode=ExecutionEvidenceMode.SIMULATION,
                producer_kind=EvidenceProducerKind.SIMULATION,
                agent_id="agent-shadowlab-runner",
                agent_revision="1.0.0",
                artifact_digests=(rehearsal_outcome.evidence_digest,),
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.REHEARSING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state REHEARSING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 4: Ground (GROUNDED) — Epistemic Memory Trust & Deterministic Policy
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.GROUNDED,
            reason="Grounding change in epistemic memory trust and deterministic policy rules",
            producer_id="agent-memory-trust",
            producer_role="memory_trust",
            producer_revision="1.0.0",
            payload_summary={
                "action": "epistemic_grounding",
                "memory_count": len(initial_memory_records),
            },
        )

        # Evaluate Epistemic Memory Trust
        trusted_memory_refs = []
        for mem in initial_memory_records:
            eval_res = MemoryTrustEvaluator.evaluate(mem, now=now)
            if eval_res.trust_class == EpistemicTrustClass.ACCEPTED_TRUSTED:
                trusted_memory_refs.append(mem.memory_id)

        # Evaluate Deterministic Policy Pre-checks
        policy_checker = DeterministicPolicyChecker()
        policy_res = policy_checker.evaluate(
            input_text="ALTER TABLE billing_accounts ADD COLUMN payment_tier VARCHAR(32);",
            tool_ids=["tool-migration-planner", "tool-artifact-generator"],
            target_paths=["synthetic/migrations/001_add_billing_column.sql"],
            action_type="SCHEMA_MIGRATION",
            data_classification=request.data_classification.value,
            change_id=change_id,
        )
        if policy_res.blocked_count > 0:
            transition_and_persist(
                target_state=ChangeState.BLOCKED,
                reason=f"Deterministic policy blocked change: {policy_res.findings}",
                producer_id="agent-policy-guardian",
                producer_role="policy_guardian",
                producer_revision="1.0.0",
                payload_summary={
                    "action": "policy_precheck_blocked",
                    "findings": list(policy_res.findings),
                },
            )
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.BLOCKED,
                is_completed=False,
                autonomy_class=AutonomyClass.BLOCKED,
                stopped_reason="BLOCKED by deterministic policy pre-checks",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-ground-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-memory-trust",
                agent_role="memory_trust",
                agent_revision="1.0.0",
                action_class="EPISTEMIC_GROUNDING",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=(
                    f"Epistemic grounding complete: {len(trusted_memory_refs)} trusted memory refs"
                ),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-ground-{change_id}",
                subject="epistemic_grounding",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id="agent-memory-trust",
                agent_revision="1.0.0",
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.GROUNDED:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state GROUNDED",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 5: Authorize (AUTHORIZED / AWAITING_AUTHORITY / BLOCKED)
        # -------------------------------------------------------------------------
        # Determine Reversibility Classification deterministically (zero caller overrides)
        sample_sql_up = "ALTER TABLE billing_accounts ADD COLUMN payment_tier VARCHAR(32);"
        sample_sql_down = "ALTER TABLE billing_accounts DROP COLUMN payment_tier;"
        blast_score = (
            min(1.0, len(blast_radius_artifact.impacted_assets) * 0.1)
            if blast_radius_artifact.impacted_assets
            else 0.2
        )

        rev_assessment = ReversibilityClassifier.classify_sql(
            change_id=change_id,
            sql_up=sample_sql_up,
            sql_down=sample_sql_down,
            blast_radius_score=blast_score,
        )

        rehearsal_status = (
            RehearsalStatus.REHEARSAL_PASSED
            if rehearsal_outcome.passed
            else RehearsalStatus.REHEARSAL_FAILED
        )

        policy_inputs = DeterministicPolicyInputs(
            change_id=change_id,
            blast_radius_score=blast_score,
            blast_radius_source="impact_scout",
            blast_radius_reason=(
                f"Impacted assets count: {len(blast_radius_artifact.impacted_assets)}"
            ),
            reversibility_class=rev_assessment.reversibility_class,
            has_down_migration=rev_assessment.has_down_migration,
            rollback_summary=rev_assessment.rollback_plan_summary,
            reversibility_source="reversibility_classifier",
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
            privilege_source="migration_planner",
            data_classification=request.data_classification,
            sensitivity_source="change_request",
            evidence_state=EvidenceState.PASS,
            evidence_mode=evidence_mode,
            evidence_digests=(blast_radius_artifact.digest,),
            evidence_source="impact_scout",
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            novelty_source="novelty_classifier",
            rehearsal_status=rehearsal_status,
            rehearsal_digests=(rehearsal_outcome.evidence_digest,),
            rehearsal_source="shadowlab",
        )

        gate_result = self.policy_gate.evaluate_inputs(
            policy_inputs,
            assessment=rev_assessment,
            now=now,
        )
        active_autonomy_class = gate_result.autonomy_class

        # Check for HARD BLOCKER (BLOCKED)
        if gate_result.autonomy_class == AutonomyClass.BLOCKED:
            transition_and_persist(
                target_state=ChangeState.BLOCKED,
                reason=f"Policy Guardian Gate issued hard blocker: {gate_result.decision_summary}",
                producer_id="agent-policy-guardian",
                producer_role="policy_guardian",
                producer_revision="1.0.0",
                payload_summary={
                    "autonomy_class": gate_result.autonomy_class.value,
                    "reversibility_class": rev_assessment.reversibility_class.value,
                    "decision_summary": gate_result.decision_summary,
                },
            )
            # Return BLOCKED result with zero approval card and zero execution tasks
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.BLOCKED,
                is_completed=False,
                autonomy_class=AutonomyClass.BLOCKED,
                stopped_reason=f"BLOCKED: {gate_result.decision_summary}",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # Check for HUMAN_AUTHORITY_REQUIRED
        if (
            gate_result.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
            and not gate_result.is_authorized
        ):
            active_approval_card = gate_result.compression_card
            transition_and_persist(
                target_state=ChangeState.AWAITING_AUTHORITY,
                reason=(
                    "Policy Gate determined Human Authority is required: "
                    f"{gate_result.decision_summary}"
                ),
                producer_id="agent-policy-guardian",
                producer_role="policy_guardian",
                producer_revision="1.0.0",
                payload_summary={
                    "autonomy_class": gate_result.autonomy_class.value,
                    "reversibility_class": rev_assessment.reversibility_class.value,
                    "decision_summary": gate_result.decision_summary,
                },
            )

            # Persist Approval Record derived strictly from compression card
            if gate_result.compression_card is not None:
                card = gate_result.compression_card
                self.repository.create_approval(
                    tid,
                    change_id,
                    ApprovalRecord(
                        tenant_id=tid,
                        change_id=change_id,
                        card_id=card.card_id,
                        authority_slot_ref=card.authority_slot_ref,
                        decision_question=card.decision_question,
                        decision_options=card.decision_options,
                        policy_reason=card.policy_reason,
                        action_scope=card.action_scope,
                        completed_work_summary=card.completed_work_summary,
                        rehearsed_work_summary=card.rehearsed_work_summary,
                        remaining_decision_summary=card.remaining_decision_summary,
                        evidence_refs=card.evidence_refs,
                        card_created_at=card.created_at,
                        resolution_status=ApprovalResolutionStatus.PENDING,
                        created_at=now,
                        updated_at=now,
                    ),
                )

            # Stop cleanly at AWAITING_AUTHORITY — zero execution and zero Release Steward mutation!
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                approval_card=active_approval_card,
                stopped_reason=(
                    "Awaiting verified human authority decision; execution halted cleanly"
                ),
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # Autonomous Authorization Granted (AUTO_EXECUTE or REHEARSE_THEN_EXECUTE)
        transition_and_persist(
            target_state=ChangeState.AUTHORIZED,
            reason=f"Authorized under autonomy class {gate_result.autonomy_class.value}",
            producer_id="agent-policy-guardian",
            producer_role="policy_guardian",
            producer_revision="1.0.0",
            payload_summary={
                "autonomy_class": gate_result.autonomy_class.value,
                "reversibility_class": rev_assessment.reversibility_class.value,
                "decision_summary": gate_result.decision_summary,
            },
        )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-authorize-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-policy-guardian",
                agent_role="policy_guardian",
                agent_revision="1.0.0",
                action_class="AUTHORIZATION_GATE",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=f"Authorized autonomously as {gate_result.autonomy_class.value}",
                created_at=now,
                updated_at=now,
            ),
        )

        if stop_at_state == ChangeState.AUTHORIZED:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                stopped_reason="Stopped at requested state AUTHORIZED",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 6: Execute (EXECUTING) — Real P-17 Migration Plan & Manifest
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.EXECUTING,
            reason="Executing change synthesis and artifact generation",
            producer_id="agent-migration-engineer",
            producer_role="migration_engineer",
            producer_revision="1.0.0",
            payload_summary={"action": "generate_migration_artifacts"},
        )

        # Generate Migration Artifacts
        mig_gen = MigrationPlanGenerator()
        mig_plan = mig_gen.generate_plan(
            change_id=change_id,
            source_schema="billing_accounts_v1",
            target_schema="billing_accounts_v2",
            column_additions=["payment_tier"],
            table_name="billing_accounts",
        )

        manifest_gen = ManifestGenerator()
        file_manifest = manifest_gen.generate_manifest(
            change_id=change_id,
            plan_id=mig_plan.plan_id,
            file_contents={
                "migrations/001_add_billing_column.sql": (
                    "ALTER TABLE billing_accounts ADD COLUMN payment_tier VARCHAR(32);"
                )
            },
        )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-execute-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-migration-engineer",
                agent_role="migration_engineer",
                agent_revision="1.0.0",
                action_class="MIGRATION_EXECUTION",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=(
                    f"Synthesized migration with {len(mig_plan.steps)} steps and "
                    f"{len(file_manifest.entries)} files"
                ),
                artifact_hashes=({"manifest_hash": file_manifest.manifest_hash},),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-execute-{change_id}",
                subject="migration_artifacts",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id="agent-migration-engineer",
                agent_revision="1.0.0",
                artifact_digests=(file_manifest.manifest_hash,),
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.EXECUTING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                stopped_reason="Stopped at requested state EXECUTING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 7: Verify (VERIFYING) — Real P-18 Claims, Audit, Reconciliation
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.VERIFYING,
            reason="Executing independent evidence audit and deterministic reconciliation",
            producer_id="agent-evidence-auditor",
            producer_role="evidence_auditor",
            producer_revision="1.0.0",
            payload_summary={"action": "audit_and_reconcile"},
        )

        # Derive Claims & Build Audit Bundle from request success criteria
        claim_engine = ClaimDerivationEngine()
        if request.success_criteria:
            criteria_inputs = [
                {"id": crit.criterion_id, "statement": crit.description}
                for crit in request.success_criteria
            ]
        else:
            criteria_inputs = [
                {"id": "crit-01", "statement": "Rehearsal completed with zero unhandled faults."},
                {
                    "id": "crit-02",
                    "statement": "Migration manifest contains deterministic file hashes.",
                },
            ]
        claims = claim_engine.derive_claims(
            success_criteria=criteria_inputs,
            evidence_refs=[f"ev-rehearse-{change_id}", f"ev-execute-{change_id}"],
        )

        bundle_builder = AuditBundleBuilder()
        audit_bundle = bundle_builder.build_bundle(
            change_id=change_id,
            claims=claims,
            evidence_store={
                f"ev-rehearse-{change_id}": (
                    f"Rehearsal outcome: {rehearsal_outcome.evidence_state.value} "
                    f"with digest {rehearsal_outcome.evidence_digest}"
                ),
                f"ev-execute-{change_id}": (
                    f"Execution manifest: Valid SHA-256 hash {file_manifest.manifest_hash}"
                ),
            },
        )

        auditor = SemanticAuditor()
        audit_report = auditor.audit_claims(audit_bundle, use_live_gemini=False)

        reconciler = DeterministicReconciler()
        for res in audit_report.results:
            recon_res = reconciler.reconcile(
                audit_result=res,
                deterministic_state="PASS",
                change_id=change_id,
            )
            if not recon_res.deterministic_state_preserved:
                raise ValueError("Semantic audit failed to preserve deterministic state!")

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-verify-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-evidence-auditor",
                agent_role="evidence_auditor",
                agent_revision="1.0.0",
                action_class="EVIDENCE_AUDIT_RECONCILIATION",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=(
                    f"Audit completed: {audit_report.supports_count} supported claims reconciled"
                ),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-verify-{change_id}",
                subject="audit_reconciliation",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id="agent-evidence-auditor",
                agent_revision="1.0.0",
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.VERIFYING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                stopped_reason="Stopped at requested state VERIFYING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 8: Certify (CERTIFYING -> COMPLETE) — Checkpoint & Complete
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.CERTIFYING,
            reason="Certifying complete proof-carrying change evidence package",
            producer_id=self.orchestrator_id,
            producer_role="change_orchestrator",
            producer_revision=self.orchestrator_revision,
            payload_summary={"action": "certify_change_evidence"},
        )

        # Create Durable Checkpoint
        checkpoints_created += 1
        SagaCheckpointManager.create_checkpoint(
            repo=self.repository,
            tenant_id=tid,
            change_id=change_id,
            lifecycle_state=ChangeState.CERTIFYING,
            completed_task_ids=(
                f"task-discover-{change_id}",
                f"task-qualify-{change_id}",
                f"task-rehearse-{change_id}",
                f"task-ground-{change_id}",
                f"task-authorize-{change_id}",
                f"task-execute-{change_id}",
                f"task-verify-{change_id}",
            ),
            now=now,
        )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-certify-{change_id}",
                sequence_number=tasks_executed,
                agent_id=self.orchestrator_id,
                agent_role="change_orchestrator",
                agent_revision=self.orchestrator_revision,
                action_class="SAGA_CERTIFICATION",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary="Certified complete evidence package",
                created_at=now,
                updated_at=now,
            ),
        )

        # Final Transition to COMPLETE
        transition_and_persist(
            target_state=ChangeState.COMPLETE,
            reason="Change saga completed successfully with all verification gates passed",
            producer_id=self.orchestrator_id,
            producer_role="change_orchestrator",
            producer_revision=self.orchestrator_revision,
            payload_summary={
                "status": "SUCCESS",
                "tasks_executed": tasks_executed,
                "evidence_collected": evidence_collected,
            },
        )

        # Update final evidence summary in ChangeRecord
        final_record = self.repository.get_change(tid, change_id)
        if final_record is not None:
            updated_final = final_record.model_copy(
                update={
                    "evidence_summary": {
                        "pass": evidence_collected - 1,  # 1 was SIMULATED
                        "fail": 0,
                        "simulated": 1,
                        "blocked": 0,
                    },
                    "updated_at": now,
                }
            )
            self.repository.update_change(tid, updated_final, expected_version=final_record.version)

        return SagaExecutionResult(
            tenant_id=tid,
            change_id=change_id,
            correlation_id=correlation_id,
            initial_state=ChangeState.RECEIVED,
            final_state=ChangeState.COMPLETE,
            is_completed=True,
            autonomy_class=active_autonomy_class,
            stopped_reason=None,
            events_emitted=events_emitted,
            tasks_executed=tasks_executed,
            evidence_collected=evidence_collected,
            checkpoints_created=checkpoints_created,
            timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
        )
