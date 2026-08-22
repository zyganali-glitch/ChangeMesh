"""ChangeMesh P-30.01 — Pitch Narratives and Claim Audit Verification Suite.

Acceptance criteria from master plan:
  - Narratives consistent/evidence-backed.
  - Verification that 10s, 30s, and 2m pitch narratives exist
    and match verified repository terminology.
  - Verification of grounded claim matrix referencing existing passing artifacts.

Required evidence: Claim audit (docs/P-30.01_PITCH_NARRATIVES_CLAIM_AUDIT.md).
Mandatory documentation sync: README, judge start, Devpost.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
NARRATIVES_PATH = REPO_ROOT / "docs" / "P-30.01_PITCH_NARRATIVES_CLAIM_AUDIT.md"


class TestPitchNarrativesAndClaims:
    """Verify 10s, 30s, and 2m pitch narratives and claim matrix integrity."""

    def test_narratives_document_exists_and_defines_three_pitches(self):
        """Document must define 10-second, 30-second, and 2-minute narratives."""
        assert NARRATIVES_PATH.is_file(), f"Missing narratives document: {NARRATIVES_PATH}"
        text = NARRATIVES_PATH.read_text(encoding="utf-8")

        assert "1. 10-Second Hook Narrative" in text
        assert "2. 30-Second Competition Pitch Narrative" in text
        assert "3. 2-Minute Technical & Judge Walkthrough" in text

    def test_key_architectural_terms_in_narratives(self):
        """Narratives must use verified terms: ShadowLab, Gemini 3.6 Flash, 4-lane, Cloud Run."""
        text = NARRATIVES_PATH.read_text(encoding="utf-8")

        assert "ShadowLab" in text
        assert "gemini-3.6-flash" in text or "Gemini 3.6 Flash" in text
        assert "Cloud Run" in text
        assert "europe-west3" in text
        assert "OCC CAS" in text or "Optimistic Concurrency" in text

    def test_claim_verification_matrix_links_valid_files(self):
        """All claims in the matrix must point to real existing files."""
        text = NARRATIVES_PATH.read_text(encoding="utf-8")
        assert "Grounded Claim Verification Matrix" in text

        for line in text.splitlines():
            if "|" in line and (
                "src/" in line or "docs/" in line or "events/" in line or "tests/" in line
            ):
                parts = [p.strip().strip("`") for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    file_ref = parts[1]
                    target_file = REPO_ROOT / file_ref
                    assert target_file.exists(), f"Claim references non-existent file: {file_ref}"
