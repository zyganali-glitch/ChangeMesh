"""ChangeMesh domain contracts — provider-neutral event envelope.

P-05.05: Defines the canonical EventEnvelope schema carrying event
identity, change identity, causal chain, correlation, producer
provenance, schema version, and idempotency key.

Also defines EventDeliveryDisposition and classify_event_delivery for
deterministic duplicate/out-of-order/conflict classification.

Provider-neutral: no google.*, Pub/Sub, Firestore, ADK, or runtime
adapter imports.  Credential material is explicitly forbidden.

Timestamp is metadata, NOT causal authority.  Distributed clocks can
skew; causation relationships and deterministic delivery state own
causal ordering.
"""

from enum import Enum
from typing import Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.conventions import UtcDateTime


# ---------------------------------------------------------------------------
# EventDeliveryDisposition — small, bounded delivery classification
# ---------------------------------------------------------------------------

class EventDeliveryDisposition(str, Enum):
    """Deterministic delivery classification for a provider-neutral event.

    This enum captures the minimum useful vocabulary for classifying an
    incoming event against already-observed state.  It intentionally
    excludes transport/runtime states (ACK, NACK, DEAD_LETTER, RETRYING,
    PUBLISHED, CONSUMED) which belong to P-09 runtime.

    OUT_OF_ORDER means the causal predecessor required to
    deterministically admit this event has not yet been observed.
    It is NOT automatically FAIL, BLOCKED, or DEAD_LETTER.
    """
    ACCEPT = "ACCEPT"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    CONFLICT = "CONFLICT"


# ---------------------------------------------------------------------------
# EventEnvelope — immutable provider-neutral event identity/causal metadata
# ---------------------------------------------------------------------------

class EventEnvelope(BaseModel):
    """Canonical provider-neutral event envelope.

    Carries event identity, change identity, causal chain metadata,
    correlation identity, producer provenance, schema version, and
    idempotency key.

    Immutability: Once validated, the envelope is frozen and cannot be
    mutated in place.

    Credential boundary: No field may carry tokens, secrets, API keys,
    private keys, service account material, sessions, or clients.
    Environment architecture forbids credential material in event
    payloads.

    Timestamp boundary: ``timestamp`` is typed ``datetime`` metadata.
    P-05.06 owns canonical serialized format, locale, precision,
    hashing, and JSON representation.  Wall-clock timestamp is NOT
    causal authority.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    event_id: str
    change_id: str
    causation_id: Optional[str] = None
    correlation_id: str
    producer_revision: str
    timestamp: UtcDateTime
    idempotency_key: str

    # -- field validators: mandatory non-blank strings -----------------------

    @field_validator(
        "schema_version",
        "event_id",
        "change_id",
        "correlation_id",
        "producer_revision",
        "idempotency_key",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("causation_id")
    @classmethod
    def _causation_must_not_be_blank_if_present(
        cls, v: Optional[str], info
    ) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError("causation_id must not be blank")
        return v

    # -- model validator: self-causation rejection ---------------------------

    @model_validator(mode="after")
    def _reject_self_causation(self):
        """An event cannot causally produce itself."""
        if self.causation_id is not None and self.event_id == self.causation_id:
            raise ValueError(
                "Self-causation rejected: event_id cannot equal causation_id"
            )
        return self


# ---------------------------------------------------------------------------
# classify_event_delivery — pure, deterministic delivery classifier
# ---------------------------------------------------------------------------

def classify_event_delivery(
    incoming: EventEnvelope,
    seen_events: Mapping[str, EventEnvelope],
    seen_idempotency: Mapping[Tuple[str, str], str],
) -> EventDeliveryDisposition:
    """Classify an incoming event against already-observed state.

    This function is **pure**: it does not write state, read databases,
    call Pub/Sub, acknowledge messages, sleep, retry, create dead-letter
    records, or mutate its inputs.

    Parameters
    ----------
    incoming:
        The event envelope to classify.
    seen_events:
        Mapping of ``event_id -> EventEnvelope`` for already-observed
        events.
    seen_idempotency:
        Mapping of ``(change_id, idempotency_key) -> event_id`` for
        already-observed idempotency scopes.

    Returns
    -------
    EventDeliveryDisposition
        One of ACCEPT, DUPLICATE, OUT_OF_ORDER, or CONFLICT.

    Rules are applied in deterministic order:

    **RULE A — exact replay:**
    If ``incoming.event_id`` already exists and the stored envelope is
    exactly equal to ``incoming`` → ``DUPLICATE``.

    **RULE B — same event_id, different immutable content:**
    If ``event_id`` already exists but any immutable envelope field
    differs → ``CONFLICT``.

    **RULE C — idempotency-key collision inside the same change:**
    Idempotency identity is scoped at minimum by
    ``(change_id, idempotency_key)``.  If the same scoped key is
    already associated with a DIFFERENT ``event_id`` → ``CONFLICT``.

    **RULE D — causation ordering:**
    Root event (``causation_id is None``): if no duplicate/conflict
    condition exists → ``ACCEPT``.

    Child event (``causation_id is not None``): if its cause has not
    yet been observed in ``seen_events`` → ``OUT_OF_ORDER``.

    **RULE E — causal consistency:**
    If ``causation_id`` refers to an observed cause, enforce:
    ``incoming.change_id == cause.change_id`` and
    ``incoming.correlation_id == cause.correlation_id``.
    If either differs → ``CONFLICT``.

    If all checks pass → ``ACCEPT``.
    """
    # RULE A + B — event_id collision
    existing = seen_events.get(incoming.event_id)
    if existing is not None:
        if existing == incoming:
            return EventDeliveryDisposition.DUPLICATE
        # Any immutable field difference is a CONFLICT
        return EventDeliveryDisposition.CONFLICT

    # RULE C — idempotency-key collision inside the same change
    idem_key = (incoming.change_id, incoming.idempotency_key)
    prior_event_id = seen_idempotency.get(idem_key)
    if prior_event_id is not None and prior_event_id != incoming.event_id:
        return EventDeliveryDisposition.CONFLICT

    # RULE D — causation ordering
    if incoming.causation_id is None:
        # Root event with no duplicate/conflict → ACCEPT
        return EventDeliveryDisposition.ACCEPT

    # Child event — check causal predecessor
    cause = seen_events.get(incoming.causation_id)
    if cause is None:
        return EventDeliveryDisposition.OUT_OF_ORDER

    # RULE E — causal consistency
    if incoming.change_id != cause.change_id:
        return EventDeliveryDisposition.CONFLICT

    if incoming.correlation_id != cause.correlation_id:
        return EventDeliveryDisposition.CONFLICT

    return EventDeliveryDisposition.ACCEPT
