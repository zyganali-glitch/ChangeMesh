"""ChangeMesh orchestrator package.

Provides saga state persistence, multi-agent coordination, and recovery.
"""

from src.orchestrator.orchestrator_saga import (
    ChangeSagaOrchestrator,
    SagaExecutionResult,
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
]
