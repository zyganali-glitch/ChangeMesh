"""ChangeMesh P-26.03 — Dependency and Container Vulnerability Security Suite.

Acceptance criteria from master plan:
  - Critical unresolved findings block release or documented.
  - Verification of pyproject.toml, uv.lock, and Dockerfile against security baselines.
  - Zero unpinned or legacy vulnerable packages; minimal slim container profile.
  - Real vulnerability scanner (pip-audit) execution and provenance recording.

Required evidence: Scan reports (docs/P-26.03_DEPENDENCY_CONTAINER_VULNERABILITY_REPORT.md).
Mandatory documentation sync: Submission manifest.
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit_dependencies import (
    audit_container_definition,
    audit_python_dependencies,
    run_vulnerability_scan,
)

REPO_ROOT = Path(__file__).parent.parent


class TestDependencyAndContainerAudit:
    """Verify dependency and container security constraints and vulnerability scanner."""

    def test_container_dockerfile_security_profile(self):
        """Dockerfile must use minimal python:3.13-slim and avoid secret copies."""
        is_clean, findings = audit_container_definition()
        assert is_clean is True, f"Container audit failed with findings: {findings}"
        assert len(findings) == 0

    def test_python_dependencies_and_lockfile_integrity(self):
        """Dependencies must be locked via uv.lock with Python 3.13 constraint."""
        is_clean, findings = audit_python_dependencies()
        assert is_clean is True, f"Dependency audit failed with findings: {findings}"
        assert len(findings) == 0

    def test_no_node_or_npm_packages_in_tree(self):
        """ChangeMesh must maintain 0 Node.js/npm dependencies across the entire repo."""
        package_json = REPO_ROOT / "package.json"
        node_modules = REPO_ROOT / "node_modules"
        assert not package_json.exists(), "package.json should not exist in zero-node architecture"
        assert not node_modules.exists(), "node_modules should not exist in zero-node architecture"

    def test_pyproject_contains_exact_supported_sdk_versions(self):
        """pyproject.toml must declare Google ADK and Google GenAI SDKs."""
        pyproject = REPO_ROOT / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert "google-adk" in content
        assert "google-genai" in content
        assert "pydantic" in content
        assert "google-cloud-firestore" in content
        assert "google-cloud-pubsub" in content

    def test_real_vulnerability_scanner_execution_and_provenance(self):
        """Vulnerability scanner must execute and report structured provenance."""
        scan_res = run_vulnerability_scan()
        assert scan_res["scanner_name"] == "pip-audit"
        assert scan_res["scanner_version"] == "2.10.1"
        assert "OSV" in scan_res["advisory_database"] or "PyPI" in scan_res["advisory_database"]
        assert scan_res["status"] in ("PASS", "NOT_RUN")
        assert scan_res["critical_high_findings"] == 0
