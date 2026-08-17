from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.conventions import canonical_json_bytes, sha256_hex
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import ExecutionEvidenceMode
from integrations.github.github_adapter import (
    BoundedGitHubAdapter,
    GitHubAction,
    GitHubRequest,
    GitHubTransportResult,
)
from src.orchestrator.idempotency import (
    IdempotencyIntent,
    IdempotencyKeyManager,
    IdempotencyScope,
)
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.state_repository import (
    ChangeRecord,
    IdempotencyReservationRecord,
    IdempotencyReservationStatus,
    TenantRecord,
)
from src.release.briefing_generator import BriefingGenerator
from src.release.receipt_manager import ExternalActionReceipt, ReceiptManager


def _setup_test_repo(
    tid: str = "tenant-default", cid: str = "change-live-01"
) -> InMemorySagaStateRepository:
    repo = InMemorySagaStateRepository()
    now = datetime.now(timezone.utc)
    repo.create_tenant(
        TenantRecord(tenant_id=tid, name="Test Tenant", created_at=now, updated_at=now)
    )
    repo.create_change(
        tid,
        ChangeRecord(
            tenant_id=tid,
            change_id=cid,
            correlation_id="corr-1",
            title="Test Change",
            description="Testing Live Write",
            target_systems=("org/repo",),
            data_classification=DataClassLevel.INTERNAL,
            requested_by="tester",
            requested_at=now,
            state=ChangeState.RECEIVED,
            state_updated_at=now,
            created_at=now,
            updated_at=now,
        ),
    )
    return repo


class MockGitHubTransport:
    def __init__(self, outcomes: dict[GitHubAction, GitHubTransportResult] | None = None):
        self.outcomes = outcomes or {}
        self.call_count = 0
        self.last_call: dict[str, Any] = {}

    def execute(
        self,
        token: str,
        action: GitHubAction,
        repository: str,
        branch: str | None,
        commit_message: str | None,
        pr_title: str | None,
        pr_body: str | None,
        files: dict[str, str],
    ) -> GitHubTransportResult:
        self.call_count += 1
        self.last_call = {
            "token": token,
            "action": action,
            "repository": repository,
            "branch": branch,
            "commit_message": commit_message,
            "pr_title": pr_title,
            "pr_body": pr_body,
            "files": files,
        }
        if action in self.outcomes:
            return self.outcomes[action]
        if action == GitHubAction.CREATE_DRAFT_PR:
            return GitHubTransportResult(
                success=True, result_url=f"https://github.com/{repository}/pull/42"
            )
        elif action == GitHubAction.CREATE_COMMIT:
            return GitHubTransportResult(
                success=True, commit_sha="e0435f0962325e839e557b44784a0d9b9777174e"
            )
        elif action == GitHubAction.CREATE_BRANCH:
            return GitHubTransportResult(
                success=True, result_url=f"https://github.com/{repository}/tree/{branch}"
            )
        return GitHubTransportResult(success=False, error_message="Unknown action")


def test_adapter_allowed_actions():
    adapter = BoundedGitHubAdapter()
    req = GitHubRequest(
        request_id="1", action=GitHubAction.CREATE_BRANCH, repository="org/repo", branch="feature-x"
    )
    res = adapter.execute(req)
    assert res.success
    assert res.evidence_mode == ExecutionEvidenceMode.FIXTURE
    assert res.result_url is None


def test_adapter_forbidden_actions():
    adapter = BoundedGitHubAdapter()
    with pytest.raises(ValueError, match="FORBIDDEN"):
        adapter._check_forbidden("merge")
    with pytest.raises(ValueError, match="FORBIDDEN"):
        adapter._check_forbidden("deploy")
    with pytest.raises(ValueError, match="FORBIDDEN"):
        adapter._check_forbidden("force_push")
    with pytest.raises(ValueError, match="FORBIDDEN"):
        adapter._check_forbidden("delete_repo")
    with pytest.raises(ValueError, match="FORBIDDEN"):
        adapter._check_forbidden("update_protected_branch")
    with pytest.raises(ValueError, match="FORBIDDEN"):
        adapter._check_forbidden("access_secrets")


def test_dry_run():
    adapter = BoundedGitHubAdapter()
    req = GitHubRequest(
        request_id="1", action=GitHubAction.CREATE_DRAFT_PR, repository="org/repo", branch="feat-1"
    )
    artifact = adapter.dry_run(req)

    assert artifact.evidence_mode == ExecutionEvidenceMode.FIXTURE
    assert artifact.credentials_redacted


def test_idempotency():
    adapter = BoundedGitHubAdapter()
    req1 = GitHubRequest(
        request_id="1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        idempotency_key="k1",
    )
    res1 = adapter.execute(req1)

    req2 = GitHubRequest(
        request_id="2",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        idempotency_key="k1",
    )
    res2 = adapter.execute(req2)

    assert res1.success
    assert res2.success
    assert res1.result_url == res2.result_url


def test_briefing_generator():
    generator = BriefingGenerator()
    briefing1 = generator.generate_briefing("c1", "plan", ["sys1"], autonomy_class="AUTO_EXECUTE")
    assert not briefing1.approval_required

    briefing2 = generator.generate_briefing(
        "c1", "plan", ["sys1"], autonomy_class="HUMAN_AUTHORITY_REQUIRED"
    )
    assert briefing2.approval_required


def test_receipt_manager():
    manager = ReceiptManager()
    adapter = BoundedGitHubAdapter()
    req = GitHubRequest(
        request_id="1", action=GitHubAction.CREATE_BRANCH, repository="org/repo", branch="feat"
    )
    res = adapter.execute(req)

    receipt = manager.create_receipt("c1", res, req)
    assert not receipt.contains_credentials

    errors = manager.validate_receipt(receipt)
    assert not errors

    bad_receipt = ExternalActionReceipt(
        receipt_id="r1",
        change_id="c1",
        action="CREATE_BRANCH",
        target_repository="org/repo",
        evidence_mode=ExecutionEvidenceMode.FIXTURE,
        created_at="now",
        contains_credentials=True,
    )
    assert manager.validate_receipt(bad_receipt)


# --- Mandatory Negative & Boundary Tests ---


def test_token_present_without_live_transport_cannot_return_live_write_success():
    """1. Token present + no actual live transport/execution cannot return successful LIVE_WRITE."""
    adapter = BoundedGitHubAdapter(token="ghp_dummytoken12345", transport=None)
    req = GitHubRequest(
        request_id="req-live-no-transport",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/demo-repo",
        branch="feature/test-branch",
        pr_title="Add new schema",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
    )
    res = adapter.execute(req)
    assert not res.success
    assert res.evidence_mode == ExecutionEvidenceMode.LIVE_WRITE
    assert res.result_url is None
    assert res.commit_sha is None
    assert "transport unavailable" in (res.error_message or "").lower()


def test_token_presence_does_not_change_fixture_request_into_live_write():
    """2. Token presence cannot change a FIXTURE request into LIVE_WRITE."""
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(token="ghp_dummytoken12345", transport=transport)
    req = GitHubRequest(
        request_id="req-fixture",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/demo-repo",
        branch="feature/test-branch",
        pr_title="Fixture draft PR",
        evidence_mode=ExecutionEvidenceMode.FIXTURE,
    )
    res = adapter.execute(req)
    assert res.success
    assert res.evidence_mode == ExecutionEvidenceMode.FIXTURE
    assert transport.call_count == 0  # Zero external mutation


def test_fixture_execution_does_not_manufacture_real_pr_or_real_sha():
    """3. FIXTURE execution cannot manufacture a real PR URL or real commit SHA."""
    adapter = BoundedGitHubAdapter()
    req_commit = GitHubRequest(
        request_id="req-c",
        action=GitHubAction.CREATE_COMMIT,
        repository="org/repo",
        commit_message="Fix migration",
        files={"db/schema.sql": "-- content"},
        evidence_mode=ExecutionEvidenceMode.FIXTURE,
    )
    res_commit = adapter.execute(req_commit)
    assert res_commit.commit_sha is None
    assert res_commit.result_url is None
    assert res_commit.evidence_mode == ExecutionEvidenceMode.FIXTURE

    manager = ReceiptManager()
    receipt = manager.create_receipt("c1", res_commit, req_commit)
    assert receipt.evidence_mode == ExecutionEvidenceMode.FIXTURE

    # Passing a non-hex fixture commit SHA in a LIVE_WRITE receipt must fail validation
    fake_live_receipt = ExternalActionReceipt(
        receipt_id="r-fake",
        change_id="c1",
        action=GitHubAction.CREATE_COMMIT.value,
        target_repository="org/repo",
        commit_sha="fixture-sha",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        response_metadata={"success": "True"},
        created_at="now",
    )
    errors = manager.validate_receipt(fake_live_receipt)
    assert any("real commit SHA" in err for err in errors)


def test_live_write_without_credentials_or_target_fails_closed():
    """4. LIVE_WRITE requested without required credential/target/transport fails closed."""
    transport = MockGitHubTransport()
    adapter_no_token = BoundedGitHubAdapter(token=None, transport=transport)
    req = GitHubRequest(
        request_id="req-no-token",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-x",
        pr_title="PR title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
    )
    res = adapter_no_token.execute(req)
    assert not res.success
    assert "Missing GitHub credentials" in (res.error_message or "")
    assert transport.call_count == 0

    adapter = BoundedGitHubAdapter(token="ghp_token", transport=transport)
    req_bad_repo = GitHubRequest(
        request_id="req-bad-repo",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="invalid_repo_without_owner",
        branch="feat-x",
        pr_title="PR title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
    )
    res_bad_repo = adapter.execute(req_bad_repo)
    assert not res_bad_repo.success
    assert "Invalid repository format" in (res_bad_repo.error_message or "")

    req_protected_branch = GitHubRequest(
        request_id="req-protected-branch",
        action=GitHubAction.CREATE_BRANCH,
        repository="org/repo",
        branch="main",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
    )
    res_prot = adapter.execute(req_protected_branch)
    assert not res_prot.success
    assert "protected branch" in (res_prot.error_message or "").lower()


def test_failed_github_api_response_cannot_produce_live_write_evidence():
    """5. A failed GitHub API response cannot produce successful LIVE_WRITE evidence."""
    transport = MockGitHubTransport(
        outcomes={
            GitHubAction.CREATE_DRAFT_PR: GitHubTransportResult(
                success=False,
                error_message="HTTP 404 Not Found: Repository does not exist",
                raw_status_code=404,
            )
        }
    )
    adapter = BoundedGitHubAdapter(token="ghp_validtoken", transport=transport)
    req = GitHubRequest(
        request_id="req-fail-api",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/nonexistent",
        branch="feat-1",
        pr_title="PR title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
    )
    res = adapter.execute(req)
    assert not res.success
    assert res.result_url is None
    assert "404" in (res.error_message or "")


def test_malformed_live_response_cannot_produce_live_write_receipt():
    """6. Malformed/incomplete live response cannot produce a LIVE_WRITE receipt."""
    transport = MockGitHubTransport(
        outcomes={
            GitHubAction.CREATE_DRAFT_PR: GitHubTransportResult(
                success=True, result_url="malformed_url"
            )
        }
    )
    adapter = BoundedGitHubAdapter(token="ghp_validtoken", transport=transport)
    req = GitHubRequest(
        request_id="req-malformed",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-1",
        pr_title="PR title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
    )
    res = adapter.execute(req)
    assert not res.success
    assert "missing valid real PR URL" in (res.error_message or "")

    manager = ReceiptManager()
    receipt = manager.create_receipt("c1", res, req)
    errors = manager.validate_receipt(receipt)
    assert errors
    assert any("failed response" in err or "PR URL" in err for err in errors)


def test_forbidden_actions_remain_blocked():
    """7. Forbidden actions remain blocked."""
    adapter = BoundedGitHubAdapter(token="ghp_test", transport=MockGitHubTransport())
    for forbidden in ["merge", "deploy", "force_push", "delete_repo", "access_secrets"]:
        with pytest.raises(ValueError, match="FORBIDDEN"):
            adapter._check_forbidden(forbidden)


def test_replay_of_completed_live_intent_does_not_issue_second_mutation():
    """8. Replay of the same completed live intent cannot issue a second external write."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-live-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-live-1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-idemp",
        pr_title="Idempotent Draft PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-intent-key-100",
        tenant_id="tenant-default",
        change_id="change-live-01",
    )
    res1 = adapter.execute(req)
    assert res1.success
    assert res1.result_url == "https://github.com/org/repo/pull/42"
    assert transport.call_count == 1

    # Replay with same intent
    res2 = adapter.execute(req)
    assert res2.success
    assert res2.result_url == res1.result_url
    assert transport.call_count == 1  # Transport was NOT called again


def test_live_idempotency_survives_process_restart_with_durable_state_repository():
    """9. Live idempotency must survive process restart grounded in state repository."""
    durable_repo = _setup_test_repo(tid="tenant-default", cid="change-restart-01")
    transport = MockGitHubTransport()

    # Process 1
    adapter_proc1 = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=durable_repo
    )
    req = GitHubRequest(
        request_id="req-restart-test",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-restart",
        pr_title="Draft PR before restart",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-intent-restart-200",
        tenant_id="tenant-default",
        change_id="change-restart-01",
    )
    res1 = adapter_proc1.execute(req)
    assert res1.success
    assert transport.call_count == 1

    # Process 2 (simulating fresh process restart: new instance with empty dicts)
    adapter_proc2 = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=durable_repo
    )
    assert len(adapter_proc2._created_prs) == 0

    res2 = adapter_proc2.execute(req)
    assert res2.success
    assert res2.result_url == res1.result_url
    assert transport.call_count == 1


def test_credentials_never_appear_in_models_receipts_or_error_messages():
    """10. Credentials never appear in models, receipts, logs, or error text."""
    secret_token = "ghp_SECRETTOKENXYZ9876543210"
    transport = MockGitHubTransport(
        outcomes={
            GitHubAction.CREATE_DRAFT_PR: GitHubTransportResult(
                success=False,
                error_message=f"Failed auth for user with token {secret_token}",
                raw_status_code=401,
            )
        }
    )
    adapter = BoundedGitHubAdapter(token=secret_token, transport=transport)
    req = GitHubRequest(
        request_id="req-sec",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-sec",
        pr_title="PR title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
    )
    res = adapter.execute(req)
    assert not res.success
    assert secret_token not in (res.error_message or "")
    assert secret_token not in res.model_dump_json()

    manager = ReceiptManager()
    receipt = manager.create_receipt("c1", res, req)
    receipt_json = receipt.model_dump_json()
    assert secret_token not in receipt_json
    assert not receipt.contains_credentials


# --- Hard Blockers & Fixture Identity Tests ---


def test_in_progress_reservation_causes_zero_transport_calls():
    """1. Pre-existing active IN_PROGRESS reservation causes ZERO transport calls."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-concurrent-01")
    transport = MockGitHubTransport()

    # Pre-reserve the intent via canonical P-10 IdempotencyKeyManager to simulate active Worker 1
    action_type = f"{GitHubAction.CREATE_DRAFT_PR.value}:pr-concurrent-100"
    payload_dict = {
        "action": GitHubAction.CREATE_DRAFT_PR.value,
        "repository": "org/repo",
        "branch": "feat-conc",
        "pr_title": "Concurrent PR",
        "pr_body": "Body text",
    }
    payload_digest = sha256_hex(canonical_json_bytes(payload_dict))
    intent1 = IdempotencyIntent(
        tenant_id="tenant-default",
        change_id="change-concurrent-01",
        scope=IdempotencyScope.EXTERNAL_WRITE,
        action_type=action_type,
        target_system="org/repo",
        caller_revision="1.0.0",
        payload_digest=payload_digest,
    )
    outcome1 = IdempotencyKeyManager.reserve_intent(repo, intent1)
    assert outcome1.status.value == "GRANTED"

    # Worker 2 attempts same intent while Worker 1 is still in progress
    adapter_worker2 = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )
    req2 = GitHubRequest(
        request_id="req-worker-2",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-conc",
        pr_title="Concurrent PR",
        pr_body="Body text",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-concurrent-100",
        tenant_id="tenant-default",
        change_id="change-concurrent-01",
    )
    res2 = adapter_worker2.execute(req2)
    assert not res2.success
    assert "already in progress" in (res2.error_message or "").lower()
    assert transport.call_count == 0  # Zero transport call made by worker 2!

    # Verify Worker 2 did NOT release Worker 1's reservation
    idem_key = IdempotencyKeyManager.compute_canonical_idempotency_key(intent1)
    doc_id = IdempotencyKeyManager.compute_reservation_doc_id(idem_key)
    res_record = repo.get_idempotency_reservation("tenant-default", "change-concurrent-01", doc_id)
    assert res_record is not None
    assert res_record.status == IdempotencyReservationStatus.RESERVED


def test_only_granted_reservation_may_mutate():
    """2. Only the reservation owner that receives GRANTED may mutate."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-grant-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-grant-1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-grant",
        pr_title="Grant PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-grant-key",
        tenant_id="tenant-default",
        change_id="change-grant-01",
    )
    # GRANTED -> executes transport
    res1 = adapter.execute(req)
    assert res1.success
    assert transport.call_count == 1

    # EXACT_REPLAY -> does not execute transport
    res2 = adapter.execute(req)
    assert res2.success
    assert transport.call_count == 1


def test_same_semantic_draft_pr_intent_with_different_request_id_deduplicates():
    """3. Same semantic Draft PR intent with a different request_id returns EXACT_REPLAY."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-sem-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )

    req1 = GitHubRequest(
        request_id="req-envelope-1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-semantic",
        pr_title="Semantic PR",
        pr_body="Detailed body",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-sem-key-42",
        tenant_id="tenant-default",
        change_id="change-sem-01",
    )
    res1 = adapter.execute(req1)
    assert res1.success
    assert transport.call_count == 1

    # Retry with a totally different request_id (envelope) but identical semantic intent
    req2 = GitHubRequest(
        request_id="req-envelope-2-retry",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-semantic",
        pr_title="Semantic PR",
        pr_body="Detailed body",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-sem-key-42",
        tenant_id="tenant-default",
        change_id="change-sem-01",
    )
    res2 = adapter.execute(req2)
    assert res2.success
    assert res2.result_url == res1.result_url
    assert transport.call_count == 1  # Deduplicated!


def test_same_idempotency_intent_with_materially_different_pr_body_fails_closed_as_conflict():
    """4. Same idempotency intent with materially different PR body fails closed as conflict."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-conflict-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )

    req1 = GitHubRequest(
        request_id="req-conf-1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-conf",
        pr_title="PR Title",
        pr_body="Original PR body",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-conf-key",
        tenant_id="tenant-default",
        change_id="change-conflict-01",
    )
    res1 = adapter.execute(req1)
    assert res1.success
    assert transport.call_count == 1

    # Request with same key but materially DIFFERENT pr_body
    req2 = GitHubRequest(
        request_id="req-conf-2",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-conf",
        pr_title="PR Title",
        pr_body="CHANGED AND CONFLICTING PR body",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-conf-key",
        tenant_id="tenant-default",
        change_id="change-conflict-01",
    )
    res2 = adapter.execute(req2)
    assert not res2.success
    assert (
        "conflict" in (res2.error_message or "").lower()
        or "failed" in (res2.error_message or "").lower()
    )
    assert transport.call_count == 1  # Zero second mutation!


def test_two_distinct_intended_external_writes_do_not_collide():
    """5. Two distinct intended external writes can be represented distinctly without colliding."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-distinct-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )

    req_a = GitHubRequest(
        request_id="req-alpha",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-alpha",
        pr_title="PR Alpha",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-intent-alpha",
        tenant_id="tenant-default",
        change_id="change-distinct-01",
    )
    req_b = GitHubRequest(
        request_id="req-beta",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-beta",
        pr_title="PR Beta",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-intent-beta",
        tenant_id="tenant-default",
        change_id="change-distinct-01",
    )

    res_a = adapter.execute(req_a)
    res_b = adapter.execute(req_b)

    assert res_a.success
    assert res_b.success
    assert transport.call_count == 2


def test_exact_replay_with_malformed_cached_pr_url_fails_closed():
    """6. EXACT_REPLAY with malformed/missing cached PR URL fails closed."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-badcache-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )

    action_type = f"{GitHubAction.CREATE_DRAFT_PR.value}:pr-badcache-key"
    payload_dict = {
        "action": GitHubAction.CREATE_DRAFT_PR.value,
        "repository": "org/repo",
        "branch": "feat-badcache",
        "pr_title": "Bad Cache PR",
        "pr_body": "",
    }
    payload_digest = sha256_hex(canonical_json_bytes(payload_dict))
    intent = IdempotencyIntent(
        tenant_id="tenant-default",
        change_id="change-badcache-01",
        scope=IdempotencyScope.EXTERNAL_WRITE,
        action_type=action_type,
        target_system="org/repo",
        caller_revision="1.0.0",
        payload_digest=payload_digest,
    )
    idem_key = IdempotencyKeyManager.compute_canonical_idempotency_key(intent)
    doc_id = IdempotencyKeyManager.compute_reservation_doc_id(idem_key)
    now = datetime.now(timezone.utc)

    # Insert a committed reservation with a corrupted / non-URL cached receipt
    repo.create_idempotency_reservation(
        "tenant-default",
        "change-badcache-01",
        IdempotencyReservationRecord(
            tenant_id="tenant-default",
            change_id="change-badcache-01",
            reservation_id=doc_id,
            idempotency_key=idem_key,
            scope=IdempotencyScope.EXTERNAL_WRITE.value,
            action_type=action_type,
            target_system="org/repo",
            caller_revision="1.0.0",
            payload_digest=payload_digest,
            status=IdempotencyReservationStatus.COMMITTED,
            reserved_at=now,
            expires_at=now + timedelta(minutes=15),
            result_digest="a" * 64,
            receipt_status="malformed_not_a_pr_url",
        ),
    )

    req = GitHubRequest(
        request_id="req-badcache-test",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-badcache",
        pr_title="Bad Cache PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-badcache-key",
        tenant_id="tenant-default",
        change_id="change-badcache-01",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "invalid real pr url" in (res.error_message or "").lower()
    assert transport.call_count == 0  # Does NOT issue external write to fix corrupt cache!


def test_exact_replay_with_malformed_cached_commit_sha_fails_closed():
    """7. EXACT_REPLAY with malformed/missing cached commit SHA fails closed."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-badsha-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )

    action_type = f"{GitHubAction.CREATE_COMMIT.value}:commit-badsha-key"
    payload_dict = {
        "action": GitHubAction.CREATE_COMMIT.value,
        "repository": "org/repo",
        "branch": "feat-badsha",
        "commit_message": "Commit msg",
        "files": sorted({"a.py": "1"}.items()),
    }
    payload_digest = sha256_hex(canonical_json_bytes(payload_dict))
    intent = IdempotencyIntent(
        tenant_id="tenant-default",
        change_id="change-badsha-01",
        scope=IdempotencyScope.EXTERNAL_WRITE,
        action_type=action_type,
        target_system="org/repo",
        caller_revision="1.0.0",
        payload_digest=payload_digest,
    )
    idem_key = IdempotencyKeyManager.compute_canonical_idempotency_key(intent)
    doc_id = IdempotencyKeyManager.compute_reservation_doc_id(idem_key)
    now = datetime.now(timezone.utc)

    # Insert committed reservation with fake "fixture-sha" as cached receipt
    repo.create_idempotency_reservation(
        "tenant-default",
        "change-badsha-01",
        IdempotencyReservationRecord(
            tenant_id="tenant-default",
            change_id="change-badsha-01",
            reservation_id=doc_id,
            idempotency_key=idem_key,
            scope=IdempotencyScope.EXTERNAL_WRITE.value,
            action_type=action_type,
            target_system="org/repo",
            caller_revision="1.0.0",
            payload_digest=payload_digest,
            status=IdempotencyReservationStatus.COMMITTED,
            reserved_at=now,
            expires_at=now + timedelta(minutes=15),
            result_digest="a" * 64,
            receipt_status="fixture-sha",  # Rejected!
        ),
    )

    req = GitHubRequest(
        request_id="req-badsha-test",
        action=GitHubAction.CREATE_COMMIT,
        repository="org/repo",
        branch="feat-badsha",
        commit_message="Commit msg",
        files={"a.py": "1"},
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="commit-badsha-key",
        tenant_id="tenant-default",
        change_id="change-badsha-01",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "invalid commit sha" in (res.error_message or "").lower()
    assert transport.call_count == 0


def test_branch_replay_does_not_synthesize_predicted_github_url():
    """8. Branch replay does not synthesize a predicted GitHub URL."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-branch-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_testtoken", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-branch-1",
        action=GitHubAction.CREATE_BRANCH,
        repository="org/repo",
        branch="feat-mybranch",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="branch-key-01",
        tenant_id="tenant-default",
        change_id="change-branch-01",
    )
    res1 = adapter.execute(req)
    assert res1.success
    assert res1.result_url == "https://github.com/org/repo/tree/feat-mybranch"
    assert transport.call_count == 1

    # Replay returns exact persisted real URL
    res2 = adapter.execute(req)
    assert res2.success
    assert res2.result_url == "https://github.com/org/repo/tree/feat-mybranch"
    assert transport.call_count == 1


def test_fixture_draft_pr_does_not_return_github_pull_url():
    """9. FIXTURE Draft PR does not return a github.com/.../pull/<number> identifier."""
    adapter = BoundedGitHubAdapter()
    req = GitHubRequest(
        request_id="req-f-pr",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-fixture",
        pr_title="Fixture PR",
        evidence_mode=ExecutionEvidenceMode.FIXTURE,
    )
    res = adapter.execute(req)
    assert res.success
    assert res.result_url is None
    assert res.commit_sha is None
    assert res.evidence_mode == ExecutionEvidenceMode.FIXTURE


def test_fixture_commit_does_not_return_provider_commit_sha():
    """10. FIXTURE commit does not return a provider-looking real commit identifier."""
    adapter = BoundedGitHubAdapter()
    req = GitHubRequest(
        request_id="req-f-commit",
        action=GitHubAction.CREATE_COMMIT,
        repository="org/repo",
        commit_message="Fix things",
        files={"code.py": "x = 1"},
        evidence_mode=ExecutionEvidenceMode.FIXTURE,
    )
    res = adapter.execute(req)
    assert res.success
    assert res.commit_sha is None
    assert res.result_url is None
    assert res.evidence_mode == ExecutionEvidenceMode.FIXTURE
