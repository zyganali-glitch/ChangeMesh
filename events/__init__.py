"""ChangeMesh event backbone package.

Provider-neutral event abstractions, topology contracts, publisher/consumer
protocols, runtime delivery classification, retry schedules, and dead-letter handling.
"""

from domain.contracts.event_envelope import EventDeliveryDisposition
from events.consumer import EventConsumer, EventConsumeResult
from events.dead_letter import (
    DEAD_LETTER_SCHEMA_VERSION,
    DeadLetterEventRecord,
    TerminalFailureHandoff,
    build_dead_letter_record,
    sanitize_error_message,
)
from events.delivery_state import InMemoryDeliveryState
from events.publisher import EventPublisher, EventPublishResult
from events.retry import (
    EventRetryPolicy,
    FailureClassification,
    RetryAttemptRecord,
    RetryExecutionResult,
    classify_failure,
    execute_with_retry,
)
from events.topology import (
    CANONICAL_TOPOLOGY_VERSION,
    LogicalTopicKind,
    SubscriptionConfig,
    TopicConfig,
    TopologyConfig,
    get_canonical_topology,
    load_topology_from_json,
)
from events.wire import WIRE_SCHEMA_VERSION, EventWireMessage, scan_payload_for_secrets

__all__ = [
    "CANONICAL_TOPOLOGY_VERSION",
    "DEAD_LETTER_SCHEMA_VERSION",
    "DeadLetterEventRecord",
    "EventConsumeResult",
    "EventConsumer",
    "EventDeliveryDisposition",
    "EventPublishResult",
    "EventPublisher",
    "EventRetryPolicy",
    "EventWireMessage",
    "FailureClassification",
    "InMemoryDeliveryState",
    "LogicalTopicKind",
    "RetryAttemptRecord",
    "RetryExecutionResult",
    "SubscriptionConfig",
    "TerminalFailureHandoff",
    "TopicConfig",
    "TopologyConfig",
    "WIRE_SCHEMA_VERSION",
    "build_dead_letter_record",
    "classify_failure",
    "execute_with_retry",
    "get_canonical_topology",
    "load_topology_from_json",
    "sanitize_error_message",
    "scan_payload_for_secrets",
]
