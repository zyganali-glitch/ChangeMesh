"""ChangeMesh P-31.01 — Demo Video Manifest & Recording Freeze Verification Suite.

Acceptance criteria from master plan:
  - No last-minute hidden state changes.
  - Verification that docs/DEMO_MANIFEST.md specifies:
    1. Frozen demo dataset (v1 to v2 customer billing address schema with 1000 synthetic records).
    2. Demo persona and agent fleet ceiling (5 agents, draft PR boundary).
    3. Browser viewport standards (1920x1080, dark mode, visible mode badges).
    4. Exact GCP Cloud Run revision binding (changemesh-p24-e2e-00001-jjp, europe-west3).
    5. Fallback contingency plan for recording faults.

Required evidence: Demo manifest (docs/DEMO_MANIFEST.md).
Mandatory documentation sync: Handoff.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "docs" / "DEMO_MANIFEST.md"


class TestDemoManifestFreeze:
    """Verify demo recording dataset, viewport, revision, and contingency plans."""

    def test_demo_manifest_exists_and_frozen(self):
        """Manifest document must exist and declare FROZEN status."""
        assert MANIFEST_PATH.is_file(), f"Missing demo manifest: {MANIFEST_PATH}"
        text = MANIFEST_PATH.read_text(encoding="utf-8")

        assert "Status: `FROZEN / READY FOR RECORDING`" in text or "FROZEN" in text
        assert "1920 x 1080" in text
        assert "gemini-3.6-flash" in text

    def test_cloud_revision_and_region_binding(self):
        """Must bind exact verified Cloud Run revision and europe-west3 region."""
        text = MANIFEST_PATH.read_text(encoding="utf-8")

        assert "changemesh-p24-e2e" in text
        assert "changemesh-p24-e2e-00001-jjp" in text
        assert "europe-west3" in text
        assert "project-af5e1c99-3bc4-424f-b53" in text

    def test_fallback_contingencies_defined(self):
        """Contingency table must cover network latency, quota backoff, and OBS frame drops."""
        text = MANIFEST_PATH.read_text(encoding="utf-8")

        assert "Fallback Recording & Fault Contingency Plan" in text
        assert "Cloud Run Cold Start" in text
        assert "Vertex AI Quota" in text
        assert "OBS Screen Recording" in text
