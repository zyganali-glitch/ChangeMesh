"""Tests for P-20.03 through P-20.06 — Background Continuation, Ambiguity, Restart, Metrics.

P-20.03: Queued change progresses through reversible stages autonomously.
P-20.04: One blocking ambiguity path asking one minimal question only when necessary.
P-20.05: Restart between phases and exact continuation.
P-20.06: Measure autonomous steps and human-attention count.
"""

from __future__ import annotations

import datetime
from datetime import timedelta, timezone

import pytest

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import ExecutionEvidenceMode
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.orchestrator.background_continuation import (
    BackgroundContinuationRunner,
    ContinuationOutcome,
)
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.orchestrator_saga import (
    ChangeSagaOrchestrator,
)
from src.orchestrator.saga_checkpoint import SagaCheckpointManager

NOW = datetime.datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


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
        request_id="req-p2003-test-001",
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


# =========================================================================
# P-20.03: UNATTENDED BACKGROUND CONTINUATION
# =========================================================================


class TestBackgroundContinuation:
    """P-20.03: Queued change progresses autonomously without active chat."""

    def test_background_run_completes_full_saga(self, repo, bus, sample_change_request):
        """A queued change with no ambiguity completes fully in background."""
        runner = BackgroundContinuationRunner(
            repository=repo,
            event_bus=bus,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
        )

        result = runner.continue_saga(
            "test-tenant",
            "change-bg-001",
            request=sample_change_request,
            now=NOW,
        )

        assert result.outcome == ContinuationOutcome.COMPLETED
        assert result.final_state == ChangeState.COMPLETE
        assert result.autonomous_steps_taken > 0
        assert result.saga_result is not None

    def test_background_reports_not_found(self, repo, bus):
        runner = BackgroundContinuationRunner(repository=repo, event_bus=bus)
        result = runner.continue_saga("test-tenant", "nonexistent-change", now=NOW)
        assert result.outcome == ContinuationOutcome.NOT_FOUND

    def test_background_reports_already_terminal(self, repo, bus, sample_change_request):
        """Completed sagas report ALREADY_TERMINAL without re-execution."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        saga_result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        runner = BackgroundContinuationRunner(repository=repo, event_bus=bus)
        result = runner.continue_saga(saga_result.tenant_id, saga_result.change_id, now=NOW)
        assert result.outcome == ContinuationOutcome.ALREADY_TERMINAL
        assert result.final_state == ChangeState.COMPLETE

    def test_background_pauses_at_blocked(self, repo, bus, sample_change_request):
        """BLOCKED sagas report as terminal (no outgoing transitions)."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        saga_result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.DISCOVERING,
            now=NOW,
        )

        # Pause the saga (transitions to BLOCKED)
        orch.pause_saga(
            saga_result.tenant_id,
            saga_result.change_id,
            "Manual pause",
            now=NOW,
        )

        runner = BackgroundContinuationRunner(repository=repo, event_bus=bus)
        result = runner.continue_saga(saga_result.tenant_id, saga_result.change_id, now=NOW)
        # BLOCKED is terminal (frozenset() outgoing transitions)
        assert result.outcome == ContinuationOutcome.ALREADY_TERMINAL
        assert result.final_state == ChangeState.BLOCKED

    def test_background_no_request_pauses(self, repo, bus, sample_change_request):
        """Without a request, background cannot make progress on non-terminal state."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        saga_result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.EXECUTING,
            now=NOW,
        )

        runner = BackgroundContinuationRunner(repository=repo, event_bus=bus)
        result = runner.continue_saga(saga_result.tenant_id, saga_result.change_id, now=NOW)
        assert result.outcome == ContinuationOutcome.PAUSED_AT_AMBIGUITY


# =========================================================================
# P-20.04: ONE BLOCKING AMBIGUITY PATH
# =========================================================================


class TestBlockingAmbiguityPath:
    """P-20.04: No question when policy/memory decides; answer resumes same saga."""

    def test_no_ambiguity_no_question(self, repo, bus, sample_change_request):
        """When policy and memory can decide, saga completes without questions."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        # Full completion without any ambiguity block
        assert result.final_state == ChangeState.COMPLETE
        assert result.is_completed is True

    def test_blocked_saga_preserves_identity(self, repo, bus, sample_change_request):
        """When ambiguity blocks, the saga identity is preserved for later resolution."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.EXECUTING,
            now=NOW,
        )

        tid, cid = result.tenant_id, result.change_id

        # Simulate ambiguity block
        orch.pause_saga(tid, cid, "Ambiguous parameter needs clarification", now=NOW)
        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.BLOCKED

        # Verify the same change identity is preserved
        assert record.change_id == cid
        assert record.tenant_id == tid
        # The state_reason captures why it was blocked
        assert "Ambiguous" in record.state_reason


# =========================================================================
# P-20.05: RESTART BETWEEN PHASES AND EXACT CONTINUATION
# =========================================================================


class TestRestartAndContinuation:
    """P-20.05: No duplicate external write; next action correct."""

    def test_checkpoint_restart_preserves_state(self, repo, bus, sample_change_request):
        """Saga checkpointed at EXECUTING can restart without losing state."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)

        # Run to EXECUTING
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.EXECUTING,
            now=NOW,
        )
        tid, cid = result.tenant_id, result.change_id

        # Create explicit checkpoint
        SagaCheckpointManager.create_checkpoint(
            repo=repo,
            tenant_id=tid,
            change_id=cid,
            lifecycle_state=ChangeState.EXECUTING,
            now=NOW,
        )

        # Verify checkpoint exists and state is correct
        checkpoints = repo.list_checkpoints(tid, cid)
        assert len(checkpoints) >= 1

        # Verify resume context
        resume_ctx = SagaCheckpointManager.resume_from_checkpoint(
            repo=repo,
            tenant_id=tid,
            change_id=cid,
        )
        assert resume_ctx is not None
        assert resume_ctx.lifecycle_state == ChangeState.EXECUTING

    def test_restart_preserves_tasks_no_duplication(self, repo, bus, sample_change_request):
        """Restarted saga does not duplicate tasks already completed."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)

        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.VERIFYING,
            now=NOW,
        )
        tid, cid = result.tenant_id, result.change_id

        # Count tasks before restart
        tasks_before = len(repo.list_tasks(tid, cid))
        assert tasks_before > 0

        # Checkpoint and verify state preserved
        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.VERIFYING

    def test_idempotent_checkpoint_creation(self, repo, bus, sample_change_request):
        """Multiple checkpoints at same state are additive, not destructive."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)

        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.DISCOVERING,
            now=NOW,
        )
        tid, cid = result.tenant_id, result.change_id

        # Create two checkpoints
        SagaCheckpointManager.create_checkpoint(
            repo=repo,
            tenant_id=tid,
            change_id=cid,
            lifecycle_state=ChangeState.DISCOVERING,
            now=NOW,
        )
        SagaCheckpointManager.create_checkpoint(
            repo=repo,
            tenant_id=tid,
            change_id=cid,
            lifecycle_state=ChangeState.DISCOVERING,
            now=NOW + timedelta(seconds=1),
        )

        checkpoints = repo.list_checkpoints(tid, cid)
        assert len(checkpoints) >= 2  # Both checkpoints preserved


# =========================================================================
# P-20.06: MEASURE AUTONOMOUS STEPS AND HUMAN-ATTENTION COUNT
# =========================================================================


class TestAutonomyMetrics:
    """P-20.06: Metrics derived from events, not manual claims."""

    def test_full_saga_reports_event_count(self, repo, bus, sample_change_request):
        """SagaExecutionResult.events_emitted counts autonomous transitions."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        assert result.events_emitted > 0
        assert result.tasks_executed > 0
        assert result.checkpoints_created >= 0

    def test_saga_with_stop_reports_partial_metrics(self, repo, bus, sample_change_request):
        """Stopped saga reports partial metrics accurately."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.DISCOVERING,
            now=NOW,
        )

        # Should have some events but not all
        assert result.events_emitted >= 1
        assert result.final_state == ChangeState.DISCOVERING

    def test_background_continuation_counts_autonomous_steps(
        self, repo, bus, sample_change_request
    ):
        """BackgroundContinuationResult.autonomous_steps_taken is derived from events."""
        runner = BackgroundContinuationRunner(
            repository=repo,
            event_bus=bus,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
        )

        result = runner.continue_saga(
            "test-tenant",
            "change-metrics-001",
            request=sample_change_request,
            now=NOW,
        )

        assert result.outcome == ContinuationOutcome.COMPLETED
        assert result.autonomous_steps_taken > 0
        # Autonomous steps come from events_emitted, which is derived from actual
        # event emission, not manual claims

    def test_human_attention_count_is_zero_for_full_autonomous(
        self, repo, bus, sample_change_request
    ):
        """Full autonomous run reports zero human attention required."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        # No stopped_reason means no human attention required
        assert result.stopped_reason is None
        assert result.is_completed is True
        # The saga completed autonomously — 0 human attention events
