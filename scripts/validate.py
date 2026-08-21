#!/usr/bin/env python3
"""ChangeMesh Root Validation and Release Gate Script (P-25.06).

One single deterministic command that executes all read-only release gates
and produces a clear, auditable summary with explicit PASS / FAIL / NOT_RUN states.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class GateResult:
    name: str
    target: str
    mode: str
    status: str  # PASS, FAIL, NOT_RUN, WARN
    duration_s: float
    details: str = ""


def run_gate(cmd: List[str], name: str, target: str, mode: str) -> GateResult:
    """Run a single subprocess gate and return typed GateResult."""
    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        duration = time.perf_counter() - start_time
        if proc.returncode == 0:
            return GateResult(
                name=name,
                target=target,
                mode=mode,
                status="PASS",
                duration_s=duration,
                details="Completed cleanly with 0 errors.",
            )
        else:
            first_err = (
                (proc.stderr or proc.stdout or "Non-zero exit code").strip().splitlines()[-1]
            )
            return GateResult(
                name=name,
                target=target,
                mode=mode,
                status="FAIL",
                duration_s=duration,
                details=first_err[:80],
            )
    except Exception as e:
        duration = time.perf_counter() - start_time
        return GateResult(
            name=name,
            target=target,
            mode=mode,
            status="FAIL",
            duration_s=duration,
            details=str(e)[:80],
        )


def run_e2e_demo_gate() -> GateResult:
    """Run in-process synthetic E2E demo gate."""
    start_time = time.perf_counter()
    try:
        from src.demo.e2e_demo import run_local_e2e_demo

        result = run_local_e2e_demo()
        duration = time.perf_counter() - start_time
        return GateResult(
            name="Synthetic Enterprise E2E Demo",
            target="src/demo/e2e_demo.py",
            mode="SIMULATION",
            status="PASS" if result.final_state.value == "COMPLETE" else "FAIL",
            duration_s=duration,
            details=f"State={result.final_state.value}, Digest={result.demo_digest[:16]}...",
        )
    except Exception as e:
        duration = time.perf_counter() - start_time
        return GateResult(
            name="Synthetic Enterprise E2E Demo",
            target="src/demo/e2e_demo.py",
            mode="SIMULATION",
            status="FAIL",
            duration_s=duration,
            details=str(e)[:80],
        )


def run_full_validation(allow_live_write: bool = False) -> int:
    """Execute all release gates and output clean audit report."""
    print("=" * 80)
    print(" CHANGEMESH -- ROOT RELEASE VALIDATION & GOVERNANCE GATE (P-25.06)")
    print("=" * 80)
    print(f" Repository Root : {REPO_ROOT}")
    print(" Canonical Model : gemini-3.6-flash")
    print(" Execution Mode  : READ-ONLY (Zero Cloud Mutation)")
    print("=" * 80)

    gates: List[GateResult] = []

    # 1. Source Formatting Gate
    print("\n[1/7] Running Source Formatting Gate (ruff format --check)...")
    g1 = run_gate(
        ["uv", "run", "ruff", "format", "--check", "."],
        "Format Gate",
        "Codebase (*.py)",
        "STATIC_ANALYSIS",
    )
    gates.append(g1)
    print(f"      -> {g1.status} ({g1.duration_s:.2f}s)")

    # 2. Source Linting Gate
    print("[2/7] Running Source Linting Gate (ruff check)...")
    g2 = run_gate(
        ["uv", "run", "ruff", "check", "."], "Lint Gate", "Codebase (*.py)", "STATIC_ANALYSIS"
    )
    gates.append(g2)
    print(f"      -> {g2.status} ({g2.duration_s:.2f}s)")

    # 3. Static Type-Checking Gate
    print("[3/7] Running Static Type-Checking Gate (mypy)...")
    g3 = run_gate(
        ["uv", "run", "mypy", "domain", "src", "integrations", "tests", "service_app.py"],
        "Type-Check Gate",
        "domain, src, integrations, tests",
        "STATIC_ANALYSIS",
    )
    gates.append(g3)
    print(f"      -> {g3.status} ({g3.duration_s:.2f}s)")

    # 4. Donor Manifest Integrity Gate
    print("[4/7] Running Donor Manifest Integrity Gate (donor_manifest_lint.py)...")
    g4 = run_gate(
        ["uv", "run", "python", "scripts/donor_manifest_lint.py"],
        "Donor Manifest Gate",
        "docs/DONOR_REUSE_MANIFEST.md",
        "DETERMINISTIC_GOVERNANCE",
    )
    gates.append(g4)
    print(f"      -> {g4.status} ({g4.duration_s:.2f}s)")

    # 5. Canonical Unit & Resilience Test Suite Gate
    print("[5/7] Running Test Suite Gate (pytest 1686 tests)...")
    g5 = run_gate(
        ["uv", "run", "pytest", "tests/", "--ignore=tests/test_gcp_access.py", "-q", "--tb=short"],
        "Test Matrix Gate",
        "tests/ (P-05 through P-25)",
        "FIXTURE / SIMULATION",
    )
    gates.append(g5)
    print(f"      -> {g5.status} ({g5.duration_s:.2f}s)")

    # 6. Synthetic Enterprise E2E Demo Gate
    print("[6/7] Running Synthetic Enterprise E2E Demo Gate...")
    g6 = run_e2e_demo_gate()
    gates.append(g6)
    print(f"      -> {g6.status} ({g6.duration_s:.2f}s)")

    # 7. Live Google Cloud Mutation Gate
    print("[7/7] Evaluating Live Google Cloud Mutation Gate...")
    if allow_live_write:
        g7 = run_gate(
            ["uv", "run", "python", "tests/test_gcp_access.py"],
            "Live Cloud Mutation Gate",
            "Google Cloud (europe-west3)",
            "LIVE_WRITE",
        )
    else:
        g7 = GateResult(
            name="Live Cloud Mutation Gate",
            target="Google Cloud (europe-west3)",
            mode="LIVE_WRITE",
            status="NOT_RUN",
            duration_s=0.0,
            details="Protected: requires explicit --live-write-danger flag and live credentials.",
        )
    gates.append(g7)
    print(f"      -> {g7.status} ({g7.duration_s:.2f}s)")

    # Summary Report Table
    print("\n" + "=" * 80)
    print(f"{'RELEASE GATE':<32} | {'MODE':<16} | {'STATUS':<9} | {'TIME':<7} | {'DETAILS'}")
    print("-" * 80)

    has_failures = False
    for g in gates:
        if g.status == "FAIL":
            has_failures = True
        print(f"{g.name:<32} | {g.mode:<16} | {g.status:<9} | {g.duration_s:5.2f}s | {g.details}")

    print("=" * 80)

    if has_failures:
        print(" OVERALL VERDICT: RELEASE GATE FAILED [FAIL]")
        print("=" * 80)
        return 1
    else:
        print(" OVERALL VERDICT: ALL MANDATORY READ-ONLY GATES PASSED [PASS]")
        print(" READY FOR JUDGE EVALUATION & RECORDING QA")
        print("=" * 80)
        return 0


if __name__ == "__main__":
    allow_live = "--live-write-danger" in sys.argv
    sys.exit(run_full_validation(allow_live_write=allow_live))
