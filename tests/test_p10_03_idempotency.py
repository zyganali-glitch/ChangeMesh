"""ChangeMesh idempotency key, replay safety, and semantic conflict tests.

P-10.03: Validates deterministic key generation, reservation leases,
semantic conflict detection (same key + different payload => conflict),
exact replay caching, and non-duplication across workflow steps, branches,
PRs, approvals, passports, and external writes.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta, timezone

import pytest

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.data_class import DataClassLevel
from src.orchestrator.idempotency import (
    IdempotencyConflictError,
    IdempotencyIntent,
    IdempotencyKeyManager,
    IdempotencyReservationOutcomeStatus,
    IdempotencyScope,
)
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.state_repository import (
    ChangeRecord,
    IdempotencyReservationStatus,
    TenantRecord,
)


def _setup_repo() -> tuple[InMemorySagaStateRepository, str, str]:
    repo = InMemorySagaStateRepository()
    now = datetime.now(timezone.utc)
    tid = "tenant-idem"
    cid = "chg-idem-1"

    repo.create_tenant(TenantRecord(tenant_id=tid, name="Idem Org", created_at=now, updated_at=now))
    repo.create_change(
        tid,
        ChangeRecord(
            tenant_id=tid,
            change_id=cid,
            correlation_id="corr-idem",
            title="Idempotency Test",
            description="Testing replay",
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


def test_key_derivation_determinism():
    intent1 = IdempotencyIntent(
        tenant_id="tenant-1",
        change_id="chg-1",
        scope=IdempotencyScope.BRANCH_INTENT,
        action_type="CREATE_FEATURE_BRANCH",
        target_system="github.com/org/repo",
        caller_revision="rev-abc",
        payload_digest="a" * 64,
    )
    intent2 = IdempotencyIntent(
        tenant_id="tenant-1",
        change_id="chg-1",
        scope=IdempotencyScope.BRANCH_INTENT,
        action_type="CREATE_FEATURE_BRANCH",
        target_system="github.com/org/repo",
        caller_revision="rev-abc",
        payload_digest="a" * 64,
    )
    key1 = IdempotencyKeyManager.compute_canonical_idempotency_key(intent1)
    key2 = IdempotencyKeyManager.compute_canonical_idempotency_key(intent2)
    assert key1 == key2
    assert key1.startswith("idem_branch_intent_")


def test_reservation_grant_and_commit_replay():
    repo, tid, cid = _setup_repo()
    intent = IdempotencyIntent(
        tenant_id=tid,
        change_id=cid,
        scope=IdempotencyScope.PR_INTENT,
        action_type="CREATE_DRAFT_PR",
        target_system="github.com/org/repo",
        caller_revision="rev-1",
        payload_digest="b" * 64,
    )

    # 1. First attempt: GRANTED
    outcome1 = IdempotencyKeyManager.reserve_intent(repo, intent)
    assert outcome1.status == IdempotencyReservationOutcomeStatus.GRANTED
    assert outcome1.reservation.status == IdempotencyReservationStatus.RESERVED

    # 2. Concurrent second attempt before commit: IN_PROGRESS
    outcome2 = IdempotencyKeyManager.reserve_intent(repo, intent)
    assert outcome2.status == IdempotencyReservationOutcomeStatus.IN_PROGRESS

    # 3. Complete and commit
    result_digest = "c" * 64
    committed = IdempotencyKeyManager.commit_intent(
        repo, tid, cid, outcome1.reservation.reservation_id, result_digest, receipt_status="APPLIED"
    )
    assert committed.status == IdempotencyReservationStatus.COMMITTED
    assert committed.result_digest == result_digest

    # 4. Identical replay attempt: EXACT_REPLAY returns cached outcome
    outcome3 = IdempotencyKeyManager.reserve_intent(repo, intent)
    assert outcome3.status == IdempotencyReservationOutcomeStatus.EXACT_REPLAY
    assert outcome3.cached_result_digest == result_digest
    assert outcome3.cached_receipt_status == "APPLIED"


def test_conflicting_payload_reuse_fails_closed():
    """Prove that same operation identity + different payload raises IdempotencyConflictError."""
    repo, tid, cid = _setup_repo()
    intent_orig = IdempotencyIntent(
        tenant_id=tid,
        change_id=cid,
        scope=IdempotencyScope.WORKFLOW_STEP,
        action_type="APPLY_MIGRATION",
        target_system="postgres-prod",
        caller_revision="rev-1",
        payload_digest="1" * 64,
    )

    # Reserve original intent
    out = IdempotencyKeyManager.reserve_intent(repo, intent_orig)
    assert out.status == IdempotencyReservationOutcomeStatus.GRANTED

    # Commit original intent
    IdempotencyKeyManager.commit_intent(
        repo, tid, cid, out.reservation.reservation_id, result_digest="9" * 64
    )

    # Reusing same logical identity with DIFFERENT payload MUST raise IdempotencyConflictError
    intent_conflict = intent_orig.model_copy(update={"payload_digest": "2" * 64})
    with pytest.raises(IdempotencyConflictError) as exc_info:
        IdempotencyKeyManager.reserve_intent(repo, intent_conflict)

    assert exc_info.value.existing_digest == "1" * 64
    assert exc_info.value.incoming_digest == "2" * 64


def test_conflicting_payload_in_active_lease_fails_closed():
    """Active uncommitted lease also fails closed on conflicting payload."""
    repo, tid, cid = _setup_repo()
    intent_orig = IdempotencyIntent(
        tenant_id=tid,
        change_id=cid,
        scope=IdempotencyScope.EXTERNAL_WRITE,
        action_type="WRITE_DATA",
        target_system="storage-bucket",
        caller_revision="rev-1",
        payload_digest="3" * 64,
    )
    IdempotencyKeyManager.reserve_intent(repo, intent_orig)

    intent_conflict = intent_orig.model_copy(update={"payload_digest": "4" * 64})
    with pytest.raises(IdempotencyConflictError):
        IdempotencyKeyManager.reserve_intent(repo, intent_conflict)


def test_different_target_and_action_generate_distinct_keys():
    """Verify different target_system and action_type produce separate reservation keys."""
    intent_base = IdempotencyIntent(
        tenant_id="tenant-1",
        change_id="c1",
        scope=IdempotencyScope.WORKFLOW_STEP,
        action_type="ACTION_A",
        target_system="system_alpha",
        caller_revision="rev-1",
        payload_digest="a" * 64,
    )
    intent_diff_target = intent_base.model_copy(update={"target_system": "system_beta"})
    intent_diff_action = intent_base.model_copy(update={"action_type": "ACTION_B"})

    key_base = IdempotencyKeyManager.compute_canonical_idempotency_key(intent_base)
    key_target = IdempotencyKeyManager.compute_canonical_idempotency_key(intent_diff_target)
    key_action = IdempotencyKeyManager.compute_canonical_idempotency_key(intent_diff_action)

    assert key_base != key_target
    assert key_base != key_action
    assert key_target != key_action


def test_concurrent_fresh_reservation_single_grant():
    """Prove concurrent attempts for fresh reservation receive at most 1 GRANTED."""

    repo, tid, cid = _setup_repo()
    intent = IdempotencyIntent(
        tenant_id=tid,
        change_id=cid,
        scope=IdempotencyScope.BRANCH_INTENT,
        action_type="CONCURRENT_BRANCH",
        target_system="git",
        caller_revision="rev-1",
        payload_digest="5" * 64,
    )

    granted_count = 0
    in_progress_count = 0

    def try_reserve():
        nonlocal granted_count, in_progress_count
        res = IdempotencyKeyManager.reserve_intent(repo, intent)
        if res.status == IdempotencyReservationOutcomeStatus.GRANTED:
            granted_count += 1
        elif res.status == IdempotencyReservationOutcomeStatus.IN_PROGRESS:
            in_progress_count += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(try_reserve) for _ in range(8)]
        concurrent.futures.wait(futures)

    assert granted_count == 1
    assert in_progress_count == 7


def test_lease_expiry_reacquisition():
    repo, tid, cid = _setup_repo()
    t0 = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)
    intent = IdempotencyIntent(
        tenant_id=tid,
        change_id=cid,
        scope=IdempotencyScope.WORKFLOW_STEP,
        action_type="EXECUTE_STEP_1",
        target_system="system-1",
        caller_revision="rev-1",
        payload_digest="d" * 64,
        lease_duration_seconds=300,
    )

    outcome1 = IdempotencyKeyManager.reserve_intent(repo, intent, now=t0)
    assert outcome1.status == IdempotencyReservationOutcomeStatus.GRANTED

    t1 = t0 + timedelta(minutes=10)
    outcome2 = IdempotencyKeyManager.reserve_intent(repo, intent, now=t1)
    assert outcome2.status == IdempotencyReservationOutcomeStatus.GRANTED
    assert outcome2.reservation.reserved_at == t1


def test_release_and_retry():
    repo, tid, cid = _setup_repo()
    intent = IdempotencyIntent(
        tenant_id=tid,
        change_id=cid,
        scope=IdempotencyScope.EXTERNAL_WRITE,
        action_type="APPLY_STAGING_MUTATION",
        target_system="staging-db",
        caller_revision="rev-1",
        payload_digest="e" * 64,
    )

    outcome1 = IdempotencyKeyManager.reserve_intent(repo, intent)
    assert outcome1.status == IdempotencyReservationOutcomeStatus.GRANTED

    released = IdempotencyKeyManager.release_intent(
        repo, tid, cid, outcome1.reservation.reservation_id
    )
    assert released.status == IdempotencyReservationStatus.RELEASED

    outcome2 = IdempotencyKeyManager.reserve_intent(repo, intent)
    assert outcome2.status == IdempotencyReservationOutcomeStatus.GRANTED


def test_tenant_isolation_in_idempotency():
    """Verify same change_id and key under different tenants are completely isolated."""
    repo = InMemorySagaStateRepository()
    now = datetime.now(timezone.utc)
    t1, t2 = "tenant-iso-1", "tenant-iso-2"
    cid = "chg-shared-id"

    repo.create_tenant(TenantRecord(tenant_id=t1, name="Org 1", created_at=now, updated_at=now))
    repo.create_tenant(TenantRecord(tenant_id=t2, name="Org 2", created_at=now, updated_at=now))

    repo.create_change(
        t1,
        ChangeRecord(
            tenant_id=t1,
            change_id=cid,
            correlation_id="corr-1",
            title="T1",
            description="T1",
            target_systems=("s1",),
            data_classification=DataClassLevel.INTERNAL,
            requested_by="u1",
            requested_at=now,
            state=ChangeState.RECEIVED,
            state_updated_at=now,
            created_at=now,
            updated_at=now,
        ),
    )
    repo.create_change(
        t2,
        ChangeRecord(
            tenant_id=t2,
            change_id=cid,
            correlation_id="corr-2",
            title="T2",
            description="T2",
            target_systems=("s1",),
            data_classification=DataClassLevel.INTERNAL,
            requested_by="u2",
            requested_at=now,
            state=ChangeState.RECEIVED,
            state_updated_at=now,
            created_at=now,
            updated_at=now,
        ),
    )

    intent1 = IdempotencyIntent(
        tenant_id=t1,
        change_id=cid,
        scope=IdempotencyScope.BRANCH_INTENT,
        action_type="BRANCH",
        target_system="git",
        caller_revision="rev-1",
        payload_digest="a" * 64,
    )
    intent2 = intent1.model_copy(update={"tenant_id": t2})

    out1 = IdempotencyKeyManager.reserve_intent(repo, intent1)
    out2 = IdempotencyKeyManager.reserve_intent(repo, intent2)

    assert out1.status == IdempotencyReservationOutcomeStatus.GRANTED
    assert out2.status == IdempotencyReservationOutcomeStatus.GRANTED
    assert out1.reservation.tenant_id == t1
    assert out2.reservation.tenant_id == t2
