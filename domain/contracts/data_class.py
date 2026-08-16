"""ChangeMesh domain contracts — data classification."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class DataClassLevel(str, Enum):
    """Bounded set of data-classification levels.

    Derived from the ChangeMesh threat model (§7) and trust-boundary
    architecture.  The four levels cover the operational spectrum from
    freely publishable information to regulated / secret material.

    Credentials, tokens, API keys, and reusable secret material are
    outside the ordinary DataClass permission surface and remain
    adapter-only regardless of DataClass level.
    """

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class DataClass(BaseModel):
    """Typed data-classification contract.

    Provides a machine-readable, provider-neutral classification value
    that agents, tools, and orchestration layers use to enforce
    data-handling boundaries.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        classification: One of the four bounded classification levels.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    classification: DataClassLevel

    @field_validator("schema_version")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v
