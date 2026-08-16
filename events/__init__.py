"""ChangeMesh event backbone package.

Provider-neutral event abstractions, topology contracts, publisher/consumer
protocols, runtime delivery classification, retry schedules, and dead-letter handling.
"""

from domain.contracts.event_envelope import EventDeliveryDisposition
from events.consumer import EventConsumer, EventConsumeResult
from events.delivery_state import InMemoryDeliveryState
from events.publisher import EventPublisher, EventPublishResult
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
    "EventConsumeResult",
    "EventConsumer",
    "EventDeliveryDisposition",
    "EventPublishResult",
    "EventPublisher",
    "EventWireMessage",
    "InMemoryDeliveryState",
    "LogicalTopicKind",
    "SubscriptionConfig",
    "TopicConfig",
    "TopologyConfig",
    "WIRE_SCHEMA_VERSION",
    "get_canonical_topology",
    "load_topology_from_json",
    "scan_payload_for_secrets",
]
