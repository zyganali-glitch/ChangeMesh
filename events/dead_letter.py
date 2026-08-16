"""ChangeMesh dead-letter handling and terminal failure handoff generator.

P-09.03: Structured dead-letter event record, terminal failure handoff artifact,
and routing logic for poison or exhausted events.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.conventions import (
    UtcDateTime,
    normalize_utc_datetime,
)
from events.retry import FailureClassification, sanitize_error_message
from events.wire import scan_payload_for_secrets

DEAD_LETTER_SCHEMA_VERSION = "1.0.0"


def compute_dead_letter_id(change_id: str, event_id: str) -> str:
    """Compute deterministic dead-letter ID for process-local handoff idempotency."""
    digest = hashlib.sha256(f"{change_id}:{event_id}".encode("utf-8")).hexdigest()[:12]
    return f"dl-{digest}"


class TerminalFailureHandoff(BaseModel):
    """Deterministic failure diagnostic handoff artifact for terminal event failures.

    Authority invariant: Retry exhaustion NEVER manufactures human authority.
    human_authority_required is strictly False.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = DEAD_LETTER_SCHEMA_VERSION
    change_id: str
    correlation_id: str
    original_event_id: str
    original_topic_id: str
    failure_classification: FailureClassification
    failure_reason: str
    total_attempts_made: int
    terminal_state: str = "DEAD_LETTERED"
    human_authority_required: bool = False
    timestamp: UtcDateTime

    @field_validator(
        "schema_version",
        "change_id",
        "correlation_id",
        "original_event_id",
        "original_topic_id",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()

    @model_validator(mode="after")
    def _validate_secrecy_and_authority(self) -> TerminalFailureHandoff:
        if self.human_authority_required is not False:
            raise ValueError(
                "human_authority_required must strictly be False for event dead-letters"
            )
        scan_payload_for_secrets(self.model_dump(mode="json"))
        return self


class DeadLetterEventRecord(BaseModel):
    """Canonical representation of an event routed to the dead-letter sink."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = DEAD_LETTER_SCHEMA_VERSION
    dead_letter_id: str
    original_event_id: str
    change_id: str
    correlation_id: str
    original_topic_id: str
    dead_letter_topic_id: str = "changemesh-dead-letter-v1"
    failure_classification: FailureClassification
    sanitized_failure_reason: str
    attempts_made: int
    timestamp: UtcDateTime
    handoff: TerminalFailureHandoff

    @field_validator(
        "dead_letter_id",
        "original_event_id",
        "change_id",
        "correlation_id",
        "original_topic_id",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


def build_dead_letter_record(
    dead_letter_id: str,
    original_event_id: str,
    change_id: str,
    correlation_id: str,
    original_topic_id: str,
    failure_classification: FailureClassification,
    raw_error: Exception | str,
    attempts_made: int,
    timestamp: UtcDateTime,
) -> DeadLetterEventRecord:
    """Construct a canonical, sanitized DeadLetterEventRecord and TerminalFailureHandoff."""
    clean_reason = sanitize_error_message(str(raw_error))
    ts = normalize_utc_datetime(timestamp)

    handoff = TerminalFailureHandoff(
        change_id=change_id,
        correlation_id=correlation_id,
        original_event_id=original_event_id,
        original_topic_id=original_topic_id,
        failure_classification=failure_classification,
        failure_reason=clean_reason,
        total_attempts_made=attempts_made,
        terminal_state="DEAD_LETTERED",
        human_authority_required=False,
        timestamp=ts,
    )

    return DeadLetterEventRecord(
        dead_letter_id=dead_letter_id,
        original_event_id=original_event_id,
        change_id=change_id,
        correlation_id=correlation_id,
        original_topic_id=original_topic_id,
        dead_letter_topic_id="changemesh-dead-letter-v1",
        failure_classification=failure_classification,
        sanitized_failure_reason=clean_reason,
        attempts_made=attempts_made,
        timestamp=ts,
        handoff=handoff,
    )


class ProcessLocalDeadLetterState:
    """Bounded in-memory tracking for process-local terminal handoff idempotency.

    Guarantees that replaying the same terminal event identity within the retained
    capacity window of the current process runtime returns the existing logical
    DeadLetterEventRecord without manufacturing duplicate handoffs.

    Bounded FIFO capacity eviction:
    - max_records must be explicitly valid and strictly positive (>= 1).
    - When capacity is reached, the oldest record is evicted to retain at most
      max_records entries in memory.
    - Replay idempotency is strictly guaranteed within the retained bounded window.
    - This is process-local and in-memory only (not durable P-10 Firestore persistence).
    """

    def __init__(self, max_records: int = 1000) -> None:
        if max_records < 1:
            raise ValueError("max_records must be strictly positive (>= 1)")
        self._lock = threading.Lock()
        self._records: OrderedDict[tuple[str, str], DeadLetterEventRecord] = OrderedDict()
        self._max_records = max_records

    @property
    def max_records(self) -> int:
        return self._max_records

    @property
    def total_records(self) -> int:
        with self._lock:
            return len(self._records)

    def get_record(self, change_id: str, event_id: str) -> Optional[DeadLetterEventRecord]:
        with self._lock:
            return self._records.get((change_id, event_id))

    def get_or_create(
        self,
        dead_letter_id: str,
        original_event_id: str,
        change_id: str,
        correlation_id: str,
        original_topic_id: str,
        failure_classification: FailureClassification,
        raw_error: Exception | str,
        attempts_made: int,
        timestamp: UtcDateTime,
    ) -> Tuple[DeadLetterEventRecord, bool]:
        """Get existing record or create and store a new one in the bounded window.

        Returns (record, is_new).
        """
        key = (change_id, original_event_id)
        with self._lock:
            if key in self._records:
                return self._records[key], False

            record = build_dead_letter_record(
                dead_letter_id=dead_letter_id,
                original_event_id=original_event_id,
                change_id=change_id,
                correlation_id=correlation_id,
                original_topic_id=original_topic_id,
                failure_classification=failure_classification,
                raw_error=raw_error,
                attempts_made=attempts_made,
                timestamp=timestamp,
            )
            # Evict oldest entry when capacity is reached
            while len(self._records) >= self._max_records:
                self._records.popitem(last=False)
            self._records[key] = record
            return record, True

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


_DEFAULT_DEAD_LETTER_STATE: Optional[ProcessLocalDeadLetterState] = None
_DEFAULT_STATE_LOCK = threading.Lock()


def get_default_dead_letter_state() -> ProcessLocalDeadLetterState:
    """Return process-wide default ProcessLocalDeadLetterState singleton."""
    global _DEFAULT_DEAD_LETTER_STATE
    with _DEFAULT_STATE_LOCK:
        if _DEFAULT_DEAD_LETTER_STATE is None:
            _DEFAULT_DEAD_LETTER_STATE = ProcessLocalDeadLetterState()
        return _DEFAULT_DEAD_LETTER_STATE
