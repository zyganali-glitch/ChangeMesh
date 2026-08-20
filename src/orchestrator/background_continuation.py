"""ChangeMesh unattended background saga continuation.

P-20.03: Enables a queued change request to progress through reversible
lifecycle stages autonomously when no operator chat session is active.

The BackgroundContinuationRunner:
1. Picks up PENDING or IN_PROGRESS sagas from the repository.
2. Runs them through reversible stages autonomously.
3. Pauses at irreversible boundaries (AWAITING_AUTHORITY) if ambiguity exists.
4. Records all progress in persisted state with causal events.
5. Never requires an active chat connection to make progress.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from domain.contracts.change_lifecycle import ChangeState, is_terminal
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import ExecutionEvidenceMode
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.orchestrator.orchestrator_saga import (
    DEFAULT_SAGA_TIMEOUT_SECONDS,
    ChangeSagaOrchestrator,
    SagaExecutionResult,
    SagaRecoveryResult,
)
from src.orchestrator.state_repository import (
    CANONICAL_SCHEMA_VERSION,
    AmbiguityResolutionStatus,
    SagaStateRepository,
)

logger = logging.getLogger(__name__)


class ContinuationOutcome(str, Enum):
    """Result classification for a background continuation attempt."""

    COMPLETED = "COMPLETED"
    PAUSED_AT_AUTHORITY = "PAUSED_AT_AUTHORITY"
    PAUSED_AT_AMBIGUITY = "PAUSED_AT_AMBIGUITY"
    TIMED_OUT = "TIMED_OUT"
    FAILED = "FAILED"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"
    NOT_FOUND = "NOT_FOUND"


class BackgroundContinuationResult(BaseModel):
    """Result of a single background continuation attempt.

    P-20.03: Every background run produces an explicit result with
    the change's final state and the reason for stopping.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    outcome: ContinuationOutcome
    initial_state: Optional[ChangeState] = None
    final_state: Optional[ChangeState] = None
    autonomous_steps_taken: int = 0
    stopped_reason: str = ""
    saga_result: Optional[SagaExecutionResult] = None
    recovery_result: Optional[SagaRecoveryResult] = None


class BackgroundContinuationRunner:
    """Runs queued sagas through reversible stages without an active chat.

    P-20.03: This runner is the autonomous-by-default execution engine.
    It picks up changes and drives them forward through the saga lifecycle
    autonomously, stopping only at irreversible authority boundaries.
    """

    def __init__(
        self,
        repository: SagaStateRepository,
        event_bus: LocalEventBus,
        *,
        timeout_seconds: float = DEFAULT_SAGA_TIMEOUT_SECONDS,
        evidence_mode: ExecutionEvidenceMode = ExecutionEvidenceMode.SIMULATION,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.timeout_seconds = timeout_seconds
        self.evidence_mode = evidence_mode

    def continue_saga(
        self,
        tenant_id: str,
        change_id: str,
        request: Optional[ChangeRequest] = None,
        *,
        now: Optional[datetime] = None,
    ) -> BackgroundContinuationResult:
        """Attempt to continue a saga autonomously from its current state.

        If the saga is in a non-terminal, non-blocked state, runs it forward.
        If it's at an authority boundary (AWAITING_AUTHORITY), pauses.
        If it's terminal, reports ALREADY_TERMINAL.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            # If we have a request, start a new saga
            if request is not None:
                return self._start_fresh_saga(tenant_id, request, now)
            return BackgroundContinuationResult(
                tenant_id=tenant_id,
                change_id=change_id,
                outcome=ContinuationOutcome.NOT_FOUND,
                stopped_reason=f"Change {change_id!r} not found",
            )

        initial_state = record.state

        if is_terminal(initial_state):
            return BackgroundContinuationResult(
                tenant_id=tenant_id,
                change_id=change_id,
                outcome=ContinuationOutcome.ALREADY_TERMINAL,
                initial_state=initial_state,
                final_state=initial_state,
                stopped_reason=f"Already in terminal state {initial_state.value}",
            )

        # Authority boundary: cannot proceed without human decision
        if initial_state == ChangeState.AWAITING_AUTHORITY:
            return BackgroundContinuationResult(
                tenant_id=tenant_id,
                change_id=change_id,
                outcome=ContinuationOutcome.PAUSED_AT_AUTHORITY,
                initial_state=initial_state,
                final_state=initial_state,
                stopped_reason="Waiting for human authority decision",
            )

        # Ambiguity boundary: cannot proceed if open ambiguity exists
        ambiguities = self.repository.list_ambiguities(tenant_id, change_id)
        open_ambiguities = [
            a for a in ambiguities if a.resolution_status == AmbiguityResolutionStatus.OPEN
        ]
        if open_ambiguities:
            return BackgroundContinuationResult(
                tenant_id=tenant_id,
                change_id=change_id,
                outcome=ContinuationOutcome.PAUSED_AT_AMBIGUITY,
                initial_state=initial_state,
                final_state=initial_state,
                stopped_reason=(
                    f"Waiting for ambiguity resolution: {open_ambiguities[0].minimal_question}"
                ),
            )

        # Reconstruct request from record if not provided
        effective_request = request
        if effective_request is None:
            target_systems = (
                list(record.target_systems)
                if hasattr(record, "target_systems") and record.target_systems
                else ["billing-db", "payment-service"]
            )
            effective_request = ChangeRequest(
                schema_version="1.0.0",
                request_id=record.correlation_id,
                title=record.title if hasattr(record, "title") and record.title else change_id,
                description=record.description if hasattr(record, "description") else "",
                target_systems=target_systems,
                data_classification=record.data_classification
                if hasattr(record, "data_classification")
                else DataClassLevel.INTERNAL,
                success_criteria=(
                    list(record.success_criteria)
                    if hasattr(record, "success_criteria") and record.success_criteria
                    else [
                        SuccessCriterion(
                            schema_version="1.0.0",
                            criterion_id="crit-default",
                            description="Autonomous change execution verification",
                            verification_method="deterministic",
                            required_evidence_types=["REHEARSAL_SIMULATION"],
                        )
                    ]
                ),
                requested_by=record.requested_by if hasattr(record, "requested_by") else "system",
                requested_at=record.requested_at if hasattr(record, "requested_at") else now,
            )

        # Run the saga forward with the SAME change_id
        timeline = CausalEventTimeline(tenant_id)
        orchestrator = ChangeSagaOrchestrator(
            repository=self.repository,
            event_bus=self.event_bus,
            timeline=timeline,
        )

        try:
            saga_result = orchestrator.run_saga(
                tenant_id,
                effective_request,
                change_id=change_id,
                evidence_mode=self.evidence_mode,
                now=now,
            )
            outcome = (
                ContinuationOutcome.COMPLETED
                if saga_result.final_state == ChangeState.COMPLETE
                else ContinuationOutcome.PAUSED_AT_AUTHORITY
                if saga_result.final_state == ChangeState.AWAITING_AUTHORITY
                else ContinuationOutcome.FAILED
                if saga_result.final_state == ChangeState.FAILED
                else ContinuationOutcome.COMPLETED
            )

            metrics = orchestrator.compute_autonomy_metrics(tenant_id, change_id)
            return BackgroundContinuationResult(
                tenant_id=tenant_id,
                change_id=saga_result.change_id,
                outcome=outcome,
                initial_state=saga_result.initial_state,
                final_state=saga_result.final_state,
                autonomous_steps_taken=metrics["autonomous_steps"],
                stopped_reason=saga_result.stopped_reason or "",
                saga_result=saga_result,
            )

        except Exception as e:
            logger.error(
                "Background continuation failed for %s/%s: %s",
                tenant_id,
                change_id,
                str(e),
            )
            return BackgroundContinuationResult(
                tenant_id=tenant_id,
                change_id=change_id,
                outcome=ContinuationOutcome.FAILED,
                initial_state=initial_state,
                stopped_reason=f"Background execution failed: {str(e)[:200]}",
            )

    def _start_fresh_saga(
        self,
        tenant_id: str,
        request: ChangeRequest,
        now: datetime,
    ) -> BackgroundContinuationResult:
        """Start a fresh saga run for a new change request."""
        timeline = CausalEventTimeline(tenant_id)
        orchestrator = ChangeSagaOrchestrator(
            repository=self.repository,
            event_bus=self.event_bus,
            timeline=timeline,
        )

        try:
            saga_result = orchestrator.run_saga(
                tenant_id,
                request,
                evidence_mode=self.evidence_mode,
                now=now,
            )
            outcome = (
                ContinuationOutcome.COMPLETED
                if saga_result.final_state == ChangeState.COMPLETE
                else ContinuationOutcome.PAUSED_AT_AUTHORITY
                if saga_result.final_state == ChangeState.AWAITING_AUTHORITY
                else ContinuationOutcome.FAILED
                if saga_result.final_state == ChangeState.FAILED
                else ContinuationOutcome.COMPLETED
            )

            return BackgroundContinuationResult(
                tenant_id=tenant_id,
                change_id=saga_result.change_id,
                outcome=outcome,
                initial_state=saga_result.initial_state,
                final_state=saga_result.final_state,
                autonomous_steps_taken=saga_result.events_emitted,
                stopped_reason=saga_result.stopped_reason or "",
                saga_result=saga_result,
            )

        except Exception as e:
            logger.error(
                "Background fresh saga failed for %s: %s",
                tenant_id,
                str(e),
            )
            return BackgroundContinuationResult(
                tenant_id=tenant_id,
                change_id="",
                outcome=ContinuationOutcome.FAILED,
                stopped_reason=f"Fresh saga failed: {str(e)[:200]}",
            )
