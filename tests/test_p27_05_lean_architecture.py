"""ChangeMesh P-27.05 — Lean Architecture, Waste Removal, and Cost Comparison Suite.

Acceptance criteria from master plan:
  - No wasteful MVP architecture.
  - Verification of zero Node.js/npm dependencies and zero frontend build pipelines.
  - Verification of push-based event architecture over wasteful polling loops.
  - Verification of single canonical Gemini model without multi-vendor client sprawl.
  - Verification of scale-to-zero serverless footprint.

Required evidence: Diff/cost comparison (docs/P-27.05_LEAN_ARCHITECTURE_AND_COST_COMPARISON.md).
Mandatory documentation sync: Architecture.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


class TestLeanArchitectureAndWasteElimination:
    """Verify lean architecture invariants, absence of bloat, and cost efficiency."""

    def test_zero_node_and_npm_footprint(self):
        """Repository must contain zero package.json, node_modules, or JS build configs."""
        package_json = list(REPO_ROOT.rglob("package.json"))
        node_modules = list(REPO_ROOT.rglob("node_modules"))
        webpack_config = list(REPO_ROOT.rglob("webpack.config.js"))
        vite_config = list(REPO_ROOT.rglob("vite.config.js"))

        assert len(package_json) == 0, f"Found unexpected package.json: {package_json}"
        assert len(node_modules) == 0, f"Found unexpected node_modules: {node_modules}"
        assert len(webpack_config) == 0, f"Found unexpected webpack: {webpack_config}"
        assert len(vite_config) == 0, f"Found unexpected vite: {vite_config}"

    def test_single_canonical_model_governance(self):
        """Client must strictly enforce exactly gemini-3.6-flash without multi-model drift."""
        from src.core.gemini_client import CANONICAL_MODEL_ID

        assert CANONICAL_MODEL_ID == "gemini-3.6-flash"

    def test_lean_dependency_tree(self):
        """pyproject.toml must not include heavyweight or unneeded frameworks."""
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        # Invariant checks: No torch, no tensorflow, no langchain monoliths, no legacy vertexai
        assert "torch" not in pyproject
        assert "tensorflow" not in pyproject
        assert "langchain" not in pyproject
        assert "google-cloud-aiplatform" not in pyproject  # using google-genai instead
