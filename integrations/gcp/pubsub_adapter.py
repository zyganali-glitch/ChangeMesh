"""ChangeMesh Google Cloud Pub/Sub provider adapter.

P-09.02: Provider-specific transport adapter for Google Pub/Sub publishing
and consuming behind provider-neutral EventPublisher and EventConsumer protocols.

Google SDK types and imports are strictly confined to this module.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from domain.contracts.event_envelope import EventDeliveryDisposition
from events.consumer import EventConsumer, EventConsumeResult
from events.dead_letter import (
    DeadLetterEventRecord,
    ProcessLocalDeadLetterState,
    compute_dead_letter_id,
    get_default_dead_letter_state,
)
from events.delivery_state import InMemoryDeliveryState
from events.publisher import EventPublisher, EventPublishResult
from events.retry import FailureClassification, classify_failure, sanitize_error_message
from events.wire import EventWireMessage

logger = logging.getLogger(__name__)


class GooglePubSubPublisher(EventPublisher):
    """Google Cloud Pub/Sub publisher adapter."""

    def __init__(
        self,
        project_id: str,
        publisher_client: Optional[Any] = None,
    ) -> None:
        if not project_id or not project_id.strip():
            raise ValueError("project_id must not be blank")
        self.project_id = project_id.strip()

        if publisher_client is None:
            # Lazy import to avoid unnecessary SDK initialization when unused
            from google.cloud import pubsub_v1  # type: ignore[import-untyped,attr-defined]

            self._client = pubsub_v1.PublisherClient()
        else:
            self._client = publisher_client

    def publish(self, message: EventWireMessage) -> EventPublishResult:
        """Publish an EventWireMessage to Google Pub/Sub topic."""
        topic_path = f"projects/{self.project_id}/topics/{message.topic_id}"
        data = message.to_bytes()
        attributes = message.get_transport_attributes()

        try:
            future = self._client.publish(topic_path, data, **attributes)
            message_id = future.result() if hasattr(future, "result") else str(future)
            return EventPublishResult(
                status="PUBLISHED",
                message_id=str(message_id),
                topic_id=message.topic_id,
                event_id=message.envelope.event_id,
                transport="GOOGLE_PUBSUB",
            )
        except Exception as e:
            clean_err = sanitize_error_message(str(e))
            logger.error("Failed to publish message to topic %s: %s", topic_path, clean_err)
            return EventPublishResult(
                status="FAILED",
                message_id="none",
                topic_id=message.topic_id,
                event_id=message.envelope.event_id,
                transport="GOOGLE_PUBSUB",
                error_message=clean_err,
            )


class GooglePubSubConsumer(EventConsumer):
    """Google Cloud Pub/Sub consumer adapter with pre-dispatch validation and dedup."""

    def __init__(
        self,
        project_id: str,
        subscription_id: str,
        subscriber_client: Optional[Any] = None,
        delivery_state: Optional[InMemoryDeliveryState] = None,
        dead_letter_state: Optional[ProcessLocalDeadLetterState] = None,
    ) -> None:
        if not project_id or not project_id.strip():
            raise ValueError("project_id must not be blank")
        if not subscription_id or not subscription_id.strip():
            raise ValueError("subscription_id must not be blank")

        self.project_id = project_id.strip()
        self.subscription_id = subscription_id.strip()
        self.delivery_state = delivery_state
        self._dead_letter_state = (
            dead_letter_state if dead_letter_state is not None else get_default_dead_letter_state()
        )

        if subscriber_client is None:
            from google.cloud import pubsub_v1  # type: ignore[import-untyped,attr-defined]

            self._client = pubsub_v1.SubscriberClient()
        else:
            self._client = subscriber_client

    def process_raw_message(
        self,
        raw_data: bytes,
        attributes: Mapping[str, str],
        message_id: str,
        callback: Callable[[EventWireMessage], Any],
    ) -> EventConsumeResult:
        """Validate, classify, and dispatch a raw Pub/Sub message payload.

        Steps:
        1. Deserializes and validates EventWireMessage (rejects malformed JSON,
           unsupported versions, missing/extra fields, secret payloads).
        2. Classifies delivery against delivery_state (if configured).
        3. If ACCEPT: invokes callback and records accepted state.
        4. If DUPLICATE: skips callback (duplicate-delivery safe).
        5. If OUT_OF_ORDER: skips callback, returns OUT_OF_ORDER disposition.
        6. If CONFLICT: skips callback, returns CONFLICT disposition.
        """
        # Step 1: Schema & wire deserialization
        try:
            wire_msg = EventWireMessage.from_bytes(raw_data)
        except Exception as e:
            clean_err = sanitize_error_message(f"Schema validation error: {e}")
            logger.warning("Message %s failed schema validation: %s", message_id, clean_err)
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.CONFLICT,
                event_id="malformed",
                message_id=message_id,
                transport="GOOGLE_PUBSUB",
                callback_invoked=False,
                error_message=clean_err,
            )

        # Step 2: Delivery classification
        event_id = wire_msg.envelope.event_id
        if self.delivery_state is not None:
            disposition = self.delivery_state.classify(wire_msg.envelope)
        else:
            disposition = EventDeliveryDisposition.ACCEPT

        # Step 3: Handle according to disposition
        if disposition == EventDeliveryDisposition.ACCEPT:
            try:
                callback(wire_msg)
                if self.delivery_state is not None:
                    self.delivery_state.record_if_accepted(wire_msg.envelope)
                return EventConsumeResult(
                    disposition=EventDeliveryDisposition.ACCEPT,
                    event_id=event_id,
                    message_id=message_id,
                    transport="GOOGLE_PUBSUB",
                    callback_invoked=True,
                )
            except Exception as e:
                classification = classify_failure(e)
                clean_err = sanitize_error_message(str(e))
                if classification == FailureClassification.TRANSIENT_RETRYABLE:
                    logger.warning(
                        "Transient failure in callback for message %s (event %s); "
                        "raising to NACK transport: %s",
                        message_id,
                        event_id,
                        clean_err,
                    )
                    raise e

                logger.error(
                    "Callback failed with deterministic error for message %s (event %s): %s",
                    message_id,
                    event_id,
                    clean_err,
                )
                dl_id = compute_dead_letter_id(wire_msg.envelope.change_id, event_id)
                dl_record, _ = self._dead_letter_state.get_or_create(
                    dead_letter_id=dl_id,
                    original_event_id=event_id,
                    change_id=wire_msg.envelope.change_id,
                    correlation_id=wire_msg.envelope.correlation_id,
                    original_topic_id=wire_msg.topic_id,
                    failure_classification=classification,
                    raw_error=e,
                    attempts_made=1,
                    timestamp=datetime.now(timezone.utc),
                )
                return EventConsumeResult(
                    disposition=EventDeliveryDisposition.ACCEPT,
                    event_id=event_id,
                    message_id=message_id,
                    transport="GOOGLE_PUBSUB",
                    callback_invoked=True,
                    error_message=sanitize_error_message(f"Callback execution failure: {e}"),
                    dead_letter_record=dl_record,
                )

        elif disposition == EventDeliveryDisposition.DUPLICATE:
            logger.info("Duplicate event %s received; skipping callback", event_id)
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.DUPLICATE,
                event_id=event_id,
                message_id=message_id,
                transport="GOOGLE_PUBSUB",
                callback_invoked=False,
            )

        elif disposition == EventDeliveryDisposition.OUT_OF_ORDER:
            logger.warning(
                "Out-of-order event %s received (missing cause); skipping callback",
                event_id,
            )
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.OUT_OF_ORDER,
                event_id=event_id,
                message_id=message_id,
                transport="GOOGLE_PUBSUB",
                callback_invoked=False,
                error_message="Causal predecessor not yet observed",
            )

        else:  # CONFLICT
            logger.error("Conflicting event %s received; skipping callback", event_id)
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.CONFLICT,
                event_id=event_id,
                message_id=message_id,
                transport="GOOGLE_PUBSUB",
                callback_invoked=False,
                error_message="Event conflicts with observed state or idempotency key",
            )


class GooglePubSubDeadLetterConsumer:
    """Consumer for Google Cloud Pub/Sub dead-letter subscription.

    Converts messages delivered to the Google Pub/Sub dead-letter queue
    (changemesh-dead-letter-sub-v1) into canonical DeadLetterEventRecord and
    TerminalFailureHandoff artifacts.

    Preserves authority invariant (human_authority_required=False) and secrecy.
    Supports process-local replay idempotency so replayed messages do not
    manufacture duplicate handoffs.
    """

    def __init__(
        self,
        project_id: str,
        subscription_id: str = "changemesh-dead-letter-sub-v1",
        subscriber_client: Optional[Any] = None,
        dead_letter_state: Optional[ProcessLocalDeadLetterState] = None,
    ) -> None:
        if not project_id or not project_id.strip():
            raise ValueError("project_id must not be blank")
        if not subscription_id or not subscription_id.strip():
            raise ValueError("subscription_id must not be blank")

        self.project_id = project_id.strip()
        self.subscription_id = subscription_id.strip()
        self._client = subscriber_client
        self._dead_letter_state = (
            dead_letter_state if dead_letter_state is not None else get_default_dead_letter_state()
        )

    def process_dead_letter_delivery(
        self,
        raw_data: bytes,
        attributes: Mapping[str, str],
        message_id: str,
        delivery_attempt: Optional[int] = None,
        failure_reason: Optional[str] = None,
    ) -> DeadLetterEventRecord:
        """Process a message from the dead-letter queue into a DeadLetterEventRecord.

        Reconstructs canonical event identity:
        1. Preferred: deserialize EventWireMessage from raw_data.
        2. Fallback: extract required identity fields (event_id, change_id,
           correlation_id, topic_id) from trusted transport attributes.
        3. If canonical identity cannot be reconstructed: FAIL CLOSED (raises ValueError).
           Zero placeholder identity is ever fabricated.

        Delivery attempt handling:
        - If delivery_attempt is provided and positive: preserved as approximate
          provider attempt count.
        - If delivery_attempt is absent/None/<=0: set to 0 (indicating provider count unavailable).
          Never fabricates a configured policy maximum (e.g. 5) as an observed execution fact.
        """
        original_event_id: Optional[str] = None
        change_id: Optional[str] = None
        correlation_id: Optional[str] = None
        original_topic_id: Optional[str] = None

        # A. Preferred path: Parse EventWireMessage from raw bytes
        if raw_data:
            try:
                wire_msg = EventWireMessage.from_bytes(raw_data)
                original_event_id = wire_msg.envelope.event_id
                change_id = wire_msg.envelope.change_id
                correlation_id = wire_msg.envelope.correlation_id
                original_topic_id = wire_msg.topic_id
            except Exception:
                pass

        # B. Fallback path: Recover from trusted transport attributes if unparsed
        if not (original_event_id and change_id and correlation_id and original_topic_id):
            attr_event_id = attributes.get("event_id")
            attr_change_id = attributes.get("change_id")
            attr_correlation_id = attributes.get("correlation_id")
            attr_topic_id = attributes.get("topic_id")

            if (
                attr_event_id
                and attr_event_id.strip()
                and attr_change_id
                and attr_change_id.strip()
                and attr_correlation_id
                and attr_correlation_id.strip()
                and attr_topic_id
                and attr_topic_id.strip()
            ):
                original_event_id = attr_event_id.strip()
                change_id = attr_change_id.strip()
                correlation_id = attr_correlation_id.strip()
                original_topic_id = attr_topic_id.strip()

        # C. If canonical identity cannot be reconstructed: FAIL CLOSED
        if not (original_event_id and change_id and correlation_id and original_topic_id):
            missing_fields: list[str] = []
            if not original_event_id:
                missing_fields.append("event_id")
            if not change_id:
                missing_fields.append("change_id")
            if not correlation_id:
                missing_fields.append("correlation_id")
            if not original_topic_id:
                missing_fields.append("topic_id")
            raise ValueError(
                "Cannot reconstruct canonical dead-letter event identity: "
                f"missing required identity fields {missing_fields}. "
                "Identity facts must never be fabricated."
            )

        # Handle delivery attempt without false precision
        if delivery_attempt is not None and delivery_attempt > 0:
            attempts_made = delivery_attempt
            default_err = (
                f"Terminal delivery received from Google Pub/Sub DLQ "
                f"(approximate provider attempts: {delivery_attempt})"
            )
        else:
            attempts_made = 0
            default_err = (
                "Terminal delivery received from Google Pub/Sub DLQ "
                "(provider attempt count unavailable)"
            )

        raw_err = failure_reason or default_err
        clean_err = sanitize_error_message(str(raw_err))

        dl_id = compute_dead_letter_id(change_id, original_event_id)

        rec, _ = self._dead_letter_state.get_or_create(
            dead_letter_id=dl_id,
            original_event_id=original_event_id,
            change_id=change_id,
            correlation_id=correlation_id,
            original_topic_id=original_topic_id,
            failure_classification=FailureClassification.TERMINAL_EXHAUSTED,
            raw_error=clean_err,
            attempts_made=attempts_made,
            timestamp=datetime.now(timezone.utc),
        )
        return rec
