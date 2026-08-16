"""ChangeMesh idempotency key and reservation manager.

P-10.03: Enforces replay protection, semantic conflict detection, and single-execution
semantics for workflow steps, branch intentions, PR intentions, approvals, passports,
and external-write intents.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.conventions import (
    canonical_json_bytes,
    is_valid_sha256_digest,
    sha256_hex,
)
from src.orchestrator.state_repository import (
    CANONICAL_SCHEMA_VERSION,
    IdempotencyReservationRecord,
    IdempotencyReservationStatus,
    PersistenceSchemaError,
    SagaStateRepository,
    validate_tenant_id,
)


class IdempotencyScope(str, Enum):
    WORKFLOW_STEP = "WORKFLOW_STEP"
    BRANCH_INTENT = "BRANCH_INTENT"
    PR_INTENT = "PR_INTENT"
    APPROVAL = "APPROVAL"
    PASSPORT = "PASSPORT"
    EXTERNAL_WRITE = "EXTERNAL_WRITE"


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a conflicting payload or scope."""

    def __init__(
        self,
        message: str,
        idempotency_key: str = "",
        existing_digest: str = "",
        incoming_digest: str = "",
    ) -> None:
        super().__init__(message)
        self.idempotency_key = idempotency_key
        self.existing_digest = existing_digest
        self.incoming_digest = incoming_digest


class IdempotencyLeaseExpiredError(Exception):
    """Raised when a commit is attempted on an expired reservation lease."""

    pass


class IdempotencyReservationOutcomeStatus(str, Enum):
    GRANTED = "GRANTED"
    EXACT_REPLAY = "EXACT_REPLAY"
    IN_PROGRESS = "IN_PROGRESS"


class IdempotencyIntent(BaseModel):
    """Canonical input tuple defining an idempotent operation intent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    scope: IdempotencyScope
    action_type: str
    target_system: str
    caller_revision: str
    payload_digest: str
    lease_duration_seconds: int = 900  # 15 minutes default

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator("change_id", "action_type", "target_system", "caller_revision")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("payload_digest")
    @classmethod
    def _validate_digest(cls, v: str) -> str:
        if not is_valid_sha256_digest(v):
            raise ValueError(
                f"payload_digest must be a valid 64-char SHA-256 hex string, got {v!r}"
            )
        return v


class IdempotencyReservationOutcome(BaseModel):
    """Result of attempting to reserve an idempotency key."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: IdempotencyReservationOutcomeStatus
    reservation: IdempotencyReservationRecord
    cached_result_digest: Optional[str] = None
    cached_receipt_status: Optional[str] = None


class IdempotencyKeyManager:
    """Manages generation, reservation, commit, and replay checking of idempotency keys."""

    @staticmethod
    def compute_canonical_idempotency_key(intent: IdempotencyIntent) -> str:
        """Derive a deterministic, safe SHA-256 idempotency key token from the intent tuple."""
        key_tuple = {
            "tenant_id": intent.tenant_id,
            "change_id": intent.change_id,
            "scope": intent.scope.value,
            "action_type": intent.action_type,
            "target_system": intent.target_system,
            "caller_revision": intent.caller_revision,
        }
        digest = sha256_hex(canonical_json_bytes(key_tuple))
        return f"idem_{intent.scope.value.lower()}_{digest[:32]}"

    @staticmethod
    def compute_reservation_doc_id(idempotency_key: str) -> str:
        """Generate a valid, non-colliding Firestore document ID for the reservation."""
        clean_key = idempotency_key.replace("/", "_").replace(".", "_")
        return f"res_{clean_key}"

    @classmethod
    def reserve_intent(
        cls,
        repo: SagaStateRepository,
        intent: IdempotencyIntent,
        now: Optional[datetime] = None,
    ) -> IdempotencyReservationOutcome:
        """Atomically reserve or check an idempotency key with strict conflict detection."""
        if now is None:
            now = datetime.now(timezone.utc)

        tid = validate_tenant_id(intent.tenant_id)
        cid = intent.change_id
        idem_key = cls.compute_canonical_idempotency_key(intent)
        res_id = cls.compute_reservation_doc_id(idem_key)

        existing = repo.get_idempotency_reservation(tid, cid, res_id)

        if existing is not None:
            # Semantic conflict check: compare payload digest and action type
            if (
                existing.payload_digest != intent.payload_digest
                or existing.action_type != intent.action_type
            ):
                raise IdempotencyConflictError(
                    f"Idempotency conflict for key {idem_key!r}: "
                    f"stored payload digest {existing.payload_digest!r} != "
                    f"incoming payload digest {intent.payload_digest!r}",
                    idempotency_key=idem_key,
                    existing_digest=existing.payload_digest,
                    incoming_digest=intent.payload_digest,
                )

            # Committed state -> EXACT_REPLAY
            if existing.status == IdempotencyReservationStatus.COMMITTED:
                return IdempotencyReservationOutcome(
                    status=IdempotencyReservationOutcomeStatus.EXACT_REPLAY,
                    reservation=existing,
                    cached_result_digest=existing.result_digest,
                    cached_receipt_status=existing.receipt_status,
                )

            # Active lease in-progress
            if existing.status == IdempotencyReservationStatus.RESERVED:
                if existing.expires_at > now:
                    return IdempotencyReservationOutcome(
                        status=IdempotencyReservationOutcomeStatus.IN_PROGRESS,
                        reservation=existing,
                    )
                else:
                    # Lease expired: re-acquire lease
                    expires_at = now + timedelta(seconds=intent.lease_duration_seconds)
                    re_acquired = existing.model_copy(
                        update={
                            "reserved_at": now,
                            "expires_at": expires_at,
                            "status": IdempotencyReservationStatus.RESERVED,
                            "payload_digest": intent.payload_digest,
                        }
                    )
                    saved = repo.update_idempotency_reservation(
                        tid, cid, re_acquired, expected_version=existing.version
                    )
                    return IdempotencyReservationOutcome(
                        status=IdempotencyReservationOutcomeStatus.GRANTED,
                        reservation=saved,
                    )

            # Released state -> re-reserve
            if existing.status == IdempotencyReservationStatus.RELEASED:
                expires_at = now + timedelta(seconds=intent.lease_duration_seconds)
                re_reserved = existing.model_copy(
                    update={
                        "reserved_at": now,
                        "expires_at": expires_at,
                        "status": IdempotencyReservationStatus.RESERVED,
                        "payload_digest": intent.payload_digest,
                        "result_digest": None,
                        "receipt_status": None,
                    }
                )
                saved = repo.update_idempotency_reservation(
                    tid, cid, re_reserved, expected_version=existing.version
                )
                return IdempotencyReservationOutcome(
                    status=IdempotencyReservationOutcomeStatus.GRANTED,
                    reservation=saved,
                )

        # Fresh reservation
        expires_at = now + timedelta(seconds=intent.lease_duration_seconds)
        new_record = IdempotencyReservationRecord(
            tenant_id=tid,
            change_id=cid,
            reservation_id=res_id,
            idempotency_key=idem_key,
            action_type=intent.action_type,
            payload_digest=intent.payload_digest,
            target_system=intent.target_system,
            scope=intent.scope.value,
            caller_revision=intent.caller_revision,
            status=IdempotencyReservationStatus.RESERVED,
            reserved_at=now,
            expires_at=expires_at,
            version=1,
        )
        try:
            saved = repo.create_idempotency_reservation(tid, cid, new_record)
            return IdempotencyReservationOutcome(
                status=IdempotencyReservationOutcomeStatus.GRANTED,
                reservation=saved,
            )
        except PersistenceSchemaError:
            # Race condition: another process created the reservation concurrently.
            # Re-read and re-evaluate to maintain strict consistency.
            return cls.reserve_intent(repo, intent, now=now)

    @classmethod
    def commit_intent(
        cls,
        repo: SagaStateRepository,
        tenant_id: str,
        change_id: str,
        reservation_id: str,
        result_digest: str,
        receipt_status: str = "APPLIED",
    ) -> IdempotencyReservationRecord:
        """Mark reservation as COMMITTED and store deterministic result digest."""
        tid = validate_tenant_id(tenant_id)
        if not is_valid_sha256_digest(result_digest):
            raise ValueError(
                f"result_digest must be a valid 64-char SHA-256 hex string, got {result_digest!r}"
            )

        existing = repo.get_idempotency_reservation(tid, change_id, reservation_id)
        if existing is None:
            raise ValueError(f"Reservation {reservation_id!r} not found for commit")

        if existing.status == IdempotencyReservationStatus.COMMITTED:
            return existing

        now = datetime.now(timezone.utc)
        if existing.expires_at < now and existing.status != IdempotencyReservationStatus.COMMITTED:
            raise IdempotencyLeaseExpiredError(
                f"Reservation lease {reservation_id!r} expired at {existing.expires_at.isoformat()}"
            )

        committed = existing.model_copy(
            update={
                "status": IdempotencyReservationStatus.COMMITTED,
                "result_digest": result_digest,
                "receipt_status": receipt_status,
            }
        )
        return repo.update_idempotency_reservation(
            tid, change_id, committed, expected_version=existing.version
        )

    @classmethod
    def release_intent(
        cls,
        repo: SagaStateRepository,
        tenant_id: str,
        change_id: str,
        reservation_id: str,
    ) -> IdempotencyReservationRecord:
        """Release a reservation on failure so subsequent attempts can re-acquire."""
        tid = validate_tenant_id(tenant_id)
        existing = repo.get_idempotency_reservation(tid, change_id, reservation_id)
        if existing is None:
            raise ValueError(f"Reservation {reservation_id!r} not found for release")

        if existing.status == IdempotencyReservationStatus.COMMITTED:
            return existing

        released = existing.model_copy(
            update={
                "status": IdempotencyReservationStatus.RELEASED,
            }
        )
        return repo.update_idempotency_reservation(
            tid, change_id, released, expected_version=existing.version
        )
