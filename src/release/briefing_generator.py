import uuid

from pydantic import BaseModel, ConfigDict


class OwnerBriefing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    briefing_id: str
    pr_url: str | None = None
    pr_branch: str | None = None
    plan_summary: str
    impacted_systems: tuple[str, ...]
    evidence_version: str
    approval_required: bool
    evidence_refs: tuple[str, ...] = ()


class BriefingGenerator:
    """Generate owner briefing linked to PR identity."""

    def generate_briefing(
        self,
        change_id: str,
        plan_summary: str,
        impacted_systems: list[str],
        pr_url: str | None = None,
        pr_branch: str | None = None,
        autonomy_class: str = "AUTO_EXECUTE",
    ) -> OwnerBriefing:

        approval_required = autonomy_class == "HUMAN_AUTHORITY_REQUIRED"

        return OwnerBriefing(
            change_id=change_id,
            briefing_id=f"briefing_{uuid.uuid4().hex[:8]}",
            pr_url=pr_url,
            pr_branch=pr_branch,
            plan_summary=plan_summary,
            impacted_systems=tuple(impacted_systems),
            evidence_version="v1",
            approval_required=approval_required,
        )
