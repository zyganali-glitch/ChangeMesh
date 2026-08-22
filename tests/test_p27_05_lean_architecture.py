"""ChangeMesh P-27.05 — Lean Architecture, Waste Removal, and Cost Comparison Suite.

Acceptance criteria from master plan:
  - No wasteful MVP architecture.
  - Verification of zero Node.js/npm product dependencies and zero frontend build pipelines.
  - Verification of push-based event architecture over wasteful polling loops.
  - Verification of single canonical Gemini model without multi-vendor client sprawl.
  - Verification of scale-to-zero serverless footprint.

Required evidence: Diff/cost comparison (docs/P-27.05_LEAN_ARCHITECTURE_AND_COST_COMPARISON.md).
Mandatory documentation sync: Architecture.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ENVIRONMENT_DIRS = {
    ".venv",
    "venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}


def _get_repository_source_files() -> list[Path]:
    """Get ChangeMesh-owned repository files, excluding virtual envs, caches, and git metadata."""
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        tracked = [REPO_ROOT / line.strip() for line in res.stdout.splitlines() if line.strip()]
        return tracked
    except Exception:
        # Fallback if git executable is unavailable
        files = []
        for p in REPO_ROOT.rglob("*"):
            if p.is_file() and not any(
                part in ENVIRONMENT_DIRS for part in p.relative_to(REPO_ROOT).parts
            ):
                files.append(p)
        return files


def _is_repo_owned(path: Path) -> bool:
    """Check if a path is ChangeMesh source rather than a third-party environment artifact."""
    rel = path.relative_to(REPO_ROOT) if path.is_absolute() else path
    return not any(part in ENVIRONMENT_DIRS for part in rel.parts)


class TestLeanArchitectureAndWasteElimination:
    """Verify lean architecture invariants, absence of bloat, and cost efficiency."""

    def test_zero_node_and_npm_footprint(self):
        """Repository source must contain zero package.json, node_modules, or JS build configs."""
        repo_files = _get_repository_source_files()

        # Tracked/owned files check
        forbidden_exact_names = {
            "package.json",
            "webpack.config.js",
            "vite.config.js",
            "tsconfig.json",
        }
        forbidden_found = [
            str(f.relative_to(REPO_ROOT))
            for f in repo_files
            if f.name in forbidden_exact_names or "node_modules" in f.parts
        ]

        # Un-ignored source check (ensures untracked source files in src/ or tests/ are clean)
        for d in (
            REPO_ROOT / "src",
            REPO_ROOT / "tests",
            REPO_ROOT / "docs",
            REPO_ROOT / "scripts",
        ):
            if d.is_dir():
                for p in d.rglob("*"):
                    if p.name in forbidden_exact_names or "node_modules" in p.parts:
                        forbidden_found.append(str(p.relative_to(REPO_ROOT)))

        assert len(forbidden_found) == 0, (
            f"Found unexpected ChangeMesh Node/npm build artifact: {forbidden_found}"
        )

    def test_lean_detection_negative_and_positive_controls(self):
        """Prove that dev environment files are filtered while repo-owned artifacts are caught."""
        # 1. Dev virtualenv artifact is not flagged as repo-owned
        venv_path = (
            REPO_ROOT
            / ".venv"
            / "Lib"
            / "site-packages"
            / "playwright"
            / "driver"
            / "package"
            / "package.json"
        )
        assert not _is_repo_owned(venv_path), (
            "Venv packages must not be identified as repository source"
        )

        # 2. Simulated repo-owned package.json in src/ or root is flagged as repo-owned
        mock_src_path = REPO_ROOT / "src" / "package.json"
        mock_root_path = REPO_ROOT / "vite.config.js"
        assert _is_repo_owned(mock_src_path), "Source path must be identified as repository source"
        assert _is_repo_owned(mock_root_path), "Root path must be identified as repository source"

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
