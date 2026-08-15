"""ChangeMesh domain contracts — provider-neutral core contract layer.

This package exposes the P-05.01 foundational schemas, the P-05.02
lifecycle contract, P-05.03 evidence contracts, P-05.04 core
innovation contracts, P-05.05 event envelope contract, and P-05.06
frozen machine conventions.
Provider-specific layers (ADK, Firestore, Pub/Sub, GitHub, UI) depend
inward on these contracts.  These contracts never depend outward on
providers.
"""

from .agent_descriptor import AgentDescriptor
from .autonomy import ApprovalCompressionCard, AutonomyClass, AutonomyDecision
from .capability import CapabilityPassport
from .change_lifecycle import (
    CHANGE_LIFECYCLE_VERSION,
    ChangeState,
    IllegalTransitionError,
    can_transition,
    is_terminal,
    require_transition,
)
from .change_request import ChangeRequest
from .conventions import (
    REDACTION_SENTINEL,
    SECRET_KEY_PATTERNS,
    HashAlgorithm,
    UtcDateTime,
    canonical_json_bytes,
    canonical_model_sha256,
    format_utc_timestamp,
    is_valid_sha256_digest,
    normalize_utc_datetime,
    parse_utc_timestamp,
    redact_mapping,
    sha256_hex,
)
from .data_class import DataClass, DataClassLevel
from .event_envelope import (
    EventDeliveryDisposition,
    EventEnvelope,
    classify_event_delivery,
)
from .evidence import (
    ArtifactHash,
    EvidenceRecord,
    EvidenceState,
    ExecutionEvidenceMode,
    Provenance,
    TraceReference,
)
from .memory import MemoryRecord, MemoryTrustStatus
from .rehearsal import FaultInjectionSpec, RehearsalResult, RehearsalScenario
from .success_criterion import SuccessCriterion
from .tool_descriptor import ToolDescriptor

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
    # P-05.05 — Event envelope
    "EventEnvelope",
    "EventDeliveryDisposition",
    "classify_event_delivery",
    # P-05.06 — Machine conventions
    "HashAlgorithm",
    "is_valid_sha256_digest",
    "sha256_hex",
    "normalize_utc_datetime",
    "UtcDateTime",
    "format_utc_timestamp",
    "parse_utc_timestamp",
    "REDACTION_SENTINEL",
    "SECRET_KEY_PATTERNS",
    "redact_mapping",
    "canonical_json_bytes",
    "canonical_model_sha256",
]
