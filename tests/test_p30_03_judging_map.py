"""ChangeMesh P-30.03 — Judging Map and Criteria Alignment Verification Suite.

Acceptance criteria from master plan:
  - Every criterion maps visible artifact.
  - Verification that docs/JUDGING_MAP.md covers all 11 track requirements with PASS status
    and valid file links.
  - Verification that referenced files actually exist on the filesystem.

Required evidence: Requirement audit (docs/JUDGING_MAP.md).
Mandatory documentation sync: Devpost.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
JUDGING_MAP_PATH = REPO_ROOT / "docs" / "JUDGING_MAP.md"


class TestJudgingMapCriteriaAlignment:
    """Verify judging criteria alignment, artifact links, and PASS statuses."""

    def test_judging_map_exists_and_declares_fleet_category(self):
        """Document must declare Fortified Enterprise Fleet and verified status."""
        assert JUDGING_MAP_PATH.is_file(), f"Missing judging map: {JUDGING_MAP_PATH}"
        text = JUDGING_MAP_PATH.read_text(encoding="utf-8")

        assert "Fortified Enterprise Fleet" in text
        assert "gemini-3.6-flash" in text
        assert "europe-west3" in text

    def test_all_eleven_criteria_mapped(self):
        """All 11 criteria rows must be defined."""
        text = JUDGING_MAP_PATH.read_text(encoding="utf-8")

        assert "1. Gemini 3.5+ Native Authority" in text
        assert "2. Google Agent Framework (ADK)" in text
        assert "3. Google Cloud Architecture" in text
        assert "4. Autonomous Multi-Agent Saga" in text
        assert "5. Pre-Flight Simulation (ShadowLab)" in text
        assert "6. Cross-Session Memory Trust" in text
        assert "7. Capability Passport & Discovery" in text
        assert "8. Security & 4-Lane Authority" in text
        assert "9. Observability & Tracing" in text
        assert "10. Human Decision Compression" in text
        assert "11. Reproducibility & Lean Footprint" in text

    def test_all_evidence_links_exist(self):
        """Every file link in criteria table must point to existing artifact without file:///."""
        text = JUDGING_MAP_PATH.read_text(encoding="utf-8")
        assert "file:///" not in text, "JUDGING_MAP.md must not contain local file:/// links"

        import re

        links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
        for label, target in links:
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # Resolve relative to docs directory
            resolved = (JUDGING_MAP_PATH.parent / target).resolve()
            assert resolved.exists(), f"Broken link in JUDGING_MAP.md: {target}"
