"""ChangeMesh state repository and optimistic concurrency tests.

P-10.02: Concurrency, tenancy isolation, schema validation, and CAS tests
for both InMemorySagaStateRepository and GoogleFirestoreSagaRepository.
"""

from __future__ import annotations

import concurrent.futures
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest
from pydantic import ValidationError

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.data_class import DataClassLevel
from integrations.gcp.firestore_adapter import GoogleFirestoreSagaRepository
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.state_repository import (
    ApprovalRecord,
    ChangeRecord,
    DocumentNotFoundError,
    IdempotencyReservationRecord,
    IdempotencyReservationStatus,
    OptimisticConcurrencyError,
    PassportRecord,
    PersistenceSchemaError,
    SagaStateRepository,
    TaskRecord,
    TenantIsolationError,
    TenantRecord,
    TenantStatus,
    validate_tenant_id,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# Fake Firestore Engine for Deterministic Adapter Testing
# ============================================================================


class FakeFirestoreSnapshot:
    def __init__(self, exists: bool, data: Optional[dict] = None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class FakeFirestoreDocRef:
    def __init__(self, collection_path: str, doc_id: str, store: dict):
        self.collection_path = collection_path
        self.id = doc_id
        self._store = store
        self._key = f"{collection_path}/{doc_id}"

    @property
    def exists(self) -> bool:
        return self._key in self._store

    def get(self, transaction=None):
        if transaction:
            return transaction.get(self)
        if self._key in self._store:
            return FakeFirestoreSnapshot(True, dict(self._store[self._key]))
        return FakeFirestoreSnapshot(False)

    def set(self, data: dict):
        self._store[self._key] = dict(data)

    def delete(self):
        self._store.pop(self._key, None)

    def collection(self, name: str):
        return FakeFirestoreCollection(f"{self._key}/{name}", self._store)


class FakeFirestoreCollection:
    def __init__(self, path: str, store: dict):
        self.path = path
        self._store = store

    def document(self, doc_id: str):
        return FakeFirestoreDocRef(self.path, doc_id, self._store)

    def where(self, field: str, op: str, value: Any):
        return FakeFirestoreQuery(self.path, self._store, [(field, op, value)])

    def stream(self):
        prefix = f"{self.path}/"
        results = []
        for k, v in list(self._store.items()):
            if k.startswith(prefix) and "/" not in k[len(prefix) :]:
                snap = FakeFirestoreSnapshot(True, dict(v))
                doc_id = k[len(prefix) :]
                setattr(snap, "id", doc_id)
                ref = FakeFirestoreDocRef(self.path, doc_id, self._store)
                setattr(snap, "reference", ref)
                results.append(snap)
        return results


class FakeFirestoreQuery:
    def __init__(self, path: str, store: dict, filters: list):
        self.path = path
        self._store = store
        self.filters = filters

    def where(self, field: str, op: str, value: Any):
        return FakeFirestoreQuery(self.path, self._store, self.filters + [(field, op, value)])

    def stream(self):
        prefix = f"{self.path}/"
        results = []
        for k, v in list(self._store.items()):
            if k.startswith(prefix) and "/" not in k[len(prefix) :]:
                match = True
                for f, op, val in self.filters:
                    if op == "==" and v.get(f) != val:
                        match = False
                        break
                if match:
                    results.append(FakeFirestoreSnapshot(True, dict(v)))
        return results


class FakeFirestoreTransaction:
    def __init__(self, store: dict, lock: threading.RLock):
        self._store = store
        self._lock = lock
        self._read_versions: dict[str, Any] = {}
        self._writes: dict[str, Any] = {}

    def get(self, doc_ref):
        with self._lock:
            key = doc_ref._key
            if key in self._store:
                data = dict(self._store[key])
                self._read_versions[key] = data.get("version", 0)
                return FakeFirestoreSnapshot(True, data)
            self._read_versions[key] = None
            return FakeFirestoreSnapshot(False)

    def set(self, doc_ref, data):
        self._writes[doc_ref._key] = dict(data)

    def commit(self):
        with self._lock:
            for key, read_ver in self._read_versions.items():
                current_data = self._store.get(key)
                current_ver = current_data.get("version", 0) if current_data else None
                if current_ver != read_ver:
                    raise Exception("Transactional collision: modified concurrently")
            for key, write_data in self._writes.items():
                self._store[key] = dict(write_data)


class FakeFirestoreClient:
    def __init__(self):
        self._store: dict[str, Any] = {}
        self._lock = threading.RLock()

    def collection(self, name: str):
        return FakeFirestoreCollection(name, self._store)

    def transaction(self):
        return FakeFirestoreTransaction(self._store, self._lock)


# ============================================================================
# Tenant & Isolation Tests
# ============================================================================


def test_tenant_id_validation():
    assert validate_tenant_id("tenant-demo-123") == "tenant-demo-123"
    assert validate_tenant_id("tenant_org_456") == "tenant_org_456"

    with pytest.raises(TenantIsolationError):
        validate_tenant_id("")
    with pytest.raises(TenantIsolationError):
        validate_tenant_id("ab")  # too short (<3)
    with pytest.raises(TenantIsolationError):
        validate_tenant_id("tenant/with/slashes")
    with pytest.raises(TenantIsolationError):
        validate_tenant_id("tenant with spaces")


def test_tenant_crud_and_isolation():
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    tenant = TenantRecord(
        tenant_id="tenant-alpha",
        name="Alpha Org",
        status=TenantStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    saved = repo.create_tenant(tenant)
    assert saved.tenant_id == "tenant-alpha"
    assert saved.version == 1

    fetched = repo.get_tenant("tenant-alpha")
    assert fetched is not None
    assert fetched.name == "Alpha Org"

    # Nonexistent tenant
    assert repo.get_tenant("tenant-beta") is None


def test_cross_tenant_isolation_rejected():
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    repo.create_tenant(
        TenantRecord(tenant_id="tenant-alpha", name="Alpha", created_at=now, updated_at=now)
    )
    repo.create_tenant(
        TenantRecord(tenant_id="tenant-beta", name="Beta", created_at=now, updated_at=now)
    )

    change = ChangeRecord(
        tenant_id="tenant-alpha",
        change_id="chg-001",
        correlation_id="corr-001",
        title="Test Change",
        description="A test change intent",
        target_systems=("repo-a",),
        data_classification=DataClassLevel.INTERNAL,
        requested_by="user-01",
        requested_at=now,
        state=ChangeState.RECEIVED,
        state_updated_at=now,
        created_at=now,
        updated_at=now,
    )

    with pytest.raises(TenantIsolationError):
        repo.create_change("tenant-beta", change)

    repo.create_change("tenant-alpha", change)
    assert repo.get_change("tenant-beta", "chg-001") is None
    assert repo.get_change("tenant-alpha", "chg-001") is not None


# ============================================================================
# Optimistic Concurrency Control (OCC) Tests - InMemory
# ============================================================================


def test_change_occ_cas_versioning():
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    repo.create_tenant(
        TenantRecord(tenant_id="tenant-occ", name="OCC Org", created_at=now, updated_at=now)
    )

    change = ChangeRecord(
        tenant_id="tenant-occ",
        change_id="chg-occ-1",
        correlation_id="corr-1",
        title="OCC Test",
        description="Testing CAS",
        target_systems=("repo-1",),
        data_classification=DataClassLevel.INTERNAL,
        requested_by="user-1",
        requested_at=now,
        state=ChangeState.RECEIVED,
        state_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    created = repo.create_change("tenant-occ", change)
    assert created.version == 1

    # Worker A updates with expected_version=1
    updated_a = created.model_copy(
        update={"state": ChangeState.DISCOVERING, "state_updated_at": _utc_now()}
    )
    res_a = repo.update_change("tenant-occ", updated_a, expected_version=1)
    assert res_a.version == 2
    assert res_a.state == ChangeState.DISCOVERING

    # Worker B tries to update using stale expected_version=1 -> OptimisticConcurrencyError
    updated_b = created.model_copy(
        update={"state": ChangeState.QUALIFYING, "state_updated_at": _utc_now()}
    )
    with pytest.raises(OptimisticConcurrencyError) as exc_info:
        repo.update_change("tenant-occ", updated_b, expected_version=1)
    assert exc_info.value.expected_version == 1
    assert exc_info.value.actual_version == 2

    # Worker B re-reads and updates with expected_version=2 -> succeeds
    latest = repo.get_change("tenant-occ", "chg-occ-1")
    assert latest is not None
    assert latest.version == 2
    updated_b2 = latest.model_copy(
        update={"state": ChangeState.QUALIFYING, "state_updated_at": _utc_now()}
    )
    res_b2 = repo.update_change("tenant-occ", updated_b2, expected_version=2)
    assert res_b2.version == 3
    assert res_b2.state == ChangeState.QUALIFYING


def test_concurrent_multi_threaded_updates():
    """Verify thread-safety and CAS under true concurrent execution."""
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    repo.create_tenant(
        TenantRecord(tenant_id="tenant-mt", name="MT Org", created_at=now, updated_at=now)
    )
    change = ChangeRecord(
        tenant_id="tenant-mt",
        change_id="chg-mt-1",
        correlation_id="corr-mt",
        title="Multi-thread OCC",
        description="Testing threading",
        target_systems=("repo-1",),
        data_classification=DataClassLevel.INTERNAL,
        requested_by="user-1",
        requested_at=now,
        state=ChangeState.RECEIVED,
        state_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    repo.create_change("tenant-mt", change)

    success_count = 0
    conflict_count = 0

    def try_update():
        nonlocal success_count, conflict_count
        try:
            rec = repo.get_change("tenant-mt", "chg-mt-1")
            assert rec is not None
            candidate = rec.model_copy(update={"title": "Updated by thread"})
            repo.update_change("tenant-mt", candidate, expected_version=1)
            success_count += 1
        except OptimisticConcurrencyError:
            conflict_count += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(try_update) for _ in range(8)]
        concurrent.futures.wait(futures)

    assert success_count == 1
    assert conflict_count == 7
    final_doc = repo.get_change("tenant-mt", "chg-mt-1")
    assert final_doc is not None
    assert final_doc.version == 2


# ============================================================================
# GoogleFirestoreSagaRepository Contract Completeness & Atomic OCC Tests
# ============================================================================


def test_firestore_repository_instantiable_and_concrete():
    """Prove GoogleFirestoreSagaRepository is concrete and implements full abstract protocol."""
    fake_client = FakeFirestoreClient()
    repo = GoogleFirestoreSagaRepository(project_id="test-proj-123", firestore_client=fake_client)

    assert isinstance(repo, SagaStateRepository)
    assert not getattr(repo, "__abstractmethods__", None)


def test_firestore_adapter_atomic_occ_and_all_entity_types():
    """Verify atomic CAS across Change, Task, Approval, Passport, and Idempotency reservation."""
    fake_client = FakeFirestoreClient()
    repo = GoogleFirestoreSagaRepository(project_id="test-proj-123", firestore_client=fake_client)
    now = _utc_now()
    tid = "tenant-fs-occ"
    cid = "chg-fs-01"

    # 1. Tenant
    repo.create_tenant(TenantRecord(tenant_id=tid, name="FS Org", created_at=now, updated_at=now))

    # 2. Change
    change = ChangeRecord(
        tenant_id=tid,
        change_id=cid,
        correlation_id="corr-fs",
        title="FS Change",
        description="Testing FS OCC",
        target_systems=("postgres",),
        data_classification=DataClassLevel.INTERNAL,
        requested_by="dba",
        requested_at=now,
        state=ChangeState.RECEIVED,
        state_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    repo.create_change(tid, change)

    # Atomic CAS on Change
    up_chg = change.model_copy(update={"state": ChangeState.DISCOVERING})
    saved_chg = repo.update_change(tid, up_chg, expected_version=1)
    assert saved_chg.version == 2

    # Stale version fails closed
    with pytest.raises(OptimisticConcurrencyError):
        repo.update_change(tid, up_chg, expected_version=1)

    # 3. Task
    task = TaskRecord(
        tenant_id=tid,
        change_id=cid,
        task_id="task-fs-01",
        sequence_number=1,
        agent_id="impact_scout",
        agent_role="Impact Scout",
        agent_revision="rev-1",
        action_class="ANALYSIS",
        created_at=now,
        updated_at=now,
    )
    repo.create_task(tid, cid, task)

    up_task = task.model_copy(update={"output_summary": "Analysis completed"})
    saved_task = repo.update_task(tid, cid, up_task, expected_version=1)
    assert saved_task.version == 2

    with pytest.raises(OptimisticConcurrencyError):
        repo.update_task(tid, cid, up_task, expected_version=1)

    # 4. Approval
    approval = ApprovalRecord(
        tenant_id=tid,
        change_id=cid,
        card_id="card-fs-01",
        authority_slot_ref="slot:lead_dba",
        decision_question="Approve change?",
        decision_options=("APPROVE_EXECUTION", "REJECT"),
        policy_reason="Reversibility check",
        action_scope="Target: Postgres",
        completed_work_summary="Summary",
        rehearsed_work_summary="Rehearsal",
        remaining_decision_summary="Decision",
        card_created_at=now,
        created_at=now,
        updated_at=now,
    )
    repo.create_approval(tid, cid, approval)

    up_app = approval.model_copy(update={"selected_option": "APPROVE_EXECUTION"})
    saved_app = repo.update_approval(tid, cid, up_app, expected_version=1)
    assert saved_app.version == 2

    with pytest.raises(OptimisticConcurrencyError):
        repo.update_approval(tid, cid, up_app, expected_version=1)

    # 5. Passport
    passport = PassportRecord(
        tenant_id=tid,
        passport_id="pass-fs-01",
        agent_id="migration_engineer",
        agent_revision="rev-mig-1",
        qualified_capabilities=("SCHEMA_MIGRATION",),
        qualification_evidence_ids=("ev-01",),
        issuer="test_runner",
        issued_at=now,
        expires_at=now + timedelta(days=30),
        created_at=now,
        updated_at=now,
    )
    repo.create_passport(tid, passport)

    up_pass = passport.model_copy(update={"is_revoked": True, "revocation_reason": "Test"})
    saved_pass = repo.update_passport(tid, up_pass, expected_version=1)
    assert saved_pass.version == 2

    with pytest.raises(OptimisticConcurrencyError):
        repo.update_passport(tid, up_pass, expected_version=1)

    # 6. Idempotency Reservation
    res = IdempotencyReservationRecord(
        tenant_id=tid,
        change_id=cid,
        reservation_id="res-fs-01",
        idempotency_key="idem_workflow_step_123",
        action_type="SCHEMA_MIGRATION",
        payload_digest="a" * 64,
        status=IdempotencyReservationStatus.RESERVED,
        reserved_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    repo.create_idempotency_reservation(tid, cid, res)

    up_res = res.model_copy(update={"status": IdempotencyReservationStatus.COMMITTED})
    saved_res = repo.update_idempotency_reservation(tid, cid, up_res, expected_version=1)
    assert saved_res.version == 2

    with pytest.raises(OptimisticConcurrencyError):
        repo.update_idempotency_reservation(tid, cid, up_res, expected_version=1)


def test_firestore_adapter_concurrent_race_prevention():
    """Prove concurrent Firestore updates cannot silently overwrite under race conditions."""
    fake_client = FakeFirestoreClient()
    repo = GoogleFirestoreSagaRepository(project_id="test-proj-123", firestore_client=fake_client)
    now = _utc_now()
    tid = "tenant-fs-race"
    cid = "chg-fs-race-01"

    repo.create_tenant(TenantRecord(tenant_id=tid, name="Race Org", created_at=now, updated_at=now))
    change = ChangeRecord(
        tenant_id=tid,
        change_id=cid,
        correlation_id="corr-race",
        title="Race Test",
        description="Testing race safety",
        target_systems=("postgres",),
        data_classification=DataClassLevel.INTERNAL,
        requested_by="dba",
        requested_at=now,
        state=ChangeState.RECEIVED,
        state_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    repo.create_change(tid, change)

    success_count = 0
    conflict_count = 0

    def try_fs_update():
        nonlocal success_count, conflict_count
        try:
            rec = repo.get_change(tid, cid)
            assert rec is not None
            candidate = rec.model_copy(update={"title": "Updated concurrently"})
            repo.update_change(tid, candidate, expected_version=1)
            success_count += 1
        except OptimisticConcurrencyError:
            conflict_count += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(try_fs_update) for _ in range(8)]
        concurrent.futures.wait(futures)

    assert success_count == 1
    assert conflict_count == 7
    final_doc = repo.get_change(tid, cid)
    assert final_doc is not None
    assert final_doc.version == 2


def test_firestore_adapter_concurrent_fresh_reservation_race():
    """Prove concurrent fresh reservations on Firestore adapter cannot both succeed."""
    fake_client = FakeFirestoreClient()
    repo = GoogleFirestoreSagaRepository(project_id="test-proj-123", firestore_client=fake_client)
    now = _utc_now()
    tid = "tenant-res-race"
    cid = "chg-res-race-01"
    rid = "res-race-key"

    repo.create_tenant(
        TenantRecord(tenant_id=tid, name="Res Race Org", created_at=now, updated_at=now)
    )
    change = ChangeRecord(
        tenant_id=tid,
        change_id=cid,
        correlation_id="corr-res-race",
        title="Reservation Race Test",
        description="Testing reservation atomicity",
        target_systems=("postgres",),
        data_classification=DataClassLevel.INTERNAL,
        requested_by="dba",
        requested_at=now,
        state=ChangeState.RECEIVED,
        state_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    repo.create_change(tid, change)

    reservation = IdempotencyReservationRecord(
        tenant_id=tid,
        change_id=cid,
        reservation_id=rid,
        idempotency_key="key-fresh-concurrent",
        action_type="POSTGRES_SCHEMA_MIGRATE",
        payload_digest="a" * 64,
        status=IdempotencyReservationStatus.RESERVED,
        reserved_at=now,
        expires_at=now + timedelta(seconds=60),
    )

    success_count = 0
    conflict_count = 0

    def try_reserve():
        nonlocal success_count, conflict_count
        try:
            repo.create_idempotency_reservation(tid, cid, reservation)
            success_count += 1
        except PersistenceSchemaError:
            conflict_count += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(try_reserve) for _ in range(8)]
        concurrent.futures.wait(futures)

    assert success_count == 1
    assert conflict_count == 7
    stored = repo.get_idempotency_reservation(tid, cid, rid)
    assert stored is not None
    assert stored.reservation_id == rid


def test_firestore_adapter_atomic_cas_fails_closed_without_transaction():
    """Prove _atomic_cas_update fails closed when transaction semantics are missing."""

    class NonTransactionalClient:
        def collection(self, name: str):
            return None

    repo = GoogleFirestoreSagaRepository(
        project_id="test-proj-123", firestore_client=NonTransactionalClient()
    )
    with pytest.raises(
        RuntimeError, match="does not support required atomic transaction semantics"
    ):
        repo._atomic_cas_update(None, 1, {}, "path", TenantRecord)


def test_firestore_transaction_adversarial_fail_closed_semantics():
    """Adversarial suite proving fail-closed transaction semantics:
    A. client has transaction() but doc get does NOT support transaction-scoped read -> RuntimeError
    B. transaction object lacks atomic set -> RuntimeError
    C. transaction object lacks usable commit semantics -> RuntimeError
    D. no document mutation occurred after each failure
    E. reservation creation also fails closed with no residual reservation record
    """
    now = _utc_now()
    tid = "tenant-adv-tx"
    cid = "chg-adv-tx-01"
    rid = "res-adv-01"

    def _create_base_repo(client):
        repo = GoogleFirestoreSagaRepository(project_id="test-adv-proj", firestore_client=client)
        repo.create_tenant(
            TenantRecord(tenant_id=tid, name="Adv Org", created_at=now, updated_at=now)
        )
        repo.create_change(
            tid,
            ChangeRecord(
                tenant_id=tid,
                change_id=cid,
                correlation_id="corr-adv",
                title="Initial Title",
                description="Initial",
                target_systems=("sys",),
                data_classification=DataClassLevel.INTERNAL,
                requested_by="dba",
                requested_at=now,
                state=ChangeState.RECEIVED,
                state_updated_at=now,
                created_at=now,
                updated_at=now,
            ),
        )
        return repo

    sample_res = IdempotencyReservationRecord(
        tenant_id=tid,
        change_id=cid,
        reservation_id=rid,
        idempotency_key="key-adv-1",
        action_type="POSTGRES_SCHEMA_MIGRATE",
        payload_digest="f" * 64,
        status=IdempotencyReservationStatus.RESERVED,
        reserved_at=now,
        expires_at=now + timedelta(seconds=60),
    )

    # A. Document get does not accept transaction parameter & transaction has no get
    class NonTransactionalDocRef:
        def __init__(self, path, doc_id, store):
            self._key = f"{path}/{doc_id}"
            self._store = store
            self.id = doc_id
            self.collection_path = path

        def get(self):  # TypeError when called as get(transaction=txn)
            if self._key in self._store:
                return FakeFirestoreSnapshot(True, dict(self._store[self._key]))
            return FakeFirestoreSnapshot(False)

        def set(self, data):
            self._store[self._key] = dict(data)

        def collection(self, name):
            return NonTransactionalCollection(f"{self._key}/{name}", self._store)

    class NonTransactionalCollection:
        def __init__(self, path, store):
            self.path = path
            self.store = store

        def document(self, doc_id):
            return NonTransactionalDocRef(self.path, doc_id, self.store)

    class BadReadTxn:
        def __init__(self, store):
            self._store = store

        def set(self, doc_ref, data):
            pass

        def commit(self):
            pass

    class BadReadClient:
        def __init__(self):
            self._store: dict[str, Any] = {}

        def collection(self, name):
            return NonTransactionalCollection(name, self._store)

        def transaction(self):
            return BadReadTxn(self._store)

    client_a = BadReadClient()
    repo_a = _create_base_repo(client_a)
    orig_chg = repo_a.get_change(tid, cid)
    assert orig_chg is not None
    assert orig_chg.title == "Initial Title"

    with pytest.raises(RuntimeError, match="transaction-scoped read"):
        repo_a.update_change(
            tid, orig_chg.model_copy(update={"title": "Mutated"}), expected_version=1
        )

    # D. Assert no document mutation occurred
    after_a = repo_a.get_change(tid, cid)
    assert after_a is not None
    assert after_a.title == "Initial Title"
    assert after_a.version == 1

    with pytest.raises(RuntimeError, match="transaction-scoped read"):
        repo_a.create_idempotency_reservation(tid, cid, sample_res)
    assert repo_a.get_idempotency_reservation(tid, cid, rid) is None

    # B. Transaction lacks atomic set
    class BadWriteTxn:
        def __init__(self, store):
            self._store = store

        def get(self, doc_ref):
            key = doc_ref._key
            if key in self._store:
                return FakeFirestoreSnapshot(True, dict(self._store[key]))
            return FakeFirestoreSnapshot(False)

        # Lacks set()

        def commit(self):
            pass

    class BadWriteClient(FakeFirestoreClient):
        def transaction(self):
            return BadWriteTxn(self._store)

    client_b = BadWriteClient()
    repo_b = _create_base_repo(client_b)
    orig_b = repo_b.get_change(tid, cid)
    assert orig_b is not None

    with pytest.raises(RuntimeError, match="atomic write"):
        repo_b.update_change(
            tid, orig_b.model_copy(update={"title": "Mutated"}), expected_version=1
        )

    # D. Assert no document mutation occurred
    after_b = repo_b.get_change(tid, cid)
    assert after_b is not None
    assert after_b.title == "Initial Title"
    assert after_b.version == 1

    with pytest.raises(RuntimeError, match="atomic write"):
        repo_b.create_idempotency_reservation(tid, cid, sample_res)
    assert repo_b.get_idempotency_reservation(tid, cid, rid) is None

    # C. Transaction lacks usable commit semantics
    class BadCommitTxn:
        def __init__(self, store):
            self._store = store

        def get(self, doc_ref):
            key = doc_ref._key
            if key in self._store:
                return FakeFirestoreSnapshot(True, dict(self._store[key]))
            return FakeFirestoreSnapshot(False)

        def set(self, doc_ref, data):
            pass

        # Lacks commit() and _commit()

    class BadCommitClient(FakeFirestoreClient):
        def transaction(self):
            return BadCommitTxn(self._store)

    client_c = BadCommitClient()
    repo_c = _create_base_repo(client_c)
    orig_c = repo_c.get_change(tid, cid)
    assert orig_c is not None

    with pytest.raises(RuntimeError, match="commit semantics"):
        repo_c.update_change(
            tid, orig_c.model_copy(update={"title": "Mutated"}), expected_version=1
        )

    # D. Assert no document mutation occurred
    after_c = repo_c.get_change(tid, cid)
    assert after_c is not None
    assert after_c.title == "Initial Title"
    assert after_c.version == 1

    with pytest.raises(RuntimeError, match="commit semantics"):
        repo_c.create_idempotency_reservation(tid, cid, sample_res)
    assert repo_c.get_idempotency_reservation(tid, cid, rid) is None


# ============================================================================
# Child Documents & Zero Secret Tests
# ============================================================================


def test_tasks_and_checkpoints_hierarchy():
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    repo.create_tenant(
        TenantRecord(tenant_id="tenant-sub", name="Sub Org", created_at=now, updated_at=now)
    )

    task = TaskRecord(
        tenant_id="tenant-sub",
        change_id="chg-nonexistent",
        task_id="task-01",
        sequence_number=1,
        agent_id="impact_scout",
        agent_role="Impact Scout",
        agent_revision="rev-1",
        action_class="ANALYSIS",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(DocumentNotFoundError):
        repo.create_task("tenant-sub", "chg-nonexistent", task)

    change = ChangeRecord(
        tenant_id="tenant-sub",
        change_id="chg-sub-1",
        correlation_id="corr-sub",
        title="Sub Change",
        description="Has tasks",
        target_systems=("sys-1",),
        data_classification=DataClassLevel.INTERNAL,
        requested_by="u1",
        requested_at=now,
        state=ChangeState.RECEIVED,
        state_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    repo.create_change("tenant-sub", change)

    t1 = TaskRecord(
        tenant_id="tenant-sub",
        change_id="chg-sub-1",
        task_id="task-01",
        sequence_number=1,
        agent_id="impact_scout",
        agent_role="Impact Scout",
        agent_revision="rev-1",
        action_class="ANALYSIS",
        created_at=now,
        updated_at=now,
    )
    repo.create_task("tenant-sub", "chg-sub-1", t1)
    tasks = repo.list_tasks("tenant-sub", "chg-sub-1")
    assert len(tasks) == 1
    assert tasks[0].task_id == "task-01"


def test_secret_persistence_rejected():
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    repo.create_tenant(
        TenantRecord(tenant_id="tenant-sec", name="Security Org", created_at=now, updated_at=now)
    )

    with pytest.raises(ValidationError):
        TenantRecord(
            tenant_id="tenant-sec-2",
            name="Sec Org",
            api_key="secret-12345",  # type: ignore[call-arg]
            created_at=now,
            updated_at=now,
        )

    hdr = "".join([chr(45) * 5, "BEGIN ", "PRIVATE ", "KEY", chr(45) * 5])
    ftr = "".join([chr(45) * 5, "END ", "PRIVATE ", "KEY", chr(45) * 5])
    private_key_text = f"{hdr}\nMIIE...\n{ftr}"
    with pytest.raises(PersistenceSchemaError):
        change_with_key = ChangeRecord(
            tenant_id="tenant-sec",
            change_id="chg-sec-1",
            correlation_id="corr-sec",
            title="Secret Change",
            description=private_key_text,
            target_systems=("sys-1",),
            data_classification=DataClassLevel.INTERNAL,
            requested_by="u1",
            requested_at=now,
            state=ChangeState.RECEIVED,
            state_updated_at=now,
            created_at=now,
            updated_at=now,
        )
        repo.create_change("tenant-sec", change_with_key)
