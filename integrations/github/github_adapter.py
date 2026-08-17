from __future__ import annotations

import re
from enum import Enum
from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict

from domain.contracts.conventions import (
    canonical_json_bytes,
    sha256_hex,
)
from domain.contracts.evidence import ExecutionEvidenceMode
from src.orchestrator.idempotency import (
    IdempotencyIntent,
    IdempotencyKeyManager,
    IdempotencyReservationOutcomeStatus,
    IdempotencyScope,
)
from src.orchestrator.state_repository import SagaStateRepository


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
    evidence_mode: ExecutionEvidenceMode = ExecutionEvidenceMode.FIXTURE
    change_id: str | None = None
    tenant_id: str | None = None


class GitHubResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    action: GitHubAction
    success: bool
    result_url: str | None = None
    commit_sha: str | None = None
    error_message: str | None = None
    evidence_mode: ExecutionEvidenceMode
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
    evidence_mode: ExecutionEvidenceMode = ExecutionEvidenceMode.FIXTURE


class GitHubTransportResult(BaseModel):
    """Result returned by a GitHub transport boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    success: bool
    result_url: str | None = None
    commit_sha: str | None = None
    error_message: str | None = None
    raw_status_code: int | None = None


class GitHubTransport(Protocol):
    """Protocol for GitHub HTTP/API transport."""

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
    ) -> GitHubTransportResult: ...


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

    PROTECTED_BRANCHES: ClassVar[frozenset[str]] = frozenset(
        {"main", "master", "prod", "production", "release"}
    )

    def __init__(
        self,
        token: str | None = None,
        transport: GitHubTransport | None = None,
        state_repository: SagaStateRepository | None = None,
        tenant_id: str = "tenant-default",
        change_id: str = "change-default",
    ):
        self._token = token
        self._transport = transport
        self._state_repository = state_repository
        self._tenant_id = tenant_id
        self._change_id = change_id
        self._created_prs: dict[str, str] = {}
        self._commits: dict[str, str] = {}

    @property
    def is_live(self) -> bool:
        return bool(self._token and self._token.strip()) and (self._transport is not None)

    def _sanitize(self, message: str) -> str:
        if not message:
            return message
        sanitized = message
        if self._token and self._token in sanitized:
            sanitized = sanitized.replace(self._token, "[REDACTED]")
        sanitized = re.sub(r"ghp_[A-Za-z0-9_]+", "[REDACTED]", sanitized)
        sanitized = re.sub(r"github_pat_[A-Za-z0-9_]+", "[REDACTED]", sanitized)
        sanitized = re.sub(
            r"bearer\s+[A-Za-z0-9_\-\.]+", "bearer [REDACTED]", sanitized, flags=re.IGNORECASE
        )
        return sanitized

    def _check_forbidden(self, action_name: str) -> None:
        low = action_name.lower()
        if low in self.FORBIDDEN_ACTIONS or any(f in low for f in self.FORBIDDEN_ACTIONS):
            raise ValueError(f"Action {action_name} is FORBIDDEN")

    def dry_run(self, request: GitHubRequest) -> DryRunArtifact:
        self._check_forbidden(request.action.value)

        would_dup = False
        if request.action == GitHubAction.CREATE_DRAFT_PR and request.idempotency_key:
            if request.idempotency_key in self._created_prs:
                would_dup = True
            elif self._state_repository is not None:
                tid = request.tenant_id or self._tenant_id
                cid = request.change_id or self._change_id
                action_type = f"{request.action.value}:{request.idempotency_key}"
                intent = IdempotencyIntent(
                    tenant_id=tid,
                    change_id=cid,
                    scope=IdempotencyScope.EXTERNAL_WRITE,
                    action_type=action_type,
                    target_system=request.repository,
                    caller_revision="1.0.0",
                    payload_digest="0" * 64,
                )
                idem_key = IdempotencyKeyManager.compute_canonical_idempotency_key(intent)
                doc_id = IdempotencyKeyManager.compute_reservation_doc_id(idem_key)
                existing = self._state_repository.get_idempotency_reservation(tid, cid, doc_id)
                if existing is not None and existing.status.value in ("COMMITTED", "RESERVED"):
                    would_dup = True

        evidence_mode = (
            request.evidence_mode
            if request.evidence_mode != ExecutionEvidenceMode.LIVE_WRITE
            else ExecutionEvidenceMode.SIMULATION
        )

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
            evidence_mode=evidence_mode,
        )

    def execute(self, request: GitHubRequest) -> GitHubResponse:
        self._check_forbidden(request.action.value)

        if request.evidence_mode == ExecutionEvidenceMode.LIVE_WRITE:
            return self._execute_live_write(request)

        return self._execute_fixture(request)

    def _execute_live_write(self, request: GitHubRequest) -> GitHubResponse:
        if not self._token or not self._token.strip():
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message="Missing GitHub credentials for LIVE_WRITE",
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=request.idempotency_key,
            )

        repo_parts = [p for p in request.repository.strip().split("/") if p]
        if len(repo_parts) != 2:
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=f"Invalid repository format: {request.repository!r}",
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=request.idempotency_key,
            )

        if request.action == GitHubAction.CREATE_BRANCH:
            if not request.branch or not request.branch.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Branch name must not be empty for CREATE_BRANCH",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )
            if request.branch.strip().lower() in self.PROTECTED_BRANCHES:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=(
                        f"Branch creation on protected branch {request.branch!r} is forbidden"
                    ),
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

        elif request.action == GitHubAction.CREATE_COMMIT:
            if not request.commit_message or not request.commit_message.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Commit message must not be empty for CREATE_COMMIT",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )
            if not request.files:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Files dictionary must not be empty for CREATE_COMMIT",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

        elif request.action == GitHubAction.CREATE_DRAFT_PR:
            if not request.pr_title or not request.pr_title.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="PR title must not be empty for CREATE_DRAFT_PR",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )
            if not request.branch or not request.branch.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Branch must not be empty for CREATE_DRAFT_PR",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

        if self._transport is None:
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message="Real GitHub transport unavailable for LIVE_WRITE",
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=request.idempotency_key,
            )

        tenant_id = request.tenant_id or self._tenant_id
        change_id = request.change_id or self._change_id
        reservation_outcome = None
        intent = None

        if self._state_repository is not None:
            # Build semantic mutation payload dictionary (strictly excluding request_id)
            if request.action == GitHubAction.CREATE_DRAFT_PR:
                payload_dict = {
                    "action": request.action.value,
                    "repository": request.repository,
                    "branch": request.branch,
                    "pr_title": request.pr_title,
                    "pr_body": request.pr_body or "",
                }
            elif request.action == GitHubAction.CREATE_COMMIT:
                payload_dict = {
                    "action": request.action.value,
                    "repository": request.repository,
                    "branch": request.branch or "",
                    "commit_message": request.commit_message,
                    "files": sorted(request.files.items()) if request.files else [],
                }
            elif request.action == GitHubAction.CREATE_BRANCH:
                payload_dict = {
                    "action": request.action.value,
                    "repository": request.repository,
                    "branch": request.branch,
                }
            else:
                payload_dict = {
                    "action": request.action.value,
                    "repository": request.repository,
                    "branch": request.branch,
                }

            payload_digest = sha256_hex(canonical_json_bytes(payload_dict))

            if request.idempotency_key:
                action_type = f"{request.action.value}:{request.idempotency_key}"
            else:
                action_type = f"{request.action.value}:{request.branch or 'default'}"

            intent = IdempotencyIntent(
                tenant_id=tenant_id,
                change_id=change_id,
                scope=IdempotencyScope.EXTERNAL_WRITE,
                action_type=action_type,
                target_system=request.repository,
                caller_revision="1.0.0",
                payload_digest=payload_digest,
            )
            try:
                reservation_outcome = IdempotencyKeyManager.reserve_intent(
                    self._state_repository, intent
                )
            except Exception as ex:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=self._sanitize(f"Idempotency reservation failed: {ex}"),
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

            # In-progress by another active worker -> fail closed with zero transport call
            if reservation_outcome.status == IdempotencyReservationOutcomeStatus.IN_PROGRESS:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=(
                        f"External write intent {action_type!r} is already in progress "
                        f"by an active worker"
                    ),
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

            # Exact replay -> return verified real cached result without second transport call
            if reservation_outcome.status == IdempotencyReservationOutcomeStatus.EXACT_REPLAY:
                cached_res = reservation_outcome.cached_receipt_status
                result_url = None
                commit_sha = None

                if request.action == GitHubAction.CREATE_DRAFT_PR:
                    if not cached_res or not re.match(
                        r"^https://github\.com/[^/]+/[^/]+/pull/\d+$", cached_res
                    ):
                        return GitHubResponse(
                            request_id=request.request_id,
                            action=request.action,
                            success=False,
                            error_message="Cached replay receipt missing or invalid real PR URL",
                            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                            idempotency_key=request.idempotency_key,
                        )
                    result_url = cached_res

                elif request.action == GitHubAction.CREATE_COMMIT:
                    if (
                        not cached_res
                        or cached_res == "fixture-sha"
                        or not re.match(r"^[0-9a-f]{40,64}$", cached_res)
                    ):
                        return GitHubResponse(
                            request_id=request.request_id,
                            action=request.action,
                            success=False,
                            error_message="Cached replay receipt missing or invalid commit SHA",
                            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                            idempotency_key=request.idempotency_key,
                        )
                    commit_sha = cached_res

                elif request.action == GitHubAction.CREATE_BRANCH:
                    if not cached_res or not re.match(
                        r"^https://github\.com/[^/]+/[^/]+/tree/.+$", cached_res
                    ):
                        return GitHubResponse(
                            request_id=request.request_id,
                            action=request.action,
                            success=False,
                            error_message="Cached replay receipt missing or invalid branch URL",
                            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                            idempotency_key=request.idempotency_key,
                        )
                    result_url = cached_res

                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=True,
                    result_url=result_url,
                    commit_sha=commit_sha,
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

            if reservation_outcome.status != IdempotencyReservationOutcomeStatus.GRANTED:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=(
                        f"Idempotency reservation not granted: "
                        f"status={reservation_outcome.status.value}"
                    ),
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

        try:
            transport_res = self._transport.execute(
                token=self._token,
                action=request.action,
                repository=request.repository,
                branch=request.branch,
                commit_message=request.commit_message,
                pr_title=request.pr_title,
                pr_body=request.pr_body,
                files=request.files,
            )
        except Exception as ex:
            if (
                self._state_repository is not None
                and reservation_outcome
                and reservation_outcome.reservation
            ):
                IdempotencyKeyManager.release_intent(
                    self._state_repository,
                    tenant_id,
                    change_id,
                    reservation_outcome.reservation.reservation_id,
                )
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=self._sanitize(f"Transport execution error: {ex}"),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=request.idempotency_key,
            )

        if not transport_res.success:
            if (
                self._state_repository is not None
                and reservation_outcome
                and reservation_outcome.reservation
            ):
                IdempotencyKeyManager.release_intent(
                    self._state_repository,
                    tenant_id,
                    change_id,
                    reservation_outcome.reservation.reservation_id,
                )
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=self._sanitize(
                    transport_res.error_message or "GitHub live write failed"
                ),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=request.idempotency_key,
            )

        if request.action == GitHubAction.CREATE_DRAFT_PR:
            if not transport_res.result_url or not re.match(
                r"^https://github\.com/[^/]+/[^/]+/pull/\d+$", transport_res.result_url
            ):
                if (
                    self._state_repository is not None
                    and reservation_outcome
                    and reservation_outcome.reservation
                ):
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Live response missing valid real PR URL",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

        elif request.action == GitHubAction.CREATE_COMMIT:
            if (
                not transport_res.commit_sha
                or transport_res.commit_sha == "fixture-sha"
                or not re.match(r"^[0-9a-f]{40,64}$", transport_res.commit_sha)
            ):
                if (
                    self._state_repository is not None
                    and reservation_outcome
                    and reservation_outcome.reservation
                ):
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Live response missing valid real commit SHA",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

        elif request.action == GitHubAction.CREATE_BRANCH:
            if not transport_res.result_url or not re.match(
                r"^https://github\.com/[^/]+/[^/]+/tree/.+$", transport_res.result_url
            ):
                if (
                    self._state_repository is not None
                    and reservation_outcome
                    and reservation_outcome.reservation
                ):
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Live response missing valid branch URL",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=request.idempotency_key,
                )

        if (
            self._state_repository is not None
            and reservation_outcome
            and reservation_outcome.reservation
            and intent is not None
        ):
            res_val = transport_res.result_url or transport_res.commit_sha or "APPLIED"
            result_digest = sha256_hex(
                canonical_json_bytes({"result": res_val, "action": request.action.value})
            )
            IdempotencyKeyManager.commit_intent(
                self._state_repository,
                tenant_id,
                change_id,
                reservation_outcome.reservation.reservation_id,
                result_digest=result_digest,
                receipt_status=res_val,
            )

        return GitHubResponse(
            request_id=request.request_id,
            action=request.action,
            success=True,
            result_url=transport_res.result_url,
            commit_sha=transport_res.commit_sha,
            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
            idempotency_key=request.idempotency_key,
        )

    def _execute_fixture(self, request: GitHubRequest) -> GitHubResponse:
        mode = (
            request.evidence_mode
            if request.evidence_mode
            in (ExecutionEvidenceMode.FIXTURE, ExecutionEvidenceMode.SIMULATION)
            else ExecutionEvidenceMode.FIXTURE
        )

        if request.idempotency_key:
            if (
                request.action == GitHubAction.CREATE_DRAFT_PR
                and request.idempotency_key in self._created_prs
            ):
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=True,
                    result_url=None,
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
                    commit_sha=None,
                    evidence_mode=mode,
                    idempotency_key=request.idempotency_key,
                )

        if request.action == GitHubAction.CREATE_DRAFT_PR and request.idempotency_key:
            self._created_prs[request.idempotency_key] = "SIMULATED_PR"
        elif request.action == GitHubAction.CREATE_COMMIT and request.idempotency_key:
            self._commits[request.idempotency_key] = "SIMULATED_COMMIT"

        return GitHubResponse(
            request_id=request.request_id,
            action=request.action,
            success=True,
            result_url=None,
            commit_sha=None,
            evidence_mode=mode,
            idempotency_key=request.idempotency_key,
        )
