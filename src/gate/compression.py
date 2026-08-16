"""ChangeMesh approval compression card generator.

P-14.04: Compresses verified analysis and rehearsal findings into a locked-fact
1-screen decision card for irreducible human authority slots.
All facts are strictly sourced from deterministic owners; zero fabricated reassurance.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.autonomy import (
    ApprovalCompressionCard,
    AutonomyClass,
    AutonomyDecision,
)
from domain.contracts.conventions import UtcDateTime, is_valid_sha256_digest
from src.gate.reversibility import ReversibilityAssessment

CANONICAL_SCHEMA_VERSION = "1.0.0"


class LockedFact(BaseModel):
    """An immutable, verified statement produced by a deterministic analysis or rehearsal tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str
    source_agent: str
    category: str
    statement: str
    evidence_digest: str
    is_verified: bool = True

    @field_validator("fact_id", "source_agent", "category", "statement")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("evidence_digest")
    @classmethod
    def _validate_digest(cls, v: str) -> str:
        if not is_valid_sha256_digest(v):
            raise ValueError(
                f"evidence_digest must be a valid 64-char SHA-256 hex string, got {v!r}"
            )
        return v


class LockedFactBundle(BaseModel):
    """Complete bundle of locked facts consumed to generate an ApprovalCompressionCard."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    change_request_id: str
    completed_facts: Tuple[LockedFact, ...] = ()
    rehearsed_facts: Tuple[LockedFact, ...] = ()
    reversibility_assessment: ReversibilityAssessment
    authority_slot_ref: str = "slot:lead_dba"
    decision_question: str
    decision_options: Tuple[str, ...] = ("APPROVE_EXECUTION", "REJECT_AND_REQUEST_REVISION")
    action_scope: str
    risk_summary: str
    consequence_summary: str
    expires_at: UtcDateTime
    evidence_refs: Tuple[str, ...] = ()

    @field_validator("change_request_id", "authority_slot_ref", "decision_question", "action_scope")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("decision_options")
    @classmethod
    def _validate_options(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        if len(v) < 2:
            raise ValueError("decision_options must contain at least 2 options")
        if len(set(v)) != len(v):
            raise ValueError("decision_options must not contain duplicates")
        return v


class ApprovalCompressionEngine:
    """Generates tight, proof-carrying ApprovalCompressionCards strictly from locked facts."""

    @classmethod
    def generate_card(
        cls,
        bundle: LockedFactBundle,
        now: Optional[datetime] = None,
    ) -> ApprovalCompressionCard:
        """Create an ApprovalCompressionCard strictly rendering verified facts from the bundle."""
        if now is None:
            now = datetime.now(timezone.utc)

        card_id = f"card-{bundle.change_request_id}-{uuid.uuid4().hex[:6]}"
        decision_id = f"autonomy-dec-{bundle.change_request_id}-{uuid.uuid4().hex[:6]}"

        autonomy_decision = AutonomyDecision(
            schema_version="1.0.0",
            decision_id=decision_id,
            change_request_id=bundle.change_request_id,
            action_class="PRODUCTION_SCHEMA_MIGRATION",
            autonomy_class=AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
            policy_source="policy:org_change_reversibility_v1",
            decided_at=now,
            rationale=bundle.reversibility_assessment.rationale,
            authority_slot_ref=bundle.authority_slot_ref,
        )

        # Render completed facts strictly from bundle
        if bundle.completed_facts:
            completed_lines = [
                f"{i + 1}. [{f.source_agent}] {f.statement}"
                for i, f in enumerate(bundle.completed_facts)
            ]
            completed_work = "\n".join(completed_lines)
        else:
            completed_work = "Completed analysis facts: NOT_RUN / NO_FACTS"

        # Render rehearsed facts strictly from bundle
        if bundle.rehearsed_facts:
            rehearsed_lines = [
                f"{i + 1}. [{f.source_agent}] {f.statement}"
                for i, f in enumerate(bundle.rehearsed_facts)
            ]
            rehearsed_work = "\n".join(rehearsed_lines)
        else:
            rehearsed_work = "Rehearsal facts: NOT_RUN / NO_FACTS"

        # Include risk, consequence, and expiry in remaining decision
        assessment = bundle.reversibility_assessment
        remaining_decision = (
            f"Decision Required: {bundle.decision_question}\n"
            f"Scope: {bundle.action_scope}\n"
            f"Blast Radius: {assessment.blast_radius_score:.2f}\n"
            f"Reversibility: {assessment.reversibility_class.value}\n"
            f"Risk: {bundle.risk_summary}\n"
            f"Consequence: {bundle.consequence_summary}\n"
            f"Expires At: {bundle.expires_at.isoformat()}"
        )

        return ApprovalCompressionCard(
            schema_version="1.0.0",
            card_id=card_id,
            change_request_id=bundle.change_request_id,
            autonomy_decision=autonomy_decision,
            authority_slot_ref=bundle.authority_slot_ref,
            decision_question=bundle.decision_question,
            decision_options=bundle.decision_options,
            policy_reason=assessment.rationale,
            action_scope=bundle.action_scope,
            completed_work_summary=completed_work,
            rehearsed_work_summary=rehearsed_work,
            remaining_decision_summary=remaining_decision,
            evidence_refs=bundle.evidence_refs,
            created_at=now,
        )
