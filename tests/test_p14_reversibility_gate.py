"""ChangeMesh Reversibility Gate and Approval Compression comprehensive test suite.

P-14: Tests 4-class reversibility classification, 1-screen compressed decision cards,
cryptographic HMAC approval tokens, single-use idempotency, and Policy Guardian gate decisions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.contracts.autonomy import AutonomyClass
from src.gate.compression import ApprovalCompressionEngine
from src.gate.policy_guardian_gate import PolicyGuardianGate
from src.gate.reversibility import (
    ReversibilityClass,
    ReversibilityClassifier,
)
from src.gate.token import (
    ApprovalTokenManager,
    SignedApprovalToken,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# P-14.01: 4-Class Reversibility Classification
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

    # 4. Irreversible Destructive (DROP TABLE without down script)
    res_dest = ReversibilityClassifier.classify_sql(
        change_id="chg-004",
        sql_up="DROP TABLE legacy_audit_logs;",
        sql_down=None,
        blast_radius_score=0.5,
    )
    assert res_dest.reversibility_class == ReversibilityClass.IRREVERSIBLE_DESTRUCTIVE
    assert res_dest.reversibility_score == 0.0


# ============================================================================
# P-14.02: Approval Compression Card Generation
# ============================================================================

def test_approval_compression_card_generation():
    assessment = ReversibilityClassifier.classify_sql(
        change_id="chg-drop-table",
        sql_up="DROP TABLE old_records;",
        sql_down="CREATE TABLE old_records (id INT);",
        blast_radius_score=0.85,
    )

    card = ApprovalCompressionEngine.generate_card(
        change_request_id="chg-drop-table",
        assessment=assessment,
        authority_slot_ref="slot:lead_dba",
    )

    assert card.change_request_id == "chg-drop-table"
    assert card.autonomy_decision.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert len(card.decision_options) == 2
    assert "APPROVE_EXECUTION" in card.decision_options
    assert "REJECT_AND_REQUEST_REVISION" in card.decision_options
    assert "AST static analysis passed" in card.completed_work_summary
    assert "Synthetic twin rehearsal passed" in card.rehearsed_work_summary


# ============================================================================
# P-14.03: Cryptographic Approval Token Validation & Idempotency
# ============================================================================

def test_cryptographic_approval_token_lifecycle():
    mgr = ApprovalTokenManager()
    plan_hash = "sha256-plan-hash-abc-123"
    secret_key = "test-secret-key-32-characters!!"
    now = _utc_now()

    # 1. Issue Token
    token = mgr.issue_token(
        plan_hash=plan_hash,
        approver_id="alice@lead-dba.org",
        authority_slot_ref="slot:lead_dba",
        secret_key=secret_key,
        validity_seconds=3600,
        now=now,
    )
    assert token.signature is not None

    # 2. Verify against wrong plan hash (Stale Token)
    res_stale = mgr.verify_and_consume(
        token=token,
        expected_plan_hash="sha256-plan-hash-xyz-999",
        secret_key=secret_key,
        now=now + timedelta(minutes=5),
    )
    assert res_stale.is_valid is False
    assert res_stale.status == "STALE_PLAN_HASH"

    # 3. Verify against wrong secret key (Invalid Signature)
    res_tamper = mgr.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        secret_key="wrong-secret-key-attacker",
        now=now + timedelta(minutes=5),
    )
    assert res_tamper.is_valid is False
    assert res_tamper.status == "INVALID_SIGNATURE"

    # 4. Verify when expired
    res_expired = mgr.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        secret_key=secret_key,
        now=now + timedelta(hours=2),
    )
    assert res_expired.is_valid is False
    assert res_expired.status == "EXPIRED"

    # 5. Successful Verification and Single-Use Consumption
    res_valid = mgr.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        secret_key=secret_key,
        now=now + timedelta(minutes=5),
    )
    assert res_valid.is_valid is True
    assert res_valid.status == "VALID"

    # 6. Replay Attempt (Idempotency check fails closed)
    res_replay = mgr.verify_and_consume(
        token=token,
        expected_plan_hash=plan_hash,
        secret_key=secret_key,
        now=now + timedelta(minutes=6),
    )
    assert res_replay.is_valid is False
    assert res_replay.status == "TOKEN_ALREADY_CONSUMED"


# ============================================================================
# P-14.04 - P-14.06: Policy Guardian Gate Evaluation
# ============================================================================

def test_policy_guardian_gate_evaluation():
    token_mgr = ApprovalTokenManager()
    gate = PolicyGuardianGate(token_manager=token_mgr)
    secret_key = "demo-signing-secret-key-32chars!!"

    # 1. Fully reversible -> AUTO_EXECUTE
    eval_auto = gate.evaluate_change(
        change_id="chg-auto",
        sql_up="ALTER TABLE users ADD COLUMN phone TEXT;",
        sql_down="ALTER TABLE users DROP COLUMN phone;",
        blast_radius=0.1,
    )
    assert eval_auto.autonomy_class == AutonomyClass.AUTO_EXECUTE
    assert eval_auto.is_authorized is True

    # 2. Irreversible destructive -> BLOCKED
    eval_blocked = gate.evaluate_change(
        change_id="chg-block",
        sql_up="DROP TABLE customers;",
        sql_down=None,
        blast_radius=0.5,
    )
    assert eval_blocked.autonomy_class == AutonomyClass.BLOCKED
    assert eval_blocked.is_authorized is False

    # 3. High blast radius without token -> HUMAN_AUTHORITY_REQUIRED + Compression Card
    eval_human_no_tok = gate.evaluate_change(
        change_id="chg-human",
        sql_up="ALTER TABLE payments ADD COLUMN fee INT;",
        sql_down="ALTER TABLE payments DROP COLUMN fee;",
        blast_radius=0.95,
        plan_hash="plan-hash-pay",
        approval_token=None,
    )
    assert eval_human_no_tok.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert eval_human_no_tok.is_authorized is False
    assert eval_human_no_tok.compression_card is not None

    # 4. High blast radius with valid token -> AUTHORIZED
    token = token_mgr.issue_token(
        plan_hash="plan-hash-pay",
        approver_id="bob@lead-dba.org",
        secret_key=secret_key,
    )
    eval_human_tok = gate.evaluate_change(
        change_id="chg-human",
        sql_up="ALTER TABLE payments ADD COLUMN fee INT;",
        sql_down="ALTER TABLE payments DROP COLUMN fee;",
        blast_radius=0.95,
        plan_hash="plan-hash-pay",
        approval_token=token,
        signing_secret=secret_key,
    )
    assert eval_human_tok.is_authorized is True
    assert "Valid cryptographic approval token" in eval_human_tok.decision_summary
