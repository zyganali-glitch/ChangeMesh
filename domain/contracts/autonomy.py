"""ChangeMesh domain contracts — autonomy and approval compression.

P-05.04: AutonomyClass, AutonomyDecision, and ApprovalCompressionCard.

AutonomyDecision represents the machine-evaluable organizational-policy
classification of a bounded action.  It is owned by ORGANIZATIONAL_POLICY,
not Gemini and not the executor.

ApprovalCompressionCard is the smallest human-on-the-loop decision packet
for a genuine human authority slot.  Creating the card NEVER means APPROVED.
Silence NEVER means approval.

Critical semantic separations:
- AutonomyDecision != Human Decision
- ApprovalCompressionCard != Approval
- LIVE_WRITE != HUMAN_AUTHORITY_REQUIRED (policy determines)
- Gemini uncertainty != human authority
- BLOCKED != review requested
"""

from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.conventions import UtcDateTime


class AutonomyClass(str, Enum):
    """Frozen canonical autonomy classification vocabulary.

    These are the only valid autonomy classes.  Do not add synonyms
    such as AUTO, MANUAL_REVIEW, NEEDS_APPROVAL, DENIED, or UNSURE.
    Gemini uncertainty is not an autonomy class.
    """

    AUTO_EXECUTE = "AUTO_EXECUTE"
    AUTO_EXECUTE_AND_NOTIFY = "AUTO_EXECUTE_AND_NOTIFY"
    REHEARSE_THEN_EXECUTE = "REHEARSE_THEN_EXECUTE"
    HUMAN_AUTHORITY_REQUIRED = "HUMAN_AUTHORITY_REQUIRED"
    BLOCKED = "BLOCKED"


class AutonomyDecision(BaseModel):
    """Machine-evaluable organizational-policy classification of a bounded action.

    Owned semantically by ORGANIZATIONAL_POLICY — not Gemini, not the
    executor.  ``HUMAN_AUTHORITY_REQUIRED`` means a human authority slot
    is required; it does NOT mean approval has been granted.

    No model confidence/uncertainty fields are included.  Gemini semantic
    judgment may later be consumed as advisory input, but it is not the
    authority source for autonomy classification.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        decision_id: Stable decision identity.
        change_request_id: Associated change/request reference.
        action_class: Bounded action class being classified.
        autonomy_class: Organizational policy classification.
        policy_source: Organizational policy source/reference.
        policy_revision: Policy revision/reference (optional).
        decided_at: Decision timestamp.
        rationale: Bounded rationale/reason for the classification.
        authority_slot_ref: Human-authority slot reference.  Required
            for HUMAN_AUTHORITY_REQUIRED, forbidden for AUTO_EXECUTE
            and AUTO_EXECUTE_AND_NOTIFY.
        required_rehearsal_refs: Required rehearsal/scenario boundary
            references.  Required for REHEARSE_THEN_EXECUTE.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    decision_id: str
    change_request_id: str
    action_class: str
    autonomy_class: AutonomyClass
    policy_source: str
    policy_revision: Optional[str] = None
    decided_at: UtcDateTime
    rationale: str
    authority_slot_ref: Optional[str] = None
    required_rehearsal_refs: Tuple[str, ...] = ()

    @field_validator(
        "schema_version", "decision_id", "change_request_id",
        "action_class", "policy_source", "rationale",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("required_rehearsal_refs")
    @classmethod
    def _validate_ref_tuples(cls, v: Tuple[str, ...], info) -> Tuple[str, ...]:
        for ref in v:
            if not ref or not ref.strip():
                raise ValueError(f"{info.field_name} elements must not be blank")
        if len(set(v)) != len(v):
            raise ValueError(f"{info.field_name} must not contain duplicate references")
        return v

    @field_validator("policy_revision", "authority_slot_ref")
    @classmethod
    def _optional_not_blank_if_set(
        cls, v: Optional[str], info,
    ) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError(
                f"{info.field_name} must not be blank when set"
            )
        return v

    @model_validator(mode="after")
    def _validate_autonomy_invariants(self):
        ac = self.autonomy_class

        # HUMAN_AUTHORITY_REQUIRED must identify authority slot
        if ac == AutonomyClass.HUMAN_AUTHORITY_REQUIRED:
            if not self.authority_slot_ref:
                raise ValueError(
                    "HUMAN_AUTHORITY_REQUIRED must have a non-blank "
                    "authority_slot_ref"
                )
        else:
            # NO other class is allowed to have an authority_slot_ref
            if self.authority_slot_ref is not None:
                raise ValueError(
                    f"{ac.value} must not have authority_slot_ref"
                )

        # REHEARSE_THEN_EXECUTE must identify rehearsal boundary
        if ac == AutonomyClass.REHEARSE_THEN_EXECUTE:
            if not self.required_rehearsal_refs:
                raise ValueError(
                    "REHEARSE_THEN_EXECUTE must have at least one "
                    "required_rehearsal_ref"
                )

        return self


class ApprovalCompressionCard(BaseModel):
    """Smallest human-on-the-loop decision packet for a genuine
    human authority slot.

    The card summarizes what the system already did, what was
    rehearsed/simulated, and what exact irreducible decision remains.

    This contract does NOT contain human response/approval fields.
    Creating the card is NOT approval.  Silence is NOT approval.
    ``extra="forbid"`` rejects any accidental ``approved`` or
    ``human_response`` fields.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        card_id: Stable card identity.
        change_request_id: Associated change/request identity.
        autonomy_decision: Typed immutable AutonomyDecision snapshot
            (must be HUMAN_AUTHORITY_REQUIRED).
        authority_slot_ref: Human-authority slot/reference.
        decision_question: Exact bounded decision question.
        decision_options: Bounded decision options (at least 2,
            no duplicates).
        policy_reason: Why this requires human authority.
        action_scope: Bounded action/scope description.
        completed_work_summary: Summary of completed autonomous work.
        rehearsed_work_summary: Summary of rehearsed/simulated work.
        remaining_decision_summary: Summary of the remaining
            irreducible decision.
        evidence_refs: Relevant evidence/reference IDs.
        created_at: Creation timestamp.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    card_id: str
    change_request_id: str
    autonomy_decision: AutonomyDecision
    authority_slot_ref: str
    decision_question: str
    decision_options: Tuple[str, ...]
    policy_reason: str
    action_scope: str
    completed_work_summary: str
    rehearsed_work_summary: str
    remaining_decision_summary: str
    evidence_refs: Tuple[str, ...] = ()
    created_at: UtcDateTime

    @field_validator(
        "schema_version", "card_id", "change_request_id",
        "authority_slot_ref", "decision_question", "policy_reason",
        "action_scope", "completed_work_summary", "rehearsed_work_summary",
        "remaining_decision_summary",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("decision_options")
    @classmethod
    def _validate_decision_options(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        normalized = []
        for opt in v:
            if not opt or not opt.strip():
                raise ValueError("decision_options elements must not be blank")
            normalized.append(opt.strip())
        
        if len(normalized) < 2:
            raise ValueError("decision_options must have at least 2 options")
        
        if len(set(normalized)) != len(normalized):
            raise ValueError("decision_options must not contain duplicates")
        
        return tuple(normalized)

    @field_validator("evidence_refs")
    @classmethod
    def _validate_evidence_refs(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        for ref in v:
            if not ref or not ref.strip():
                raise ValueError("evidence_refs elements must not be blank")
        if len(set(v)) != len(v):
            raise ValueError("evidence_refs must not contain duplicate references")
        return v

    @model_validator(mode="after")
    def _validate_card_invariants(self):
        # Card is ONLY for HUMAN_AUTHORITY_REQUIRED
        if (
            self.autonomy_decision.autonomy_class
            != AutonomyClass.HUMAN_AUTHORITY_REQUIRED
        ):
            raise ValueError(
                "ApprovalCompressionCard requires autonomy_class == "
                "HUMAN_AUTHORITY_REQUIRED, got "
                f"{self.autonomy_decision.autonomy_class.value}"
            )

        # Consistency: card change_request_id must match decision
        if (
            self.change_request_id
            != self.autonomy_decision.change_request_id
        ):
            raise ValueError(
                "card change_request_id must match "
                "autonomy_decision.change_request_id"
            )

        # Consistency: authority slot must match decision
        if (
            self.authority_slot_ref
            != self.autonomy_decision.authority_slot_ref
        ):
            raise ValueError(
                "card authority_slot_ref must match "
                "autonomy_decision.authority_slot_ref"
            )

        # Decision options validation is now handled by field_validator

        return self
