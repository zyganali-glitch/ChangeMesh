"""ChangeMesh P-30.02 — Judge Start Here Fresh-Reader Verification Suite.

Acceptance criteria from master plan:
  - Judge verifies value without entire repo.
  - Verification that docs/JUDGE_START_HERE.md exists and provides fast evaluation paths:
    (60-second Cloud Run curl track, 3-minute local pytest track).
  - Verification of valid artifact references and canonical category / model identifiers.

Required evidence: Fresh-reader test (docs/JUDGE_START_HERE.md).
Mandatory documentation sync: README links.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
JUDGE_DOC_PATH = REPO_ROOT / "docs" / "JUDGE_START_HERE.md"


class TestJudgeStartHereFreshReader:
    """Verify judge quick-start instructions, endpoints, and artifact links."""

    def test_judge_start_here_file_exists_and_declares_category(self):
        """Document must declare Fortified Enterprise Fleet and gemini-3.6-flash."""
        assert JUDGE_DOC_PATH.is_file(), f"Missing judge guide: {JUDGE_DOC_PATH}"
        text = JUDGE_DOC_PATH.read_text(encoding="utf-8")

        assert "Fortified Enterprise Fleet" in text
        assert "gemini-3.6-flash" in text
        assert "europe-west3" in text

    def test_fast_cloud_evaluation_commands_present(self):
        """Document must provide exact curl commands for live Cloud Run testing."""
        text = JUDGE_DOC_PATH.read_text(encoding="utf-8")

        assert "curl" in text
        assert "/health" in text
        assert "/api/dashboard/snapshot" in text
        assert "/run-e2e" in text
        assert "https://changemesh-p24-e2e" in text

    def test_local_evaluation_and_artifact_table(self):
        """Document must guide local pytest execution and link essential artifacts."""
        text = JUDGE_DOC_PATH.read_text(encoding="utf-8")

        assert "uv run pytest -v" in text
        assert "docs/JUDGING_MAP.md" in text
        assert "docs/SUBMISSION_MANIFEST.md" in text
        assert "docs/P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json" in text
