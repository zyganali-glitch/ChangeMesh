"""ChangeMesh P-28.01 — GCP Infrastructure and Deployment Configuration Security Suite.

Acceptance criteria from master plan:
  - Deployment reproducible/region-consistent.
  - Verification that GCP infrastructure manifest is valid and covers Cloud Run,
    Firestore, Pub/Sub, and IAM.
  - Verification that Cloud Run service specifies europe-west3 and canonical model gemini-3.6-flash.
  - Verification that least-privilege IAM roles are strictly declared.

Required evidence: Config validation (docs/P-28.01_INFRASTRUCTURE_DEPLOYMENT_CONFIG_REPORT.md).
Mandatory documentation sync: Architecture, Environment.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "deploy" / "gcp_infrastructure_manifest.json"


class TestGCPInfrastructureConfiguration:
    """Verify GCP deployment manifest, region consistency, and least privilege IAM."""

    def test_infrastructure_manifest_parses_json(self):
        """Manifest must exist and contain valid project metadata."""
        assert MANIFEST_PATH.is_file(), f"Missing manifest: {MANIFEST_PATH}"
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert data["project_id"] == "project-af5e1c99-3bc4-424f-b53"
        assert data["canonical_region"] == "europe-west3"
        assert data["canonical_model_id"] == "gemini-3.6-flash"

    def test_cloud_run_configuration_consistency(self):
        """Cloud Run config must specify scale-to-zero, port 8080, and correct environment."""
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cr = data["services"]["cloud_run"]
        assert cr["min_instances"] == 0
        assert cr["port"] == 8080
        assert cr["region"] == "europe-west3"
        assert cr["environment_variables"]["GEMINI_MODEL"] == "gemini-3.6-flash"

    def test_firestore_and_pubsub_topology(self):
        """Firestore and Pub/Sub resources must match project topic definitions."""
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        fs = data["services"]["firestore"]
        ps = data["services"]["pubsub"]

        assert fs["mode"] == "FIRESTORE_NATIVE"
        assert fs["location"] == "europe-west3"
        assert len(ps["topics"]) >= 2
        assert len(ps["subscriptions"]) >= 1

    def test_least_privilege_iam_roles(self):
        """IAM roles must be minimal and scoped only to needed capabilities."""
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        roles = set(data["services"]["iam"]["roles"])

        # Invariant checks: Must have necessary roles, but no admin/owner roles
        assert "roles/aiplatform.user" in roles
        assert "roles/datastore.user" in roles
        assert "roles/pubsub.publisher" in roles
        assert "roles/owner" not in roles
        assert "roles/editor" not in roles
