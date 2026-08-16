"""ChangeMesh idempotency key and replay safety tests.

P-10.03: Validates deterministic key generation, reservation leases,
exact replay caching, and non-duplication across workflow steps, branches,
PRs, approvals, passports, and external writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.conventions import sha256_hex
from domain.contracts.data_class import DataClassLevel
from src.orchestrator.idempotency import (
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

    # 4. Replay attempt: EXACT_REPLAY returns cached outcome without duplicate execution
    outcome3 = IdempotencyKeyManager.reserve_intent(repo, intent)
    assert outcome3.status == IdempotencyReservationOutcomeStatus.EXACT_REPLAY
    assert outcome3.cached_result_digest == result_digest
    assert outcome3.cached_receipt_status == "APPLIED"


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
        lease_duration_seconds=300,  # 5 min
    )

    outcome1 = IdempotencyKeyManager.reserve_intent(repo, intent, now=t0)
    assert outcome1.status == IdempotencyReservationOutcomeStatus.GRANTED

    # After 10 minutes (lease expired)
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

    # Step fails transiently -> release reservation
    released = IdempotencyKeyManager.release_intent(
        repo, tid, cid, outcome1.reservation.reservation_id
    )
    assert released.status == IdempotencyReservationStatus.RELEASED

    # Retry can now re-acquire immediately
    outcome2 = IdempotencyKeyManager.reserve_intent(repo, intent)
    assert outcome2.status == IdempotencyReservationOutcomeStatus.GRANTED


def test_all_scopes_replay_protection():
    """Verify non-duplicate replay across all six canonical scopes."""
    repo, tid, cid = _setup_repo()
    scopes = [
        IdempotencyScope.WORKFLOW_STEP,
        IdempotencyScope.BRANCH_INTENT,
        IdempotencyScope.PR_INTENT,
        IdempotencyScope.APPROVAL,
        IdempotencyScope.PASSPORT,
        IdempotencyScope.EXTERNAL_WRITE,
    ]

    for scope in scopes:
        intent = IdempotencyIntent(
            tenant_id=tid,
            change_id=cid,
            scope=scope,
            action_type=f"ACTION_FOR_{scope.value}",
            target_system="target-system",
            caller_revision="rev-1",
            payload_digest="f" * 64,
        )
        res = IdempotencyKeyManager.reserve_intent(repo, intent)
        assert res.status == IdempotencyReservationOutcomeStatus.GRANTED

        digest = sha256_hex(scope.value.encode())
        IdempotencyKeyManager.commit_intent(repo, tid, cid, res.reservation.reservation_id, digest)

        replay = IdempotencyKeyManager.reserve_intent(repo, intent)
        assert replay.status == IdempotencyReservationOutcomeStatus.EXACT_REPLAY
        assert replay.cached_result_digest == digest
