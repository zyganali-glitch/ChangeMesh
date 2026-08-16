"""ChangeMesh Google Cloud Pub/Sub provider adapter.

P-09.02: Provider-specific transport adapter for Google Pub/Sub publishing
and consuming behind provider-neutral EventPublisher and EventConsumer protocols.

Google SDK types and imports are strictly confined to this module.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from domain.contracts.event_envelope import EventDeliveryDisposition
from events.consumer import EventConsumer, EventConsumeResult
from events.dead_letter import build_dead_letter_record
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
            logger.error("Failed to publish message to topic %s: %s", topic_path, e)
            return EventPublishResult(
                status="FAILED",
                message_id="none",
                topic_id=message.topic_id,
                event_id=message.envelope.event_id,
                transport="GOOGLE_PUBSUB",
                error_message=sanitize_error_message(str(e)),
            )


class GooglePubSubConsumer(EventConsumer):
    """Google Cloud Pub/Sub consumer adapter with pre-dispatch validation and dedup."""

    def __init__(
        self,
        project_id: str,
        subscription_id: str,
        subscriber_client: Optional[Any] = None,
        delivery_state: Optional[InMemoryDeliveryState] = None,
    ) -> None:
        if not project_id or not project_id.strip():
            raise ValueError("project_id must not be blank")
        if not subscription_id or not subscription_id.strip():
            raise ValueError("subscription_id must not be blank")

        self.project_id = project_id.strip()
        self.subscription_id = subscription_id.strip()
        self.delivery_state = delivery_state

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
            logger.warning("Message %s failed schema validation: %s", message_id, e)
            return EventConsumeResult(
                disposition=EventDeliveryDisposition.CONFLICT,
                event_id="malformed",
                message_id=message_id,
                transport="GOOGLE_PUBSUB",
                callback_invoked=False,
                error_message=sanitize_error_message(f"Schema validation error: {e}"),
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
                if classification == FailureClassification.TRANSIENT_RETRYABLE:
                    logger.warning(
                        "Transient failure in callback for message %s (event %s); "
                        "raising to NACK transport: %s",
                        message_id,
                        event_id,
                        e,
                    )
                    raise e

                logger.error(
                    "Callback failed with deterministic error for message %s (event %s): %s",
                    message_id,
                    event_id,
                    e,
                )
                dl_record = build_dead_letter_record(
                    dead_letter_id=f"dl-{uuid.uuid4().hex[:8]}",
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
