"""ChangeMesh ShadowLab Rehearsal Twin comprehensive test suite.

P-13: Tests scenario schemas, deterministic tool doubles, 7 standard fault
rehearsal scenarios, simulation evidence digests, and automatic plan corrections.
"""

from __future__ import annotations

import pytest

from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode
from src.shadowlab.runner import ShadowLabRunner
from src.shadowlab.scenarios import (
    FaultType,
    InjectedFault,
    ShadowScenario,
    compute_simulation_digest,
    get_standard_shadow_scenarios,
)
from src.shadowlab.tool_doubles import (
    SimulatedApiClient,
    SimulatedDatabaseClient,
    SimulatedGitClient,
)


# ============================================================================
# P-13.01: Scenario Schema & Injected Faults
# ============================================================================

def test_shadow_scenario_and_fault_schemas():
    scenarios = get_standard_shadow_scenarios()
    assert len(scenarios) == 7

    assert "SCENARIO_NORMAL_MIGRATION" in scenarios
    assert "SCENARIO_503_TRANSIENT_RECOVERY" in scenarios
    assert "SCENARIO_PARTIAL_INTERRUPTION_COMPENSATION" in scenarios
    assert "SCENARIO_STALE_APPROVAL" in scenarios
    assert "SCENARIO_PROMPT_INJECTION" in scenarios
    assert "SCENARIO_MISSING_ROLLBACK" in scenarios
    assert "SCENARIO_LEGACY_CLIENT_BREAK" in scenarios

    digest = compute_simulation_digest("TEST_SCENARIO", ["log line 1", "log line 2"])
    assert len(digest) == 64


# ============================================================================
# P-13.02: Tool Doubles Isolation & Simulation Labeling
# ============================================================================

def test_simulated_database_client_and_faults():
    fault = InjectedFault(
        fault_type=FaultType.DATABASE_LOCK_TIMEOUT,
        target_step="step_locked",
        failure_count=1,
        error_message="Lock timeout",
    )
    db = SimulatedDatabaseClient(injected_fault=fault)
    assert db.evidence_mode == ExecutionEvidenceMode.SIMULATION

    # Target step fails on first attempt
    ok1, msg1 = db.execute_ddl("CREATE INDEX idx_dummy ON users(email);", "step_locked")
    assert ok1 is False
    assert "Lock timeout" in msg1

    # Next attempt succeeds
    ok2, msg2 = db.execute_ddl("CREATE INDEX idx_dummy ON users(email);", "step_locked")
    assert ok2 is True

    db.close()


def test_simulated_api_client_and_503():
    fault = InjectedFault(
        fault_type=FaultType.HTTP_503_SERVICE_UNAVAILABLE,
        target_step="step_api",
        failure_count=2,
    )
    api = SimulatedApiClient(injected_fault=fault)
    assert api.evidence_mode == ExecutionEvidenceMode.SIMULATION

    # Attempts 1 and 2 return 503
    code1, _ = api.post("https://api.github.com", {}, "step_api")
    assert code1 == 503
    code2, _ = api.post("https://api.github.com", {}, "step_api")
    assert code2 == 503

    # Attempt 3 returns 200
    code3, resp3 = api.post("https://api.github.com", {}, "step_api")
    assert code3 == 200
    assert resp3["mode"] == "SIMULATION"


def test_simulated_git_client():
    git = SimulatedGitClient()
    assert git.evidence_mode == ExecutionEvidenceMode.SIMULATION

    assert git.create_branch("feature/new-branch") is True
    commit_sha = git.commit("feature/new-branch", "Test commit")
    assert commit_sha.startswith("sim-sha-")

    pr = git.create_pull_request("Test PR", "feature/new-branch")
    assert pr["mode"] == "SIMULATION"
    assert pr["state"] == "OPEN_DRAFT"


# ============================================================================
# P-13.03 - P-13.07: Rehearsal Scenarios Execution
# ============================================================================

def test_scenario_normal_migration():
    scenarios = get_standard_shadow_scenarios()
    outcome = ShadowLabRunner.run_scenario(scenarios["SCENARIO_NORMAL_MIGRATION"])
    assert outcome.passed is True
    assert outcome.evidence_mode == ExecutionEvidenceMode.SIMULATION
    assert outcome.evidence_state == EvidenceState.SIMULATED
    assert outcome.fault_recovered is False


def test_scenario_503_transient_recovery():
    scenarios = get_standard_shadow_scenarios()
    outcome = ShadowLabRunner.run_scenario(scenarios["SCENARIO_503_TRANSIENT_RECOVERY"])
    assert outcome.passed is True
    assert outcome.fault_recovered is True
    assert outcome.retries_attempted == 2


def test_scenario_partial_interruption_compensation():
    scenarios = get_standard_shadow_scenarios()
    outcome = ShadowLabRunner.run_scenario(scenarios["SCENARIO_PARTIAL_INTERRUPTION_COMPENSATION"])
    assert outcome.passed is True
    assert outcome.compensation_executed is True


def test_scenario_stale_approval():
    scenarios = get_standard_shadow_scenarios()
    outcome = ShadowLabRunner.run_scenario(scenarios["SCENARIO_STALE_APPROVAL"])
    assert outcome.passed is True


def test_scenario_prompt_injection():
    scenarios = get_standard_shadow_scenarios()
    outcome = ShadowLabRunner.run_scenario(scenarios["SCENARIO_PROMPT_INJECTION"])
    assert outcome.passed is True


def test_scenario_missing_rollback_and_auto_correction():
    scenarios = get_standard_shadow_scenarios()
    outcome = ShadowLabRunner.run_scenario(scenarios["SCENARIO_MISSING_ROLLBACK"])
    assert outcome.passed is True
    assert outcome.retries_attempted == 1
    assert outcome.fault_recovered is True


def test_scenario_legacy_client_break_and_auto_correction():
    scenarios = get_standard_shadow_scenarios()
    outcome = ShadowLabRunner.run_scenario(scenarios["SCENARIO_LEGACY_CLIENT_BREAK"])
    assert outcome.passed is True
    assert outcome.retries_attempted == 1
    assert outcome.fault_recovered is True
