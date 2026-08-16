"""ChangeMesh provider-neutral authority verification boundary and contracts.

P-14.05: Defines credential-free authority decision contracts, signed authority envelopes,
materialized VerifiedAuthorityDecision models, and verification protocols.
Secret material (HMAC keys, private signing keys) is strictly forbidden in this core layer
and is owned entirely by outer adapters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.conventions import UtcDateTime

CANONICAL_SCHEMA_VERSION = "1.0.0"


class SignedAuthorityEnvelope(BaseModel):
    """Cryptographic approval envelope signed by an authorized external human authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    token_id: str
    plan_hash: str
    approver_id: str
    authority_slot_ref: str
    action_scope: str = ""
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    nonce: str
    signature: str

    @field_validator(
        "token_id", "plan_hash", "approver_id", "authority_slot_ref", "nonce", "signature"
    )
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v


SignedApprovalToken = SignedAuthorityEnvelope


class VerifiedAuthorityDecision(BaseModel):
    """Credential-free verified human authority decision.

    Materialized strictly after cryptographic verification by an outer adapter.
    Core and Policy Guardian consume this credential-free decision fact.
    Valid prior authority decisions can be reused across operations within the same plan,
    slot, and scope without re-prompting the human authority.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    decision_id: str
    envelope_id: str
    approver_id: str
    authority_slot_ref: str
    plan_hash: str
    action_scope: str
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    is_revoked: bool = False
    superseded_by: Optional[str] = None

    @field_validator(
        "decision_id",
        "envelope_id",
        "approver_id",
        "authority_slot_ref",
        "plan_hash",
        "action_scope",
    )
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("approver_id")
    @classmethod
    def _validate_approver_provenance(cls, v: str) -> str:
        v_clean = v.strip().lower()
        forbidden_sources = (
            "release_steward",
            "release-steward",
            "gemini",
            "gemini_semantic_judgment",
            "model_semantic_judgment",
            "system",
            "orchestrator",
            "auto",
        )
        if any(
            v_clean == f or v_clean.startswith(f + "@") or v_clean.startswith(f + ":")
            for f in forbidden_sources
        ):
            raise ValueError(
                f"approver_id {v!r} violates authority separation: "
                f"automated agents and system identities cannot self-authorize"
            )
        return v

    def is_active_for(
        self,
        plan_hash: str,
        authority_slot_ref: str,
        action_scope: str,
        now: Optional[datetime] = None,
    ) -> bool:
        """Check whether decision is active and matches all binding dimensions."""
        if now is None:
            now = datetime.now(timezone.utc)
        if self.is_revoked:
            return False
        if self.superseded_by is not None:
            return False
        if self.expires_at <= now:
            return False
        if self.plan_hash != plan_hash:
            return False
        if self.authority_slot_ref != authority_slot_ref:
            return False
        if self.action_scope != action_scope:
            return False
        return True


class AuthorityVerificationResult(BaseModel):
    """Outcome of verifying an authority envelope at the outer adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool
    status: str
    failure_reason: Optional[str] = None
    decision: Optional[VerifiedAuthorityDecision] = None


ApprovalValidationResult = AuthorityVerificationResult


@runtime_checkable
class AuthorityDecisionResolver(Protocol):
    """Provider-neutral protocol for outer adapters that verify cryptographic authority envelopes
    and resolve active verified authority decisions.

    Core layers consume this protocol without holding cryptographic secrets.
    """

    def verify_envelope(
        self,
        envelope: SignedAuthorityEnvelope,
        expected_plan_hash: str,
        expected_slot_ref: Optional[str] = None,
        expected_scope: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> AuthorityVerificationResult:
        """Verify envelope cryptographically and return verification result."""
        ...

    def verify_and_consume(
        self,
        token: SignedApprovalToken,
        expected_plan_hash: str,
        expected_slot_ref: Optional[str] = None,
        expected_scope: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ApprovalValidationResult:
        """Compatibility method mapping directly to verify_envelope."""
        ...

    def find_active_authority(
        self,
        plan_hash: str,
        authority_slot_ref: str,
        action_scope: str,
        now: Optional[datetime] = None,
    ) -> Optional[VerifiedAuthorityDecision]:
        """Find an active, unexpired, non-revoked authority decision matching all binding facts."""
        ...


# Provider-neutral protocol aliases
AuthorityDecisionVerifier = AuthorityDecisionResolver
AuthorityDecisionLookup = AuthorityDecisionResolver
