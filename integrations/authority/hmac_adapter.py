"""ChangeMesh HMAC-SHA256 Authority Verification Adapter.

P-14.05: Outer adapter owning cryptographic HMAC verification and secret handling.
Enforces single-use replay protection for SignedAuthorityEnvelopes and materializes
credential-free VerifiedAuthorityDecision records.
Core layers and PolicyGuardianGate never hold or process the cryptographic secret.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, Set

from src.gate.token import (
    AuthorityVerificationResult,
    SignedAuthorityEnvelope,
    VerifiedAuthorityDecision,
)


class HmacAuthorityDecisionVerifier:
    """Outer integration adapter verifying HMAC-SHA256 signed authority envelopes.

    Holds the verification secret strictly within this adapter boundary.
    Produces credential-free VerifiedAuthorityDecision objects upon successful verification.
    """

    def __init__(self, verification_secret: str) -> None:
        if not verification_secret or not verification_secret.strip():
            raise ValueError(
                "verification_secret must be explicitly provided (no defaults allowed)"
            )
        self._verification_secret = verification_secret
        self._lock = threading.RLock()
        self._consumed_token_ids: Set[str] = set()

    @staticmethod
    def compute_token_signature(
        token_id: str,
        plan_hash: str,
        approver_id: str,
        authority_slot_ref: str,
        action_scope: str,
        issued_at: datetime,
        expires_at: datetime,
        nonce: str,
        secret_key: str,
    ) -> str:
        """Compute deterministic HMAC-SHA256 signature."""
        msg = (
            f"token_id={token_id}:plan_hash={plan_hash}:approver={approver_id}:"
            f"slot={authority_slot_ref}:scope={action_scope}:"
            f"issued={issued_at.isoformat()}:expires={expires_at.isoformat()}:nonce={nonce}"
        )
        return hmac.new(secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_envelope(
        self,
        envelope: SignedAuthorityEnvelope,
        expected_plan_hash: str,
        expected_slot_ref: Optional[str] = None,
        expected_scope: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> AuthorityVerificationResult:
        """Verify envelope signature, freshness, plan hash, scope, and consume it once."""
        if now is None:
            now = datetime.now(timezone.utc)

        # Disallow blank / placeholder plan hashes
        if not expected_plan_hash or not expected_plan_hash.strip():
            return AuthorityVerificationResult(
                is_valid=False,
                status="MISSING_PLAN_HASH",
                failure_reason=(
                    "Active plan hash must be explicitly provided for authority validation"
                ),
            )

        with self._lock:
            # 1. Single-use consumption check (Idempotency / Replay Prevention)
            if envelope.token_id in self._consumed_token_ids:
                return AuthorityVerificationResult(
                    is_valid=False,
                    status="TOKEN_ALREADY_CONSUMED",
                    failure_reason=(
                        f"Approval envelope {envelope.token_id} has already been consumed "
                        f"(replay prevention violation)"
                    ),
                )

            # 2. Expiration check
            if envelope.expires_at <= now:
                return AuthorityVerificationResult(
                    is_valid=False,
                    status="EXPIRED",
                    failure_reason=(
                        f"Approval envelope expired at {envelope.expires_at.isoformat()}"
                    ),
                )

            # 3. Slot match check
            if expected_slot_ref is not None and envelope.authority_slot_ref != expected_slot_ref:
                return AuthorityVerificationResult(
                    is_valid=False,
                    status="SLOT_MISMATCH",
                    failure_reason=(
                        f"Envelope authority slot {envelope.authority_slot_ref!r} "
                        f"does not match required slot {expected_slot_ref!r}"
                    ),
                )

            # 4. Scope match check
            if expected_scope is not None and envelope.action_scope != expected_scope:
                return AuthorityVerificationResult(
                    is_valid=False,
                    status="SCOPE_MISMATCH",
                    failure_reason=(
                        f"Envelope action scope {envelope.action_scope!r} "
                        f"does not match expected scope {expected_scope!r}"
                    ),
                )

            # 5. Plan Hash Matching (Stale Plan Check)
            if not hmac.compare_digest(envelope.plan_hash, expected_plan_hash):
                return AuthorityVerificationResult(
                    is_valid=False,
                    status="STALE_PLAN_HASH",
                    failure_reason=(
                        f"Envelope plan hash {envelope.plan_hash!r} "
                        f"does not match active plan hash {expected_plan_hash!r}"
                    ),
                )

            # 6. Cryptographic Signature Check
            expected_sig = self.compute_token_signature(
                token_id=envelope.token_id,
                plan_hash=envelope.plan_hash,
                approver_id=envelope.approver_id,
                authority_slot_ref=envelope.authority_slot_ref,
                action_scope=envelope.action_scope,
                issued_at=envelope.issued_at,
                expires_at=envelope.expires_at,
                nonce=envelope.nonce,
                secret_key=self._verification_secret,
            )

            if not hmac.compare_digest(envelope.signature, expected_sig):
                return AuthorityVerificationResult(
                    is_valid=False,
                    status="INVALID_SIGNATURE",
                    failure_reason=(
                        "Cryptographic signature verification failed (tampered envelope)"
                    ),
                )

            # 7. Consume envelope for single-use replay protection
            self._consumed_token_ids.add(envelope.token_id)

            # 8. Materialize credential-free VerifiedAuthorityDecision
            try:
                decision = VerifiedAuthorityDecision(
                    decision_id=f"auth-dec-{uuid.uuid4().hex[:12]}",
                    envelope_id=envelope.token_id,
                    approver_id=envelope.approver_id,
                    authority_slot_ref=envelope.authority_slot_ref,
                    plan_hash=envelope.plan_hash,
                    action_scope=envelope.action_scope,
                    issued_at=envelope.issued_at,
                    expires_at=envelope.expires_at,
                    is_revoked=False,
                    superseded_by=None,
                )
            except ValueError as e:
                return AuthorityVerificationResult(
                    is_valid=False,
                    status="INVALID_APPROVER_PROVENANCE",
                    failure_reason=str(e),
                )

            return AuthorityVerificationResult(
                is_valid=True,
                status="VALID",
                decision=decision,
            )

    def verify_and_consume(
        self,
        token: SignedAuthorityEnvelope,
        expected_plan_hash: str,
        expected_slot_ref: Optional[str] = None,
        expected_scope: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> AuthorityVerificationResult:
        """Compatibility method mapping directly to verify_envelope."""
        return self.verify_envelope(
            envelope=token,
            expected_plan_hash=expected_plan_hash,
            expected_slot_ref=expected_slot_ref,
            expected_scope=expected_scope,
            now=now,
        )


# Canonical alias
TrustedAuthorityDecisionVerifier = HmacAuthorityDecisionVerifier
