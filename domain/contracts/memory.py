"""ChangeMesh domain contracts — memory record.

P-05.04: MemoryRecord represents cross-session ChangeMesh memory
subject to deterministic trust checks.

A trusted MemoryRecord may provide context.  It CANNOT:
- authorize an action,
- override deterministic evidence,
- override organizational policy,
- create human authority.

Credentials, tokens, API keys, and reusable secret material are
forbidden in the memory contract surface.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.data_class import DataClassLevel


class MemoryTrustStatus(str, Enum):
    """Explicit trust status for a MemoryRecord.

    Minimal representation — no large state machine.
    A record is either trusted with deterministic basis,
    untrusted (default/initial), or quarantined.
    """

    UNTRUSTED = "UNTRUSTED"
    TRUSTED = "TRUSTED"
    QUARANTINED = "QUARANTINED"


class MemoryRecord(BaseModel):
    """Cross-session ChangeMesh memory record with deterministic trust checks.

    ``MemoryRecord`` is a *context* contract — it stores typed memory
    with provenance, TTL, trust status, and contradiction tracking.
    It is **not** an authority source, action authorization, or
    policy decision.

    The contract is sufficient for the later Memory Trust Layer (P-11)
    to evaluate trust properties without introducing runtime now.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        memory_id: Stable memory identity.
        scope: What the memory belongs to (change, agent, system).
        content: Memory content or bounded summary payload.
        source: Provenance/source reference identifying origin.
        capture_timestamp: When the memory was captured/created.
        expiry_timestamp: When the memory expires.
        data_classification: Data-sensitivity scope using existing
            ``DataClassLevel``.
        trust_status: Explicit trust status (UNTRUSTED, TRUSTED,
            QUARANTINED).
        trust_evidence_ids: Deterministic trust basis/reference IDs.
            Required when trust_status is TRUSTED.
        contradiction_ids: Reference IDs for known contradictions.
        is_quarantined: Explicit quarantine flag.
        quarantine_reason: Reason for quarantine (required when
            quarantined).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    memory_id: str
    scope: str
    content: str
    source: str
    capture_timestamp: datetime
    expiry_timestamp: datetime
    data_classification: DataClassLevel
    trust_status: MemoryTrustStatus = MemoryTrustStatus.UNTRUSTED
    trust_evidence_ids: Tuple[str, ...] = ()
    contradiction_ids: Tuple[str, ...] = ()
    is_quarantined: bool = False
    quarantine_reason: Optional[str] = None

    @field_validator(
        "schema_version", "memory_id", "scope", "content", "source",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("trust_evidence_ids", "contradiction_ids")
    @classmethod
    def _validate_ref_tuples(cls, v: Tuple[str, ...], info) -> Tuple[str, ...]:
        for ref in v:
            if not ref or not ref.strip():
                raise ValueError(f"{info.field_name} elements must not be blank")
        
        # Check duplicates
        if len(set(v)) != len(v):
            raise ValueError(f"{info.field_name} must not contain duplicate references")
        return v

    @field_validator("quarantine_reason")
    @classmethod
    def _quarantine_reason_not_blank_if_set(
        cls, v: Optional[str], info,
    ) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError("quarantine_reason must not be blank when set")
        return v

    @model_validator(mode="after")
    def _validate_memory_invariants(self):
        # Expiry must logically follow capture time
        if self.expiry_timestamp <= self.capture_timestamp:
            raise ValueError(
                "expiry_timestamp must be after capture_timestamp"
            )

        # Quarantined memory cannot simultaneously be trusted
        if self.is_quarantined and self.trust_status == MemoryTrustStatus.TRUSTED:
            raise ValueError(
                "quarantined memory cannot simultaneously be TRUSTED"
            )

        # QUARANTINED trust_status must align with is_quarantined flag
        if self.trust_status == MemoryTrustStatus.QUARANTINED and not self.is_quarantined:
            raise ValueError(
                "trust_status QUARANTINED requires is_quarantined=True"
            )

        if self.is_quarantined and self.trust_status not in (
            MemoryTrustStatus.QUARANTINED,
            MemoryTrustStatus.UNTRUSTED,
        ):
            raise ValueError(
                "quarantined memory trust_status must be QUARANTINED or UNTRUSTED"
            )

        # Quarantined memory must have a quarantine reason
        if self.is_quarantined and not self.quarantine_reason:
            raise ValueError(
                "quarantined memory must have a quarantine_reason"
            )

        # Trusted memory must have deterministic trust basis
        if (
            self.trust_status == MemoryTrustStatus.TRUSTED
            and not self.trust_evidence_ids
        ):
            raise ValueError(
                "TRUSTED memory must have at least one trust_evidence_id"
            )

        return self
