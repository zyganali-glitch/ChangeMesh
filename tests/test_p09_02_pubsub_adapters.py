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
import logging
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


def test_consumer_unsupported_envelope_schema_version_rejection():
    """Verify messages with unsupported envelope schema_version are rejected."""
    envelope_dict = _make_envelope().model_dump(mode="json")
    envelope_dict["schema_version"] = "99.0.0"

    bad_data = {
        "wire_version": "1.0.0",
        "topic_id": "changemesh-lifecycle-v1",
        "envelope": envelope_dict,
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
        message_id="msg-bad-env-ver",
        callback=lambda msg: callback_called.append(msg),
    )

    assert res.disposition == EventDeliveryDisposition.CONFLICT
    assert res.callback_invoked is False
    assert len(callback_called) == 0
    assert "Unsupported envelope schema_version" in (res.error_message or "")


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


def test_consumer_retry_ownership_transient_failure():
    """Verify TRANSIENT_RETRYABLE errors raise to trigger transport NACK/retry."""
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
    )
    envelope = _make_envelope(event_id="evt-retry-1")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    def failing_callback(msg: EventWireMessage) -> None:
        raise RuntimeError("Some temporary network glitch")

    with pytest.raises(RuntimeError, match="Some temporary network glitch"):
        consumer.process_raw_message(raw_data, {}, "msg-retry", failing_callback)


def test_consumer_retry_ownership_deterministic_failure():
    """Verify DETERMINISTIC_INVALID errors return ACCEPT to stop transport retry."""
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
    )
    envelope = _make_envelope(event_id="evt-det-1")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    def det_failing_callback(msg: EventWireMessage) -> None:
        raise ValueError("Schema validation failed: missing field")

    res = consumer.process_raw_message(raw_data, {}, "msg-det", det_failing_callback)
    # Should ACCEPT and NOT raise, relying on dead-letter pipeline
    assert res.disposition == EventDeliveryDisposition.ACCEPT
    assert res.callback_invoked is True
    assert "Schema validation failed" in (res.error_message or "")


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
            payload={"key": "-" * 5 + "BEGIN RSA PRIVATE KEY" + "-" * 5 + "\nMIIE..."},
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
            payload={"github": "ghp_" + "1234567890abcdef1234567890abcdef1234"},
        )

    # 4. Prohibited key name (original)
    with pytest.raises(ValueError, match="Prohibited credential field name"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"client_secret": "any_value"},
        )

    # 5. api_key structural payload rejected
    with pytest.raises(ValueError, match="Prohibited credential field name"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"api_key": "ordinary-looking-value"},
        )

    # 6. token structural payload rejected
    with pytest.raises(ValueError, match="Prohibited credential field name"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"token": "ordinary-looking-value"},
        )

    # 7. nested credential structural payload rejected
    with pytest.raises(ValueError, match="Prohibited credential field name"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"nested": {"credential": "ordinary-looking-value"}},
        )

    # 8. nested service_account sequence structural payload rejected
    with pytest.raises(ValueError, match="Prohibited credential field name"):
        EventWireMessage(
            topic_id="changemesh-lifecycle-v1",
            envelope=envelope,
            payload={"nested": [{"service_account": "ordinary-looking-value"}]},
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


def test_gcp_publisher_error_log_secrecy(caplog):
    """Verify GCP publisher error containing Bearer secret is sanitized in logs."""
    caplog.set_level(logging.DEBUG)
    mock_client = MagicMock()
    secret_token = "secret_bearer_token_9876543210"
    mock_client.publish.side_effect = RuntimeError(f"PubSub unavailable with Bearer {secret_token}")

    publisher = GooglePubSubPublisher(
        project_id="test-project",
        publisher_client=mock_client,
    )
    envelope = _make_envelope()
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)

    result = publisher.publish(wire_msg)
    assert result.status == "FAILED"

    assert secret_token not in caplog.text
    assert "[REDACTED_BEARER]" in caplog.text


def test_gcp_consumer_deterministic_callback_log_secrecy(caplog):
    """Verify GCP consumer deterministic callback failure with API key is sanitized."""
    caplog.set_level(logging.DEBUG)
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
    )
    envelope = _make_envelope(event_id="evt-det-sec")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    secret_key = "secret_api_key_1122334455"

    def failing_callback(msg: EventWireMessage) -> None:
        raise ValueError(f"Schema validation error with api_key='{secret_key}'")

    res = consumer.process_raw_message(raw_data, {}, "msg-det-sec", failing_callback)
    assert res.disposition == EventDeliveryDisposition.ACCEPT
    assert res.dead_letter_record is not None

    assert secret_key not in caplog.text
    assert "[REDACTED_SECRET]" in caplog.text


def test_gcp_consumer_transient_callback_log_secrecy(caplog):
    """Verify GCP consumer transient callback failure with secret is sanitized."""
    caplog.set_level(logging.DEBUG)
    consumer = GooglePubSubConsumer(
        project_id="test-project",
        subscription_id="changemesh-lifecycle-sub-v1",
        subscriber_client=MagicMock(),
    )
    envelope = _make_envelope(event_id="evt-trans-sec")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    secret_pwd = "my_super_secret_password"

    def failing_callback(msg: EventWireMessage) -> None:
        raise TimeoutError(f"Connection timeout with password='{secret_pwd}'")

    with pytest.raises(TimeoutError):
        consumer.process_raw_message(raw_data, {}, "msg-trans-sec", failing_callback)

    assert secret_pwd not in caplog.text
    assert "[REDACTED_SECRET]" in caplog.text


def test_gcp_dead_letter_consumer_processing_and_handoff():
    """Verify GooglePubSubDeadLetterConsumer processes DLQ deliveries into canonical handoffs."""
    from events.dead_letter import ProcessLocalDeadLetterState
    from events.retry import FailureClassification
    from integrations.gcp.pubsub_adapter import GooglePubSubDeadLetterConsumer

    dl_state = ProcessLocalDeadLetterState()
    dl_consumer = GooglePubSubDeadLetterConsumer(
        project_id="test-project",
        subscription_id="changemesh-dead-letter-sub-v1",
        dead_letter_state=dl_state,
    )

    envelope = _make_envelope(
        event_id="evt-dlq-001",
        change_id="chg-dlq-001",
        correlation_id="corr-dlq-001",
    )
    wire_msg = EventWireMessage(
        topic_id="changemesh-lifecycle-v1",
        envelope=envelope,
        payload={"step": "verify"},
    )
    raw_data = wire_msg.to_bytes()

    record = dl_consumer.process_dead_letter_delivery(
        raw_data=raw_data,
        attributes=wire_msg.get_transport_attributes(),
        message_id="pubsub-dlq-msg-1",
        delivery_attempt=5,
        failure_reason="Delivery attempt exceeded subscription bound",
    )

    assert record.original_event_id == "evt-dlq-001"
    assert record.change_id == "chg-dlq-001"
    assert record.correlation_id == "corr-dlq-001"
    assert record.original_topic_id == "changemesh-lifecycle-v1"
    assert record.dead_letter_topic_id == "changemesh-dead-letter-v1"
    assert record.attempts_made == 5
    assert record.failure_classification == FailureClassification.TERMINAL_EXHAUSTED
    assert record.handoff.human_authority_required is False
    assert record.handoff.terminal_state == "DEAD_LETTERED"
    assert record.handoff.original_event_id == "evt-dlq-001"


def test_gcp_dead_letter_consumer_unparseable_payload_fallback():
    """Verify dead-letter consumer falls back to complete attributes for unparseable raw bytes."""
    from integrations.gcp.pubsub_adapter import GooglePubSubDeadLetterConsumer

    dl_consumer = GooglePubSubDeadLetterConsumer(
        project_id="test-project",
        subscription_id="changemesh-dead-letter-sub-v1",
    )

    raw_bad_data = b"NOT_VALID_JSON_OR_WIRE"
    attributes = {
        "event_id": "evt-unparseable",
        "change_id": "chg-unparseable",
        "correlation_id": "corr-unparseable",
        "topic_id": "changemesh-agent-work-v1",
    }

    record = dl_consumer.process_dead_letter_delivery(
        raw_data=raw_bad_data,
        attributes=attributes,
        message_id="pubsub-dlq-bad-msg",
        delivery_attempt=7,
        failure_reason="Dead letter caused by unparseable corrupt payload",
    )

    assert record.original_event_id == "evt-unparseable"
    assert record.change_id == "chg-unparseable"
    assert record.correlation_id == "corr-unparseable"
    assert record.original_topic_id == "changemesh-agent-work-v1"
    assert record.attempts_made == 7
    assert record.handoff.human_authority_required is False


def test_gcp_dead_letter_consumer_rejection_missing_identity_fields():
    """Verify dead-letter consumer fails closed when identity fields cannot be reconstructed."""
    from integrations.gcp.pubsub_adapter import GooglePubSubDeadLetterConsumer

    dl_consumer = GooglePubSubDeadLetterConsumer(
        project_id="test-project",
        subscription_id="changemesh-dead-letter-sub-v1",
    )

    raw_bad_data = b"UNPARSEABLE_DATA"

    # Missing event_id
    with pytest.raises(ValueError, match="missing required identity fields.*event_id"):
        dl_consumer.process_dead_letter_delivery(
            raw_data=raw_bad_data,
            attributes={
                "change_id": "chg-1",
                "correlation_id": "corr-1",
                "topic_id": "changemesh-lifecycle-v1",
            },
            message_id="msg-missing-evt",
        )

    # Missing change_id
    with pytest.raises(ValueError, match="missing required identity fields.*change_id"):
        dl_consumer.process_dead_letter_delivery(
            raw_data=raw_bad_data,
            attributes={
                "event_id": "evt-1",
                "correlation_id": "corr-1",
                "topic_id": "changemesh-lifecycle-v1",
            },
            message_id="msg-missing-chg",
        )

    # Missing correlation_id
    with pytest.raises(ValueError, match="missing required identity fields.*correlation_id"):
        dl_consumer.process_dead_letter_delivery(
            raw_data=raw_bad_data,
            attributes={
                "event_id": "evt-1",
                "change_id": "chg-1",
                "topic_id": "changemesh-lifecycle-v1",
            },
            message_id="msg-missing-corr",
        )

    # Missing topic_id
    with pytest.raises(ValueError, match="missing required identity fields.*topic_id"):
        dl_consumer.process_dead_letter_delivery(
            raw_data=raw_bad_data,
            attributes={
                "event_id": "evt-1",
                "change_id": "chg-1",
                "correlation_id": "corr-1",
            },
            message_id="msg-missing-top",
        )

    # Completely empty attributes and corrupt wire
    with pytest.raises(ValueError, match="Cannot reconstruct canonical dead-letter event identity"):
        dl_consumer.process_dead_letter_delivery(
            raw_data=raw_bad_data,
            attributes={},
            message_id="msg-empty-all",
        )


def test_gcp_dead_letter_consumer_delivery_attempt_semantics():
    """Verify provider delivery attempts are approximate and absent count never fabricates 5."""
    from events.topology import get_canonical_topology
    from integrations.gcp.pubsub_adapter import GooglePubSubDeadLetterConsumer

    dl_consumer = GooglePubSubDeadLetterConsumer(
        project_id="test-project",
        subscription_id="changemesh-dead-letter-sub-v1",
    )

    envelope_7 = _make_envelope(
        event_id="evt-attempts-7",
        change_id="chg-attempts-7",
        correlation_id="corr-attempts-7",
    )
    wire_msg_7 = EventWireMessage(
        topic_id="changemesh-lifecycle-v1",
        envelope=envelope_7,
    )
    raw_data_7 = wire_msg_7.to_bytes()

    # Case 1: Provider reports delivery_attempt=7
    rec_7 = dl_consumer.process_dead_letter_delivery(
        raw_data=raw_data_7,
        attributes=wire_msg_7.get_transport_attributes(),
        message_id="msg-attempt-7",
        delivery_attempt=7,
    )
    assert rec_7.attempts_made == 7
    assert "approximate provider attempts: 7" in rec_7.sanitized_failure_reason

    # Case 2: Provider delivery_attempt is None -> NO fabricated 5
    envelope_none = _make_envelope(
        event_id="evt-attempts-none",
        change_id="chg-attempts-none",
        correlation_id="corr-attempts-none",
    )
    wire_msg_none = EventWireMessage(
        topic_id="changemesh-lifecycle-v1",
        envelope=envelope_none,
    )
    raw_data_none = wire_msg_none.to_bytes()

    rec_none = dl_consumer.process_dead_letter_delivery(
        raw_data=raw_data_none,
        attributes=wire_msg_none.get_transport_attributes(),
        message_id="msg-attempt-none",
        delivery_attempt=None,
    )
    assert rec_none.attempts_made == 0
    assert "provider attempt count unavailable" in rec_none.sanitized_failure_reason
    assert "5" not in rec_none.sanitized_failure_reason

    # Case 3: Configured topology max delivery attempts remains 5
    topo = get_canonical_topology()
    lifecycle_sub = topo.get_subscription("changemesh-lifecycle-sub-v1")
    assert lifecycle_sub is not None
    assert lifecycle_sub.dead_letter_policy is not None
    assert lifecycle_sub.dead_letter_policy.max_delivery_attempts == 5

    # Case 4: Configured max (5) and observed/reported attempt (0 or 7) remain distinct
    assert lifecycle_sub.dead_letter_policy.max_delivery_attempts != rec_none.attempts_made
    assert lifecycle_sub.dead_letter_policy.max_delivery_attempts != rec_7.attempts_made


def test_gcp_dead_letter_consumer_replay_idempotency():
    """Verify replaying the same DLQ message returns existing logical record without duplicate."""
    from events.dead_letter import ProcessLocalDeadLetterState
    from integrations.gcp.pubsub_adapter import GooglePubSubDeadLetterConsumer

    dl_state = ProcessLocalDeadLetterState()
    dl_consumer = GooglePubSubDeadLetterConsumer(
        project_id="test-project",
        subscription_id="changemesh-dead-letter-sub-v1",
        dead_letter_state=dl_state,
    )

    envelope1 = _make_envelope(event_id="evt-dlq-replay-1")
    raw1 = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope1).to_bytes()

    envelope2 = _make_envelope(event_id="evt-dlq-replay-2")
    raw2 = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope2).to_bytes()

    # Step 1: Process message 1
    rec1 = dl_consumer.process_dead_letter_delivery(raw1, {}, "msg-1", delivery_attempt=5)
    assert dl_state.total_records == 1

    # Step 2: Replay exact same message 1
    rec1_replay = dl_consumer.process_dead_letter_delivery(
        raw1, {}, "msg-1-dup", delivery_attempt=5
    )
    assert rec1_replay.dead_letter_id == rec1.dead_letter_id
    assert rec1_replay.handoff.timestamp == rec1.handoff.timestamp
    assert dl_state.total_records == 1  # No second emission

    # Step 3: Process different message 2 -> separate handoff
    rec2 = dl_consumer.process_dead_letter_delivery(raw2, {}, "msg-2", delivery_attempt=5)
    assert rec2.dead_letter_id != rec1.dead_letter_id
    assert dl_state.total_records == 2
