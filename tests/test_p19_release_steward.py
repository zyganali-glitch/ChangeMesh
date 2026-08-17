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
    GitHubReconciliationQuery,
    GitHubReconciliationResult,
    GitHubRequest,
    GitHubTransportResult,
    ReconciliationStatus,
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


class MockStoredEntity:
    def __init__(
        self,
        action: GitHubAction,
        repository: str,
        branch: str | None,
        commit_message: str | None = None,
        pr_title: str | None = None,
        pr_body: str | None = None,
        files: dict[str, str] | None = None,
        result_url: str | None = None,
        commit_sha: str | None = None,
    ):
        self.action = action
        self.repository = repository
        self.branch = branch
        self.commit_message = commit_message
        self.pr_title = pr_title
        self.pr_body = pr_body
        self.files = files or {}
        self.result_url = result_url
        self.commit_sha = commit_sha


class MockTransportLackingReconciliation:
    def __init__(self):
        self.call_count = 0

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
        return GitHubTransportResult(success=True)


class MockTransportNonCallableReconciliation:
    def __init__(self):
        self.call_count = 0
        self.find_existing = "non-callable-string"

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
        return GitHubTransportResult(success=True)


class MockGitHubTransport:
    def __init__(
        self,
        outcomes: dict[GitHubAction, GitHubTransportResult] | None = None,
        existing_items: dict[Any, Any] | list[MockStoredEntity] | None = None,
        find_outcome: GitHubReconciliationResult | None = None,
        find_raises: Exception | None = None,
        find_status: ReconciliationStatus | None = None,
        find_error: str | None = None,
    ):
        self.outcomes = outcomes or {}
        self.stored_entities: list[MockStoredEntity] = []
        if isinstance(existing_items, list):
            self.stored_entities.extend(existing_items)
        elif isinstance(existing_items, dict):
            for k, v in existing_items.items():
                if isinstance(v, (GitHubTransportResult, GitHubReconciliationResult)):
                    action = k if isinstance(k, GitHubAction) else GitHubAction.CREATE_DRAFT_PR
                    self.stored_entities.append(
                        MockStoredEntity(
                            action=action,
                            repository="org/repo",
                            branch=None,
                            result_url=v.result_url,
                            commit_sha=v.commit_sha,
                        )
                    )
        self.find_outcome = find_outcome
        self.find_raises = find_raises
        self.find_status = find_status
        self.find_error = find_error
        self.call_count = 0
        self.find_count = 0
        self.last_call: dict[str, Any] = {}
        self.last_find_query: GitHubReconciliationQuery | None = None

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
            res = self.outcomes[action]
            if res.success:
                self.stored_entities.append(
                    MockStoredEntity(
                        action=action,
                        repository=repository,
                        branch=branch,
                        commit_message=commit_message,
                        pr_title=pr_title,
                        pr_body=pr_body,
                        files=files,
                        result_url=res.result_url,
                        commit_sha=res.commit_sha,
                    )
                )
            return res

        if action == GitHubAction.CREATE_DRAFT_PR:
            res = GitHubTransportResult(
                success=True, result_url=f"https://github.com/{repository}/pull/42"
            )
            self.stored_entities.append(
                MockStoredEntity(
                    action=action,
                    repository=repository,
                    branch=branch,
                    pr_title=pr_title,
                    pr_body=pr_body,
                    result_url=res.result_url,
                )
            )
            return res
        elif action == GitHubAction.CREATE_COMMIT:
            res = GitHubTransportResult(
                success=True, commit_sha="e0435f0962325e839e557b44784a0d9b9777174e"
            )
            self.stored_entities.append(
                MockStoredEntity(
                    action=action,
                    repository=repository,
                    branch=branch,
                    commit_message=commit_message,
                    files=files,
                    commit_sha=res.commit_sha,
                )
            )
            return res
        elif action == GitHubAction.CREATE_BRANCH:
            res = GitHubTransportResult(
                success=True, result_url=f"https://github.com/{repository}/tree/{branch}"
            )
            self.stored_entities.append(
                MockStoredEntity(
                    action=action,
                    repository=repository,
                    branch=branch,
                    result_url=res.result_url,
                )
            )
            return res
        return GitHubTransportResult(success=False, error_message="Unknown action")

    def find_existing(
        self,
        token: str,
        query: GitHubReconciliationQuery,
    ) -> GitHubReconciliationResult:
        self.find_count += 1
        self.last_find_query = query

        if self.find_raises is not None:
            raise self.find_raises
        if self.find_status is not None:
            return GitHubReconciliationResult(
                status=self.find_status,
                error_message=self.find_error,
            )
        if self.find_outcome is not None:
            return self.find_outcome

        for entity in self.stored_entities:
            if entity.action != query.action or entity.repository != query.repository:
                continue

            if query.action == GitHubAction.CREATE_DRAFT_PR:
                if entity.branch is not None and entity.branch != query.branch:
                    continue

                matched = False
                if (
                    query.idempotency_key
                    and entity.pr_body
                    and f"key={query.idempotency_key}" in entity.pr_body
                ):
                    matched = True
                elif (
                    query.payload_digest
                    and entity.pr_body
                    and f"digest={query.payload_digest}" in entity.pr_body
                ):
                    matched = True
                elif entity.pr_title == query.pr_title and (
                    entity.pr_body == query.pr_body
                    or (entity.pr_body and (query.pr_body or "") in entity.pr_body)
                ):
                    matched = True
                elif entity.result_url and (
                    entity.pr_title is None or entity.pr_title == query.pr_title
                ):
                    matched = True

                if matched:
                    return GitHubReconciliationResult(
                        status=ReconciliationStatus.FOUND,
                        result_url=entity.result_url,
                        matched_idempotency_key=query.idempotency_key,
                        matched_payload_digest=query.payload_digest,
                    )

            elif query.action == GitHubAction.CREATE_COMMIT:
                if (
                    (entity.branch is None or entity.branch == query.branch)
                    and (
                        entity.commit_message is None
                        or entity.commit_message == query.commit_message
                    )
                    and (not entity.files or entity.files == query.files)
                ):
                    return GitHubReconciliationResult(
                        status=ReconciliationStatus.FOUND,
                        commit_sha=entity.commit_sha,
                    )

            elif query.action == GitHubAction.CREATE_BRANCH:
                if entity.branch is None or entity.branch == query.branch:
                    return GitHubReconciliationResult(
                        status=ReconciliationStatus.FOUND,
                        result_url=entity.result_url,
                    )

        return GitHubReconciliationResult(status=ReconciliationStatus.NOT_FOUND)


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
    repo = _setup_test_repo(tid="tenant-default", cid="change-fail-api")
    transport = MockGitHubTransport(
        outcomes={
            GitHubAction.CREATE_DRAFT_PR: GitHubTransportResult(
                success=False,
                error_message="HTTP 404 Not Found: Repository does not exist",
                raw_status_code=404,
            )
        }
    )
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken", transport=transport, state_repository=repo
    )
    req = GitHubRequest(
        request_id="req-fail-api",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/nonexistent",
        branch="feat-1",
        pr_title="PR title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        tenant_id="tenant-default",
        change_id="change-fail-api",
    )
    res = adapter.execute(req)
    assert not res.success
    assert res.result_url is None
    assert "404" in (res.error_message or "")


def test_malformed_live_response_cannot_produce_live_write_receipt():
    """6. Malformed/incomplete live response cannot produce a LIVE_WRITE receipt."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-malformed")
    transport = MockGitHubTransport(
        outcomes={
            GitHubAction.CREATE_DRAFT_PR: GitHubTransportResult(
                success=True, result_url="malformed_url"
            )
        }
    )
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken", transport=transport, state_repository=repo
    )
    req = GitHubRequest(
        request_id="req-malformed",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-1",
        pr_title="PR title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        tenant_id="tenant-default",
        change_id="change-malformed",
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
    repo = _setup_test_repo(tid="tenant-default", cid="change-sec")
    secret_token = "ghp_" + "SECRETTOKENXYZ9876543210"
    transport = MockGitHubTransport(
        outcomes={
            GitHubAction.CREATE_DRAFT_PR: GitHubTransportResult(
                success=False,
                error_message=f"Failed auth for user with token {secret_token}",
                raw_status_code=401,
            )
        }
    )
    adapter = BoundedGitHubAdapter(token=secret_token, transport=transport, state_repository=repo)
    req = GitHubRequest(
        request_id="req-sec",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-sec",
        pr_title="PR title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        tenant_id="tenant-default",
        change_id="change-sec",
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


# --- P-19.01 Hard Blockers 1, 2, 3 Focused Safety Regression Tests ---


def test_live_write_with_token_and_transport_but_no_state_repository_fails_closed():
    """1. LIVE_WRITE with token, transport, state_repository=None fails closed."""
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=None
    )
    req = GitHubRequest(
        request_id="req-live-no-repo",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-x",
        pr_title="PR Title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
    )
    res = adapter.execute(req)
    assert not res.success
    assert res.evidence_mode == ExecutionEvidenceMode.LIVE_WRITE
    assert "Durable SagaStateRepository is required" in (res.error_message or "")
    assert transport.call_count == 0


def test_live_write_cannot_bypass_durable_idempotency_without_tenant_or_change_id():
    """2. LIVE_WRITE cannot bypass durable idempotency binding."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-live-01")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123",
        transport=transport,
        state_repository=repo,
        tenant_id="",
        change_id="",
    )
    req = GitHubRequest(
        request_id="req-live-no-binding",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-x",
        pr_title="PR Title",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        tenant_id=None,
        change_id=None,
    )
    res = adapter.execute(req)
    assert not res.success
    assert "Valid tenant_id and change_id are required" in (res.error_message or "")
    assert transport.call_count == 0


def test_fixture_and_simulation_usable_without_state_repository_and_zero_network():
    """3. FIXTURE/SIMULATION remain usable without state repo and perform zero network mutation."""
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=None
    )
    for mode in (ExecutionEvidenceMode.FIXTURE, ExecutionEvidenceMode.SIMULATION):
        req = GitHubRequest(
            request_id=f"req-{mode.value}",
            action=GitHubAction.CREATE_DRAFT_PR,
            repository="org/repo",
            branch="feat-safe",
            pr_title="Safe PR",
            evidence_mode=mode,
        )
        res = adapter.execute(req)
        assert res.success
        assert res.evidence_mode == mode
        assert res.result_url is None
        assert res.commit_sha is None
        assert transport.call_count == 0


def test_create_commit_on_protected_branch_main_fails_closed():
    """4. CREATE_COMMIT(branch='main') fails closed and performs zero transport calls."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-main-commit")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )
    req = GitHubRequest(
        request_id="req-main-commit",
        action=GitHubAction.CREATE_COMMIT,
        repository="org/repo",
        branch="main",
        commit_message="Direct commit to main",
        files={"src/app.py": "x = 1"},
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        tenant_id="tenant-default",
        change_id="change-main-commit",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "Commit on protected branch 'main' is forbidden" in (res.error_message or "")
    assert transport.call_count == 0


def test_create_commit_on_protected_branch_master_fails_closed():
    """5. CREATE_COMMIT(branch='master') fails closed."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-master-commit")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )
    for protected in ("master", "prod", "production", "release"):
        req = GitHubRequest(
            request_id=f"req-{protected}-commit",
            action=GitHubAction.CREATE_COMMIT,
            repository="org/repo",
            branch=protected,
            commit_message=f"Direct commit to {protected}",
            files={"src/app.py": "x = 1"},
            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
            tenant_id="tenant-default",
            change_id="change-master-commit",
        )
        res = adapter.execute(req)
        assert not res.success
        assert f"Commit on protected branch '{protected}' is forbidden" in (res.error_message or "")
        assert transport.call_count == 0


def test_live_write_create_commit_with_none_branch_fails_closed():
    """6. LIVE_WRITE CREATE_COMMIT(branch=None) fails closed."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-none-branch")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )
    req = GitHubRequest(
        request_id="req-none-branch",
        action=GitHubAction.CREATE_COMMIT,
        repository="org/repo",
        branch=None,
        commit_message="Commit without branch",
        files={"src/app.py": "x = 1"},
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        tenant_id="tenant-default",
        change_id="change-none-branch",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "Branch name must be explicit and non-empty for CREATE_COMMIT" in (
        res.error_message or ""
    )
    assert transport.call_count == 0


def test_create_commit_on_feature_branch_succeeds_via_canonical_path():
    """7. LIVE_WRITE commit to valid feature branch works through reservation path."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-feat-commit")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )
    req = GitHubRequest(
        request_id="req-feat-commit",
        action=GitHubAction.CREATE_COMMIT,
        repository="org/repo",
        branch="feature/safe-branch",
        commit_message="Commit on feature branch",
        files={"src/app.py": "x = 2"},
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="commit-key-feat",
        tenant_id="tenant-default",
        change_id="change-feat-commit",
    )
    res = adapter.execute(req)
    assert res.success
    assert res.commit_sha == "e0435f0962325e839e557b44784a0d9b9777174e"
    assert transport.call_count == 1


class FailingCommitRepoWrapper:
    """Wraps a SagaStateRepository to fail on update_idempotency_reservation when committing."""

    def __init__(self, inner: InMemorySagaStateRepository):
        self._inner = inner

    def get_idempotency_reservation(self, *args, **kwargs):
        return self._inner.get_idempotency_reservation(*args, **kwargs)

    def create_idempotency_reservation(self, *args, **kwargs):
        return self._inner.create_idempotency_reservation(*args, **kwargs)

    def update_idempotency_reservation(self, tid, cid, record, expected_version=None):
        if record.status == IdempotencyReservationStatus.COMMITTED:
            raise RuntimeError("Simulated database failure during durable commit_intent")
        return self._inner.update_idempotency_reservation(
            tid, cid, record, expected_version=expected_version
        )


def test_provider_success_followed_by_durable_commit_failure_holds_reservation():
    """10. Simulate provider success followed by durable commit_intent persistence failure."""
    inner_repo = _setup_test_repo(tid="tenant-default", cid="change-ambig-01")
    failing_repo = FailingCommitRepoWrapper(inner_repo)
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123",
        transport=transport,
        state_repository=failing_repo,  # type: ignore[arg-type]
    )

    req = GitHubRequest(
        request_id="req-ambig-1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-ambig",
        pr_title="Ambiguous PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-ambig-key",
        tenant_id="tenant-default",
        change_id="change-ambig-01",
    )

    res = adapter.execute(req)
    assert not res.success
    assert "External mutation succeeded on provider" in (res.error_message or "")
    assert "durable commit failed" in (res.error_message or "")
    assert "reconciliation required" in (res.error_message or "").lower()
    assert transport.call_count == 1  # Transport DID run

    # Verify that the reservation was NOT released and remains RESERVED
    action_type = f"{GitHubAction.CREATE_DRAFT_PR.value}:pr-ambig-key"
    payload_dict = {
        "action": GitHubAction.CREATE_DRAFT_PR.value,
        "repository": "org/repo",
        "branch": "feat-ambig",
        "pr_title": "Ambiguous PR",
        "pr_body": "",
    }
    payload_digest = sha256_hex(canonical_json_bytes(payload_dict))
    intent = IdempotencyIntent(
        tenant_id="tenant-default",
        change_id="change-ambig-01",
        scope=IdempotencyScope.EXTERNAL_WRITE,
        action_type=action_type,
        target_system="org/repo",
        caller_revision="1.0.0",
        payload_digest=payload_digest,
    )
    idem_key = IdempotencyKeyManager.compute_canonical_idempotency_key(intent)
    doc_id = IdempotencyKeyManager.compute_reservation_doc_id(idem_key)
    res_rec = inner_repo.get_idempotency_reservation("tenant-default", "change-ambig-01", doc_id)
    assert res_rec is not None
    assert res_rec.status == IdempotencyReservationStatus.RESERVED


def test_immediate_retry_after_ambiguous_post_write_failure_does_zero_mutation():
    """11. After ambiguous post-write failure, immediate retry performs zero second mutation."""
    inner_repo = _setup_test_repo(tid="tenant-default", cid="change-ambig-02")
    failing_repo = FailingCommitRepoWrapper(inner_repo)
    transport = MockGitHubTransport()
    adapter1 = BoundedGitHubAdapter(
        token="ghp_validtoken123",
        transport=transport,
        state_repository=failing_repo,  # type: ignore[arg-type]
    )

    req = GitHubRequest(
        request_id="req-ambig-first",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-ambig-2",
        pr_title="Ambiguous PR 2",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-ambig-key-2",
        tenant_id="tenant-default",
        change_id="change-ambig-02",
    )
    res1 = adapter1.execute(req)
    assert not res1.success
    assert transport.call_count == 1

    # Immediate retry with healthy repository
    adapter2 = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=inner_repo
    )
    res2 = adapter2.execute(req)
    assert not res2.success
    assert "already in progress" in (res2.error_message or "").lower()
    assert transport.call_count == 1  # ZERO second mutation call!


def test_successful_reconciliation_reuses_verified_provider_evidence():
    """12 & 13. Successful reconciliation returns and reuses verified real provider evidence."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-reconcile-01")
    # Transport already has the existing PR from a prior external creation
    existing_pr = GitHubTransportResult(
        success=True, result_url="https://github.com/org/repo/pull/777"
    )
    transport = MockGitHubTransport(existing_items={GitHubAction.CREATE_DRAFT_PR: existing_pr})
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-reconcile-test",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-reconcile",
        pr_title="Reconciled PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-reconcile-key",
        tenant_id="tenant-default",
        change_id="change-reconcile-01",
    )
    res = adapter.execute(req)
    assert res.success
    assert res.result_url == "https://github.com/org/repo/pull/777"
    assert transport.call_count == 0  # Zero mutation execute() call!
    assert transport.find_count == 1  # find_existing was called

    # Replay of now-committed state
    res_replay = adapter.execute(req)
    assert res_replay.success
    assert res_replay.result_url == "https://github.com/org/repo/pull/777"
    assert transport.call_count == 0


def test_reconciliation_failure_remains_fail_closed_and_does_not_mutate():
    """14. Reconciliation failure/unknown state remains fail-closed and does not mutate."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-reconcile-fail")
    transport = MockGitHubTransport(
        find_raises=RuntimeError("GitHub API rate limit / 503 error during reconciliation")
    )
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-reconcile-fail",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-rec-fail",
        pr_title="Reconciliation Fail PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-rec-fail-key",
        tenant_id="tenant-default",
        change_id="change-reconcile-fail",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "reconciliation check failed" in (res.error_message or "").lower()
    assert transport.call_count == 0  # Zero mutation execute() call!


def test_live_write_transport_lacking_find_existing_fails_closed_zero_mutation():
    """Matrix 1: LIVE_WRITE transport lacking find_existing fails closed with zero mutation."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-no-find")
    transport = MockTransportLackingReconciliation()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-no-find",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-no-find",
        pr_title="No Find PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-no-find-key",
        tenant_id="tenant-default",
        change_id="change-no-find",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "lacks required reconciliation capability" in (res.error_message or "").lower()
    assert transport.call_count == 0


def test_live_write_transport_non_callable_find_existing_fails_closed_zero_mutation():
    """Matrix 2: Non-callable reconciliation capability fails closed with zero mutation."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-non-callable")
    transport = MockTransportNonCallableReconciliation()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-non-callable",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-non-callable",
        pr_title="Non-Callable PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-non-callable-key",
        tenant_id="tenant-default",
        change_id="change-non-callable",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "lacks required reconciliation capability" in (res.error_message or "").lower()
    assert transport.call_count == 0


def test_live_write_reconciliation_unknown_status_fails_closed_zero_mutation():
    """Matrix 3: Reconciliation UNKNOWN / ERROR status fails closed with zero mutation."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-rec-unknown")
    transport = MockGitHubTransport(find_status=ReconciliationStatus.UNKNOWN)
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-rec-unknown",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-unknown",
        pr_title="Unknown PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-unknown-key",
        tenant_id="tenant-default",
        change_id="change-rec-unknown",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "indeterminate status" in (res.error_message or "").lower()
    assert transport.call_count == 0


def test_live_write_authoritative_not_found_permits_single_mutation():
    """Matrix 5: Authoritative NOT_FOUND permits exactly one new mutation."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-not-found")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-not-found-1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-not-found",
        pr_title="Fresh PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-not-found-key",
        tenant_id="tenant-default",
        change_id="change-not-found",
    )
    res = adapter.execute(req)
    assert res.success
    assert res.result_url == "https://github.com/org/repo/pull/42"
    assert transport.find_count == 1
    assert transport.call_count == 1


def test_live_write_same_branch_different_semantic_identity_is_not_treated_as_found():
    """Matrix 7: Same repo + branch but different Draft PR semantic identity is NOT FOUND."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-diff-ident")
    transport = MockGitHubTransport()

    # Step 1: Create PR Alpha on branch feat-shared
    adapter1 = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )
    req1 = GitHubRequest(
        request_id="req-alpha",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-shared",
        pr_title="PR Alpha Title",
        pr_body="Body Alpha",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-alpha-key",
        tenant_id="tenant-default",
        change_id="change-diff-ident",
    )
    res1 = adapter1.execute(req1)
    assert res1.success
    assert transport.call_count == 1

    # Step 2: Now create a different change/request for PR Beta on same branch feat-shared
    req2 = GitHubRequest(
        request_id="req-beta",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-shared",
        pr_title="PR Beta Different Title",
        pr_body="Body Beta Different",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-beta-key",
        tenant_id="tenant-default",
        change_id="change-diff-ident",
    )
    res2 = adapter1.execute(req2)
    assert res2.success
    # Must NOT have treated PR Alpha as FOUND; must have executed PR Beta mutation
    assert transport.call_count == 2
    assert len(transport.stored_entities) == 2


def test_live_write_different_pr_body_under_same_branch_title_idempotency_detected():
    """Matrix 8: Different PR body under same branch/title/idempotency is conflict."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-body-mod")
    transport = MockGitHubTransport()
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )

    req1 = GitHubRequest(
        request_id="req-body-1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-body-mod",
        pr_title="PR Title",
        pr_body="Body Original",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-body-key-shared",
        tenant_id="tenant-default",
        change_id="change-body-mod",
    )
    res1 = adapter.execute(req1)
    assert res1.success
    assert transport.call_count == 1

    req2 = GitHubRequest(
        request_id="req-body-2",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-body-mod",
        pr_title="PR Title",
        pr_body="Body Mutated Modified",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-body-key-shared",
        tenant_id="tenant-default",
        change_id="change-body-mod",
    )
    res2 = adapter.execute(req2)
    assert not res2.success
    assert "idempotency conflict" in (res2.error_message or "").lower()
    assert transport.call_count == 1  # Zero second mutation call!


def test_live_write_malformed_found_provider_evidence_fails_closed():
    """Matrix 11: Malformed FOUND provider evidence fails closed."""
    repo = _setup_test_repo(tid="tenant-default", cid="change-malformed-found")
    transport = MockGitHubTransport(
        find_outcome=GitHubReconciliationResult(
            status=ReconciliationStatus.FOUND,
            result_url="invalid-not-a-pull-url",
        )
    )
    adapter = BoundedGitHubAdapter(
        token="ghp_validtoken123", transport=transport, state_repository=repo
    )

    req = GitHubRequest(
        request_id="req-malformed-found",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-malformed",
        pr_title="Malformed Found PR",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-malformed-key",
        tenant_id="tenant-default",
        change_id="change-malformed-found",
    )
    res = adapter.execute(req)
    assert not res.success
    assert "missing valid real pr url" in (res.error_message or "").lower()
    assert transport.call_count == 0


def test_lease_expiry_reconciliation_and_single_mutation_end_to_end():
    """Matrix 10: Complete 10-step ambiguous post-write lease expiry and reconciliation test.

    Sequence:
    1. Reserve semantic Draft PR intent
    2. Provider mutation succeeds (call_count == 1)
    3. Durable commit_intent fails
    4. Reservation remains RESERVED
    5. Immediate retry returns IN_PROGRESS (call_count == 1)
    6. Advance lease expiration so expires_at <= now
    7. Fresh worker process re-acquires reservation
    8. Provider reconciliation finds exact created action via marker / semantic identity
    9. Commits durable state from verified provider evidence
    10. transport.call_count remains exactly 1 for the entire scenario!
    """
    inner_repo = _setup_test_repo(tid="tenant-default", cid="change-lease-exp-01")
    failing_repo = FailingCommitRepoWrapper(inner_repo)
    transport = MockGitHubTransport()

    # Step 1-4: Execute through adapter with failing commit repo wrapper
    adapter1 = BoundedGitHubAdapter(
        token="ghp_validtoken123",
        transport=transport,
        state_repository=failing_repo,  # type: ignore[arg-type]
    )
    req = GitHubRequest(
        request_id="req-e2e-1",
        action=GitHubAction.CREATE_DRAFT_PR,
        repository="org/repo",
        branch="feat-e2e-lease",
        pr_title="E2E Lease Expiry PR",
        pr_body="E2E Body Content",
        evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        idempotency_key="pr-e2e-lease-key",
        tenant_id="tenant-default",
        change_id="change-lease-exp-01",
    )
    res1 = adapter1.execute(req)
    assert not res1.success
    assert "External mutation succeeded on provider" in (res1.error_message or "")
    assert transport.call_count == 1  # Step 2: Provider mutation executed once
    assert len(transport.stored_entities) == 1

    # Step 5: Immediate retry within active lease -> IN_PROGRESS
    adapter_immediate = BoundedGitHubAdapter(
        token="ghp_validtoken123",
        transport=transport,
        state_repository=inner_repo,
    )
    res_imm = adapter_immediate.execute(req)
    assert not res_imm.success
    assert "already in progress" in (res_imm.error_message or "").lower()
    assert transport.call_count == 1  # ZERO additional mutation

    # Step 6: Advance lease so it genuinely expires
    action_type = f"{GitHubAction.CREATE_DRAFT_PR.value}:pr-e2e-lease-key"
    payload_dict = {
        "action": GitHubAction.CREATE_DRAFT_PR.value,
        "repository": "org/repo",
        "branch": "feat-e2e-lease",
        "pr_title": "E2E Lease Expiry PR",
        "pr_body": "E2E Body Content",
    }
    payload_digest = sha256_hex(canonical_json_bytes(payload_dict))
    intent = IdempotencyIntent(
        tenant_id="tenant-default",
        change_id="change-lease-exp-01",
        scope=IdempotencyScope.EXTERNAL_WRITE,
        action_type=action_type,
        target_system="org/repo",
        caller_revision="1.0.0",
        payload_digest=payload_digest,
    )
    idem_key = IdempotencyKeyManager.compute_canonical_idempotency_key(intent)
    doc_id = IdempotencyKeyManager.compute_reservation_doc_id(idem_key)
    res_rec = inner_repo.get_idempotency_reservation(
        "tenant-default", "change-lease-exp-01", doc_id
    )
    assert res_rec is not None
    assert res_rec.status == IdempotencyReservationStatus.RESERVED

    # Expire reservation record
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    expired_rec = res_rec.model_copy(update={"expires_at": past_time})
    inner_repo.update_idempotency_reservation(
        "tenant-default", "change-lease-exp-01", expired_rec, expected_version=res_rec.version
    )

    # Step 7: Create fresh worker / adapter process
    adapter_fresh = BoundedGitHubAdapter(
        token="ghp_validtoken123",
        transport=transport,
        state_repository=inner_repo,
    )

    # Step 8-10: Execute retry
    res_reconciled = adapter_fresh.execute(req)
    assert res_reconciled.success
    assert res_reconciled.result_url == "https://github.com/org/repo/pull/42"
    # Total mutation calls across the entire lifecycle remain exactly 1!
    assert transport.call_count == 1
    assert transport.find_count >= 1

    # Step 11: Subsequent exact replay returns committed state
    res_replay = adapter_fresh.execute(req)
    assert res_replay.success
    assert res_replay.result_url == "https://github.com/org/repo/pull/42"
    assert transport.call_count == 1
