"""ChangeMesh Reversibility Gate, Approval Compression, and Policy Guardian test suite.

P-14: Tests 7 deterministic policy inputs, complete 7-action autonomy mapping,
locked-fact-only Approval Compression Cards, cryptographic approval token verification
without hardcoded secrets, and real demonstrable friction reduction metrics.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from domain.contracts.autonomy import AutonomyClass
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import EvidenceState
from src.gate.action_map import CanonicalActionType, get_canonical_action_map
from src.gate.compression import (
    ApprovalCompressionEngine,
    LockedFact,
    LockedFactBundle,
)
from src.gate.friction_metrics import (
    FrictionMetricsCalculator,
)
from src.gate.policy_guardian_gate import (
    PolicyGuardianGate,
)
from src.gate.reversibility import (
    DeterministicPolicyInputs,
    NoveltyTier,
    PrivilegeLevel,
    RehearsalStatus,
    ReversibilityClass,
    ReversibilityClassifier,
)
from src.gate.token import (
    SignedApprovalToken,
    TrustedAuthorityDecisionVerifier,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# Test-Only Authority Signer (Lives strictly in test boundary)
# ============================================================================


class TestHmacAuthoritySigner:
    """Test fixture helper to sign approval tokens for test verification."""

    @classmethod
    def sign_token(
        cls,
        plan_hash: str,
        approver_id: str,
        authority_slot_ref: str,
        secret_key: str,
        action_scope: str = "Target: Production",
        validity_seconds: int = 3600,
        now: datetime | None = None,
    ) -> SignedApprovalToken:
        if now is None:
            now = _utc_now()

        token_id = f"tok-test-{uuid.uuid4().hex[:8]}"
        nonce = uuid.uuid4().hex
        expires_at = now + timedelta(seconds=validity_seconds)

        msg = (
            f"token_id={token_id}:plan_hash={plan_hash}:approver={approver_id}:"
            f"slot={authority_slot_ref}:scope={action_scope}:"
            f"issued={now.isoformat()}:expires={expires_at.isoformat()}:nonce={nonce}"
        )
        sig = hmac.new(secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

        return SignedApprovalToken(
            token_id=token_id,
            plan_hash=plan_hash,
            approver_id=approver_id,
            authority_slot_ref=authority_slot_ref,
            action_scope=action_scope,
            issued_at=now,
            expires_at=expires_at,
            nonce=nonce,
            signature=sig,
        )


# ============================================================================
# P-14.01 & P-14.02: 7 Deterministic Policy Inputs & Rehearsal Authorization
# ============================================================================


def test_reversibility_classification_tiers():
    # 1. Fully Reversible Automated
    res_auto = ReversibilityClassifier.classify_sql(
        change_id="chg-001",
        sql_up="ALTER TABLE users ADD COLUMN phone TEXT;",
        sql_down="ALTER TABLE users DROP COLUMN phone;",
        blast_radius_score=0.1,
    )
    assert res_auto.reversibility_class == ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED
    assert res_auto.reversibility_score == 1.0

    # 2. Reversible With Compensation
    res_comp = ReversibilityClassifier.classify_sql(
        change_id="chg-002",
        sql_up="CREATE VIEW v_active_users AS SELECT * FROM users WHERE active = 1;",
        sql_down=None,
        blast_radius_score=0.2,
    )
    assert res_comp.reversibility_class == ReversibilityClass.REVERSIBLE_WITH_COMPENSATION
    assert res_comp.reversibility_score > 0.8

    # 3. Human Intervention Required (High blast radius)
    res_human = ReversibilityClassifier.classify_sql(
        change_id="chg-003",
        sql_up="ALTER TABLE orders ADD COLUMN order_status TEXT;",
        sql_down="ALTER TABLE orders DROP COLUMN order_status;",
        blast_radius_score=0.92,
    )
    assert res_human.reversibility_class == ReversibilityClass.HUMAN_INTERVENTION_REQUIRED

    # 4. Irreversible Destructive
    res_dest = ReversibilityClassifier.classify_sql(
        change_id="chg-004",
        sql_up="DROP TABLE legacy_audit_logs;",
        sql_down=None,
        blast_radius_score=0.5,
    )
    assert res_dest.reversibility_class == ReversibilityClass.IRREVERSIBLE_DESTRUCTIVE
    assert res_dest.reversibility_score == 0.0


def test_rehearse_then_execute_not_authorized_until_rehearsal_passed():
    """Prove REHEARSE_THEN_EXECUTE does NOT authorize execution until rehearsal status is PASSED."""
    gate = PolicyGuardianGate()

    # Rehearsal NOT_RUN -> Execution UNAUTHORIZED
    inputs_not_run = DeterministicPolicyInputs(
        change_id="chg-rehearse-1",
        blast_radius_score=0.25,
        reversibility_class=ReversibilityClass.REVERSIBLE_WITH_COMPENSATION,
        has_down_migration=True,
        rehearsal_status=RehearsalStatus.REHEARSAL_NOT_RUN,
    )
    eval_not_run = gate.evaluate_inputs(inputs_not_run)
    assert eval_not_run.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE
    assert eval_not_run.is_authorized is False
    assert "UNAUTHORIZED" in eval_not_run.decision_summary

    # Rehearsal PASSED -> Execution AUTHORIZED
    inputs_passed = inputs_not_run.model_copy(
        update={"rehearsal_status": RehearsalStatus.REHEARSAL_PASSED}
    )
    eval_passed = gate.evaluate_inputs(inputs_passed)
    assert eval_passed.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE
    assert eval_passed.is_authorized is True
    assert "rehearsal passed" in eval_passed.decision_summary.lower()


# ============================================================================
# P-14.03: Complete Exact Action Map
# ============================================================================


def test_complete_canonical_action_map():
    """Verify action map maps all 7 demo actions without fallback defaults."""
    action_map = get_canonical_action_map()
    assert len(action_map) == 7

    assert action_map[CanonicalActionType.ANALYSIS].autonomy_class == AutonomyClass.AUTO_EXECUTE
    assert action_map[CanonicalActionType.BRANCH].autonomy_class == AutonomyClass.AUTO_EXECUTE
    assert action_map[CanonicalActionType.DRAFT_PR].autonomy_class == AutonomyClass.AUTO_EXECUTE
    assert (
        action_map[CanonicalActionType.STAGING_MUTATION].autonomy_class
        == AutonomyClass.REHEARSE_THEN_EXECUTE
    )
    assert (
        action_map[CanonicalActionType.PRODUCTION_ADD_DROP].autonomy_class
        == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    )
    assert (
        action_map[CanonicalActionType.PRIVILEGE_EXPANSION].autonomy_class
        == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    )
    assert (
        action_map[CanonicalActionType.DATA_EXPORT].autonomy_class
        == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    )

    # Verify authority slot requirement
    assert action_map[CanonicalActionType.PRODUCTION_ADD_DROP].requires_human_authority is True
    assert action_map[CanonicalActionType.PRODUCTION_ADD_DROP].authority_slot_ref == "slot:lead_dba"


# ============================================================================
# P-14.04: Locked Facts Only in Approval Compression Card
# ============================================================================


def test_approval_compression_card_locked_facts_only():
    """Prove engine renders strictly from supplied locked facts without reassurance."""
    now = _utc_now()
    assessment = ReversibilityClassifier.classify_sql(
        change_id="chg-drop-01",
        sql_up="DROP TABLE old_audit_logs;",
        sql_down="CREATE TABLE old_audit_logs (id INT);",
        blast_radius_score=0.88,
    )

    fact_ast = LockedFact(
        fact_id="fact-ast-01",
        source_agent="impact_scout",
        category="AST_ANALYSIS",
        statement="Scanned 42 SQL queries across 3 microservices; identified 2 dependent queries",
        evidence_digest="a" * 64,
    )
    fact_rehearse = LockedFact(
        fact_id="fact-reh-01",
        source_agent="shadowlab",
        category="REHEARSAL",
        statement="Rehearsed DDL in Postgres twin; verified recreation rollback script in 45ms",
        evidence_digest="b" * 64,
    )

    bundle = LockedFactBundle(
        change_request_id="chg-drop-01",
        completed_facts=(fact_ast,),
        rehearsed_facts=(fact_rehearse,),
        reversibility_assessment=assessment,
        authority_slot_ref="slot:lead_dba",
        decision_question="Authorize DROP TABLE old_audit_logs on production database?",
        decision_options=("APPROVE_EXECUTION", "REJECT_AND_REQUEST_REVISION"),
        action_scope="Production PostgreSQL / public.old_audit_logs",
        risk_summary="High blast radius (0.88) destructive table drop",
        consequence_summary="Table will be deleted; restore requires running recreation script.",
        expires_at=now + timedelta(hours=1),
        evidence_refs=("ev-ast-01", "ev-reh-01"),
    )

    card = ApprovalCompressionEngine.generate_card(bundle, now=now)

    assert card.change_request_id == "chg-drop-01"
    assert card.autonomy_decision.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED

    # Verify facts are rendered strictly from the locked facts
    assert "Scanned 42 SQL queries" in card.completed_work_summary
    assert "verified recreation rollback script" in card.rehearsed_work_summary

    # Prove NO fabricated default reassurance exists
    assert "AST static analysis passed (0 breaking changes)" not in card.completed_work_summary
    assert "Synthetic twin rehearsal passed in ShadowLab sandbox" not in card.rehearsed_work_summary
    assert card.evidence_refs == ("ev-ast-01", "ev-reh-01")


# ============================================================================
# P-14.05: Human Authority Cryptographic Verification
# ============================================================================


def test_trusted_authority_decision_verification_lifecycle():
    """Verify cryptographic token verification, expiry, plan binding, and replay prevention."""
    secret_key = "test-secret-injected-for-unit-test-only!!"
    verifier = TrustedAuthorityDecisionVerifier(verification_secret=secret_key)
    plan_hash = "sha256-plan-hash-abc"
    slot_ref = "slot:lead_dba"
    now = _utc_now()

    # 1. Sign valid token in test fixture
    token = TestHmacAuthoritySigner.sign_token(
        plan_hash=plan_hash,
        approver_id="alice@lead-dba.org",
        authority_slot_ref=slot_ref,
        secret_key=secret_key,
        now=now,
    )

    # 2. Verify with wrong plan hash (Stale Plan Check)
    val_stale = verifier.verify_and_consume(
        token=token,
        expected_plan_hash="sha256-plan-hash-stale-diff",
        expected_slot_ref=slot_ref,
        now=now,
    )
    assert val_stale.is_valid is False
    assert val_stale.status == "STALE_PLAN_HASH"

    # 3. Verify when expired
    val_exp = verifier.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref=slot_ref,
        now=now + timedelta(hours=2),
    )
    assert val_exp.is_valid is False
    assert val_exp.status == "EXPIRED"

    # 4. Verify with wrong slot ref
    val_wrong_slot = verifier.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref="slot:other_dba",
        now=now + timedelta(minutes=1),
    )
    assert val_wrong_slot.is_valid is False
    assert val_wrong_slot.status == "SLOT_MISMATCH"

    # 5. Verify with wrong scope
    val_wrong_scope = verifier.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref=slot_ref,
        expected_scope="Target: Staging. Change: chg-123",
        now=now + timedelta(minutes=2),
    )
    assert val_wrong_scope.is_valid is False
    assert val_wrong_scope.status == "SCOPE_MISMATCH"

    # 6. Successful Verification and Single-Use Consumption
    val_ok = verifier.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref=slot_ref,
        expected_scope="Target: Production",
        now=now + timedelta(minutes=5),
    )
    assert val_ok.is_valid is True
    assert val_ok.status == "VALID"

    # 7. Replay attempt fails closed (Single-use consumption)
    val_replay = verifier.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref=slot_ref,
        expected_scope="Target: Production",
        now=now + timedelta(minutes=6),
    )
    assert val_replay.is_valid is False
    assert val_replay.status == "TOKEN_ALREADY_CONSUMED"


def test_policy_guardian_gate_with_injected_authority_verifier():
    """Verify PolicyGuardianGate uses injected verifier without hardcoded secrets."""
    secret = "injected-test-secret-key-48chars-for-testing!!"
    verifier = TrustedAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    plan_hash = "plan-pay-01"

    # 1. Fully reversible -> AUTO_EXECUTE
    eval_auto = gate.evaluate_change_sql(
        change_id="chg-auto",
        sql_up="ALTER TABLE users ADD COLUMN phone TEXT;",
        sql_down="ALTER TABLE users DROP COLUMN phone;",
        blast_radius=0.1,
    )
    assert eval_auto.autonomy_class == AutonomyClass.AUTO_EXECUTE
    assert eval_auto.is_authorized is True

    # 2. High blast radius without token -> HUMAN_AUTHORITY_REQUIRED + card
    eval_human_no_tok = gate.evaluate_change_sql(
        change_id="chg-human",
        sql_up="ALTER TABLE payments ADD COLUMN fee INT;",
        sql_down="ALTER TABLE payments DROP COLUMN fee;",
        blast_radius=0.95,
        plan_hash=plan_hash,
        approval_token=None,
    )
    assert eval_human_no_tok.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert eval_human_no_tok.is_authorized is False
    assert eval_human_no_tok.compression_card is not None
    # Verify card contains bounded future expiry in remaining decision summary
    assert "Expires At:" in eval_human_no_tok.compression_card.remaining_decision_summary

    # 3. High blast radius with valid signed token matching exact scope -> AUTHORIZED
    token = TestHmacAuthoritySigner.sign_token(
        plan_hash=plan_hash,
        approver_id="lead-dba@enterprise.org",
        authority_slot_ref="slot:lead_dba",
        secret_key=secret,
        action_scope="Target: Production. Change: chg-human",
    )
    eval_human_tok = gate.evaluate_change_sql(
        change_id="chg-human",
        sql_up="ALTER TABLE payments ADD COLUMN fee INT;",
        sql_down="ALTER TABLE payments DROP COLUMN fee;",
        blast_radius=0.95,
        plan_hash=plan_hash,
        approval_token=token,
    )
    assert eval_human_tok.is_authorized is True
    assert "Valid cryptographic approval token" in eval_human_tok.decision_summary


# ============================================================================
# P-14.06: Real Friction Metric Calculation
# ============================================================================


def test_friction_metrics_calculation_from_real_traces():
    """Verify FrictionMetricsCalculator computes metric artifact from actual traces."""

    secret = "test-secret-key-32-chars-long!!"
    verifier = TrustedAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)

    eval1 = gate.evaluate_change_sql(
        "c1", "ALTER TABLE a ADD COLUMN x INT;", "ALTER TABLE a DROP COLUMN x;", blast_radius=0.1
    )
    eval2 = gate.evaluate_change_sql(
        "c2", "ALTER TABLE b ADD COLUMN y INT;", "ALTER TABLE b DROP COLUMN y;", blast_radius=0.1
    )
    eval3 = gate.evaluate_change_sql("c3", "CREATE VIEW v AS SELECT 1;", None, blast_radius=0.2)
    eval4 = gate.evaluate_change_sql("c4", "DROP TABLE c;", None, blast_radius=0.5)

    token = TestHmacAuthoritySigner.sign_token(
        "plan-h5", "dba@org", "slot:lead_dba", secret, action_scope="Target: Production. Change: c5"
    )
    eval5 = gate.evaluate_change_sql(
        "c5",
        "ALTER TABLE d DROP COLUMN z;",
        "ALTER TABLE d ADD COLUMN z INT;",
        blast_radius=0.9,
        plan_hash="plan-h5",
        approval_token=token,
    )

    traces = [eval1, eval2, eval3, eval4, eval5]
    artifact = FrictionMetricsCalculator.calculate(traces, repeated_prompts_avoided=2)

    assert artifact.total_workflow_decisions == 5
    assert artifact.autonomous_decisions == 2
    assert artifact.rehearse_then_execute_decisions == 1
    assert artifact.blocked_decisions == 1
    assert artifact.human_authority_decisions == 1
    assert artifact.repeated_prompts_avoided == 2
    assert artifact.autonomy_ratio == 0.4

    md = artifact.to_markdown_summary()
    assert "Workflow Friction Reduction Metrics" in md
    assert "Overall Fleet Autonomy Ratio" in md


# ============================================================================
# P-14.07: Table-Driven Seven Deterministic Inputs Policy Matrix
# ============================================================================


def test_seven_deterministic_inputs_policy_matrix():
    """Verify PolicyGuardianGate deterministically evaluates all 7 input dimensions."""
    gate = PolicyGuardianGate()

    # 1. ANOMALOUS novelty -> BLOCKED (fail closed)
    res_anom = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-anom",
            blast_radius_score=0.1,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            novelty_tier=NoveltyTier.ANOMALOUS,
        )
    )
    assert res_anom.autonomy_class == AutonomyClass.BLOCKED
    assert res_anom.is_authorized is False

    # 2. EvidenceState.FAIL -> BLOCKED
    res_ev_fail = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-ev-fail",
            blast_radius_score=0.1,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            evidence_state=EvidenceState.FAIL,
        )
    )
    assert res_ev_fail.autonomy_class == AutonomyClass.BLOCKED
    assert res_ev_fail.is_authorized is False

    # 3. EvidenceState.NOT_RUN -> BLOCKED
    res_ev_not_run = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-not-run",
            blast_radius_score=0.1,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            evidence_state=EvidenceState.NOT_RUN,
        )
    )
    assert res_ev_not_run.autonomy_class == AutonomyClass.BLOCKED
    assert res_ev_not_run.is_authorized is False

    # 4. NOVEL_UNVERIFIED -> REHEARSE_THEN_EXECUTE (requires rehearsal before authorization)
    res_novel = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-novel",
            blast_radius_score=0.2,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            novelty_tier=NoveltyTier.NOVEL_UNVERIFIED,
            rehearsal_status=RehearsalStatus.NOT_REQUIRED,
        )
    )
    assert res_novel.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE
    assert res_novel.is_authorized is False

    # 5. RESTRICTED sensitivity with SCHEMA_MODIFY and blast > 0.3 -> HUMAN_AUTHORITY_REQUIRED
    res_restr = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-restr",
            blast_radius_score=0.5,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            data_classification=DataClassLevel.RESTRICTED,
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        )
    )
    assert res_restr.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res_restr.is_authorized is False

    # 6. Rehearsal failed -> BLOCKED
    res_reh_fail = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-reh-fail",
            blast_radius_score=0.2,
            reversibility_class=ReversibilityClass.REVERSIBLE_WITH_COMPENSATION,
            rehearsal_status=RehearsalStatus.REHEARSAL_FAILED,
        )
    )
    assert res_reh_fail.autonomy_class == AutonomyClass.BLOCKED
    assert res_reh_fail.is_authorized is False

    # 7. Rehearsal passed on compensation -> REHEARSE_THEN_EXECUTE authorized
    res_reh_pass = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-reh-pass",
            blast_radius_score=0.2,
            reversibility_class=ReversibilityClass.REVERSIBLE_WITH_COMPENSATION,
            rehearsal_status=RehearsalStatus.REHEARSAL_PASSED,
        )
    )
    assert res_reh_pass.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE
    assert res_reh_pass.is_authorized is True
