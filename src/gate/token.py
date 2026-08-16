"""ChangeMesh cryptographic approval token generator and verifier.

P-14.03: Generates HMAC-SHA256 signed approval tokens cryptographically bound
to the exact change plan hash, enforcing single-use idempotency and stale-plan rejection.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.conventions import UtcDateTime

CANONICAL_SCHEMA_VERSION = "1.0.0"


class SignedApprovalToken(BaseModel):
    """Cryptographic approval token signed by an authorized human authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    token_id: str
    plan_hash: str
    approver_id: str
    authority_slot_ref: str
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
    status: (
        str  # "VALID", "INVALID_SIGNATURE", "STALE_PLAN_HASH", "EXPIRED", "TOKEN_ALREADY_CONSUMED"
    )
    failure_reason: Optional[str] = None


class ApprovalTokenManager:
    """Issues and verifies cryptographic HMAC approval tokens with single-use tracking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._consumed_token_ids: Set[str] = set()

    @staticmethod
    def compute_token_signature(
        token_id: str,
        plan_hash: str,
        approver_id: str,
        authority_slot_ref: str,
        issued_at: datetime,
        expires_at: datetime,
        nonce: str,
        secret_key: str,
    ) -> str:
        """Compute deterministic HMAC-SHA256 signature."""
        msg = (
            f"token_id={token_id}:plan_hash={plan_hash}:approver={approver_id}:"
            f"slot={authority_slot_ref}:issued={issued_at.isoformat()}:"
            f"expires={expires_at.isoformat()}:nonce={nonce}"
        )
        return hmac.new(secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

    def issue_token(
        self,
        plan_hash: str,
        approver_id: str,
        authority_slot_ref: str = "slot:lead_dba",
        secret_key: str = "demo-signing-secret-key-32chars!!",
        validity_seconds: int = 3600,
        now: Optional[datetime] = None,
    ) -> SignedApprovalToken:
        """Issue a new signed approval token."""
        if now is None:
            now = datetime.now(timezone.utc)

        token_id = f"tok-{uuid.uuid4().hex[:12]}"
        nonce = uuid.uuid4().hex
        expires_at = now + timedelta(seconds=validity_seconds)

        sig = self.compute_token_signature(
            token_id=token_id,
            plan_hash=plan_hash,
            approver_id=approver_id,
            authority_slot_ref=authority_slot_ref,
            issued_at=now,
            expires_at=expires_at,
            nonce=nonce,
            secret_key=secret_key,
        )

        return SignedApprovalToken(
            token_id=token_id,
            plan_hash=plan_hash,
            approver_id=approver_id,
            authority_slot_ref=authority_slot_ref,
            issued_at=now,
            expires_at=expires_at,
            nonce=nonce,
            signature=sig,
        )

    def verify_and_consume(
        self,
        token: SignedApprovalToken,
        expected_plan_hash: str,
        secret_key: str = "demo-signing-secret-key-32chars!!",
        now: Optional[datetime] = None,
    ) -> ApprovalValidationResult:
        """Verify token cryptographic signature, freshness, plan hash, and consume it once."""
        if now is None:
            now = datetime.now(timezone.utc)

        with self._lock:
            # 1. Single-use consumption check
            if token.token_id in self._consumed_token_ids:
                return ApprovalValidationResult(
                    is_valid=False,
                    status="TOKEN_ALREADY_CONSUMED",
                    failure_reason=f"Approval token {token.token_id} has already been consumed (idempotency violation)",
                )

            # 2. Expiration check
            if token.expires_at <= now:
                return ApprovalValidationResult(
                    is_valid=False,
                    status="EXPIRED",
                    failure_reason=f"Approval token expired at {token.expires_at.isoformat()}",
                )

            # 3. Plan Hash Matching (Stale Plan Check)
            if not hmac.compare_digest(token.plan_hash, expected_plan_hash):
                return ApprovalValidationResult(
                    is_valid=False,
                    status="STALE_PLAN_HASH",
                    failure_reason=f"Token plan hash {token.plan_hash!r} does not match active plan hash {expected_plan_hash!r}",
                )

            # 4. Cryptographic Signature Check
            expected_sig = self.compute_token_signature(
                token_id=token.token_id,
                plan_hash=token.plan_hash,
                approver_id=token.approver_id,
                authority_slot_ref=token.authority_slot_ref,
                issued_at=token.issued_at,
                expires_at=token.expires_at,
                nonce=token.nonce,
                secret_key=secret_key,
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
