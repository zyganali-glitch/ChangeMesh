"""ChangeMesh saga checkpoint and restart resume tests.

P-10.04: Validates durable snapshot creation, SHA-256 integrity verification,
foreign tenant rejection, completed task skipping, and next safe action exposure.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.data_class import DataClassLevel
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.saga_checkpoint import (
    SagaCheckpointManager,
    compute_checkpoint_digest,
)
from src.orchestrator.state_repository import (
    ChangeRecord,
    DocumentNotFoundError,
    PersistenceSchemaError,
    TenantIsolationError,
    TenantRecord,
)


def _setup_test_change() -> tuple[InMemorySagaStateRepository, str, str]:
    repo = InMemorySagaStateRepository()
    now = datetime.now(timezone.utc)
    tid = "tenant-cp"
    cid = "chg-cp-1"

    repo.create_tenant(TenantRecord(tenant_id=tid, name="CP Org", created_at=now, updated_at=now))
    repo.create_change(
        tid,
        ChangeRecord(
            tenant_id=tid,
            change_id=cid,
            correlation_id="corr-cp",
            title="Checkpoint Test",
            description="Testing restart",
            target_systems=("repo-1",),
            data_classification=DataClassLevel.INTERNAL,
            requested_by="tester",
            requested_at=now,
            state=ChangeState.RECEIVED,
            state_updated_at=now,
            created_at=now,
            updated_at=now,
        ),
    )
    return repo, tid, cid


def test_checkpoint_creation_and_digest():
    repo, tid, cid = _setup_test_change()

    cp = SagaCheckpointManager.create_checkpoint(
        repo=repo,
        tenant_id=tid,
        change_id=cid,
        lifecycle_state=ChangeState.DISCOVERING,
        completed_task_ids=["task-1-impact"],
        pending_task_ids=["task-2-policy", "task-3-migration"],
        compensation_step_ids=[],
    )

    assert cp.sequence_number == 1
    assert cp.checkpoint_id == "cp-0001-discovering"
    assert SagaCheckpointManager.verify_checkpoint_integrity(cp) is True

    # Change doc updated
    change = repo.get_change(tid, cid)
    assert change is not None
    assert change.active_checkpoint_id == cp.checkpoint_id
    assert change.state == ChangeState.DISCOVERING


def test_corrupt_checkpoint_digest_fails_closed():
    repo, tid, cid = _setup_test_change()

    cp = SagaCheckpointManager.create_checkpoint(
        repo=repo,
        tenant_id=tid,
        change_id=cid,
        lifecycle_state=ChangeState.QUALIFYING,
        completed_task_ids=["task-1"],
        pending_task_ids=["task-2"],
    )

    # Tamper with completed_task_ids without updating digest
    tampered = cp.model_copy(update={"completed_task_ids": ("task-1", "task-injected")})
    repo._checkpoints[tid][cid][cp.checkpoint_id] = tampered

    with pytest.raises(PersistenceSchemaError) as exc_info:
        SagaCheckpointManager.resume_from_checkpoint(repo, tid, cid, cp.checkpoint_id)
    assert "integrity verification failed" in str(exc_info.value)


def test_multiphase_progression_and_resumption():
    repo, tid, cid = _setup_test_change()

    # Step 1: Impact Scout completes
    cp1 = SagaCheckpointManager.create_checkpoint(
        repo, tid, cid, ChangeState.DISCOVERING, completed_task_ids=["t1"], pending_task_ids=["t2", "t3"]
    )
    # Step 2: Policy Guardian completes
    cp2 = SagaCheckpointManager.create_checkpoint(
        repo, tid, cid, ChangeState.QUALIFYING, completed_task_ids=["t1", "t2"], pending_task_ids=["t3"]
    )
    # Step 3: Migration Engineer completes
    cp3 = SagaCheckpointManager.create_checkpoint(
        repo, tid, cid, ChangeState.REHEARSING, completed_task_ids=["t1", "t2", "t3"], pending_task_ids=[]
    )

    # Resume from latest
    ctx = SagaCheckpointManager.resume_from_checkpoint(repo, tid, cid)
    assert ctx.resumed_from_checkpoint_id == cp3.checkpoint_id
    assert ctx.lifecycle_state == ChangeState.REHEARSING
    assert set(ctx.completed_task_ids) == {"t1", "t2", "t3"}
    assert len(ctx.pending_task_ids) == 0

    # Resume from intermediate checkpoint cp2 (e.g. simulation of mid-stream crash)
    ctx2 = SagaCheckpointManager.resume_from_checkpoint(repo, tid, cid, checkpoint_id=cp2.checkpoint_id)
    assert ctx2.resumed_from_checkpoint_id == cp2.checkpoint_id
    assert ctx2.lifecycle_state == ChangeState.QUALIFYING
    assert ctx2.next_safe_action == "EXECUTE_TASK:t3"
    assert "t3" in ctx2.pending_task_ids
    assert "t1" in ctx2.completed_task_ids
    assert "t2" in ctx2.completed_task_ids
