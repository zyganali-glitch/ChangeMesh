"""ChangeMesh dead-letter handling and terminal failure handoff generator.

P-09.03: Structured dead-letter event record, terminal failure handoff artifact,
and routing logic for poison or exhausted events.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.conventions import (
    UtcDateTime,
    normalize_utc_datetime,
)
from events.retry import FailureClassification
from events.wire import scan_payload_for_secrets

DEAD_LETTER_SCHEMA_VERSION = "1.0.0"


def sanitize_error_message(msg: str) -> str:
    """Sanitize error messages to ensure no tokens or passwords leak into logs/artifacts."""
    # Redact common secret substrings if present
    sanitized = re.sub(
        r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*['\"][^'\"]+['\"]",
        "[REDACTED_SECRET]",
        msg,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"\bBearer\s+[A-Za-z0-9_\-\.]{10,}\b",
        "[REDACTED_BEARER]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"-{5}BEGIN[^-]+-{5}[\s\S]+?-{5}END[^-]+-{5}", "[REDACTED_KEY]", sanitized)
    sanitized = re.sub(
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b", "[REDACTED_TOKEN]", sanitized
    )
    return sanitized


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
