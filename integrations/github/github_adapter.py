from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class GitHubAction(str, Enum):
    CREATE_BRANCH = "CREATE_BRANCH"
    CREATE_COMMIT = "CREATE_COMMIT"
    CREATE_DRAFT_PR = "CREATE_DRAFT_PR"


class GitHubRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    action: GitHubAction
    repository: str
    branch: str | None = None
    commit_message: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    files: dict[str, str] = {}
    idempotency_key: str | None = None


class GitHubResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    action: GitHubAction
    success: bool
    result_url: str | None = None
    commit_sha: str | None = None
    error_message: str | None = None
    evidence_mode: str
    idempotency_key: str | None = None


class DryRunArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    action: GitHubAction
    repository: str
    branch: str | None = None
    files_count: int
    commit_message: str | None = None
    pr_title: str | None = None
    credentials_redacted: bool = True
    would_create_duplicate: bool = False
    evidence_mode: str = "FIXTURE"


class BoundedGitHubAdapter:
    """Bounded GitHub adapter: branch, commits, draft PR ONLY."""

    FORBIDDEN_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "merge",
            "deploy",
            "force_push",
            "delete_repo",
            "update_protected_branch",
            "access_secrets",
            "export_secrets",
        }
    )

    def __init__(self, token: str | None = None):
        self._token = token
        self._created_prs: dict[str, str] = {}
        self._commits: dict[str, str] = {}

    @property
    def is_live(self) -> bool:
        return bool(self._token)

    def dry_run(self, request: GitHubRequest) -> DryRunArtifact:
        self._check_forbidden(request.action.value)

        would_dup = False
        if request.action == GitHubAction.CREATE_DRAFT_PR and request.idempotency_key:
            if request.idempotency_key in self._created_prs:
                would_dup = True

        return DryRunArtifact(
            request_id=request.request_id,
            action=request.action,
            repository=request.repository,
            branch=request.branch,
            files_count=len(request.files),
            commit_message=request.commit_message,
            pr_title=request.pr_title,
            credentials_redacted=True,
            would_create_duplicate=would_dup,
            evidence_mode="FIXTURE",
        )

    def execute(self, request: GitHubRequest) -> GitHubResponse:
        self._check_forbidden(request.action.value)

        mode = "LIVE_WRITE" if self.is_live else "FIXTURE"

        if request.idempotency_key:
            if (
                request.action == GitHubAction.CREATE_DRAFT_PR
                and request.idempotency_key in self._created_prs
            ):
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=True,
                    result_url=self._created_prs[request.idempotency_key],
                    evidence_mode=mode,
                    idempotency_key=request.idempotency_key,
                )
            if (
                request.action == GitHubAction.CREATE_COMMIT
                and request.idempotency_key in self._commits
            ):
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=True,
                    commit_sha=self._commits[request.idempotency_key],
                    evidence_mode=mode,
                    idempotency_key=request.idempotency_key,
                )

        result_url = None
        commit_sha = None

        if request.action == GitHubAction.CREATE_BRANCH:
            result_url = f"https://github.com/{request.repository}/tree/{request.branch}"
        elif request.action == GitHubAction.CREATE_COMMIT:
            commit_sha = "fixture-sha"
            if request.idempotency_key:
                self._commits[request.idempotency_key] = commit_sha
        elif request.action == GitHubAction.CREATE_DRAFT_PR:
            result_url = f"https://github.com/{request.repository}/pull/1"
            if request.idempotency_key:
                self._created_prs[request.idempotency_key] = result_url

        return GitHubResponse(
            request_id=request.request_id,
            action=request.action,
            success=True,
            result_url=result_url,
            commit_sha=commit_sha,
            evidence_mode=mode,
            idempotency_key=request.idempotency_key,
        )

    def _check_forbidden(self, action_name: str) -> None:
        if action_name.lower() in self.FORBIDDEN_ACTIONS:
            raise ValueError(f"Action {action_name} is FORBIDDEN")
