"""ChangeMesh domain contracts — provider-neutral core contract layer.

This package exposes the P-05.01 foundational schemas, the P-05.02
lifecycle contract, P-05.03 evidence contracts, and P-05.04 core
innovation contracts.  Provider-specific layers (ADK, Firestore,
Pub/Sub, GitHub, UI) depend inward on these contracts.  These
contracts never depend outward on providers.
"""

from .change_request import ChangeRequest
from .success_criterion import SuccessCriterion
from .agent_descriptor import AgentDescriptor
from .tool_descriptor import ToolDescriptor
from .data_class import DataClass, DataClassLevel

from .evidence import (
    EvidenceRecord,
    EvidenceState,
    ExecutionEvidenceMode,
    Provenance,
    TraceReference,
    ArtifactHash,
)

from .change_lifecycle import (
    ChangeState,
    IllegalTransitionError,
    CHANGE_LIFECYCLE_VERSION,
    can_transition,
    require_transition,
    is_terminal,
)

from .memory import MemoryRecord, MemoryTrustStatus
from .capability import CapabilityPassport
from .rehearsal import RehearsalScenario, RehearsalResult, FaultInjectionSpec
from .autonomy import AutonomyClass, AutonomyDecision, ApprovalCompressionCard

__all__ = [
    # P-05.01 — Foundational contracts
    "DataClassLevel",
    "DataClass",
    "SuccessCriterion",
    "ChangeRequest",
    "AgentDescriptor",
    "ToolDescriptor",
    # P-05.02 — Lifecycle
    "ChangeState",
    "IllegalTransitionError",
    "CHANGE_LIFECYCLE_VERSION",
    "can_transition",
    "require_transition",
    "is_terminal",
    # P-05.03 — Evidence contracts
    "EvidenceRecord",
    "EvidenceState",
    "ExecutionEvidenceMode",
    "Provenance",
    "TraceReference",
    "ArtifactHash",
    # P-05.04 — Core innovation contracts
    "MemoryRecord",
    "MemoryTrustStatus",
    "CapabilityPassport",
    "RehearsalScenario",
    "RehearsalResult",
    "FaultInjectionSpec",
    "AutonomyClass",
    "AutonomyDecision",
    "ApprovalCompressionCard",
]
