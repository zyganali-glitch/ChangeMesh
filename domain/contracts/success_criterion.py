"""ChangeMesh domain contracts — success criterion."""

from pydantic import BaseModel, ConfigDict, field_validator


class SuccessCriterion(BaseModel):
    """What must be true for a requested change to count as successful.

    This contract describes *desired conditions*, not proof that those
    conditions were met.  Evidence of satisfaction belongs to
    ``EvidenceRecord`` (P-05.03).

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        criterion_id: Stable identifier for this criterion.
        description: Human-readable statement of the success condition.
        verification_method: How this criterion should be verified
            (e.g. ``"deterministic"``, ``"semantic"``, ``"manual"``).
        required_evidence_types: What kinds of evidence would satisfy
            this criterion.  These are *type labels*, not actual
            evidence records.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    criterion_id: str
    description: str
    verification_method: str
    required_evidence_types: list[str]

    @field_validator("criterion_id", "schema_version")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v
