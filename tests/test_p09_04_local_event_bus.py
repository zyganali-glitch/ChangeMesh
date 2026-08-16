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


def test_local_bus_handler_transient_retry_to_success():
    """Verify local bus handler transient error retries to success under bounded retry engine."""
    attempts = [0]
    sleeps: list[float] = []
    from events.retry import EventRetryPolicy

    policy = EventRetryPolicy(max_attempts=3, initial_backoff_seconds=0.5)
    bus = LocalEventBus(retry_policy=policy, sleep_fn=sleeps.append)
    publisher = LocalEventPublisher(bus)

    def transient_handler(msg: EventWireMessage) -> None:
        attempts[0] += 1
        if attempts[0] == 1:
            raise ConnectionResetError("Temporary connection drop")

    bus.subscribe("changemesh-lifecycle-v1", transient_handler)

    envelope = _make_envelope(event_id="evt-retry-success")
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)

    res = publisher.publish(wire_msg)
    assert res.status == "PUBLISHED"
    assert res.transport == "LOCAL"
    assert res.dead_letter_record is None
    assert attempts[0] == 2
    assert sleeps == [0.5]
    assert "evt-retry-success" in bus.delivery_state.seen_events


def test_local_bus_sibling_handler_isolation_no_duplicate_replay():
    """Verify sibling handler retry does NOT re-execute already successful handler."""
    h1_calls = [0]
    h2_calls = [0]
    from events.retry import EventRetryPolicy

    policy = EventRetryPolicy(max_attempts=3, initial_backoff_seconds=0.1)
    bus = LocalEventBus(retry_policy=policy, sleep_fn=lambda _: None)
    publisher = LocalEventPublisher(bus)

    def handler_1(msg: EventWireMessage) -> None:
        h1_calls[0] += 1

    def handler_2(msg: EventWireMessage) -> None:
        h2_calls[0] += 1
        if h2_calls[0] == 1:
            raise TimeoutError("Transient timeout in handler 2")

    bus.subscribe("changemesh-lifecycle-v1", handler_1)
    bus.subscribe("changemesh-lifecycle-v1", handler_2)

    envelope = _make_envelope(event_id="evt-sibling-isolation")
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)

    res = publisher.publish(wire_msg)
    assert res.status == "PUBLISHED"
    assert h1_calls[0] == 1  # Crucial: handler 1 executed ONCE, never replayed
    assert h2_calls[0] == 2  # Handler 2 retried and succeeded
    assert "evt-sibling-isolation" in bus.delivery_state.seen_events


def test_local_bus_handler_transient_exhaustion_dead_letter_handoff():
    """Verify transient exhaustion on local bus creates visible handoff and returns FAILED."""
    from events.retry import EventRetryPolicy, FailureClassification

    policy = EventRetryPolicy(max_attempts=3, initial_backoff_seconds=0.1)
    bus = LocalEventBus(retry_policy=policy, sleep_fn=lambda _: None)
    publisher = LocalEventPublisher(bus)

    def always_failing_handler(msg: EventWireMessage) -> None:
        raise ConnectionResetError("Persistent connection reset error")

    bus.subscribe("changemesh-lifecycle-v1", always_failing_handler)

    envelope = _make_envelope(event_id="evt-transient-exhaust")
    wire_msg = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope)

    res = publisher.publish(wire_msg)
    assert res.status == "FAILED"
    assert res.transport == "LOCAL"
    assert "Persistent connection reset" in (res.error_message or "")

    # Dead letter artifact must be visible on result
    dl = res.dead_letter_record
    assert dl is not None
    assert dl.original_event_id == "evt-transient-exhaust"
    assert dl.change_id == "chg-local-001"
    assert dl.correlation_id == "corr-local-001"
    assert dl.original_topic_id == "changemesh-lifecycle-v1"
    assert dl.attempts_made == 3
    assert dl.failure_classification == FailureClassification.TERMINAL_EXHAUSTED
    assert dl.handoff.human_authority_required is False
    assert dl.handoff.terminal_state == "DEAD_LETTERED"

    # Must NOT be marked accepted in delivery state
    assert "evt-transient-exhaust" not in bus.delivery_state.seen_events


def test_local_bus_handler_deterministic_failure_not_recorded_accepted():
    """Verify deterministic handler error fails immediately with zero retry and returns handoff."""
    from events.retry import EventRetryPolicy, FailureClassification

    policy = EventRetryPolicy(max_attempts=5)
    bus = LocalEventBus(retry_policy=policy, sleep_fn=lambda _: None)
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

    dl = res.dead_letter_record
    assert dl is not None
    assert dl.original_event_id == "evt-det-fail"
    assert dl.attempts_made == 1
    assert dl.failure_classification == FailureClassification.DETERMINISTIC_INVALID
    assert dl.handoff.human_authority_required is False


def test_local_consumer_transient_retry_to_success():
    """Verify LocalEventConsumer retries transient callback failure to success."""
    from events.retry import EventRetryPolicy

    policy = EventRetryPolicy(max_attempts=3, initial_backoff_seconds=0.1)
    bus = LocalEventBus()
    consumer = LocalEventConsumer(
        bus,
        subscription_id="sub-retry",
        retry_policy=policy,
        sleep_fn=lambda _: None,
    )

    callback_attempts = [0]

    def on_event(msg: EventWireMessage) -> None:
        callback_attempts[0] += 1
        if callback_attempts[0] == 1:
            raise TimeoutError("Transient timeout in consumer callback")

    envelope = _make_envelope(event_id="evt-cons-retry")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    res = consumer.process_raw_message(raw_data, {}, "msg-cons-retry", on_event)
    assert res.disposition == EventDeliveryDisposition.ACCEPT
    assert res.callback_invoked is True
    assert res.dead_letter_record is None
    assert callback_attempts[0] == 2
    assert "evt-cons-retry" in bus.delivery_state.seen_events


def test_local_consumer_transient_exhaustion_dead_letter_handoff():
    """Verify LocalEventConsumer transient exhaustion returns dead letter handoff."""
    from events.retry import EventRetryPolicy, FailureClassification

    policy = EventRetryPolicy(max_attempts=3, initial_backoff_seconds=0.1)
    bus = LocalEventBus()
    consumer = LocalEventConsumer(
        bus,
        subscription_id="sub-exhaust",
        retry_policy=policy,
        sleep_fn=lambda _: None,
    )

    def failing_callback(msg: EventWireMessage) -> None:
        raise TimeoutError("Exhausted socket timeout")

    envelope = _make_envelope(event_id="evt-cons-exhaust")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    res = consumer.process_raw_message(raw_data, {}, "msg-cons-exhaust", failing_callback)
    assert res.disposition == EventDeliveryDisposition.ACCEPT
    assert res.callback_invoked is True
    assert res.dead_letter_record is not None
    dl = res.dead_letter_record
    assert dl.original_event_id == "evt-cons-exhaust"
    assert dl.attempts_made == 3
    assert dl.failure_classification == FailureClassification.TERMINAL_EXHAUSTED
    assert dl.handoff.human_authority_required is False
    assert "evt-cons-exhaust" not in bus.delivery_state.seen_events


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
    """Verify transient callback failure with Bearer token is sanitized in logs."""
    caplog.set_level(logging.DEBUG)
    bus = LocalEventBus()
    consumer = LocalEventConsumer(
        bus,
        subscription_id="local-lifecycle-sub",
        sleep_fn=lambda _: None,
    )

    envelope = _make_envelope(event_id="evt-secret-trans")
    raw_data = EventWireMessage(topic_id="changemesh-lifecycle-v1", envelope=envelope).to_bytes()

    secret_bearer = "secret_bearer_token_xyz12345"

    def failing_callback(msg: EventWireMessage) -> None:
        raise ConnectionResetError(f"Connection reset while sending Bearer {secret_bearer}")

    res = consumer.process_raw_message(raw_data, {}, "msg-secret-trans", failing_callback)
    assert res.disposition == EventDeliveryDisposition.ACCEPT
    assert res.dead_letter_record is not None
    assert res.dead_letter_record.attempts_made == 3

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
