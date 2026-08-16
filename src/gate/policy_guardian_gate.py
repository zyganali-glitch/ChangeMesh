"""ChangeMesh Policy Guardian Reversibility Gate and Decision Engine.

P-14.04 - P-14.06: Evaluates change reversibility against organizational policy,
enforces autonomous-by-default execution, issues compressed decision packets
for genuine human authority slots, and validates signed approval tokens.
"""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict

from domain.contracts.autonomy import ApprovalCompressionCard, AutonomyClass
from src.gate.compression import ApprovalCompressionEngine
from src.gate.reversibility import (
    ReversibilityAssessment,
    ReversibilityClass,
    ReversibilityClassifier,
)
from src.gate.token import (
    ApprovalTokenManager,
    SignedApprovalToken,
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

    def __init__(self, token_manager: Optional[ApprovalTokenManager] = None) -> None:
        self._token_manager = token_manager or ApprovalTokenManager()

    def evaluate_change(
        self,
        change_id: str,
        sql_up: str,
        sql_down: Optional[str] = None,
        blast_radius: float = 0.1,
        plan_hash: str = "plan-hash-1",
        approval_token: Optional[SignedApprovalToken] = None,
        signing_secret: str = "demo-signing-secret-key-32chars!!",
    ) -> PolicyGateEvaluationResult:
        """Evaluate a change through the reversibility gate."""
        assessment = ReversibilityClassifier.classify_sql(
            change_id=change_id,
            sql_up=sql_up,
            sql_down=sql_down,
            blast_radius_score=blast_radius,
        )

        trace_id = f"trace-gate-{uuid.uuid4().hex[:8]}"

        # 1. Irreversible Destructive -> Blocked immediately
        if assessment.reversibility_class == ReversibilityClass.IRREVERSIBLE_DESTRUCTIVE:
            return PolicyGateEvaluationResult(
                change_id=change_id,
                autonomy_class=AutonomyClass.BLOCKED,
                is_authorized=False,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="BLOCKED: Irreversible destructive operation lacks down-migration rollback script",
            )

        # 2. Fully Reversible Automated -> Autonomous execution authorized
        if assessment.reversibility_class == ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED:
            return PolicyGateEvaluationResult(
                change_id=change_id,
                autonomy_class=AutonomyClass.AUTO_EXECUTE,
                is_authorized=True,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="AUTO_EXECUTE: Change is fully reversible with verified automated rollback",
            )

        # 3. Reversible with Compensation -> Rehearse then execute
        if assessment.reversibility_class == ReversibilityClass.REVERSIBLE_WITH_COMPENSATION:
            return PolicyGateEvaluationResult(
                change_id=change_id,
                autonomy_class=AutonomyClass.REHEARSE_THEN_EXECUTE,
                is_authorized=True,
                reversibility_assessment=assessment,
                audit_trace_id=trace_id,
                decision_summary="REHEARSE_THEN_EXECUTE: Multi-phase change requires saga compensation rehearsal",
            )

        # 4. Human Intervention Required -> Check approval token
        if assessment.reversibility_class == ReversibilityClass.HUMAN_INTERVENTION_REQUIRED:
            if approval_token is None:
                # Generate compressed decision packet
                card = ApprovalCompressionEngine.generate_card(
                    change_request_id=change_id,
                    assessment=assessment,
                    authority_slot_ref="slot:lead_dba",
                )
                return PolicyGateEvaluationResult(
                    change_id=change_id,
                    autonomy_class=AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
                    is_authorized=False,
                    reversibility_assessment=assessment,
                    compression_card=card,
                    audit_trace_id=trace_id,
                    decision_summary="HUMAN_AUTHORITY_REQUIRED: High blast radius or destructive step requires signed human token",
                )
            else:
                # Verify cryptographic token
                val = self._token_manager.verify_and_consume(
                    token=approval_token,
                    expected_plan_hash=plan_hash,
                    secret_key=signing_secret,
                )
                if val.is_valid:
                    return PolicyGateEvaluationResult(
                        change_id=change_id,
                        autonomy_class=AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
                        is_authorized=True,
                        reversibility_assessment=assessment,
                        audit_trace_id=trace_id,
                        decision_summary=f"AUTHORIZED: Valid cryptographic approval token signed by {approval_token.approver_id}",
                    )
                else:
                    return PolicyGateEvaluationResult(
                        change_id=change_id,
                        autonomy_class=AutonomyClass.BLOCKED,
                        is_authorized=False,
                        reversibility_assessment=assessment,
                        audit_trace_id=trace_id,
                        decision_summary=f"DENIED: Invalid approval token ({val.status}: {val.failure_reason})",
                    )

        # Fallback default (fail-closed)
        return PolicyGateEvaluationResult(
            change_id=change_id,
            autonomy_class=AutonomyClass.BLOCKED,
            is_authorized=False,
            reversibility_assessment=assessment,
            audit_trace_id=trace_id,
            decision_summary="BLOCKED: Unrecognized change profile",
        )
