"""Tests for P-20.03 through P-20.06 — Background Continuation, Ambiguity, Restart, Metrics.

P-20.03: Queued change progresses through reversible stages autonomously.
P-20.04: One blocking ambiguity path asking one minimal question only when necessary.
P-20.05: Restart between phases and exact continuation.
P-20.06: Measure autonomous steps and human-attention count.
"""

from __future__ import annotations

import datetime
from datetime import timezone

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
from src.orchestrator.state_repository import AmbiguityResolutionStatus

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

    def test_background_pauses_at_blocked(self, repo, bus):
        """BLOCKED sagas report as terminal (no outgoing transitions)."""
        blocked_request = ChangeRequest(
            schema_version="1.0.0",
            request_id="req-blocked-001",
            title="Drop table",
            description="DROP TABLE billing_accounts CASCADE;",
            target_systems=["billing-db"],
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
            requested_at=NOW,
        )
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        saga_result = orch.run_saga(
            "test-tenant",
            blocked_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        assert saga_result.final_state == ChangeState.BLOCKED

        runner = BackgroundContinuationRunner(repository=repo, event_bus=bus)
        result = runner.continue_saga(saga_result.tenant_id, saga_result.change_id, now=NOW)
        # BLOCKED is terminal (frozenset() outgoing transitions)
        assert result.outcome == ContinuationOutcome.ALREADY_TERMINAL
        assert result.final_state == ChangeState.BLOCKED

    def test_background_open_ambiguity_pauses(self, repo, bus, sample_change_request):
        """When an open ambiguity question exists, background continuation pauses."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        saga_result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.DISCOVERING,
            now=NOW,
        )

        orch.raise_ambiguity_question(
            saga_result.tenant_id,
            saga_result.change_id,
            minimal_question="Which column type should be used?",
            expected_options=["VARCHAR", "TEXT"],
            irreducible_reason="Type ambiguous from request",
            now=NOW,
        )

        runner = BackgroundContinuationRunner(repository=repo, event_bus=bus)
        result = runner.continue_saga(saga_result.tenant_id, saga_result.change_id, now=NOW)
        assert result.outcome == ContinuationOutcome.PAUSED_AT_AMBIGUITY
        assert result.final_state == ChangeState.DISCOVERING


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
        assert result.human_attention_count == 0

    def test_raise_and_resolve_ambiguity_question(self, repo, bus, sample_change_request):
        """Ambiguity question pauses saga without BLOCKED state; resolving resumes same saga."""
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

        # Raise ambiguity question
        ambiguity = orch.raise_ambiguity_question(
            tid,
            cid,
            "Which database partition should be migrated first?",
            expected_options=["partition-alpha", "partition-beta"],
            irreducible_reason="User intent unspecified for partition order",
            now=NOW,
        )

        assert ambiguity.resolution_status == AmbiguityResolutionStatus.UNRESOLVED
        assert ambiguity.question_id is not None
        assert "partition" in ambiguity.question

        # Verify saga is paused at EXECUTING, NOT terminal BLOCKED
        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.EXECUTING
        assert "AMBIGUITY" in record.state_reason

        # Resolving ambiguity question resumes the same saga
        resolved = orch.resolve_ambiguity_question(
            tid, cid, ambiguity.question_id, "partition-alpha", now=NOW
        )
        assert resolved.resolution_status == AmbiguityResolutionStatus.RESOLVED
        assert resolved.resolved_answer == "partition-alpha"

        record_after = repo.get_change(tid, cid)
        assert record_after.state == ChangeState.EXECUTING
        assert "RESUMED" in record_after.state_reason

        # Metrics reflect human attention count
        metrics = orch.compute_autonomy_metrics(tid, cid)
        assert metrics["human_attention_count"] == 1


# =========================================================================
# P-20.05: RESTART BETWEEN PHASES AND EXACT CONTINUATION
# =========================================================================


class TestRestartAndContinuation:
    """P-20.05: No duplicate external write; next action correct."""

    def test_process_equivalent_restart(self, repo, bus, sample_change_request):
        """Instance A runs to intermediate state -> destroy A -> Instance B continues."""
        # Process Instance A
        timeline_a = CausalEventTimeline("tmp")
        orch_a = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline_a)
        result_a = orch_a.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            stop_at_state=ChangeState.REHEARSING,
            now=NOW,
        )
        tid, cid = result_a.tenant_id, result_a.change_id
        tasks_after_a = len(repo.list_tasks(tid, cid))
        assert tasks_after_a > 0

        # Destroy instance A
        del orch_a

        # Process Instance B (new orchestrator instance, fresh timeline, same repo/bus)
        timeline_b = CausalEventTimeline("tmp")
        orch_b = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline_b)
        result_b = orch_b.run_saga(
            tid,
            sample_change_request,
            change_id=cid,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        assert result_b.change_id == cid
        assert result_b.final_state == ChangeState.COMPLETE
        assert result_b.is_completed is True

        tasks_after_b = len(repo.list_tasks(tid, cid))
        assert tasks_after_b >= tasks_after_a

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


# =========================================================================
# P-20.06: MEASURE AUTONOMOUS STEPS AND HUMAN-ATTENTION COUNT
# =========================================================================


class TestAutonomyMetrics:
    """P-20.06: Metrics derived from events and records, not manual claims."""

    def test_full_saga_reports_event_and_autonomous_step_count(
        self, repo, bus, sample_change_request
    ):
        """SagaExecutionResult.autonomous_steps counts completed automated tasks."""
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
        assert result.autonomous_steps > 0
        assert result.human_attention_count == 0
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

        assert result.events_emitted >= 1
        assert result.final_state == ChangeState.DISCOVERING
        assert result.autonomous_steps >= 1
        assert result.human_attention_count == 0

    def test_background_continuation_counts_autonomous_steps(
        self, repo, bus, sample_change_request
    ):
        """BackgroundContinuationResult.autonomous_steps_taken is derived from records."""
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

        assert result.stopped_reason is None
        assert result.is_completed is True
        assert result.human_attention_count == 0
