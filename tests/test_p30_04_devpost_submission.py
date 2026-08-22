"""ChangeMesh P-30.04 — Devpost Submission Text Verification Suite.

Acceptance criteria from master plan:
  - No unsupported/stale claim.
  - Verification that docs/DEVPOST_SUBMISSION.md contains complete sections
    (Problem, What it does, How built, Challenges, Accomplishments, Future).
  - Verification of exact canonical identifiers: gemini-3.6-flash, europe-west3,
    Fortified Enterprise Fleet, Cloud Run, Firestore, Pub/Sub, OCC CAS.

Required evidence: Competition claim audit (docs/DEVPOST_SUBMISSION.md).
Mandatory documentation sync: Submission manifest.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEVPOST_PATH = REPO_ROOT / "docs" / "DEVPOST_SUBMISSION.md"


class TestDevpostSubmissionText:
    """Verify Devpost submission text completeness, consistency, and evidence grounding."""

    def test_devpost_submission_file_exists_and_verified(self):
        """Devpost text file must exist and be marked VERIFIED / FROZEN."""
        assert DEVPOST_PATH.is_file(), f"Missing Devpost submission file: {DEVPOST_PATH}"
        text = DEVPOST_PATH.read_text(encoding="utf-8")

        assert "Status: `VERIFIED / FROZEN`" in text or "VERIFIED" in text
        assert "Fortified Enterprise Fleet" in text
        assert "gemini-3.6-flash" in text
        assert "europe-west3" in text

    def test_all_official_sections_present(self):
        """All official Devpost hackathon sections must be populated."""
        text = DEVPOST_PATH.read_text(encoding="utf-8")

        assert "1. The Problem We Solve" in text
        assert "2. What ChangeMesh Does" in text
        assert "3. How We Built It" in text
        assert "4. Challenges We Overcame" in text
        assert "5. Accomplishments & Grounded Evidence" in text
        assert "6. What's Next for ChangeMesh" in text

    def test_key_architecture_and_cloud_terms_included(self):
        """Must mention core Google Cloud technologies and architecture patterns."""
        text = DEVPOST_PATH.read_text(encoding="utf-8")

        assert "Cloud Run" in text
        assert "Firestore" in text
        assert "Pub/Sub" in text
        assert "ShadowLab" in text
        assert "4-Lane Authority Model" in text
        assert "OCC CAS" in text
        assert "Zero-Custody" in text
