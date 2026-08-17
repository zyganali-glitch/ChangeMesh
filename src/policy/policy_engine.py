"""Deterministic Policy Engine (P-16)."""

import re
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from domain.contracts.conventions import (
    UtcDateTime,
    normalize_utc_datetime,
)


class PolicyFindingCategory(str, Enum):
    SECRET_DETECTED = "SECRET_DETECTED"
    PROHIBITED_DATA_CLASS = "PROHIBITED_DATA_CLASS"
    UNREGISTERED_TOOL = "UNREGISTERED_TOOL"
    UNAUTHORIZED_PATH = "UNAUTHORIZED_PATH"
    IRREVERSIBLE_ACTION = "IRREVERSIBLE_ACTION"
    PROMPT_INJECTION_INDICATOR = "PROMPT_INJECTION_INDICATOR"
    MODEL_ARMOR_RESULT = "MODEL_ARMOR_RESULT"


class PolicyFindingSeverity(str, Enum):
    BLOCK = "BLOCK"
    WARN = "WARN"
    INFO = "INFO"


class PolicyFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str
    category: PolicyFindingCategory
    severity: PolicyFindingSeverity
    description: str
    source: str = "DETERMINISTIC_CODE"
    evidence_ref: str | None = None
    path: str | None = None
    is_deterministic: bool = True


class PolicyEvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    findings: tuple[PolicyFinding, ...]
    overall_verdict: str
    blocked_count: int
    warning_count: int
    evidence_mode: str
    evaluated_at: UtcDateTime
    gemini_explanation: str | None = None
    gemini_explanation_authority: str = "GEMINI_SEMANTIC_JUDGMENT"


class DeterministicPolicyChecker:
    REGISTERED_TOOLS: ClassVar[frozenset[str]] = frozenset(
        {
            "tool-git-diff-analyzer",
            "tool-metadata-graph-reader",
            "tool-dependency-graph-reader",
            "tool-policy-checker",
            "tool-migration-planner",
            "tool-artifact-generator",
            "tool-evidence-collector",
            "tool-github-draft-pr",
        }
    )

    ALLOWED_WRITE_PATHS: ClassVar[frozenset[str]] = frozenset(
        {
            "synthetic/",
            "fixtures/",
            "tests/",
            "tmp/",
        }
    )

    SECRET_PATTERNS: ClassVar[list[tuple[str, re.Pattern]]] = [
        (
            "private_key",
            re.compile(r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----", re.IGNORECASE),
        ),
        (
            "api_key",
            re.compile(r'(?:api[_-]?key|apikey)\s*[:=]\s*[\'"]?[A-Za-z0-9_\-]{20,}', re.IGNORECASE),
        ),
        ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE)),
        ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.")),
        (
            "connection_string",
            re.compile(r"(?:mongodb|postgres|mysql|redis)://[^\s]{10,}", re.IGNORECASE),
        ),
    ]

    def evaluate(
        self,
        input_text: str,
        tool_ids: list[str],
        target_paths: list[str],
        action_type: str,
        data_classification: str,
        change_id: str,
    ) -> PolicyEvaluationResult:
        findings: list[PolicyFinding] = []

        # 1. Secret detection
        for secret_name, pattern in self.SECRET_PATTERNS:
            if isinstance(input_text, str) and pattern.search(input_text):
                findings.append(
                    PolicyFinding(
                        finding_id=f"f-{uuid4()}",
                        category=PolicyFindingCategory.SECRET_DETECTED,
                        severity=PolicyFindingSeverity.BLOCK,
                        description=f"Secret of type {secret_name} detected in input text",
                        source="DETERMINISTIC_CODE",
                        is_deterministic=True,
                    )
                )

        # 2. Prohibited data
        if data_classification == "RESTRICTED":
            findings.append(
                PolicyFinding(
                    finding_id=f"f-{uuid4()}",
                    category=PolicyFindingCategory.PROHIBITED_DATA_CLASS,
                    severity=PolicyFindingSeverity.BLOCK,
                    description="RESTRICTED data classification requires authorized actor",
                    source="DETERMINISTIC_CODE",
                    is_deterministic=True,
                )
            )

        # 3. Unregistered tools
        for tool_id in tool_ids:
            if tool_id not in self.REGISTERED_TOOLS:
                findings.append(
                    PolicyFinding(
                        finding_id=f"f-{uuid4()}",
                        category=PolicyFindingCategory.UNREGISTERED_TOOL,
                        severity=PolicyFindingSeverity.BLOCK,
                        description=f"Unregistered tool requested: {tool_id}",
                        source="DETERMINISTIC_CODE",
                        is_deterministic=True,
                    )
                )

        # 4. Unauthorized paths
        for path in target_paths:
            allowed = False
            for allowed_prefix in self.ALLOWED_WRITE_PATHS:
                if path.startswith(allowed_prefix):
                    allowed = True
                    break
            if not allowed:
                findings.append(
                    PolicyFinding(
                        finding_id=f"f-{uuid4()}",
                        category=PolicyFindingCategory.UNAUTHORIZED_PATH,
                        severity=PolicyFindingSeverity.BLOCK,
                        description=f"Unauthorized write path: {path}",
                        path=path,
                        source="DETERMINISTIC_CODE",
                        is_deterministic=True,
                    )
                )

        # 5. Irreversible actions
        if action_type == "DESTRUCTIVE_NO_MIGRATION":
            findings.append(
                PolicyFinding(
                    finding_id=f"f-{uuid4()}",
                    category=PolicyFindingCategory.IRREVERSIBLE_ACTION,
                    severity=PolicyFindingSeverity.BLOCK,
                    description="Destructive action requires down-migration plan",
                    source="DETERMINISTIC_CODE",
                    is_deterministic=True,
                )
            )

        blocked = sum(1 for f in findings if f.severity == PolicyFindingSeverity.BLOCK)
        warnings = sum(1 for f in findings if f.severity == PolicyFindingSeverity.WARN)
        verdict = "BLOCK" if blocked > 0 else "ALLOW"

        return PolicyEvaluationResult(
            change_id=change_id,
            findings=tuple(findings),
            overall_verdict=verdict,
            blocked_count=blocked,
            warning_count=warnings,
            evidence_mode="SIMULATION",
            evaluated_at=normalize_utc_datetime(datetime.now(timezone.utc)),
        )


class InjectionDetector:
    INJECTION_PATTERNS: ClassVar[list[tuple[str, re.Pattern]]] = [
        (
            "instruction_override",
            re.compile(
                r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions|rules|constraints)",
                re.IGNORECASE,
            ),
        ),
        (
            "role_manipulation",
            re.compile(
                r"(?:you\s+are|act\s+as|pretend\s+to\s+be|your\s+new\s+role)", re.IGNORECASE
            ),
        ),
        (
            "system_prompt_extraction",
            re.compile(
                r"(?:show|reveal|display|print|output)\s+(?:(?:your|the)\s+)?(?:system\s+)?(?:prompt|instructions|rules)",
                re.IGNORECASE,
            ),
        ),
        (
            "delimiter_injection",
            re.compile(r"(?:`{3}|<\/?system>|<\/?user>|\[INST\]|\[\/INST\])", re.IGNORECASE),
        ),
        (
            "authority_fabrication",
            re.compile(
                r"(?:i\s+am\s+(?:an?\s+)?admin|authorized\s+to|override\s+(?:policy|security))",
                re.IGNORECASE,
            ),
        ),
    ]

    def detect(self, content: str, model_armor_available: bool = False) -> list[PolicyFinding]:
        findings: list[PolicyFinding] = []
        if not isinstance(content, str):
            return findings

        for name, pattern in self.INJECTION_PATTERNS:
            if pattern.search(content):
                findings.append(
                    PolicyFinding(
                        finding_id=f"inj-{uuid4()}",
                        category=PolicyFindingCategory.PROMPT_INJECTION_INDICATOR,
                        severity=PolicyFindingSeverity.BLOCK,
                        description=f"Deterministic injection indicator detected: {name}",
                        source="DETERMINISTIC_CODE",
                        is_deterministic=True,
                    )
                )

        if not model_armor_available:
            findings.append(
                PolicyFinding(
                    finding_id=f"ma-{uuid4()}",
                    category=PolicyFindingCategory.MODEL_ARMOR_RESULT,
                    severity=PolicyFindingSeverity.WARN,
                    description="Model Armor not run",
                    source="DETERMINISTIC_CODE",
                    is_deterministic=True,
                )
            )

        return findings

    def quarantine_suspicious(self, content: str, findings: list[PolicyFinding]) -> str:
        if not findings or not isinstance(content, str):
            return str(content) if content is not None else ""

        sanitized = content
        for _, pattern in self.INJECTION_PATTERNS:
            sanitized = pattern.sub("[QUARANTINED_CONTENT]", sanitized)

        return sanitized


class PolicyExplanationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    change_id: str
    locked_findings: tuple[PolicyFinding, ...]


class PolicyExplanation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    change_id: str
    explanation_text: str
    authority: str = "GEMINI_SEMANTIC_JUDGMENT"
    original_finding_count: int


def generate_policy_explanation(request: PolicyExplanationRequest) -> PolicyExplanation:
    count = len(request.locked_findings)
    if count == 0:
        text = "No policy violations found."
    else:
        text = (
            f"Found {count} deterministic policy finding(s). These cannot be overridden by model."
        )

    return PolicyExplanation(
        change_id=request.change_id, explanation_text=text, original_finding_count=count
    )


class BoundPolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    decision_id: str
    evaluation_result: PolicyEvaluationResult
    bound_event_id: str | None = None
    bound_state: str | None = None
    bound_rehearsal_id: str | None = None
    bound_passport_id: str | None = None
    causal_identifiers: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    created_at: UtcDateTime
