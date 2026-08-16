"""ChangeMesh saga checkpoint and restart resume manager.

P-10.04: Manages durable snapshot checkpointing and deterministic workflow
resume without unsafe repetition of completed work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.conventions import (
    UtcDateTime,
    canonical_json_bytes,
    sha256_hex,
)
from src.orchestrator.state_repository import (
    CANONICAL_SCHEMA_VERSION,
    CheckpointRecord,
    DocumentNotFoundError,
    PersistenceSchemaError,
    SagaStateRepository,
    TenantIsolationError,
    validate_tenant_id,
)


def compute_checkpoint_digest(
    tenant_id: str,
    change_id: str,
    sequence_number: int,
    lifecycle_state: ChangeState,
    completed_task_ids: Sequence[str],
    pending_task_ids: Sequence[str],
    compensation_step_ids: Sequence[str],
) -> str:
    """Compute canonical deterministic SHA-256 digest of checkpoint state."""
    payload = {
        "tenant_id": tenant_id,
        "change_id": change_id,
        "sequence_number": sequence_number,
        "lifecycle_state": lifecycle_state.value,
        "completed_task_ids": sorted(list(completed_task_ids)),
        "pending_task_ids": sorted(list(pending_task_ids)),
        "compensation_step_ids": sorted(list(compensation_step_ids)),
    }
    return sha256_hex(canonical_json_bytes(payload))


class SagaResumeContext(BaseModel):
    """Execution context restored from a durable checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    resumed_from_checkpoint_id: str
    sequence_number: int
    lifecycle_state: ChangeState
    completed_task_ids: Tuple[str, ...]
    pending_task_ids: Tuple[str, ...]
    compensation_step_ids: Tuple[str, ...]
    next_safe_action: Optional[str] = None
    resumed_at: UtcDateTime

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)


class SagaCheckpointManager:
    """Manages creation, verification, and resumption of saga checkpoints."""

    @classmethod
    def create_checkpoint(
        cls,
        repo: SagaStateRepository,
        tenant_id: str,
        change_id: str,
        lifecycle_state: ChangeState,
        completed_task_ids: Sequence[str] = (),
        pending_task_ids: Sequence[str] = (),
        compensation_step_ids: Sequence[str] = (),
        now: Optional[datetime] = None,
    ) -> CheckpointRecord:
        """Create and persist a new durable checkpoint."""
        if now is None:
            now = datetime.now(timezone.utc)

        tid = validate_tenant_id(tenant_id)
        change = repo.get_change(tid, change_id)
        if change is None:
            raise DocumentNotFoundError(f"Change {change_id!r} not found in tenant {tid!r}")

        existing_cps = repo.list_checkpoints(tid, change_id)
        next_seq = (existing_cps[0].sequence_number + 1) if existing_cps else 1
        cp_id = f"cp-{next_seq:04d}-{lifecycle_state.value.lower()}"

        digest = compute_checkpoint_digest(
            tenant_id=tid,
            change_id=change_id,
            sequence_number=next_seq,
            lifecycle_state=lifecycle_state,
            completed_task_ids=completed_task_ids,
            pending_task_ids=pending_task_ids,
            compensation_step_ids=compensation_step_ids,
        )

        record = CheckpointRecord(
            tenant_id=tid,
            change_id=change_id,
            checkpoint_id=cp_id,
            sequence_number=next_seq,
            lifecycle_state_at_checkpoint=lifecycle_state,
            completed_task_ids=tuple(completed_task_ids),
            pending_task_ids=tuple(pending_task_ids),
            compensation_step_ids=tuple(compensation_step_ids),
            checkpoint_digest=digest,
            created_at=now,
        )

        saved = repo.create_checkpoint(tid, change_id, record)

        # Update change pointer
        updated_change = change.model_copy(
            update={
                "active_checkpoint_id": cp_id,
                "state": lifecycle_state,
                "state_updated_at": now,
            }
        )
        repo.update_change(tid, updated_change, expected_version=change.version)

        return saved

    @classmethod
    def verify_checkpoint_integrity(cls, checkpoint: CheckpointRecord) -> bool:
        """Verify that the checkpoint digest matches its canonical state."""
        expected_digest = compute_checkpoint_digest(
            tenant_id=checkpoint.tenant_id,
            change_id=checkpoint.change_id,
            sequence_number=checkpoint.sequence_number,
            lifecycle_state=checkpoint.lifecycle_state_at_checkpoint,
            completed_task_ids=checkpoint.completed_task_ids,
            pending_task_ids=checkpoint.pending_task_ids,
            compensation_step_ids=checkpoint.compensation_step_ids,
        )
        return expected_digest == checkpoint.checkpoint_digest

    @classmethod
    def resume_from_checkpoint(
        cls,
        repo: SagaStateRepository,
        tenant_id: str,
        change_id: str,
        checkpoint_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> SagaResumeContext:
        """Load and validate checkpoint to construct the resume context."""
        if now is None:
            now = datetime.now(timezone.utc)

        tid = validate_tenant_id(tenant_id)
        change = repo.get_change(tid, change_id)
        if change is None:
            raise DocumentNotFoundError(f"Change {change_id!r} not found in tenant {tid!r}")

        if checkpoint_id:
            cp = repo.get_checkpoint(tid, change_id, checkpoint_id)
            if cp is None:
                raise DocumentNotFoundError(f"Checkpoint {checkpoint_id!r} not found")
        else:
            cp = repo.get_latest_checkpoint(tid, change_id)
            if cp is None:
                raise DocumentNotFoundError(f"No checkpoint found for change {change_id!r}")

        # Check tenant isolation
        if cp.tenant_id != tid:
            raise TenantIsolationError(f"Foreign tenant checkpoint {cp.tenant_id!r} rejected")

        # Verify integrity digest
        if not cls.verify_checkpoint_integrity(cp):
            raise PersistenceSchemaError(
                f"Checkpoint {cp.checkpoint_id!r} integrity verification failed: digest mismatch"
            )

        # Determine next safe action
        next_action: Optional[str] = None
        if cp.pending_task_ids:
            next_action = f"EXECUTE_TASK:{cp.pending_task_ids[0]}"
        elif cp.lifecycle_state_at_checkpoint == ChangeState.AWAITING_AUTHORITY:
            next_action = "AWAIT_HUMAN_AUTHORITY"
        elif cp.lifecycle_state_at_checkpoint == ChangeState.AUTHORIZED:
            next_action = "BEGIN_EXECUTION"
        elif cp.lifecycle_state_at_checkpoint == ChangeState.COMPENSATING:
            next_action = "EXECUTE_COMPENSATION"

        return SagaResumeContext(
            tenant_id=tid,
            change_id=change_id,
            resumed_from_checkpoint_id=cp.checkpoint_id,
            sequence_number=cp.sequence_number,
            lifecycle_state=cp.lifecycle_state_at_checkpoint,
            completed_task_ids=cp.completed_task_ids,
            pending_task_ids=cp.pending_task_ids,
            compensation_step_ids=cp.compensation_step_ids,
            next_safe_action=next_action,
            resumed_at=now,
        )
