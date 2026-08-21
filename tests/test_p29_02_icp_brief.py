"""ChangeMesh P-29.02 — Ideal Customer Profile (ICP) and Commercial Problem Verification Suite.

Acceptance criteria from master plan:
  - Problem specific/budget-bearing; no invented traction.
  - Verification that ICP brief identifies specific buyer persona, budget-bearing problem,
    and clear enterprise value proposition.
  - Verification that document contains explicit honest non-traction disclosures.

Required evidence: ICP brief (docs/P-29.02_IDEAL_CUSTOMER_PROFILE_BRIEF.md).
Mandatory documentation sync: Devpost future.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ICP_PATH = REPO_ROOT / "docs" / "P-29.02_IDEAL_CUSTOMER_PROFILE_BRIEF.md"


class TestIdealCustomerProfileBrief:
    """Verify ICP definition, commercial problem scope, and honest disclosures."""

    def test_icp_brief_exists_and_defines_personas(self):
        """ICP brief must define specific buyer personas and target verticals."""
        assert ICP_PATH.is_file(), f"Missing ICP brief: {ICP_PATH}"
        text = ICP_PATH.read_text(encoding="utf-8")

        assert "VP of Platform Engineering" in text
        assert "FinTech" in text or "B2B SaaS" in text
        assert "Budget Authority" in text

    def test_budget_bearing_problem_identified(self):
        """Brief must articulate downtime, schema drift, and cross-repo blindspots."""
        text = ICP_PATH.read_text(encoding="utf-8")

        assert "Schema drift" in text
        assert "ShadowLab" in text
        assert "Proof-Carrying" in text or "Evidence" in text

    def test_honest_traction_boundary(self):
        """Document must explicitly disclaim fabricated logos or commercial traction."""
        text = ICP_PATH.read_text(encoding="utf-8")

        assert "Zero Invented Traction" in text
        assert "competition MVP" in text or "developer preview" in text
