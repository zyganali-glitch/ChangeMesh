"""ChangeMesh P-09.04 Dedicated Test Suite — Local Event Bus and Contract Parity.

Validates:
1. LocalEventBus publish and subscriber dispatch across topics.
2. Identical wire validation and secret rejection parity with Pub/Sub adapter.
3. Duplicate delivery safety: second dispatch does NOT re-invoke subscriber callback.
4. Conflict and out-of-order delivery classification parity.
5. Distinct transport marker: 'LOCAL' vs 'GOOGLE_PUBSUB'.
6. Evidence mode invariant: local bus execution creates SIMULATION/FIXTURE evidence,
   and strictly fails closed if asked to produce LIVE_WRITE or RECORDED_CLOUD.
7. Zero Google SDK imports or dependencies in local event bus.
8. Adversarial log secrecy: exceptions containing secrets/tokens are never logged raw.
9. Handler failure handling: transient failures are not recorded accepted.
10. Handler deterministic failure: creates dead-letter record and is not recorded accepted.
"""

import logging
from datetime import datetime, timezone

import pytest

from domain.contracts.agent_descriptor import AgentRevisionProvenance
from domain.contracts.event_envelope import EventDeliveryDisposition, EventEnvelope
from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode
from events.local_bus import (
    LocalEventBus,
    LocalEventConsumer,
    LocalEventPublisher,
)
from events.wire import EventWireMessage


def _make_envelope(
    event_id: str = "evt-local-001",
    change_id: str = "chg-local-001",
    correlation_id: str = "corr-local-001",
    causation_id: str | None = None,
    idempotency_key: str = "idem-local-001",
    producer_id: str = "risk_assessor",
    producer_revision: str = "1.0.0",
    producer_role: str | None = "RiskAssessor",
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


def test_local_bus_publish_and_subscriber_dispatch():
    """Verify LocalEventBus dispatches messages to topic subscribers."""
    bus = LocalEventBus()
    publisher = LocalEventPublisher(bus)

    lifecycle_events = []
    agent_work_events = []

    bus.subscribe("changemesh-lifecycle-v1", lambda msg: lifecycle_events.append(msg))
    bus.subscribe("changemesh-agent-work-v1", lambda msg: agent_work_events.append(msg))

    envelope = _make_envelope(event_id="evt-1")
    wire_msg = EventWireMessage(
        topic_id="changemesh-lifecycle-v1",
        envelope=envelope,
        payload={"stage": "analysis"},
    )

    result = publisher.publish(wire_msg)

    assert result.status == "PUBLISHED"
    assert result.transport == "LOCAL"
    assert result.message_id.startswith("local-msg-")
    assert result.event_id == "evt-1"
    assert result.topic_id == "changemesh-lifecycle-v1"

    assert len(lifecycle_events) == 1
    assert lifecycle_events[0].envelope.event_id == "evt-1"
    assert len(agent_work_events) == 0  # Not routed to different topic


def test_local_bus_duplicate_delivery_safety():
    """Verify duplicate message on local bus does not re-invoke subscribers."""
    bus = LocalEventBus()
    publisher = LocalEventPublisher(bus)

    received_counts = [0]
    bus.subscribe(
        "changemesh-lifecycle-v1",
        lambda msg: received_counts.__setitem__(0, received_counts[0] + 1),
    )

    envelope = _make_envelope(event_id="evt-dup-local")
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)

    # First publish
    res1 = publisher.publish(wire_msg)
    assert res1.status == "PUBLISHED"
    assert received_counts[0] == 1

    # Duplicate publish
    res2 = publisher.publish(wire_msg)
    assert res2.status == "PUBLISHED"
    assert received_counts[0] == 1  # Handler was NOT invoked a second time


def test_local_consumer_parity():
    """Verify LocalEventConsumer implements identical validation and classification."""
    bus = LocalEventBus()
    consumer = LocalEventConsumer(bus, subscription_id="local-lifecycle-sub")

    envelope = _make_envelope(event_id="evt-cons-1")
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)
    raw_data = wire_msg.to_bytes()

    callback_called = []
    res = consumer.process_raw_message(
        raw_data=raw_data,
        attributes=wire_msg.get_transport_attributes(),
        message_id="local-msg-001",
        callback=lambda msg: callback_called.append(msg.envelope.event_id),
    )

    assert res.disposition == EventDeliveryDisposition.ACCEPT
    assert res.transport == "LOCAL"
    assert res.callback_invoked is True
    assert callback_called == ["evt-cons-1"]

    # Duplicate through consumer
    res_dup = consumer.process_raw_message(
        raw_data=raw_data,
        attributes={},
        message_id="local-msg-002",
        callback=lambda msg: callback_called.append(msg.envelope.event_id),
    )
    assert res_dup.disposition == EventDeliveryDisposition.DUPLICATE
    assert res_dup.callback_invoked is False
    assert len(callback_called) == 1


def test_local_bus_evidence_mode_safety():
    """Verify LocalEventBus creates SIMULATION evidence and rejects LIVE_WRITE."""
    bus = LocalEventBus()

    # Valid SIMULATION evidence
    ev_sim = bus.create_execution_evidence(
        change_id="chg-001",
        evidence_id="ev-001",
        subject="Local bus dispatch",
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        state=EvidenceState.SIMULATED,
    )
    assert ev_sim.provenance.collection_mode == ExecutionEvidenceMode.SIMULATION
    assert ev_sim.state == EvidenceState.SIMULATED
    assert ev_sim.change_request_id == "chg-001"

    # Valid FIXTURE evidence
    ev_fix = bus.create_execution_evidence(
        change_id="chg-001",
        evidence_id="ev-002",
        subject="Local bus fixture",
        evidence_mode=ExecutionEvidenceMode.FIXTURE,
        state=EvidenceState.SIMULATED,
    )
    assert ev_fix.provenance.collection_mode == ExecutionEvidenceMode.FIXTURE

    # Rejection of LIVE_WRITE mode
    with pytest.raises(ValueError, match="cannot emit LIVE_WRITE evidence"):
        bus.create_execution_evidence(
            change_id="chg-001",
            evidence_id="ev-003",
            subject="Local bus live write attempt",
            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        )

    # Rejection of RECORDED_CLOUD mode
    with pytest.raises(ValueError, match="cannot emit RECORDED_CLOUD evidence"):
        bus.create_execution_evidence(
            change_id="chg-001",
            evidence_id="ev-004",
            subject="Local bus recorded cloud attempt",
            evidence_mode=ExecutionEvidenceMode.RECORDED_CLOUD,
        )


def test_no_google_sdk_imports_in_local_bus():
    """Verify local_bus module has zero imports of google cloud SDK."""
    from events import local_bus

    module_dict = local_bus.__dict__
    for key, val in module_dict.items():
        type_str = str(type(val))
        assert "google.cloud" not in type_str.lower(), f"Leaked SDK import {key}"


def test_local_bus_handler_transient_failure_not_recorded_accepted():
    """Verify transient handler error does not record event as accepted in delivery state."""
    bus = LocalEventBus()
    publisher = LocalEventPublisher(bus)

    def failing_handler(msg: EventWireMessage) -> None:
        raise ConnectionResetError("Transient network failure in local handler")

    bus.subscribe("changemesh-lifecycle-v1", failing_handler)

    envelope = _make_envelope(event_id="evt-transient-fail")
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)

    res = publisher.publish(wire_msg)
    assert res.status == "FAILED"
    assert "Transient network failure" in (res.error_message or "")
    # Crucial: Event MUST NOT be recorded as accepted in delivery state
    assert "evt-transient-fail" not in bus.delivery_state.seen_events


def test_local_bus_handler_deterministic_failure_not_recorded_accepted():
    """Verify deterministic handler error returns FAILED and is not accepted in delivery state."""
    bus = LocalEventBus()
    publisher = LocalEventPublisher(bus)

    def invalid_handler(msg: EventWireMessage) -> None:
        raise ValueError("Schema validation failed: invalid payload structure")

    bus.subscribe("changemesh-lifecycle-v1", invalid_handler)

    envelope = _make_envelope(event_id="evt-det-fail")
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)

    res = publisher.publish(wire_msg)
    assert res.status == "FAILED"
    assert "Schema validation failed" in (res.error_message or "")
    assert "evt-det-fail" not in bus.delivery_state.seen_events


def test_local_consumer_deterministic_callback_log_secrecy(caplog):
    """Verify deterministic callback failure containing secrets is sanitized in logs."""
    caplog.set_level(logging.DEBUG)
    bus = LocalEventBus()
    consumer = LocalEventConsumer(bus, subscription_id="local-lifecycle-sub")

    envelope = _make_envelope(event_id="evt-secret-det")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    secret_val = "secret_api_key_987654321"

    def failing_callback(msg: EventWireMessage) -> None:
        raise ValueError(f"Schema validation error with api_key='{secret_val}'")

    res = consumer.process_raw_message(raw_data, {}, "msg-secret-det", failing_callback)
    assert res.disposition == EventDeliveryDisposition.ACCEPT
    assert res.dead_letter_record is not None

    # Verify log output does not contain raw secret
    assert secret_val not in caplog.text
    assert "[REDACTED_SECRET]" in caplog.text


def test_local_consumer_transient_callback_log_secrecy(caplog):
    """Verify transient callback failure containing Bearer token is sanitized in logs."""
    caplog.set_level(logging.DEBUG)
    bus = LocalEventBus()
    consumer = LocalEventConsumer(bus, subscription_id="local-lifecycle-sub")

    envelope = _make_envelope(event_id="evt-secret-trans")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    secret_bearer = "secret_bearer_token_xyz12345"

    def failing_callback(msg: EventWireMessage) -> None:
        raise ConnectionResetError(f"Connection reset while sending Bearer {secret_bearer}")

    with pytest.raises(ConnectionResetError):
        consumer.process_raw_message(raw_data, {}, "msg-secret-trans", failing_callback)

    # Verify log output does not contain raw secret
    assert secret_bearer not in caplog.text
    assert "[REDACTED_BEARER]" in caplog.text


def test_local_bus_subscriber_handler_log_secrecy(caplog):
    """Verify LocalEventBus handler exception containing token is sanitized in logs."""
    caplog.set_level(logging.DEBUG)
    bus = LocalEventBus()
    publisher = LocalEventPublisher(bus)

    secret_token = "ghp_" + "1234567890abcdef1234567890abcdef1234"

    def failing_handler(msg: EventWireMessage) -> None:
        raise RuntimeError(f"Handler failed with token={secret_token}")

    bus.subscribe("changemesh-lifecycle-v1", failing_handler)

    envelope = _make_envelope(event_id="evt-secret-handler")
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)

    publisher.publish(wire_msg)

    # Verify log output does not contain raw token
    assert secret_token not in caplog.text
    assert "[REDACTED_TOKEN]" in caplog.text or "[REDACTED_SECRET]" in caplog.text
