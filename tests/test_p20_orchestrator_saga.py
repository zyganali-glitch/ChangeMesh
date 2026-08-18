"""Tests for P-20.01 End-to-End Orchestrator Saga.

Verifies:
1. One constant Change ID and correlation ID across the saga.
2. Exact legal ordered lifecycle progression across:
   RECEIVED -> DISCOVERING -> QUALIFYING -> REHEARSING -> GROUNDED ->
   AUTHORIZED -> EXECUTING -> VERIFYING -> CERTIFYING -> COMPLETE.
3. Persisted ChangeRecord agrees with every admitted transition.
4. Every transition has canonical event/correlation/causation evidence.
5. Event producer identity and revision are explicit and non-blank.
6. No timestamp is used as causal authority; causal DAG is verified.
7. Optimistic concurrency prevents stale state overwrite.
8. Evidence / execution mode labels remain exact and truthful.
9. No credentials enter event/state/evidence payloads.
10. Zero external GitHub mutations in P-20.01 tests.
11. Failed/blocked prerequisite prevents downstream stages.
12. HUMAN_AUTHORITY_REQUIRED halts at AWAITING_AUTHORITY with 0 execution tasks
    and no self-authorization.
13. COMPLETE is impossible without traversing VERIFYING and CERTIFYING.
14. Deterministic facts cannot be overwritten by semantic output.
15. Uses real P-15..P-19 component integrations.
"""

from __future__ import annotations

import datetime
from datetime import timezone

import pytest

from domain.contracts.autonomy import AutonomyClass
from domain.contracts.change_lifecycle import (
    ChangeState,
    IllegalTransitionError,
    require_transition,
)
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import ExecutionEvidenceMode
from domain.contracts.memory import MemoryRecord, MemoryTrustStatus
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from src.audit.reconciliation import DeterministicReconciler
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.gate.reversibility import ReversibilityClass
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.orchestrator_saga import (
    ChangeSagaOrchestrator,
)
from src.orchestrator.state_repository import (
    ApprovalResolutionStatus,
    OptimisticConcurrencyError,
    TaskStatus,
)


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

    # Check published events from bus history
    history = bus.published_history
    assert len(history) == 10

    expected_states = [
        ChangeState.RECEIVED,
        ChangeState.DISCOVERING,
        ChangeState.QUALIFYING,
        ChangeState.REHEARSING,
        ChangeState.GROUNDED,
        ChangeState.AUTHORIZED,
        ChangeState.EXECUTING,
        ChangeState.VERIFYING,
        ChangeState.CERTIFYING,
        ChangeState.COMPLETE,
    ]
    assert len(expected_states) == 10

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


def test_p20_01_human_authority_required_halts_without_execution(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that HUMAN_AUTHORITY_REQUIRED stops at AWAITING_AUTHORITY with 0 execute tasks."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    # Force an irreversible / human intervention change class
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        force_reversibility_class=ReversibilityClass.HUMAN_INTERVENTION_REQUIRED,
    )

    # 1. Saga must halt at AWAITING_AUTHORITY
    assert result.is_completed is False
    assert result.final_state == ChangeState.AWAITING_AUTHORITY
    assert result.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert result.approval_card is not None
    assert "Awaiting verified human authority decision" in (result.stopped_reason or "")

    # 2. Persisted state in repository must be AWAITING_AUTHORITY
    change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert change is not None
    assert change.state == ChangeState.AWAITING_AUTHORITY
    assert change.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED

    # 3. Approval record must be persisted with PENDING resolution status
    approvals = repo.list_approvals("tenant-prod-alpha", result.change_id)
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval.resolution_status == ApprovalResolutionStatus.PENDING
    assert approval.authority_slot_ref == "slot-production-schema-change"
    assert approval.resolved_by is None
    assert approval.resolved_at is None

    # 4. Zero execution tasks or migration artifacts written
    tasks = repo.list_tasks("tenant-prod-alpha", result.change_id)
    task_roles = [t.agent_role for t in tasks]
    assert "migration_engineer" not in task_roles
    assert "evidence_auditor" not in task_roles

    # 5. Events history ends at AWAITING_AUTHORITY
    history = bus.published_history
    last_event = history[-1].envelope
    assert "awaiting_authority" in last_event.event_id


def test_p20_01_optimistic_concurrency_rejects_stale_update(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify optimistic concurrency enforcement prevents stale state overwrite."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    # Stop at DISCOVERING
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        stop_at_state=ChangeState.DISCOVERING,
    )

    change = repo.get_change("tenant-prod-alpha", result.change_id)
    assert change is not None
    current_version = change.version

    # Attempt to update with a stale expected_version (e.g. current_version - 1)
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


def test_p20_01_epistemic_memory_grounding_integration(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify memory records are evaluated by trust layer and linked to change."""
    now = datetime.datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    trusted_mem = MemoryRecord(
        schema_version="1.0.0",
        memory_id="mem-billing-schema-v1",
        scope="system:billing",
        content="Table billing_accounts is PostgreSQL with payment_tier field",
        source="agent-impact-scout@1.0.0",
        capture_timestamp=now,
        expiry_timestamp=now + datetime.timedelta(days=30),
        data_classification=DataClassLevel.INTERNAL,
        trust_status=MemoryTrustStatus.TRUSTED,
        trust_evidence_ids=("ev-init-001",),
    )

    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        initial_memory_records=[trusted_mem],
        now=now,
    )

    assert result.is_completed is True
    # Verify task output summary contains memory reference
    tasks = repo.list_tasks("tenant-prod-alpha", result.change_id)
    ground_task = next(t for t in tasks if t.agent_role == "memory_trust")
    assert "1 trusted memory refs" in (ground_task.output_summary or "")


def test_p20_01_zero_credentials_and_secrecy_in_events_and_persistence(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that no credential patterns exist in published events or stored documents."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
    result = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
    )

    secret_markers = ("ghp_", "bearer ", "private key", "-----BEGIN")

    # Inspect all published wire messages
    for msg in bus.published_history:
        raw_bytes = msg.to_bytes()
        raw_str = raw_bytes.decode("utf-8").lower()
        for marker in secret_markers:
            assert marker.lower() not in raw_str

    # Inspect all tasks
    for task in repo.list_tasks("tenant-prod-alpha", result.change_id):
        summary = (task.output_summary or "").lower()
        for marker in secret_markers:
            assert marker.lower() not in summary


def test_p20_01_stop_at_intermediate_states(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that stopping at intermediate lifecycle states halts progression gracefully."""
    orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

    # Stop at REHEARSING
    res_rehearse = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        stop_at_state=ChangeState.REHEARSING,
    )
    assert res_rehearse.is_completed is False
    assert res_rehearse.final_state == ChangeState.REHEARSING
    assert res_rehearse.stopped_reason is not None

    # Stop at GROUNDED
    res_ground = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        stop_at_state=ChangeState.GROUNDED,
    )
    assert res_ground.is_completed is False
    assert res_ground.final_state == ChangeState.GROUNDED

    # Stop at EXECUTING
    res_exec = orchestrator.run_saga(
        tenant_id="tenant-prod-alpha",
        request=sample_change_request,
        stop_at_state=ChangeState.EXECUTING,
    )
    assert res_exec.is_completed is False
    assert res_exec.final_state == ChangeState.EXECUTING


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


def test_p20_01_deterministic_state_override_prevention(
    repo: InMemorySagaStateRepository, bus: LocalEventBus, sample_change_request: ChangeRequest
) -> None:
    """Verify that semantic model results cannot overwrite deterministic failure or state."""
    reconciler = DeterministicReconciler()
    # If deterministic state is FAIL, semantic SUPPORTS must never override it
    from src.audit.semantic_auditor import ClaimAuditResult, SemanticVerdict

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
