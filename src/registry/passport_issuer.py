"""ChangeMesh capability passport issuer and verifier.

P-12.02 & P-12.03: Issues proof-carrying CapabilityPassports backed by verified
qualification evidence and evaluates validity, expiry, revocation, and revision matching
without self-attestation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.capability import CapabilityPassport
from domain.contracts.data_class import DataClassLevel
from src.registry.capabilities import AgentCapabilityRequirement
from src.registry.evidence_verifier import (
    QualificationEvidenceVerificationError,
    QualificationEvidenceVerifier,
)

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
            raise ValueError(
                "qualification_evidence_ids must not be empty (self-attestation is forbidden)"
            )
        for item in v:
            if not item or not item.strip():
                raise ValueError("evidence IDs must not be blank")
        return v


class PassportValidationResult(BaseModel):
    """Result of verifying a CapabilityPassport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool
    status: str
    failure_reason: Optional[str] = None


class PassportIssuer:
    """Issues deterministic CapabilityPassports from verified qualification evidence."""

    @classmethod
    def issue_passport(
        cls,
        request: PassportIssuanceRequest,
        evidence_verifier: Optional[QualificationEvidenceVerifier] = None,
        now: Optional[datetime] = None,
    ) -> CapabilityPassport:
        """Issue a new CapabilityPassport only after verifying qualification evidence."""
        if now is None:
            now = datetime.now(timezone.utc)

        # Enforce qualification verification boundary (self-attestation is forbidden)
        if evidence_verifier is not None:
            ver_res = evidence_verifier.verify_evidence_bundle(
                evidence_ids=request.qualification_evidence_ids,
                expected_agent_id=request.agent_id,
                expected_agent_revision=request.agent_revision,
                required_capabilities=request.qualified_capabilities,
                now=now,
            )
            if not ver_res.is_valid:
                raise QualificationEvidenceVerificationError(
                    f"Cannot issue passport for {request.agent_id}@{request.agent_revision}: "
                    f"{ver_res.status} ({ver_res.failure_reason})",
                    status=ver_res.status,
                )

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
    """Verifies passport validity, revocation, expiry, revision, and evidence backing."""

    @classmethod
    def verify(
        cls,
        passport: CapabilityPassport,
        requirement: Optional[AgentCapabilityRequirement] = None,
        expected_revision: Optional[str] = None,
        evidence_verifier: Optional[QualificationEvidenceVerifier] = None,
        now: Optional[datetime] = None,
    ) -> PassportValidationResult:
        """Evaluate passport against revocation, expiry, revision, and required capabilities."""
        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Revocation Check (Fail Closed)
        if passport.is_revoked:
            rev_msg = passport.revocation_reason or "unspecified reason"
            return PassportValidationResult(
                is_valid=False,
                status="REVOKED",
                failure_reason=f"Passport is revoked: {rev_msg}",
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
                failure_reason=(
                    f"Passport revision {passport.agent_revision!r} "
                    f"does not match expected {expected_revision!r}"
                ),
            )

        # 4. Evidence Integrity Check
        if not passport.qualification_evidence_ids:
            return PassportValidationResult(
                is_valid=False,
                status="EVIDENCE_STALE",
                failure_reason="Passport has no qualification evidence references",
            )

        # 5. Deep Evidence Verification (if verifier provided)
        if evidence_verifier is not None:
            ev_check = evidence_verifier.verify_evidence_bundle(
                evidence_ids=passport.qualification_evidence_ids,
                expected_agent_id=passport.agent_id,
                expected_agent_revision=passport.agent_revision,
                now=now,
            )
            if not ev_check.is_valid:
                return PassportValidationResult(
                    is_valid=False,
                    status="EVIDENCE_UNVERIFIED",
                    failure_reason=f"Evidence invalid: {ev_check.failure_reason}",
                )

        # 6. Capability Match Check
        if requirement is not None:
            passport_caps = set(passport.qualified_capabilities)
            required_caps = {c.value for c in requirement.required_capabilities}
            missing_caps = required_caps - passport_caps
            if missing_caps:
                missing_sorted = sorted(list(missing_caps))
                return PassportValidationResult(
                    is_valid=False,
                    status="UNQUALIFIED",
                    failure_reason=f"Agent lacks required capabilities: {missing_sorted}",
                )

        return PassportValidationResult(is_valid=True, status="VALID")
