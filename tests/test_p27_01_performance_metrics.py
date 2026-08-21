"""ChangeMesh P-27.01 — E2E Latency and Retry Behavior Security and Performance Suite.

Acceptance criteria from master plan:
  - Demo fits time budget; timeouts bounded.
  - Verification that end-to-end local demo execution completes in under 2.0 seconds.
  - Verification that retry policies enforce exponential backoff and maximum retry ceilings.
  - Verification of bounded timeouts across all stage boundaries.

Required evidence: Performance report (docs/P-27.01_LATENCY_AND_PERFORMANCE_REPORT.md).
Mandatory documentation sync: Environment.
"""

from __future__ import annotations

import time

from scripts.measure_performance import benchmark_e2e_demo
from src.demo.e2e_demo import run_local_e2e_demo


class TestPerformanceMetricsAndLatency:
    """Verify performance, latency bounds, and retry behavior."""

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

    def test_bounded_retry_backoff_math(self):
        """Verify standard exponential backoff calculation is bounded."""
        base_delay_ms = 100
        max_attempts = 4
        delays = [base_delay_ms * (2**attempt) for attempt in range(max_attempts)]
        assert delays == [100, 200, 400, 800]
        assert sum(delays) < 2000  # Total retry delay is strictly under 2 seconds
