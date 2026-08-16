"""ChangeMesh ShadowLab Rehearsal Twin comprehensive test suite.

P-13: Tests all 8 synthetic twin scenarios, deterministic backoff recording (P-13.03),
checkpoint/resume recovery (P-13.05), strict fail-closed unknown scenario rejection,
authorization eligibility binding (P-13.06), and typed plan correction (P-13.07).
"""

from __future__ import annotations

from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode
from src.shadowlab.runner import (
    AuthorizationEligibilityEvaluator,
    MigrationPlan,
    PlanCorrectionEngine,
    PlanStep,
    ShadowLabRunner,
)
from src.shadowlab.scenarios import (
    ShadowScenario,
    get_standard_shadow_scenarios,
)

# ============================================================================
# P-13.01 & Unknown Scenario Fail-Closed Rejection
# ============================================================================


def test_unknown_scenario_fails_closed_never_generic_pass():
    """Prove unknown scenario ID fails closed with passed=False and EvidenceState.FAIL."""
    unknown = ShadowScenario(
        scenario_id="SCENARIO_UNKNOWN_UNREGISTERED_999",
        name="Unknown Fake Scenario",
        description="Should fail closed immediately",
        expected_policy_outcome="DENY",
        pass_criteria="Must not pass",
    )

    outcome = ShadowLabRunner.run_scenario(unknown)
    assert outcome.passed is False
    assert outcome.evidence_state == EvidenceState.FAIL
    assert outcome.steps_executed == 0
    assert "rejected" in outcome.details.lower()


# ============================================================================
# P-13.03: 503 Transient Failure & Exponential Backoff Recording
# ============================================================================


def test_503_transient_recovery_with_recorded_exponential_backoff():
    """Verify 503 recovery executes with recorded bounded exponential backoff delays."""
    scenarios = get_standard_shadow_scenarios()
    sc = scenarios["SCENARIO_503_TRANSIENT_RECOVERY"]

    outcome = ShadowLabRunner.run_scenario(sc)
    assert outcome.passed is True
    assert outcome.retries_attempted == 2
    assert outcome.fault_recovered is True
    assert len(outcome.backoff_delays_ms) == 2
    # Verify exponential backoff: attempt 1 = 100ms, attempt 2 = 200ms
    assert outcome.backoff_delays_ms == (100, 200)
    assert "exponential backoff" in outcome.details


# ============================================================================
# P-13.05: All Canonical Scenarios Execution
# ============================================================================


def test_all_canonical_shadow_scenarios_execute_correctly():
    """Execute all 8 standard scenarios and verify deterministic simulation results."""
    scenarios = get_standard_shadow_scenarios()
    assert len(scenarios) == 8

    # 1. Normal Migration
    out_norm = ShadowLabRunner.run_scenario(scenarios["SCENARIO_NORMAL_MIGRATION"])
    assert out_norm.passed is True
    assert out_norm.evidence_mode == ExecutionEvidenceMode.SIMULATION

    # 2. 503 Recovery
    out_503 = ShadowLabRunner.run_scenario(scenarios["SCENARIO_503_TRANSIENT_RECOVERY"])
    assert out_503.passed is True

    # 3. Partial Compensation
    out_comp = ShadowLabRunner.run_scenario(scenarios["SCENARIO_PARTIAL_INTERRUPTION_COMPENSATION"])
    assert out_comp.passed is True
    assert out_comp.compensation_executed is True

    # 4. Stale Approval
    out_stale = ShadowLabRunner.run_scenario(scenarios["SCENARIO_STALE_APPROVAL"])
    assert out_stale.passed is True

    # 5. Prompt Injection
    out_inj = ShadowLabRunner.run_scenario(scenarios["SCENARIO_PROMPT_INJECTION"])
    assert out_inj.passed is True

    # 6. Missing Rollback
    out_roll = ShadowLabRunner.run_scenario(scenarios["SCENARIO_MISSING_ROLLBACK"])
    assert out_roll.passed is True

    # 7. Legacy Client Break
    out_leg = ShadowLabRunner.run_scenario(scenarios["SCENARIO_LEGACY_CLIENT_BREAK"])
    assert out_leg.passed is True

    # 8. Restart Resume (exercising P-10 checkpoint/resume)
    out_restart = ShadowLabRunner.run_scenario(scenarios["SCENARIO_RESTART_RESUME"])
    assert out_restart.passed is True
    assert out_restart.fault_recovered is True


# ============================================================================
# P-13.06: Authorization Eligibility Binding
# ============================================================================


def test_authorization_eligibility_binding():
    """Verify rehearsal outcomes bind to execution eligibility without self-minting authority."""
    scenarios = get_standard_shadow_scenarios()

    out_norm = ShadowLabRunner.run_scenario(scenarios["SCENARIO_NORMAL_MIGRATION"])
    out_503 = ShadowLabRunner.run_scenario(scenarios["SCENARIO_503_TRANSIENT_RECOVERY"])

    # All required scenarios present and passed -> ELIGIBLE for execution
    elig_pass = AuthorizationEligibilityEvaluator.evaluate(
        required_scenario_ids=("SCENARIO_NORMAL_MIGRATION", "SCENARIO_503_TRANSIENT_RECOVERY"),
        rehearsal_outcomes=(out_norm, out_503),
    )
    assert elig_pass.is_eligible is True
    assert elig_pass.status == "REHEARSAL_SATISFIED"

    # Missing required scenario -> BLOCKED
    elig_missing = AuthorizationEligibilityEvaluator.evaluate(
        required_scenario_ids=(
            "SCENARIO_NORMAL_MIGRATION",
            "SCENARIO_PARTIAL_INTERRUPTION_COMPENSATION",
        ),
        rehearsal_outcomes=(out_norm,),  # Missing compensation rehearsal
    )
    assert elig_missing.is_eligible is False
    assert elig_missing.status == "DENY_BLOCKED"

    # Failed required scenario -> BLOCKED
    failed_outcome = out_norm.model_copy(
        update={"passed": False, "evidence_state": EvidenceState.FAIL}
    )
    elig_fail = AuthorizationEligibilityEvaluator.evaluate(
        required_scenario_ids=("SCENARIO_NORMAL_MIGRATION",),
        rehearsal_outcomes=(failed_outcome,),
    )
    assert elig_fail.is_eligible is False
    assert elig_fail.status == "REHEARSAL_FAILED"


# ============================================================================
# P-13.07: Bounded Automatic Typed Plan Correction
# ============================================================================


def test_typed_plan_correction_for_missing_rollback():
    """Verify automatic plan correction synthesizes down migration for irreversible plan."""
    initial_plan = MigrationPlan(
        plan_id="plan-drop-col-01",
        change_id="chg-drop-01",
        target_table="users",
        steps=(
            PlanStep(
                step_id="step_drop_legacy",
                action_type="DROP_COLUMN",
                sql="ALTER TABLE users DROP COLUMN legacy_id;",
                rollback_sql=None,
            ),
        ),
        has_rollback=False,
    )

    res = PlanCorrectionEngine.correct_and_rehearse(
        initial_plan=initial_plan,
        failing_scenario_id="SCENARIO_MISSING_ROLLBACK",
    )
    assert res.is_corrected is True
    assert res.status == "CORRECTED"
    assert res.attempts_used == 1
    assert res.corrected_plan is not None
    assert res.corrected_plan.has_rollback is True
    assert res.corrected_plan.steps[0].rollback_sql is not None


def test_typed_plan_correction_for_legacy_client_break():
    """Verify plan correction applies Expand-Contract view for breaking rename."""

    initial_plan = MigrationPlan(
        plan_id="plan-rename-01",
        change_id="chg-rename-01",
        target_table="users",
        steps=(
            PlanStep(
                step_id="step_rename",
                action_type="RENAME_COLUMN",
                sql="ALTER TABLE users RENAME COLUMN email TO user_email;",
                rollback_sql="ALTER TABLE users RENAME COLUMN user_email TO email;",
            ),
        ),
        uses_expand_contract=False,
    )

    res = PlanCorrectionEngine.correct_and_rehearse(
        initial_plan=initial_plan,
        failing_scenario_id="SCENARIO_LEGACY_CLIENT_BREAK",
    )
    assert res.is_corrected is True
    assert res.corrected_plan is not None
    assert res.corrected_plan.uses_expand_contract is True
    assert len(res.corrected_plan.steps) == 2
    assert res.rehearsal_outcome is not None
    assert res.rehearsal_outcome.passed is True
    assert res.rehearsal_outcome.evidence_mode == ExecutionEvidenceMode.SIMULATION


def test_typed_plan_correction_mutated_invalid_rehearsal_fails():
    """Prove that an invalid or mutated plan fails deterministic re-rehearsal evaluation."""
    # 1. Invalid plan for missing rollback scenario (has_rollback=False or missing rollback_sql)
    invalid_plan_1 = MigrationPlan(
        plan_id="plan-bad-rollback-01",
        change_id="chg-bad-01",
        target_table="users",
        steps=(
            PlanStep(
                step_id="step_drop_legacy",
                action_type="DROP_COLUMN",
                sql="ALTER TABLE users DROP COLUMN legacy_id;",
                rollback_sql="",  # Empty rollback SQL
            ),
        ),
        has_rollback=True,
    )
    ok1, outcome1, _ = PlanCorrectionEngine.evaluate_corrected_plan(
        invalid_plan_1, "SCENARIO_MISSING_ROLLBACK"
    )
    assert ok1 is False
    assert outcome1.passed is False
    assert outcome1.evidence_state == EvidenceState.FAIL

    # 2. Invalid plan for legacy client break (uses_expand_contract=False)
    invalid_plan_2 = MigrationPlan(
        plan_id="plan-bad-expand-01",
        change_id="chg-bad-02",
        target_table="users",
        steps=(
            PlanStep(
                step_id="step_rename",
                action_type="RENAME_COLUMN",
                sql="ALTER TABLE users RENAME COLUMN email TO user_email;",
                rollback_sql="ALTER TABLE users RENAME COLUMN user_email TO email;",
            ),
        ),
        uses_expand_contract=False,
    )
    ok2, outcome2, _ = PlanCorrectionEngine.evaluate_corrected_plan(
        invalid_plan_2, "SCENARIO_LEGACY_CLIENT_BREAK"
    )
    assert ok2 is False
    assert outcome2.passed is False
    assert outcome2.evidence_state == EvidenceState.FAIL
