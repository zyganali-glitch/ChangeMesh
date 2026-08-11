"""ChangeMesh domain contracts — data classification."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DataClassLevel(StrEnum):
    """Bounded set of data-classification levels.

    Derived from the ChangeMesh threat model (§7) and trust-boundary
    architecture.  The four levels cover the operational spectrum from
    freely publishable information to regulated / secret material.
    """

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class DataClassification(BaseModel):
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
