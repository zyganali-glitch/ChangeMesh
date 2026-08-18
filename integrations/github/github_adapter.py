from __future__ import annotations

import re
from enum import Enum
from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field

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


class ReconciliationStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class GitHubReconciliationQuery(BaseModel):
    """Semantic query for provider-observable reconciliation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: GitHubAction
    repository: str
    branch: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    commit_message: str | None = None
    files: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str | None = None
    payload_digest: str | None = None
    tenant_id: str | None = None
    change_id: str | None = None


class GitHubReconciliationResult(BaseModel):
    """Authoritative result returned by provider reconciliation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReconciliationStatus
    result_url: str | None = None
    commit_sha: str | None = None
    error_message: str | None = None
    raw_status_code: int | None = None
    matched_idempotency_key: str | None = None
    matched_payload_digest: str | None = None


class GitHubRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    action: GitHubAction
    repository: str
    branch: str | None = None
    commit_message: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    files: dict[str, str] = Field(default_factory=dict)
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

    def find_existing(
        self,
        token: str,
        query: GitHubReconciliationQuery,
    ) -> GitHubReconciliationResult: ...


def _caller_idempotency_fingerprint(caller_key: str | None) -> str | None:
    """Derives a safe non-secret deterministic SHA-256 fingerprint for caller idempotency keys."""
    if not caller_key or not caller_key.strip():
        return None
    return sha256_hex(caller_key.strip().encode("utf-8"))[:32]


def format_draft_pr_body_with_intent_marker(
    pr_body: str | None,
    idempotency_key: str | None,
    payload_digest: str,
) -> str:
    """Embeds non-secret deterministic intent marker for provider-observable idempotency."""
    body = (pr_body or "").strip()
    marker = f"<!-- changemesh-intent: key={idempotency_key or 'none'} digest={payload_digest} -->"
    if marker in body:
        return body
    if body:
        return f"{body}\n\n{marker}"
    return marker


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
        return (
            bool(self._token and self._token.strip())
            and (self._transport is not None)
            and (self._state_repository is not None)
        )

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
            key_fp = _caller_idempotency_fingerprint(request.idempotency_key)
            if key_fp and key_fp in self._created_prs:
                would_dup = True
            elif self._state_repository is not None and key_fp:
                tid = request.tenant_id or self._tenant_id
                cid = request.change_id or self._change_id
                action_type = f"{request.action.value}:fp_{key_fp[:16]}"
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
                idempotency_key=None,
            )

        repo_parts = [p for p in request.repository.strip().split("/") if p]
        if len(repo_parts) != 2:
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=f"Invalid repository format: {request.repository!r}",
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        if request.action == GitHubAction.CREATE_BRANCH:
            if not request.branch or not request.branch.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Branch name must not be empty for CREATE_BRANCH",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
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
                    idempotency_key=None,
                )

        elif request.action == GitHubAction.CREATE_COMMIT:
            if not request.branch or not request.branch.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Branch name must be explicit and non-empty for CREATE_COMMIT",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )
            if request.branch.strip().lower() in self.PROTECTED_BRANCHES:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=(f"Commit on protected branch {request.branch!r} is forbidden"),
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )
            if not request.commit_message or not request.commit_message.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Commit message must not be empty for CREATE_COMMIT",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )
            if not request.files:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Files dictionary must not be empty for CREATE_COMMIT",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

        elif request.action == GitHubAction.CREATE_DRAFT_PR:
            if not request.pr_title or not request.pr_title.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="PR title must not be empty for CREATE_DRAFT_PR",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )
            if not request.branch or not request.branch.strip():
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Branch must not be empty for CREATE_DRAFT_PR",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

        if self._transport is None:
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message="Real GitHub transport unavailable for LIVE_WRITE",
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        if self._state_repository is None:
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=(
                    "Durable SagaStateRepository is required for LIVE_WRITE external mutations"
                ),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        tenant_id = request.tenant_id or self._tenant_id
        change_id = request.change_id or self._change_id
        if not tenant_id or not tenant_id.strip() or not change_id or not change_id.strip():
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=(
                    "Valid tenant_id and change_id are required for LIVE_WRITE idempotency"
                ),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

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

        caller_fp = _caller_idempotency_fingerprint(request.idempotency_key)
        if caller_fp:
            action_type = f"{request.action.value}:fp_{caller_fp[:16]}"
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
        canonical_idempotency_id = IdempotencyKeyManager.compute_canonical_idempotency_key(intent)

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
                idempotency_key=None,
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
                idempotency_key=None,
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
                        idempotency_key=None,
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
                        idempotency_key=None,
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
                        idempotency_key=None,
                    )
                result_url = cached_res

            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=True,
                result_url=result_url,
                commit_sha=commit_sha,
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=canonical_idempotency_id,
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
                idempotency_key=None,
            )

        # Check provider reconciliation before executing mutation (MANDATORY for LIVE_WRITE)
        find_existing_fn = getattr(self._transport, "find_existing", None)
        if find_existing_fn is None or not callable(find_existing_fn):
            if reservation_outcome and reservation_outcome.reservation:
                try:
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                except Exception:
                    pass
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=(
                    "Transport lacks required reconciliation capability 'find_existing' "
                    "for LIVE_WRITE"
                ),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        recon_query = GitHubReconciliationQuery(
            action=request.action,
            repository=request.repository,
            branch=request.branch,
            pr_title=request.pr_title,
            pr_body=request.pr_body,
            commit_message=request.commit_message,
            files=request.files,
            idempotency_key=canonical_idempotency_id,
            payload_digest=payload_digest,
            tenant_id=tenant_id,
            change_id=change_id,
        )

        try:
            recon_res = find_existing_fn(
                token=self._token,
                query=recon_query,
            )
        except Exception as find_ex:
            if reservation_outcome and reservation_outcome.reservation:
                try:
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                except Exception:
                    pass
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=self._sanitize(f"Provider reconciliation check failed: {find_ex}"),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        if not isinstance(recon_res, GitHubReconciliationResult):
            if reservation_outcome and reservation_outcome.reservation:
                try:
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                except Exception:
                    pass
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message="Provider reconciliation returned invalid result type",
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        if (
            recon_res.status == ReconciliationStatus.UNKNOWN
            or recon_res.status == ReconciliationStatus.ERROR
        ):
            if reservation_outcome and reservation_outcome.reservation:
                try:
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                except Exception:
                    pass
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=self._sanitize(
                    recon_res.error_message
                    or (
                        f"Provider reconciliation returned indeterminate status "
                        f"({recon_res.status.value})"
                    )
                ),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        if recon_res.status == ReconciliationStatus.FOUND:
            # Reconciled existing action found on provider!
            # Exact semantic and cryptographic binding checks
            reconciled_url = recon_res.result_url
            reconciled_sha = recon_res.commit_sha

            identifier_valid = True
            identifier_err = ""

            if request.action == GitHubAction.CREATE_DRAFT_PR:
                if not reconciled_url or not re.match(
                    r"^https://github\.com/[^/]+/[^/]+/pull/\d+$", reconciled_url
                ):
                    identifier_valid = False
                    identifier_err = "Reconciled PR response missing valid real PR URL"
            elif request.action == GitHubAction.CREATE_COMMIT:
                if (
                    not reconciled_sha
                    or reconciled_sha == "fixture-sha"
                    or not re.match(r"^[0-9a-f]{40,64}$", reconciled_sha)
                ):
                    identifier_valid = False
                    identifier_err = "Reconciled commit response missing valid real commit SHA"
            elif request.action == GitHubAction.CREATE_BRANCH:
                if not reconciled_url or not re.match(
                    r"^https://github\.com/[^/]+/[^/]+/tree/.+$", reconciled_url
                ):
                    identifier_valid = False
                    identifier_err = "Reconciled branch response missing valid branch URL"

            if not identifier_valid:
                if reservation_outcome and reservation_outcome.reservation:
                    try:
                        IdempotencyKeyManager.release_intent(
                            self._state_repository,
                            tenant_id,
                            change_id,
                            reservation_outcome.reservation.reservation_id,
                        )
                    except Exception:
                        pass
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=identifier_err,
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

            # Verification 2 & 3: matched_payload_digest presence and exact match
            if not recon_res.matched_payload_digest or not recon_res.matched_payload_digest.strip():
                if reservation_outcome and reservation_outcome.reservation:
                    try:
                        IdempotencyKeyManager.release_intent(
                            self._state_repository,
                            tenant_id,
                            change_id,
                            reservation_outcome.reservation.reservation_id,
                        )
                    except Exception:
                        pass
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Reconciled entity missing matched_payload_digest",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

            if recon_res.matched_payload_digest != payload_digest:
                if reservation_outcome and reservation_outcome.reservation:
                    try:
                        IdempotencyKeyManager.release_intent(
                            self._state_repository,
                            tenant_id,
                            change_id,
                            reservation_outcome.reservation.reservation_id,
                        )
                    except Exception:
                        pass
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=(
                        f"Reconciled entity matched_payload_digest mismatch: "
                        f"expected {payload_digest!r}, got {recon_res.matched_payload_digest!r}"
                    ),
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

            # Verification 4 & 5: matched_idempotency_key presence and exact match
            if (
                not recon_res.matched_idempotency_key
                or not recon_res.matched_idempotency_key.strip()
            ):
                if reservation_outcome and reservation_outcome.reservation:
                    try:
                        IdempotencyKeyManager.release_intent(
                            self._state_repository,
                            tenant_id,
                            change_id,
                            reservation_outcome.reservation.reservation_id,
                        )
                    except Exception:
                        pass
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Reconciled entity missing matched_idempotency_key",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

            if recon_res.matched_idempotency_key != canonical_idempotency_id:
                if reservation_outcome and reservation_outcome.reservation:
                    try:
                        IdempotencyKeyManager.release_intent(
                            self._state_repository,
                            tenant_id,
                            change_id,
                            reservation_outcome.reservation.reservation_id,
                        )
                    except Exception:
                        pass
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=(
                        "Reconciled entity matched_idempotency_key mismatch: "
                        f"expected {canonical_idempotency_id!r}, "
                        f"got {recon_res.matched_idempotency_key!r}"
                    ),
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

            # All 5 verifications passed! Persist reconciled result to durable state repository
            res_val = reconciled_url or reconciled_sha or "APPLIED"
            result_digest = sha256_hex(
                canonical_json_bytes({"result": res_val, "action": request.action.value})
            )
            try:
                IdempotencyKeyManager.commit_intent(
                    self._state_repository,
                    tenant_id,
                    change_id,
                    reservation_outcome.reservation.reservation_id,
                    result_digest=result_digest,
                    receipt_status=res_val,
                )
            except Exception as commit_ex:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message=self._sanitize(
                        f"Reconciled existing provider entity ({res_val}) "
                        f"but durable commit failed: {commit_ex}"
                    ),
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=True,
                result_url=reconciled_url,
                commit_sha=reconciled_sha,
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=canonical_idempotency_id,
            )

        if recon_res.status != ReconciliationStatus.NOT_FOUND:
            if reservation_outcome and reservation_outcome.reservation:
                try:
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                except Exception:
                    pass
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=(
                    f"Reconciliation check did not authoritatively establish NOT_FOUND "
                    f"(status={recon_res.status.value})"
                ),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        # Authoritative NOT_FOUND -> proceed with fresh mutation
        pr_body_for_transport = request.pr_body
        if request.action == GitHubAction.CREATE_DRAFT_PR:
            pr_body_for_transport = format_draft_pr_body_with_intent_marker(
                request.pr_body, canonical_idempotency_id, payload_digest
            )

        try:
            transport_res = self._transport.execute(
                token=self._token,
                action=request.action,
                repository=request.repository,
                branch=request.branch,
                commit_message=request.commit_message,
                pr_title=request.pr_title,
                pr_body=pr_body_for_transport,
                files=request.files,
            )
        except Exception as ex:
            if reservation_outcome and reservation_outcome.reservation:
                try:
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                except Exception:
                    pass
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=self._sanitize(f"Transport execution error: {ex}"),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        if not transport_res.success:
            if reservation_outcome and reservation_outcome.reservation:
                try:
                    IdempotencyKeyManager.release_intent(
                        self._state_repository,
                        tenant_id,
                        change_id,
                        reservation_outcome.reservation.reservation_id,
                    )
                except Exception:
                    pass
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=self._sanitize(
                    transport_res.error_message or "GitHub live write failed"
                ),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        # Provider SUCCESS observed!
        if request.action == GitHubAction.CREATE_DRAFT_PR:
            if not transport_res.result_url or not re.match(
                r"^https://github\.com/[^/]+/[^/]+/pull/\d+$", transport_res.result_url
            ):
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Live response missing valid real PR URL",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

        elif request.action == GitHubAction.CREATE_COMMIT:
            if (
                not transport_res.commit_sha
                or transport_res.commit_sha == "fixture-sha"
                or not re.match(r"^[0-9a-f]{40,64}$", transport_res.commit_sha)
            ):
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Live response missing valid real commit SHA",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

        elif request.action == GitHubAction.CREATE_BRANCH:
            if not transport_res.result_url or not re.match(
                r"^https://github\.com/[^/]+/[^/]+/tree/.+$", transport_res.result_url
            ):
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=False,
                    error_message="Live response missing valid branch URL",
                    evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                    idempotency_key=None,
                )

        # Commit reservation to durable storage (DO NOT release on commit failure!)
        res_val = transport_res.result_url or transport_res.commit_sha or "APPLIED"
        result_digest = sha256_hex(
            canonical_json_bytes({"result": res_val, "action": request.action.value})
        )
        try:
            IdempotencyKeyManager.commit_intent(
                self._state_repository,
                tenant_id,
                change_id,
                reservation_outcome.reservation.reservation_id,
                result_digest=result_digest,
                receipt_status=res_val,
            )
        except Exception as commit_ex:
            return GitHubResponse(
                request_id=request.request_id,
                action=request.action,
                success=False,
                error_message=self._sanitize(
                    f"External mutation succeeded on provider ({res_val}) "
                    f"but durable commit failed: {commit_ex}. "
                    f"Reservation held; reconciliation required before retry."
                ),
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
                idempotency_key=None,
            )

        return GitHubResponse(
            request_id=request.request_id,
            action=request.action,
            success=True,
            result_url=transport_res.result_url,
            commit_sha=transport_res.commit_sha,
            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
            idempotency_key=canonical_idempotency_id,
        )

    def _execute_fixture(self, request: GitHubRequest) -> GitHubResponse:
        mode = (
            request.evidence_mode
            if request.evidence_mode
            in (ExecutionEvidenceMode.FIXTURE, ExecutionEvidenceMode.SIMULATION)
            else ExecutionEvidenceMode.FIXTURE
        )

        key_fp = _caller_idempotency_fingerprint(request.idempotency_key)
        if key_fp:
            if request.action == GitHubAction.CREATE_DRAFT_PR and key_fp in self._created_prs:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=True,
                    result_url=None,
                    evidence_mode=mode,
                    idempotency_key=None,
                )
            if request.action == GitHubAction.CREATE_COMMIT and key_fp in self._commits:
                return GitHubResponse(
                    request_id=request.request_id,
                    action=request.action,
                    success=True,
                    commit_sha=None,
                    evidence_mode=mode,
                    idempotency_key=None,
                )

        if request.action == GitHubAction.CREATE_DRAFT_PR and key_fp:
            self._created_prs[key_fp] = "SIMULATED_PR"
        elif request.action == GitHubAction.CREATE_COMMIT and key_fp:
            self._commits[key_fp] = "SIMULATED_COMMIT"

        return GitHubResponse(
            request_id=request.request_id,
            action=request.action,
            success=True,
            result_url=None,
            commit_sha=None,
            evidence_mode=mode,
            idempotency_key=None,
        )
