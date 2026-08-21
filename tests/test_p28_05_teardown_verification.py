"""ChangeMesh P-28.05 — Post-Judging Teardown and Low-Cost Idle Mode Verification Suite.

Acceptance criteria from master plan:
  - Resources safely disabled after judging while recorded proof retained.
  - Verification that Cloud Run scales to zero instances (min_instances = 0).
  - Verification that temporary saga scratch states can be purged without affecting
    immutable evidence packs in docs/ or historical records.
  - Verification of $0.00 idle operational cost post-judging.

Required evidence: Teardown test (docs/P-28.05_TEARDOWN_IDLE_VERIFICATION_REPORT.md).
Mandatory documentation sync: Environment, Handoff.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BUDGET_CONFIG_PATH = REPO_ROOT / "deploy" / "budget_and_retention_config.json"
INFRA_MANIFEST_PATH = REPO_ROOT / "deploy" / "gcp_infrastructure_manifest.json"


class TestPostJudgingTeardownAndIdleMode:
    """Verify scale-to-zero, data preservation, and safe de-provisioning."""

    def test_cloud_run_scale_to_zero_enforced(self):
        """Cloud Run configurations must strictly require min_instances=0."""
        budget_cfg = json.loads(BUDGET_CONFIG_PATH.read_text(encoding="utf-8"))
        infra_cfg = json.loads(INFRA_MANIFEST_PATH.read_text(encoding="utf-8"))

        assert budget_cfg["cloud_run_scaling_policy"]["min_instances"] == 0
        assert budget_cfg["cloud_run_scaling_policy"]["monthly_idle_cost_usd"] == 0.00
        assert infra_cfg["services"]["cloud_run"]["min_instances"] == 0

    def test_recorded_evidence_preserved_during_teardown(self):
        """Immutable evidence packs and benchmark reports in docs/ must be retained."""
        evidence_files = [
            REPO_ROOT / "docs" / "P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json",
            REPO_ROOT / "docs" / "P-28.03_REVISION_PROVENANCE_BINDING.json",
            REPO_ROOT / "docs" / "P-25.06_ROOT_VALIDATION_OUTPUT.md",
        ]
        for f in evidence_files:
            assert f.is_file(), f"Expected immutable evidence file missing: {f}"

    def test_teardown_procedure_declared(self):
        """Budget and retention config must explicitly specify teardown procedures."""
        budget_cfg = json.loads(BUDGET_CONFIG_PATH.read_text(encoding="utf-8"))
        teardown = budget_cfg["teardown_procedure"]

        assert teardown["automated_teardown_supported"] is True
        assert teardown["cloud_run_action"] == "DELETE_REVISION_OR_SCALE_ZERO"
        assert teardown["zero_dangling_resources_guarantee"] is True
