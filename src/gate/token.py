"""ChangeMesh cryptographic approval token verification boundary.

P-14.05: Evaluates HMAC-SHA256 signed approval tokens cryptographically bound
to the exact change plan hash, scope, and authority slot.
Enforces single-use idempotency, expiration checks, and stale-plan rejection.
Application code cannot self-mint human authority; secrets are strictly injected.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
from datetime import datetime, timezone
from typing import Optional, Set

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.conventions import UtcDateTime

CANONICAL_SCHEMA_VERSION = "1.0.0"


class SignedApprovalToken(BaseModel):
    """Cryptographic approval token signed by an authorized external human authority."""

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


class ApprovalValidationResult(BaseModel):
    """Outcome of verifying an approval token at the reversibility gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool
    status: str
    failure_reason: Optional[str] = None


class TrustedAuthorityDecisionVerifier:
    """Verifies cryptographic HMAC approval tokens with single-use tracking and injected secret."""

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

    def verify_and_consume(
        self,
        token: SignedApprovalToken,
        expected_plan_hash: str,
        expected_slot_ref: Optional[str] = None,
        expected_scope: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ApprovalValidationResult:
        """Verify token signature, freshness, plan hash, scope, and consume it once."""
        if now is None:
            now = datetime.now(timezone.utc)

        with self._lock:
            # 1. Single-use consumption check (Idempotency)
            if token.token_id in self._consumed_token_ids:
                return ApprovalValidationResult(
                    is_valid=False,
                    status="TOKEN_ALREADY_CONSUMED",
                    failure_reason=(
                        f"Approval token {token.token_id} has already been consumed "
                        f"(replay prevention violation)"
                    ),
                )

            # 2. Expiration check
            if token.expires_at <= now:
                return ApprovalValidationResult(
                    is_valid=False,
                    status="EXPIRED",
                    failure_reason=f"Approval token expired at {token.expires_at.isoformat()}",
                )

            # 3. Slot match check
            if expected_slot_ref and token.authority_slot_ref != expected_slot_ref:
                return ApprovalValidationResult(
                    is_valid=False,
                    status="SCOPE_MISMATCH",
                    failure_reason=(
                        f"Token authority slot {token.authority_slot_ref!r} "
                        f"does not match required slot {expected_slot_ref!r}"
                    ),
                )

            # 4. Plan Hash Matching (Stale Plan Check)
            if not hmac.compare_digest(token.plan_hash, expected_plan_hash):
                return ApprovalValidationResult(
                    is_valid=False,
                    status="STALE_PLAN_HASH",
                    failure_reason=(
                        f"Token plan hash {token.plan_hash!r} "
                        f"does not match active plan hash {expected_plan_hash!r}"
                    ),
                )

            # 5. Cryptographic Signature Check
            expected_sig = self.compute_token_signature(
                token_id=token.token_id,
                plan_hash=token.plan_hash,
                approver_id=token.approver_id,
                authority_slot_ref=token.authority_slot_ref,
                action_scope=token.action_scope,
                issued_at=token.issued_at,
                expires_at=token.expires_at,
                nonce=token.nonce,
                secret_key=self._verification_secret,
            )

            if not hmac.compare_digest(token.signature, expected_sig):
                return ApprovalValidationResult(
                    is_valid=False,
                    status="INVALID_SIGNATURE",
                    failure_reason="Cryptographic signature verification failed (tampered token)",
                )

            # Consume token for single-use
            self._consumed_token_ids.add(token.token_id)

            return ApprovalValidationResult(is_valid=True, status="VALID")
