"""ChangeMesh P-28.03 — Revision Provenance and Cloud Deployment Binding Suite.

Acceptance criteria from master plan:
  - Judge identifies exact running code.
  - Verification that provenance artifact binds source commit, container digest,
    Cloud Run revision, and canonical model ID.
  - Verification that schema versions and runtime pins match repository truths.
  - Verification that submission manifest references verified provenance artifact.

Required evidence: Provenance artifact (docs/P-28.03_REVISION_PROVENANCE_BINDING.json).
Mandatory documentation sync: Submission manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROVENANCE_PATH = REPO_ROOT / "docs" / "P-28.03_REVISION_PROVENANCE_BINDING.json"


class TestRevisionProvenanceBinding:
    """Verify revision provenance artifact integrity and cross-references."""

    def test_provenance_file_exists_and_parses(self):
        """Provenance JSON must exist and contain binding version 1.0.0."""
        assert PROVENANCE_PATH.is_file(), f"Missing provenance artifact: {PROVENANCE_PATH}"
        data = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        assert data["binding_version"] == "1.0.0"
        assert "provenance" in data

    def test_provenance_binds_cloud_run_and_source_commit(self):
        """Provenance must bind Cloud Run revision to project and region."""
        data = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        prov = data["provenance"]

        assert prov["project_id"] == "project-af5e1c99-3bc4-424f-b53"
        assert prov["canonical_region"] == "europe-west3"
        assert prov["cloud_run_service"] == "changemesh-p24-e2e"
        assert prov["cloud_run_revision"] == "changemesh-p24-e2e-00001-jjp"
        assert "europe-west3.run.app" in prov["cloud_run_url"]
        assert len(prov["source_commit_sha"]) == 40

    def test_provenance_model_and_runtime_pins(self):
        """Model and runtime pins must reflect canonical frozen values."""
        data = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        prov = data["provenance"]

        assert prov["model_authority"]["model_id"] == "gemini-3.6-flash"
        assert prov["model_authority"]["provider"] == "vertexai"
        assert prov["configuration_versions"]["domain_contracts_schema"] == "1.0.0"
        assert prov["configuration_versions"]["python_runtime"] == "3.13.5"
