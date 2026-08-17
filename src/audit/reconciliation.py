from enum import Enum

from pydantic import BaseModel, ConfigDict

from src.audit.semantic_auditor import ClaimAuditResult, SemanticVerdict


class ReconciliationOutcome(str, Enum):
    AGREEMENT = "AGREEMENT"
    ADVISORY_REVIEW = "ADVISORY_REVIEW"
    ESCALATION = "ESCALATION"


class ReconciliationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    claim_id: str
    semantic_verdict: SemanticVerdict
    deterministic_state: str
    outcome: ReconciliationOutcome
    disagreement_detected: bool
    deterministic_state_preserved: bool = True
    authority_of_deterministic: str = "DETERMINISTIC_CODE"
    authority_of_semantic: str = "GEMINI_SEMANTIC_JUDGMENT"


class DeterministicReconciler:
    """Reconcile semantic opinion without changing deterministic states."""

    def reconcile(
        self, audit_result: ClaimAuditResult, deterministic_state: str, change_id: str
    ) -> ReconciliationResult:

        disagreement = False
        outcome = ReconciliationOutcome.AGREEMENT

        if deterministic_state == "PASS" and audit_result.verdict != SemanticVerdict.SUPPORTS:
            disagreement = True
            outcome = ReconciliationOutcome.ADVISORY_REVIEW
        elif deterministic_state == "FAIL" and audit_result.verdict != SemanticVerdict.CONTRADICTS:
            disagreement = True
            outcome = ReconciliationOutcome.ADVISORY_REVIEW

        return ReconciliationResult(
            change_id=change_id,
            claim_id=audit_result.claim_id,
            semantic_verdict=audit_result.verdict,
            deterministic_state=deterministic_state,
            outcome=outcome,
            disagreement_detected=disagreement,
        )
