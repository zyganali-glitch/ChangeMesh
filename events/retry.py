"""ChangeMesh event delivery retry schedule and classification.

P-09.03: Single canonical retry policy for event delivery, differentiating
transient retryable failures from deterministic non-retryable errors.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class FailureClassification(str, Enum):
    """Classification of event processing failures."""

    TRANSIENT_RETRYABLE = "TRANSIENT_RETRYABLE"
    DETERMINISTIC_INVALID = "DETERMINISTIC_INVALID"
    TERMINAL_EXHAUSTED = "TERMINAL_EXHAUSTED"


# Deterministic non-retryable error markers
_DETERMINISTIC_ERROR_MARKERS = (
    "schema validation",
    "unsupported wire_version",
    "malformed json",
    "secret or credential",
    "prohibited credential",
    "extra inputs are not permitted",
    "conflict",
    "invalid event",
    "causal cycle",
    "unresolved causal predecessor",
    "correlation id mismatch",
    "idempotency collision",
    "event id conflict",
    "cross-change event",
)


def classify_failure(exc: Exception | str) -> FailureClassification:
    """Deterministically classify an exception or error string as retryable or not."""
    msg = str(exc).lower()
    for marker in _DETERMINISTIC_ERROR_MARKERS:
        if marker in msg:
            return FailureClassification.DETERMINISTIC_INVALID
    return FailureClassification.TRANSIENT_RETRYABLE


def sanitize_error_message(msg: str) -> str:
    """Sanitize error messages to ensure no tokens or passwords leak into logs/artifacts."""
    sanitized = re.sub(
        r"(?:api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{8,}['\"]?",
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
    sanitized = re.sub(
        r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b",
        "[REDACTED_JWT]",
        sanitized,
    )
    return sanitized


class EventRetryPolicy(BaseModel):
    """Canonical bounded retry schedule policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    backoff_multiplier: float = 2.0

    @field_validator("max_attempts")
    @classmethod
    def _validate_max_attempts(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError(f"max_attempts must be between 1 and 10, got {v}")
        return v

    @field_validator("initial_backoff_seconds", "max_backoff_seconds", "backoff_multiplier")
    @classmethod
    def _validate_positive(cls, v: float) -> float:
        if v <= 0 or not math.isfinite(v):
            raise ValueError("Backoff parameters must be strictly positive and finite")
        return v

    @model_validator(mode="after")
    def _validate_backoff_order(self) -> EventRetryPolicy:
        if self.initial_backoff_seconds > self.max_backoff_seconds:
            raise ValueError("initial_backoff_seconds cannot exceed max_backoff_seconds")
        return self

    def compute_backoff_delay(self, attempt_index: int) -> float:
        """Compute deterministic backoff delay (in seconds) for a given 0-indexed attempt."""
        if attempt_index < 0:
            raise ValueError(f"attempt_index must be non-negative, got {attempt_index}")
        delay = self.initial_backoff_seconds * (self.backoff_multiplier**attempt_index)
        return min(delay, self.max_backoff_seconds)


class RetryAttemptRecord(BaseModel):
    """Record of a single execution attempt during event dispatch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_number: int
    classification: FailureClassification
    error_message: str
    backoff_delay_seconds: float


class RetryExecutionResult(BaseModel):
    """Result of executing an operation under the canonical retry policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    succeeded: bool
    total_attempts: int
    final_classification: Optional[FailureClassification] = None
    attempts: Sequence[RetryAttemptRecord]
    result: Optional[Any] = None
    terminal_error: Optional[str] = None
    dead_letter_record: Optional[Any] = None


def execute_with_retry(
    fn: Callable[[], Any],
    policy: Optional[EventRetryPolicy] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    dead_letter_context: Optional[Mapping[str, Any]] = None,
) -> RetryExecutionResult:
    """Execute a callable with deterministic bounded retries (local/test retry engine).

    Note: This is the local and test execution retry engine. Google Cloud Pub/Sub
    transport owns its own distributed redelivery and retry runtime via subscription
    policies and does NOT wrap message receipt in execute_with_retry.

    Non-retryable (DETERMINISTIC_INVALID) errors fail on attempt 1 with zero retries.
    Transient retryable errors retry up to policy.max_attempts.
    When execution terminates in failure (either DETERMINISTIC_INVALID or TERMINAL_EXHAUSTED),
    exactly one sanitized DeadLetterEventRecord and TerminalFailureHandoff is constructed.
    """
    from events.dead_letter import build_dead_letter_record

    pol = policy or EventRetryPolicy()
    attempt_records: list[RetryAttemptRecord] = []

    def _build_dl(
        classification: FailureClassification,
        raw_err: Exception | str,
        attempts: int,
    ) -> Any:
        ctx = dead_letter_context or {}
        return build_dead_letter_record(
            dead_letter_id=str(ctx.get("dead_letter_id") or f"dl-{uuid.uuid4().hex[:8]}"),
            original_event_id=str(ctx.get("event_id") or "evt-local-retry"),
            change_id=str(ctx.get("change_id") or "chg-local-retry"),
            correlation_id=str(ctx.get("correlation_id") or "corr-local-retry"),
            original_topic_id=str(ctx.get("topic_id") or "changemesh-retry-v1"),
            failure_classification=classification,
            raw_error=raw_err,
            attempts_made=attempts,
            timestamp=datetime.now(timezone.utc),
        )

    for attempt_idx in range(pol.max_attempts):
        attempt_num = attempt_idx + 1
        try:
            val = fn()
            attempt_records.append(
                RetryAttemptRecord(
                    attempt_number=attempt_num,
                    classification=FailureClassification.TRANSIENT_RETRYABLE,
                    error_message="success",
                    backoff_delay_seconds=0.0,
                )
            )
            return RetryExecutionResult(
                succeeded=True,
                total_attempts=attempt_num,
                attempts=attempt_records,
                result=val,
                dead_letter_record=None,
            )
        except Exception as e:
            classification = classify_failure(e)
            delay = (
                pol.compute_backoff_delay(attempt_idx) if attempt_num < pol.max_attempts else 0.0
            )

            clean_err = sanitize_error_message(str(e))
            attempt_records.append(
                RetryAttemptRecord(
                    attempt_number=attempt_num,
                    classification=classification,
                    error_message=clean_err,
                    backoff_delay_seconds=delay,
                )
            )

            # Non-retryable fails immediately on attempt 1 with zero retries
            if classification == FailureClassification.DETERMINISTIC_INVALID:
                dl_rec = _build_dl(FailureClassification.DETERMINISTIC_INVALID, e, attempt_num)
                return RetryExecutionResult(
                    succeeded=False,
                    total_attempts=attempt_num,
                    final_classification=FailureClassification.DETERMINISTIC_INVALID,
                    attempts=attempt_records,
                    terminal_error=clean_err,
                    dead_letter_record=dl_rec,
                )

            # If more attempts remain, invoke backoff sleep hook
            if attempt_num < pol.max_attempts:
                if sleep_fn is not None:
                    sleep_fn(delay)
            else:
                dl_rec = _build_dl(FailureClassification.TERMINAL_EXHAUSTED, e, pol.max_attempts)
                return RetryExecutionResult(
                    succeeded=False,
                    total_attempts=pol.max_attempts,
                    final_classification=FailureClassification.TERMINAL_EXHAUSTED,
                    attempts=attempt_records,
                    terminal_error=clean_err,
                    dead_letter_record=dl_rec,
                )

    dl_rec = _build_dl(
        FailureClassification.TERMINAL_EXHAUSTED, "Exceeded max attempts", pol.max_attempts
    )
    return RetryExecutionResult(
        succeeded=False,
        total_attempts=pol.max_attempts,
        final_classification=FailureClassification.TERMINAL_EXHAUSTED,
        attempts=attempt_records,
        terminal_error="Exceeded max attempts",
        dead_letter_record=dl_rec,
    )
