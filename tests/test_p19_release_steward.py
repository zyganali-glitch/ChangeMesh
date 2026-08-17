from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import ExecutionEvidenceMode
from integrations.github.github_adapter import (
    BoundedGitHubAdapter,
    GitHubAction,
    GitHubRequest,
    GitHubTransportResult,
)
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.state_repository import ChangeRecord, TenantRecord
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
    assert res_commit.commit_sha == "fixture-sha"
    assert res_commit.evidence_mode == ExecutionEvidenceMode.FIXTURE

    manager = ReceiptManager()
    receipt = manager.create_receipt("c1", res_commit, req_commit)
    assert receipt.evidence_mode == ExecutionEvidenceMode.FIXTURE

    # If someone tries to pass a fixture commit SHA in a LIVE_WRITE receipt, it must fail validation
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
    # Missing token
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

    # Invalid repository target
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

    # Protected branch creation attempt
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
    # Transport claims success but returns invalid PR URL format
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
    assert len(adapter_proc2._created_prs) == 0  # In-memory dict is empty

    res2 = adapter_proc2.execute(req)
    assert res2.success
    assert res2.result_url == res1.result_url
    assert transport.call_count == 1  # Still exactly 1 transport call! No duplicate mutation!


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
