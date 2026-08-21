"""ChangeMesh P-29.03 — Deployment and Privacy Models Architecture Decision Suite.

Acceptance criteria from master plan:
  - Tradeoffs/security boundaries explicit.
  - Verification that ADR-008 defines Model A (Hosted SaaS), Model B (Hybrid VPC Runner),
    and Model C (Fully Private Air-Gapped).
  - Verification of zero-ingress outbound connection model and fail-closed boundaries.

Required evidence: ADR (docs/P-29.03_DEPLOYMENT_PRIVACY_MODELS_ADR.md).
Mandatory documentation sync: Architecture.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ADR_PATH = REPO_ROOT / "docs" / "P-29.03_DEPLOYMENT_PRIVACY_MODELS_ADR.md"


class TestDeploymentPrivacyModelsADR:
    """Verify deployment privacy models, security boundaries, and tradeoffs."""

    def test_adr_defines_three_deployment_tiers(self):
        """ADR must explicitly define Models A, B, and C."""
        assert ADR_PATH.is_file(), f"Missing ADR document: {ADR_PATH}"
        text = ADR_PATH.read_text(encoding="utf-8")

        assert "Model A: Multi-Tenant Hosted SaaS" in text
        assert "Model B: Hybrid VPC Runner" in text
        assert "Model C: Fully Private Air-Gapped" in text

    def test_security_boundaries_and_zero_ingress(self):
        """Zero-ingress customer VPC model and payload minimization must be documented."""
        text = ADR_PATH.read_text(encoding="utf-8")

        assert "Zero Ingress to Customer VPC" in text
        assert "Payload Minimization" in text
        assert "Fail-Closed Isolation" in text

    def test_compliance_and_data_custody_matrix(self):
        """Data custody and compliance mapping must be articulated."""
        text = ADR_PATH.read_text(encoding="utf-8")

        assert "Zero custody" in text
        assert "SOC 2" in text
        assert "gemini-3.6-flash" in text
