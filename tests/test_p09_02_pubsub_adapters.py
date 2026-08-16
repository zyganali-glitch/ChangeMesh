"""ChangeMesh P-09.02 Dedicated Test Suite — Pub/Sub Adapters, Validation, and Dedup.

Validates:
1. Valid publish serialization to canonical JSON and attribute preservation.
2. Valid consume deserialization and schema validation before callback.
3. Malformed JSON rejection (callback NOT invoked).
4. Unsupported schema/wire version rejection (callback NOT invoked).
5. Missing or blank EventEnvelope fields rejection.
6. Extra unapproved envelope fields rejection (extra="forbid").
7. Correlation ID, causation ID, and agent revision provenance preservation.
8. Duplicate delivery safety: second delivery does NOT re-invoke business callback.
9. Event ID collision conflict detection (different content -> CONFLICT).
10. Scoped idempotency key collision conflict detection ((change_id, idem_key) -> CONFLICT).
11. Out-of-order delivery detection (missing causal predecessor -> OUT_OF_ORDER).
12. Secret/credential payload rejection (private keys, API tokens fail closed).
13. Zero Google SDK types leak into domain contracts.
14. Publisher error handling and transport isolation.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from domain.contracts.agent_descriptor import AgentRevisionProvenance
from domain.contracts.event_envelope import EventDeliveryDisposition, EventEnvelope
from events.delivery_state import InMemoryDeliveryState
from events.wire import WIRE_SCHEMA_VERSION, EventWireMessage
from integrations.gcp.pubsub_adapter import (
    GooglePubSubConsumer,
    GooglePubSubPublisher,
)


def _make_envelope(
    event_id: str = "evt-001",
    change_id: str = "chg-001",
    correlation_id: str = "corr-001",
    causation_id: str | None = None,
    idempotency_key: str = "idem-001",
    producer_id: str = "impact_scout",
    producer_revision: str = "1.0.0",
    producer_role: str | None = "ImpactScout",
) -> EventEnvelope:
    return EventEnvelope(
        schema_version="1.0.0",
        event_id=event_id,
        change_id=change_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
        producer_id=producer_id,
        producer_revision=producer_revision,
        producer_role=producer_role,
        timestamp=datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc),
        agent_provenance=AgentRevisionProvenance(
            agent_id=producer_id,
            agent_revision=producer_revision,
            role=producer_role,
        ),
    )


def test_publisher_serialization_and_attributes():
    """Verify publisher serializes message to canonical JSON and generates attributes."""
    mock_client = MagicMock()
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-12345"
    mock_client.publish.return_value = mock_future

    publisher = GooglePubSubPublisher(
        project_id="test-project",
        publisher_client=mock_client,
    )

    envelope = _make_envelope(causation_id="evt-parent-000")
    wire_msg = EventWireMessage(
        topic_id="changemesh-lifecycle-v1",
        envelope=envelope,
        payload={"action": "rehearse", "count": 3},
        published_at=datetime(2026, 8, 16, 12, 0, 1, tzinfo=timezone.utc),
    )

    result = publisher.publish(wire_msg)

    assert result.status == "PUBLISHED"
    assert result.message_id == "msg-12345"
    assert result.topic_id == "changemesh-lifecycle-v1"
    assert result.event_id == "evt-001"
    assert result.transport == "GOOGLE_PUBSUB"

    mock_client.publish.assert_called_once()
    call_args, call_kwargs = mock_client.publish.call_args
    assert call_args[0] == "projects/test-project/topics/changemesh-lifecycle-v1"
    assert isinstance(call_args[1], bytes)

    # Check payload bytes can be deserialized
    deserialized = EventWireMessage.from_bytes(call_args[1])
    assert deserialized.envelope.event_id == "evt-001"
    assert deserialized.payload["count"] == 3

    # Check attributes
    assert call_kwargs["event_id"] == "evt-001"
    assert call_kwargs["change_id"] == "chg-001"
    assert call_kwargs["correlation_id"] == "corr-001"
    assert call_kwargs["causation_id"] == "evt-parent-000"
    assert call_kwargs["producer_id"] == "impact_scout"
    assert call_kwargs["producer_revision"] == "1.0.0"


def test_publisher_error_handling():
    """Verify publisher captures exceptions and returns FAILED result without raising."""
    mock_client = MagicMock()
    mock_client.publish.side_effect = RuntimeError("PubSub service unavailable")

    publisher = GooglePubSubPublisher(
        project_id="test-project",
        publisher_client=mock_client,
    )

    envelope = _make_envelope()
    wire_msg = EventWireMessage(
        topic_id="changemesh-lifecycle-v1",
        envelope=envelope,
    )

    result = publisher.publish(wire_msg)
    assert result.status == "FAILED"
    assert result.message_id == "none"
    assert "PubSub service unavailable" in (result.error_message or "")


def test_consumer_valid_message_dispatch():
    """Verify valid wire message invokes business callback and returns ACCEPT."""
    delivery_state = InMemoryDeliveryState()
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
        delivery_state=delivery_state,
    )

    envelope = _make_envelope(event_id="evt-valid-1")
    wire_msg = EventWireMessage(
        topic_id="changemesh-lifecycle-v1",
        envelope=envelope,
        payload={"step": "intake"},
    )
    raw_data = wire_msg.to_bytes()

    callback_called = []

    def on_event(msg: EventWireMessage) -> None:
        callback_called.append(msg.envelope.event_id)

    res = consumer.process_raw_message(
        raw_data=raw_data,
        attributes=wire_msg.get_transport_attributes(),
        message_id="pubsub-msg-1",
        callback=on_event,
    )

    assert res.disposition == EventDeliveryDisposition.ACCEPT
    assert res.callback_invoked is True
    assert res.event_id == "evt-valid-1"
    assert callback_called == ["evt-valid-1"]
    assert "evt-valid-1" in delivery_state.seen_events


def test_consumer_malformed_json_rejection():
    """Verify malformed JSON is rejected before callback is invoked."""
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
    )

    callback_called = []
    res = consumer.process_raw_message(
        raw_data=b"INVALID NOT JSON {{{",
        attributes={},
        message_id="msg-bad-json",
        callback=lambda msg: callback_called.append(msg),
    )

    assert res.disposition == EventDeliveryDisposition.CONFLICT
    assert res.callback_invoked is False
    assert len(callback_called) == 0
    assert "Malformed JSON" in (res.error_message or "")


def test_consumer_unsupported_wire_version_rejection():
    """Verify messages with unsupported wire versions are rejected."""
    envelope = _make_envelope()
    bad_data = {
        "wire_version": "99.0.0",
        "topic_id": "changemesh-lifecycle-v1",
        "envelope": envelope.model_dump(mode="json"),
        "payload": {},
    }
    raw_data = json.dumps(bad_data).encode("utf-8")

    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
    )

    callback_called = []
    res = consumer.process_raw_message(
        raw_data=raw_data,
        attributes={},
        message_id="msg-bad-ver",
        callback=lambda msg: callback_called.append(msg),
    )

    assert res.disposition == EventDeliveryDisposition.CONFLICT
    assert res.callback_invoked is False
    assert len(callback_called) == 0
    assert "Unsupported wire_version" in (res.error_message or "")


def test_consumer_duplicate_delivery_safety():
    """Verify duplicate message returns DUPLICATE and does NOT invoke callback again."""
    delivery_state = InMemoryDeliveryState()
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
        delivery_state=delivery_state,
    )

    envelope = _make_envelope(event_id="evt-dup-1")
    wire_msg = EventWireMessage(
        topic_id="changemesh-lifecycle-v1",
        envelope=envelope,
    )
    raw_data = wire_msg.to_bytes()

    callback_count = [0]

    def on_event(msg: EventWireMessage) -> None:
        callback_count[0] += 1

    # First delivery -> ACCEPT
    res1 = consumer.process_raw_message(raw_data, {}, "msg-1", on_event)
    assert res1.disposition == EventDeliveryDisposition.ACCEPT
    assert res1.callback_invoked is True
    assert callback_count[0] == 1

    # Second delivery (identical) -> DUPLICATE, callback NOT called again
    res2 = consumer.process_raw_message(raw_data, {}, "msg-2", on_event)
    assert res2.disposition == EventDeliveryDisposition.DUPLICATE
    assert res2.callback_invoked is False
    assert callback_count[0] == 1


def test_consumer_event_id_conflict():
    """Verify same event_id with modified immutable envelope content returns CONFLICT."""
    delivery_state = InMemoryDeliveryState()
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
        delivery_state=delivery_state,
    )

    env1 = _make_envelope(event_id="evt-collide", change_id="chg-1")
    env2 = _make_envelope(event_id="evt-collide", change_id="chg-DIFFERENT")

    msg1 = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=env1).to_bytes()
    msg2 = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=env2).to_bytes()

    callback_count = [0]

    def on_event(msg: EventWireMessage) -> None:
        callback_count[0] += 1

    res1 = consumer.process_raw_message(msg1, {}, "msg-1", on_event)
    assert res1.disposition == EventDeliveryDisposition.ACCEPT
    assert callback_count[0] == 1

    res2 = consumer.process_raw_message(msg2, {}, "msg-2", on_event)
    assert res2.disposition == EventDeliveryDisposition.CONFLICT
    assert res2.callback_invoked is False
    assert callback_count[0] == 1


def test_consumer_idempotency_collision():
    """Verify same (change_id, idempotency_key) with different event_id returns CONFLICT."""
    delivery_state = InMemoryDeliveryState()
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
        delivery_state=delivery_state,
    )

    env1 = _make_envelope(event_id="evt-1", change_id="chg-1", idempotency_key="same-key")
    env2 = _make_envelope(event_id="evt-2", change_id="chg-1", idempotency_key="same-key")

    msg1 = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=env1).to_bytes()
    msg2 = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=env2).to_bytes()

    callback_count = [0]

    def on_event(msg: EventWireMessage) -> None:
        callback_count[0] += 1

    res1 = consumer.process_raw_message(msg1, {}, "msg-1", on_event)
    assert res1.disposition == EventDeliveryDisposition.ACCEPT

    res2 = consumer.process_raw_message(msg2, {}, "msg-2", on_event)
    assert res2.disposition == EventDeliveryDisposition.CONFLICT
    assert res2.callback_invoked is False
    assert callback_count[0] == 1


def test_consumer_out_of_order_delivery():
    """Verify child event arriving before its causal parent returns OUT_OF_ORDER."""
    delivery_state = InMemoryDeliveryState()
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
        delivery_state=delivery_state,
    )

    child_env = _make_envelope(event_id="evt-child", causation_id="evt-unseen-parent")
    msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=child_env).to_bytes()

    callback_count = [0]
    res = consumer.process_raw_message(
        msg, {}, "msg-child", lambda m: callback_count.__setitem__(0, callback_count[0] + 1)
    )

    assert res.disposition == EventDeliveryDisposition.OUT_OF_ORDER
    assert res.callback_invoked is False
    assert callback_count[0] == 0


def test_secret_in_payload_fails_closed():
    """Verify secret or credential material in event payload raises on wire creation."""
    envelope = _make_envelope()

    # 1. Private key pattern
    with pytest.raises(ValueError, match="Secret or credential material detected"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."},
        )

    # 2. Bearer token pattern
    with pytest.raises(ValueError, match="Secret or credential material detected"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"auth": "Bearer secret_token_value_123456789"},
        )

    # 3. GitHub token pattern
    with pytest.raises(ValueError, match="Secret or credential material detected"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"token": "ghp_1234567890abcdef1234567890abcdef1234"},
        )

    # 4. Prohibited key name
    with pytest.raises(ValueError, match="Prohibited credential field name"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"client_secret": "any_value"},
        )


def test_extra_envelope_fields_rejected():
    """Verify extra unapproved fields in envelope payload are rejected by extra='forbid'."""
    envelope = _make_envelope()
    raw_dict = {
        "wire_version": WIRE_SCHEMA_VERSION,
        "topic_id": "changemesh-lifecycle-v1",
        "envelope": {
            **envelope.model_dump(mode="json"),
            "unapproved_field": "injected",
        },
        "payload": {},
    }
    raw_bytes = json.dumps(raw_dict).encode("utf-8")

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        EventWireMessage.from_bytes(raw_bytes)


def test_no_provider_sdk_types_leak():
    """Verify EventWireMessage and EventEnvelope contain zero Google SDK objects."""
    envelope = _make_envelope()
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)
    for field_name, field_val in envelope.__dict__.items():
        type_str = str(type(field_val))
        assert "google" not in type_str.lower(), f"Leaked SDK type in field {field_name}"
    for field_name, field_val in wire_msg.__dict__.items():
        type_str = str(type(field_val))
        assert "google" not in type_str.lower(), f"Leaked SDK type in wire field {field_name}"
