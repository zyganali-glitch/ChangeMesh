"""ChangeMesh P-09.03 Dedicated Test Suite — Retry Schedules and Dead-Letter Handling.

Validates:
1. Transient retryable failures succeed on subsequent attempts with backoff.
2. Repeated retryable failures terminate at exact max_attempts bound.
3. No further execution attempts occur after terminal bound is reached.
4. Deterministic non-retryable errors fail immediately on attempt 1 with zero retries.
5. Canonical DeadLetterEventRecord and TerminalFailureHandoff structure and immutability.
6. Authority invariant: human_authority_required is strictly False on retry exhaustion.
7. Secrecy invariant: credentials/tokens are sanitized from error messages and handoffs.
8. EventRetryPolicy parameter validation and deterministic backoff computation.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from events.dead_letter import (
    DEAD_LETTER_SCHEMA_VERSION,
    TerminalFailureHandoff,
    build_dead_letter_record,
    sanitize_error_message,
)
from events.retry import (
    EventRetryPolicy,
    FailureClassification,
    classify_failure,
    execute_with_retry,
)


def test_retry_policy_validation_and_computation():
    """Verify EventRetryPolicy bounds and deterministic backoff calculations."""
    policy = EventRetryPolicy(
        max_attempts=4,
        initial_backoff_seconds=1.5,
        max_backoff_seconds=10.0,
        backoff_multiplier=2.0,
    )
    assert policy.compute_backoff_delay(0) == 1.5
    assert policy.compute_backoff_delay(1) == 3.0
    assert policy.compute_backoff_delay(2) == 6.0
    assert policy.compute_backoff_delay(3) == 10.0  # capped at max_backoff_seconds

    with pytest.raises(ValueError, match="between 1 and 10"):
        EventRetryPolicy(max_attempts=0)

    with pytest.raises(ValueError, match="strictly positive"):
        EventRetryPolicy(initial_backoff_seconds=-1.0)

    with pytest.raises(ValueError, match="cannot exceed max_backoff_seconds"):
        EventRetryPolicy(initial_backoff_seconds=20.0, max_backoff_seconds=10.0)


def test_transient_failure_then_success():
    """Verify operation that fails once with transient error succeeds on attempt 2."""
    attempts = [0]
    sleeps: list[float] = []

    def op() -> str:
        attempts[0] += 1
        if attempts[0] == 1:
            raise ConnectionResetError("Temporary network reset")
        return "success-value"

    policy = EventRetryPolicy(max_attempts=3, initial_backoff_seconds=0.5)
    res = execute_with_retry(op, policy=policy, sleep_fn=sleeps.append)

    assert res.succeeded is True
    assert res.total_attempts == 2
    assert res.result == "success-value"
    assert len(res.attempts) == 2
    assert res.attempts[0].classification == FailureClassification.TRANSIENT_RETRYABLE
    assert sleeps == [0.5]


def test_repeated_failure_reaches_exact_bound():
    """Verify repeated retryable failure terminates after exact max_attempts."""
    attempts = [0]
    sleeps: list[float] = []

    def op() -> None:
        attempts[0] += 1
        raise TimeoutError("PubSub deadline exceeded")

    policy = EventRetryPolicy(max_attempts=3, initial_backoff_seconds=1.0)
    res = execute_with_retry(op, policy=policy, sleep_fn=sleeps.append)

    assert res.succeeded is False
    assert res.total_attempts == 3
    assert attempts[0] == 3
    assert res.final_classification == FailureClassification.TERMINAL_EXHAUSTED
    assert len(res.attempts) == 3
    assert sleeps == [1.0, 2.0]  # Sleeps between attempt 1->2 and 2->3


def test_deterministic_error_fails_immediately():
    """Verify deterministic errors (schema, validation, secret, conflict) fail on attempt 1."""
    attempts = [0]
    sleeps: list[float] = []

    def op() -> None:
        attempts[0] += 1
        raise ValueError("Schema validation error: extra inputs are not permitted")

    policy = EventRetryPolicy(max_attempts=5)
    res = execute_with_retry(op, policy=policy, sleep_fn=sleeps.append)

    assert res.succeeded is False
    assert res.total_attempts == 1
    assert attempts[0] == 1
    assert res.final_classification == FailureClassification.DETERMINISTIC_INVALID
    assert sleeps == []  # Zero sleeps, zero retries


def test_classify_failure_markers():
    """Verify failure classification correctly categorizes various exception messages."""
    assert (
        classify_failure("Schema validation failed") == FailureClassification.DETERMINISTIC_INVALID
    )
    assert (
        classify_failure("Unsupported wire_version 2.0")
        == FailureClassification.DETERMINISTIC_INVALID
    )
    assert classify_failure("Malformed JSON") == FailureClassification.DETERMINISTIC_INVALID
    assert (
        classify_failure("Secret or credential detected")
        == FailureClassification.DETERMINISTIC_INVALID
    )
    assert (
        classify_failure("Event CONFLICT detected") == FailureClassification.DETERMINISTIC_INVALID
    )
    assert (
        classify_failure(TimeoutError("Socket timeout"))
        == FailureClassification.TRANSIENT_RETRYABLE
    )
    assert (
        classify_failure(ConnectionError("Connection refused"))
        == FailureClassification.TRANSIENT_RETRYABLE
    )


def test_dead_letter_record_construction_and_handoff():
    """Verify build_dead_letter_record produces canonical, valid records."""
    ts = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)
    record = build_dead_letter_record(
        dead_letter_id="dl-001",
        original_event_id="evt-100",
        change_id="chg-200",
        correlation_id="corr-300",
        original_topic_id="changemesh-lifecycle-v1",
        failure_classification=FailureClassification.TERMINAL_EXHAUSTED,
        raw_error="Max retries exhausted for topic changemesh-lifecycle-v1",
        attempts_made=3,
        timestamp=ts,
    )

    assert record.schema_version == DEAD_LETTER_SCHEMA_VERSION
    assert record.dead_letter_id == "dl-001"
    assert record.original_event_id == "evt-100"
    assert record.change_id == "chg-200"
    assert record.correlation_id == "corr-300"
    assert record.dead_letter_topic_id == "changemesh-dead-letter-v1"
    assert record.attempts_made == 3
    assert record.handoff.terminal_state == "DEAD_LETTERED"
    assert record.handoff.human_authority_required is False


def test_authority_invariant_dead_letter_never_manufactures_human_authority():
    """Verify TerminalFailureHandoff rejects human_authority_required=True."""
    ts = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="human_authority_required must strictly be False"):
        TerminalFailureHandoff(
            change_id="chg-1",
            correlation_id="corr-1",
            original_event_id="evt-1",
            original_topic_id="changemesh-lifecycle-v1",
            failure_classification=FailureClassification.TERMINAL_EXHAUSTED,
            failure_reason="Timeout",
            total_attempts_made=3,
            terminal_state="DEAD_LETTERED",
            human_authority_required=True,  # FORBIDDEN!
            timestamp=ts,
        )


def test_secrecy_invariant_error_sanitization():
    """Verify sensitive tokens and private keys are redacted from error messages."""
    raw_err = "Failed with Bearer secret_bearer_token_12345678 and api_key='secret_key_12345'"
    clean = sanitize_error_message(raw_err)
    assert "secret_bearer_token" not in clean
    assert "secret_key" not in clean
    assert "[REDACTED_SECRET]" in clean

    key_err = (
        "Key was: "
        + "-" * 5
        + "BEGIN RSA PRIVATE KEY"
        + "-" * 5
        + "\nMIIE...\n"
        + "-" * 5
        + "END RSA PRIVATE KEY"
        + "-" * 5
    )
    clean_key = sanitize_error_message(key_err)
    assert "MIIE" not in clean_key
    assert "[REDACTED_KEY]" in clean_key
