"""ChangeMesh P-09.05 Dedicated Test Suite — Causal Event Timeline.

Donor component: CCT-FLIGHT-001 (Clean-room reimplemented).

Validates:
1. Topological causal DAG ordering (causal parent precedes child even under clock skew).
2. Independent concurrent event ordering (deterministic tie-breaking).
3. Payload secret redaction on ingest.
4. JSON export and import restart continuity.
5. Deterministic tamper-protection digest hashing (sha256).
6. Zero forbidden carry-over (no Codex events, no UI styling, no Google SDK in src/evidence).
"""

from datetime import datetime, timezone

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


def test_causal_dag_ordering_overrules_clock_skew():
    """Verify parent event precedes child even if child has earlier wall-clock timestamp."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")

    # Event 1: Root event with later clock time
    env1 = _make_envelope(
        event_id="evt-1-root",
        causation_id=None,
        timestamp=datetime(2026, 8, 16, 12, 0, 10, tzinfo=timezone.utc),
    )

    # Event 2: Child of Event 1 with EARLIER clock time due to simulated clock skew
    env2 = _make_envelope(
        event_id="evt-2-child",
        causation_id="evt-1-root",
        timestamp=datetime(2026, 8, 16, 12, 0, 5, tzinfo=timezone.utc),
    )

    # Event 3: Child of Event 2
    env3 = _make_envelope(
        event_id="evt-3-grandchild",
        causation_id="evt-2-child",
        timestamp=datetime(2026, 8, 16, 12, 0, 15, tzinfo=timezone.utc),
    )

    # Record out of order
    timeline.record_event(env3, topic_id="changemesh-agent-work-v1")
    timeline.record_event(env1, topic_id="changemesh-lifecycle-v1")
    timeline.record_event(env2, topic_id="changemesh-agent-work-v1")

    ordered = timeline.get_causally_ordered_entries()
    assert len(ordered) == 3

    # Causal order MUST be root -> child -> grandchild regardless of arrival order or timestamps
    assert ordered[0].event_id == "evt-1-root"
    assert ordered[1].event_id == "evt-2-child"
    assert ordered[2].event_id == "evt-3-grandchild"

    assert ordered[0].depth == 0
    assert ordered[1].depth == 1
    assert ordered[2].depth == 2


def test_independent_concurrent_events_deterministic_tiebreak():
    """Verify causally unlinked concurrent events are deterministically ordered."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")

    # Two sibling events with same timestamp and no causation
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
    # Tie break by event_id ascending
    assert ordered[0].event_id == "evt-sibling-a"
    assert ordered[1].event_id == "evt-sibling-b"


def test_payload_secret_redaction():
    """Verify secrets in event payloads are redacted with [REDACTED] in timeline."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")

    env = _make_envelope(event_id="evt-secret-test")
    entry = timeline.record_event(
        envelope=env,
        topic_id="changemesh-lifecycle-v1",
        payload={
            "status": "ready",
            "api_key": "super_secret_12345678",
            "password": "db_password_value",
            "safe_count": 42,
        },
    )

    assert entry.payload_summary["status"] == "ready"
    assert entry.payload_summary["safe_count"] == 42
    assert entry.payload_summary["api_key"] == "[REDACTED]"
    assert entry.payload_summary["password"] == "[REDACTED]"


def test_timeline_serialization_and_restart_continuity():
    """Verify timeline can be serialized to canonical JSON and deserialized identically."""
    timeline = CausalEventTimeline(change_id="chg-demo-001")

    env1 = _make_envelope(event_id="evt-1", causation_id=None)
    env2 = _make_envelope(event_id="evt-2", causation_id="evt-1")

    timeline.record_event(env1, topic_id="changemesh-lifecycle-v1", payload={"step": 1})
    timeline.record_event(env2, topic_id="changemesh-agent-work-v1", payload={"step": 2})

    digest_orig = timeline.compute_timeline_digest()
    data_dict = timeline.to_dict()

    assert data_dict["schema_version"] == TIMELINE_SCHEMA_VERSION
    assert data_dict["change_id"] == "chg-demo-001"
    assert data_dict["total_events"] == 2
    assert data_dict["timeline_digest"] == digest_orig

    # Reload from dictionary
    reloaded = CausalEventTimeline.from_dict(data_dict)
    assert reloaded.change_id == "chg-demo-001"
    assert reloaded.total_events == 2
    assert reloaded.compute_timeline_digest() == digest_orig

    ordered = reloaded.get_causally_ordered_entries()
    assert ordered[0].event_id == "evt-1"
    assert ordered[1].event_id == "evt-2"


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
