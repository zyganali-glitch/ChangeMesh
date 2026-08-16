"""ChangeMesh qualification evidence verifier and evidence registry.

P-12.02 & P-12.03: Enforces proof-carrying CapabilityPassport issuance by strictly
verifying that qualification evidence exists, has a valid cryptographic digest,
matches the exact agent revision, has passed the required scenario evaluation,
is not stale/expired/revoked, and does not exceed data classification limits.
Self-attestation from arbitrary strings is strictly forbidden.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.conventions import UtcDateTime, is_valid_sha256_digest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import (
    EvidenceProducerKind,
    EvidenceState,
    ExecutionEvidenceMode,
)

CANONICAL_SCHEMA_VERSION = "1.0.0"


class QualificationEvidenceVerificationError(Exception):
    """Raised when evidence verification fails for passport issuance or validation."""

    def __init__(self, message: str, evidence_id: str = "", status: str = "FAILED") -> None:
        super().__init__(message)
        self.evidence_id = evidence_id
        self.status = status


class QualificationEvidenceRecord(BaseModel):
    """Immutable evidence record certifying an agent revision's capability qualification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    evidence_id: str
    agent_id: str
    agent_revision: str
    qualified_capability: str
    scenario_id: str
    passed: bool
    evidence_state: EvidenceState
    evidence_mode: ExecutionEvidenceMode
    producer_kind: EvidenceProducerKind = EvidenceProducerKind.SIMULATION
    evidence_digest: str

    permitted_data_classification: DataClassLevel = DataClassLevel.RESTRICTED
    collected_at: UtcDateTime
    expires_at: UtcDateTime
    is_revoked: bool = False
    revocation_reason: Optional[str] = None

    @field_validator(
        "evidence_id", "agent_id", "agent_revision", "qualified_capability", "scenario_id"
    )
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("evidence_digest")
    @classmethod
    def _validate_digest(cls, v: str) -> str:
        if not is_valid_sha256_digest(v):
            raise ValueError(
                f"evidence_digest must be a valid 64-char hex SHA-256 digest, got {v!r}"
            )
        return v


class EvidenceVerificationResult(BaseModel):
    """Result of evaluating a qualification evidence set for passport issuance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool
    status: str
    verified_capabilities: Tuple[str, ...] = ()
    failure_reason: Optional[str] = None
    evaluated_evidence_ids: Tuple[str, ...] = ()


class QualificationEvidenceRegistry:
    """Thread-safe registry for qualification evidence records."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, QualificationEvidenceRecord] = {}

    def register_evidence(self, record: QualificationEvidenceRecord) -> QualificationEvidenceRecord:
        with self._lock:
            self._records[record.evidence_id] = record
            return record

    def get_evidence(self, evidence_id: str) -> Optional[QualificationEvidenceRecord]:
        with self._lock:
            return self._records.get(evidence_id)

    def revoke_evidence(
        self, evidence_id: str, reason: str, revoked_at: Optional[datetime] = None
    ) -> QualificationEvidenceRecord:
        with self._lock:
            existing = self._records.get(evidence_id)
            if existing is None:
                raise QualificationEvidenceVerificationError(
                    f"Evidence {evidence_id!r} not found for revocation",
                    evidence_id=evidence_id,
                    status="EVIDENCE_MISSING",
                )
            revoked = existing.model_copy(update={"is_revoked": True, "revocation_reason": reason})
            self._records[evidence_id] = revoked
            return revoked


class QualificationEvidenceVerifier:
    """Verifies that evidence records satisfy capability qualification requirements."""

    def __init__(self, registry: Optional[QualificationEvidenceRegistry] = None) -> None:
        self._registry = registry or QualificationEvidenceRegistry()

    @property
    def registry(self) -> QualificationEvidenceRegistry:
        return self._registry

    def verify_evidence_bundle(
        self,
        evidence_ids: Sequence[str],
        expected_agent_id: str,
        expected_agent_revision: str,
        required_capabilities: Sequence[str] = (),
        now: Optional[datetime] = None,
    ) -> EvidenceVerificationResult:
        """Verify that all evidence IDs exist, match revision, passed, and are fresh."""
        if now is None:
            now = datetime.now(timezone.utc)

        if not evidence_ids:
            return EvidenceVerificationResult(
                is_valid=False,
                status="EVIDENCE_MISSING",
                failure_reason="No evidence IDs provided (self-attestation forbidden)",
                evaluated_evidence_ids=(),
            )

        verified_caps: list[str] = []

        for ev_id in evidence_ids:
            record = self._registry.get_evidence(ev_id)
            if record is None:
                return EvidenceVerificationResult(
                    is_valid=False,
                    status="EVIDENCE_MISSING",
                    failure_reason=f"Evidence {ev_id!r} does not exist in registry",
                    evaluated_evidence_ids=tuple(evidence_ids),
                )

            # 1. Check revision match
            if (
                record.agent_id != expected_agent_id
                or record.agent_revision != expected_agent_revision
            ):
                return EvidenceVerificationResult(
                    is_valid=False,
                    status="REVISION_MISMATCH",
                    failure_reason=(
                        f"Evidence {ev_id} belongs to agent "
                        f"{record.agent_id}@{record.agent_revision}, "
                        f"expected {expected_agent_id}@{expected_agent_revision}"
                    ),
                    evaluated_evidence_ids=tuple(evidence_ids),
                )

            # 2. Check digest validity
            if not is_valid_sha256_digest(record.evidence_digest):
                return EvidenceVerificationResult(
                    is_valid=False,
                    status="INVALID_DIGEST",
                    failure_reason=f"Evidence {ev_id} has invalid digest",
                    evaluated_evidence_ids=tuple(evidence_ids),
                )

            # 3. Check revocation
            if record.is_revoked:
                return EvidenceVerificationResult(
                    is_valid=False,
                    status="EVIDENCE_REVOKED",
                    failure_reason=(
                        f"Evidence {ev_id} is revoked: "
                        f"{record.revocation_reason or 'unspecified reason'}"
                    ),
                    evaluated_evidence_ids=tuple(evidence_ids),
                )

            # 4. Check expiration
            if record.expires_at <= now:
                return EvidenceVerificationResult(
                    is_valid=False,
                    status="EVIDENCE_EXPIRED",
                    failure_reason=f"Evidence {ev_id} expired at {record.expires_at.isoformat()}",
                    evaluated_evidence_ids=tuple(evidence_ids),
                )

            # 5. Check outcome
            if not record.passed or record.evidence_state == EvidenceState.FAIL:
                return EvidenceVerificationResult(
                    is_valid=False,
                    status="QUALIFICATION_FAILED",
                    failure_reason=f"Evidence {ev_id} indicates failed scenario qualification",
                    evaluated_evidence_ids=tuple(evidence_ids),
                )

            verified_caps.append(record.qualified_capability)

        # Check that all required capabilities are covered
        missing = set(required_capabilities) - set(verified_caps)
        if missing:
            missing_sorted = sorted(list(missing))
            return EvidenceVerificationResult(
                is_valid=False,
                status="UNQUALIFIED_CAPABILITY",
                failure_reason=f"Missing qualification proof for: {missing_sorted}",
                verified_capabilities=tuple(verified_caps),
                evaluated_evidence_ids=tuple(evidence_ids),
            )

        return EvidenceVerificationResult(
            is_valid=True,
            status="VERIFIED",
            verified_capabilities=tuple(sorted(set(verified_caps))),
            evaluated_evidence_ids=tuple(evidence_ids),
        )
