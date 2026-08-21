"""ChangeMesh P-26.05 — Honest Security Limitations & Non-Certification Security Suite.

Acceptance criteria from master plan:
  - No absolute safety/compliance claim.
  - Verification that documentation contains honest disclosures regarding non-certification,
    deterministic code primacy, draft-only restrictions, and simulated cloud isolation.
  - Zero unverified or exaggerated security assertions.

Required evidence: Claim audit (docs/P-26.05_HONEST_SECURITY_LIMITATIONS_REPORT.md).
Mandatory documentation sync: README, Devpost.
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit_security_claims import (
    audit_markdown_claims,
    audit_non_certification_statements,
)

REPO_ROOT = Path(__file__).parent.parent


class TestHonestSecurityLimitationsAndClaims:
    """Verify absence of exaggerated security claims and presence of honest boundaries."""

    def test_no_prohibited_absolute_security_claims_in_docs(self):
        """Markdown documentation must not make unverified absolute security claims."""
        clean, findings = audit_markdown_claims()
        assert clean is True, f"Prohibited claims found in documentation: {findings}"
        assert len(findings) == 0

    def test_explicit_non_certification_disclosures_present(self):
        """Core documentation files must contain explicit non-certification notices."""
        clean, findings = audit_non_certification_statements()
        assert clean is True, f"Missing non-certification statements: {findings}"
        assert len(findings) == 0

    def test_readme_contains_dedicated_limitations_section(self):
        """README.md must contain the Honest Security Limitations section."""
        readme = REPO_ROOT / "README.md"
        content = readme.read_text(encoding="utf-8")
        assert "Honest Security Limitations & Non-Certification Boundary" in content
        assert "Non-Certification Notice" in content
        assert "officially certified substitute" in content
        assert "Deterministic Code Primacy" in content
        assert "Draft-Only Pull Requests" in content
