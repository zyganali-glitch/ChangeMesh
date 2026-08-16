"""ChangeMesh Reversibility Gate, Approval Compression, and Policy Guardian test suite.

P-14: Tests 7 deterministic policy inputs, complete 7-action autonomy mapping,
locked-fact-only Approval Compression Cards, adapter-only cryptographic approval tokens,
fail-closed public entry points, reusable verified authority, and friction reduction.
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from domain.contracts.autonomy import AutonomyClass
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import EvidenceState
from integrations.authority.hmac_adapter import (
    HmacAuthorityDecisionVerifier,
)
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
    SignedAuthorityEnvelope,
    VerifiedAuthorityDecision,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# Test-Only Authority Signer (Lives strictly in test boundary)
# ============================================================================


class TestHmacAuthoritySigner:
    """Test fixture helper to sign approval envelopes for test verification."""

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
    ) -> SignedAuthorityEnvelope:
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

        return SignedAuthorityEnvelope(
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
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        rehearsal_status=RehearsalStatus.REHEARSAL_NOT_RUN,
    )
    eval_not_run = gate.evaluate_inputs(inputs_not_run)
    assert eval_not_run.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE
    assert eval_not_run.is_authorized is False
    assert "UNAUTHORIZED" in eval_not_run.decision_summary

    # Rehearsal PASSED with digest -> Execution AUTHORIZED
    inputs_passed = inputs_not_run.model_copy(
        update={
            "rehearsal_status": RehearsalStatus.REHEARSAL_PASSED,
            "rehearsal_digests": ("2" * 64,),
        }
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
# P-14.05: Adapter-Only Cryptographic Verification & Replay Protection
# ============================================================================


def test_trusted_authority_decision_verification_lifecycle():
    """Verify cryptographic token verification, expiry, and replay prevention in adapter."""
    secret_key = "test-secret-injected-for-unit-test-only!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret_key)
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
    val_stale = verifier.verify_envelope(
        envelope=token,
        expected_plan_hash="sha256-plan-hash-stale-diff",
        expected_slot_ref=slot_ref,
        now=now,
    )
    assert val_stale.is_valid is False
    assert val_stale.status == "STALE_PLAN_HASH"
    assert val_stale.decision is None

    # 3. Verify when expired
    val_exp = verifier.verify_envelope(
        envelope=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref=slot_ref,
        now=now + timedelta(hours=2),
    )
    assert val_exp.is_valid is False
    assert val_exp.status == "EXPIRED"

    # 4. Verify with wrong slot ref
    val_wrong_slot = verifier.verify_envelope(
        envelope=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref="slot:other_dba",
        now=now + timedelta(minutes=1),
    )
    assert val_wrong_slot.is_valid is False
    assert val_wrong_slot.status == "SLOT_MISMATCH"

    # 5. Verify with wrong scope
    val_wrong_scope = verifier.verify_envelope(
        envelope=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref=slot_ref,
        expected_scope="Target: Staging. Change: chg-123",
        now=now + timedelta(minutes=2),
    )
    assert val_wrong_scope.is_valid is False
    assert val_wrong_scope.status == "SCOPE_MISMATCH"

    # 6. Successful Verification and Materialization of VerifiedAuthorityDecision
    val_ok = verifier.verify_envelope(
        envelope=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref=slot_ref,
        expected_scope="Target: Production",
        now=now + timedelta(minutes=5),
    )
    assert val_ok.is_valid is True
    assert val_ok.status == "VALID"
    assert val_ok.decision is not None
    assert val_ok.decision.approver_id == "alice@lead-dba.org"
    assert val_ok.decision.plan_hash == plan_hash
    assert val_ok.decision.authority_slot_ref == slot_ref

    # 7. Replay attempt fails closed (Single-use envelope consumption)
    val_replay = verifier.verify_envelope(
        envelope=token,
        expected_plan_hash=plan_hash,
        expected_slot_ref=slot_ref,
        expected_scope="Target: Production",
        now=now + timedelta(minutes=6),
    )
    assert val_replay.is_valid is False
    assert val_replay.status == "TOKEN_ALREADY_CONSUMED"


def test_policy_guardian_gate_with_injected_authority_verifier():
    """Verify PolicyGuardianGate uses injected verifier and accepts explicit safe facts."""
    secret = "injected-test-secret-key-48chars-for-testing!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    plan_hash = "plan-pay-01"

    # 1. Fully reversible with verified evidence and explicit safe facts -> AUTO_EXECUTE
    eval_auto = gate.evaluate_change_sql(
        change_id="chg-auto",
        sql_up="ALTER TABLE users ADD COLUMN phone TEXT;",
        sql_down="ALTER TABLE users DROP COLUMN phone;",
        blast_radius=0.1,
        privilege_level=PrivilegeLevel.STANDARD_WRITE,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("a" * 64,),
        rehearsal_status=RehearsalStatus.NOT_REQUIRED,
    )
    assert eval_auto.autonomy_class == AutonomyClass.AUTO_EXECUTE
    assert eval_auto.is_authorized is True

    # 2. High blast radius without token -> HUMAN_AUTHORITY_REQUIRED + card
    eval_human_no_tok = gate.evaluate_change_sql(
        change_id="chg-human",
        sql_up="ALTER TABLE payments ADD COLUMN fee INT;",
        sql_down="ALTER TABLE payments DROP COLUMN fee;",
        blast_radius=0.95,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        plan_hash=plan_hash,
        approval_token=None,
        evidence_digests=("b" * 64,),
    )
    assert eval_human_no_tok.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert eval_human_no_tok.is_authorized is False
    assert eval_human_no_tok.compression_card is not None
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
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        plan_hash=plan_hash,
        approval_token=token,
        evidence_digests=("b" * 64,),
    )
    assert eval_human_tok.is_authorized is True
    assert "Valid cryptographic approval token" in eval_human_tok.decision_summary


# ============================================================================
# P-14.05: Reusable Verified Authority & Supersession Semantics Matrix (7 tests)
# ============================================================================


def test_reusable_authority_same_binding_prevents_repeated_prompt():
    """1. Same valid authority reused across operations without another human prompt."""
    secret = "test-secret-key-32-chars-long!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    plan_hash = "plan-migration-v1"
    slot_ref = "slot:lead_dba"
    scope = "Target: Production. Change: chg-batch-01"
    now = _utc_now()

    # Sign valid token for initial authorization
    token = TestHmacAuthoritySigner.sign_token(
        plan_hash=plan_hash,
        approver_id="alice@lead-dba.org",
        authority_slot_ref=slot_ref,
        secret_key=secret,
        action_scope=scope,
        now=now,
    )

    # First evaluation with signed token authorizes and materializes reusable decision in verifier
    res1 = gate.evaluate_change_sql(
        change_id="chg-batch-01",
        sql_up="ALTER TABLE orders DROP COLUMN temp_col;",
        sql_down="ALTER TABLE orders ADD COLUMN temp_col INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=token,
        now=now,
    )
    assert res1.is_authorized is True
    assert res1.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res1.compression_card is None
    assert "Valid cryptographic approval token" in res1.decision_summary

    # Second evaluation in same plan/scope/slot passes autonomously without token or prompt
    res2 = gate.evaluate_change_sql(
        change_id="chg-batch-01",
        sql_up="ALTER TABLE orders DROP COLUMN temp_col;",
        sql_down="ALTER TABLE orders ADD COLUMN temp_col INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=None,
        now=now + timedelta(minutes=5),
    )
    assert res2.is_authorized is True
    assert res2.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res2.compression_card is None
    assert "reused without re-prompt" in res2.decision_summary


def test_reusable_authority_changed_plan_invalidates_reuse():
    """2. Changed plan invalidates reuse and requires new decision."""
    secret = "test-secret-key-32-chars-long!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    now = _utc_now()

    # Sign and verify token for plan-original-hash
    token = TestHmacAuthoritySigner.sign_token(
        plan_hash="plan-original-hash",
        approver_id="alice@lead-dba.org",
        authority_slot_ref="slot:lead_dba",
        secret_key=secret,
        action_scope="Target: Production. Change: chg-002",
        now=now,
    )
    res1 = gate.evaluate_change_sql(
        change_id="chg-002",
        sql_up="ALTER TABLE accounts DROP COLUMN balance_old;",
        sql_down="ALTER TABLE accounts ADD COLUMN balance_old INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("2" * 64,),
        plan_hash="plan-original-hash",
        approval_token=token,
        now=now,
    )
    assert res1.is_authorized is True

    # Attempt reuse under a DIFFERENT plan hash with approval_token=None
    res2 = gate.evaluate_change_sql(
        change_id="chg-002",
        sql_up="ALTER TABLE accounts DROP COLUMN balance_old;",
        sql_down="ALTER TABLE accounts ADD COLUMN balance_old INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("2" * 64,),
        plan_hash="plan-mutated-hash",
        approval_token=None,
        now=now,
    )
    assert res2.is_authorized is False
    assert res2.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res2.compression_card is not None


def test_reusable_authority_changed_scope_invalidates_reuse():
    """3. Changed action scope invalidates reuse."""
    secret = "test-secret-key-32-chars-long!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    now = _utc_now()

    # Sign and verify token for chg-table-A
    token = TestHmacAuthoritySigner.sign_token(
        plan_hash="plan-scope-v1",
        approver_id="alice@lead-dba.org",
        authority_slot_ref="slot:lead_dba",
        secret_key=secret,
        action_scope="Target: Production. Change: chg-table-A",
        now=now,
    )
    res1 = gate.evaluate_change_sql(
        change_id="chg-table-A",
        sql_up="ALTER TABLE a DROP COLUMN x;",
        sql_down="ALTER TABLE a ADD COLUMN x INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("3" * 64,),
        plan_hash="plan-scope-v1",
        approval_token=token,
        now=now,
    )
    assert res1.is_authorized is True

    # Evaluate for change "chg-table-B" with approval_token=None
    res2 = gate.evaluate_change_sql(
        change_id="chg-table-B",
        sql_up="ALTER TABLE b DROP COLUMN x;",
        sql_down="ALTER TABLE b ADD COLUMN x INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("3" * 64,),
        plan_hash="plan-scope-v1",
        approval_token=None,
        now=now,
    )
    assert res2.is_authorized is False
    assert res2.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res2.compression_card is not None


def test_reusable_authority_changed_slot_invalidates_reuse():
    """4. Changed authority slot invalidates reuse."""
    now = _utc_now()
    decision = VerifiedAuthorityDecision(
        decision_id="auth-dec-004",
        envelope_id="tok-env-004",
        approver_id="sec-officer@enterprise.org",
        authority_slot_ref="slot:security_officer",
        plan_hash="plan-slot-v1",
        action_scope="Target: Production. Change: chg-004",
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    # Expected slot is slot:lead_dba
    assert (
        decision.is_active_for(
            plan_hash="plan-slot-v1",
            authority_slot_ref="slot:lead_dba",
            action_scope="Target: Production. Change: chg-004",
            now=now,
        )
        is False
    )


def test_reusable_authority_expiry_invalidates_reuse():
    """5. Expired authority invalidates reuse."""
    secret = "test-secret-key-32-chars-long!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    now = _utc_now()

    # Sign and verify token with 10 seconds validity
    token = TestHmacAuthoritySigner.sign_token(
        plan_hash="plan-exp-v1",
        approver_id="alice@lead-dba.org",
        authority_slot_ref="slot:lead_dba",
        secret_key=secret,
        action_scope="Target: Production. Change: chg-005",
        validity_seconds=10,
        now=now,
    )
    res1 = gate.evaluate_change_sql(
        change_id="chg-005",
        sql_up="ALTER TABLE c DROP COLUMN y;",
        sql_down="ALTER TABLE c ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("5" * 64,),
        plan_hash="plan-exp-v1",
        approval_token=token,
        now=now,
    )
    assert res1.is_authorized is True

    # Call gate after expiration (20 seconds later) with approval_token=None
    res2 = gate.evaluate_change_sql(
        change_id="chg-005",
        sql_up="ALTER TABLE c DROP COLUMN y;",
        sql_down="ALTER TABLE c ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("5" * 64,),
        plan_hash="plan-exp-v1",
        approval_token=None,
        now=now + timedelta(seconds=20),
    )
    assert res2.is_authorized is False
    assert res2.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res2.compression_card is not None


def test_reusable_authority_superseded_or_revoked_invalidates_reuse():
    """6. Superseded or revoked authority invalidates reuse."""
    secret = "test-secret-key-32-chars-long!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    now = _utc_now()
    plan_hash = "plan-revoke-v1"
    scope = "Target: Production. Change: chg-006"

    # 1. Sign and verify token
    token = TestHmacAuthoritySigner.sign_token(
        plan_hash=plan_hash,
        approver_id="alice@lead-dba.org",
        authority_slot_ref="slot:lead_dba",
        secret_key=secret,
        action_scope=scope,
        now=now,
    )
    res1 = gate.evaluate_change_sql(
        change_id="chg-006",
        sql_up="ALTER TABLE c DROP COLUMN z;",
        sql_down="ALTER TABLE c ADD COLUMN z INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("6" * 64,),
        plan_hash=plan_hash,
        approval_token=token,
        now=now,
    )
    assert res1.is_authorized is True

    # 2. Revoke decision in verifier
    dec = verifier.find_active_authority(
        plan_hash=plan_hash,
        authority_slot_ref="slot:lead_dba",
        action_scope=scope,
        now=now,
    )
    assert dec is not None
    assert verifier.revoke_decision(dec.decision_id) is True
    revoked = verifier.get_decision(dec.decision_id)
    assert revoked is not None and revoked.is_revoked is True

    # Evaluation with approval_token=None fails closed
    res_rev = gate.evaluate_change_sql(
        change_id="chg-006",
        sql_up="ALTER TABLE c DROP COLUMN z;",
        sql_down="ALTER TABLE c ADD COLUMN z INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("6" * 64,),
        plan_hash=plan_hash,
        approval_token=None,
        now=now,
    )
    assert res_rev.is_authorized is False
    assert res_rev.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res_rev.compression_card is not None

    # 3. Supersession test: Sign second token and supersede it
    token2 = TestHmacAuthoritySigner.sign_token(
        plan_hash=plan_hash,
        approver_id="bob@lead-dba.org",
        authority_slot_ref="slot:lead_dba",
        secret_key=secret,
        action_scope=scope,
        now=now,
    )
    res2 = gate.evaluate_change_sql(
        change_id="chg-006",
        sql_up="ALTER TABLE c DROP COLUMN z;",
        sql_down="ALTER TABLE c ADD COLUMN z INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("6" * 64,),
        plan_hash=plan_hash,
        approval_token=token2,
        now=now,
    )
    assert res2.is_authorized is True

    dec2 = verifier.find_active_authority(
        plan_hash=plan_hash,
        authority_slot_ref="slot:lead_dba",
        action_scope=scope,
        now=now,
    )
    assert dec2 is not None
    assert verifier.supersede_decision(dec2.decision_id, "auth-dec-newer-008") is True

    res_sup = gate.evaluate_change_sql(
        change_id="chg-006",
        sql_up="ALTER TABLE c DROP COLUMN z;",
        sql_down="ALTER TABLE c ADD COLUMN z INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("6" * 64,),
        plan_hash=plan_hash,
        approval_token=None,
        now=now,
    )
    assert res_sup.is_authorized is False
    assert res_sup.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res_sup.compression_card is not None


def test_unverified_entity_cannot_become_verified_authority_decision():
    """7. Automated agents cannot self-authorize or create VerifiedAuthorityDecision."""
    now = _utc_now()
    forbidden_approvers = [
        "release_steward",
        "release-steward",
        "release_steward@enterprise.internal",
        "gemini",
        "gemini_semantic_judgment",
        "system",
        "orchestrator",
        "auto",
    ]
    for bad_approver in forbidden_approvers:
        with pytest.raises(ValidationError, match="violates authority separation"):
            VerifiedAuthorityDecision(
                decision_id="auth-dec-bad",
                envelope_id="tok-env-bad",
                approver_id=bad_approver,
                authority_slot_ref="slot:lead_dba",
                plan_hash="plan-h1",
                action_scope="Target: Production",
                issued_at=now,
                expires_at=now + timedelta(hours=1),
            )


def test_adversarial_fabricated_authority_decision_exploit_fails_completely():
    """Adversarial Proof: A freely constructed VerifiedAuthorityDecision cannot authorize anything.

    Proves:
    1. evaluate_inputs / evaluate_change_sql no longer exposes any verified_authority parameter;
    2. arbitrary VerifiedAuthorityDecision cannot be inserted into the production trusted
       authority resolver;
    3. fabricated data model instance alone never authorizes;
    4. Proof A: valid signed envelope -> authorized;
    5. Proof B: successful verification creates reusable decision;
    6. Proof C: second same-binding call reuses it;
    7. Proof D: invalid signature creates ZERO reusable decision;
    8. Proof E: wrong plan does not persist authority;
    9. Proof F: wrong scope does not persist authority;
    10. Proof G: expired envelope does not persist authority;
    11. Proof H: fabricated data model instance alone never authorizes.
    """
    secret = "test-secret-key-32-chars-long!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    now = _utc_now()
    plan_hash = "plan-adversarial-01"
    scope = "Target: Production. Change: chg-adv-01"
    slot_ref = "slot:lead_dba"

    # 1. Structural Check: PolicyGuardianGate.evaluate_inputs and evaluate_change_sql
    # MUST NOT have verified_authority parameter
    eval_inputs_params = inspect.signature(PolicyGuardianGate.evaluate_inputs).parameters
    assert "verified_authority" not in eval_inputs_params

    eval_sql_params = inspect.signature(PolicyGuardianGate.evaluate_change_sql).parameters
    assert "verified_authority" not in eval_sql_params

    # 2. Structural Check: HmacAuthorityDecisionVerifier MUST NOT expose store_decision
    assert not hasattr(verifier, "store_decision")

    # 3. Fabricate an arbitrary VerifiedAuthorityDecision
    fake = VerifiedAuthorityDecision(
        decision_id="fake-dec-001",
        envelope_id="fake-env-001",
        approver_id="alice@lead-dba.org",
        authority_slot_ref=slot_ref,
        plan_hash=plan_hash,
        action_scope=scope,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )

    # 4. Attempting to pass `verified_authority=fake` to evaluate_change_sql MUST raise TypeError
    with pytest.raises(TypeError, match="unexpected keyword argument 'verified_authority'"):
        gate.evaluate_change_sql(
            change_id="chg-adv-01",
            sql_up="ALTER TABLE x DROP COLUMN y;",
            sql_down="ALTER TABLE x ADD COLUMN y INT;",
            blast_radius=0.9,
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
            data_classification=DataClassLevel.INTERNAL,
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("1" * 64,),
            plan_hash=plan_hash,
            verified_authority=fake,  # type: ignore[call-arg]
        )

    # 5. Proof H: Fabricated decision alone without a signed envelope produces unauthorized / card
    res_fake_alone = gate.evaluate_change_sql(
        change_id="chg-adv-01",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=None,
    )
    assert res_fake_alone.is_authorized is False
    assert res_fake_alone.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
    assert res_fake_alone.compression_card is not None

    # 6. Proof A: Valid signed envelope -> authorized
    valid_token = TestHmacAuthoritySigner.sign_token(
        plan_hash=plan_hash,
        approver_id="alice@lead-dba.org",
        authority_slot_ref=slot_ref,
        secret_key=secret,
        action_scope=scope,
        now=now,
    )
    res_valid = gate.evaluate_change_sql(
        change_id="chg-adv-01",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=valid_token,
        now=now,
    )
    assert res_valid.is_authorized is True
    assert "Valid cryptographic approval token" in res_valid.decision_summary

    # 7. Proof B & C: Successful verification created reusable decision; second call reuses it
    res_reused = gate.evaluate_change_sql(
        change_id="chg-adv-01",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=None,
        now=now + timedelta(minutes=2),
    )
    assert res_reused.is_authorized is True
    assert res_reused.compression_card is None
    assert "reused without re-prompt" in res_reused.decision_summary

    # 8. Proof D: Invalid signature creates ZERO reusable decision
    fresh_verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    fresh_gate = PolicyGuardianGate(authority_verifier=fresh_verifier)
    bad_token = SignedAuthorityEnvelope(
        token_id="tok-bad-01",
        plan_hash=plan_hash,
        approver_id="alice@lead-dba.org",
        authority_slot_ref=slot_ref,
        action_scope=scope,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        nonce="nonce-1",
        signature="invalid-fake-signature-00000000000000000000000000000000000000000000",
    )
    res_bad_sig = fresh_gate.evaluate_change_sql(
        change_id="chg-adv-01",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=bad_token,
        now=now,
    )
    assert res_bad_sig.is_authorized is False
    assert res_bad_sig.autonomy_class == AutonomyClass.BLOCKED
    assert "INVALID_SIGNATURE" in res_bad_sig.decision_summary

    # Verifier stored ZERO decision
    assert fresh_verifier.find_active_authority(plan_hash, slot_ref, scope, now=now) is None
    # Subsequent call without token cannot authorize
    res_bad_sig_2 = fresh_gate.evaluate_change_sql(
        change_id="chg-adv-01",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=None,
        now=now,
    )
    assert res_bad_sig_2.is_authorized is False
    assert res_bad_sig_2.compression_card is not None

    # 9. Proof E: Wrong plan does not persist authority
    wrong_plan_verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    wrong_plan_gate = PolicyGuardianGate(authority_verifier=wrong_plan_verifier)
    plan_token = TestHmacAuthoritySigner.sign_token(
        plan_hash="plan-A",
        approver_id="alice@lead-dba.org",
        authority_slot_ref=slot_ref,
        secret_key=secret,
        action_scope=scope,
        now=now,
    )
    res_wrong_plan = wrong_plan_gate.evaluate_change_sql(
        change_id="chg-adv-01",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash="plan-B",
        approval_token=plan_token,
        now=now,
    )
    assert res_wrong_plan.is_authorized is False
    assert wrong_plan_verifier.find_active_authority("plan-B", slot_ref, scope, now=now) is None

    # 10. Proof F: Wrong scope does not persist authority
    wrong_scope_verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    wrong_scope_gate = PolicyGuardianGate(authority_verifier=wrong_scope_verifier)
    scope_token = TestHmacAuthoritySigner.sign_token(
        plan_hash=plan_hash,
        approver_id="alice@lead-dba.org",
        authority_slot_ref=slot_ref,
        secret_key=secret,
        action_scope="Target: Staging. Change: chg-adv-01",
        now=now,
    )
    res_wrong_scope = wrong_scope_gate.evaluate_change_sql(
        change_id="chg-adv-01",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=scope_token,
        now=now,
    )
    assert res_wrong_scope.is_authorized is False
    assert wrong_scope_verifier.find_active_authority(plan_hash, slot_ref, scope, now=now) is None

    # 11. Proof G: Expired envelope does not persist authority
    exp_verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    exp_gate = PolicyGuardianGate(authority_verifier=exp_verifier)
    exp_token = TestHmacAuthoritySigner.sign_token(
        plan_hash=plan_hash,
        approver_id="alice@lead-dba.org",
        authority_slot_ref=slot_ref,
        secret_key=secret,
        action_scope=scope,
        validity_seconds=5,
        now=now - timedelta(seconds=60),
    )
    res_exp = exp_gate.evaluate_change_sql(
        change_id="chg-adv-01",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=plan_hash,
        approval_token=exp_token,
        now=now,
    )
    assert res_exp.is_authorized is False
    assert exp_verifier.find_active_authority(plan_hash, slot_ref, scope, now=now) is None


# ============================================================================
# Adversarial & Static Architecture Invariants
# ============================================================================


def test_static_credential_boundary_core_has_no_secrets():
    """Static test proving core gate classes and modules do not hold secret parameters/fields."""
    # Check SignedAuthorityEnvelope
    envelope_fields = SignedAuthorityEnvelope.model_fields.keys()
    assert "secret" not in envelope_fields
    assert "verification_secret" not in envelope_fields
    assert "secret_key" not in envelope_fields

    # Check VerifiedAuthorityDecision
    decision_fields = VerifiedAuthorityDecision.model_fields.keys()
    assert "secret" not in decision_fields
    assert "verification_secret" not in decision_fields
    assert "secret_key" not in decision_fields

    # Check PolicyGuardianGate constructor params
    gate_init_params = inspect.signature(PolicyGuardianGate.__init__).parameters
    assert "secret" not in gate_init_params
    assert "verification_secret" not in gate_init_params
    assert "secret_key" not in gate_init_params


def test_plan_hash_binding_invariants():
    """Prove missing plan hash, placeholder plan hash, or mismatched plan hash cannot authorize."""
    secret = "secret-key-32-chars-test-only!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)
    token = TestHmacAuthoritySigner.sign_token(
        plan_hash="plan-real-hash-123",
        approver_id="alice@lead-dba.org",
        authority_slot_ref="slot:lead_dba",
        secret_key=secret,
        action_scope="Target: Production. Change: chg-test-plan",
    )

    # 1. Authority token + missing plan identity (None / empty) -> BLOCKED
    res_no_plan = gate.evaluate_change_sql(
        change_id="chg-test-plan",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash=None,
        approval_token=token,
    )
    assert res_no_plan.is_authorized is False
    assert res_no_plan.autonomy_class == AutonomyClass.BLOCKED
    assert "Explicit active plan hash required" in res_no_plan.decision_summary

    # 2. Authority token + wrong plan identity -> BLOCKED
    res_wrong_plan = gate.evaluate_change_sql(
        change_id="chg-test-plan",
        sql_up="ALTER TABLE x DROP COLUMN y;",
        sql_down="ALTER TABLE x ADD COLUMN y INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        plan_hash="plan-wrong-hash-456",
        approval_token=token,
    )
    assert res_wrong_plan.is_authorized is False
    assert res_wrong_plan.autonomy_class == AutonomyClass.BLOCKED
    assert "STALE_PLAN_HASH" in res_wrong_plan.decision_summary


def test_adversarial_evaluate_change_sql_omitted_facts_fail_closed():
    """Adversarial invariant: omitted facts MUST NOT obtain AUTO_EXECUTE from helper defaults."""
    gate = PolicyGuardianGate()

    # Omitted facts: blast_radius, privilege, sensitivity, novelty, evidence_state
    # Even with syntactically valid SQL and valid SHA-256 evidence digest, it MUST fail closed.
    res_omitted = gate.evaluate_change_sql(
        change_id="chg-adversarial-01",
        sql_up="ALTER TABLE users ADD COLUMN phone TEXT;",
        sql_down="ALTER TABLE users DROP COLUMN phone;",
        evidence_digests=("a" * 64,),
    )
    assert res_omitted.is_authorized is False
    assert res_omitted.autonomy_class == AutonomyClass.BLOCKED
    assert res_omitted.autonomy_class != AutonomyClass.AUTO_EXECUTE


# ============================================================================
# P-14.06: Real Friction Metric Calculation
# ============================================================================


def test_friction_metrics_calculation_from_real_traces():
    """Verify FrictionMetricsCalculator computes metric artifact from actual traces."""
    secret = "test-secret-key-32-chars-long!!"
    verifier = HmacAuthorityDecisionVerifier(verification_secret=secret)
    gate = PolicyGuardianGate(authority_verifier=verifier)

    eval1 = gate.evaluate_change_sql(
        "c1",
        "ALTER TABLE a ADD COLUMN x INT;",
        "ALTER TABLE a DROP COLUMN x;",
        blast_radius=0.1,
        privilege_level=PrivilegeLevel.STANDARD_WRITE,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("1" * 64,),
        rehearsal_status=RehearsalStatus.NOT_REQUIRED,
    )
    eval2 = gate.evaluate_change_sql(
        "c2",
        "ALTER TABLE b ADD COLUMN y INT;",
        "ALTER TABLE b DROP COLUMN y;",
        blast_radius=0.1,
        privilege_level=PrivilegeLevel.STANDARD_WRITE,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("2" * 64,),
        rehearsal_status=RehearsalStatus.NOT_REQUIRED,
    )
    eval3 = gate.evaluate_change_sql(
        "c3",
        "CREATE VIEW v AS SELECT 1;",
        None,
        blast_radius=0.2,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("3" * 64,),
        rehearsal_status=RehearsalStatus.REHEARSAL_PASSED,
        rehearsal_digests=("3" * 64,),
    )
    eval4 = gate.evaluate_change_sql(
        "c4",
        "DROP TABLE c;",
        None,
        blast_radius=0.5,
        privilege_level=PrivilegeLevel.DDL_ADMIN,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        evidence_digests=("4" * 64,),
        rehearsal_status=RehearsalStatus.NOT_REQUIRED,
    )

    token = TestHmacAuthoritySigner.sign_token(
        "plan-h5", "dba@org", "slot:lead_dba", secret, action_scope="Target: Production. Change: c5"
    )
    eval5 = gate.evaluate_change_sql(
        "c5",
        "ALTER TABLE d DROP COLUMN z;",
        "ALTER TABLE d ADD COLUMN z INT;",
        blast_radius=0.9,
        privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
        data_classification=DataClassLevel.INTERNAL,
        novelty_tier=NoveltyTier.ROUTINE_KNOWN,
        evidence_state=EvidenceState.PASS,
        plan_hash="plan-h5",
        approval_token=token,
        evidence_digests=("5" * 64,),
        rehearsal_status=RehearsalStatus.NOT_REQUIRED,
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
            evidence_state=EvidenceState.PASS,
            evidence_digests=("a" * 64,),
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
            evidence_digests=("a" * 64,),
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
            evidence_digests=("a" * 64,),
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
            has_down_migration=True,
            data_classification=DataClassLevel.INTERNAL,
            privilege_level=PrivilegeLevel.STANDARD_WRITE,
            novelty_tier=NoveltyTier.NOVEL_UNVERIFIED,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("a" * 64,),
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
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("a" * 64,),
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
            has_down_migration=True,
            data_classification=DataClassLevel.INTERNAL,
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("a" * 64,),
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
            has_down_migration=True,
            data_classification=DataClassLevel.INTERNAL,
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("a" * 64,),
            rehearsal_status=RehearsalStatus.REHEARSAL_PASSED,
            rehearsal_digests=("b" * 64,),
        )
    )
    assert res_reh_pass.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE
    assert res_reh_pass.is_authorized is True


def test_fail_closed_deterministic_policy_invariants():
    """Prove the 7 core fail-closed policy invariants:
    1. minimal DeterministicPolicyInputs cannot authorize
    2. reversible SQL + no evidence cannot authorize
    3. SIMULATED + empty evidence_digests cannot authorize
    4. REHEARSAL_PASSED + empty rehearsal_digests cannot satisfy rehearsal
    5. explicit complete safe facts can still AUTO_EXECUTE
    6. explicit complete rehearse-required facts can still REHEARSE_THEN_EXECUTE
    7. explicit organizational policy may still allow LIVE_WRITE without HUMAN_AUTHORITY_REQUIRED
    """
    gate = PolicyGuardianGate()

    # 1. Minimal DeterministicPolicyInputs cannot authorize
    minimal_inputs = DeterministicPolicyInputs(change_id="chg-minimal")
    res_min = gate.evaluate_inputs(minimal_inputs)
    assert res_min.is_authorized is False
    assert res_min.autonomy_class == AutonomyClass.BLOCKED
    assert res_min.autonomy_class != AutonomyClass.HUMAN_AUTHORITY_REQUIRED

    # 2. Reversible SQL + no evidence cannot authorize
    res_sql_no_ev = gate.evaluate_change_sql(
        change_id="chg-sql-no-ev",
        sql_up="ALTER TABLE users ADD COLUMN phone TEXT;",
        sql_down="ALTER TABLE users DROP COLUMN phone;",
        blast_radius=0.1,
        evidence_digests=(),
    )
    assert res_sql_no_ev.is_authorized is False
    assert res_sql_no_ev.autonomy_class == AutonomyClass.BLOCKED

    # 3. SIMULATED + empty evidence_digests cannot authorize
    res_sim_empty = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-sim-empty",
            blast_radius_score=0.1,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            has_down_migration=True,
            data_classification=DataClassLevel.INTERNAL,
            privilege_level=PrivilegeLevel.STANDARD_WRITE,
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.SIMULATED,
            evidence_digests=(),
            rehearsal_status=RehearsalStatus.NOT_REQUIRED,
        )
    )
    assert res_sim_empty.is_authorized is False
    assert res_sim_empty.autonomy_class == AutonomyClass.BLOCKED

    # 4. REHEARSAL_PASSED + empty rehearsal_digests cannot satisfy rehearsal
    res_reh_empty = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-reh-empty",
            blast_radius_score=0.2,
            reversibility_class=ReversibilityClass.REVERSIBLE_WITH_COMPENSATION,
            has_down_migration=True,
            data_classification=DataClassLevel.INTERNAL,
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("1" * 64,),
            rehearsal_status=RehearsalStatus.REHEARSAL_PASSED,
            rehearsal_digests=(),
        )
    )
    assert res_reh_empty.is_authorized is False
    assert res_reh_empty.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE

    # 5. Explicit complete safe facts can still AUTO_EXECUTE
    res_safe_auto = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-safe-auto",
            blast_radius_score=0.1,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            has_down_migration=True,
            data_classification=DataClassLevel.INTERNAL,
            privilege_level=PrivilegeLevel.STANDARD_WRITE,
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("2" * 64,),
            rehearsal_status=RehearsalStatus.NOT_REQUIRED,
        )
    )
    assert res_safe_auto.is_authorized is True
    assert res_safe_auto.autonomy_class == AutonomyClass.AUTO_EXECUTE

    # 6. Explicit complete rehearse-required facts can still REHEARSE_THEN_EXECUTE
    res_reh_ok = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-reh-ok",
            blast_radius_score=0.2,
            reversibility_class=ReversibilityClass.REVERSIBLE_WITH_COMPENSATION,
            has_down_migration=True,
            data_classification=DataClassLevel.INTERNAL,
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("3" * 64,),
            rehearsal_status=RehearsalStatus.REHEARSAL_PASSED,
            rehearsal_digests=("4" * 64,),
        )
    )
    assert res_reh_ok.is_authorized is True
    assert res_reh_ok.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE

    # 7. Explicit organizational policy may still allow LIVE_WRITE without HUMAN_AUTHORITY_REQUIRED
    res_live_write = gate.evaluate_inputs(
        DeterministicPolicyInputs(
            change_id="chg-live-write",
            blast_radius_score=0.15,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            has_down_migration=True,
            data_classification=DataClassLevel.INTERNAL,
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            evidence_state=EvidenceState.PASS,
            evidence_digests=("5" * 64,),
            rehearsal_status=RehearsalStatus.NOT_REQUIRED,
        )
    )
    assert res_live_write.is_authorized is True
    assert res_live_write.autonomy_class == AutonomyClass.AUTO_EXECUTE
    assert res_live_write.autonomy_class != AutonomyClass.HUMAN_AUTHORITY_REQUIRED
