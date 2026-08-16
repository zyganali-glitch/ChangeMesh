"""ChangeMesh event backbone package.

Provider-neutral event abstractions, topology contracts, publisher/consumer
protocols, runtime delivery classification, retry schedules, and dead-letter handling.
"""

from events.topology import (
    CANONICAL_TOPOLOGY_VERSION,
    LogicalTopicKind,
    SubscriptionConfig,
    TopicConfig,
    TopologyConfig,
    get_canonical_topology,
    load_topology_from_json,
)

__all__ = [
    "CANONICAL_TOPOLOGY_VERSION",
    "LogicalTopicKind",
    "SubscriptionConfig",
    "TopicConfig",
    "TopologyConfig",
    "get_canonical_topology",
    "load_topology_from_json",
]
