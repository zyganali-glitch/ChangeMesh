"""ChangeMesh orchestrator package.

Provides saga state persistence, multi-agent coordination, and recovery.
"""

from src.orchestrator.orchestrator_saga import (
    BoundedCriterionConditionSpec,
    ChangeSagaOrchestrator,
    SagaExecutionResult,
    build_standard_demo_registry,
    sanitize_secrets_in_text,
    validate_criterion_condition_semantics,
    validate_supported_change_intent,
)
from src.orchestrator.state_repository import (
    ApprovalRecord,
    ChangeRecord,
    CheckpointRecord,
    DocumentNotFoundError,
    EvidenceRefRecord,
    IdempotencyReservationRecord,
    OptimisticConcurrencyError,
    PassportRecord,
    PersistenceSchemaError,
    SagaStateRepository,
    TaskRecord,
    TenantIsolationError,
    TenantRecord,
)

__all__ = [
    "OptimisticConcurrencyError",
    "DocumentNotFoundError",
    "TenantIsolationError",
    "PersistenceSchemaError",
    "TenantRecord",
    "ChangeRecord",
    "TaskRecord",
    "CheckpointRecord",
    "IdempotencyReservationRecord",
    "EvidenceRefRecord",
    "ApprovalRecord",
    "PassportRecord",
    "SagaStateRepository",
    "ChangeSagaOrchestrator",
    "SagaExecutionResult",
    "build_standard_demo_registry",
    "sanitize_secrets_in_text",
    "validate_supported_change_intent",
    "BoundedCriterionConditionSpec",
    "validate_criterion_condition_semantics",
]
