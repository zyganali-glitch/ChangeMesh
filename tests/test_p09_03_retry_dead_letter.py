"""ChangeMesh P-09.03 Dedicated Test Suite — Retry Schedules and Dead-Letter Handling.

Validates:
1. Transient retryable failures succeed on subsequent attempts with backoff (no handoff).
2. Repeated retryable failures terminate at exact max_attempts bound with one handoff.
3. No further execution attempts occur after terminal bound is reached.
4. Deterministic non-retryable errors fail on attempt 1 with zero retries and one handoff.
5. Canonical DeadLetterEventRecord and TerminalFailureHandoff structure and immutability.
6. Authority invariant: human_authority_required is strictly False on retry exhaustion.
7. Secrecy invariant: credentials/tokens/keys are sanitized from error messages and handoffs.
8. EventRetryPolicy parameter validation and deterministic backoff computation.
9. Terminal result replay does not manufacture duplicate handoffs.
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


def test_transient_failure_then_success_no_handoff():
    """Verify operation that fails once with transient error succeeds with NO handoff."""
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
    assert res.dead_letter_record is None  # No handoff on success
    assert sleeps == [0.5]


def test_transient_exhaustion_creates_exactly_one_handoff():
    """Verify repeated retryable failure terminates after max_attempts with ONE handoff."""
    attempts = [0]
    sleeps: list[float] = []

    secret_key = "secret_token_12345678"

    def op() -> None:
        attempts[0] += 1
        raise TimeoutError(f"PubSub deadline exceeded with token={secret_key}")

    policy = EventRetryPolicy(max_attempts=3, initial_backoff_seconds=1.0)
    ctx = {
        "change_id": "chg-test-01",
        "correlation_id": "corr-test-01",
        "event_id": "evt-timeout",
        "topic_id": "changemesh-retry-v1",
    }
    res = execute_with_retry(op, policy=policy, sleep_fn=sleeps.append, dead_letter_context=ctx)

    assert res.succeeded is False
    assert res.total_attempts == 3
    assert attempts[0] == 3
    assert res.final_classification == FailureClassification.TERMINAL_EXHAUSTED
    assert len(res.attempts) == 3
    assert sleeps == [1.0, 2.0]

    # Exactly one dead-letter handoff created
    dl = res.dead_letter_record
    assert dl is not None
    assert dl.change_id == "chg-test-01"
    assert dl.original_event_id == "evt-timeout"
    assert dl.attempts_made == 3
    assert dl.failure_classification == FailureClassification.TERMINAL_EXHAUSTED
    assert dl.handoff.human_authority_required is False
    assert dl.handoff.terminal_state == "DEAD_LETTERED"

    # Secrecy: secret_key redacted from handoff
    assert secret_key not in dl.sanitized_failure_reason
    assert secret_key not in dl.handoff.failure_reason
    clean_err = dl.sanitized_failure_reason
    assert "[REDACTED_SECRET]" in clean_err or "[REDACTED_TOKEN]" in clean_err


def test_deterministic_error_fails_immediately_with_one_handoff():
    """Verify deterministic errors fail on attempt 1 with zero retries and exactly ONE handoff."""
    attempts = [0]
    sleeps: list[float] = []

    def op() -> None:
        attempts[0] += 1
        raise ValueError("Schema validation error: extra inputs are not permitted")

    policy = EventRetryPolicy(max_attempts=5)
    ctx = {
        "change_id": "chg-test-02",
        "correlation_id": "corr-test-02",
        "event_id": "evt-invalid-schema",
    }
    res = execute_with_retry(op, policy=policy, sleep_fn=sleeps.append, dead_letter_context=ctx)

    assert res.succeeded is False
    assert res.total_attempts == 1
    assert attempts[0] == 1
    assert res.final_classification == FailureClassification.DETERMINISTIC_INVALID
    assert sleeps == []  # Zero sleeps, zero retries

    dl = res.dead_letter_record
    assert dl is not None
    assert dl.change_id == "chg-test-02"
    assert dl.original_event_id == "evt-invalid-schema"
    assert dl.attempts_made == 1
    assert dl.failure_classification == FailureClassification.DETERMINISTIC_INVALID
    assert dl.handoff.human_authority_required is False


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


def test_terminal_failure_replay_idempotency():
    """Verify terminal failure replay does not manufacture duplicate handoffs.

    Semantics:
    1. Terminal event processed once -> creates one dead-letter handoff.
    2. Same terminal event identity replayed -> returns same existing logical handoff.
    3. Different terminal event -> creates separate independent handoff.
    4. human_authority_required is strictly False across all emissions.
    """
    from events.dead_letter import ProcessLocalDeadLetterState

    local_state = ProcessLocalDeadLetterState()
    policy = EventRetryPolicy(max_attempts=2)

    def failing_op_1() -> None:
        raise TimeoutError("Transient network timeout occurred")

    def failing_op_2() -> None:
        raise ValueError("Schema validation error: missing required envelope field")

    ctx_event_1 = {
        "change_id": "chg-replay-001",
        "correlation_id": "corr-replay-001",
        "event_id": "evt-terminal-replay-1",
        "topic_id": "changemesh-retry-v1",
    }

    ctx_event_2 = {
        "change_id": "chg-replay-001",
        "correlation_id": "corr-replay-002",
        "event_id": "evt-terminal-replay-2",
        "topic_id": "changemesh-lifecycle-v1",
    }

    # Step 1: Process terminal event 1 first time
    res1 = execute_with_retry(
        failing_op_1,
        policy=policy,
        sleep_fn=lambda _: None,
        dead_letter_context=ctx_event_1,
        dead_letter_state=local_state,
    )
    assert res1.succeeded is False
    assert res1.dead_letter_record is not None
    dl1 = res1.dead_letter_record
    assert dl1.original_event_id == "evt-terminal-replay-1"
    assert dl1.change_id == "chg-replay-001"
    assert dl1.handoff.human_authority_required is False
    assert local_state.total_records == 1

    # Step 2: Replay exact same terminal event identity
    res1_replay = execute_with_retry(
        failing_op_1,
        policy=policy,
        sleep_fn=lambda _: None,
        dead_letter_context=ctx_event_1,
        dead_letter_state=local_state,
    )
    assert res1_replay.succeeded is False
    assert res1_replay.dead_letter_record is not None
    dl1_replay = res1_replay.dead_letter_record

    # Must be exact same logical handoff and dead letter record (no second emission)
    assert dl1_replay.dead_letter_id == dl1.dead_letter_id
    assert dl1_replay.original_event_id == dl1.original_event_id
    assert dl1_replay.handoff.timestamp == dl1.handoff.timestamp
    assert dl1_replay.handoff.human_authority_required is False
    assert local_state.total_records == 1  # No duplicate record created

    # Step 3: Process different terminal event -> separate handoff
    res2 = execute_with_retry(
        failing_op_2,
        policy=policy,
        sleep_fn=lambda _: None,
        dead_letter_context=ctx_event_2,
        dead_letter_state=local_state,
    )
    assert res2.succeeded is False
    assert res2.dead_letter_record is not None
    dl2 = res2.dead_letter_record
    assert dl2.original_event_id == "evt-terminal-replay-2"
    assert dl2.dead_letter_id != dl1.dead_letter_id
    assert dl2.handoff.human_authority_required is False
    assert local_state.total_records == 2


def test_bounded_replay_state_capacity_and_fifo_eviction():
    """Verify ProcessLocalDeadLetterState strictly bounds capacity and evicts via FIFO."""
    from datetime import datetime, timezone

    import pytest

    from events.dead_letter import ProcessLocalDeadLetterState, compute_dead_letter_id
    from events.retry import FailureClassification

    # Invalid max_records (< 1) must fail closed
    with pytest.raises(ValueError, match="max_records must be strictly positive"):
        ProcessLocalDeadLetterState(max_records=0)

    with pytest.raises(ValueError, match="max_records must be strictly positive"):
        ProcessLocalDeadLetterState(max_records=-5)

    # Bounded capacity window of exactly 1
    state = ProcessLocalDeadLetterState(max_records=1)
    assert state.max_records == 1
    assert state.total_records == 0

    now = datetime.now(timezone.utc)

    # 1. Insert first event
    rec1, is_new1 = state.get_or_create(
        dead_letter_id=compute_dead_letter_id("chg-1", "evt-1"),
        original_event_id="evt-1",
        change_id="chg-1",
        correlation_id="corr-1",
        original_topic_id="changemesh-lifecycle-v1",
        failure_classification=FailureClassification.TERMINAL_EXHAUSTED,
        raw_error="err-1",
        attempts_made=3,
        timestamp=now,
    )
    assert is_new1 is True
    assert state.total_records == 1

    # 2. Replay evt-1 within retained bounded window -> returns same existing record
    rec1_replay, is_new1_replay = state.get_or_create(
        dead_letter_id=compute_dead_letter_id("chg-1", "evt-1"),
        original_event_id="evt-1",
        change_id="chg-1",
        correlation_id="corr-1",
        original_topic_id="changemesh-lifecycle-v1",
        failure_classification=FailureClassification.TERMINAL_EXHAUSTED,
        raw_error="err-1-dup",
        attempts_made=3,
        timestamp=now,
    )
    assert is_new1_replay is False
    assert rec1_replay.dead_letter_id == rec1.dead_letter_id
    assert rec1_replay.handoff.timestamp == rec1.handoff.timestamp
    assert state.total_records == 1

    # 3. Insert second event -> evicts evt-1 (oldest) and stores evt-2
    rec2, is_new2 = state.get_or_create(
        dead_letter_id=compute_dead_letter_id("chg-1", "evt-2"),
        original_event_id="evt-2",
        change_id="chg-1",
        correlation_id="corr-1",
        original_topic_id="changemesh-lifecycle-v1",
        failure_classification=FailureClassification.TERMINAL_EXHAUSTED,
        raw_error="err-2",
        attempts_made=3,
        timestamp=now,
    )
    assert is_new2 is True
    assert state.total_records == 1
    assert state.get_record("chg-1", "evt-1") is None  # Evicted
    assert state.get_record("chg-1", "evt-2") is not None

    # 4. Replay evt-2 -> returns same existing record
    rec2_replay, is_new2_replay = state.get_or_create(
        dead_letter_id=compute_dead_letter_id("chg-1", "evt-2"),
        original_event_id="evt-2",
        change_id="chg-1",
        correlation_id="corr-1",
        original_topic_id="changemesh-lifecycle-v1",
        failure_classification=FailureClassification.TERMINAL_EXHAUSTED,
        raw_error="err-2-dup",
        attempts_made=3,
        timestamp=now,
    )
    assert is_new2_replay is False
    assert rec2_replay.dead_letter_id == rec2.dead_letter_id
    assert state.total_records == 1
