"""ChangeMesh Evidence Auditor — Google ADK Agent Definition.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the canonical Evidence Auditor ADK agent.

Responsibilities:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Semantic sufficiency reviews of collected execution evidence against success criteria.
- Deterministic evidence records and execution facts are strictly READ-ONLY.
- May never rewrite PASS/FAIL, hashes, execution occurrence, test counts, or timestamps.
- Zero credentials required and zero external writes. The explicit blind-audit
  method uses the canonical bounded Gemini client; the ADK definition path itself
  remains side-effect free.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, AsyncGenerator, ClassVar, Type

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from pydantic import BaseModel, ConfigDict, StrictStr, model_validator

from domain.contracts.agent_descriptor import AgentDescriptor
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode
from src.agents.definition import (
    EVIDENCE_AUDITOR_INSTRUCTION,
    AgentDefinition,
)
from src.agents.schemas import EvidenceAuditorInput, EvidenceAuditorOutput

MAX_BLIND_CLAIMS = 64
MAX_BLIND_EVIDENCE = 128
MAX_BLIND_TEXT_CHARS = 4000
MAX_BLIND_PROMPT_CHARS = 32000
_EXPECTED_FIELD_PATTERN = re.compile(
    r"\b(?:expected_result|expected_answer|expected_verdict|should_pass|"
    r"deterministic_status|deterministic_basis|human_review_required)\b",
    re.IGNORECASE,
)
_EXPECTED_FIELD_KEYS = frozenset(
    {"expected_result", "expected_answer", "expected_verdict", "should_pass"}
)


class BlindAuditError(ValueError):
    """Base error for deterministic blind-audit bundle and reconciliation checks."""


class BlindAuditInputError(BlindAuditError):
    """Raised when input would leak expected answers or violate the bundle contract."""


class BlindAuditReconciliationError(BlindAuditError):
    """Raised when model output cannot be reconciled with locked deterministic claims."""


class BlindAuditClaim(BaseModel):
    """Only model-visible claim fields; deterministic fields are intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: StrictStr
    claim_description: StrictStr
    target_criterion: StrictStr


class BlindAuditEvidence(BaseModel):
    """Bounded model-visible evidence summary without expected-answer metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_key: StrictStr
    summary: StrictStr
    source: StrictStr


class BlindAuditModelContext(BaseModel):
    """The exact context permitted to cross into the semantic audit prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictStr
    audit_id: StrictStr
    change_id: StrictStr
    claims: tuple[BlindAuditClaim, ...]
    evidence_summaries: tuple[BlindAuditEvidence, ...]
    collection_mode: ExecutionEvidenceMode
    declared_mode: ExecutionEvidenceMode

    @model_validator(mode="after")
    def _validate_context(self) -> "BlindAuditModelContext":
        if self.schema_version != "1.0.0":
            raise BlindAuditInputError("Unsupported blind-audit schema version.")
        if self.collection_mode != self.declared_mode:
            raise BlindAuditInputError("PROVENANCE_MODE_MISMATCH")
        if not self.claims or not self.evidence_summaries:
            raise BlindAuditInputError("Blind-audit context cannot be empty.")
        return self


class LockedAuditClaim(BaseModel):
    """Application-only deterministic claim state never serialized into the prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: StrictStr
    deterministic_status: EvidenceState
    deterministic_basis: StrictStr
    evidence_keys: tuple[StrictStr, ...]


@dataclass(frozen=True)
class BlindAuditPackage:
    """Separated model context and locked local facts."""

    model_context: BlindAuditModelContext
    locked_claims: tuple[LockedAuditClaim, ...]

    def build_prompt(self) -> str:
        """Build the model prompt from model-visible context only."""
        from src.core.gemini_structured_output import build_semantic_audit_prompt

        prompt = build_semantic_audit_prompt(
            audit_id=self.model_context.audit_id,
            change_id=self.model_context.change_id,
            claims=[claim.model_dump() for claim in self.model_context.claims],
            evidence_summaries=[
                evidence.model_dump() for evidence in self.model_context.evidence_summaries
            ],
            collection_mode=self.model_context.collection_mode.value,
            declared_mode=self.model_context.declared_mode.value,
        )
        if len(prompt) > MAX_BLIND_PROMPT_CHARS:
            raise BlindAuditInputError("BLIND_PROMPT_EXCEEDS_BOUND")
        return prompt


@dataclass(frozen=True)
class ClaimAuditReconciliation:
    """Advisory model assessment joined to, but unable to change, local state."""

    claim_id: str
    deterministic_status: EvidenceState
    model_assessment: str
    relation: str
    human_review_required: bool


@dataclass(frozen=True)
class SemanticAuditReconciliation:
    """Final P-08.04 result preserving deterministic state sovereignty."""

    audit_id: str
    change_id: str
    model_overall_verdict: str
    claim_audits: tuple[ClaimAuditReconciliation, ...]
    review_state: str
    human_review_required: bool


def _require_exact_keys(value: Mapping[str, Any], allowed: set[str]) -> None:
    if any(str(key) in _EXPECTED_FIELD_KEYS for key in value):
        raise BlindAuditInputError("EXPECTED_FIELD_LEAKAGE")
    if set(value) != allowed:
        raise BlindAuditInputError("BLIND_CONTEXT_ALLOWLIST_MISMATCH")


def _bounded_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BlindAuditInputError(f"{field_name} must be non-blank.")
    cleaned = value.strip()
    if len(cleaned) > MAX_BLIND_TEXT_CHARS:
        raise BlindAuditInputError(f"{field_name} exceeds bounded blind-audit size.")
    if _EXPECTED_FIELD_PATTERN.search(cleaned):
        raise BlindAuditInputError("EXPECTED_FIELD_LEAKAGE")
    return cleaned


def build_blind_audit_package(
    *,
    audit_id: str,
    change_id: str,
    deterministic_claims: Sequence[Mapping[str, Any]],
    evidence_summaries: Sequence[Mapping[str, Any]],
    collection_mode: ExecutionEvidenceMode | str,
    declared_mode: ExecutionEvidenceMode | str,
) -> BlindAuditPackage:
    """Separate locked facts from the exact context visible to Gemini."""
    if len(deterministic_claims) == 0 or len(deterministic_claims) > MAX_BLIND_CLAIMS:
        raise BlindAuditInputError("Invalid blind-audit claim count.")
    if len(evidence_summaries) == 0 or len(evidence_summaries) > MAX_BLIND_EVIDENCE:
        raise BlindAuditInputError("Invalid blind-audit evidence count.")

    model_claims: list[BlindAuditClaim] = []
    locked_claims: list[LockedAuditClaim] = []
    for raw_claim in deterministic_claims:
        if not isinstance(raw_claim, Mapping):
            raise BlindAuditInputError("Each deterministic claim must be a mapping.")
        _require_exact_keys(
            raw_claim,
            {
                "claim_id",
                "claim_description",
                "target_criterion",
                "deterministic_status",
                "deterministic_basis",
                "evidence_keys",
            },
        )
        claim_id = _bounded_text(raw_claim["claim_id"], "claim_id")
        try:
            deterministic_status = EvidenceState(raw_claim["deterministic_status"])
        except (TypeError, ValueError) as exc:
            raise BlindAuditInputError("INVALID_DETERMINISTIC_STATE") from exc
        evidence_keys = raw_claim["evidence_keys"]
        if not isinstance(evidence_keys, Sequence) or isinstance(evidence_keys, (str, bytes)):
            raise BlindAuditInputError("INVALID_EVIDENCE_KEYS")
        cleaned_evidence_keys = tuple(_bounded_text(key, "evidence_key") for key in evidence_keys)
        model_claims.append(
            BlindAuditClaim(
                claim_id=claim_id,
                claim_description=_bounded_text(
                    raw_claim["claim_description"], "claim_description"
                ),
                target_criterion=_bounded_text(raw_claim["target_criterion"], "target_criterion"),
            )
        )
        locked_claims.append(
            LockedAuditClaim(
                claim_id=claim_id,
                deterministic_status=deterministic_status,
                deterministic_basis=_bounded_text(
                    raw_claim["deterministic_basis"], "deterministic_basis"
                ),
                evidence_keys=cleaned_evidence_keys,
            )
        )

    model_evidence: list[BlindAuditEvidence] = []
    for raw_evidence in evidence_summaries:
        if not isinstance(raw_evidence, Mapping):
            raise BlindAuditInputError("Each evidence summary must be a mapping.")
        _require_exact_keys(raw_evidence, {"evidence_key", "summary", "source"})
        model_evidence.append(
            BlindAuditEvidence(
                evidence_key=_bounded_text(raw_evidence["evidence_key"], "evidence_key"),
                summary=_bounded_text(raw_evidence["summary"], "summary"),
                source=_bounded_text(raw_evidence["source"], "source"),
            )
        )

    try:
        collection_mode_value = ExecutionEvidenceMode(collection_mode)
        declared_mode_value = ExecutionEvidenceMode(declared_mode)
    except (TypeError, ValueError) as exc:
        raise BlindAuditInputError("UNKNOWN_EXECUTION_MODE") from exc

    model_context = BlindAuditModelContext(
        schema_version="1.0.0",
        audit_id=_bounded_text(audit_id, "audit_id"),
        change_id=_bounded_text(change_id, "change_id"),
        claims=tuple(model_claims),
        evidence_summaries=tuple(model_evidence),
        collection_mode=collection_mode_value,
        declared_mode=declared_mode_value,
    )
    if len({claim.claim_id for claim in locked_claims}) != len(locked_claims):
        raise BlindAuditInputError("DUPLICATE_CLAIM_ID")
    return BlindAuditPackage(model_context=model_context, locked_claims=tuple(locked_claims))


def reconcile_semantic_audit(
    package: BlindAuditPackage,
    model_result: Any,
) -> SemanticAuditReconciliation:
    """Reconcile advisory output without promoting or rewriting local evidence."""
    if (
        model_result.audit_id != package.model_context.audit_id
        or model_result.change_id != package.model_context.change_id
    ):
        raise BlindAuditReconciliationError("MODEL_AUDIT_IDENTITY_MISMATCH")
    expected_ids = {claim.claim_id for claim in package.locked_claims}
    assessments = getattr(model_result, "claim_assessments", None)
    if (
        not isinstance(assessments, list)
        or len(assessments) != len(expected_ids)
        or {item.claim_id for item in assessments} != expected_ids
    ):
        raise BlindAuditReconciliationError("MODEL_CLAIM_SET_MISMATCH")

    allowed_evidence = {item.evidence_key for item in package.model_context.evidence_summaries}
    locked_by_id = {claim.claim_id: claim for claim in package.locked_claims}
    for item in assessments:
        locked = locked_by_id.get(item.claim_id)
        if locked is None:
            raise BlindAuditReconciliationError("MODEL_CLAIM_SET_MISMATCH")
        if any(key not in allowed_evidence for key in item.cited_evidence_keys):
            raise BlindAuditReconciliationError("MODEL_CITATION_OUTSIDE_BUNDLE")
        if any(key not in locked.evidence_keys for key in item.cited_evidence_keys):
            raise BlindAuditReconciliationError("MODEL_CITATION_OUTSIDE_CLAIM")
    for citation in getattr(model_result, "evidence_citations", ()):
        if citation.evidence_key not in allowed_evidence:
            raise BlindAuditReconciliationError("MODEL_CITATION_OUTSIDE_BUNDLE")
        for claim_id in citation.supports_claim_ids:
            if claim_id not in expected_ids:
                raise BlindAuditReconciliationError("MODEL_CITATION_CLAIM_UNKNOWN")
            if citation.evidence_key not in locked_by_id[claim_id].evidence_keys:
                raise BlindAuditReconciliationError("MODEL_CITATION_OUTSIDE_CLAIM")

    reconciled: list[ClaimAuditReconciliation] = []
    for item in assessments:
        locked = locked_by_id[item.claim_id]
        model_assessment = item.assessment.value
        if locked.deterministic_status == EvidenceState.PASS and model_assessment == "SUPPORTS":
            relation = "AGREEMENT"
            review_required = False
        elif locked.deterministic_status != EvidenceState.PASS and model_assessment != "SUPPORTS":
            relation = "COMPATIBLE_WITH_LOCKED_STATE"
            review_required = False
        else:
            relation = "DISAGREEMENT_WITH_LOCKED_STATE"
            review_required = True
        reconciled.append(
            ClaimAuditReconciliation(
                claim_id=item.claim_id,
                deterministic_status=locked.deterministic_status,
                model_assessment=model_assessment,
                relation=relation,
                human_review_required=review_required,
            )
        )

    requires_review = any(item.human_review_required for item in reconciled)
    return SemanticAuditReconciliation(
        audit_id=model_result.audit_id,
        change_id=model_result.change_id,
        model_overall_verdict=model_result.overall_verdict.value,
        claim_audits=tuple(reconciled),
        review_state="HUMAN_REVIEW_REQUIRED" if requires_review else "NO_MODEL_CONFLICT",
        human_review_required=requires_review,
    )


def run_blind_semantic_audit(
    package: BlindAuditPackage, client: Any
) -> SemanticAuditReconciliation:
    """Execute one blind audit through the canonical bounded Gemini client."""
    from src.core.gemini_structured_output import parse_semantic_audit_output

    response = client.generate_text(package.build_prompt())
    model_result = parse_semantic_audit_output(response.text)
    return reconcile_semantic_audit(package, model_result)


class EvidenceAuditor(BaseAgent):
    """ChangeMesh Evidence Auditor ADK Agent.

    Performs semantic sufficiency reviews of collected execution evidence
    against success criteria. Deterministic evidence records are read-only.
    """

    # ChangeMesh Agent Definition Metadata (P-07.02)
    agent_id: ClassVar[str] = "agent-evidence-auditor"
    role: ClassVar[str] = "evidence_auditor"
    agent_revision: ClassVar[str] = "1.0.0"
    revision: ClassVar[str] = "1.0.0"
    agent_description: ClassVar[str] = (
        "Performs semantic sufficiency reviews of collected execution evidence "
        "against success criteria. Deterministic evidence records are read-only."
    )
    declared_capabilities: ClassVar[list[str]] = [
        "semantic_evidence_sufficiency_review",
        "evidence_completeness_verification",
        "claim_justification_analysis",
    ]
    capabilities: ClassVar[list[str]] = declared_capabilities
    forbidden_actions: ClassVar[list[str]] = [
        "rewrite_deterministic_facts",
        "forge_execution_evidence",
        "grant_unauthorized_pass",
        "execute_system_mutations",
    ]
    instruction_contract: ClassVar[str] = EVIDENCE_AUDITOR_INSTRUCTION
    permitted_tool_ids: ClassVar[list[str]] = [
        "tool-evidence-ledger-reader",
        "tool-artifact-hash-verifier",
        "tool-rehearsal-result-reader",
    ]
    permitted_data_classifications: ClassVar[list[DataClassLevel]] = [
        DataClassLevel.PUBLIC,
        DataClassLevel.INTERNAL,
        DataClassLevel.CONFIDENTIAL,
        DataClassLevel.RESTRICTED,
    ]

    # ADK BaseAgent fields
    name: str = "evidence_auditor"
    description: str = agent_description
    input_schema: Type[BaseModel] = EvidenceAuditorInput
    output_schema: Type[BaseModel] = EvidenceAuditorOutput

    @classmethod
    def get_definition(cls) -> AgentDefinition:
        """Return the complete runtime AgentDefinition contract for this agent."""
        return AgentDefinition(
            agent_id=cls.agent_id,
            role=cls.role,
            agent_revision=cls.agent_revision,
            description=cls.agent_description,
            declared_capabilities=cls.declared_capabilities,
            forbidden_actions=cls.forbidden_actions,
            input_schema=cls.model_fields["input_schema"].default,
            output_schema=cls.model_fields["output_schema"].default,
            instruction_contract=cls.instruction_contract,
            permitted_tool_ids=cls.permitted_tool_ids,
            permitted_data_classifications=cls.permitted_data_classifications,
        )

    @classmethod
    def get_descriptor(cls) -> AgentDescriptor:
        """Return the frozen domain contract AgentDescriptor for this agent."""
        return cls.get_definition().to_descriptor()

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """ADK core execution logic for the Evidence Auditor.

        In P-07.02 definition stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
