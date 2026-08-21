#!/usr/bin/env python3
"""ChangeMesh Honest Security Limitations and Non-Certification Claim Auditor (P-26.05).

Performs static analysis across repository markdown and documentation files:
1. Asserts absence of absolute, exaggerated, or misleading security claims
   (e.g., "100% secure", "unhackable", "guaranteed zero bugs", "SOC2 certified", "HIPAA certified").
2. Asserts presence of honest non-certification boundaries and limitation disclosures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Exaggerated or prohibited claim regexes
PROHIBITED_CLAIM_PATTERNS = [
    r"\b100%\s+secure\b",
    r"\bunhackable\b",
    r"\bcompletely\s+safe\b",
    r"\bzero\s+vulnerabilit(?:y|ies)\s+guaranteed\b",
    r"\bfully\s+certified\s+for\s+(?:soc2|hipaa|fedramp|pci)\b",
    r"\bofficially\s+soc2\s+certified\b",
    r"\bofficially\s+hipaa\s+certified\b",
]

DOC_EXTENSIONS = {".md", ".rst", ".txt"}


def audit_markdown_claims() -> tuple[bool, list[str]]:
    """Scan all tracked markdown files for prohibited absolute claims."""
    findings: list[str] = []

    # Files to inspect
    for p in REPO_ROOT.rglob("*.md"):
        # Skip .git or venvs
        if ".git" in p.parts or ".venv" in p.parts:
            continue

        try:
            content = p.read_text(encoding="utf-8")
        except Exception as e:
            findings.append(f"Failed to read {p.relative_to(REPO_ROOT)}: {e}")
            continue

        for pattern in PROHIBITED_CLAIM_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for m in matches:
                # Check if it's explicitly discussing a non-goal, prohibited claim, or lesson
                snippet = content[max(0, m.start() - 40) : min(len(content), m.end() + 40)]
                # Allow if negated, quoted as an example,
                # or marked as non-goal / limitation / audit pattern
                lower_snippet = snippet.lower()
                if (
                    "not claim" in lower_snippet
                    or "never" in lower_snippet
                    or "prohibited" in lower_snippet
                    or "forbidden" in lower_snippet
                    or "absence of" in lower_snippet
                    or "e.g." in lower_snippet
                    or "exaggerated" in lower_snippet
                    or "disallowed" in lower_snippet
                    or '"' in snippet
                    or "'" in snippet
                    or "`" in snippet
                ):
                    continue
                findings.append(
                    f"{p.relative_to(REPO_ROOT)}: Match found for "
                    f"prohibited claim pattern: {pattern!r}"
                )

    is_clean = len(findings) == 0
    return is_clean, findings


def audit_non_certification_statements() -> tuple[bool, list[str]]:
    """Verify that core documentation contains explicit non-certification notices."""
    required_files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "THREAT_MODEL.md",
        REPO_ROOT / "docs" / "NON_GOALS.md",
    ]
    findings: list[str] = []

    for f in required_files:
        if not f.is_file():
            findings.append(f"Required document missing: {f.name}")
            continue
        text = f.read_text(encoding="utf-8").lower()
        if "certif" not in text and "limitation" not in text and "non-goal" not in text:
            findings.append(f"{f.name} missing honest limitation or non-certification notice")

    is_clean = len(findings) == 0
    return is_clean, findings


def main() -> int:
    print("=" * 80)
    print(" CHANGEMESH -- HONEST SECURITY LIMITATIONS & CLAIM AUDITOR (P-26.05)")
    print("=" * 80)

    clean_claims, claim_findings = audit_markdown_claims()
    clean_notices, notice_findings = audit_non_certification_statements()

    print(f" Prohibited Claims Scan       : {'PASS' if clean_claims else 'FAIL'}")
    for f in claim_findings:
        print(f"   [!] {f}")

    print(f" Non-Certification Disclosures: {'PASS' if clean_notices else 'FAIL'}")
    for f in notice_findings:
        print(f"   [!] {f}")

    print("=" * 80)

    if clean_claims and clean_notices:
        print(" VERDICT: HONEST SECURITY CLAIMS VERIFIED [PASS]")
        return 0
    else:
        print(" VERDICT: CLAIM AUDIT FAILED [FAIL]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
