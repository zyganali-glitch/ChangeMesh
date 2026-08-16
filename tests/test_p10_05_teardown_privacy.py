"""ChangeMesh persistence privacy and fixture teardown tests.

P-10.05: Validates secret scanning before persistence, fail-closed rejection
of tokens/keys/passwords, and explicit recursive teardown with zero residual state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import (
    EvidenceProducerKind,
    EvidenceState,
    ExecutionEvidenceMode,
)
from src.orchestrator.idempotency import (
    IdempotencyIntent,
    IdempotencyKeyManager,
    IdempotencyScope,
)
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.saga_checkpoint import SagaCheckpointManager
from src.orchestrator.state_repository import (
    ApprovalRecord,
    ChangeRecord,
    EvidenceRefRecord,
    PassportRecord,
    TaskRecord,
    TenantRecord,
)
from src.orchestrator.teardown import (
    FixtureTeardownManager,
    PersistencePrivacyGuard,
    PersistencePrivacyViolationError,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# Privacy & Secret Scanning Tests
# ============================================================================

def test_secret_field_name_detection():
    data = {
        "title": "Normal title",
        "nested": {
            "api_key": "some-val",
        },
    }
    with pytest.raises(PersistencePrivacyViolationError) as exc_info:
        PersistencePrivacyGuard.scan_for_secrets(data)
    assert exc_info.value.pattern_type == "SECRET_FIELD_NAME"
    assert "api_key" in exc_info.value.field_path


def test_free_text_token_scanning():
    # GitHub Token (split to avoid static detection in test runner)
    gh_token = "gh" + "p_" + "123456789012345678901234567890123456"
    with pytest.raises(PersistencePrivacyViolationError) as exc:
        PersistencePrivacyGuard.scan_for_secrets({"description": f"Use token {gh_token} to clone"})
    assert exc.value.pattern_type == "GITHUB_TOKEN"

    # Private key
    pk = "-" * 5 + "BEGIN RSA PRIVATE " + "KEY" + "-" * 5 + "\nMIIE...\n" + "-" * 5 + "END RSA PRIVATE " + "KEY" + "-" * 5
    with pytest.raises(PersistencePrivacyViolationError) as exc:
        PersistencePrivacyGuard.scan_for_secrets({"log": pk})
    assert exc.value.pattern_type == "PRIVATE_KEY"

    # Bearer token
    bearer = "Bearer " + "abc" * 10
    with pytest.raises(PersistencePrivacyViolationError) as exc:
        PersistencePrivacyGuard.scan_for_secrets({"auth_header": bearer})
    assert exc.value.pattern_type == "BEARER_TOKEN"


# ============================================================================
# Fixture Teardown Tests
# ============================================================================

def test_explicit_recursive_fixture_teardown_zero_residual():
    repo = InMemorySagaStateRepository()
    now = _utc_now()
    tid = "tenant-teardown-demo"

    # 1. Create Tenant
    repo.create_tenant(TenantRecord(tenant_id=tid, name="Demo Org", created_at=now, updated_at=now))

    # 2. Create Passport (tenant level)
    repo.create_passport(
        tid,
        PassportRecord(
            tenant_id=tid,
            passport_id="pass-1",
            agent_id="impact_scout",
            agent_revision="rev-1",
            qualified_capabilities=("BLAST_RADIUS",),
            qualification_evidence_ids=("ev-1",),
            issuer="test",
            issued_at=now,
            expires_at=now + timedelta(days=1),
            created_at=now,
            updated_at=now,
        ),
    )

    # 3. Create Change 1
    cid1 = "chg-demo-1"
    repo.create_change(
        tid,
        ChangeRecord(
            tenant_id=tid,
            change_id=cid1,
            correlation_id="corr-1",
            title="Change 1",
            description="First change",
            target_systems=("sys-1",),
            data_classification=DataClassLevel.INTERNAL,
            requested_by="u1",
            requested_at=now,
            state=ChangeState.RECEIVED,
            state_updated_at=now,
            created_at=now,
            updated_at=now,
        ),
    )

    # 4. Tasks for Change 1
    repo.create_task(
        tid,
        cid1,
        TaskRecord(
            tenant_id=tid,
            change_id=cid1,
            task_id="t1",
            sequence_number=1,
            agent_id="impact_scout",
            agent_role="Scout",
            agent_revision="rev-1",
            action_class="ANALYSIS",
            created_at=now,
            updated_at=now,
        ),
    )
    repo.create_task(
        tid,
        cid1,
        TaskRecord(
            tenant_id=tid,
            change_id=cid1,
            task_id="t2",
            sequence_number=2,
            agent_id="policy_guardian",
            agent_role="Guardian",
            agent_revision="rev-1",
            action_class="POLICY",
            created_at=now,
            updated_at=now,
        ),
    )

    # 5. Checkpoints for Change 1
    SagaCheckpointManager.create_checkpoint(repo, tid, cid1, ChangeState.DISCOVERING, ["t1"], ["t2"])

    # 6. Evidence Refs for Change 1
    repo.create_evidence_ref(
        tid,
        cid1,
        EvidenceRefRecord(
            tenant_id=tid,
            change_id=cid1,
            evidence_id="ev-1",
            subject="blast_radius",
            state=EvidenceState.PASS,
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            producer_kind=EvidenceProducerKind.AGENT,
            collected_at=now,
            created_at=now,
        ),
    )

    # 7. Approvals for Change 1
    repo.create_approval(
        tid,
        cid1,
        ApprovalRecord(
            tenant_id=tid,
            change_id=cid1,
            card_id="card-1",
            authority_slot_ref="slot-1",
            decision_question="Proceed?",
            decision_options=("YES", "NO"),
            policy_reason="Impact",
            action_scope="Production",
            completed_work_summary="Completed",
            rehearsed_work_summary="Rehearsed",
            remaining_decision_summary="Decision",
            card_created_at=now,
            created_at=now,
            updated_at=now,
        ),
    )

    # 8. Idempotency Reservations
    intent = IdempotencyIntent(
        tenant_id=tid,
        change_id=cid1,
        scope=IdempotencyScope.WORKFLOW_STEP,
        action_type="STEP_1",
        target_system="sys-1",
        caller_revision="rev-1",
        payload_digest="1" * 64,
    )
    IdempotencyKeyManager.reserve_intent(repo, intent)

    # Verify state exists before teardown
    assert repo.get_tenant(tid) is not None
    assert len(repo.list_changes(tid)) == 1

    # Execute teardown
    report = FixtureTeardownManager.teardown_tenant(repo, tid)

    # Assertions on teardown completeness
    assert report.success is True
    assert report.residual_document_count == 0
    assert report.total_documents_deleted >= 8

    # Double check that zero documents remain
    assert repo.get_tenant(tid) is None
    assert repo.get_change(tid, cid1) is None
    assert repo.get_task(tid, cid1, "t1") is None
    assert repo.get_checkpoint(tid, cid1, "cp-0001-discovering") is None
    assert repo.get_evidence_ref(tid, cid1, "ev-1") is None
    assert repo.get_approval(tid, cid1, "card-1") is None
    assert repo.get_passport(tid, "pass-1") is None
