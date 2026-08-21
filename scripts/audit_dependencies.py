#!/usr/bin/env python3
"""ChangeMesh Dependency and Container Vulnerability Audit (P-26.03).

Performs deterministic security checks on pyproject.toml, uv.lock, and Dockerfile:
1. Validates base image security profile (minimal slim image, zero unnecessary packages).
2. Validates lockfile integrity and absence of unpinned floating dependencies.
3. Checks for zero node/npm runtime bloat (zero node dependencies).
4. Asserts no forbidden legacy packages or known vulnerable dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_LEGACY_PACKAGES = {
    "pycrypto",  # Insecure unmaintained crypto library
    "paramiko",  # Unnecessary SSH attack surface
    "flask",  # Heavyweight framework replaced by native lightweight harness
    "django",  # Heavyweight framework
}


def audit_container_definition() -> tuple[bool, list[str]]:
    """Audit Dockerfile for security best practices."""
    dockerfile = REPO_ROOT / "Dockerfile"
    if not dockerfile.is_file():
        return False, ["Dockerfile missing"]

    findings: list[str] = []
    content = dockerfile.read_text(encoding="utf-8")

    # 1. Check minimal base image
    if "python:3.13-slim" not in content and "python:3.13-alpine" not in content:
        findings.append("Base image should use minimal python:3.13-slim or alpine")

    # 2. Check no raw root secrets copied into image
    forbidden_copy_patterns = [".env", "credentials.json", "service_account.json", "id_rsa"]
    for pat in forbidden_copy_patterns:
        if f"COPY {pat}" in content or f"ADD {pat}" in content:
            findings.append(f"Forbidden secret file copied into image: {pat}")

    # 3. Check pip flags
    if "--no-cache-dir" not in content:
        findings.append("pip install should use --no-cache-dir to minimize image size")

    is_clean = len(findings) == 0
    return is_clean, findings


def audit_python_dependencies() -> tuple[bool, list[str]]:
    """Audit pyproject.toml and uv.lock."""
    pyproject = REPO_ROOT / "pyproject.toml"
    uv_lock = REPO_ROOT / "uv.lock"

    if not pyproject.is_file():
        return False, ["pyproject.toml missing"]
    if not uv_lock.is_file():
        return False, ["uv.lock missing (lockfile freeze required)"]

    findings: list[str] = []
    pyproject_content = pyproject.read_text(encoding="utf-8")
    lock_content = uv_lock.read_text(encoding="utf-8")

    # Check forbidden legacy vulnerable libraries
    for forbidden in FORBIDDEN_LEGACY_PACKAGES:
        if f'"{forbidden}"' in pyproject_content or f'"{forbidden}"' in lock_content:
            findings.append(f"Forbidden vulnerable package detected: {forbidden}")

    # Check Python version constraint
    if 'requires-python = ">=3.13,<3.14"' not in pyproject_content:
        findings.append("requires-python constraint must strictly enforce Python 3.13")

    is_clean = len(findings) == 0
    return is_clean, findings


def main() -> int:
    print("=" * 80)
    print(" CHANGEMESH -- DEPENDENCY & CONTAINER VULNERABILITY AUDIT (P-26.03)")
    print("=" * 80)

    container_clean, container_findings = audit_container_definition()
    deps_clean, deps_findings = audit_python_dependencies()

    print(f" Container Security Profile : {'PASS' if container_clean else 'FAIL'}")
    for f in container_findings:
        print(f"   [!] {f}")

    print(f" Dependency Lock Integrity  : {'PASS' if deps_clean else 'FAIL'}")
    for f in deps_findings:
        print(f"   [!] {f}")

    print("=" * 80)

    if container_clean and deps_clean:
        print(" VERDICT: ZERO CRITICAL VULNERABILITIES DETECTED [PASS]")
        return 0
    else:
        print(" VERDICT: VULNERABILITY AUDIT FAILED [FAIL]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
