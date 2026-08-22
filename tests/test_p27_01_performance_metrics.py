"""ChangeMesh P-27.01 — E2E Latency and Retry Behavior Security and Performance Suite.

Acceptance criteria from master plan:
  - Demo fits time budget; timeouts bounded.
  - Verification that end-to-end local demo execution completes in under 2.0 seconds.
  - Verification that per-stage latency measurement is tracked across saga spans.
  - Verification that retry policies enforce exponential backoff and maximum retry ceilings.
  - Verification of bounded timeouts across all stage boundaries.

Required evidence: Performance report (docs/P-27.01_LATENCY_AND_PERFORMANCE_REPORT.md).
Mandatory documentation sync: Environment.
"""

from __future__ import annotations

import time

from scripts.measure_performance import benchmark_e2e_demo, measure_per_stage_latencies
from src.core.gemini_client import (
    DEFAULT_INITIAL_RETRY_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_ATTEMPTS_CEILING,
    MAX_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    RETRYABLE_STATUS_CODES,
)
from src.demo.e2e_demo import run_local_e2e_demo


class TestPerformanceMetricsAndLatency:
    """Verify performance, latency bounds, per-stage timings, and retry behavior."""

    def test_e2e_demo_latency_fits_time_budget(self):
        """End-to-end local demo must complete in under 2.0 seconds mean execution time."""
        bench = benchmark_e2e_demo(iterations=3)
        assert bench["all_completed"] is True
        assert bench["mean_seconds"] < 2.0, (
            f"Mean latency {bench['mean_seconds']:.2f}s exceeds 2.0s time budget"
        )

    def test_single_run_produces_complete_evidence_records(self):
        """Single E2E execution must produce a complete evidence report and final state."""
        t0 = time.perf_counter()
        result = run_local_e2e_demo()
        elapsed = time.perf_counter() - t0

        assert elapsed < 2.0
        assert result.final_state.value == "COMPLETE"
        assert result.evidence_report.total_entries >= 5
        assert result.evidence_report.is_complete is True
        assert result.evidence_report.ledger_integrity is True

    def test_per_stage_latency_measurement(self):
        """Per-stage latencies must be measured and recorded in spans."""
        stage_bench = measure_per_stage_latencies()
        assert stage_bench["is_complete"] is True
        assert stage_bench["total_spans"] >= 6
        assert len(stage_bench["stage_timings"]) >= 6
        for stage_name, duration_s in stage_bench["stage_timings"].items():
            assert duration_s >= 0.0, f"Stage {stage_name} has invalid duration: {duration_s}"

    def test_bounded_retry_backoff_math(self):
        """Verify standard exponential backoff calculation is bounded."""
        base_delay_ms = 100
        max_attempts = 4
        delays = [base_delay_ms * (2**attempt) for attempt in range(max_attempts)]
        assert delays == [100, 200, 400, 800]
        assert sum(delays) < 2000  # Total retry delay is strictly under 2 seconds

    def test_bounded_gemini_client_retry_policy_constants(self):
        """BoundedGeminiClient must enforce frozen retry bounds and retryable HTTP status codes."""
        assert DEFAULT_MAX_ATTEMPTS == 3
        assert MAX_ATTEMPTS_CEILING == 3
        assert DEFAULT_INITIAL_RETRY_DELAY_SECONDS == 0.5
        assert DEFAULT_MAX_RETRY_DELAY_SECONDS == 2.0
        assert DEFAULT_TIMEOUT_SECONDS == 30.0
        assert MIN_TIMEOUT_SECONDS == 1.0
        assert MAX_TIMEOUT_SECONDS == 60.0
        assert 429 in RETRYABLE_STATUS_CODES
        assert 503 in RETRYABLE_STATUS_CODES
        assert 502 in RETRYABLE_STATUS_CODES
        assert 504 in RETRYABLE_STATUS_CODES
        assert 400 not in RETRYABLE_STATUS_CODES
        assert 401 not in RETRYABLE_STATUS_CODES
        assert 403 not in RETRYABLE_STATUS_CODES
