"""ChangeMesh P-09.01 Dedicated Test Suite — Pub/Sub Topic and Subscription Topology.

Validates:
1. Canonical topic/subscription topology creation and versioning.
2. Complete coverage of logical flows (lifecycle, agent work, approval, evidence, retry, DL).
3. Complete 16-state ChangeState lifecycle route mapping without missing or unknown states.
4. Topic/subscription name uniqueness, formatting, and subscription-topic linkage.
5. Dead-letter policy integrity and cycle prevention.
6. Retry policy backoff validity.
7. Rejection of invalid configs (blanks, malformed names, cycles, undeclared topics).
8. Deterministic serialization and deserialization from JSON manifest.
9. Credential and secret absence in topology configuration.
10. Provider neutrality (no google.cloud.pubsub imports in events package).
"""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.contracts.change_lifecycle import ChangeState
from events.topology import (
    CANONICAL_TOPOLOGY_VERSION,
    DeadLetterPolicyConfig,
    LogicalTopicKind,
    RetryPolicyConfig,
    SubscriptionConfig,
    TopicConfig,
    TopologyConfig,
    get_canonical_topology,
    load_topology_from_json,
)


def test_canonical_topology_version_and_structure():
    """Verify canonical topology has explicit version and non-empty collections."""
    topo = get_canonical_topology()
    assert topo.schema_version == CANONICAL_TOPOLOGY_VERSION
    assert len(topo.topics) == 6
    assert len(topo.subscriptions) == 6
    assert len(topo.lifecycle_routes) == 16


def test_all_logical_topic_kinds_declared():
    """Verify all 6 LogicalTopicKind enum values exist in canonical topics."""
    topo = get_canonical_topology()
    declared_kinds = {t.logical_kind for t in topo.topics}
    for kind in LogicalTopicKind:
        assert kind in declared_kinds, f"Missing LogicalTopicKind: {kind}"


def test_topic_names_unique_and_valid():
    """Verify topic names are unique and match resource naming conventions."""
    topo = get_canonical_topology()
    topic_ids = [t.topic_id for t in topo.topics]
    assert len(topic_ids) == len(set(topic_ids))
    for t_id in topic_ids:
        assert t_id.startswith("changemesh-")
        assert t_id.endswith("-v1")


def test_subscription_names_unique_and_linked_to_declared_topics():
    """Verify subscription IDs are unique and reference only declared topic IDs."""
    topo = get_canonical_topology()
    declared_topics = {t.topic_id for t in topo.topics}
    sub_ids = [s.subscription_id for s in topo.subscriptions]
    assert len(sub_ids) == len(set(sub_ids))

    for s in topo.subscriptions:
        assert s.topic_id in declared_topics, (
            f"Subscription {s.subscription_id} references undeclared topic {s.topic_id}"
        )
        assert 10 <= s.ack_deadline_seconds <= 600


def test_dead_letter_policy_integrity_and_cycle_prevention():
    """Verify dead-letter policies point to dead_letter topic and dead-letter sub has no cycle."""
    topo = get_canonical_topology()
    dl_topic = topo.get_topic_by_kind(LogicalTopicKind.DEAD_LETTER)
    assert dl_topic is not None

    for sub in topo.subscriptions:
        if sub.logical_kind == LogicalTopicKind.DEAD_LETTER:
            # Dead letter subscription must NOT dead-letter to itself
            assert sub.dead_letter_policy is None
        else:
            assert sub.dead_letter_policy is not None
            assert sub.dead_letter_policy.dead_letter_topic == dl_topic.topic_id
            assert sub.dead_letter_policy.max_delivery_attempts == 5


def test_retry_policy_bounds():
    """Verify retry policies have positive and ordered backoff values."""
    topo = get_canonical_topology()
    for sub in topo.subscriptions:
        if sub.retry_policy is not None:
            assert sub.retry_policy.minimum_backoff_seconds > 0
            assert (
                sub.retry_policy.maximum_backoff_seconds >= sub.retry_policy.minimum_backoff_seconds
            )


def test_all_16_change_states_mapped():
    """Verify every canonical ChangeState enum value is mapped exactly once in lifecycle_routes."""
    topo = get_canonical_topology()
    routed_states = {r.state for r in topo.lifecycle_routes}
    all_states = set(ChangeState)
    assert routed_states == all_states, f"Mismatch in mapped states: {all_states ^ routed_states}"

    declared_topics = {t.topic_id for t in topo.topics}
    for r in topo.lifecycle_routes:
        assert r.primary_topic_id in declared_topics
        if r.secondary_topic_id is not None:
            assert r.secondary_topic_id in declared_topics


def test_topology_lookup_helpers():
    """Verify get_topic, get_subscription, and get_route_for_state helpers."""
    topo = get_canonical_topology()
    t = topo.get_topic("changemesh-lifecycle-v1")
    assert t is not None
    assert t.logical_kind == LogicalTopicKind.CHANGE_LIFECYCLE

    assert topo.get_topic("nonexistent") is None

    s = topo.get_subscription("changemesh-lifecycle-sub-v1")
    assert s is not None
    assert s.topic_id == "changemesh-lifecycle-v1"
    assert topo.get_subscription("nonexistent") is None

    r = topo.get_route_for_state(ChangeState.REHEARSING)
    assert r is not None
    assert r.primary_topic_id == "changemesh-lifecycle-v1"
    assert r.secondary_topic_id == "changemesh-evidence-v1"


def test_topology_manifest_json_file_sync():
    """Verify events/topology_manifest.json matches get_canonical_topology()."""
    manifest_path = Path(__file__).resolve().parent.parent / "events" / "topology_manifest.json"
    assert manifest_path.exists(), "topology_manifest.json does not exist"
    content = manifest_path.read_text(encoding="utf-8")
    loaded = load_topology_from_json(content)
    canonical = get_canonical_topology()
    assert loaded == canonical


def test_rejection_duplicate_topics():
    """Verify validation fails if duplicate topic IDs are supplied."""
    canonical = get_canonical_topology()
    dup_topics = list(canonical.topics) + [canonical.topics[0]]
    with pytest.raises(ValidationError, match="Duplicate topic_id declared"):
        TopologyConfig(
            schema_version=canonical.schema_version,
            topics=dup_topics,
            subscriptions=canonical.subscriptions,
            lifecycle_routes=canonical.lifecycle_routes,
        )


def test_rejection_undeclared_topic_in_subscription():
    """Verify validation fails if a subscription references an undeclared topic."""
    canonical = get_canonical_topology()
    bad_sub = SubscriptionConfig(
        subscription_id="changemesh-orphan-sub-v1",
        topic_id="changemesh-unknown-topic-v1",
        logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
        description="Bad sub",
    )
    with pytest.raises(ValidationError, match="points to undeclared topic"):
        TopologyConfig(
            schema_version=canonical.schema_version,
            topics=canonical.topics,
            subscriptions=list(canonical.subscriptions) + [bad_sub],
            lifecycle_routes=canonical.lifecycle_routes,
        )


def test_rejection_dead_letter_cycle():
    """Verify validation fails if dead-letter sub sets dead-letter policy on its own topic."""
    canonical = get_canonical_topology()
    bad_sub = SubscriptionConfig(
        subscription_id="changemesh-bad-dl-sub-v1",
        topic_id="changemesh-dead-letter-v1",
        logical_kind=LogicalTopicKind.DEAD_LETTER,
        description="Cyclic dead letter sub",
        dead_letter_policy=DeadLetterPolicyConfig(
            dead_letter_topic="changemesh-dead-letter-v1",
            max_delivery_attempts=5,
        ),
    )
    with pytest.raises(ValidationError, match="Dead-letter cycle detected"):
        TopologyConfig(
            schema_version=canonical.schema_version,
            topics=canonical.topics,
            subscriptions=[
                s
                for s in canonical.subscriptions
                if s.subscription_id != "changemesh-dead-letter-sub-v1"
            ]
            + [bad_sub],
            lifecycle_routes=canonical.lifecycle_routes,
        )


def test_rejection_missing_change_state_route():
    """Verify validation fails if any ChangeState is missing from routes."""
    canonical = get_canonical_topology()
    incomplete_routes = [r for r in canonical.lifecycle_routes if r.state != ChangeState.CANCELLED]
    with pytest.raises(ValidationError, match="Topology lifecycle routes missing ChangeStates"):
        TopologyConfig(
            schema_version=canonical.schema_version,
            topics=canonical.topics,
            subscriptions=canonical.subscriptions,
            lifecycle_routes=incomplete_routes,
        )


def test_rejection_invalid_retry_backoff():
    """Verify RetryPolicyConfig rejects min > max or non-positive values."""
    with pytest.raises(ValidationError, match="cannot exceed maximum_backoff_seconds"):
        RetryPolicyConfig(minimum_backoff_seconds=10.0, maximum_backoff_seconds=5.0)

    with pytest.raises(ValidationError, match="strictly positive"):
        RetryPolicyConfig(minimum_backoff_seconds=-1.0, maximum_backoff_seconds=5.0)


def test_rejection_blank_and_malformed_names():
    """Verify resource names reject blanks and non-compliant strings."""
    with pytest.raises(ValidationError, match="topic_id must not be blank"):
        TopicConfig(
            topic_id="",
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            description="blank topic",
        )

    with pytest.raises(ValidationError, match="Invalid topic_id format"):
        TopicConfig(
            topic_id="INVALID_UPPERCASE_TOPIC",
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            description="bad topic",
        )


def test_no_credentials_in_topology():
    """Verify no credential-looking tokens exist in topology config."""
    topo = get_canonical_topology()
    topo_json = topo.model_dump_json().lower()
    for forbidden in [
        "private_key",
        "client_secret",
        "bearer",
        "api_key",
        "oauth",
        "token",
        "password",
    ]:
        assert forbidden not in topo_json, (
            f"Forbidden credential token {forbidden!r} found in topology"
        )


def test_provider_neutral_import_boundary():
    """Verify events package does NOT import google.cloud.pubsub or provider SDKs."""
    import events.topology

    source_code = Path(events.topology.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source_code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("google.cloud"), f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("google.cloud"), f"Forbidden import from: {mod}"
