"""ChangeMesh Policy Guardian Reversibility Gate and Decision Engine.

P-14.01 & P-14.02: Evaluates all 7 deterministic policy inputs against organizational policy,
enforces autonomous-by-default execution, issues compressed decision packets for genuine
human authority slots, and validates signed approval tokens through injected verifiers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict

from domain.contracts.autonomy import ApprovalCompressionCard, AutonomyClass
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import EvidenceState
from src.gate.compression import (
    ApprovalCompressionEngine,
    LockedFact,
    LockedFactBundle,
)
from src.gate.reversibility import (
    DeterministicPolicyInputs,
    NoveltyTier,
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
        now: Optional[datetime] = None,
    ) -> PolicyGateEvaluationResult:
        """Evaluate deterministic policy inputs against organizational autonomy policy."""
        if now is None:
            now = datetime.now(timezone.utc)
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

        # 1. Hard Blockers: Anomalous Novelty, Failed Evidence, Quarantined,
        # Destructive without Down Migration, Failed Rehearsal
        if inputs.novelty_tier == NoveltyTier.ANOMALOUS:
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.BLOCKED,
                is_authorized=False,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="BLOCKED: Anomalous change intent detected (fail closed)",
            )

        if inputs.evidence_state in (
            EvidenceState.FAIL,
            EvidenceState.QUARANTINED,
            EvidenceState.NOT_RUN,
        ):
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.BLOCKED,
                is_authorized=False,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary=(
                    f"BLOCKED: Underlying evidence state is {inputs.evidence_state.value}"
                ),
            )

        # Missing evidence or missing evidence digests fails closed
        # (SIMULATED/PASS with zero digests cannot qualify)
        if not inputs.evidence_digests or len(inputs.evidence_digests) == 0:
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.BLOCKED,
                is_authorized=False,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="BLOCKED: Missing qualifying evidence digests (fail closed)",
            )

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

        if inputs.rehearsal_status == RehearsalStatus.REHEARSAL_FAILED:
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.BLOCKED,
                is_authorized=False,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="BLOCKED: Required ShadowLab rehearsal failed",
            )

        # 2. Human Authority Triggers:
        # - Reversibility class is HUMAN_INTERVENTION_REQUIRED
        # - High blast radius (> 0.8)
        # - Elevated privilege (DDL_ADMIN, IAM_ADMIN, DATA_EXPORT)
        # - RESTRICTED sensitivity with modifying privilege and moderate+ blast radius (> 0.3)
        is_restricted_high_risk = (
            inputs.data_classification == DataClassLevel.RESTRICTED
            and inputs.privilege_level
            in (
                PrivilegeLevel.SCHEMA_MODIFY,
                PrivilegeLevel.DDL_ADMIN,
                PrivilegeLevel.DATA_EXPORT,
            )
            and inputs.blast_radius_score > 0.3
        )
        is_human_required = (
            inputs.reversibility_class == ReversibilityClass.HUMAN_INTERVENTION_REQUIRED
            or inputs.blast_radius_score > 0.8
            or inputs.privilege_level
            in (PrivilegeLevel.DDL_ADMIN, PrivilegeLevel.IAM_ADMIN, PrivilegeLevel.DATA_EXPORT)
            or is_restricted_high_risk
        )

        expected_scope = f"Target: Production. Change: {inputs.change_id}"

        if is_human_required:
            if approval_token is None:
                # Generate compressed decision card from verified locked facts (zero fake digests)
                blast_stmt = (
                    f"Blast radius estimated at {inputs.blast_radius_score:.2f} "
                    f"({inputs.blast_radius_reason})"
                )
                completed_facts: tuple[LockedFact, ...] = ()
                if inputs.evidence_digests:
                    completed_facts = (
                        LockedFact(
                            fact_id=f"fact-blast-{inputs.change_id}",
                            source_agent="impact_scout",
                            category="BLAST_RADIUS",
                            statement=blast_stmt,
                            evidence_digest=inputs.evidence_digests[0],
                            is_verified=True,
                        ),
                    )

                rehearsed_facts: tuple[LockedFact, ...] = ()
                if (
                    inputs.rehearsal_status == RehearsalStatus.REHEARSAL_PASSED
                    and inputs.rehearsal_digests
                ):
                    rehearsed_facts = (
                        LockedFact(
                            fact_id=f"fact-rehearse-{inputs.change_id}",
                            source_agent="shadowlab",
                            category="REHEARSAL",
                            statement=f"Rehearsal status: {inputs.rehearsal_status.value}",
                            evidence_digest=inputs.rehearsal_digests[0],
                            is_verified=True,
                        ),
                    )

                bundle = LockedFactBundle(
                    change_request_id=inputs.change_id,
                    completed_facts=completed_facts,
                    rehearsed_facts=rehearsed_facts,
                    reversibility_assessment=assessment,
                    authority_slot_ref="slot:lead_dba",
                    decision_question=f"Authorize live execution of change {inputs.change_id}?",
                    decision_options=("APPROVE_EXECUTION", "REJECT_AND_REQUEST_REVISION"),
                    action_scope=expected_scope,
                    risk_summary=(
                        f"High blast radius ({inputs.blast_radius_score:.2f}), "
                        f"elevated privilege ({inputs.privilege_level.value}), "
                        f"or sensitivity ({inputs.data_classification.value})"
                    ),
                    consequence_summary="Live execution will mutate production database state.",
                    expires_at=now + timedelta(minutes=30),
                    evidence_refs=inputs.rehearsal_digests + inputs.evidence_digests,
                )
                card = ApprovalCompressionEngine.generate_card(bundle, now=now)
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
                    expected_scope=expected_scope,
                    now=now,
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

        # 3. Rehearsal Requirement Triggers:
        # - Multi-Phase / Compensation
        # - Novel unverified intent
        # - Explicit rehearsal requested
        # - Restricted/Confidential sensitivity with modifying privilege
        is_rehearsal_required = (
            inputs.reversibility_class == ReversibilityClass.REVERSIBLE_WITH_COMPENSATION
            or inputs.novelty_tier == NoveltyTier.NOVEL_UNVERIFIED
            or inputs.rehearsal_status != RehearsalStatus.NOT_REQUIRED
            or (
                inputs.data_classification
                in (DataClassLevel.RESTRICTED, DataClassLevel.CONFIDENTIAL)
                and inputs.privilege_level == PrivilegeLevel.SCHEMA_MODIFY
            )
        )

        if is_rehearsal_required:
            if inputs.rehearsal_status == RehearsalStatus.REHEARSAL_PASSED:
                if inputs.rehearsal_digests and len(inputs.rehearsal_digests) > 0:
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
                            "UNAUTHORIZED: Rehearsal passed claim lacks required rehearsal digest"
                        ),
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

        # 4. Fully Reversible Automated -> AUTO_EXECUTE
        if (
            inputs.reversibility_class == ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED
            and inputs.blast_radius_score <= 0.3
            and inputs.has_down_migration
            and inputs.novelty_tier == NoveltyTier.ROUTINE_KNOWN
            and inputs.data_classification in (DataClassLevel.PUBLIC, DataClassLevel.INTERNAL)
            and inputs.privilege_level
            not in (
                PrivilegeLevel.DDL_ADMIN,
                PrivilegeLevel.IAM_ADMIN,
                PrivilegeLevel.DATA_EXPORT,
            )
        ):
            return PolicyGateEvaluationResult(
                change_id=inputs.change_id,
                autonomy_class=AutonomyClass.AUTO_EXECUTE,
                is_authorized=True,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="AUTO_EXECUTE: Fully reversible with automated rollback",
            )

        # 6. Moderate Routine / Extension -> AUTO_EXECUTE_AND_NOTIFY
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
        data_classification: DataClassLevel = DataClassLevel.INTERNAL,
        privilege_level: PrivilegeLevel = PrivilegeLevel.SCHEMA_MODIFY,
        novelty_tier: NoveltyTier = NoveltyTier.ROUTINE_KNOWN,
        evidence_state: EvidenceState = EvidenceState.PASS,
        evidence_digests: Tuple[str, ...] = (),
        rehearsal_status: RehearsalStatus = RehearsalStatus.NOT_REQUIRED,
        rehearsal_digests: Tuple[str, ...] = (),
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
            privilege_level=privilege_level,
            data_classification=data_classification,
            novelty_tier=novelty_tier,
            evidence_state=evidence_state,
            evidence_digests=evidence_digests,
            rehearsal_status=rehearsal_status,
            rehearsal_digests=rehearsal_digests,
        )
        return self.evaluate_inputs(
            inputs=inputs,
            plan_hash=plan_hash,
            approval_token=approval_token,
            assessment=assessment,
        )
