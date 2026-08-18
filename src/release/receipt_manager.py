from __future__ import annotations

import datetime
import re

from pydantic import BaseModel, ConfigDict

from domain.contracts.evidence import ExecutionEvidenceMode
from integrations.github.github_adapter import GitHubAction, GitHubRequest, GitHubResponse


class ExternalActionReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    receipt_id: str
    change_id: str
    action: str
    target_repository: str
    branch: str | None = None
    commit_sha: str | None = None
    pr_url: str | None = None
    evidence_mode: ExecutionEvidenceMode
    request_metadata: dict[str, str] = {}
    response_metadata: dict[str, str] = {}
    contains_credentials: bool = False
    created_at: str


class ReceiptManager:
    """Record and validate external-action receipts without credentials."""

    SECRET_PATTERNS = (
        re.compile(r"ghp_[A-Za-z0-9_]+"),
        re.compile(r"github_pat_[A-Za-z0-9_]+"),
        re.compile(r"bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
        re.compile(r"-{5}BEGIN[A-Z\s]+PRIVATE KEY-{5}"),
    )

    def _sanitize_meta(self, meta: dict[str, str]) -> dict[str, str]:
        sanitized = {}
        for k, v in meta.items():
            clean_v = str(v)
            for pat in self.SECRET_PATTERNS:
                clean_v = pat.sub("[REDACTED]", clean_v)
            sanitized[k] = clean_v
        return sanitized

    def create_receipt(
        self, change_id: str, github_response: GitHubResponse, github_request: GitHubRequest
    ) -> ExternalActionReceipt:
        req_meta = {"idempotency_key": str(github_response.idempotency_key or "none")}
        resp_meta = {
            "success": str(github_response.success),
            "evidence_mode": github_response.evidence_mode.value,
        }
        if github_response.error_message:
            resp_meta["error_message"] = github_response.error_message

        return ExternalActionReceipt(
            receipt_id=f"receipt_{github_response.request_id}",
            change_id=change_id,
            action=github_response.action.value,
            target_repository=github_request.repository,
            branch=github_request.branch,
            commit_sha=github_response.commit_sha,
            pr_url=github_response.result_url,
            evidence_mode=github_response.evidence_mode,
            request_metadata=self._sanitize_meta(req_meta),
            response_metadata=self._sanitize_meta(resp_meta),
            contains_credentials=False,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    def validate_receipt(self, receipt: ExternalActionReceipt) -> tuple[str, ...]:
        errors: list[str] = []
        if receipt.contains_credentials:
            errors.append("Receipt claims to contain credentials")

        all_values = (
            list(receipt.request_metadata.values())
            + list(receipt.response_metadata.values())
            + [
                receipt.target_repository,
                receipt.branch or "",
                receipt.commit_sha or "",
                receipt.pr_url or "",
            ]
        )
        for val in all_values:
            low = val.lower()
            if "token" in low or "secret" in low:
                errors.append("Possible credential leak in receipt")
                break
            for pat in self.SECRET_PATTERNS:
                if pat.search(val):
                    errors.append("Secret signature detected in receipt")
                    break

        if receipt.evidence_mode == ExecutionEvidenceMode.LIVE_WRITE:
            if receipt.response_metadata.get("success") != "True":
                errors.append("LIVE_WRITE receipt indicates failed response")
            if receipt.action == GitHubAction.CREATE_DRAFT_PR.value:
                if not receipt.pr_url or not re.match(
                    r"^https://github\.com/[^/]+/[^/]+/pull/\d+$", receipt.pr_url
                ):
                    errors.append("Missing or invalid real PR URL in LIVE_WRITE mode")
            elif receipt.action == GitHubAction.CREATE_COMMIT.value:
                if (
                    not receipt.commit_sha
                    or receipt.commit_sha == "fixture-sha"
                    or not re.match(r"^[0-9a-f]{40,64}$", receipt.commit_sha)
                ):
                    errors.append("Missing or invalid real commit SHA in LIVE_WRITE mode")
            elif receipt.action == GitHubAction.CREATE_BRANCH.value:
                if not receipt.branch:
                    errors.append("Missing branch in LIVE_WRITE mode")

        return tuple(errors)
