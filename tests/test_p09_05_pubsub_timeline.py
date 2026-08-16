"""ChangeMesh P-09.05 Dedicated Test Suite — Causal Event Timeline.

Donor component: CCT-FLIGHT-001 (Clean-room reimplemented).

Validates:
1. Out-of-order arrival != missing cause: child may be ingested before parent,
   final topological causal DAG ordering succeeds once predecessors arrive.
2. Unresolved causal predecessor fails closed at ordering/export/digest time.
3. Timestamp never converts a missing predecessor into a root.
4. Exact duplicate delivery is idempotent (same event/projection replayed).
5. Event-ID conflict fails closed (same event_id with changed content).
6. Idempotency collision fails closed (same change_id + idempotency_key, different event_id).
7. Correlation mismatch fails closed even when child is ingested first.
8. Cross-change event fails closed.
9. Causal cycles and self-causation fail closed.
10. Independent concurrent event ordering (deterministic tie-breaking).
11. Payload secret scanning fails closed on ingest.
12. Strict from_dict deserialization covering all 12 mandatory validation cases.
13. Deterministic tamper-protection digest hashing (sha256).
14. Zero forbidden carry-over (no Codex events, no UI styling, no Google SDK in src/evidence).
"""

import copy
from datetime import datetime, timezone

import pytest

from domain.contracts.agent_descriptor import AgentRevisionProvenance
from domain.contracts.event_envelope import EventEnvelope
from src.evidence.pubsub_timeline import (
    TIMELINE_SCHEMA_VERSION,
    CausalEventTimeline,
    CausalTimelineEntry,
)


def _make_envelope(
    event_id: str,
    change_id: str = "chg-demo-001",
    correlation_id: str = "corr-demo-001",
    causation_id: str | None = None,
    idempotency_key: str | None = None,
    producer_id: str = "impact_scout",
    producer_revision: str = "1.0.0",
    producer_role: str | None = "ImpactScout",
    timestamp: datetime | None = None,
) -> EventEnvelope:
    ts = timestamp or datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)
    return EventEnvelope(
        schema_version="1.0.0",
        event_id=event_id,
        change_id=change_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key or f"idem-{event_id}",
        producer_id=producer_id,
        producer_revision=producer_revision,
        producer_role=producer_role,
        timestamp=ts,
        agent_provenance=AgentRevisionProvenance(
            agent_id=producer_id,
            agent_revision=producer_revision,
            role=producer_role,
        ),
    )


def test_out_of_order_ingestion_and_causal_ordering():
    """Adversarial proof: child ingested before parent, ordering succeeds on arrival."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")

    # Event 1: Root event (timestamp 12:00:10)
    env1 = _make_envelope(
        event_id="evt-1-root",
        causation_id=None,
        timestamp=datetime(2026, 8, 16, 12, 0, 10, tzinfo=timezone.utc),
    )

    # Event 2: Child of Event 1 (timestamp 12:00:05 - earlier clock time)
    env2 = _make_envelope(
        event_id="evt-2-child",
        causation_id="evt-1-root",
        timestamp=datetime(2026, 8, 16, 12, 0, 5, tzinfo=timezone.utc),
    )

    # Event 3: Grandchild (Child of Event 2)
    env3 = _make_envelope(
        event_id="evt-3-grandchild",
        causation_id="evt-2-child",
        timestamp=datetime(2026, 8, 16, 12, 0, 15, tzinfo=timezone.utc),
    )

    # INGEST OUT OF ORDER: Grandchild first, then Child, then Root
    entry3 = timeline.record_event(env3, topic_id="changemesh-agent-work-v1")
    assert entry3.event_id == "evt-3-grandchild"

    entry2 = timeline.record_event(env2, topic_id="changemesh-agent-work-v1")
    assert entry2.event_id == "evt-2-child"

    entry1 = timeline.record_event(env1, topic_id="changemesh-lifecycle-v1")
    assert entry1.event_id == "evt-1-root"

    # Now that all predecessors have arrived, get_causally_ordered_entries must succeed
    ordered = timeline.get_causally_ordered_entries()
    assert len(ordered) == 3

    # Causal order MUST be root -> child -> grandchild
    assert ordered[0].event_id == "evt-1-root"
    assert ordered[1].event_id == "evt-2-child"
    assert ordered[2].event_id == "evt-3-grandchild"

    assert ordered[0].depth == 0
    assert ordered[1].depth == 1
    assert ordered[2].depth == 2


def test_unresolved_causal_predecessor_fails_closed():
    """Verify missing causal predecessor fails closed at projection/digest/export time."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")

    env_child = _make_envelope(event_id="evt-child", causation_id="never-arrives")
    # Ingestion succeeds and preserves unresolved reference
    timeline.record_event(env_child, topic_id="changemesh-agent-work-v1")
    assert timeline.total_events == 1

    # Projection fails closed
    with pytest.raises(ValueError, match="Unresolved causal predecessor 'never-arrives'"):
        timeline.get_causally_ordered_entries()

    # Digest fails closed
    with pytest.raises(ValueError, match="Unresolved causal predecessor 'never-arrives'"):
        timeline.compute_timeline_digest()

    # Export fails closed
    with pytest.raises(ValueError, match="Unresolved causal predecessor 'never-arrives'"):
        timeline.to_dict()


def test_exact_duplicate_is_idempotent():
    """Verify exact duplicate event replay returns existing entry without creating duplicates."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    env = _make_envelope(event_id="evt-1")

    e1 = timeline.record_event(env, topic_id="changemesh-lifecycle-v1", payload={"step": 1})
    assert timeline.total_events == 1

    # Replay exact same event
    e2 = timeline.record_event(env, topic_id="changemesh-lifecycle-v1", payload={"step": 1})
    assert timeline.total_events == 1
    assert e1 == e2


def test_event_id_content_conflict_fails_closed():
    """Verify same event_id with changed content fails closed."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    env1 = _make_envelope(event_id="evt-1", correlation_id="corr-A")
    env2 = _make_envelope(event_id="evt-1", correlation_id="corr-B")

    timeline.record_event(env1, topic_id="changemesh-lifecycle-v1")

    with pytest.raises(ValueError, match="Event ID conflict for 'evt-1'"):
        timeline.record_event(env2, topic_id="changemesh-lifecycle-v1")


def test_idempotency_collision_fails_closed():
    """Verify same (change_id, idempotency_key) with different event_id fails closed."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    env1 = _make_envelope(event_id="evt-1", idempotency_key="same-key")
    env2 = _make_envelope(event_id="evt-2", idempotency_key="same-key")

    timeline.record_event(env1, topic_id="changemesh-lifecycle-v1")

    with pytest.raises(ValueError, match="Idempotency collision for key 'same-key'"):
        timeline.record_event(env2, topic_id="changemesh-lifecycle-v1")


def test_cross_change_event_rejected():
    """Verify event with change_id != timeline.change_id is rejected."""
    timeline = CausalEventTimeline(change_id="chg-001")
    env = _make_envelope(event_id="evt-1", change_id="chg-OTHER")

    with pytest.raises(ValueError, match="does not match timeline change_id"):
        timeline.record_event(env, topic_id="changemesh-lifecycle-v1")


def test_correlation_mismatch_fails_closed_child_ingested_first():
    """Verify correlation mismatch is caught even when child was ingested before parent."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    child_env = _make_envelope(
        event_id="evt-child", causation_id="evt-parent", correlation_id="corr-child"
    )
    parent_env = _make_envelope(
        event_id="evt-parent", causation_id=None, correlation_id="corr-parent"
    )

    # Ingest child first
    timeline.record_event(child_env, topic_id="changemesh-agent-work-v1")
    # Ingest parent second
    timeline.record_event(parent_env, topic_id="changemesh-lifecycle-v1")

    with pytest.raises(ValueError, match="Correlation ID mismatch between parent"):
        timeline.get_causally_ordered_entries()


def test_causal_cycle_fails_closed():
    """Verify cyclical causation fails closed."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    env_a = _make_envelope(event_id="evt-a", causation_id="evt-b")
    env_b = _make_envelope(event_id="evt-b", causation_id="evt-a")

    timeline.record_event(env_a, topic_id="changemesh-agent-work-v1")
    timeline.record_event(env_b, topic_id="changemesh-agent-work-v1")

    with pytest.raises(ValueError, match="Causal cycle detected"):
        timeline.get_causally_ordered_entries()


def test_self_causation_cycle_fails_closed():
    """Verify self-causation fails closed in timeline ordering."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    entry = CausalTimelineEntry(
        schema_version=TIMELINE_SCHEMA_VERSION,
        event_id="evt-self",
        change_id="chg-demo-001",
        correlation_id="corr-demo-001",
        causation_id="evt-self",
        idempotency_key="idem-self",
        topic_id="changemesh-agent-work-v1",
        producer_id="impact_scout",
        producer_revision="1.0.0",
        producer_role="ImpactScout",
        timestamp=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
        depth=0,
        transport="LOCAL",
        payload_summary={},
    )
    timeline._entries_by_id["evt-self"] = entry

    with pytest.raises(ValueError, match="Causal cycle detected: event 'evt-self'"):
        timeline.get_causally_ordered_entries()


def test_independent_concurrent_events_deterministic_tiebreak():
    """Verify causally unlinked concurrent events are deterministically ordered."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")

    env_b = _make_envelope(
        event_id="evt-sibling-b",
        timestamp=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
    )
    env_a = _make_envelope(
        event_id="evt-sibling-a",
        timestamp=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
    )

    timeline.record_event(env_b, topic_id="changemesh-agent-work-v1")
    timeline.record_event(env_a, topic_id="changemesh-agent-work-v1")

    ordered = timeline.get_causally_ordered_entries()
    assert len(ordered) == 2
    assert ordered[0].event_id == "evt-sibling-a"
    assert ordered[1].event_id == "evt-sibling-b"


def test_payload_secret_fails_closed():
    """Verify secrets in event payloads fail closed at timeline ingestion."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    env = _make_envelope(event_id="evt-secret-test")

    with pytest.raises(
        ValueError,
        match="Credential material is forbidden|Prohibited credential field",
    ):
        timeline.record_event(
            envelope=env,
            topic_id="changemesh-lifecycle-v1",
            payload={
                "status": "ready",
                "api_key": "super_secret_12345678",
                "password": "db_password_value",
                "safe_count": 42,
            },
        )


def test_strict_from_dict_12_validation_cases():
    """Verify from_dict enforces all 12 mandatory strict validation rules."""
    # Build baseline valid timeline dictionary
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    env1 = _make_envelope(event_id="evt-1", causation_id=None, idempotency_key="key-1")
    env2 = _make_envelope(event_id="evt-2", causation_id="evt-1", idempotency_key="key-2")
    timeline.record_event(env1, topic_id="changemesh-lifecycle-v1", payload={"step": 1})
    timeline.record_event(env2, topic_id="changemesh-agent-work-v1", payload={"step": 2})

    valid_dict = timeline.to_dict()

    # 1. Valid round-trip
    reloaded = CausalEventTimeline.from_dict(valid_dict)
    assert reloaded.change_id == "chg-demo-001"
    assert reloaded.total_events == 2
    assert reloaded.compute_timeline_digest() == valid_dict["timeline_digest"]

    # 2. Missing digest -> reject
    d_no_digest = copy.deepcopy(valid_dict)
    d_no_digest["timeline_digest"] = ""
    with pytest.raises(ValueError, match="Missing or blank timeline_digest"):
        CausalEventTimeline.from_dict(d_no_digest)

    # 3. Wrong digest -> reject
    d_wrong_digest = copy.deepcopy(valid_dict)
    d_wrong_digest["timeline_digest"] = "a" * 64
    with pytest.raises(ValueError, match="Timeline digest mismatch"):
        CausalEventTimeline.from_dict(d_wrong_digest)

    # 4. Wrong total_events -> reject
    d_wrong_count = copy.deepcopy(valid_dict)
    d_wrong_count["total_events"] = 99
    with pytest.raises(ValueError, match="total_events mismatch"):
        CausalEventTimeline.from_dict(d_wrong_count)

    # 5. Wrong schema_version -> reject
    d_wrong_ver = copy.deepcopy(valid_dict)
    d_wrong_ver["schema_version"] = "99.0.0"
    with pytest.raises(ValueError, match="Unsupported timeline schema_version"):
        CausalEventTimeline.from_dict(d_wrong_ver)

    # 6. Unknown top-level field -> reject
    d_unknown_field = copy.deepcopy(valid_dict)
    d_unknown_field["unexpected_metadata"] = "injected"
    with pytest.raises(ValueError, match="Unknown top-level fields"):
        CausalEventTimeline.from_dict(d_unknown_field)

    # 7. Duplicate serialized event ID -> reject
    d_dup_id = copy.deepcopy(valid_dict)
    d_dup_id["events"].append(copy.deepcopy(d_dup_id["events"][0]))
    d_dup_id["total_events"] = len(d_dup_id["events"])
    with pytest.raises(ValueError, match="Duplicate serialized event_id"):
        CausalEventTimeline.from_dict(d_dup_id)

    # 8. Missing parent -> reject
    d_missing_parent = copy.deepcopy(valid_dict)
    d_missing_parent["events"][1]["causation_id"] = "non-existent-parent"
    with pytest.raises(ValueError, match="Unresolved causal predecessor"):
        CausalEventTimeline.from_dict(d_missing_parent)

    # 9. Cycle -> reject
    d_cycle = copy.deepcopy(valid_dict)
    d_cycle["events"][0]["causation_id"] = "evt-2"  # 1 causes 2, 2 causes 1
    with pytest.raises(ValueError, match="Causal cycle detected"):
        CausalEventTimeline.from_dict(d_cycle)

    # 10. Cross-change event -> reject
    d_cross_change = copy.deepcopy(valid_dict)
    d_cross_change["events"][0]["change_id"] = "chg-DIFFERENT"
    with pytest.raises(ValueError, match="Cross-change event"):
        CausalEventTimeline.from_dict(d_cross_change)

    # 11. Correlation mismatch -> reject
    d_corr_mismatch = copy.deepcopy(valid_dict)
    d_corr_mismatch["events"][1]["correlation_id"] = "corr-MISMATCH"
    with pytest.raises(ValueError, match="Correlation ID mismatch"):
        CausalEventTimeline.from_dict(d_corr_mismatch)

    # 12. Idempotency collision -> reject
    d_idem_collision = copy.deepcopy(valid_dict)
    first_key = d_idem_collision["events"][0]["idempotency_key"]
    d_idem_collision["events"][1]["idempotency_key"] = first_key
    with pytest.raises(ValueError, match="Idempotency collision for key"):
        CausalEventTimeline.from_dict(d_idem_collision)


def test_tamper_protection_digest_mismatch():
    """Verify changing any field in timeline alters the timeline digest."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")
    env1 = _make_envelope(event_id="evt-1")
    timeline.record_event(env1, topic_id="changemesh-lifecycle-v1", payload={"count": 1})

    digest_clean = timeline.compute_timeline_digest()

    # Modify payload
    timeline._entries_by_id["evt-1"] = CausalTimelineEntry(
        schema_version=TIMELINE_SCHEMA_VERSION,
        event_id="evt-1",
        change_id="chg-demo-001",
        correlation_id="corr-demo-001",
        causation_id=None,
        idempotency_key="idem-evt-1",
        topic_id="changemesh-lifecycle-v1",
        producer_id="impact_scout",
        producer_revision="1.0.0",
        producer_role="ImpactScout",
        timestamp=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
        depth=0,
        transport="LOCAL",
        payload_summary={"count": 999},  # Tampered!
    )

    digest_tampered = timeline.compute_timeline_digest()
    assert digest_clean != digest_tampered


def test_no_forbidden_donor_carryover():
    """Verify zero Codex event names, UI styles, or Google SDK imports in src/evidence."""
    from src.evidence import pubsub_timeline

    content = open(pubsub_timeline.__file__, encoding="utf-8").read()
    assert "codex" not in content.lower()
    assert "google.cloud" not in content.lower()
    assert "react" not in content.lower()
    assert "tailwind" not in content.lower()
