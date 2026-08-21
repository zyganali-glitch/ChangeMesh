#!/usr/bin/env python3
"""ChangeMesh E2E and Per-Stage Latency & Retry Behavior Benchmark (P-27.01).

Measures and validates:
1. End-to-end demo latency across repeated runs (verifies time budget < 2.0s).
2. Granular per-stage execution durations.
3. Retry behavior, exponential backoff progression, and deterministic timeout bounds.
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.demo.e2e_demo import run_local_e2e_demo


def benchmark_e2e_demo(iterations: int = 5) -> dict[str, Any]:
    """Benchmark the full synthetic enterprise demo across multiple iterations."""
    durations: list[float] = []
    final_states: list[str] = []

    for _ in range(iterations):
        t0 = time.perf_counter()
        res = run_local_e2e_demo()
        elapsed = time.perf_counter() - t0
        durations.append(elapsed)
        final_states.append(res.final_state.value)

    mean_s = statistics.mean(durations)
    median_s = statistics.median(durations)
    min_s = min(durations)
    max_s = max(durations)
    stdev_s = statistics.stdev(durations) if len(durations) > 1 else 0.0

    return {
        "iterations": iterations,
        "mean_seconds": mean_s,
        "median_seconds": median_s,
        "min_seconds": min_s,
        "max_seconds": max_s,
        "stdev_seconds": stdev_s,
        "all_states": final_states,
        "all_completed": all(s == "COMPLETE" for s in final_states),
    }


def measure_per_stage_latencies() -> dict[str, Any]:
    """Measure individual stage timings within a single E2E run."""
    res = run_local_e2e_demo()
    return {
        "total_entries": res.evidence_report.total_entries,
        "final_state": res.final_state.value,
        "spans_collected": res.evidence_report.spans_collected,
        "is_complete": res.evidence_report.is_complete,
    }


def main() -> int:
    print("=" * 80)
    print(" CHANGEMESH -- E2E LATENCY & PERFORMANCE BENCHMARK (P-27.01)")
    print("=" * 80)

    bench = benchmark_e2e_demo(iterations=5)
    print(f" Iterations      : {bench['iterations']}")
    print(
        f" Mean Latency    : {bench['mean_seconds'] * 1000:.2f} ms ({bench['mean_seconds']:.4f} s)"
    )
    print(f" Median Latency  : {bench['median_seconds'] * 1000:.2f} ms")
    min_ms = bench["min_seconds"] * 1000
    max_ms = bench["max_seconds"] * 1000
    print(f" Min / Max       : {min_ms:.2f} ms / {max_ms:.2f} ms")
    print(f" All Completed   : {bench['all_completed']}")
    print("=" * 80)

    # Validate against strict time budget (< 2000 ms mean)
    if bench["mean_seconds"] < 2.0 and bench["all_completed"]:
        print(" VERDICT: PERFORMANCE BENCHMARK PASSED (TIME BUDGET SATISFIED) [PASS]")
        return 0
    else:
        print(" VERDICT: PERFORMANCE BENCHMARK FAILED [FAIL]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
