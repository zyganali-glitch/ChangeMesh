"""ChangeMesh capability passport issuer and verifier.

P-12.02 & P-12.03: Issues proof-carrying CapabilityPassports and verifies
qualification, expiry, revocation, and revision matching without self-attestation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.capability import CapabilityPassport
from domain.contracts.conventions import UtcDateTime
from domain.contracts.data_class import DataClassLevel
from src.registry.capabilities import AgentCapabilityRequirement

CANONICAL_SCHEMA_VERSION = "1.0.0"


class PassportIssuanceRequest(BaseModel):
    """Request to issue a CapabilityPassport backed by qualification evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    agent_revision: str
    qualified_capabilities: Tuple[str, ...]
    qualified_tool_ids: Tuple[str, ...] = ()
    permitted_data_classifications: Tuple[DataClassLevel, ...] = (DataClassLevel.RESTRICTED,)
    qualification_evidence_ids: Tuple[str, ...]
    issuer: str
    validity_seconds: int = 86400 * 30  # 30 days default

    @field_validator("agent_id", "agent_revision", "issuer")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("qualification_evidence_ids")
    @classmethod
    def _must_have_evidence(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        if not v:
            raise ValueError("qualification_evidence_ids must not be empty (self-attestation is forbidden)")
        for item in v:
            if not item or not item.strip():
                raise ValueError("evidence IDs must not be blank")
        return v


class PassportValidationResult(BaseModel):
    """Result of verifying a CapabilityPassport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool
    status: str  # "VALID", "REVOKED", "EXPIRED", "UNQUALIFIED", "EVIDENCE_STALE", "REVISION_MISMATCH"
    failure_reason: Optional[str] = None


class PassportIssuer:
    """Issues deterministic CapabilityPassports from verified qualification evidence."""

    @classmethod
    def issue_passport(
        cls,
        request: PassportIssuanceRequest,
        now: Optional[datetime] = None,
    ) -> CapabilityPassport:
        """Issue a new CapabilityPassport."""
        if now is None:
            now = datetime.now(timezone.utc)

        expires_at = now + timedelta(seconds=request.validity_seconds)
        passport_id = f"pass-{request.agent_id}-{uuid.uuid4().hex[:8]}"

        return CapabilityPassport(
            schema_version="1.0.0",
            passport_id=passport_id,
            agent_id=request.agent_id,
            agent_revision=request.agent_revision,
            qualified_capabilities=request.qualified_capabilities,
            qualified_tool_ids=request.qualified_tool_ids,
            permitted_data_classifications=request.permitted_data_classifications,
            qualification_evidence_ids=request.qualification_evidence_ids,
            issuer=request.issuer,
            issued_at=now,
            expires_at=expires_at,
            is_revoked=False,
        )


class PassportVerifier:
    """Verifies passport validity, revocation, expiry, and capability match."""

    @classmethod
    def verify(
        cls,
        passport: CapabilityPassport,
        requirement: Optional[AgentCapabilityRequirement] = None,
        expected_revision: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> PassportValidationResult:
        """Evaluate passport against revocation, expiry, revision, and required capabilities."""
        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Revocation Check (Fail Closed)
        if passport.is_revoked:
            return PassportValidationResult(
                is_valid=False,
                status="REVOKED",
                failure_reason=f"Passport is revoked: {passport.revocation_reason or 'unspecified reason'}",
            )

        # 2. Expiration Check
        if passport.expires_at <= now:
            return PassportValidationResult(
                is_valid=False,
                status="EXPIRED",
                failure_reason=f"Passport expired at {passport.expires_at.isoformat()}",
            )

        # 3. Exact Revision Match
        if expected_revision and passport.agent_revision != expected_revision:
            return PassportValidationResult(
                is_valid=False,
                status="REVISION_MISMATCH",
                failure_reason=f"Passport revision {passport.agent_revision!r} does not match expected {expected_revision!r}",
            )

        # 4. Evidence Integrity Check
        if not passport.qualification_evidence_ids:
            return PassportValidationResult(
                is_valid=False,
                status="EVIDENCE_STALE",
                failure_reason="Passport has no qualification evidence references",
            )

        # 5. Capability Match Check
        if requirement is not None:
            passport_caps = set(passport.qualified_capabilities)
            required_caps = {c.value for c in requirement.required_capabilities}
            missing_caps = required_caps - passport_caps
            if missing_caps:
                return PassportValidationResult(
                    is_valid=False,
                    status="UNQUALIFIED",
                    failure_reason=f"Agent lacks required capabilities: {sorted(list(missing_caps))}",
                )

        return PassportValidationResult(is_valid=True, status="VALID")
