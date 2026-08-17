import pytest

from integrations.github.github_adapter import BoundedGitHubAdapter, GitHubAction, GitHubRequest
from src.release.briefing_generator import BriefingGenerator
from src.release.receipt_manager import ExternalActionReceipt, ReceiptManager


def test_adapter_allowed_actions():
    adapter = BoundedGitHubAdapter()
    req = GitHubRequest(
        request_id="1", action=GitHubAction.CREATE_BRANCH, repository="repo", branch="main"
    )
    res = adapter.execute(req)
    assert res.success
    assert res.evidence_mode == "FIXTURE"


def test_adapter_forbidden_actions():
    adapter = BoundedGitHubAdapter()
    with pytest.raises(ValueError, match="FORBIDDEN"):
        adapter._check_forbidden("merge")
    with pytest.raises(ValueError, match="FORBIDDEN"):
        adapter._check_forbidden("deploy")


def test_dry_run():
    adapter = BoundedGitHubAdapter()
    req = GitHubRequest(request_id="1", action=GitHubAction.CREATE_DRAFT_PR, repository="repo")
    artifact = adapter.dry_run(req)

    assert artifact.evidence_mode == "FIXTURE"
    assert artifact.credentials_redacted


def test_idempotency():
    adapter = BoundedGitHubAdapter()
    req1 = GitHubRequest(
        request_id="1", action=GitHubAction.CREATE_DRAFT_PR, repository="repo", idempotency_key="k1"
    )
    res1 = adapter.execute(req1)

    req2 = GitHubRequest(
        request_id="2", action=GitHubAction.CREATE_DRAFT_PR, repository="repo", idempotency_key="k1"
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
    req = GitHubRequest(request_id="1", action=GitHubAction.CREATE_BRANCH, repository="repo")
    res = adapter.execute(req)

    receipt = manager.create_receipt("c1", res, req)
    assert not receipt.contains_credentials

    errors = manager.validate_receipt(receipt)
    assert not errors

    # Simulate bad receipt
    bad_receipt = ExternalActionReceipt(
        receipt_id="r1",
        change_id="c1",
        action="CREATE_BRANCH",
        target_repository="repo",
        evidence_mode="FIXTURE",
        created_at="now",
        contains_credentials=True,
    )
    assert manager.validate_receipt(bad_receipt)
