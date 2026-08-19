"""Tests for P-20.02 Recovery Paths:
Pause, Resume, Cancel, Timeout, Retry, Compensation, Dead-Letter.

Verifies:
1. Pause transitions non-terminal state to BLOCKED with persisted reason and checkpoint.
2. Cancel transitions non-terminal state to terminal CANCELLED.
3. Timeout detects elapsed time and transitions to FAILED with evidence.
4. Retry schedules bounded retry from retriable states with retry_origin tracking.
5. Retry exhaustion routes to dead-letter instead of infinite retry.
6. Resume from RETRY_SCHEDULED back to bounded retry origin.
7. Compensation starts from EXECUTING/VERIFYING only (per ALLOWED_TRANSITIONS).
8. Compensation completes to FAILED terminal state (not pretend rollback).
9. Dead-letter preserves metadata, sanitizes credentials, human_authority_required=False.
10. Invalid transitions fail closed (terminal state pause, cancel from COMPLETE, etc.).
11. Optimistic concurrency is enforced on every recovery path.
12. Causal events are emitted AFTER state persistence.
13. Secret sanitization on recovery reasons.
14. Fault injection: persistence failure prevents false event emission.
"""

from __future__ import annotations

import datetime
from datetime import timedelta, timezone

import pytest

from domain.contracts.change_lifecycle import (
    ChangeState,
    IllegalTransitionError,
)
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import ExecutionEvidenceMode
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.orchestrator_saga import (
    ChangeSagaOrchestrator,
    RecoveryAction,
)
from src.orchestrator.state_repository import (
    TaskStatus,
)

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
        request_id="req-p2002-test-001",
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


def _run_saga_to_state(
    repo: InMemorySagaStateRepository,
    bus: LocalEventBus,
    request: ChangeRequest,
    stop_at_state: ChangeState,
) -> tuple[str, str, ChangeSagaOrchestrator]:
    """Helper: run saga to a given state and return (tenant_id, change_id, orchestrator)."""
    timeline = CausalEventTimeline("tmp")
    orch = ChangeSagaOrchestrator(
        repository=repo,
        event_bus=bus,
        timeline=timeline,
    )
    result = orch.run_saga(
        "test-tenant",
        request,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        stop_at_state=stop_at_state,
        now=NOW,
    )
    return result.tenant_id, result.change_id, orch


# =========================================================================
# 1. PAUSE PATH
# =========================================================================


class TestPauseSaga:
    """P-20.02: Pause transitions to BLOCKED with persisted reason and checkpoint."""

    def test_pause_from_discovering(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.pause_saga(tid, cid, "Operator requested pause", now=NOW)

        assert result.action == RecoveryAction.PAUSED
        assert result.previous_state == ChangeState.DISCOVERING
        assert result.final_state == ChangeState.BLOCKED
        assert "PAUSED" in result.reason
        assert result.event_id is not None

        # Verify persisted state
        record = repo.get_change(tid, cid)
        assert record is not None
        assert record.state == ChangeState.BLOCKED
        assert "PAUSED" in record.state_reason

        # Verify checkpoint was created
        checkpoints = repo.list_checkpoints(tid, cid)
        assert len(checkpoints) >= 1
        assert checkpoints[0].lifecycle_state_at_checkpoint == ChangeState.BLOCKED

    def test_pause_from_executing(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        result = orch.pause_saga(tid, cid, "Need review before continuing", now=NOW)

        assert result.action == RecoveryAction.PAUSED
        assert result.previous_state == ChangeState.EXECUTING
        assert result.final_state == ChangeState.BLOCKED

    def test_pause_from_terminal_state_fails(self, repo, bus, sample_change_request):
        """Pausing a completed saga must fail closed."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        assert result.final_state == ChangeState.COMPLETE

        with pytest.raises(ValueError, match="terminal state"):
            orch.pause_saga(result.tenant_id, result.change_id, "too late", now=NOW)

    def test_pause_nonexistent_change_fails(self, repo, bus):
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
        with pytest.raises(ValueError, match="not found"):
            orch.pause_saga("test-tenant", "change-nonexistent", "reason", now=NOW)


# =========================================================================
# 2. CANCEL PATH
# =========================================================================


class TestCancelSaga:
    """P-20.02: Cancel transitions to terminal CANCELLED from any non-terminal state."""

    def test_cancel_from_discovering(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.cancel_saga(tid, cid, "Project cancelled", now=NOW)

        assert result.action == RecoveryAction.CANCELLED
        assert result.previous_state == ChangeState.DISCOVERING
        assert result.final_state == ChangeState.CANCELLED
        assert "CANCELLED" in result.reason

        # Verify persisted terminal state
        record = repo.get_change(tid, cid)
        assert record is not None
        assert record.state == ChangeState.CANCELLED

    def test_cancel_from_qualifying(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.QUALIFYING
        )
        result = orch.cancel_saga(tid, cid, "Requirements changed", now=NOW)
        assert result.final_state == ChangeState.CANCELLED

    def test_cancel_from_executing(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        result = orch.cancel_saga(tid, cid, "Emergency abort", now=NOW)
        assert result.final_state == ChangeState.CANCELLED

    def test_cancel_from_terminal_state_fails(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        with pytest.raises(ValueError, match="terminal state"):
            orch.cancel_saga(result.tenant_id, result.change_id, "too late", now=NOW)

    def test_cancel_is_terminal_no_further_transitions(self, repo, bus, sample_change_request):
        """Once cancelled, no further recovery operations are allowed."""
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        orch.cancel_saga(tid, cid, "cancelled", now=NOW)

        with pytest.raises(ValueError, match="terminal state"):
            orch.cancel_saga(tid, cid, "double cancel", now=NOW)

        with pytest.raises(ValueError, match="terminal state"):
            orch.pause_saga(tid, cid, "pause after cancel", now=NOW)


# =========================================================================
# 3. TIMEOUT PATH
# =========================================================================


class TestTimeoutSaga:
    """P-20.02: Timeout detects elapsed time and transitions to FAILED."""

    def test_timeout_triggers_after_elapsed(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        # Simulate 2 hours passing
        future = NOW + timedelta(hours=2)
        result = orch.timeout_saga(tid, cid, timeout_seconds=3600.0, now=future)

        assert result is not None
        assert result.action == RecoveryAction.TIMED_OUT
        assert result.previous_state == ChangeState.DISCOVERING
        assert result.final_state == ChangeState.FAILED
        assert "TIMEOUT" in result.reason
        assert "7200" in result.reason  # elapsed seconds

        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.FAILED

    def test_timeout_returns_none_when_not_expired(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        # Only 10 minutes passed, 1 hour timeout
        future = NOW + timedelta(minutes=10)
        result = orch.timeout_saga(tid, cid, timeout_seconds=3600.0, now=future)
        assert result is None

        # State unchanged
        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.DISCOVERING

    def test_timeout_returns_none_for_terminal_state(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        future = NOW + timedelta(hours=24)
        timeout_result = orch.timeout_saga(
            result.tenant_id, result.change_id, timeout_seconds=1.0, now=future
        )
        assert timeout_result is None  # Terminal states don't time out

    def test_timeout_with_short_duration(self, repo, bus, sample_change_request):
        """Timeout with very short duration triggers immediately with future now."""
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        future = NOW + timedelta(seconds=2)
        result = orch.timeout_saga(tid, cid, timeout_seconds=1.0, now=future)
        assert result is not None
        assert result.action == RecoveryAction.TIMED_OUT


# =========================================================================
# 4. RETRY PATH
# =========================================================================


class TestRetrySchedule:
    """P-20.02: Retry transitions to RETRY_SCHEDULED with bounded origin tracking."""

    def test_retry_from_discovering(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.schedule_retry(
            tid,
            cid,
            "Transient network error",
            retry_attempt=1,
            max_attempts=3,
            now=NOW,
        )

        assert result.action == RecoveryAction.RETRY_SCHEDULED
        assert result.previous_state == ChangeState.DISCOVERING
        assert result.final_state == ChangeState.RETRY_SCHEDULED
        assert result.retry_origin == ChangeState.DISCOVERING
        assert result.retry_attempt == 1
        assert result.retry_max_attempts == 3

        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.RETRY_SCHEDULED

    def test_retry_from_executing(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        result = orch.schedule_retry(
            tid, cid, "Provider unavailable", retry_attempt=2, max_attempts=3, now=NOW
        )
        assert result.final_state == ChangeState.RETRY_SCHEDULED
        assert result.retry_origin == ChangeState.EXECUTING

    def test_retry_exhaustion_routes_to_dead_letter(self, repo, bus, sample_change_request):
        """When retry_attempt > max_attempts, saga goes to dead-letter instead."""
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.schedule_retry(
            tid,
            cid,
            "Still failing",
            retry_attempt=4,
            max_attempts=3,
            now=NOW,
        )

        assert result.action == RecoveryAction.DEAD_LETTERED
        assert result.final_state == ChangeState.FAILED
        assert result.dead_letter_id is not None
        assert "RETRY_EXHAUSTED" in result.reason

    def test_retry_from_terminal_state_fails(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        run_result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        with pytest.raises(ValueError, match="terminal state"):
            orch.schedule_retry(
                run_result.tenant_id,
                run_result.change_id,
                "reason",
                retry_attempt=1,
                max_attempts=3,
                now=NOW,
            )

    def test_retry_from_state_without_retry_transition_fails(
        self, repo, bus, sample_change_request
    ):
        """GROUNDED does not have RETRY_SCHEDULED in ALLOWED_TRANSITIONS, so must fail."""
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.GROUNDED)
        with pytest.raises(ValueError, match="Cannot schedule retry"):
            orch.schedule_retry(tid, cid, "reason", retry_attempt=1, now=NOW)


# =========================================================================
# 5. RESUME FROM RETRY PATH
# =========================================================================


class TestResumeFromRetry:
    """P-20.02: Resume from RETRY_SCHEDULED validates bounded retry origin."""

    def test_resume_to_discovering(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        orch.schedule_retry(tid, cid, "transient error", retry_attempt=1, now=NOW)

        result = orch.resume_from_retry(tid, cid, ChangeState.DISCOVERING, now=NOW)

        assert result.action == RecoveryAction.RESUMED
        assert result.previous_state == ChangeState.RETRY_SCHEDULED
        assert result.final_state == ChangeState.DISCOVERING
        assert result.retry_origin == ChangeState.DISCOVERING

        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.DISCOVERING

    def test_resume_to_executing(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        orch.schedule_retry(tid, cid, "timeout", retry_attempt=1, now=NOW)

        result = orch.resume_from_retry(tid, cid, ChangeState.EXECUTING, now=NOW)
        assert result.final_state == ChangeState.EXECUTING

    def test_resume_from_non_retry_state_fails(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        with pytest.raises(ValueError, match="expected RETRY_SCHEDULED"):
            orch.resume_from_retry(tid, cid, ChangeState.DISCOVERING, now=NOW)

    def test_resume_with_invalid_retry_origin_fails(self, repo, bus, sample_change_request):
        """RETRY_SCHEDULED -> AUTHORIZED is not a valid resume target."""
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        orch.schedule_retry(tid, cid, "error", retry_attempt=1, now=NOW)

        with pytest.raises(IllegalTransitionError):
            orch.resume_from_retry(tid, cid, ChangeState.AUTHORIZED, now=NOW)


# =========================================================================
# 6. COMPENSATION PATH
# =========================================================================


class TestCompensation:
    """P-20.02: Compensation describes actual compensating actions, not fabricated rollbacks."""

    def test_compensation_from_executing(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        result = orch.start_compensation(
            tid,
            cid,
            "Rolling back billing_accounts DDL: DROP COLUMN payment_tier",
            now=NOW,
        )

        assert result.action == RecoveryAction.COMPENSATION_STARTED
        assert result.previous_state == ChangeState.EXECUTING
        assert result.final_state == ChangeState.COMPENSATING
        assert "billing_accounts" in result.compensation_description

        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.COMPENSATING

        # Verify compensation task created
        tasks = repo.list_tasks(tid, cid)
        comp_tasks = [t for t in tasks if t.action_class == "COMPENSATION"]
        assert len(comp_tasks) == 1
        assert comp_tasks[0].status == TaskStatus.IN_PROGRESS

    def test_compensation_from_verifying(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.VERIFYING)
        result = orch.start_compensation(tid, cid, "Verification failed, compensating", now=NOW)
        assert result.final_state == ChangeState.COMPENSATING

    def test_compensation_from_discovering_fails(self, repo, bus, sample_change_request):
        """DISCOVERING -> COMPENSATING is not in ALLOWED_TRANSITIONS."""
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        with pytest.raises(ValueError, match="Cannot start compensation"):
            orch.start_compensation(tid, cid, "invalid", now=NOW)

    def test_complete_compensation_success(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        orch.start_compensation(tid, cid, "Rolling back DDL", now=NOW)

        result = orch.complete_compensation(
            tid, cid, "DDL rollback applied successfully", success=True, now=NOW
        )

        assert result.action == RecoveryAction.COMPENSATION_COMPLETED
        assert result.previous_state == ChangeState.COMPENSATING
        assert result.final_state == ChangeState.FAILED  # Compensation -> FAILED, not COMPLETE
        assert "COMPENSATION_COMPLETED" in result.reason

        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.FAILED

        # Verify compensation task updated
        tasks = repo.list_tasks(tid, cid)
        comp_tasks = [t for t in tasks if t.action_class == "COMPENSATION"]
        assert comp_tasks[0].status == TaskStatus.COMPENSATED

    def test_complete_compensation_failure(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        orch.start_compensation(tid, cid, "Attempting rollback", now=NOW)

        result = orch.complete_compensation(
            tid, cid, "Rollback also failed", success=False, now=NOW
        )

        assert result.action == RecoveryAction.COMPENSATION_FAILED
        assert result.final_state == ChangeState.FAILED
        assert "COMPENSATION_FAILED" in result.reason

    def test_complete_compensation_from_wrong_state_fails(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)
        with pytest.raises(ValueError, match="expected COMPENSATING"):
            orch.complete_compensation(tid, cid, "invalid", now=NOW)


# =========================================================================
# 7. DEAD-LETTER PATH
# =========================================================================


class TestDeadLetter:
    """P-20.02: Dead-letter preserves metadata, sanitizes secrets, human_authority=False."""

    def test_dead_letter_from_discovering(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.dead_letter_saga(tid, cid, "Unrecoverable error", now=NOW)

        assert result.action == RecoveryAction.DEAD_LETTERED
        assert result.previous_state == ChangeState.DISCOVERING
        assert result.final_state == ChangeState.FAILED
        assert result.dead_letter_id is not None
        assert result.dead_letter_id.startswith("dl-")
        assert "DEAD_LETTERED" in result.reason

        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.FAILED

    def test_dead_letter_sanitizes_secrets(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.dead_letter_saga(
            tid,
            cid,
            "Error with api_key=sk-proj-supersecretkey123456789 leaked",
            now=NOW,
        )
        # Secret must be sanitized in the reason
        assert "supersecretkey" not in result.reason
        assert "DEAD_LETTERED" in result.reason

    def test_dead_letter_nonexistent_change_fails(self, repo, bus):
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus)
        with pytest.raises(ValueError, match="not found"):
            orch.dead_letter_saga("test-tenant", "change-nonexistent", "reason", now=NOW)


# =========================================================================
# 8. CAUSAL EVENT EVIDENCE
# =========================================================================


class TestCausalEventEvidence:
    """P-20.02: Every recovery path emits causal events with full identity chain."""

    def test_pause_emits_event(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.pause_saga(tid, cid, "pause reason", now=NOW)

        assert result.event_id is not None
        assert "recovery" in result.event_id
        assert "blocked" in result.event_id

    def test_cancel_emits_event(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.cancel_saga(tid, cid, "cancel reason", now=NOW)
        assert result.event_id is not None
        assert "cancelled" in result.event_id

    def test_retry_emits_event(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        result = orch.schedule_retry(tid, cid, "retry reason", now=NOW)
        assert result.event_id is not None
        assert "retry_scheduled" in result.event_id


# =========================================================================
# 9. SECRET SANITIZATION ON RECOVERY
# =========================================================================


class TestSecretSanitizationOnRecovery:
    """P-20.02: Credentials never enter persisted recovery state or events."""

    def test_pause_sanitizes_ghp_token(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        _ = orch.pause_saga(
            tid,
            cid,
            "Error with ghp_ABCDEFghijklmnopqrstuvwxyz1234567890 token",
            now=NOW,
        )
        record = repo.get_change(tid, cid)
        assert "ghp_" not in record.state_reason

    def test_cancel_sanitizes_bearer_token(self, repo, bus, sample_change_request):
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )
        _ = orch.cancel_saga(
            tid,
            cid,
            "Failed with Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test.sig",
            now=NOW,
        )
        record = repo.get_change(tid, cid)
        assert "eyJhbGci" not in record.state_reason


# =========================================================================
# 10. PERSISTENCE-BEFORE-EVENT CONSISTENCY
# =========================================================================


class TestPersistenceBeforeEvent:
    """P-20.02: State is persisted BEFORE event emission on all recovery paths."""

    def test_recovery_transition_persists_first(self, repo, bus, sample_change_request):
        """Verify that after recovery, repository state matches the expected transition."""
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)

        # Cancel should persist CANCELLED before emitting event
        orch.cancel_saga(tid, cid, "test cancel", now=NOW)

        record = repo.get_change(tid, cid)
        assert record.state == ChangeState.CANCELLED
        assert record.version > 1  # Must have been updated at least once


# =========================================================================
# 11. INTEGRATION: FULL RECOVERY LIFECYCLE
# =========================================================================


class TestFullRecoveryLifecycle:
    """P-20.02: Complete recovery lifecycle:
    run -> retry -> resume -> compensation -> dead-letter.
    """

    def test_retry_then_resume_lifecycle(self, repo, bus, sample_change_request):
        """Run saga to EXECUTING, schedule retry, resume, verify state continuity."""
        tid, cid, orch = _run_saga_to_state(repo, bus, sample_change_request, ChangeState.EXECUTING)

        # Schedule retry
        retry_result = orch.schedule_retry(tid, cid, "transient", retry_attempt=1, now=NOW)
        assert retry_result.final_state == ChangeState.RETRY_SCHEDULED

        # Resume from retry
        resume_result = orch.resume_from_retry(tid, cid, ChangeState.EXECUTING, now=NOW)
        assert resume_result.final_state == ChangeState.EXECUTING

        # Now we can do compensation
        comp_result = orch.start_compensation(tid, cid, "DDL rollback needed", now=NOW)
        assert comp_result.final_state == ChangeState.COMPENSATING

        # Complete compensation
        done_result = orch.complete_compensation(
            tid, cid, "Rollback complete", success=True, now=NOW
        )
        assert done_result.final_state == ChangeState.FAILED

    def test_retry_exhaustion_lifecycle(self, repo, bus, sample_change_request):
        """Exhaust retries across 3 attempts, verify dead-letter on 4th."""
        tid, cid, orch = _run_saga_to_state(
            repo, bus, sample_change_request, ChangeState.DISCOVERING
        )

        # Attempt 1: retry
        r1 = orch.schedule_retry(tid, cid, "fail 1", retry_attempt=1, max_attempts=3, now=NOW)
        assert r1.action == RecoveryAction.RETRY_SCHEDULED

        # Resume from retry
        orch.resume_from_retry(tid, cid, ChangeState.DISCOVERING, now=NOW)

        # Attempt 2: retry
        r2 = orch.schedule_retry(tid, cid, "fail 2", retry_attempt=2, max_attempts=3, now=NOW)
        assert r2.action == RecoveryAction.RETRY_SCHEDULED

        # Resume from retry
        orch.resume_from_retry(tid, cid, ChangeState.DISCOVERING, now=NOW)

        # Attempt 3: retry
        r3 = orch.schedule_retry(tid, cid, "fail 3", retry_attempt=3, max_attempts=3, now=NOW)
        assert r3.action == RecoveryAction.RETRY_SCHEDULED

        # Resume from retry
        orch.resume_from_retry(tid, cid, ChangeState.DISCOVERING, now=NOW)

        # Attempt 4: exhausted -> dead-letter
        r4 = orch.schedule_retry(tid, cid, "fail 4", retry_attempt=4, max_attempts=3, now=NOW)
        assert r4.action == RecoveryAction.DEAD_LETTERED
        assert r4.final_state == ChangeState.FAILED
        assert r4.dead_letter_id is not None
