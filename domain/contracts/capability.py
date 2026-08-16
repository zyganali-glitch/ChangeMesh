"""ChangeMesh domain contracts — capability passport.

P-05.04: CapabilityPassport is deterministic qualification proof
for a specific agent revision.

A valid CapabilityPassport proves that a specific agent revision is
qualified for bounded capabilities.  It does NOT mean:
- that the current action is organizationally permitted,
- that LIVE_WRITE is automatically permitted,
- that a human decision exists.

CapabilityPassport is NOT AgentDescriptor:
- AgentDescriptor = what an agent declares it is/can do.
- CapabilityPassport = deterministic qualification proof.

Credentials, tokens, API keys, and reusable secret material are
forbidden in the passport contract surface.
"""

from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.conventions import UtcDateTime
from domain.contracts.data_class import DataClassLevel


class CapabilityPassport(BaseModel):
    """Deterministic qualification proof for a specific agent revision.

    ``CapabilityPassport`` carries qualification proof — it proves
    that a particular agent revision is qualified for bounded
    capabilities.  It is **not** an action authorization, permission
    grant, or human decision.

    Organizational policy still decides whether the action is allowed.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        passport_id: Stable passport identity.
        agent_id: Identity reference to the agent (not embedded
        mutable AgentDescriptor).
        agent_revision: Specific revision of the qualified agent.
        qualified_capabilities: Set of capabilities the agent is
            qualified for.
        qualified_tool_ids: Bounded permitted tool/action surface.
        permitted_data_classifications: Data-classification scope.
        qualification_evidence_ids: References to qualification
            evidence (must not be empty).
        issuer: Issuer/qualification source reference.
        issued_at: When the passport was issued.
        expires_at: When the passport expires.
        is_revoked: Whether the passport has been revoked.
        revoked_at: When revocation occurred (required if revoked).
        revocation_reason: Why revocation occurred (required if
            revoked).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    passport_id: str
    agent_id: str
    agent_revision: str
    qualified_capabilities: Tuple[str, ...]
    qualified_tool_ids: Tuple[str, ...] = ()
    permitted_data_classifications: Tuple[DataClassLevel, ...] = ()
    qualification_evidence_ids: Tuple[str, ...]
    issuer: str
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    is_revoked: bool = False
    revoked_at: Optional[UtcDateTime] = None
    revocation_reason: Optional[str] = None

    @field_validator(
        "schema_version",
        "passport_id",
        "agent_id",
        "agent_revision",
        "issuer",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("revocation_reason")
    @classmethod
    def _revocation_reason_not_blank_if_set(
        cls,
        v: Optional[str],
        info,
    ) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError("revocation_reason must not be blank when set")
        return v

    @field_validator(
        "qualified_capabilities",
        "qualified_tool_ids",
        "qualification_evidence_ids",
    )
    @classmethod
    def _validate_ref_tuples(cls, v: Tuple[str, ...], info) -> Tuple[str, ...]:
        for ref in v:
            if not ref or not ref.strip():
                raise ValueError(f"{info.field_name} elements must not be blank")
        if len(set(v)) != len(v):
            raise ValueError(f"{info.field_name} must not contain duplicate references")
        return v

    @model_validator(mode="after")
    def _validate_passport_invariants(self):
        # Qualified capabilities cannot be empty
        if not self.qualified_capabilities:
            raise ValueError("qualified_capabilities must not be empty")

        # Qualification evidence cannot be empty
        if not self.qualification_evidence_ids:
            raise ValueError("qualification_evidence_ids must not be empty")

        # Expiry must follow issuance
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")

        # Revoked passport must have consistent metadata
        if self.is_revoked:
            if self.revoked_at is None:
                raise ValueError("revoked passport must have revoked_at timestamp")
            if self.revoked_at < self.issued_at:
                raise ValueError("revoked_at must not predate issued_at")
            if not self.revocation_reason:
                raise ValueError("revoked passport must have revocation_reason")

        # Unrevoked passport must not masquerade as revoked
        if not self.is_revoked:
            if self.revoked_at is not None:
                raise ValueError("unrevoked passport must not have revoked_at")
            if self.revocation_reason is not None:
                raise ValueError("unrevoked passport must not have revocation_reason")

        return self
