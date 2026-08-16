"""ChangeMesh prompt-injection and unverified-input quarantine engine.

P-11.04: Detects adversarial injection attempts, suspicious repository
text, and hostile instruction overrides in candidate memory payloads,
quarantining them before they can enter agent context or become authoritative.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from domain.contracts.memory import MemoryRecord, MemoryTrustStatus


class PromptInjectionDetectedError(ValueError):
    """Raised when an adversarial instruction or prompt injection attempt is detected."""

    def __init__(self, message: str, pattern_name: str = "", matched_snippet: str = "") -> None:
        super().__init__(message)
        self.pattern_name = pattern_name
        self.matched_snippet = matched_snippet


_INJECTION_PATTERNS = [
    (
        "IGNORE_INSTRUCTIONS",
        re.compile(
            r"\b(?:ignore|disregard|forget|bypass)\s+(?:all\s+)?(?:previous|prior|above|system)?\s*(?:instructions|prompts|rules|constraints)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "SYSTEM_PROMPT_OVERRIDE",
        re.compile(
            r"\b(?:system\s+prompt\s+override|override\s+system\s+prompt|new\s+system\s+instruction)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "JAILBREAK_ROLEPLAY",
        re.compile(
            r"\b(?:you\s+are\s+now(?:\s+in)?|act\s+as|pretend\s+to\s+be|switch\s+to)\s+(?:DAN|developer\s+mode|unrestricted|jailbroken|root|god\s+mode)\b|\b(?:developer\s+mode|jailbreak\s+mode|unrestricted\s+mode)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "DELIMITER_HIJACK",
        re.compile(
            r"(?:<{3,}\s*system\s*>{3,}|\[{3,}\s*SYSTEM\s*\]{3,}|###\s*SYSTEM\s*PROMPT)",
            re.IGNORECASE,
        ),
    ),
    (
        "AUTHORITY_FABRICATION",
        re.compile(
            r"\b(?:human\s+approval\s+granted\s+automatically|skip\s+reversibility\s+gate|bypass\s+policy\s+guardian)\b",
            re.IGNORECASE,
        ),
    ),
]


class MemoryQuarantineEngine:
    """Scans and quarantines untrusted memory content."""

    @classmethod
    def scan_content(cls, content: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Scan candidate memory content for injection patterns.

        Returns:
            (is_safe, pattern_name, matched_snippet)
        """
        if not content:
            return True, None, None

        for name, pattern in _INJECTION_PATTERNS:
            match = pattern.search(content)
            if match:
                snippet = match.group(0)
                return False, name, snippet

        return True, None, None

    @classmethod
    def quarantine_if_hostile(cls, record: MemoryRecord) -> MemoryRecord:
        """Scan memory record and transition to QUARANTINED if hostile patterns found."""
        is_safe, pattern_name, snippet = cls.scan_content(record.content)
        if not is_safe:
            reason = f"Adversarial prompt injection pattern [{pattern_name}] detected: '{snippet}'"
            return record.model_copy(
                update={
                    "is_quarantined": True,
                    "trust_status": MemoryTrustStatus.QUARANTINED,
                    "quarantine_reason": reason,
                }
            )
        return record
