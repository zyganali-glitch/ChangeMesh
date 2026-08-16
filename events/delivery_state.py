"""ChangeMesh in-memory event delivery state tracker.

P-09.02: Bounded in-memory snapshot for local duplicate, conflict, and
out-of-order delivery classification.

CRITICAL OWNERSHIP BOUNDARY:
This state tracker is NON-DURABLE and intended for single-process runtime,
local execution, and testing. Cross-process durable saga state and persistent
idempotency storage belong strictly to P-10 (Firestore).
"""

from __future__ import annotations

import threading
from typing import Dict, Mapping, Tuple

from domain.contracts.event_envelope import (
    EventDeliveryDisposition,
    EventEnvelope,
    classify_event_delivery,
)


class InMemoryDeliveryState:
    """Bounded, thread-safe in-memory state tracker for event delivery classification."""

    def __init__(self, max_capacity: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._max_capacity = max_capacity
        self._seen_events: Dict[str, EventEnvelope] = {}
        self._seen_idempotency: Dict[Tuple[str, str], str] = {}

    @property
    def seen_events(self) -> Mapping[str, EventEnvelope]:
        with self._lock:
            return dict(self._seen_events)

    @property
    def seen_idempotency(self) -> Mapping[Tuple[str, str], str]:
        with self._lock:
            return dict(self._seen_idempotency)

    def classify(self, incoming: EventEnvelope) -> EventDeliveryDisposition:
        """Classify incoming envelope against currently observed state."""
        with self._lock:
            return classify_event_delivery(
                incoming=incoming,
                seen_events=self._seen_events,
                seen_idempotency=self._seen_idempotency,
            )

    def record_if_accepted(self, incoming: EventEnvelope) -> EventDeliveryDisposition:
        """Atomically classify and record event if disposition is ACCEPT.

        Returns the classified disposition. If ACCEPT, updates internal maps.
        """
        with self._lock:
            disposition = classify_event_delivery(
                incoming=incoming,
                seen_events=self._seen_events,
                seen_idempotency=self._seen_idempotency,
            )
            if disposition == EventDeliveryDisposition.ACCEPT:
                self._seen_events[incoming.event_id] = incoming
                key = (incoming.change_id, incoming.idempotency_key)
                self._seen_idempotency[key] = incoming.event_id
            return disposition

    def reset(self) -> None:
        """Clear all observed events and idempotency keys."""
        with self._lock:
            self._seen_events.clear()
            self._seen_idempotency.clear()
