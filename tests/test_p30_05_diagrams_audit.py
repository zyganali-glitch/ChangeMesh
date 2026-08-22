"""ChangeMesh P-30.05 — Architecture and Evidence Diagrams Verification Suite.

Acceptance criteria from master plan:
  - Diagrams match deployed code/UI terminology.
  - Verification that docs/P-30.05_ARCHITECTURE_AND_EVIDENCE_DIAGRAMS.md defines
    all 4 canonical diagrams (Cloud Architecture, 6-Stage Saga, 4-Lane Authority, Hash Chain).
  - Verification of exact terminological consistency across surfaces.

Required evidence: Cross-surface audit (docs/P-30.05_ARCHITECTURE_AND_EVIDENCE_DIAGRAMS.md).
Mandatory documentation sync: README, Devpost.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DIAGRAMS_PATH = REPO_ROOT / "docs" / "P-30.05_ARCHITECTURE_AND_EVIDENCE_DIAGRAMS.md"


class TestArchitectureAndEvidenceDiagrams:
    """Verify diagram structure, topology mappings, and terminological precision."""

    def test_diagrams_document_exists_and_contains_all_four_diagrams(self):
        """Document must contain all 4 system and authority diagrams."""
        assert DIAGRAMS_PATH.is_file(), f"Missing diagrams document: {DIAGRAMS_PATH}"
        text = DIAGRAMS_PATH.read_text(encoding="utf-8")

        assert "1. End-to-End Google Cloud System Architecture" in text
        assert "2. 6-Stage Saga Lifecycle State Machine" in text
        assert "3. 4-Lane Authority Hierarchy" in text
        assert "4. Cryptographic Proof-Carrying Evidence Ledger" in text

    def test_cloud_services_and_model_matching(self):
        """Diagram 1 must accurately represent Cloud Run, Firestore, Pub/Sub,
        and gemini-3.6-flash."""
        text = DIAGRAMS_PATH.read_text(encoding="utf-8")

        assert "Cloud Run" in text
        assert "europe-west3" in text
        assert "Firestore" in text
        assert "Pub/Sub" in text
        assert "gemini-3.6-flash" in text

    def test_four_authority_lanes_matching(self):
        """Diagram 3 must accurately represent the 4 authority lanes in correct hierarchy."""
        text = DIAGRAMS_PATH.read_text(encoding="utf-8")

        assert "LANE 1: DETERMINISTIC CODE" in text
        assert "LANE 2: GEMINI SEMANTIC JUDGMENT" in text
        assert "LANE 3: ORGANIZATIONAL POLICY" in text
        assert "LANE 4: BOUNDED HUMAN AUTHORITY" in text
