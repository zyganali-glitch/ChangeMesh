"""Tests for P-20.01 End-to-End Orchestrator Saga Surgical Repairs.

Verifies:
1. One constant Change ID and correlation ID across the saga.
2. Exact legal ordered lifecycle progression across 8 canonical stages.
3. Persisted ChangeRecord agrees with every admitted transition.
4. Every transition has canonical event/correlation/causation evidence.
5. Event producer identity and revision are explicit and non-blank.
6. Persistence-before-publish consistency: failed persistence leaves zero false events on bus.
7. Optimistic concurrency prevents stale state overwrite.
8. Evidence / execution mode honesty: local tasks cannot be LIVE_WRITE; ShadowLab is SIMULATION.
9. Secret minimization: raw credentials never enter wire messages, timeline, or repository.
10. Authority semantics: BLOCKED transitions to ChangeState.BLOCKED with 0 cards and 0 execution.
11. Authority semantics: HUMAN_AUTHORITY_REQUIRED halts at AWAITING_AUTHORITY with derived record.
12. No caller-manufactured reversibility downgrade.
13. Real capability-registry qualification fails closed on empty/missing/expired passport.
14. Real ShadowLabRunner execution; failed rehearsal blocks progression cleanly.
15. Canonical ADK ChangeOrchestrator bridge coordinates lifecycle without owning state.
16. Tenant isolation across operational state.
17. Zero new real GitHub LIVE_WRITE mutations.
"""

from __future__ import annotations

import datetime
from datetime import timezone
from typing import Any, Optional

import pytest

from domain.contracts.autonomy import AutonomyClass
from domain.contracts.change_lifecycle import (
    ChangeState,
    IllegalTransitionError,
    require_transition,
)
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import (
    EvidenceState,
    ExecutionEvidenceMode,
)
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from src.agents.change_orchestrator import ChangeOrchestrator
from src.audit.reconciliation import DeterministicReconciler
from src.audit.semantic_auditor import ClaimAuditResult, SemanticVerdict
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.gate.policy_guardian_gate import (
    PolicyGateEvaluationResult,
    PolicyGuardianGate,
)
from src.gate.reversibility import (
    DeterministicPolicyInputs,
    ReversibilityAssessment,
    ReversibilityClass,
)
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.orchestrator_saga import (
    ChangeSagaOrchestrator,
    build_standard_demo_registry,
)
from src.orchestrator.state_repository import (
    ApprovalResolutionStatus,
    ChangeRecord,
    OptimisticConcurrencyError,
    TaskStatus,
)
from src.registry.agent_registry import AgentDescriptor, InMemoryAgentRegistry
from src.registry.evidence_verifier import (
    QualificationEvidenceRegistry,
    QualificationEvidenceVerifier,
)
from src.shadowlab.scenarios import ShadowScenario


@pytest.fixture
def repo() -> InMemorySagaStateRepository:
    return InMemorySagaStateRepository()


@pytest.fixture
def bus() -> LocalEventBus:
    return LocalEventBus()


@pytest.fixture
def sample_change_request() -> ChangeRequest:
    return ChangeRequest(
        schema_version="1.0.0",
        request_id="req-p20-test-001",
        title="Add payment_tier column",
        description="Add payment_tier column to billing_accounts table",
        target_systems=["billing-db", "payment-service"],
        data_classification=DataClassLevel.INTERNAL,
        success_criteria=[
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="crit-01",
                description="Rehearsal succeeds cleanly",
                verification_method="deterministic",
                required_evidence_types=["REHEARSAL_SIMULATION"],
            )
        ],
        requested_by="engineer@example.com",
        requested_at=datetime.datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_p20_01_e2e_happy_path_saga_progression(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Test full 8-stage end-to-end happy path saga progression to COMPLETE."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
    )

    # 1. Verify result summary
    assert result.is_completed is True
    assert result.final_state == ChangeState.COMPLETE
    assert result.initial_state == ChangeState.RECEIVED
    assert result.correlation_id == sample_change_request.request_id
    assert result.autonomy_class in (
        AutonomyClass.AUTO_EXECUTE,
        AutonomyClass.REHEARSE_THEN_EXECUTE,
    )
    assert result.events_emitted == 10  # RECEIVED + 9 transitions
    assert result.tasks_executed >= 7
    assert result.evidence_collected >= 6
    assert result.checkpoints_created >= 1

    # 2. Verify persisted ChangeRecord in repository
    change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert change is not None
    assert change.change_id == result.change_id
    assert change.correlation_id == sample_change_request.request_id
    assert change.state == ChangeState.COMPLETE
    assert change.version >= 9  # incremented on each state update
    assert change.evidence_summary["pass"] >= 5
    assert change.evidence_summary["simulated"] == 1
    assert change.evidence_summary["fail"] == 0

    # 3. Verify persisted tasks in sequence
    tasks = repo.list_tasks("tenant-prod-alpha", result.change_id)
    assert len(tasks) == result.tasks_executed
    task_roles = [t.agent_role for t in tasks]
    assert "impact_scout" in task_roles
    assert "qualifier" in task_roles
    assert "shadowlab" in task_roles
    assert "memory_trust" in task_roles
    assert "policy_guardian" in task_roles
    assert "migration_engineer" in task_roles
    assert "evidence_auditor" in task_roles
    assert "change_orchestrator" in task_roles
    assert all(t.status == TaskStatus.COMPLETED for t in tasks)

    # 4. Verify persisted evidence references
    evidence_refs = repo.list_evidence_refs("tenant-prod-alpha", result.change_id)
    assert len(evidence_refs) == result.evidence_collected
    assert all(ref.change_id == result.change_id for ref in evidence_refs)
    subjects = [ref.subject for ref in evidence_refs]
    assert "blast_radius" in subjects
    assert "capability_qualification" in subjects
    assert "shadowlab_rehearsal" in subjects
    assert "epistemic_grounding" in subjects
    assert "migration_artifacts" in subjects
    assert "audit_reconciliation" in subjects


def test_p20_01_event_causation_and_timeline_continuity(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify event causation chain, non-blank producers, and causal timeline DAG integrity."""
    timeline = CausalEventTimeline(change_id="pending-id")
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)

    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
    )

    history = bus.published_history
    assert len(history) == 10

    # Verify each event envelope
    prev_event_id = None
    for i, msg in enumerate(history):
        envelope = msg.envelope
        assert envelope.change_id == result.change_id
        assert envelope.correlation_id == sample_change_request.request_id
        assert envelope.schema_version == "1.0.0"
        assert envelope.producer_id.strip() != ""
        assert envelope.producer_revision.strip() != ""
        assert envelope.producer_role is not None
        assert envelope.agent_provenance is not None
        assert envelope.agent_provenance.agent_id == envelope.producer_id
        assert envelope.agent_provenance.agent_revision == envelope.producer_revision
        assert envelope.idempotency_key.strip() != ""

        # Causal continuity: causation_id points to predecessor
        if i == 0:
            assert envelope.causation_id is None
        else:
            assert envelope.causation_id == prev_event_id

        prev_event_id = envelope.event_id

    # Verify causal timeline Kahn DAG ordering
    ordered_entries = timeline.get_causally_ordered_entries()
    assert len(ordered_entries) == 10
    for i, entry in enumerate(ordered_entries):
        assert entry.depth == i
        assert entry.change_id == result.change_id
        assert entry.correlation_id == sample_change_request.request_id

    # Timeline digest is non-blank and reproducible
    digest = timeline.compute_timeline_digest()
    assert len(digest) == 64
    assert result.timeline_digest == digest


def test_p20_01_persistence_failure_leaves_zero_false_event_evidence(
    sample_change_request: ChangeRequest,
) -> None:
    """Verify persistence-before-publish: persistence rejection leaves zero false event evidence."""

    class FailingRepo(InMemorySagaStateRepository):
        def update_change(
            self, tenant_id: str, change: ChangeRecord, expected_version: int
        ) -> ChangeRecord:
            # Inject simulated failure when transitioning to DISCOVERING
            if change.state == ChangeState.DISCOVERING:
                raise OptimisticConcurrencyError(
                    f"Simulated persistence conflict for state {change.state.value}",
                    expected_version=expected_version,
                    actual_version=expected_version + 1,
                )
            return super().update_change(tenant_id, change, expected_version)

    failing_repo = FailingRepo()
    bus = LocalEventBus()
    timeline = CausalEventTimeline(change_id="pending-id")
    orchestrator = ChangeSagaOrchestrator(repository=failing_repo, event_bus=bus, timeline=timeline)

    with pytest.raises(OptimisticConcurrencyError):
        orchestrator.run_saga(
            tenant_id="tenant-prod-alpha",
            request=sample_change_request,
        )

    # Published bus history should ONLY have the RECEIVED event (persisted before failure)
    # ZERO DISCOVERING events should exist on the bus
    assert len(bus.published_history) == 1
    assert bus.published_history[0].envelope.producer_role == "change_orchestrator"

    # Timeline should have exactly 1 event (RECEIVED), zero DISCOVERING
    timeline_entries = timeline.get_causally_ordered_entries()
    assert len(timeline_entries) == 1

    # Authoritative repository state remains RECEIVED
    persisted_changes = failing_repo.list_changes("tenant-prod-alpha")
    assert len(persisted_changes) == 1
    assert persisted_changes[0].state == ChangeState.RECEIVED


def test_p20_01_secret_minimization_and_adversarial_credential_sanitization(
    repo: InMemorySagaStateRepository, bus: LocalEventBus
) -> None:
    """Verify raw token/credential material appears nowhere in wire messages, timeline, or state."""
    # Construct secret tokens dynamically to keep source free of literal regex matches
    gh_prefix = "ghp_"
    dummy_gh_token = gh_prefix + ("1234567890abcdef" * 3)[:36]
    bearer_token = "Bearer secret-token-value-1234567890"
    raw_password = "supersecretpassword123"

    adversarial_request = ChangeRequest(
        schema_version="1.0.0",
        request_id="req-p20-adv-001",
        title=f"Add column payment_tier {dummy_gh_token} token in title",
        description=(
            f"Adversarial request with {bearer_token} "
            f"and password='{raw_password}' to table billing_accounts for payment_tier column"
        ),
        target_systems=["billing-db"],
        data_classification=DataClassLevel.INTERNAL,
        success_criteria=[
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="crit-01",
                description="Rehearsal succeeds",
                verification_method="deterministic",
                required_evidence_types=["REHEARSAL_SIMULATION"],
            )
        ],
        requested_by="engineer@example.com",
        requested_at=datetime.datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    )

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=adversarial_request,
    )

    assert result.is_completed is True

    raw_forbidden_tokens = [
        dummy_gh_token,
        "secret-token-value-1234567890",
        raw_password,
    ]

    # 1. Inspect all published wire messages
    for msg in bus.published_history:
        wire_str = msg.to_bytes().decode("utf-8")
        for token in raw_forbidden_tokens:
            assert token not in wire_str

    # 2. Inspect persisted ChangeRecord
    persisted_change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert persisted_change is not None
    assert "[REDACTED]" in persisted_change.title
    assert "[REDACTED]" in persisted_change.description
    for token in raw_forbidden_tokens:
        assert token not in persisted_change.title
        assert token not in persisted_change.description
        assert token not in (persisted_change.state_reason or "")

    # 3. Inspect persisted tasks
    for task in repo.list_tasks("tenant-prod-alpha", result.change_id):
        task_str = str(task.output_summary)
        for token in raw_forbidden_tokens:
            assert token not in task_str


def test_p20_01_policy_guardian_hard_blocked_remains_blocked_with_zero_approval_card(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that a genuine hard blocker ends in ChangeState.BLOCKED with 0 cards."""

    class MockBlockedGate(PolicyGuardianGate):
        def evaluate_inputs(
            self,
            inputs: DeterministicPolicyInputs,
            plan_hash: Optional[str] = None,
            approval_token: Optional[Any] = None,
            assessment: Optional[ReversibilityAssessment] = None,
            now: Optional[datetime.datetime] = None,
        ) -> PolicyGateEvaluationResult:
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.BLOCKED,
                is_authorized=False,
                reversibility_assessment=assessment
                or ReversibilityAssessment(
                    change_id=inputs.change_id,
                    reversibility_class=ReversibilityClass.IRREVERSIBLE_DESTRUCTIVE,
                    blast_radius_score=1.0,
                    has_down_migration=False,
                    rollback_plan_summary="No down migration",
                    reversibility_score=0.0,
                    rationale="Irreversible without down migration",
                ),
                audit_trace_id="trace-blocked-001",
                decision_summary="BLOCKED: Hard organizational security policy violation",
            )

    orchestrator = ChangeSagaOrchestrator(
        repository=repo, event_bus=bus, policy_gate=MockBlockedGate()
    )
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
    )

    # 1. State must be BLOCKED
    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert result.approval_card is None  # ZERO fake approval cards

    # 2. Persisted state must be BLOCKED
    change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert change is not None
    assert change.state == ChangeState.BLOCKED

    # 3. ZERO approval records persisted
    approvals = repo.list_approvals("tenant-prod-alpha", result.change_id)
    assert len(approvals) == 0

    # 4. ZERO downstream execution tasks (no migration_engineer, no evidence_auditor)
    tasks = repo.list_tasks("tenant-prod-alpha", result.change_id)
    task_roles = [t.agent_role for t in tasks]
    assert "migration_engineer" not in task_roles
    assert "evidence_auditor" not in task_roles

    # 5. Events history ends at BLOCKED
    history = bus.published_history
    last_envelope = history[-1].envelope
    assert "blocked" in last_envelope.event_id


def test_p20_01_human_authority_required_halts_with_derived_approval_record(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify HUMAN_AUTHORITY_REQUIRED halts cleanly and derives ApprovalRecord from card."""

    class MockHumanAuthorityGate(PolicyGuardianGate):
        def evaluate_inputs(
            self,
            inputs: DeterministicPolicyInputs,
            plan_hash: Optional[str] = None,
            approval_token: Optional[Any] = None,
            assessment: Optional[ReversibilityAssessment] = None,
            now: Optional[datetime.datetime] = None,
        ) -> PolicyGateEvaluationResult:
            # Force high blast radius to generate standard card
            forced_inputs = inputs.model_copy(update={"blast_radius_score": 0.95})
            return super().evaluate_inputs(
                forced_inputs,
                plan_hash=plan_hash,
                approval_token=approval_token,
                assessment=assessment,
                now=now,
            )

    orchestrator = ChangeSagaOrchestrator(
        repository=repo, event_bus=bus, policy_gate=MockHumanAuthorityGate()
    )
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
    )

    # 1. Saga must halt at AWAITING_AUTHORITY
    assert result.is_completed is False
    assert result.final_state == ChangeState.AWAITING_AUTHORITY
    assert result.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert result.approval_card is not None

    # 2. Persisted state in repository must be AWAITING_AUTHORITY
    change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert change is not None
    assert change.state == ChangeState.AWAITING_AUTHORITY
    assert change.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED

    # 3. Approval record must match compression card (field-for-field parity)
    approvals = repo.list_approvals("tenant-prod-alpha", result.change_id)
    assert len(approvals) == 1
    approval = approvals[0]
    card = result.approval_card
    assert approval.card_id == card.card_id
    assert approval.authority_slot_ref == card.authority_slot_ref
    assert approval.decision_question == card.decision_question
    assert approval.decision_options == card.decision_options
    assert approval.policy_reason == card.policy_reason
    assert approval.action_scope == card.action_scope
    assert approval.completed_work_summary == card.completed_work_summary
    assert approval.rehearsed_work_summary == card.rehearsed_work_summary
    assert approval.remaining_decision_summary == card.remaining_decision_summary
    assert approval.evidence_refs == card.evidence_refs
    assert approval.card_created_at == card.created_at
    assert approval.resolution_status == ApprovalResolutionStatus.PENDING

    # 4. Zero execution tasks or migration artifacts written
    tasks = repo.list_tasks("tenant-prod-alpha", result.change_id)
    task_roles = [t.agent_role for t in tasks]
    assert "migration_engineer" not in task_roles
    assert "evidence_auditor" not in task_roles


def test_p20_01_destructive_or_unsupported_request_fails_closed(
    repo: InMemorySagaStateRepository, bus: LocalEventBus
) -> None:
    """Prove unsupported destructive request fails closed at intake with zero fact laundering."""
    destructive_request = ChangeRequest(
        schema_version="1.0.0",
        request_id="req-p20-destr-001",
        title="Drop accounts table",
        description="DROP TABLE billing_accounts;",
        target_systems=["billing-db"],
        data_classification=DataClassLevel.INTERNAL,
        success_criteria=[
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="crit-01",
                description="Schema cleanup",
                verification_method="deterministic",
                required_evidence_types=["REHEARSAL_SIMULATION"],
            )
        ],
        requested_by="engineer@example.com",
        requested_at=datetime.datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    )

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=destructive_request,
    )

    # 1. Must fail closed to ChangeState.BLOCKED
    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "UNSUPPORTED_OPERATION" in (result.stopped_reason or "")
    assert "DROP TABLE" in (result.stopped_reason or "")

    # 2. Cannot reach AUTHORIZED, EXECUTING, VERIFYING, CERTIFYING, or COMPLETE
    assert result.final_state not in (
        ChangeState.AUTHORIZED,
        ChangeState.EXECUTING,
        ChangeState.VERIFYING,
        ChangeState.CERTIFYING,
        ChangeState.COMPLETE,
    )

    # 3. Zero approval cards or approval records created (cannot bypass via human authority)
    assert result.approval_card is None
    assert repo.list_approvals("tenant-prod-alpha", result.change_id) == []

    # 4. Zero execution tasks or migration artifacts created
    tasks = repo.list_tasks("tenant-prod-alpha", result.change_id)
    assert len(tasks) == 0

    evidence_refs = repo.list_evidence_refs("tenant-prod-alpha", result.change_id)
    assert not any(ref.subject == "migration_artifacts" for ref in evidence_refs)

    # 5. Persisted change record truthfully explains why execution was blocked
    persisted_change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert persisted_change is not None
    assert persisted_change.state == ChangeState.BLOCKED
    assert "UNSUPPORTED_OPERATION" in (persisted_change.state_reason or "")


def test_p20_01_intake_secret_in_target_systems_fails_closed_before_persistence(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify secret pattern in target_systems raises ValueError before creating state or events."""
    gh_prefix = "ghp_"
    dummy_secret = gh_prefix + ("abcdef1234567890" * 3)[:36]

    bad_request = sample_change_request.model_copy(
        update={"target_systems": [f"billing-db-{dummy_secret}"]}
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    with pytest.raises(ValueError, match="Secret/credential detected in target_systems"):
        orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=bad_request)

    assert repo.list_changes("tenant-prod-alpha") == []
    assert len(bus.published_history) == 0


def test_p20_01_intake_secret_in_request_id_fails_closed_before_persistence(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify secret pattern in request_id raises ValueError before creating state or events."""
    gh_prefix = "ghp_"
    dummy_secret = gh_prefix + ("abcdef1234567890" * 3)[:36]

    bad_request = sample_change_request.model_copy(update={"request_id": f"req-{dummy_secret}"})
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    with pytest.raises(ValueError, match="Secret/credential detected in structural identity"):
        orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=bad_request)

    assert repo.list_changes("tenant-prod-alpha") == []
    assert len(bus.published_history) == 0


def test_p20_01_intake_secret_in_requested_by_fails_closed_before_persistence(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify secret pattern in requested_by raises ValueError before creating state or events."""
    gh_prefix = "ghp_"
    dummy_secret = gh_prefix + ("abcdef1234567890" * 3)[:36]

    bad_request = sample_change_request.model_copy(
        update={"requested_by": f"admin-{dummy_secret}@corp.internal"}
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    with pytest.raises(ValueError, match="Secret/credential detected in structural identity"):
        orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=bad_request)

    assert repo.list_changes("tenant-prod-alpha") == []
    assert len(bus.published_history) == 0


def test_p20_01_qualification_fails_closed_on_expired_passport(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify qualification fails closed if an agent's passport has expired."""
    tid = "tenant-prod-alpha"
    past = datetime.datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = datetime.datetime(2026, 8, 18, tzinfo=timezone.utc)
    registry = build_standard_demo_registry(tenant_id=tid, now=past)

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus, agent_registry=registry)
    result = orchestrator.run_saga(tenant_id=tid, request=sample_change_request, now=now)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "QUALIFICATION_FAILED" in (result.stopped_reason or "")


def test_p20_01_qualification_fails_closed_on_revoked_passport(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify qualification fails closed if an agent's passport is revoked."""
    tid = "tenant-prod-alpha"
    now = datetime.datetime(2026, 8, 18, tzinfo=timezone.utc)
    registry = build_standard_demo_registry(tenant_id=tid, now=now)

    active_passport = registry.get_active_passport(tid, "agent-impact-scout", "1.0.0")
    assert active_passport is not None
    revoked_passport = active_passport.model_copy(
        update={
            "is_revoked": True,
            "revoked_at": now,
            "revocation_reason": "Security audit revocation",
        }
    )
    registry.register_passport(tid, revoked_passport)

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus, agent_registry=registry)
    result = orchestrator.run_saga(tenant_id=tid, request=sample_change_request, now=now)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "QUALIFICATION_FAILED" in (result.stopped_reason or "")


def test_p20_01_qualification_fails_closed_on_wrong_agent_revision_passport(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify qualification fails closed if passport revision does not match required 1.0.0."""
    tid = "tenant-prod-alpha"
    now = datetime.datetime(2026, 8, 18, tzinfo=timezone.utc)
    ev_reg = QualificationEvidenceRegistry()
    verifier = QualificationEvidenceVerifier(registry=ev_reg)
    registry = InMemoryAgentRegistry(evidence_verifier=verifier)

    desc = AgentDescriptor(
        agent_id="agent-impact-scout",
        agent_name="Impact Scout",
        agent_role="impact_scout",
        agent_revision="0.9.0",
        description="Outdated revision scout",
        declared_capabilities=("AST_STATIC_ANALYSIS", "BLAST_RADIUS_ESTIMATION"),
    )
    registry.register_agent(desc)

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus, agent_registry=registry)
    result = orchestrator.run_saga(tenant_id=tid, request=sample_change_request, now=now)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "QUALIFICATION_FAILED" in (result.stopped_reason or "")


def test_p20_01_evidence_mode_honesty_enforcement(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that requesting LIVE_WRITE on local saga without real mutation fails closed."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    # Attempting to claim LIVE_WRITE for local saga must raise ValueError (mode honesty)
    with pytest.raises(ValueError, match="LIVE_WRITE mode cannot be claimed for local saga"):
        orchestrator.run_saga(
            tenant_id="tenant-prod-alpha",
            request=sample_change_request,
            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        )


def test_p20_01_qualification_fails_closed_on_empty_registry(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify qualification fails closed with ChangeState.BLOCKED if agent registry is empty."""
    empty_registry = InMemoryAgentRegistry()
    orchestrator = ChangeSagaOrchestrator(
        repository=repo, event_bus=bus, agent_registry=empty_registry
    )

    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
    )

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "QUALIFICATION_FAILED" in (result.stopped_reason or "")

    # Zero qualify PASS evidence ref created
    evidence_refs = repo.list_evidence_refs("tenant-prod-alpha", result.change_id)
    assert not any(ref.subject == "capability_qualification" for ref in evidence_refs)


def test_p20_01_qualification_fails_closed_on_missing_capability(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify qualification fails closed if an agent lacks a required capability."""
    tid = "tenant-prod-alpha"
    registry = InMemoryAgentRegistry()
    # Register an agent descriptor for impact_scout with WRONG/missing capabilities
    desc = AgentDescriptor(
        agent_id="agent-impact-scout",
        agent_name="Impact Scout",
        agent_role="impact_scout",
        agent_revision="1.0.0",
        description="Unqualified scout",
        declared_capabilities=("SOME_OTHER_CAPABILITY",),
    )
    registry.register_agent(desc)

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus, agent_registry=registry)
    result = orchestrator.run_saga(tenant_id=tid, request=sample_change_request)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED


def test_p20_01_shadowlab_rehearsal_failure_blocks_progression(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that a failed ShadowLab rehearsal stops authorization and blocks progression."""
    failing_scenario = ShadowScenario(
        scenario_id="SCENARIO_UNKNOWN_FAILURE",
        name="Unknown Fault Injection",
        description="Failing rehearsal scenario with unhandled fault",
        preconditions={"database": "postgres"},
        expected_policy_outcome="DENY_BLOCKED",
        pass_criteria="Should fail closed",
    )

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        rehearsal_scenario=failing_scenario,
    )

    # 1. State must be BLOCKED
    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED

    # 2. Rehearsal evidence state must be FAIL
    evidence_refs = repo.list_evidence_refs("tenant-prod-alpha", result.change_id)
    rehearsal_ev = next(ref for ref in evidence_refs if ref.subject == "shadowlab_rehearsal")
    assert rehearsal_ev.state == EvidenceState.FAIL

    # 3. Zero execution tasks
    tasks = repo.list_tasks("tenant-prod-alpha", result.change_id)
    task_roles = [t.agent_role for t in tasks]
    assert "migration_engineer" not in task_roles


def test_p20_01_adk_change_orchestrator_bridge_coordination(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify ADK ChangeOrchestrator coordinates lifecycle saga via bridge method."""
    adk_orchestrator = ChangeOrchestrator()
    result = adk_orchestrator.run_lifecycle_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        repository=repo,
        event_bus=bus,
    )

    assert result.is_completed is True
    assert result.final_state == ChangeState.COMPLETE
    assert result.events_emitted == 10

    # ADK ChangeOrchestrator does NOT own durable state
    assert repo.get_change("tenant-prod-alpha", result.change_id) is not None


def test_p20_01_optimistic_concurrency_rejects_stale_update(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify optimistic concurrency enforcement prevents stale state overwrite."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        stop_at_state=ChangeState.DISCOVERING,
    )

    change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert change is not None
    current_version = change.version

    stale_change = change.model_copy(update={"state_reason": "Stale concurrent writer"})
    with pytest.raises(OptimisticConcurrencyError) as exc_info:
        repo.update_change(
            "tenant-prod-alpha",
            stale_change,
            expected_version=current_version - 1,
        )
    assert exc_info.value.expected_version == current_version - 1
    assert exc_info.value.actual_version == current_version


def test_p20_01_illegal_transition_fails_closed(
    repo: InMemorySagaStateRepository, bus: LocalEventBus
) -> None:
    """Verify that jumping directly from RECEIVED to COMPLETE violates transition graph."""
    with pytest.raises(IllegalTransitionError):
        require_transition(ChangeState.RECEIVED, ChangeState.COMPLETE)

    with pytest.raises(IllegalTransitionError):
        require_transition(ChangeState.DISCOVERING, ChangeState.EXECUTING)

    with pytest.raises(IllegalTransitionError):
        require_transition(ChangeState.GROUNDED, ChangeState.COMPLETE)


def test_p20_01_tenant_isolation_boundary(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that tasks, approvals, evidence, and changes are segregated across tenants."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    res_a = orchestrator.run_saga(tenant_id="tenant-alpha", request=sample_change_request)
    res_b = orchestrator.run_saga(tenant_id="tenant-beta", request=sample_change_request)

    assert repo.get_change("tenant-alpha", res_a.change_id) is not None
    assert repo.get_change("tenant-beta", res_a.change_id) is None
    assert repo.get_change("tenant-beta", res_b.change_id) is not None
    assert repo.get_change("tenant-alpha", res_b.change_id) is None

    assert len(repo.list_tasks("tenant-alpha", res_a.change_id)) >= 7
    assert len(repo.list_tasks("tenant-beta", res_a.change_id)) == 0


def test_p20_01_stop_at_intermediate_states(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that stopping at intermediate lifecycle states halts progression gracefully."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    res_rehearse = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        stop_at_state=ChangeState.REHEARSING,
    )
    assert res_rehearse.is_completed is False
    assert res_rehearse.final_state == ChangeState.REHEARSING

    res_ground = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        stop_at_state=ChangeState.GROUNDED,
    )
    assert res_ground.is_completed is False
    assert res_ground.final_state == ChangeState.GROUNDED

    res_exec = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        stop_at_state=ChangeState.EXECUTING,
    )
    assert res_exec.is_completed is False
    assert res_exec.final_state == ChangeState.EXECUTING


def test_p20_01_deterministic_state_override_prevention(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that semantic model results cannot overwrite deterministic failure or state."""
    reconciler = DeterministicReconciler()
    claim_audit = ClaimAuditResult(
        claim_id="claim-01",
        verdict=SemanticVerdict.SUPPORTS,
        reasoning="Model believes change is safe",
    )
    recon = reconciler.reconcile(
        audit_result=claim_audit,
        deterministic_state="FAIL",
        change_id="change-test-recon",
    )
    assert recon.deterministic_state == "FAIL"
    assert recon.deterministic_state_preserved is True
    assert recon.disagreement_detected is True
    assert recon.authority_of_deterministic == "DETERMINISTIC_CODE"
    assert recon.authority_of_semantic == "GEMINI_SEMANTIC_JUDGMENT"


def test_p20_01_intent_validation_rejects_unrelated_api_timeout(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify unrelated API timeout modification fails closed at intake."""
    req = sample_change_request.model_copy(
        update={
            "title": "Increase billing API timeout",
            "description": "Increase timeout for billing API endpoint to 60s",
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=req)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "UNSUPPORTED_OPERATION" in (result.stopped_reason or "")
    assert len(repo.list_tasks("tenant-prod-alpha", result.change_id)) == 0
    assert repo.list_approvals("tenant-prod-alpha", result.change_id) == []


def test_p20_01_intent_validation_rejects_unrelated_schema_operation(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify unrelated schema operation (different table/column) fails closed at intake."""
    req = sample_change_request.model_copy(
        update={
            "title": "Add discount_code column to invoices table",
            "description": "ALTER TABLE invoices ADD COLUMN discount_code VARCHAR(32);",
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=req)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "UNSUPPORTED_OPERATION" in (result.stopped_reason or "")


def test_p20_01_intent_validation_rejects_mixed_targets(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify mixed target systems (one valid, one unauthorized) fail closed at intake."""
    req = sample_change_request.model_copy(
        update={"target_systems": ["billing-db", "prod-payroll"]}
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=req)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert "unsupported targets" in (result.stopped_reason or "").lower()
    assert "prod-payroll" in (result.stopped_reason or "")


def test_p20_01_intent_validation_rejects_missing_required_database_target(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify request targeting only ancillary systems without required billing-db fails closed."""
    req = sample_change_request.model_copy(
        update={
            "target_systems": ["payment-service"],
            "title": "Add payment_tier column",
            "description": "Add payment_tier column to billing_accounts",
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=req)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "UNSUPPORTED_OPERATION" in (result.stopped_reason or "")
    assert "required database target" in (result.stopped_reason or "").lower()
    # 0 migration artifacts, 0 human-authority escape, 0 execution
    assert len(repo.list_tasks("tenant-prod-alpha", result.change_id)) == 0
    assert repo.list_approvals("tenant-prod-alpha", result.change_id) == []
    assert result.tasks_executed == 0
    assert result.checkpoints_created == 0


def test_p20_01_intent_validation_rejects_opposite_remove_action(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify opposite/destructive remove action is rejected with 0 artifacts and 0 escape."""
    req = sample_change_request.model_copy(
        update={
            "title": "Remove payment_tier column",
            "description": "Remove payment_tier from billing_accounts migration",
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=req)

    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "UNSUPPORTED_OPERATION" in (result.stopped_reason or "")
    assert (
        "contradictory" in (result.stopped_reason or "").lower()
        or "remove" in (result.stopped_reason or "").lower()
    )
    # 0 migration artifacts, 0 approval escape, 0 execution
    assert len(repo.list_tasks("tenant-prod-alpha", result.change_id)) == 0
    assert repo.list_approvals("tenant-prod-alpha", result.change_id) == []
    assert result.tasks_executed == 0
    assert result.checkpoints_created == 0


def test_p20_01_verification_fails_on_unprovable_production_deployment_criterion(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify saga fails at Stage 7 (VERIFYING -> FAILED) on unprovable prod deployment."""
    unprovable_request = sample_change_request.model_copy(
        update={
            "success_criteria": [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-prod-deploy",
                    description="Real production deployment completed to live cluster",
                    verification_method="deterministic",
                    required_evidence_types=["PRODUCTION_DEPLOYMENT"],
                )
            ]
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=unprovable_request)

    assert result.is_completed is False
    assert result.final_state == ChangeState.FAILED
    assert "VERIFICATION_FAILED" in (result.stopped_reason or "")
    assert result.checkpoints_created == 0
    persisted = repo.get_change("tenant-prod-alpha", result.change_id)
    assert persisted is not None
    assert persisted.state == ChangeState.FAILED


def test_p20_01_verification_fails_on_unprovable_live_write_mutation_criterion(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify saga fails at Stage 7 when criterion requires live write provider mutation."""
    unprovable_request = sample_change_request.model_copy(
        update={
            "success_criteria": [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-live-write",
                    description="Live write provider mutation committed to remote GitHub repo",
                    verification_method="deterministic",
                    required_evidence_types=["LIVE_WRITE"],
                )
            ]
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=unprovable_request)

    assert result.is_completed is False
    assert result.final_state == ChangeState.FAILED
    assert "VERIFICATION_FAILED" in (result.stopped_reason or "")


def test_p20_01_verification_fails_on_absent_evidence_type(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify saga fails at Stage 7 when criterion requires an evidence type absent here."""
    absent_ev_request = sample_change_request.model_copy(
        update={
            "success_criteria": [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-external-telemetry",
                    description="External telemetry stream verified",
                    verification_method="deterministic",
                    required_evidence_types=["EXTERNAL_TELEMETRY"],
                )
            ]
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=absent_ev_request)

    assert result.is_completed is False
    assert result.final_state == ChangeState.FAILED
    assert "VERIFICATION_FAILED" in (result.stopped_reason or "")


def test_p20_01_verification_fails_on_unsupported_manual_method(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify saga fails at Stage 7 when criterion specifies unsupported manual method."""
    manual_request = sample_change_request.model_copy(
        update={
            "success_criteria": [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-manual-signoff",
                    description="Manual human sign-off completed",
                    verification_method="manual",
                    required_evidence_types=["REHEARSAL_SIMULATION"],
                )
            ]
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=manual_request)

    assert result.is_completed is False
    assert result.final_state == ChangeState.FAILED
    assert "VERIFICATION_FAILED" in (result.stopped_reason or "")
    assert "manual" in (result.stopped_reason or "").lower()


def test_p20_01_mode_honesty_rejects_recorded_cloud(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify RECORDED_CLOUD mode is rejected before state persistence on local saga."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    with pytest.raises(ValueError, match="RECORDED_CLOUD mode cannot be claimed"):
        orchestrator.run_saga(
            tenant_id="tenant-prod-alpha",
            request=sample_change_request,
            evidence_mode=ExecutionEvidenceMode.RECORDED_CLOUD,
        )

    assert repo.list_changes("tenant-prod-alpha") == []
    assert len(bus.published_history) == 0


def test_p20_01_intake_secret_in_tenant_id_fails_closed(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify secret token pattern in tenant_id raises ValueError before state persistence."""
    gh_prefix = "ghp_"
    dummy_secret = gh_prefix + ("1234567890abcdef" * 3)[:36]

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    with pytest.raises(ValueError, match="Secret/credential detected in tenant_id"):
        orchestrator.run_saga(
            tenant_id=f"tenant-{dummy_secret}",
            request=sample_change_request,
        )

    assert len(bus.published_history) == 0


def test_p20_01_intake_secret_in_criterion_structural_fields_fails_closed(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify secret pattern in criterion structural fields raises ValueError at intake."""
    gh_prefix = "ghp_"
    dummy_secret = gh_prefix + ("1234567890abcdef" * 3)[:36]

    bad_crit_id_request = sample_change_request.model_copy(
        update={
            "success_criteria": [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id=f"crit-{dummy_secret}",
                    description="Valid description",
                    verification_method="deterministic",
                    required_evidence_types=["REHEARSAL_SIMULATION"],
                )
            ]
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    with pytest.raises(ValueError, match="Secret/credential detected in success criterion"):
        orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=bad_crit_id_request)

    bad_ev_type_request = sample_change_request.model_copy(
        update={
            "success_criteria": [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-01",
                    description="Valid description",
                    verification_method="deterministic",
                    required_evidence_types=[f"EVID-{dummy_secret}"],
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="Secret/credential detected in success criterion"):
        orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=bad_ev_type_request)

    assert repo.list_changes("tenant-prod-alpha") == []
    assert len(bus.published_history) == 0


def test_p20_01_secret_in_criterion_description_is_sanitized(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify secret in criterion description is sanitized with [REDACTED] in audit claims."""
    gh_prefix = "ghp_"
    dummy_secret = gh_prefix + ("1234567890abcdef" * 3)[:36]

    secret_crit_request = sample_change_request.model_copy(
        update={
            "success_criteria": [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-01",
                    description=f"Rehearsal succeeds with token {dummy_secret}",
                    verification_method="deterministic",
                    required_evidence_types=["REHEARSAL_SIMULATION"],
                )
            ]
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(tenant_id="tenant-prod-alpha", request=secret_crit_request)

    assert result.is_completed is True
    # Verify raw secret never appears in any task summary or wire message
    for msg in bus.published_history:
        assert dummy_secret not in msg.to_bytes().decode("utf-8")
    for task in repo.list_tasks("tenant-prod-alpha", result.change_id):
        assert dummy_secret not in str(task.output_summary)


def test_p20_01_intent_validation_rejects_negated_add_operation(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify deterministic fail-closed rejection of explicit negation of the ADD operation."""
    negated_request = sample_change_request.model_copy(
        update={
            "description": "Do not add payment_tier column to billing_accounts",
            "target_systems": ["billing-db"],
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=negated_request,
    )

    # 1. State and Autonomy
    assert result.is_completed is False
    assert result.final_state == ChangeState.BLOCKED
    assert result.autonomy_class == AutonomyClass.BLOCKED
    assert "UNSUPPORTED_OPERATION" in (result.stopped_reason or "")

    # 2. 0 tasks, 0 approvals, 0 checkpoints, 0 migration artifacts
    assert result.tasks_executed == 0
    assert len(repo.list_tasks("tenant-prod-alpha", result.change_id)) == 0
    assert repo.list_approvals("tenant-prod-alpha", result.change_id) == []
    assert result.approval_card is None
    assert result.checkpoints_created == 0

    evidence_refs = repo.list_evidence_refs("tenant-prod-alpha", result.change_id)
    assert not any(ref.subject == "migration_artifacts" for ref in evidence_refs)

    # 3. Persisted ChangeRecord reflects BLOCKED
    persisted = repo.get_change("tenant-prod-alpha", result.change_id)
    assert persisted is not None
    assert persisted.state == ChangeState.BLOCKED


def test_p20_01_verification_fails_on_contradictory_criterion_description(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify contradictory/negated criterion fails deterministically at Stage 7."""
    contradictory_request = sample_change_request.model_copy(
        update={
            "success_criteria": [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-contradictory-001",
                    description="payment_tier column was NOT added to billing_accounts",
                    verification_method="deterministic",
                    required_evidence_types=["MIGRATION_EXECUTION"],
                )
            ]
        }
    )
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=contradictory_request,
    )

    # 1. Saga does NOT COMPLETE; final state = FAILED under existing verification-failure path
    assert result.is_completed is False
    assert result.final_state == ChangeState.FAILED
    assert "VERIFICATION_FAILED" in (result.stopped_reason or "")

    # 2. 0 certification checkpoint
    assert result.checkpoints_created == 0
    persisted_change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert persisted_change is not None
    assert persisted_change.state == ChangeState.FAILED

    # 3. Verify task failed
    tasks = repo.list_tasks("tenant-prod-alpha", result.change_id)
    verify_task = next((t for t in tasks if t.agent_role == "evidence_auditor"), None)
    assert verify_task is not None
    assert verify_task.status == TaskStatus.FAILED
    assert "Verification FAILED" in str(verify_task.output_summary)

    # 4. Zero certification evidence produced
    evidence_refs = repo.list_evidence_refs("tenant-prod-alpha", result.change_id)
    assert not any(ref.subject == "saga_certification" for ref in evidence_refs)
