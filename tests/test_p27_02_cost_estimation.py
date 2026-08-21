"""ChangeMesh P-27.02 — Token and Cloud Cost Estimation Security and Economics Suite.

Acceptance criteria from master plan:
  - Expected demo/idle cost documented.
  - Verification that per-saga Gemini 3.6 Flash token cost is under $0.01 (< 1 cent per run).
  - Verification that scale-to-zero serverless architecture incurs $0.00 / month idle cost.
  - Verification of Firestore and Pub/Sub free-tier alignment.

Required evidence: Cost report (docs/P-27.02_COST_AND_TOKEN_ESTIMATION_REPORT.md).
Mandatory documentation sync: README/Devpost.
"""

from __future__ import annotations

from scripts.estimate_cost import (
    calculate_cloud_infrastructure_cost,
    calculate_saga_token_cost,
)


class TestTokenAndCostEstimation:
    """Verify unit economics, token consumption, and idle cloud costs."""

    def test_saga_gemini_cost_under_one_cent(self):
        """A complete multi-agent change saga must cost less than $0.005 in Gemini tokens."""
        tokens = calculate_saga_token_cost()
        assert tokens["total_tokens"] < 10_000
        assert tokens["total_gemini_cost_usd"] < 0.005
        assert tokens["total_gemini_cost_usd"] > 0.0

    def test_serverless_idle_cost_is_zero(self):
        """Monthly idle infrastructure cost must be strictly $0.00."""
        infra = calculate_cloud_infrastructure_cost()
        assert infra["total_idle_cost_monthly_usd"] == 0.0
        assert infra["cloud_run"]["min_instances"] == 0
        assert infra["cloud_run"]["scale_to_zero"] is True

    def test_firestore_and_pubsub_within_free_tier(self):
        """Demo operations must fit completely within serverless free tier allowances."""
        infra = calculate_cloud_infrastructure_cost()
        assert infra["firestore"]["free_tier_covered"] is True
        assert infra["pubsub"]["free_tier_covered"] is True
