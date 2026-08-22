"""ChangeMesh P-29.05 — Post-Competition 90-Day Roadmap Verification Suite.

Acceptance criteria from master plan:
  - Competition plan remains achievable; future work separate.
  - Verification that 90-day roadmap defines explicit 3-phase milestones
    (Days 1-30, Days 31-60, Days 61-90).
  - Verification of strict separation between competition MVP and post-freeze commercial roadmap.

Required evidence: Roadmap (docs/P-29.05_90_DAY_ROADMAP.md).
Mandatory documentation sync: README.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ROADMAP_PATH = REPO_ROOT / "docs" / "P-29.05_90_DAY_ROADMAP.md"


class TestPostCompetitionRoadmap:
    """Verify 90-day post-competition roadmap integrity and boundaries."""

    def test_roadmap_exists_and_defines_three_phases(self):
        """Roadmap document must define 30, 60, and 90 day milestones."""
        assert ROADMAP_PATH.is_file(), f"Missing roadmap document: {ROADMAP_PATH}"
        text = ROADMAP_PATH.read_text(encoding="utf-8")

        assert "Days 1–30" in text or "Days 1-30" in text
        assert "Days 31–60" in text or "Days 31-60" in text
        assert "Days 61–90" in text or "Days 61-90" in text

    def test_commercial_deliverables_specified(self):
        """Roadmap must articulate concrete commercial deliverables."""
        text = ROADMAP_PATH.read_text(encoding="utf-8")

        assert "VPC Runner" in text or "Helm" in text
        assert "SOC 2" in text or "compliance" in text.lower()
        assert "Marketplace" in text or "Plugin" in text

    def test_clean_separation_from_competition_mvp(self):
        """Roadmap must explicitly declare competition MVP separation."""
        text = ROADMAP_PATH.read_text(encoding="utf-8")

        assert "Separation of Concerns" in text
        assert "Competition MVP" in text or "hackathon code freeze" in text
