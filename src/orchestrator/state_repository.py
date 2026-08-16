"""ChangeMesh saga state repository contracts and data models.

P-10.02: Provider-neutral durable persistence models, exceptions, and
repository protocol.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.contracts.autonomy import AutonomyClass
from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.conventions import (
    SECRET_KEY_PATTERNS,
    UtcDateTime,
    is_valid_sha256_digest,
)
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import (
    EvidenceProducerKind,
    EvidenceState,
    ExecutionEvidenceMode,
)

TENANT_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")
CANONICAL_SCHEMA_VERSION = "1.0.0"


class OptimisticConcurrencyError(Exception):
    """Raised when an update encounters a version mismatch (stale expected_version)."""

    def __init__(
        self,
        message: str,
        document_path: str = "",
        expected_version: int = 0,
        actual_version: int = 0,
    ) -> None:
        super().__init__(message)
        self.document_path = document_path
        self.expected_version = expected_version
        self.actual_version = actual_version


class DocumentNotFoundError(Exception):
    """Raised when a requested document does not exist."""

    def __init__(self, message: str, document_path: str = "") -> None:
        super().__init__(message)
        self.document_path = document_path


class TenantIsolationError(ValueError):
    """Raised when a cross-tenant operation or malformed tenant ID is detected."""

    pass


class PersistenceSchemaError(ValueError):
    """Raised when a document violates persistence schema invariants."""

    pass


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format strictly before any database interaction."""
    if not tenant_id or not isinstance(tenant_id, str) or not TENANT_ID_REGEX.match(tenant_id):
        raise TenantIsolationError(
            f"Invalid tenant_id {tenant_id!r}: must match regex ^[a-zA-Z0-9_-]{{3,64}}$"
        )
    return tenant_id


def scan_for_secrets(data: Any, path: str = "") -> None:
    """Recursively scan data for secret field names or plain text tokens to fail closed."""
    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(pattern in k_lower for pattern in SECRET_KEY_PATTERNS):
                raise PersistenceSchemaError(
                    f"Prohibited secret field {k!r} at {path or 'root'}; "
                    f"credentials must never be persisted."
                )

            scan_for_secrets(v, f"{path}.{k}" if path else str(k))
    elif isinstance(data, (list, tuple)):
        for i, item in enumerate(data):
            scan_for_secrets(item, f"{path}[{i}]")
    elif isinstance(data, str):
        # Basic check for raw private key headers or bearer tokens
        if "-----BEGIN" in data and "PRIVATE KEY" in data:
            raise PersistenceSchemaError(
                f"Prohibited private key detected at {path}; credentials must never be persisted."
            )


# ============================================================================
# Document Records
# ============================================================================


class TenantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    TEARDOWN_PENDING = "TEARDOWN_PENDING"


class TenantRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    data_classification_limit: DataClassLevel = DataClassLevel.RESTRICTED
    version: int = 1
    created_at: UtcDateTime
    updated_at: UtcDateTime
    ttl_expires_at: Optional[UtcDateTime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be blank")
        return v


class ChangeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    correlation_id: str
    title: str
    description: str
    target_systems: Tuple[str, ...]
    data_classification: DataClassLevel
    requested_by: str
    requested_at: UtcDateTime
    state: ChangeState = ChangeState.RECEIVED
    state_updated_at: UtcDateTime
    state_reason: Optional[str] = None
    assigned_orchestrator_revision: Optional[str] = None
    autonomy_class: Optional[AutonomyClass] = None
    active_checkpoint_id: Optional[str] = None
    memory_refs: Tuple[str, ...] = ()
    evidence_summary: Dict[str, int] = Field(
        default_factory=lambda: {"pass": 0, "fail": 0, "simulated": 0, "blocked": 0}
    )
    version: int = 1
    created_at: UtcDateTime
    updated_at: UtcDateTime
    ttl_expires_at: Optional[UtcDateTime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator("change_id", "correlation_id", "title", "description", "requested_by")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("memory_refs", "target_systems")
    @classmethod
    def _validate_tuples(cls, v: Tuple[str, ...], info) -> Tuple[str, ...]:
        for item in v:
            if not item or not item.strip():
                raise ValueError(f"{info.field_name} elements must not be blank")
        return v


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPENSATED = "COMPENSATED"


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    task_id: str
    sequence_number: int
    agent_id: str
    agent_role: str
    agent_revision: str
    action_class: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[UtcDateTime] = None
    completed_at: Optional[UtcDateTime] = None
    output_summary: Optional[str] = None
    artifact_hashes: Tuple[Dict[str, str], ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    error_classification: Optional[str] = None
    error_message_sanitized: Optional[str] = None
    version: int = 1
    created_at: UtcDateTime
    updated_at: UtcDateTime
    ttl_expires_at: Optional[UtcDateTime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator(
        "change_id", "task_id", "agent_id", "agent_role", "agent_revision", "action_class"
    )
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class CheckpointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    checkpoint_id: str
    sequence_number: int
    lifecycle_state_at_checkpoint: ChangeState
    completed_task_ids: Tuple[str, ...] = ()
    pending_task_ids: Tuple[str, ...] = ()
    compensation_step_ids: Tuple[str, ...] = ()
    checkpoint_digest: str
    created_at: UtcDateTime
    ttl_expires_at: Optional[UtcDateTime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator("change_id", "checkpoint_id")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("checkpoint_digest")
    @classmethod
    def _validate_digest(cls, v: str) -> str:
        if not is_valid_sha256_digest(v):
            raise ValueError(
                f"checkpoint_digest must be a valid 64-char hex SHA-256 digest, got {v!r}"
            )
        return v


class IdempotencyReservationStatus(str, Enum):
    RESERVED = "RESERVED"
    COMMITTED = "COMMITTED"
    RELEASED = "RELEASED"


class IdempotencyReservationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    reservation_id: str
    idempotency_key: str
    action_type: str
    payload_digest: str
    target_system: Optional[str] = None
    scope: Optional[str] = None
    caller_revision: Optional[str] = None
    status: IdempotencyReservationStatus = IdempotencyReservationStatus.RESERVED
    reserved_at: UtcDateTime
    expires_at: UtcDateTime
    result_digest: Optional[str] = None
    receipt_status: Optional[str] = None
    version: int = 1
    ttl_expires_at: Optional[UtcDateTime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator(
        "change_id",
        "reservation_id",
        "idempotency_key",
        "action_type",
        "payload_digest",
    )
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("payload_digest")
    @classmethod
    def _validate_payload_digest(cls, v: str) -> str:
        if not is_valid_sha256_digest(v):
            raise ValueError(
                f"payload_digest must be a valid 64-char hex SHA-256 digest, got {v!r}"
            )
        return v


class EvidenceRefRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    evidence_id: str
    subject: str
    state: EvidenceState
    collection_mode: ExecutionEvidenceMode
    producer_kind: EvidenceProducerKind
    agent_id: Optional[str] = None
    agent_revision: Optional[str] = None
    artifact_digests: Tuple[str, ...] = ()
    trace_id: Optional[str] = None
    collected_at: UtcDateTime
    created_at: UtcDateTime
    ttl_expires_at: Optional[UtcDateTime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator("change_id", "evidence_id", "subject")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class ApprovalResolutionStatus(str, Enum):
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    card_id: str
    authority_slot_ref: str
    decision_question: str
    decision_options: Tuple[str, ...]
    policy_reason: str
    action_scope: str
    completed_work_summary: str
    rehearsed_work_summary: str
    remaining_decision_summary: str
    evidence_refs: Tuple[str, ...] = ()
    card_created_at: UtcDateTime
    resolution_status: ApprovalResolutionStatus = ApprovalResolutionStatus.PENDING
    selected_option: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[UtcDateTime] = None
    resolution_receipt_digest: Optional[str] = None
    version: int = 1
    created_at: UtcDateTime
    updated_at: UtcDateTime
    ttl_expires_at: Optional[UtcDateTime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator(
        "change_id",
        "card_id",
        "authority_slot_ref",
        "decision_question",
        "policy_reason",
        "action_scope",
    )
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("decision_options")
    @classmethod
    def _validate_opts(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        if len(v) < 2:
            raise ValueError("decision_options must have at least 2 options")
        if len(set(v)) != len(v):
            raise ValueError("decision_options must not contain duplicates")
        return v


class PassportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
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
    version: int = 1
    created_at: UtcDateTime
    updated_at: UtcDateTime
    ttl_expires_at: Optional[UtcDateTime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)

    @field_validator("passport_id", "agent_id", "agent_revision", "issuer")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("qualified_capabilities", "qualification_evidence_ids")
    @classmethod
    def _not_empty_tuple(cls, v: Tuple[str, ...], info) -> Tuple[str, ...]:
        if not v:
            raise ValueError(f"{info.field_name} must not be empty")
        for item in v:
            if not item or not item.strip():
                raise ValueError(f"{info.field_name} elements must not be blank")
        return v


# ============================================================================
# Repository Protocol
# ============================================================================


class SagaStateRepository(ABC):
    """Provider-neutral abstract repository interface for ChangeMesh durable saga state."""

    @abstractmethod
    def create_tenant(self, tenant: TenantRecord) -> TenantRecord:
        """Persist a new tenant record."""
        pass

    @abstractmethod
    def get_tenant(self, tenant_id: str) -> Optional[TenantRecord]:
        """Fetch tenant record by ID."""
        pass

    @abstractmethod
    def create_change(self, tenant_id: str, change: ChangeRecord) -> ChangeRecord:
        """Create a new change record under /tenants/{tenant_id}/changes/{change_id}."""
        pass

    @abstractmethod
    def get_change(self, tenant_id: str, change_id: str) -> Optional[ChangeRecord]:
        """Fetch change record by tenant and change ID."""
        pass

    @abstractmethod
    def update_change(
        self, tenant_id: str, change: ChangeRecord, expected_version: int
    ) -> ChangeRecord:
        """Update change record with atomic compare-and-set version check."""
        pass

    @abstractmethod
    def list_changes(
        self, tenant_id: str, state: Optional[ChangeState] = None
    ) -> List[ChangeRecord]:
        """List changes for a tenant, optionally filtered by state."""
        pass

    @abstractmethod
    def create_task(self, tenant_id: str, change_id: str, task: TaskRecord) -> TaskRecord:
        """Create a task document under /tenants/{tenant_id}/changes/{change_id}/tasks/{task_id}."""
        pass

    @abstractmethod
    def get_task(self, tenant_id: str, change_id: str, task_id: str) -> Optional[TaskRecord]:
        """Fetch a specific task."""
        pass

    @abstractmethod
    def list_tasks(self, tenant_id: str, change_id: str) -> List[TaskRecord]:
        """Enumerate tasks for a change ordered by sequence_number ASC."""
        pass

    @abstractmethod
    def update_task(
        self, tenant_id: str, change_id: str, task: TaskRecord, expected_version: int
    ) -> TaskRecord:
        """Update task with atomic compare-and-set version check."""
        pass

    @abstractmethod
    def create_checkpoint(
        self, tenant_id: str, change_id: str, checkpoint: CheckpointRecord
    ) -> CheckpointRecord:
        """Persist a new checkpoint."""
        pass

    @abstractmethod
    def get_checkpoint(
        self, tenant_id: str, change_id: str, checkpoint_id: str
    ) -> Optional[CheckpointRecord]:
        """Fetch a specific checkpoint."""
        pass

    @abstractmethod
    def list_checkpoints(self, tenant_id: str, change_id: str) -> List[CheckpointRecord]:
        """List checkpoints ordered by sequence_number DESC."""
        pass

    @abstractmethod
    def get_latest_checkpoint(self, tenant_id: str, change_id: str) -> Optional[CheckpointRecord]:
        """Fetch the most recent checkpoint by sequence_number."""
        pass

    @abstractmethod
    def create_evidence_ref(
        self, tenant_id: str, change_id: str, ref: EvidenceRefRecord
    ) -> EvidenceRefRecord:
        """Persist an evidence reference."""
        pass

    @abstractmethod
    def get_evidence_ref(
        self, tenant_id: str, change_id: str, evidence_id: str
    ) -> Optional[EvidenceRefRecord]:
        """Fetch an evidence reference."""
        pass

    @abstractmethod
    def list_evidence_refs(self, tenant_id: str, change_id: str) -> List[EvidenceRefRecord]:
        """List all evidence references for a change."""
        pass

    @abstractmethod
    def create_approval(
        self, tenant_id: str, change_id: str, approval: ApprovalRecord
    ) -> ApprovalRecord:
        """Persist an approval metadata record."""
        pass

    @abstractmethod
    def get_approval(
        self, tenant_id: str, change_id: str, card_id: str
    ) -> Optional[ApprovalRecord]:
        """Fetch an approval metadata record."""
        pass

    @abstractmethod
    def list_approvals(
        self, tenant_id: str, change_id: str, status: Optional[ApprovalResolutionStatus] = None
    ) -> List[ApprovalRecord]:
        """List approvals for a change, optionally filtered by status."""
        pass

    @abstractmethod
    def update_approval(
        self, tenant_id: str, change_id: str, approval: ApprovalRecord, expected_version: int
    ) -> ApprovalRecord:
        """Update approval with atomic compare-and-set version check."""
        pass

    @abstractmethod
    def create_passport(self, tenant_id: str, passport: PassportRecord) -> PassportRecord:
        """Persist a capability passport under /tenants/{tenant_id}/passports/{passport_id}."""
        pass

    @abstractmethod
    def get_passport(self, tenant_id: str, passport_id: str) -> Optional[PassportRecord]:
        """Fetch passport by ID."""
        pass

    @abstractmethod
    def get_active_passport(
        self, tenant_id: str, agent_id: str, agent_revision: str
    ) -> Optional[PassportRecord]:
        """Fetch active (unrevoked, non-expired) passport for exact agent revision."""
        pass

    @abstractmethod
    def update_passport(
        self, tenant_id: str, passport: PassportRecord, expected_version: int
    ) -> PassportRecord:
        """Update passport with atomic compare-and-set version check."""
        pass

    @abstractmethod
    def create_idempotency_reservation(
        self, tenant_id: str, change_id: str, reservation: IdempotencyReservationRecord
    ) -> IdempotencyReservationRecord:
        """Persist an idempotency reservation under idempotency subcollection."""
        pass

    @abstractmethod
    def get_idempotency_reservation(
        self, tenant_id: str, change_id: str, reservation_id: str
    ) -> Optional[IdempotencyReservationRecord]:
        """Fetch an idempotency reservation by ID."""
        pass

    @abstractmethod
    def update_idempotency_reservation(
        self,
        tenant_id: str,
        change_id: str,
        reservation: IdempotencyReservationRecord,
        expected_version: int,
    ) -> IdempotencyReservationRecord:
        """Update an idempotency reservation with compare-and-set version check."""
        pass
