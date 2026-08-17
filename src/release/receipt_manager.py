import datetime

from pydantic import BaseModel, ConfigDict

from integrations.github.github_adapter import GitHubRequest, GitHubResponse


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
    evidence_mode: str
    request_metadata: dict[str, str] = {}
    response_metadata: dict[str, str] = {}
    contains_credentials: bool = False
    created_at: str


class ReceiptManager:
    """Record external-action receipts without credentials."""

    def create_receipt(
        self, change_id: str, github_response: GitHubResponse, github_request: GitHubRequest
    ) -> ExternalActionReceipt:

        return ExternalActionReceipt(
            receipt_id=f"receipt_{github_response.request_id}",
            change_id=change_id,
            action=github_response.action.value,
            target_repository=github_request.repository,
            branch=github_request.branch,
            commit_sha=github_response.commit_sha,
            pr_url=github_response.result_url,
            evidence_mode=github_response.evidence_mode,
            request_metadata={"idempotency_key": github_request.idempotency_key or "none"},
            response_metadata={"success": str(github_response.success)},
            contains_credentials=False,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    def validate_receipt(self, receipt: ExternalActionReceipt) -> tuple[str, ...]:
        errors = []
        if receipt.contains_credentials:
            errors.append("Receipt claims to contain credentials")

        # check meta for leak hints (rudimentary)
        for val in receipt.request_metadata.values():
            if "token" in val.lower() or "secret" in val.lower():
                errors.append("Possible credential leak in request_metadata")

        return tuple(errors)
