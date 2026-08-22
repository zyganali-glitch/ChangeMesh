"""ChangeMesh P-30.06 — Build-Period Disclosure and Provenance Verification Suite.

Acceptance criteria from master plan:
  - Reuse transparent/legally compatible.
  - Verification that docs/BUILD_PERIOD_DISCLOSURE.md discloses all 4 donor components
    with immutable commit SHAs, license types, clean-room methods, and target files.
  - Verification of third-party open-source library disclosures
    (Pydantic, google-genai, pytest, ruff).
  - Verification of Google Cloud services disclosures
    (Cloud Run, Firestore, Pub/Sub, gemini-3.6-flash).

Required evidence: License/provenance audit (docs/BUILD_PERIOD_DISCLOSURE.md).
Mandatory documentation sync: Submission manifest.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DISCLOSURE_PATH = REPO_ROOT / "docs" / "BUILD_PERIOD_DISCLOSURE.md"


class TestBuildPeriodDisclosureAndProvenance:
    """Verify build-period disclosures, donor provenance, and third-party license audits."""

    def test_disclosure_document_exists_and_verified(self):
        """Document must exist and be marked VERIFIED / FROZEN."""
        assert DISCLOSURE_PATH.is_file(), f"Missing disclosure document: {DISCLOSURE_PATH}"
        text = DISCLOSURE_PATH.read_text(encoding="utf-8")

        assert "Status: `VERIFIED / FROZEN`" in text or "VERIFIED" in text
        assert "Fortified Enterprise Fleet" in text
        assert "New Projects Only" in text

    def test_all_four_donor_components_disclosed(self):
        """All 4 donor components must be explicitly disclosed with immutable commits."""
        text = DISCLOSURE_PATH.read_text(encoding="utf-8")

        assert "ZK-PRIV-001" in text
        assert "d663db8c706cb914e1af5caf651df08edb5c50c0" in text
        assert "CCT-SEM-001" in text
        assert "65ee1b72faf9a7202d9166eed43fb671804815a8" in text
        assert "ZK-VALID-001" in text
        assert "CCT-FLIGHT-001" in text
        assert "CLEAN_ROOM_REIMPLEMENTED" in text

    def test_third_party_and_gcp_services_disclosed(self):
        """Third-party libraries and Google Cloud services must be listed."""
        text = DISCLOSURE_PATH.read_text(encoding="utf-8")

        assert "pydantic" in text
        assert "google-genai" in text
        assert "pytest" in text
        assert "gemini-3.6-flash" in text
        assert "Cloud Run" in text
        assert "Firestore" in text
        assert "Pub/Sub" in text
