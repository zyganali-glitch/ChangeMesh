"""ChangeMesh Policy Guardian Reversibility Gate and Decision Engine.

P-14.01 & P-14.02: Evaluates all 7 deterministic policy inputs against organizational policy,
enforces autonomous-by-default execution, issues compressed decision packets for genuine
human authority slots, and validates signed approval tokens through injected verifiers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict

from domain.contracts.autonomy import ApprovalCompressionCard, AutonomyClass
from domain.contracts.evidence import EvidenceState
from src.gate.compression import (
    ApprovalCompressionEngine,
    LockedFact,
    LockedFactBundle,
)
from src.gate.reversibility import (
    DeterministicPolicyInputs,
    PrivilegeLevel,
    RehearsalStatus,
    ReversibilityAssessment,
    ReversibilityClass,
    ReversibilityClassifier,
)
from src.gate.token import (
    SignedApprovalToken,
    TrustedAuthorityDecisionVerifier,
)

CANONICAL_SCHEMA_VERSION = "1.0.0"


class PolicyGateEvaluationResult(BaseModel):
    """Authoritative gate decision issued by Policy Guardian."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    change_id: str
    autonomy_class: AutonomyClass
    is_authorized: bool
    reversibility_assessment: ReversibilityAssessment
    compression_card: Optional[ApprovalCompressionCard] = None
    audit_trace_id: str
    decision_summary: str


class PolicyGuardianGate:
    """The central Policy Guardian reversibility and authorization gate."""

    def __init__(
        self, authority_verifier: Optional[TrustedAuthorityDecisionVerifier] = None
    ) -> None:
        self._authority_verifier = authority_verifier

    def evaluate_inputs(
        self,
        inputs: DeterministicPolicyInputs,
        plan_hash: str = "plan-hash-1",
        approval_token: Optional[SignedApprovalToken] = None,
        assessment: Optional[ReversibilityAssessment] = None,
    ) -> PolicyGateEvaluationResult:
        """Evaluate deterministic policy inputs against organizational autonomy policy."""
        trace_id = f"trace-gate-{uuid.uuid4().hex[:8]}"

        if assessment is None:
            is_full_rev = (
                inputs.reversibility_class == ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED
            )
            assessment = ReversibilityAssessment(
                change_id=inputs.change_id,
                reversibility_class=inputs.reversibility_class,
                blast_radius_score=inputs.blast_radius_score,
                has_down_migration=inputs.has_down_migration,
                rollback_plan_summary=inputs.rollback_summary,
                reversibility_score=1.0 if is_full_rev else 0.5,
                rationale=(
                    f"Classified {inputs.reversibility_class.value} "
                    f"with blast radius {inputs.blast_radius_score:.2f}"
                ),
            )

        # 1. Irreversible Destructive -> Blocked immediately
        if (
            inputs.reversibility_class == ReversibilityClass.IRREVERSIBLE_DESTRUCTIVE
            and not inputs.has_down_migration
        ):
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.BLOCKED,
                is_authorized=False,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="BLOCKED: Irreversible operation lacks down migration",
            )

        # 2. Failed Evidence or Quarantined Input -> Blocked
        if inputs.evidence_state == EvidenceState.FAIL:
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.BLOCKED,
                is_authorized=False,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="BLOCKED: Underlying evidence or qualification failed",
            )

        # 3. High Blast Radius, Destructive DDL, or Elevated Privilege -> HUMAN_AUTHORITY_REQUIRED
        is_human_required = (
            inputs.reversibility_class == ReversibilityClass.HUMAN_INTERVENTION_REQUIRED
            or inputs.blast_radius_score > 0.8
            or inputs.privilege_level
            in (PrivilegeLevel.DDL_ADMIN, PrivilegeLevel.IAM_ADMIN, PrivilegeLevel.DATA_EXPORT)
        )

        if is_human_required:
            if approval_token is None:
                # Generate compressed decision card from locked facts
                blast_stmt = (
                    f"Blast radius estimated at {inputs.blast_radius_score:.2f} "
                    f"({inputs.blast_radius_reason})"
                )
                rehearsed_facts: tuple[LockedFact, ...] = ()
                if inputs.rehearsal_status == RehearsalStatus.REHEARSAL_PASSED:
                    rehearsed_facts = (
                        LockedFact(
                            fact_id=f"fact-rehearse-{inputs.change_id}",
                            source_agent="shadowlab",
                            category="REHEARSAL",
                            statement=f"Rehearsal status: {inputs.rehearsal_status.value}",
                            evidence_digest=inputs.rehearsal_digests[0]
                            if inputs.rehearsal_digests
                            else "b" * 64,
                        ),
                    )

                bundle = LockedFactBundle(
                    change_request_id=inputs.change_id,
                    completed_facts=(
                        LockedFact(
                            fact_id=f"fact-blast-{inputs.change_id}",
                            source_agent="impact_scout",
                            category="BLAST_RADIUS",
                            statement=blast_stmt,
                            evidence_digest=inputs.rehearsal_digests[0]
                            if inputs.rehearsal_digests
                            else "a" * 64,
                        ),
                    ),
                    rehearsed_facts=rehearsed_facts,
                    reversibility_assessment=assessment,
                    authority_slot_ref="slot:lead_dba",
                    decision_question=f"Authorize live execution of change {inputs.change_id}?",
                    decision_options=("APPROVE_EXECUTION", "REJECT_AND_REQUEST_REVISION"),
                    action_scope=f"Target: Production. Change: {inputs.change_id}",
                    risk_summary=(
                        f"High blast radius ({inputs.blast_radius_score:.2f}) "
                        f"or elevated privilege ({inputs.privilege_level.value})"
                    ),
                    consequence_summary="Live execution will mutate production database state.",
                    expires_at=datetime.now(timezone.utc),
                    evidence_refs=inputs.rehearsal_digests,
                )
                card = ApprovalCompressionEngine.generate_card(bundle)
                return PolicyGateEvaluationResult(
                    change_id=inputs.change_id,
                    autonomy_class=AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
                    is_authorized=False,
                    reversibility_assessment=assessment,
                    compression_card=card,
                    audit_trace_id=trace_id,
                    decision_summary="HUMAN_AUTHORITY_REQUIRED: External authority needed",
                )
            else:
                if self._authority_verifier is None:
                    return PolicyGateEvaluationResult(
                        change_id=inputs.change_id,
                        autonomy_class=AutonomyClass.BLOCKED,
                        is_authorized=False,
                        reversibility_assessment=assessment,
                        audit_trace_id=trace_id,
                        decision_summary="BLOCKED: No authority verifier configured",
                    )
                val = self._authority_verifier.verify_and_consume(
                    token=approval_token,
                    expected_plan_hash=plan_hash,
                    expected_slot_ref="slot:lead_dba",
                )
                if val.is_valid:
                    return PolicyGateEvaluationResult(
                        change_id=inputs.change_id,
                        autonomy_class=AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
                        is_authorized=True,
                        reversibility_assessment=assessment,
                        audit_trace_id=trace_id,
                        decision_summary=(
                            f"AUTHORIZED: Valid cryptographic approval token signed by "
                            f"{approval_token.approver_id}"
                        ),
                    )
                else:
                    return PolicyGateEvaluationResult(
                        change_id=inputs.change_id,
                        autonomy_class=AutonomyClass.BLOCKED,
                        is_authorized=False,
                        reversibility_assessment=assessment,
                        audit_trace_id=trace_id,
                        decision_summary=f"DENIED: Invalid token ({val.status})",
                    )

        # 4. Multi-Phase / Compensation / Novel -> REHEARSE_THEN_EXECUTE
        if (
            inputs.reversibility_class == ReversibilityClass.REVERSIBLE_WITH_COMPENSATION
            or inputs.rehearsal_status != RehearsalStatus.NOT_REQUIRED
        ):
            if inputs.rehearsal_status == RehearsalStatus.REHEARSAL_PASSED:
                return PolicyGateEvaluationResult(
                    change_id=inputs.change_id,
                    autonomy_class=AutonomyClass.REHEARSE_THEN_EXECUTE,
                    is_authorized=True,
                    reversibility_assessment=assessment,
                    audit_trace_id=trace_id,
                    decision_summary="REHEARSE_THEN_EXECUTE: Rehearsal passed; authorized",
                )
            else:
                return PolicyGateEvaluationResult(
                    change_id=inputs.change_id,
                    autonomy_class=AutonomyClass.REHEARSE_THEN_EXECUTE,
                    is_authorized=False,
                    reversibility_assessment=assessment,
                    audit_trace_id=trace_id,
                    decision_summary=(
                        f"UNAUTHORIZED: Rehearsal required before execution "
                        f"(status: {inputs.rehearsal_status.value})"
                    ),
                )

        # 5. Fully Reversible Automated -> AUTO_EXECUTE
        if (
            inputs.reversibility_class == ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED
            and inputs.blast_radius_score <= 0.3
            and inputs.has_down_migration
        ):
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.AUTO_EXECUTE,
                is_authorized=True,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="AUTO_EXECUTE: Fully reversible with automated rollback",
            )

        # 6. Moderate Routine -> AUTO_EXECUTE_AND_NOTIFY
        return PolicyGateEvaluationResult(
            change_id=inputs.change_id,
            autonomy_class=AutonomyClass.AUTO_EXECUTE_AND_NOTIFY,
            is_authorized=True,
            reversibility_assessment=assessment,
            audit_trace_id=trace_id,
            decision_summary="AUTO_EXECUTE_AND_NOTIFY: Executes autonomously with notify",
        )

    def evaluate_change_sql(
        self,
        change_id: str,
        sql_up: str,
        sql_down: Optional[str] = None,
        blast_radius: float = 0.1,
        plan_hash: str = "plan-hash-1",
        approval_token: Optional[SignedApprovalToken] = None,
        rehearsal_status: RehearsalStatus = RehearsalStatus.NOT_REQUIRED,
    ) -> PolicyGateEvaluationResult:
        """Convenience method to evaluate a SQL migration change."""
        assessment = ReversibilityClassifier.classify_sql(
            change_id=change_id,
            sql_up=sql_up,
            sql_down=sql_down,
            blast_radius_score=blast_radius,
        )
        inputs = DeterministicPolicyInputs(
            change_id=change_id,
            blast_radius_score=blast_radius,
            reversibility_class=assessment.reversibility_class,
            has_down_migration=assessment.has_down_migration,
            rollback_summary=assessment.rollback_plan_summary,
            rehearsal_status=rehearsal_status,
        )
        return self.evaluate_inputs(
            inputs=inputs,
            plan_hash=plan_hash,
            approval_token=approval_token,
            assessment=assessment,
        )
