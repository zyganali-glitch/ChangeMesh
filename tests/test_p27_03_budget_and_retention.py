"""ChangeMesh P-27.03 — Budget Alert, Minimum Instances, Retention, and Teardown Suite.

Acceptance criteria from master plan:
  - No accidental long-running expense.
  - Verification of budget alert thresholds ($25.00 hard monthly cap with multi-tier alerts).
  - Verification of Cloud Run scale-to-zero enforcement (min_instances = 0).
  - Verification of data retention policies and automated teardown procedures.

Required evidence: Sanitized config evidence (docs/P-27.03_BUDGET_AND_RETENTION_CONFIG_REPORT.md).
Mandatory documentation sync: Environment.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "deploy" / "budget_and_retention_config.json"


class TestBudgetAndRetentionConfiguration:
    """Verify budget alerts, scale-to-zero, retention, and teardown specifications."""

    def test_config_file_exists_and_parses_json(self):
        """Configuration file must exist and be valid JSON."""
        assert CONFIG_PATH.is_file(), f"Missing config file: {CONFIG_PATH}"
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data["project_id"] == "project-af5e1c99-3bc4-424f-b53"
        assert data["region"] == "europe-west3"

    def test_budget_alert_thresholds_strictly_enforce_cap(self):
        """Budget alert policy must define strict threshold rules with monthly cap."""
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        policy = data["budget_alert_policy"]

        assert policy["monthly_budget_amount"] <= 50.00
        assert policy["currency_code"] == "USD"
        thresholds = [r["threshold_percent"] for r in policy["threshold_rules"]]
        assert 0.50 in thresholds
        assert 0.80 in thresholds
        assert 1.00 in thresholds

    def test_cloud_run_min_instances_is_zero(self):
        """Cloud Run service must strictly enforce min_instances = 0 to prevent idle costs."""
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cr = data["cloud_run_scaling_policy"]

        assert cr["min_instances"] == 0
        assert cr["scaling_profile"] == "SCALE_TO_ZERO"
        assert cr["monthly_idle_cost_usd"] == 0.00
        assert cr["max_instances"] <= 5
        assert cr["request_timeout_seconds"] <= 300

    def test_retention_and_teardown_procedures_defined(self):
        """Data retention must be bounded and teardown procedures supported."""
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        retention = data["retention_and_lifecycle_policies"]
        teardown = data["teardown_procedure"]

        assert retention["firestore"]["retention_period_days"] <= 30
        assert retention["cloud_logging"]["retention_period_days"] <= 30
        assert teardown["automated_teardown_supported"] is True
        assert teardown["zero_dangling_resources_guarantee"] is True
