"""ChangeMesh state repository and optimistic concurrency tests.

P-10.02: Concurrency, tenancy isolation, schema validation, and CAS tests.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from domain.contracts.autonomy import AutonomyClass
from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import (
    EvidenceProducerKind,
    EvidenceState,
    ExecutionEvidenceMode,
)
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.state_repository import (
    ApprovalRecord,
    ApprovalResolutionStatus,
    ChangeRecord,
    CheckpointRecord,
    DocumentNotFoundError,
    EvidenceRefRecord,
    OptimisticConcurrencyError,
    PassportRecord,
    PersistenceSchemaError,
    TaskRecord,
    TenantIsolationError,
    TenantRecord,
    TenantStatus,
    validate_tenant_id,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

    # Attempting to save change under mismatched tenant path fails closed
    with pytest.raises(TenantIsolationError):
        repo.create_change("tenant-beta", change)

    # Saving under correct tenant succeeds
    repo.create_change("tenant-alpha", change)

    # Fetching from wrong tenant returns None
    assert repo.get_change("tenant-beta", "chg-001") is None
    assert repo.get_change("tenant-alpha", "chg-001") is not None


# ============================================================================
# Optimistic Concurrency Control (OCC) Tests
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
    updated_a = created.model_copy(update={"state": ChangeState.DISCOVERING, "state_updated_at": _utc_now()})
    res_a = repo.update_change("tenant-occ", updated_a, expected_version=1)
    assert res_a.version == 2
    assert res_a.state == ChangeState.DISCOVERING

    # Worker B tries to update using stale expected_version=1 -> OptimisticConcurrencyError
    updated_b = created.model_copy(update={"state": ChangeState.QUALIFYING, "state_updated_at": _utc_now()})
    with pytest.raises(OptimisticConcurrencyError) as exc_info:
        repo.update_change("tenant-occ", updated_b, expected_version=1)
    assert exc_info.value.expected_version == 1
    assert exc_info.value.actual_version == 2

    # Worker B re-reads and updates with expected_version=2 -> succeeds
    latest = repo.get_change("tenant-occ", "chg-occ-1")
    assert latest is not None
    assert latest.version == 2
    updated_b2 = latest.model_copy(update={"state": ChangeState.QUALIFYING, "state_updated_at": _utc_now()})
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
            # Everyone tries to advance version 1
            rec = repo.get_change("tenant-mt", "chg-mt-1")
            assert rec is not None
            candidate = rec.model_copy(update={"title": f"Updated by thread"})
            repo.update_change("tenant-mt", candidate, expected_version=1)
            success_count += 1
        except OptimisticConcurrencyError:
            conflict_count += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(try_update) for _ in range(8)]
        concurrent.futures.wait(futures)

    # Exactly 1 thread must succeed at version 1, remaining 7 must conflict
    assert success_count == 1
    assert conflict_count == 7
    final_doc = repo.get_change("tenant-mt", "chg-mt-1")
    assert final_doc is not None
    assert final_doc.version == 2


# ============================================================================
# Child Documents & Referential Integrity Tests
# ============================================================================

def test_tasks_and_checkpoints_hierarchy():
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    repo.create_tenant(
        TenantRecord(tenant_id="tenant-sub", name="Sub Org", created_at=now, updated_at=now)
    )

    # Creating task without parent change fails closed
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

    # Create change first
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

    # Now creating tasks succeeds
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
    t2 = TaskRecord(
        tenant_id="tenant-sub",
        change_id="chg-sub-1",
        task_id="task-02",
        sequence_number=2,
        agent_id="migration_engineer",
        agent_role="Migration Engineer",
        agent_revision="rev-2",
        action_class="SYNTHESIS",
        created_at=now,
        updated_at=now,
    )
    repo.create_task("tenant-sub", "chg-sub-1", t1)
    repo.create_task("tenant-sub", "chg-sub-1", t2)

    tasks = repo.list_tasks("tenant-sub", "chg-sub-1")
    assert len(tasks) == 2
    assert tasks[0].task_id == "task-01"
    assert tasks[1].task_id == "task-02"

    # Checkpoint
    digest = "a" * 64
    cp1 = CheckpointRecord(
        tenant_id="tenant-sub",
        change_id="chg-sub-1",
        checkpoint_id="cp-01",
        sequence_number=1,
        lifecycle_state_at_checkpoint=ChangeState.DISCOVERING,
        completed_task_ids=("task-01",),
        checkpoint_digest=digest,
        created_at=now,
    )
    cp2 = CheckpointRecord(
        tenant_id="tenant-sub",
        change_id="chg-sub-1",
        checkpoint_id="cp-02",
        sequence_number=2,
        lifecycle_state_at_checkpoint=ChangeState.QUALIFYING,
        completed_task_ids=("task-01", "task-02"),
        checkpoint_digest=digest,
        created_at=now,
    )
    repo.create_checkpoint("tenant-sub", "chg-sub-1", cp1)
    repo.create_checkpoint("tenant-sub", "chg-sub-1", cp2)

    latest = repo.get_latest_checkpoint("tenant-sub", "chg-sub-1")
    assert latest is not None
    assert latest.checkpoint_id == "cp-02"
    assert latest.sequence_number == 2


# ============================================================================
# Capability Passport Query & Revocation Tests
# ============================================================================

def test_passport_active_lookup_and_revocation():
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    repo.create_tenant(
        TenantRecord(tenant_id="tenant-pass", name="Passport Org", created_at=now, updated_at=now)
    )

    valid_passport = PassportRecord(
        tenant_id="tenant-pass",
        passport_id="pass-001",
        agent_id="migration_engineer",
        agent_revision="sha-rev-1",
        qualified_capabilities=("SCHEMA_MIGRATION",),
        qualification_evidence_ids=("ev-001",),
        issuer="test_runner",
        issued_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=30),
        is_revoked=False,
        created_at=now,
        updated_at=now,
    )
    repo.create_passport("tenant-pass", valid_passport)

    active = repo.get_active_passport("tenant-pass", "migration_engineer", "sha-rev-1")
    assert active is not None
    assert active.passport_id == "pass-001"

    # Revoke passport
    revoked = valid_passport.model_copy(
        update={
            "is_revoked": True,
            "revoked_at": _utc_now(),
            "revocation_reason": "Failed critical rehearsal test",
        }
    )
    repo.update_passport("tenant-pass", revoked, expected_version=1)

    # Active lookup now returns None
    assert repo.get_active_passport("tenant-pass", "migration_engineer", "sha-rev-1") is None


# ============================================================================
# Zero Secret Persistence Tests
# ============================================================================

def test_secret_persistence_rejected():
    repo = InMemorySagaStateRepository()
    now = _utc_now()

    repo.create_tenant(
        TenantRecord(tenant_id="tenant-sec", name="Security Org", created_at=now, updated_at=now)
    )

    # Extra fields like 'api_key' rejected by Pydantic extra='forbid'
    with pytest.raises(ValidationError):
        TenantRecord(
            tenant_id="tenant-sec-2",
            name="Sec Org",
            api_key="secret-12345",  # type: ignore[call-arg]
            created_at=now,
            updated_at=now,
        )

    # Private key in free text rejected by scan_for_secrets
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
