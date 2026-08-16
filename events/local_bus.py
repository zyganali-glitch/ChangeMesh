"""ChangeMesh local in-memory event bus adapter.

P-09.04: In-memory event bus implementing identical EventPublisher and EventConsumer
protocols with explicit LOCAL transport identity and SIMULATION/FIXTURE evidence modes.

CRITICAL EVIDENCE INVARIANT:
ExecutionEvidenceMode remains strictly 4 canonical values (FIXTURE, SIMULATION,
RECORDED_CLOUD, LIVE_WRITE). Local event-bus execution maps to SIMULATION/FIXTURE
and identifies transport as 'LOCAL'. It is physically impossible for local event-bus
execution to produce LIVE_WRITE or RECORDED_CLOUD evidence.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from domain.contracts.event_envelope import EventDeliveryDisposition
from domain.contracts.evidence import (
    EvidenceRecord,
    EvidenceState,
    ExecutionEvidenceMode,
    Provenance,
)
from events.consumer import EventConsumer, EventConsumeResult
from events.dead_letter import ProcessLocalDeadLetterState
from events.delivery_state import InMemoryDeliveryState
from events.publisher import EventPublisher, EventPublishResult
from events.retry import (
    EventRetryPolicy,
    execute_with_retry,
    sanitize_error_message,
)
from events.wire import EventWireMessage

logger = logging.getLogger(__name__)


class LocalEventBus:
    """Thread-safe in-memory event bus with subscriber routing and delivery classification.

    Acts as the local in-memory event transport fan-out and retry owner for local dispatch.
    """

    def __init__(
        self,
        delivery_state: Optional[InMemoryDeliveryState] = None,
        retry_policy: Optional[EventRetryPolicy] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        dead_letter_state: Optional[ProcessLocalDeadLetterState] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, List[Callable[[EventWireMessage], Any]]] = {}
        self._published_history: List[EventWireMessage] = []
        self._delivery_state = delivery_state or InMemoryDeliveryState()
        self._retry_policy = retry_policy or EventRetryPolicy()
        self._sleep_fn = sleep_fn
        self._dead_letter_state = dead_letter_state
        self._message_counter = 0

    @property
    def delivery_state(self) -> InMemoryDeliveryState:
        return self._delivery_state

    @property
    def published_history(self) -> Sequence[EventWireMessage]:
        with self._lock:
            return list(self._published_history)

    def subscribe(self, topic_id: str, handler: Callable[[EventWireMessage], Any]) -> None:
        """Register a handler for a topic."""
        with self._lock:
            if topic_id not in self._subscribers:
                self._subscribers[topic_id] = []
            self._subscribers[topic_id].append(handler)

    def publish_message(self, message: EventWireMessage) -> EventPublishResult:
        """Publish message across local subscribers with validation, dedup, and bounded retry."""
        # 1. Validate wire serialization and secret scanning
        raw_bytes = message.to_bytes()
        _ = EventWireMessage.from_bytes(raw_bytes)

        with self._lock:
            self._message_counter += 1
            msg_id = f"local-msg-{self._message_counter:06d}"
            self._published_history.append(message)
            handlers = list(self._subscribers.get(message.topic_id, []))

        # 2. Classify delivery
        disposition = self._delivery_state.classify(message.envelope)

        if disposition == EventDeliveryDisposition.ACCEPT:
            dead_letter_ctx = {
                "change_id": message.envelope.change_id,
                "correlation_id": message.envelope.correlation_id,
                "event_id": message.envelope.event_id,
                "topic_id": message.topic_id,
            }
            # Invoke each handler through canonical bounded retry engine
            for handler in handlers:
                res = execute_with_retry(
                    lambda: handler(message),
                    policy=self._retry_policy,
                    sleep_fn=self._sleep_fn,
                    dead_letter_context=dead_letter_ctx,
                    dead_letter_state=self._dead_letter_state,
                )
                if not res.succeeded:
                    clean_err = sanitize_error_message(str(res.terminal_error))
                    logger.error(
                        "Handler error on local topic %s (event %s): %s",
                        message.topic_id,
                        message.envelope.event_id,
                        clean_err,
                    )
                    # Transient exhaustion or deterministic failure must NOT be recorded accepted
                    return EventPublishResult(
                        status="FAILED",
                        message_id=msg_id,
                        topic_id=message.topic_id,
                        event_id=message.envelope.event_id,
                        transport="LOCAL",
                        error_message=clean_err,
                        dead_letter_record=res.dead_letter_record,
                    )

            # All handlers succeeded -> record accepted
            self._delivery_state.record_if_accepted(message.envelope)

        elif disposition == EventDeliveryDisposition.DUPLICATE:
            # Handlers are not re-invoked on duplicate
            pass
        elif disposition in (
            EventDeliveryDisposition.OUT_OF_ORDER,
            EventDeliveryDisposition.CONFLICT,
        ):
            return EventPublishResult(
                status="FAILED",
                message_id=msg_id,
                topic_id=message.topic_id,
                event_id=message.envelope.event_id,
                transport="LOCAL",
                error_message=f"Event {disposition.value}",
            )

        return EventPublishResult(
            status="PUBLISHED",
            message_id=msg_id,
            topic_id=message.topic_id,
            event_id=message.envelope.event_id,
            transport="LOCAL",
        )

    def create_execution_evidence(
        self,
        change_id: str,
        evidence_id: str,
        subject: str,
        evidence_mode: ExecutionEvidenceMode = ExecutionEvidenceMode.SIMULATION,
        state: EvidenceState = EvidenceState.SIMULATED,
        source: str = "local_event_bus",
        collection_timestamp: Optional[Any] = None,
    ) -> EvidenceRecord:
        """Generate canonical EvidenceRecord for local bus activity.

        Enforces that local execution cannot produce LIVE_WRITE or RECORDED_CLOUD evidence.
        """
        if evidence_mode in (
            ExecutionEvidenceMode.LIVE_WRITE,
            ExecutionEvidenceMode.RECORDED_CLOUD,
        ):
            raise ValueError(
                f"Local event bus cannot emit {evidence_mode.value} evidence. "
                "Only SIMULATION or FIXTURE modes are valid for local execution."
            )

        from datetime import datetime, timezone

        from domain.contracts.conventions import normalize_utc_datetime

        ts = normalize_utc_datetime(collection_timestamp or datetime.now(timezone.utc))
        provenance = Provenance(
            schema_version="1.0.0",
            source=source,
            collection_mode=evidence_mode,
            collection_timestamp=ts,
        )
        return EvidenceRecord(
            schema_version="1.0.0",
            evidence_id=evidence_id,
            change_request_id=change_id,
            subject=subject,
            state=state,
            provenance=provenance,
        )


class LocalEventPublisher(EventPublisher):
    """EventPublisher adapter backed by LocalEventBus."""

    def __init__(self, bus: LocalEventBus) -> None:
        self._bus = bus

    def publish(self, message: EventWireMessage) -> EventPublishResult:
        return self._bus.publish_message(message)


class LocalEventConsumer(EventConsumer):
    """EventConsumer adapter backed by LocalEventBus and InMemoryDeliveryState."""

    def __init__(
        self,
        bus: LocalEventBus,
        subscription_id: str,
        retry_policy: Optional[EventRetryPolicy] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        dead_letter_state: Optional[ProcessLocalDeadLetterState] = None,
    ) -> None:
        if not subscription_id or not subscription_id.strip():
            raise ValueError("subscription_id must not be blank")
        self._bus = bus
        self.subscription_id = subscription_id.strip()
        self._retry_policy = retry_policy or EventRetryPolicy()
        self._sleep_fn = sleep_fn
        self._dead_letter_state = dead_letter_state

    def process_raw_message(
        self,
        raw_data: bytes,
        attributes: Mapping[str, str],
        message_id: str,
        callback: Callable[[EventWireMessage], Any],
    ) -> EventConsumeResult:
        """Validate, classify, and dispatch a raw local message payload with bounded retry."""
        # 1. Schema & wire deserialization
        try:
            wire_msg = EventWireMessage.from_bytes(raw_data)
        except Exception as e:
            clean_err = sanitize_error_message(f"Schema validation error: {e}")
            logger.warning("Local message %s failed schema validation: %s", message_id, clean_err)
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.CONFLICT,
                event_id="malformed",
                message_id=message_id,
                transport="LOCAL",
                callback_invoked=False,
                error_message=clean_err,
            )

        # 2. Delivery classification
        event_id = wire_msg.envelope.event_id
        disposition = self._bus.delivery_state.classify(wire_msg.envelope)

        # 3. Handle according to disposition
        if disposition == EventDeliveryDisposition.ACCEPT:
            dead_letter_ctx = {
                "change_id": wire_msg.envelope.change_id,
                "correlation_id": wire_msg.envelope.correlation_id,
                "event_id": event_id,
                "topic_id": wire_msg.topic_id,
            }
            res = execute_with_retry(
                lambda: callback(wire_msg),
                policy=self._retry_policy,
                sleep_fn=self._sleep_fn,
                dead_letter_context=dead_letter_ctx,
                dead_letter_state=self._dead_letter_state,
            )
            if res.succeeded:
                self._bus.delivery_state.record_if_accepted(wire_msg.envelope)
                return EventConsumeResult(
                    disposition=EventDeliveryDisposition.ACCEPT,
                    event_id=event_id,
                    message_id=message_id,
                    transport="LOCAL",
                    callback_invoked=True,
                )
            else:
                clean_err = sanitize_error_message(str(res.terminal_error))
                logger.error(
                    "Local callback failed for message %s (event %s): %s",
                    message_id,
                    event_id,
                    clean_err,
                )
                return EventConsumeResult(
                    disposition=EventDeliveryDisposition.ACCEPT,
                    event_id=event_id,
                    message_id=message_id,
                    transport="LOCAL",
                    callback_invoked=True,
                    error_message=sanitize_error_message(
                        f"Callback execution failure: {res.terminal_error}"
                    ),
                    dead_letter_record=res.dead_letter_record,
                )

        elif disposition == EventDeliveryDisposition.DUPLICATE:
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.DUPLICATE,
                event_id=event_id,
                message_id=message_id,
                transport="LOCAL",
                callback_invoked=False,
            )

        elif disposition == EventDeliveryDisposition.OUT_OF_ORDER:
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.OUT_OF_ORDER,
                event_id=event_id,
                message_id=message_id,
                transport="LOCAL",
                callback_invoked=False,
                error_message="Causal predecessor not yet observed",
            )

        else:  # CONFLICT
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.CONFLICT,
                event_id=event_id,
                message_id=message_id,
                transport="LOCAL",
                callback_invoked=False,
                error_message="Event conflicts with observed state or idempotency key",
            )
