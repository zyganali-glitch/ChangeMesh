"""ChangeMesh Gemini Structured Output Boundary & Schema Validation.

P-08.02: Implement schema-constrained prompts/parsers for goal decomposition,
policy explanation, and semantic audit.

Derived via Clean Room Reimplementation from ZK-VALID-001 (D-ZEROKIT) and
CCT-SEM-001 (D-CCT), adapted for ChangeMesh Pydantic v2 domain schemas.

Guarantees:
- OUT-01: Untrusted until deterministic schema validation succeeds.
- OUT-02: Missing required fields fail closed without default injection.
- OUT-03: Extra fields fail closed (extra="forbid").
- OUT-04: Wrong types fail closed without silent coercion (Strict types).
- OUT-05: No silent repair or fuzzy correction of malformed JSON.
- OUT-06: Unsafe paths (path traversal) and unsafe endpoints fail deterministically.
- OUT-07: Provider-specific hidden fields/SDK internals are forbidden.
- OUT-08: Model output belongs strictly to GEMINI_SEMANTIC_JUDGMENT and cannot
          author or overwrite deterministic facts, EvidenceState, or policy.
- OUT-10: Evidence citations and counter-evidence are structurally distinct
          from generated explanation prose.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, Final, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

# --- Authority Lane & Schema Version Constants ---
CANONICAL_AUTHORITY_LANE: Final[str] = "GEMINI_SEMANTIC_JUDGMENT"
CANONICAL_STRUCTURED_SCHEMA_VERSION: Final[str] = "1.0.0"


# --- Controlled Vocabularies ---
class SemanticAssessmentVerdict(str, Enum):
    """Canonical verdict vocabulary for independent semantic review."""

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INSUFFICIENT = "INSUFFICIENT"


class SemanticRiskLevel(str, Enum):
    """Estimated risk level for decomposed goals."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyImpactLevel(str, Enum):
    """Impact level for policy rule explanations."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyComplianceStatus(str, Enum):
    """Compliance status for policy rule explanations."""

    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    EXEMPT = "EXEMPT"


# --- Canonical Action Types & Specialist Roles Allowlists ---
CANONICAL_ACTION_TYPES: Final[frozenset[str]] = frozenset(
    {
        "inspect_impact",
        "evaluate_policy",
        "generate_migration",
        "audit_evidence",
        "prepare_release",
        "verify_artifacts",
        "rehearse_migration",
        "check_dependencies",
        "scan_repository",
        "dry_run_migration",
        "validate_contracts",
    }
)

CANONICAL_SPECIALIST_ROLES: Final[frozenset[str]] = frozenset(
    {
        "Change Orchestrator",
        "Impact Scout",
        "Policy Guardian",
        "Migration Engineer",
        "Evidence Auditor",
        "Release Steward",
        "change_orchestrator",
        "impact_scout",
        "policy_guardian",
        "migration_engineer",
        "evidence_auditor",
        "release_steward",
    }
)


# --- Exceptions Hierarchy ---
class StructuredOutputError(Exception):
    """Base exception for all structured output parsing and validation errors."""


class StructuredOutputJSONError(StructuredOutputError):
    """Raised when raw model output cannot be parsed as valid, non-malformed JSON."""


class StructuredOutputValidationError(StructuredOutputError):
    """Raised when parsed JSON fails strict schema validation."""

    def __init__(
        self,
        message: str,
        *,
        errors: Optional[list[Any]] = None,
    ) -> None:
        super().__init__(message)
        self.errors = errors or []


class StructuredOutputSecurityError(StructuredOutputValidationError):
    """Raised on security violations (traversal, unsafe endpoint, unknown action)."""


# --- Deterministic Security Validators ---
def validate_safe_relative_path(path_str: str, field_name: str = "path") -> str:
    """Validate that a path string is safe, relative, and contains no traversal tokens.

    Rejects:
    - Path traversal: '..', '../', '..\\', URL-encoded '%2e%2e'
    - Absolute paths: '/etc/passwd', 'C:\\Windows', '\\server\\share'
    - Control characters, null bytes, URI schemes: 'file://', 'http://'
    """
    if not isinstance(path_str, str) or not path_str.strip():
        raise StructuredOutputSecurityError(f"{field_name} must not be empty.")

    cleaned = path_str.strip()

    if "\x00" in cleaned or any(ord(c) < 32 for c in cleaned):
        raise StructuredOutputSecurityError(
            f"{field_name} contains null byte or control characters: {path_str!r}"
        )

    # Reject URI schemes
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", cleaned):
        raise StructuredOutputSecurityError(
            f"{field_name} must be a relative repository path, not a URL: {path_str!r}"
        )

    # Reject Windows drive letters or absolute root slashes
    if re.match(r"^[a-zA-Z]:", cleaned) or cleaned.startswith("/") or cleaned.startswith("\\"):
        raise StructuredOutputSecurityError(
            f"{field_name} must be a relative path, not absolute: {path_str!r}"
        )

    # Split by / and \ to check individual components
    parts = re.split(r"[/\\]+", cleaned)
    for part in parts:
        if part == "..":
            raise StructuredOutputSecurityError(
                f"{field_name} contains path traversal token '..': {path_str!r}"
            )
        lower_part = part.lower()
        if "%2e" in lower_part or "%2f" in lower_part or "%5c" in lower_part:
            raise StructuredOutputSecurityError(
                f"{field_name} contains URL-encoded traversal characters: {path_str!r}"
            )

    return cleaned


def validate_safe_endpoint(endpoint_str: str, field_name: str = "endpoint") -> str:
    """Validate that an endpoint is a root-relative path or safe internal route.

    Rejects external URLs (http://, https://, ftp://), dangerous protocols (javascript:, data:),
    and path traversal.
    """
    if not isinstance(endpoint_str, str) or not endpoint_str.strip():
        raise StructuredOutputSecurityError(f"{field_name} must not be empty.")

    cleaned = endpoint_str.strip()

    if "\x00" in cleaned or any(ord(c) < 32 for c in cleaned):
        raise StructuredOutputSecurityError(f"{field_name} contains invalid characters.")

    lower = cleaned.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:", "file:")):
        raise StructuredOutputSecurityError(
            f"{field_name} contains forbidden protocol: {endpoint_str!r}"
        )

    if lower.startswith(("http://", "https://", "ftp://")):
        raise StructuredOutputSecurityError(
            f"{field_name} contains unapproved external URL: {endpoint_str!r}"
        )

    if not cleaned.startswith("/") and not re.match(
        r"^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_.-]+)*$", cleaned
    ):
        raise StructuredOutputSecurityError(
            f"{field_name} is not a valid relative endpoint: {endpoint_str!r}"
        )

    parts = re.split(r"[/\\]+", cleaned)
    for part in parts:
        if part == "..":
            raise StructuredOutputSecurityError(
                f"{field_name} contains path traversal: {endpoint_str!r}"
            )

    return cleaned


def validate_action_type(action_str: str, field_name: str = "action_type") -> str:
    """Validate action type against canonical known action types."""
    if not isinstance(action_str, str) or not action_str.strip():
        raise StructuredOutputSecurityError(f"{field_name} must not be empty.")
    cleaned = action_str.strip()
    if cleaned not in CANONICAL_ACTION_TYPES:
        allowed = sorted(CANONICAL_ACTION_TYPES)
        raise StructuredOutputSecurityError(
            f"Unknown action type '{cleaned}'. Allowed action types: {allowed}"
        )
    return cleaned


# ==============================================================================
# Surface 1: Goal Decomposition Models
# ==============================================================================
class GoalDecompositionSubGoal(BaseModel):
    """Structured sub-goal from goal decomposition reasoning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sub_goal_id: StrictStr
    title: StrictStr
    description: StrictStr
    target_component: StrictStr
    action_type: StrictStr
    priority: StrictInt = Field(ge=1, le=100)

    @field_validator("sub_goal_id", "title", "description")
    @classmethod
    def _validate_non_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise StructuredOutputValidationError(f"{info.field_name} must not be blank.")
        return v.strip()

    @field_validator("target_component")
    @classmethod
    def _validate_target_component(cls, v: str) -> str:
        return validate_safe_relative_path(v, field_name="target_component")

    @field_validator("action_type")
    @classmethod
    def _validate_action(cls, v: str) -> str:
        return validate_action_type(v, field_name="action_type")


class GoalDecompositionResult(BaseModel):
    """Validated structured output for goal decomposition semantic reasoning.

    Authority: GEMINI_SEMANTIC_JUDGMENT (advisory, cannot overwrite deterministic facts).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictStr = CANONICAL_STRUCTURED_SCHEMA_VERSION
    change_request_id: StrictStr
    summary: StrictStr
    sub_goals: list[GoalDecompositionSubGoal] = Field(min_length=1)
    affected_components: list[StrictStr] = Field(min_length=1)
    recommended_specialists: list[StrictStr] = Field(min_length=1)
    estimated_risk_level: SemanticRiskLevel
    rationale: StrictStr
    suggested_action_types: list[StrictStr] = Field(min_length=1)

    @property
    def authority_lane(self) -> str:
        """Authority classification for this model artifact."""
        return CANONICAL_AUTHORITY_LANE

    @field_validator("schema_version", "change_request_id", "summary", "rationale")
    @classmethod
    def _validate_non_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise StructuredOutputValidationError(f"{info.field_name} must not be blank.")
        return v.strip()

    @field_validator("affected_components")
    @classmethod
    def _validate_components(cls, v: list[str]) -> list[str]:
        cleaned = []
        for comp in v:
            c = validate_safe_relative_path(comp, field_name="affected_components")
            cleaned.append(c)
        return cleaned

    @field_validator("recommended_specialists")
    @classmethod
    def _validate_specialists(cls, v: list[str]) -> list[str]:
        cleaned = []
        for spec in v:
            if not spec or not spec.strip():
                raise StructuredOutputValidationError(
                    "recommended_specialists items must not be blank."
                )
            s = spec.strip()
            if s not in CANONICAL_SPECIALIST_ROLES:
                allowed = sorted(CANONICAL_SPECIALIST_ROLES)
                raise StructuredOutputValidationError(
                    f"Unknown specialist '{s}'. Allowed specialists: {allowed}"
                )
            cleaned.append(s)
        return cleaned

    @field_validator("suggested_action_types")
    @classmethod
    def _validate_actions(cls, v: list[str]) -> list[str]:
        cleaned = []
        for action in v:
            a = validate_action_type(action, field_name="suggested_action_types")
            cleaned.append(a)
        return cleaned


# ==============================================================================
# Surface 2: Policy Explanation Models
# ==============================================================================
class PolicyRuleExplanation(BaseModel):
    """Structured explanation for an individual policy rule evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: StrictStr
    rule_name: StrictStr
    explanation: StrictStr
    impact_level: PolicyImpactLevel
    compliance_status: PolicyComplianceStatus

    @field_validator("rule_id", "rule_name", "explanation")
    @classmethod
    def _validate_non_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise StructuredOutputValidationError(f"{info.field_name} must not be blank.")
        return v.strip()


class PolicyExplanationResult(BaseModel):
    """Validated structured output for policy explanation semantic reasoning.

    Authority: GEMINI_SEMANTIC_JUDGMENT (advisory explanation of supplied policy context;
    does NOT author policy or alter autonomy classification).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictStr = CANONICAL_STRUCTURED_SCHEMA_VERSION
    change_id: StrictStr
    decision_id: StrictStr
    summary_explanation: StrictStr
    rule_explanations: list[PolicyRuleExplanation] = Field(min_length=1)
    compliance_considerations: list[StrictStr] = Field(default_factory=list)
    remediation_guidance: list[StrictStr] = Field(default_factory=list)
    explanation_scope: StrictStr

    @property
    def authority_lane(self) -> str:
        """Authority classification for this model artifact."""
        return CANONICAL_AUTHORITY_LANE

    @field_validator(
        "schema_version",
        "change_id",
        "decision_id",
        "summary_explanation",
        "explanation_scope",
    )
    @classmethod
    def _validate_non_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise StructuredOutputValidationError(f"{info.field_name} must not be blank.")
        return v.strip()

    @field_validator("compliance_considerations", "remediation_guidance")
    @classmethod
    def _validate_str_lists(cls, v: list[str], info: Any) -> list[str]:
        cleaned = []
        for item in v:
            if not item or not item.strip():
                raise StructuredOutputValidationError(f"{info.field_name} items must not be blank.")
            cleaned.append(item.strip())
        return cleaned


# ==============================================================================
# Surface 3: Semantic Audit Models
# ==============================================================================
class SemanticEvidenceCitation(BaseModel):
    """Structured evidence citation reference distinct from prose explanation (OUT-10)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: StrictStr
    evidence_key: StrictStr
    relevance_summary: StrictStr
    supports_claim_ids: list[StrictStr] = Field(min_length=1)

    @field_validator("citation_id", "evidence_key", "relevance_summary")
    @classmethod
    def _validate_non_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise StructuredOutputValidationError(f"{info.field_name} must not be blank.")
        return v.strip()

    @field_validator("supports_claim_ids")
    @classmethod
    def _validate_claims(cls, v: list[str]) -> list[str]:
        cleaned = []
        for c in v:
            if not c or not c.strip():
                raise StructuredOutputValidationError("supports_claim_ids items must not be blank.")
            cleaned.append(c.strip())
        return cleaned


class SemanticClaimAssessment(BaseModel):
    """Structured evaluation of a single claim or success criterion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: StrictStr
    assessment: SemanticAssessmentVerdict
    assessment_narrative: StrictStr
    cited_evidence_keys: list[StrictStr] = Field(default_factory=list)
    counter_evidence_points: list[StrictStr] = Field(default_factory=list)
    missing_evidence_points: list[StrictStr] = Field(default_factory=list)

    @field_validator("claim_id", "assessment_narrative")
    @classmethod
    def _validate_non_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise StructuredOutputValidationError(f"{info.field_name} must not be blank.")
        return v.strip()

    @model_validator(mode="after")
    def _validate_claim_invariants(self) -> SemanticClaimAssessment:
        if self.assessment == SemanticAssessmentVerdict.SUPPORTS:
            if not self.cited_evidence_keys:
                raise StructuredOutputValidationError(
                    f"Claim assessment SUPPORTS for '{self.claim_id}' requires "
                    "at least one cited_evidence_keys entry."
                )
        elif self.assessment == SemanticAssessmentVerdict.CONTRADICTS:
            if not self.counter_evidence_points:
                raise StructuredOutputValidationError(
                    f"Claim assessment CONTRADICTS for '{self.claim_id}' requires "
                    "counter_evidence_points."
                )
            if not self.cited_evidence_keys:
                raise StructuredOutputValidationError(
                    f"Claim assessment CONTRADICTS for '{self.claim_id}' requires "
                    "cited_evidence_keys."
                )
        elif self.assessment == SemanticAssessmentVerdict.INSUFFICIENT:
            if not self.missing_evidence_points:
                raise StructuredOutputValidationError(
                    f"Claim assessment INSUFFICIENT for '{self.claim_id}' requires "
                    "missing_evidence_points."
                )
        return self


class SemanticAuditResult(BaseModel):
    """Validated structured output for independent semantic audit review.

    Authority: GEMINI_SEMANTIC_JUDGMENT (advisory, cannot overwrite deterministic facts).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictStr = CANONICAL_STRUCTURED_SCHEMA_VERSION
    audit_id: StrictStr
    change_id: StrictStr
    overall_verdict: SemanticAssessmentVerdict
    reasoning_narrative: StrictStr
    claim_assessments: list[SemanticClaimAssessment] = Field(min_length=1)
    evidence_citations: list[SemanticEvidenceCitation] = Field(default_factory=list)
    counter_evidence: list[StrictStr] = Field(default_factory=list)
    missing_evidence: list[StrictStr] = Field(default_factory=list)

    @property
    def authority_lane(self) -> str:
        """Authority classification for this model artifact."""
        return CANONICAL_AUTHORITY_LANE

    @field_validator("schema_version", "audit_id", "change_id", "reasoning_narrative")
    @classmethod
    def _validate_non_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise StructuredOutputValidationError(f"{info.field_name} must not be blank.")
        return v.strip()

    @model_validator(mode="after")
    def _validate_audit_invariants(self) -> SemanticAuditResult:
        if self.overall_verdict == SemanticAssessmentVerdict.SUPPORTS:
            if not self.evidence_citations:
                raise StructuredOutputValidationError(
                    "Overall verdict SUPPORTS requires at least one evidence citation."
                )
        elif self.overall_verdict == SemanticAssessmentVerdict.CONTRADICTS:
            if not self.counter_evidence:
                raise StructuredOutputValidationError(
                    "Overall verdict CONTRADICTS requires counter_evidence items."
                )
            if not self.evidence_citations:
                raise StructuredOutputValidationError(
                    "Overall verdict CONTRADICTS requires evidence_citations."
                )
        elif self.overall_verdict == SemanticAssessmentVerdict.INSUFFICIENT:
            if not self.missing_evidence:
                raise StructuredOutputValidationError(
                    "Overall verdict INSUFFICIENT requires missing_evidence items."
                )
        return self


# ==============================================================================
# Fail-Closed JSON Parser & Extractor
# ==============================================================================
def _reject_special_json_constants(constant_name: str) -> None:
    """Fail closed on NaN, Infinity, -Infinity in JSON."""
    raise StructuredOutputJSONError(
        f"Invalid JSON constant '{constant_name}' not permitted in canonical structured output."
    )


def parse_structured_json(raw_text: str) -> dict[str, Any]:
    """Parse raw model text into a validated JSON dictionary with strict fail-closed semantics.

    - Strips markdown code block wrappers (```json ... ``` or ``` ... ```) if cleanly present.
    - Rejects malformed JSON, incomplete syntax, trailing garbage, or special constants (NaN).
    - Ensures root is a JSON object (dict), not a list, number, boolean, string, or null.
    - Does NOT attempt fuzzy repairs, regex key matching, bracket guessing, or auto-fixing.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise StructuredOutputJSONError("Raw model response text is empty or not a string.")

    cleaned = raw_text.strip()

    # Clean markdown code block if present
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        first_line = lines[0].strip().lower()
        if first_line.startswith("```json") or first_line == "```":
            if lines[-1].strip() == "```":
                cleaned = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(cleaned, parse_constant=_reject_special_json_constants)
    except (json.JSONDecodeError, StructuredOutputJSONError) as exc:
        raise StructuredOutputJSONError(
            f"Failed to parse model output as valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise StructuredOutputJSONError(
            f"Expected JSON root to be an object (dict), got {type(data).__name__}."
        )

    return data


# ==============================================================================
# Surface Parsers
# ==============================================================================
def parse_goal_decomposition_output(
    raw: str | dict[str, Any],
) -> GoalDecompositionResult:
    """Parse and strictly validate raw model output into GoalDecompositionResult.

    Fails closed on any malformed JSON, missing field, extra field, wrong type,
    or security violation (e.g. path traversal, unknown action).
    """
    dict_data = parse_structured_json(raw) if isinstance(raw, str) else raw
    if not isinstance(dict_data, dict):
        raise StructuredOutputValidationError("Input must be a JSON string or dict.")

    try:
        return GoalDecompositionResult.model_validate(dict_data)
    except StructuredOutputError:
        raise
    except ValidationError as exc:
        raise StructuredOutputValidationError(
            f"Goal decomposition validation failed: {exc}",
            errors=exc.errors(),
        ) from exc


def parse_policy_explanation_output(
    raw: str | dict[str, Any],
) -> PolicyExplanationResult:
    """Parse and strictly validate raw model output into PolicyExplanationResult.

    Fails closed on any malformed JSON, missing field, extra field, wrong type,
    or policy authority violation.
    """
    dict_data = parse_structured_json(raw) if isinstance(raw, str) else raw
    if not isinstance(dict_data, dict):
        raise StructuredOutputValidationError("Input must be a JSON string or dict.")

    try:
        return PolicyExplanationResult.model_validate(dict_data)
    except StructuredOutputError:
        raise
    except ValidationError as exc:
        raise StructuredOutputValidationError(
            f"Policy explanation validation failed: {exc}",
            errors=exc.errors(),
        ) from exc


def parse_semantic_audit_output(
    raw: str | dict[str, Any],
) -> SemanticAuditResult:
    """Parse and strictly validate raw model output into SemanticAuditResult.

    Fails closed on any malformed JSON, missing field, extra field, wrong type,
    uncited decisive assessment, or fact-overwriting attempt.
    """
    dict_data = parse_structured_json(raw) if isinstance(raw, str) else raw
    if not isinstance(dict_data, dict):
        raise StructuredOutputValidationError("Input must be a JSON string or dict.")

    try:
        return SemanticAuditResult.model_validate(dict_data)
    except StructuredOutputError:
        raise
    except ValidationError as exc:
        raise StructuredOutputValidationError(
            f"Semantic audit validation failed: {exc}",
            errors=exc.errors(),
        ) from exc


# ==============================================================================
# Prompt Builders for the Three Semantic Surfaces
# ==============================================================================
def build_goal_decomposition_prompt(
    *,
    change_request_id: str,
    title: str,
    description: str,
    target_systems: list[str],
    data_classification: str,
    success_criteria: list[str],
) -> str:
    """Construct schema-constrained prompt for goal decomposition reasoning."""
    action_types_doc = (
        "inspect_impact, evaluate_policy, generate_migration, audit_evidence, "
        "prepare_release, verify_artifacts, rehearse_migration, check_dependencies, "
        "scan_repository, dry_run_migration, validate_contracts"
    )
    return (
        "You are ChangeMesh Goal Decomposition Specialist. Your task is to analyze "
        "the requested change and produce a structured breakdown of sub-goals, "
        "affected components, and recommended specialists.\n\n"
        "Input Change Specification:\n"
        f"- Change Request ID: {change_request_id}\n"
        f"- Title: {title}\n"
        f"- Description: {description}\n"
        f"- Target Systems: {', '.join(target_systems)}\n"
        f"- Data Classification: {data_classification}\n"
        f"- Success Criteria:\n" + "\n".join(f"  * {crit}" for crit in success_criteria) + "\n\n"
        "Strict Output Requirements:\n"
        "Return ONLY a valid, raw JSON object matching this exact schema (no prose outside JSON):\n"
        "{\n"
        '  "schema_version": "1.0.0",\n'
        f'  "change_request_id": "{change_request_id}",\n'
        '  "summary": "<high-level summary of decomposition>",\n'
        '  "sub_goals": [\n'
        "    {\n"
        '      "sub_goal_id": "<e.g. sub-1>",\n'
        '      "title": "<sub-goal title>",\n'
        '      "description": "<detailed sub-goal description>",\n'
        '      "target_component": "<relative repository path without traversal>",\n'
        f'      "action_type": "<one of: {action_types_doc}>",\n'
        '      "priority": 1\n'
        "    }\n"
        "  ],\n"
        '  "affected_components": ["<relative_path_1>", ...],\n'
        '  "recommended_specialists": ["Impact Scout", "Policy Guardian", ...],\n'
        '  "estimated_risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",\n'
        '  "rationale": "<reasoning for decomposition>",\n'
        '  "suggested_action_types": ["inspect_impact", ...]\n'
        "}\n"
    )


def build_policy_explanation_prompt(
    *,
    change_id: str,
    decision_id: str,
    action_class: str,
    autonomy_class: str,
    policy_source: str,
    rationale: str,
    violated_rules: list[str],
) -> str:
    """Construct schema-constrained prompt for policy explanation reasoning."""
    return (
        "You are ChangeMesh Policy Guardian Explainer. Your task is to provide "
        "an advisory explanation of an already supplied organizational policy decision. "
        "You DO NOT author or modify policy.\n\n"
        "Supplied Policy Decision Context:\n"
        f"- Change ID: {change_id}\n"
        f"- Decision ID: {decision_id}\n"
        f"- Action Class: {action_class}\n"
        f"- Autonomy Class: {autonomy_class}\n"
        f"- Policy Source: {policy_source}\n"
        f"- Policy Rationale: {rationale}\n"
        f"- Violated Rules: {', '.join(violated_rules) if violated_rules else 'None'}\n\n"
        "Strict Output Requirements:\n"
        "Return ONLY a valid, raw JSON object matching this exact schema (no prose outside JSON):\n"
        "{\n"
        '  "schema_version": "1.0.0",\n'
        f'  "change_id": "{change_id}",\n'
        f'  "decision_id": "{decision_id}",\n'
        '  "summary_explanation": "<clear explanation of the policy decision>",\n'
        '  "rule_explanations": [\n'
        "    {\n"
        '      "rule_id": "<rule_id>",\n'
        '      "rule_name": "<rule_name>",\n'
        '      "explanation": "<why this rule applies>",\n'
        '      "impact_level": "<INFO|LOW|MEDIUM|HIGH|CRITICAL>",\n'
        '      "compliance_status": "<COMPLIANT|NON_COMPLIANT|REQUIRES_REVIEW|EXEMPT>"\n'
        "    }\n"
        "  ],\n"
        '  "compliance_considerations": ["<consideration_1>", ...],\n'
        '  "remediation_guidance": ["<remediation_step_1>", ...],\n'
        '  "explanation_scope": "<bounded scope description>"\n'
        "}\n"
    )


def build_semantic_audit_prompt(
    *,
    audit_id: str,
    change_id: str,
    claims: list[dict[str, Any]],
    evidence_summaries: list[dict[str, Any]],
) -> str:
    """Construct schema-constrained prompt for semantic audit review."""
    claims_text = "\n".join(
        f"- Claim [{c.get('claim_id')}]: {c.get('claim_description')} "
        f"(Target: {c.get('target_criterion')})"
        for c in claims
    )
    evidence_text = "\n".join(
        f"- Evidence [{e.get('evidence_key')}]: {e.get('summary')} (Source: {e.get('source')})"
        for e in evidence_summaries
    )

    return (
        "You are ChangeMesh Independent Evidence Auditor. Your task is to perform "
        "an advisory semantic review evaluating whether the provided evidence "
        "semantically supports the stated claims.\n\n"
        f"Audit ID: {audit_id}\n"
        f"Change ID: {change_id}\n\n"
        "Claims to Audit:\n"
        f"{claims_text}\n\n"
        "Provided Evidence Context:\n"
        f"{evidence_text}\n\n"
        "Strict Output Requirements:\n"
        "Return ONLY a valid, raw JSON object matching this exact schema (no prose outside JSON):\n"
        "{\n"
        '  "schema_version": "1.0.0",\n'
        f'  "audit_id": "{audit_id}",\n'
        f'  "change_id": "{change_id}",\n'
        '  "overall_verdict": "<SUPPORTS|CONTRADICTS|INSUFFICIENT>",\n'
        '  "reasoning_narrative": "<overall audit reasoning narrative>",\n'
        '  "claim_assessments": [\n'
        "    {\n"
        '      "claim_id": "<claim_id>",\n'
        '      "assessment": "<SUPPORTS|CONTRADICTS|INSUFFICIENT>",\n'
        '      "assessment_narrative": "<explanation for this claim>",\n'
        '      "cited_evidence_keys": ["<evidence_key_1>", ...],\n'
        '      "counter_evidence_points": [],\n'
        '      "missing_evidence_points": []\n'
        "    }\n"
        "  ],\n"
        '  "evidence_citations": [\n'
        "    {\n"
        '      "citation_id": "<cit-1>",\n'
        '      "evidence_key": "<evidence_key_1>",\n'
        '      "relevance_summary": "<relevance of this evidence>",\n'
        '      "supports_claim_ids": ["<claim_id>"]\n'
        "    }\n"
        "  ],\n"
        '  "counter_evidence": [],\n'
        '  "missing_evidence": []\n'
        "}\n"
    )
