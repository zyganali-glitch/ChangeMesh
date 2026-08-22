"""ChangeMesh P-26.04 — Authorization Boundaries and External-Write Restrictions Security Suite.

Acceptance criteria from master plan:
  - No agent merges, production-deploys, or accesses unregistered data.
  - Verification of GitHub adapter draft-only boundaries and protected branch enforcement.
  - Verification that Release Steward cannot trigger live production deployments or self-authorize.
  - Verification that deterministic policy guardian blocks attempts to access
    unregistered tables or unauthorized paths.
  - Verification that organizational policy (not LLM confidence) governs autonomy class.
  - Verification that LIVE_WRITE != HUMAN_AUTHORITY_REQUIRED.
  - Verification that Gemini uncertainty cannot manufacture human authority.
  - Verification that invalid/expired/scope-mismatched authority tokens fail closed.
  - Verification that waiting for authority (AWAITING_AUTHORITY) is distinct from BLOCKED.

Required evidence: Security suite (docs/P-26.04_AUTHORIZATION_BOUNDARIES_REPORT.md).
Mandatory documentation sync: Judging map.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from domain.contracts.autonomy import AutonomyClass
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import ExecutionEvidenceMode
from domain.contracts.success_criterion import SuccessCriterion
from integrations.github.github_adapter import (
    BoundedGitHubAdapter,
    GitHubAction,
    GitHubRequest,
)
from src.audit.reconciliation import DeterministicReconciler, ReconciliationOutcome
from src.audit.semantic_auditor import ClaimAuditResult, SemanticVerdict
from src.gate.policy_guardian_gate import PolicyGuardianGate
from src.gate.reversibility import (
    DeterministicPolicyInputs,
    NoveltyTier,
    PrivilegeLevel,
    RehearsalStatus,
    ReversibilityClass,
    ReversibilityClassifier,
)
from src.gate.token import (
    VerifiedAuthorityDecision,
)
from src.orchestrator.orchestrator_saga import (
    validate_supported_change_intent,
)
from src.policy.policy_engine import (
    DeterministicPolicyChecker,
    PolicyFindingCategory,
)


class TestGitHubAuthorizationBoundaries:
    """Verify that GitHub adapter enforces strict draft-only and non-destructive boundaries."""

    def test_github_actions_enum_forbids_merge_and_destructive_operations(self):
        """GitHubAction enum must only permit CREATE_BRANCH, CREATE_COMMIT, and CREATE_DRAFT_PR."""
        valid_actions = {a.value for a in GitHubAction}
        assert "MERGE_PR" not in valid_actions
        assert "DELETE_REPO" not in valid_actions
        assert "FORCE_PUSH" not in valid_actions
        assert "UPDATE_PROTECTED_BRANCH" not in valid_actions
        assert valid_actions == {"CREATE_BRANCH", "CREATE_COMMIT", "CREATE_DRAFT_PR"}

    def test_github_request_rejects_invalid_action(self):
        """Constructing a GitHubRequest with an invalid action must fail validation."""
        with pytest.raises(ValidationError):
            GitHubRequest.model_validate(
                {
                    "request_id": "req-1",
                    "action": "MERGE_PR",
                    "repository": "zyganali-glitch/changemesh",
                    "evidence_mode": "FIXTURE",
                }
            )

    def test_github_adapter_blocks_commits_to_protected_branches(self):
        """BoundedGitHubAdapter must block direct commits to protected branches."""
        adapter = BoundedGitHubAdapter(
            token="ghp_" + "dummy_token_1234567890abcdef",
        )
        for protected in ["main", "master", "prod", "production", "release"]:
            request = GitHubRequest(
                request_id=f"req-commit-{protected}",
                action=GitHubAction.CREATE_COMMIT,
                repository="zyganali-glitch/changemesh",
                branch=protected,
                commit_message="Direct commit to protected branch",
                files={"migrations/001.sql": "SELECT 1;"},
                evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
            )
            response = adapter.execute(request)
            assert response.success is False
            assert "forbidden" in response.error_message.lower()

    def test_github_adapter_blocks_branch_creation_named_protected(self):
        """BoundedGitHubAdapter must block creating a branch with a protected name."""
        adapter = BoundedGitHubAdapter(
            token="ghp_" + "dummy_token_1234567890abcdef",
        )
        request = GitHubRequest(
            request_id="req-branch-main",
            action=GitHubAction.CREATE_BRANCH,
            repository="zyganali-glitch/changemesh",
            branch="main",
            evidence_mode=ExecutionEvidenceMode.LIVE_WRITE,
        )
        response = adapter.execute(request)
        assert response.success is False
        assert "forbidden" in response.error_message.lower()


class TestPolicyGuardianAuthorizationBoundaries:
    """Verify that Policy Guardian denies unauthorized paths and unregistered tools."""

    def test_policy_blocks_unauthorized_governance_and_system_paths(self):
        """DeterministicPolicyChecker must block attempts to modify contracts or workflows."""
        checker = DeterministicPolicyChecker()
        unauthorized_paths = [
            "domain/contracts/change_lifecycle.py",
            ".github/workflows/deploy.yml",
            ".env",
            "/etc/passwd",
            "../outside_repo/config.json",
        ]
        for path in unauthorized_paths:
            decision = checker.evaluate(
                input_text="SELECT 1;",
                tool_ids=["tool-sql-generator"],
                target_paths=[path],
                action_type="schema_migration",
                data_classification="INTERNAL",
                change_id="chg-auth-01",
            )
            assert decision.overall_verdict == "BLOCK"
            assert any(
                f.category == PolicyFindingCategory.UNAUTHORIZED_PATH for f in decision.findings
            )

    def test_policy_blocks_unregistered_tools(self):
        """DeterministicPolicyChecker must block tools not in the registered whitelist."""
        checker = DeterministicPolicyChecker()
        decision = checker.evaluate(
            input_text="SELECT 1;",
            tool_ids=["unregistered_arbitrary_shell_executor"],
            target_paths=["tmp/test.sql"],
            action_type="schema_migration",
            data_classification="INTERNAL",
            change_id="chg-auth-02",
        )
        assert decision.overall_verdict == "BLOCK"
        assert any(f.category == PolicyFindingCategory.UNREGISTERED_TOOL for f in decision.findings)


class TestReversibilityAndAuthorityBoundaries:
    """Verify 4-lane authority boundaries, token validation, and human decision slots."""

    def test_destructive_sql_operations_fail_intent_validation(self):
        """validate_supported_change_intent must reject destructive DROP/DELETE operations."""
        now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
        destructive_requests = [
            ChangeRequest(
                schema_version="1.0.0",
                request_id="req-destruct-01",
                title="Drop accounts table",
                description="DROP TABLE billing_accounts;",
                target_systems=["billing-db"],
                data_classification=DataClassLevel.INTERNAL,
                success_criteria=[
                    SuccessCriterion(
                        schema_version="1.0.0",
                        criterion_id="sc-1",
                        description="Table removed",
                        verification_method="deterministic",
                        required_evidence_types=["POLICY_EVALUATION"],
                    )
                ],
                requested_by="attacker",
                requested_at=now,
            ),
            ChangeRequest(
                schema_version="1.0.0",
                request_id="req-destruct-02",
                title="Truncate accounts table",
                description="TRUNCATE billing_accounts;",
                target_systems=["billing-db"],
                data_classification=DataClassLevel.INTERNAL,
                success_criteria=[
                    SuccessCriterion(
                        schema_version="1.0.0",
                        criterion_id="sc-2",
                        description="Data cleared",
                        verification_method="deterministic",
                        required_evidence_types=["POLICY_EVALUATION"],
                    )
                ],
                requested_by="attacker",
                requested_at=now,
            ),
        ]
        for req in destructive_requests:
            valid, reason = validate_supported_change_intent(req)
            assert valid is False
            assert "destructive" in reason.lower()

    def test_destructive_sql_classified_as_irreversible_or_human_intervention(self):
        """ReversibilityClassifier must classify destructive DDLs appropriately."""
        assessment_no_down = ReversibilityClassifier.classify_sql(
            change_id="chg-rev-01",
            sql_up="ALTER TABLE billing_accounts DROP COLUMN balance;",
            sql_down=None,
        )
        assert assessment_no_down.reversibility_class == ReversibilityClass.IRREVERSIBLE_DESTRUCTIVE
        assert assessment_no_down.has_down_migration is False

        assessment_with_down = ReversibilityClassifier.classify_sql(
            change_id="chg-rev-02",
            sql_up="ALTER TABLE billing_accounts DROP COLUMN balance;",
            sql_down="ALTER TABLE billing_accounts ADD COLUMN balance NUMERIC;",
        )
        assert (
            assessment_with_down.reversibility_class
            == ReversibilityClass.HUMAN_INTERVENTION_REQUIRED
        )
        assert assessment_with_down.has_down_migration is True

    def test_release_steward_cannot_self_authorize(self):
        """VerifiedAuthorityDecision must reject executor/steward identities as approvers."""
        now = datetime.now(timezone.utc)
        forbidden_approvers = [
            "release_steward",
            "release-steward",
            "gemini",
            "orchestrator",
            "system",
            "auto",
        ]
        for bad_approver in forbidden_approvers:
            with pytest.raises(ValidationError, match="cannot self-authorize"):
                VerifiedAuthorityDecision(
                    schema_version="1.0.0",
                    decision_id=f"dec-{bad_approver}",
                    envelope_id="env-1",
                    approver_id=bad_approver,
                    authority_slot_ref="slot-prod-release",
                    plan_hash="hash-12345678",
                    action_scope="scope-1",
                    issued_at=now,
                    expires_at=now + timedelta(hours=1),
                )

    def test_gemini_uncertainty_cannot_manufacture_human_authority(self):
        """Model disagreement or uncertainty must not create required human review slots."""
        reconciler = DeterministicReconciler()

        audit_result = ClaimAuditResult(
            claim_id="claim-001",
            verdict=SemanticVerdict.CONTRADICTS,  # Model disagrees with deterministic fact
            reasoning="Model disagrees with deterministic result",
        )

        recon_res = reconciler.reconcile(
            audit_result=audit_result,
            deterministic_state="PASS",
            change_id="chg-001",
        )

        # Disagreement is recorded, but outcome is ADVISORY_REVIEW, not ESCALATION
        assert recon_res.disagreement_detected is True
        assert recon_res.outcome == ReconciliationOutcome.ADVISORY_REVIEW
        assert recon_res.deterministic_state == "PASS"
        assert recon_res.deterministic_state_preserved is True

    def test_invalid_expired_scope_mismatched_token_rejected(self):
        """VerifiedAuthorityDecision must reject expired or scope-mismatched decisions."""
        now = datetime.now(timezone.utc)

        # 1. Valid decision
        decision = VerifiedAuthorityDecision(
            schema_version="1.0.0",
            decision_id="dec-001",
            envelope_id="env-001",
            approver_id="human:vp-eng-alice",
            authority_slot_ref="slot-schema-change",
            plan_hash="plan-hash-abc",
            action_scope="billing-db",
            issued_at=now - timedelta(minutes=10),
            expires_at=now + timedelta(hours=1),
        )
        assert (
            decision.is_active_for(
                plan_hash="plan-hash-abc",
                authority_slot_ref="slot-schema-change",
                action_scope="billing-db",
                now=now,
            )
            is True
        )

        # 2. Plan hash mismatch
        assert (
            decision.is_active_for(
                plan_hash="plan-hash-WRONG",
                authority_slot_ref="slot-schema-change",
                action_scope="billing-db",
                now=now,
            )
            is False
        )

        # 3. Scope mismatch
        assert (
            decision.is_active_for(
                plan_hash="plan-hash-abc",
                authority_slot_ref="slot-schema-change",
                action_scope="auth-db",
                now=now,
            )
            is False
        )

        # 4. Expired decision
        expired_decision = VerifiedAuthorityDecision(
            schema_version="1.0.0",
            decision_id="dec-002",
            envelope_id="env-002",
            approver_id="human:vp-eng-alice",
            authority_slot_ref="slot-schema-change",
            plan_hash="plan-hash-abc",
            action_scope="billing-db",
            issued_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        assert (
            expired_decision.is_active_for(
                plan_hash="plan-hash-abc",
                authority_slot_ref="slot-schema-change",
                action_scope="billing-db",
                now=now,
            )
            is False
        )

    def test_awaiting_authority_distinct_from_blocked_and_retains_autonomy(self):
        """AWAITING_AUTHORITY halts for human sign-off without marking change BLOCKED."""
        gate = PolicyGuardianGate()
        now = datetime.now(timezone.utc)

        # Change requiring human authority with qualifying evidence digests
        from domain.contracts.evidence import EvidenceState

        inputs = DeterministicPolicyInputs(
            change_id="chg-await-01",
            reversibility_class=ReversibilityClass.HUMAN_INTERVENTION_REQUIRED,
            blast_radius_score=0.45,
            novelty_tier=NoveltyTier.NOVEL_UNVERIFIED,
            privilege_level=PrivilegeLevel.STANDARD_WRITE,
            data_classification=DataClassLevel.INTERNAL,
            rehearsal_status=RehearsalStatus.REHEARSAL_PASSED,
            has_down_migration=True,
            rollback_summary="Execute down migration",
            evidence_state=EvidenceState.PASS,
            evidence_digests=["a" * 64],
        )

        res = gate.evaluate_inputs(inputs, now=now)
        assert res.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
        assert res.is_authorized is False
        assert res.compression_card is not None
        assert res.compression_card.decision_question != ""
        assert res.autonomy_class != AutonomyClass.BLOCKED
