"""ChangeMesh Policy Guardian — Google ADK Agent Definition.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the canonical Policy Guardian ADK agent.

Responsibilities:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Evaluates/enforces organizational policy boundaries and privacy classifications.
- Organizational Policy is the AUTHORITY SOURCE; Policy Guardian is the evaluator/enforcer.
- Cannot manufacture human authority from uncertainty or model opinion.
- Cannot override deterministic execution facts.
- Zero credentials required, zero external writes, zero Gemini model invocations.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator, ClassVar, Final, Type

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from pydantic import BaseModel

from domain.contracts.agent_descriptor import AgentDescriptor
from domain.contracts.data_class import DataClassLevel
from src.agents.definition import (
    POLICY_GUARDIAN_INSTRUCTION,
    AgentDefinition,
)
from src.agents.schemas import PolicyGuardianInput, PolicyGuardianOutput


class PrivacySeverity(str, Enum):
    """Deterministic severity assigned to a model-boundary finding."""

    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


class PromptSurface(str, Enum):
    """Semantic prompt surfaces with independently minimized input contracts."""

    GOAL_DECOMPOSITION = "goal_decomposition"
    POLICY_EXPLANATION = "policy_explanation"
    SEMANTIC_AUDIT = "semantic_audit"


@dataclass(frozen=True)
class PrivacyFinding:
    """Non-sensitive finding metadata; matched content is never retained."""

    code: str
    severity: PrivacySeverity
    position: int


@dataclass(frozen=True)
class PrivacyAudit:
    """Deterministic privacy result for one text value."""

    safe_to_send: bool
    findings: tuple[PrivacyFinding, ...]
    blockers: tuple[PrivacyFinding, ...]
    review_items: tuple[PrivacyFinding, ...]


class PrivacyBoundaryError(ValueError):
    """Raised without raw input when Policy Guardian blocks model-boundary data."""

    def __init__(self, reason_codes: Sequence[str], *, surface: str = "model_input") -> None:
        self.reason_codes = tuple(dict.fromkeys(reason_codes))
        self.surface = surface
        codes = ", ".join(self.reason_codes) or "UNSAFE_INPUT"
        super().__init__(f"Policy Guardian blocked {surface}; deterministic reason codes: {codes}.")


class PromptContextError(ValueError):
    """Raised when a semantic prompt context violates its exact field contract."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"Prompt context rejected by Policy Guardian: {reason_code}.")


# One canonical privacy pattern table owned by Policy Guardian.  Patterns record
# only categories and offsets; matched values never enter findings or exceptions.
_BLOCKING_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "private_key",
        re.compile(r"-{5}BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-{5}", re.IGNORECASE),
    ),
    (
        "api_key",
        re.compile(r"\b(?:sk-(?:proj-|svcacct-)?|AIza)[A-Za-z0-9_-]{8,}\b"),
    ),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("cloud_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    (
        "authorization_bearer",
        re.compile(r"\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/-]{16,}", re.IGNORECASE),
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}", re.IGNORECASE),
    ),
    (
        "connection_string_password",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/[^\s:@/]+:[^\s@/]+@",
            re.IGNORECASE,
        ),
    ),
    (
        "session_cookie",
        re.compile(r"\b(?:set-cookie|cookie)\s*:\s*[^\r\n]{12,}", re.IGNORECASE),
    ),
    (
        "credential_assignment",
        re.compile(
            r"\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|client[_ -]?secret)"
            r"\s*[:=]\s*\S+",
            re.IGNORECASE,
        ),
    ),
    (
        "service_account_material",
        re.compile(
            r'"(?:type|private_key|client_email|client_secret)"\s*:\s*"[^"\r\n]+"',
            re.IGNORECASE,
        ),
    ),
    (
        "non_reserved_email",
        re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE),
    ),
    (
        "phone_number",
        re.compile(
            r"(?<!\d)(?:\+?1[\s.-]?)?(?:\([2-9]\d{2}\)|[2-9]\d{2})[\s.-]\d{3}[\s.-]\d{4}(?!\d)"
        ),
    ),
)

_REVIEW_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "uuid",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "public_ip",
        re.compile(
            r"\b(?!(?:10|127)\.)(?!(?:192\.168)\.)(?!(?:172\.(?:1[6-9]|2\d|3[01]))\.)(?:\d{1,3}\.){3}\d{1,3}\b"
        ),
    ),
    (
        "production_marker",
        re.compile(
            r"\b(?:production dump|prod dump|raw traffic|customer export|"
            r"patient record|student record)\b",
            re.IGNORECASE,
        ),
    ),
)

_RESERVED_EMAIL_DOMAINS: Final[frozenset[str]] = frozenset(
    {"example.com", "example.net", "example.org", "example.test"}
)

_PROMPT_FIELD_ALLOWLISTS: Final[dict[PromptSurface, frozenset[str]]] = {
    PromptSurface.GOAL_DECOMPOSITION: frozenset(
        {
            "change_request_id",
            "title",
            "description",
            "target_systems",
            "data_classification",
            "success_criteria",
            "collection_mode",
            "declared_mode",
        }
    ),
    PromptSurface.POLICY_EXPLANATION: frozenset(
        {
            "change_id",
            "decision_id",
            "action_class",
            "autonomy_class",
            "policy_source",
            "rationale",
            "violated_rules",
            "collection_mode",
            "declared_mode",
        }
    ),
    PromptSurface.SEMANTIC_AUDIT: frozenset(
        {
            "audit_id",
            "change_id",
            "claims",
            "evidence_summaries",
            "collection_mode",
            "declared_mode",
        }
    ),
}

_NESTED_PROMPT_FIELD_ALLOWLISTS: Final[dict[str, frozenset[str]]] = {
    "claims": frozenset({"claim_id", "claim_description", "target_criterion"}),
    "evidence_summaries": frozenset({"evidence_key", "summary", "source"}),
}


class PolicyGuardian(BaseAgent):
    """ChangeMesh Policy Guardian ADK Agent.

    Evaluates proposed changes against organizational policy boundaries,
    data privacy rules, and separation-of-duty constraints.
    """

    # ChangeMesh Agent Definition Metadata (P-07.02)
    agent_id: ClassVar[str] = "agent-policy-guardian"
    role: ClassVar[str] = "policy_guardian"
    agent_revision: ClassVar[str] = "1.0.0"
    revision: ClassVar[str] = "1.0.0"
    agent_description: ClassVar[str] = (
        "Evaluates proposed changes against organizational policy boundaries, "
        "data privacy rules, and separation-of-duty constraints."
    )
    declared_capabilities: ClassVar[list[str]] = [
        "organizational_policy_evaluation",
        "privacy_boundary_check",
        "separation_of_duty_enforcement",
        "autonomy_classification_evaluation",
    ]
    capabilities: ClassVar[list[str]] = declared_capabilities
    forbidden_actions: ClassVar[list[str]] = [
        "author_organizational_policy",
        "manufacture_human_authority",
        "override_deterministic_facts",
        "execute_external_changes",
    ]
    instruction_contract: ClassVar[str] = POLICY_GUARDIAN_INSTRUCTION
    permitted_tool_ids: ClassVar[list[str]] = [
        "tool-policy-ruleset-evaluator",
        "tool-data-class-checker",
        "tool-shadowlab-auth-checker",
    ]
    permitted_data_classifications: ClassVar[list[DataClassLevel]] = [
        DataClassLevel.PUBLIC,
        DataClassLevel.INTERNAL,
        DataClassLevel.CONFIDENTIAL,
        DataClassLevel.RESTRICTED,
    ]

    # ADK BaseAgent fields
    name: str = "policy_guardian"
    description: str = agent_description
    input_schema: Type[BaseModel] = PolicyGuardianInput
    output_schema: Type[BaseModel] = PolicyGuardianOutput

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

    @staticmethod
    def audit_privacy_text(text: str) -> PrivacyAudit:
        """Inspect text deterministically without retaining matched content."""
        if not isinstance(text, str):
            raise PromptContextError("NON_TEXT_INPUT")

        findings: list[PrivacyFinding] = []
        for code, pattern in _BLOCKING_PATTERNS:
            for match in pattern.finditer(text):
                if code == "non_reserved_email":
                    domain = match.group(1).lower()
                    if domain in _RESERVED_EMAIL_DOMAINS or domain.endswith(".example.test"):
                        continue
                findings.append(
                    PrivacyFinding(
                        code=code,
                        severity=PrivacySeverity.BLOCK,
                        position=match.start(),
                    )
                )

        for code, pattern in _REVIEW_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(
                    PrivacyFinding(
                        code=code,
                        severity=PrivacySeverity.REVIEW,
                        position=match.start(),
                    )
                )

        findings.sort(key=lambda finding: (finding.position, finding.code))
        blockers = tuple(f for f in findings if f.severity == PrivacySeverity.BLOCK)
        review_items = tuple(f for f in findings if f.severity == PrivacySeverity.REVIEW)
        return PrivacyAudit(
            safe_to_send=not blockers and not review_items,
            findings=tuple(findings),
            blockers=blockers,
            review_items=review_items,
        )

    @classmethod
    def assert_model_input_safe(
        cls,
        prompt: str,
        *,
        system_instruction: str | None = None,
        surface: str = "model_input",
    ) -> tuple[PrivacyAudit, ...]:
        """Reject unsafe prompt and system text before any SDK call."""
        audits: list[PrivacyAudit] = []
        for value in (prompt, system_instruction):
            if value is None:
                continue
            audit = cls.audit_privacy_text(value)
            audits.append(audit)
            if not audit.safe_to_send:
                codes = [finding.code for finding in audit.findings]
                raise PrivacyBoundaryError(codes, surface=surface)
        return tuple(audits)

    @classmethod
    def minimize_prompt_context(
        cls,
        surface: PromptSurface | str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return an exact allowlisted context or reject it before rendering."""
        try:
            normalized_surface = (
                surface if isinstance(surface, PromptSurface) else PromptSurface(surface)
            )
        except (TypeError, ValueError) as exc:
            raise PromptContextError("UNKNOWN_PROMPT_SURFACE") from exc

        if not isinstance(context, Mapping):
            raise PromptContextError("CONTEXT_MUST_BE_MAPPING")

        allowed = _PROMPT_FIELD_ALLOWLISTS[normalized_surface]
        if set(context) != allowed:
            raise PromptContextError("ALLOWLIST_MISMATCH")

        if normalized_surface == PromptSurface.SEMANTIC_AUDIT:
            minimized: dict[str, Any] = {
                "audit_id": cls._clean_context_text(context["audit_id"]),
                "change_id": cls._clean_context_text(context["change_id"]),
                "claims": cls._clean_nested_context(context["claims"], "claims"),
                "evidence_summaries": cls._clean_nested_context(
                    context["evidence_summaries"], "evidence_summaries"
                ),
                "collection_mode": cls._clean_context_text(context["collection_mode"]),
                "declared_mode": cls._clean_context_text(context["declared_mode"]),
            }
        else:
            minimized = {key: cls._clean_context_value(context[key]) for key in sorted(allowed)}

        cls.validate_provenance(
            collection_mode=minimized["collection_mode"],
            declared_mode=minimized["declared_mode"],
        )
        cls._assert_context_values_safe(minimized, surface=normalized_surface.value)
        return copy.deepcopy(minimized)

    @staticmethod
    def validate_provenance(*, collection_mode: str, declared_mode: str) -> str:
        """Reject a mode label that does not match the actual source mode."""
        allowed_modes = {"FIXTURE", "SIMULATION", "RECORDED_CLOUD", "LIVE_WRITE"}
        if collection_mode not in allowed_modes or declared_mode not in allowed_modes:
            raise PromptContextError("UNKNOWN_EXECUTION_MODE")
        if collection_mode != declared_mode:
            raise PromptContextError("PROVENANCE_MODE_MISMATCH")
        return collection_mode

    @staticmethod
    def _clean_context_text(value: Any) -> str:
        if isinstance(value, Enum):
            value = value.value
        if not isinstance(value, str) or not value.strip():
            raise PromptContextError("NON_BLANK_TEXT_REQUIRED")
        return value.strip()

    @classmethod
    def _clean_context_value(cls, value: Any) -> Any:
        if isinstance(value, Enum):
            value = value.value
        if isinstance(value, str):
            return cls._clean_context_text(value)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [cls._clean_context_text(item) for item in value]
        raise PromptContextError("UNSUPPORTED_CONTEXT_VALUE")

    @classmethod
    def _clean_nested_context(cls, value: Any, field_name: str) -> list[dict[str, str]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise PromptContextError("NESTED_CONTEXT_MUST_BE_LIST")

        allowed = _NESTED_PROMPT_FIELD_ALLOWLISTS[field_name]
        cleaned: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, Mapping) or set(item) != allowed:
                raise PromptContextError("NESTED_ALLOWLIST_MISMATCH")
            cleaned.append({key: cls._clean_context_text(item[key]) for key in sorted(allowed)})
        return cleaned

    @classmethod
    def _assert_context_values_safe(cls, value: Any, *, surface: str) -> None:
        if isinstance(value, str):
            cls.assert_model_input_safe(value, surface=surface)
        elif isinstance(value, Mapping):
            for child in value.values():
                cls._assert_context_values_safe(child, surface=surface)
        elif isinstance(value, Sequence):
            for child in value:
                cls._assert_context_values_safe(child, surface=surface)

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """ADK core execution logic for the Policy Guardian.

        In P-07.02 definition stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
