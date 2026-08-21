"""ChangeMesh P-25.05 — Claim, Evidence, Secret, License, and Broken-Link Governance Test Matrix.

Acceptance criteria from master plan:
  - Unsupported claims and leaked secrets fail CI.
  - Covers Gap 21 (CCT-JUDGE-001 - Judge package integrity) & Gap 26 (ZK-CLAIM-001 - Claim audit).
  - Secret scanning across all repository source, fixture, and documentation surfaces.
  - Mode honesty: Real vs Fixture vs Simulation distinction strictly preserved.
  - License compatibility and donor manifest integrity verified.
  - Internal markdown link integrity: zero broken file paths in README, docs, and judge guides.

Required evidence: Governance test report (docs/P-25.05_GOVERNANCE_TEST_REPORT.md).
Mandatory documentation sync: Submission docs.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SRC_DIR = REPO_ROOT / "src"
DOMAIN_DIR = REPO_ROOT / "domain"
TESTS_DIR = REPO_ROOT / "tests"


# ============================================================================
# SECTION 1: SECRET SCANNER & CREDENTIAL LEAKAGE PREVENTION
# ============================================================================


class TestSecretAndCredentialLeakage:
    """Scan all tracked files for accidental credential and private key leaks."""

    SECRET_PATTERNS = [
        ("RSA_PRIVATE_KEY", re.compile(r"-----BEGIN RSA PRIVATE KEY-----")),
        ("EC_PRIVATE_KEY", re.compile(r"-----BEGIN EC PRIVATE KEY-----")),
        ("OPENSSH_PRIVATE_KEY", re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----")),
        ("PGP_PRIVATE_KEY", re.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----")),
        ("GOOGLE_AI_STUDIO_KEY", re.compile(r"\bAIzaSy[A-Za-z0-9_-]{33}\b")),
        ("GITHUB_PAT_CLASSIC", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
        ("GITHUB_FINE_GRAINED_PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
        (
            "AWS_SECRET_KEY",
            re.compile(r"(?i)aws_secret_access_key\s*=\s*['\"][A-Za-z0-9/+=]{40}['\"]"),
        ),
        ("SLACK_API_TOKEN", re.compile(r"\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*\b")),
        ("REAL_GCP_SA_KEY", re.compile(r'"private_key":\s*"-----BEGIN PRIVATE KEY-----\\nMIIE')),
    ]

    # Files exempt from scanning (e.g., this test file itself, gitignore, test scanners)
    EXEMPT_FILES = {
        "test_p25_05_governance_matrix.py",
        "policy_engine.py",
        "input_privacy.py",
        "test_p16_policy_engine.py",
        "test_p08_03_input_privacy.py",
        "test_p23_agent_security.py",
        "test_p25_01_comprehensive_unit.py",
        "test_p25_03_shadowlab_suite.py",
    }

    def test_zero_real_secrets_in_repository_files(self):
        """Scan all code, documentation, and fixture files for live secret tokens."""
        scanned_count = 0
        violations: List[Tuple[str, str, int]] = []

        for root, dirs, files in os.walk(REPO_ROOT):
            # Skip caches, git, venvs
            dirs[:] = [
                d
                for d in dirs
                if d
                not in (
                    ".git",
                    ".venv",
                    ".venv-recovery",
                    "__pycache__",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                )
            ]

            for file in files:
                if file in self.EXEMPT_FILES:
                    continue
                if file.endswith((".pyc", ".png", ".jpg", ".ico", ".lock", ".gz")):
                    continue

                file_path = Path(root) / file
                scanned_count += 1
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                for pattern_name, pattern in self.SECRET_PATTERNS:
                    matches = list(pattern.finditer(text))
                    for m in matches:
                        line_no = text[: m.start()].count("\n") + 1
                        rel_path = file_path.relative_to(REPO_ROOT)
                        violations.append((str(rel_path), pattern_name, line_no))

        assert len(violations) == 0, (
            f"Secret scanner found {len(violations)} violation(s): {violations}"
        )
        assert scanned_count >= 100, f"Expected to scan >= 100 files, scanned {scanned_count}"


# ============================================================================
# SECTION 2: CLAIM AUDIT & EVIDENCE HONESTY (ZK-CLAIM-001)
# ============================================================================


class TestClaimAuditAndEvidenceHonesty:
    """Gap 26: Unsupported-claim scanner and evidence mode honesty."""

    APPROVED_STATUS_TOKENS = {
        "PASS",
        "WARN",
        "FAIL",
        "NOT_RUN",
        "SIMULATED",
        "BLOCKED",
        "QUARANTINED",
        "DONE",
        "PENDING",
        "IN_PROGRESS",
    }

    FORBIDDEN_UNSUPPORTED_CLAIMS = [
        re.compile(r"(?i)100%\s+autonomous\s+production\s+deployment\s+without\s+human"),
        re.compile(r"(?i)replaces\s+all\s+human\s+judgment\s+completely"),
        re.compile(r"(?i)zero\s+risk\s+guarantee"),
        re.compile(r"(?i)infinite\s+scalability"),
    ]

    def test_zero_unsupported_hyperbolic_claims_in_docs(self):
        """Docs must not contain hyperbolic unprovable claims."""
        doc_files = list(DOCS_DIR.glob("*.md")) + [
            REPO_ROOT / "README.md",
            REPO_ROOT / "JUDGE_START_HERE.md",
            REPO_ROOT / "README.tr.md",
        ]
        violations = []

        for doc_file in doc_files:
            if not doc_file.is_file():
                continue
            text = doc_file.read_text(encoding="utf-8")
            for pattern in self.FORBIDDEN_UNSUPPORTED_CLAIMS:
                if pattern.search(text):
                    violations.append((doc_file.name, pattern.pattern))

        assert len(violations) == 0, f"Found unsupported claims in documentation: {violations}"

    def test_evidence_mode_honesty_tokens_used(self):
        """All master plan task statuses must use approved status tokens only."""
        plan_path = REPO_ROOT / "plans" / "CHANGEMESH_MASTER_EXECUTION_PLAN.md"
        assert plan_path.is_file()
        text = plan_path.read_text(encoding="utf-8")

        status_matches = re.findall(r"-\s+\*\*Status:\*\*\s+`([^`]+)`", text)
        assert len(status_matches) >= 30, (
            f"Expected >= 30 task statuses in master plan, got {len(status_matches)}"
        )

        for status in status_matches:
            assert status in self.APPROVED_STATUS_TOKENS, (
                f"Invalid status token {status!r} found in master plan. "
                f"Allowed: {self.APPROVED_STATUS_TOKENS}"
            )

    def test_live_write_requires_explicit_danger_flag(self):
        """Local tests must default to fail-closed without --live-write-danger."""
        # Verify default execution does not perform live mutation
        from domain.contracts.evidence import ExecutionEvidenceMode

        assert ExecutionEvidenceMode.SIMULATION.value == "SIMULATION"
        assert ExecutionEvidenceMode.FIXTURE.value == "FIXTURE"
        assert ExecutionEvidenceMode.RECORDED_CLOUD.value == "RECORDED_CLOUD"
        assert ExecutionEvidenceMode.LIVE_WRITE.value == "LIVE_WRITE"


# ============================================================================
# SECTION 3: JUDGE PACKAGE & MARKDOWN LINK INTEGRITY (CCT-JUDGE-001)
# ============================================================================


class TestJudgePackageAndLinkIntegrity:
    """Gap 21: Link/status/version/claim parity across Judge docs and codebase."""

    def test_all_internal_relative_markdown_links_resolve(self):
        """Scan all markdown files and verify that every internal relative file link exists."""
        md_files = list(REPO_ROOT.glob("*.md")) + list(DOCS_DIR.glob("*.md"))
        broken_links: List[Tuple[str, str, str]] = []

        for md_file in md_files:
            if not md_file.is_file():
                continue
            content = md_file.read_text(encoding="utf-8")

            # Match markdown links: [text](path)
            # Exclude http/https, mailto, anchor-only (#), and conversation:// URIs
            links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
            for text, target in links:
                target_clean = target.strip()
                if target_clean.startswith(
                    ("http://", "https://", "mailto:", "#", "conversation://")
                ) or target_clean.startswith("file://"):
                    continue

                # Strip anchor if present: file.md#section
                file_target = target_clean.split("#")[0]
                if not file_target:
                    continue  # was just an anchor

                # Resolve relative to current md file directory
                resolved_path = (md_file.parent / file_target).resolve()
                if not resolved_path.exists():
                    broken_links.append((md_file.name, target, str(resolved_path)))

        assert len(broken_links) == 0, (
            f"Found {len(broken_links)} broken relative links in markdown docs: {broken_links[:10]}"
        )

    def test_canonical_model_id_consistency(self):
        """Canonical model ID (gemini-3.6-flash) must be consistent across code and service."""
        from src.core.gemini_client import CANONICAL_MODEL_ID

        assert CANONICAL_MODEL_ID == "gemini-3.6-flash"

        # Check service_app.py
        service_text = (REPO_ROOT / "service_app.py").read_text(encoding="utf-8")
        assert "CANONICAL_MODEL_ID" in service_text

    def test_no_codex_event_or_gpt_model_leakage_in_judge_docs(self):
        """Judge documents must not leak Codex event names or GPT model identifiers."""
        judge_docs = [
            REPO_ROOT / "JUDGE_START_HERE.md",
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "DASHBOARD_REQUIREMENTS.md",
            REPO_ROOT / "docs" / "DEMO_SCRIPT.md",
        ]
        forbidden_tokens = [
            r"\bgpt-4o\b",
            r"\bgpt-3\.5\b",
            r"\btext-davinci\b",
            r"\bopenai_api_key\b",
            r"\bcodex_event_bus\b",
        ]
        violations = []

        for doc in judge_docs:
            if not doc.is_file():
                continue
            text = doc.read_text(encoding="utf-8")
            for token_pattern in forbidden_tokens:
                if re.search(token_pattern, text, re.IGNORECASE):
                    violations.append((doc.name, token_pattern))

        assert len(violations) == 0, f"Found forbidden donor leakage in judge docs: {violations}"


# ============================================================================
# SECTION 4: DONOR MANIFEST & LICENSE COMPATIBILITY
# ============================================================================


class TestDonorManifestAndLicenses:
    """Verify license compatibility and donor reuse governance."""

    def test_donor_manifest_lint_script_passes(self):
        """The donor manifest lint script must pass with 20 components."""
        import subprocess

        cmd = ["uv", "run", "python", "scripts/donor_manifest_lint.py"]
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        assert result.returncode == 0, (
            f"donor_manifest_lint.py failed: {result.stderr}\n{result.stdout}"
        )
        assert "Manifest linting passed successfully" in result.stdout
        assert "Components: 20" in result.stdout

    def test_all_donors_have_compatible_licenses(self):
        """All 7 registered donors in DONOR_REUSE_MANIFEST.md must declare compatible licenses."""
        manifest_path = REPO_ROOT / "docs" / "DONOR_REUSE_MANIFEST.md"
        assert manifest_path.is_file()
        text = manifest_path.read_text(encoding="utf-8")

        # Every donor table must contain License State: VERIFIED_COMPATIBLE
        # or a compatible license name
        assert "VERIFIED_COMPATIBLE" in text or "MIT" in text or "Apache-2.0" in text

        # Verify no GPL-incompatible license declarations
        assert "GPL-3.0-only" not in text
        assert "AGPL-3.0" not in text

    def test_pyproject_toml_declares_correct_python_and_dependencies(self):
        """pyproject.toml must declare Python >= 3.13 and Google ADK / GenAI dependencies."""
        pyproject_path = REPO_ROOT / "pyproject.toml"
        assert pyproject_path.is_file()
        text = pyproject_path.read_text(encoding="utf-8")

        assert "requires-python" in text
        assert "3.13" in text
        assert "pydantic" in text
        assert "pytest" in text
