"""ChangeMesh P-06.03 — Safe local configuration templates and secret handling tests.

Acceptance criteria:
1. Canonical configuration template (.env.example) exists and is tracked.
2. Variable names in template are not duplicated and match canonical registry.
3. Secret-bearing variables (GITHUB_TOKEN) have NO secret defaults (empty).
4. No private-key / PEM material or live token signatures in template.
5. .gitignore covers local credentials, service account keys, and sensitive artifacts.
6. .gitignore explicitly preserves .env.example while ignoring real .env files.
7. Local authentication policy enforces Application Default Credentials (ADC)
   without teaching or distributing service-account JSON key files.
8. Future-phase variables preserve phase ownership without premature requiredness.
9. Domain contracts remain provider-neutral without credential fields or leaks.
10. Whole-repository tracked files contain no real credentials or secret defaults.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List

import pytest

# Repository root directory
REPO_ROOT = Path(__file__).resolve().parent.parent

# Canonical environment variable registry (from AGENT_ENVIRONMENT_AND_API.md)
CANONICAL_ENV_VARS: Dict[str, Dict[str, str | bool]] = {
    "GOOGLE_CLOUD_PROJECT": {
        "secret": False,
        "owner": "P-02/P-28",
        "description": "Google Cloud project ID",
    },
    "GOOGLE_CLOUD_LOCATION": {
        "secret": False,
        "owner": "P-02/P-28",
        "description": "Deployment region",
    },
    "GEMINI_MODEL": {
        "secret": False,
        "owner": "P-08",
        "description": "Exact model ID",
    },
    "GITHUB_TOKEN": {
        "secret": True,
        "owner": "P-19",
        "description": "Optional live draft-PR action",
    },
    "DEMO_REPO": {
        "secret": False,
        "owner": "P-24",
        "description": "Synthetic target repository",
    },
}

# Suspicious token/key patterns that must never appear in configuration templates
SUSPICIOUS_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN\s+.*PRIVATE\s+KEY-----"),
    re.compile(r"-----BEGIN\s+CERTIFICATE-----"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"gho_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"AIza[0-9A-Za-z-_]{35}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"),
    re.compile(r"\b(?:changeme|dummy-key|fake-secret|secret-value)\b", re.IGNORECASE),
]


def _parse_env_template(filepath: Path) -> Dict[str, str]:
    """Parse a .env or .env.example file as raw key-value data without executing."""
    assert filepath.is_file(), f"File {filepath} does not exist"
    env_vars: Dict[str, str] = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            # Remove optional surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            if key in env_vars:
                pytest.fail(f"Duplicate environment variable '{key}' found at line {line_num}")
            env_vars[key] = val
    return env_vars


# =============================================================================
# 1. TEMPLATE EXISTENCE AND TRACKING
# =============================================================================

def test_env_example_exists_and_is_non_empty():
    """Verify that .env.example exists at repository root and has content."""
    template_path = REPO_ROOT / ".env.example"
    assert template_path.is_file(), ".env.example must exist at repository root"
    content = template_path.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, ".env.example must not be empty"


def test_env_example_is_trackable_by_git():
    """Verify that .env.example is not ignored by git."""
    template_path = REPO_ROOT / ".env.example"
    result = subprocess.run(
        ["git", "check-ignore", str(template_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    # git check-ignore returns exit code 1 if the file is NOT ignored (i.e. trackable)
    # or exit code 0 if ignored. If it's a negative rule, check output.
    if result.returncode == 0:
        # If exit code is 0, verify it matched a negative ignore rule (starts with '!')
        assert "!" in result.stdout or "! .env.example" in result.stdout or "!.env.example" in result.stdout, (
            f".env.example is ignored by git: {result.stdout}"
        )


# =============================================================================
# 2. CANONICAL VARIABLE SET AND NO DUPLICATES
# =============================================================================

def test_env_example_variables_match_canonical_registry():
    """Verify that .env.example defines exactly the registered canonical variables."""
    template_path = REPO_ROOT / ".env.example"
    parsed_vars = _parse_env_template(template_path)
    registered_keys = set(CANONICAL_ENV_VARS.keys())
    template_keys = set(parsed_vars.keys())

    assert template_keys == registered_keys, (
        f"Mismatch between .env.example and canonical registry.\n"
        f"Extra in template: {template_keys - registered_keys}\n"
        f"Missing from template: {registered_keys - template_keys}"
    )


def test_env_example_has_no_duplicate_keys():
    """Verify that no duplicate variable keys exist in .env.example."""
    template_path = REPO_ROOT / ".env.example"
    keys_seen: List[str] = []
    with open(template_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=", 1)[0].strip()
                assert key not in keys_seen, f"Duplicate key '{key}' found in .env.example"
                keys_seen.append(key)


# =============================================================================
# 3. SECRET SAFETY AND NO SECRET DEFAULTS
# =============================================================================

def test_secret_variables_have_no_defaults():
    """Verify that secret-bearing variables (e.g. GITHUB_TOKEN) have empty values."""
    template_path = REPO_ROOT / ".env.example"
    parsed_vars = _parse_env_template(template_path)

    for var_name, meta in CANONICAL_ENV_VARS.items():
        if meta["secret"]:
            value = parsed_vars[var_name]
            assert value == "", (
                f"Secret-bearing variable '{var_name}' must have empty default, but got: '{value}'"
            )


def test_non_secret_variables_have_safe_empty_or_placeholder_values():
    """Verify that future-owned non-secret variables are empty to prevent premature freezing."""
    template_path = REPO_ROOT / ".env.example"
    parsed_vars = _parse_env_template(template_path)

    for var_name, meta in CANONICAL_ENV_VARS.items():
        if not meta["secret"]:
            value = parsed_vars[var_name]
            # Must be empty in template so it does not freeze future phase implementations
            assert value == "", (
                f"Non-secret variable '{var_name}' should be empty in template, got: '{value}'"
            )


def test_no_suspicious_secret_patterns_in_template():
    """Verify that .env.example contains no private keys, certificates, or tokens."""
    template_path = REPO_ROOT / ".env.example"
    content = template_path.read_text(encoding="utf-8")

    for pattern in SUSPICIOUS_SECRET_PATTERNS:
        match = pattern.search(content)
        assert match is None, (
            f"Suspicious secret pattern '{pattern.pattern}' found in .env.example: '{match.group(0) if match else ''}'"
        )


# =============================================================================
# 4. AUTHENTICATION POLICY AND ADC GUIDANCE
# =============================================================================

def test_template_promotes_application_default_credentials():
    """Verify that .env.example explains Application Default Credentials (ADC) for local dev."""
    template_path = REPO_ROOT / ".env.example"
    content = template_path.read_text(encoding="utf-8")

    assert "Application Default Credentials" in content or "ADC" in content, (
        ".env.example must document ADC policy for local development"
    )
    assert "application-default login" in content or "gcloud auth" in content, (
        ".env.example must reference gcloud auth application-default login"
    )


def test_template_does_not_distribute_service_account_keys():
    """Verify that .env.example does not configure GOOGLE_APPLICATION_CREDENTIALS JSON files."""
    template_path = REPO_ROOT / ".env.example"
    content = template_path.read_text(encoding="utf-8")
    parsed_vars = _parse_env_template(template_path)

    assert "GOOGLE_APPLICATION_CREDENTIALS" not in parsed_vars, (
        "GOOGLE_APPLICATION_CREDENTIALS pointing to service account keys must not be in template"
    )
    # Check that service account keys are explicitly discouraged
    assert "service-account" in content.lower() or "service account" in content.lower(), (
        ".env.example should mention that service account key files are prohibited/ignored"
    )


# =============================================================================
# 5. GITIGNORE CREDENTIAL AND ARTIFACT COVERAGE
# =============================================================================

def test_gitignore_ignores_real_env_files():
    """Verify that .gitignore ignores .env and environment variants while keeping .env.example."""
    gitignore_path = REPO_ROOT / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore must exist"

    test_paths = [
        ".env",
        ".env.local",
        ".env.development",
        ".env.production",
        ".env.test",
        ".env.staging",
    ]
    for path in test_paths:
        result = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"Path '{path}' should be ignored by .gitignore"

    # .env.example must NOT be ignored
    example_result = subprocess.run(
        ["git", "check-ignore", "-v", ".env.example"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if example_result.returncode == 0:
        assert "!" in example_result.stdout, (
            f".env.example must not be ignored (should match negative pattern): {example_result.stdout}"
        )


def test_gitignore_ignores_credential_and_key_files():
    """Verify that .gitignore covers common secret, key, and credential file patterns."""
    sensitive_test_files = [
        "id_rsa.key",
        "server.key",
        "private.pem",
        "certificate.pem",
        "keystore.p12",
        "cert.pfx",
        "bundle.pkcs12",
        "service-account.json",
        "my-service-account-key.json",
        "changemesh_service_account.json",
        "credentials.json",
        "gcp_credentials.json",
        "client_credential.json",
        "application_default_credentials.json",
        "local_adc.json",
        "api_key.txt",
        "access.token",
        "secret.token",
        "db.secret",
    ]
    for filename in sensitive_test_files:
        result = subprocess.run(
            ["git", "check-ignore", "-q", filename],
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"Credential file '{filename}' must be ignored by .gitignore"


def test_gitignore_ignores_sensitive_directories():
    """Verify that .gitignore ignores sensitive and temporary directories."""
    sensitive_dirs = [
        "tmp/temp_output.log",
        "artifacts/private/evidence.json",
        "private/keys.txt",
        "secrets/app_secrets.json",
        ".secrets/token.txt",
        ".gemini/context.json",
        ".changemesh-backups/backup.tar",
    ]
    for dir_path in sensitive_dirs:
        result = subprocess.run(
            ["git", "check-ignore", "-q", dir_path],
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"Sensitive path '{dir_path}' must be ignored by .gitignore"


# =============================================================================
# 6. DOMAIN CONTRACTS PROVIDER NEUTRALITY AND CREDENTIAL ISOLATION
# =============================================================================

def test_domain_contracts_contain_no_credentials():
    """Verify that domain contracts contain no credential fields or hardcoded secrets."""
    contracts_dir = REPO_ROOT / "domain" / "contracts"
    assert contracts_dir.is_dir(), "domain/contracts directory must exist"

    credential_field_names = {
        "api_key",
        "apikey",
        "secret",
        "password",
        "token",
        "access_token",
        "private_key",
        "service_account",
        "credentials",
    }

    for py_file in contracts_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        parsed_ast = ast.parse(content, filename=str(py_file))

        # Inspect AST to ensure no model fields are credential fields
        for node in ast.walk(parsed_ast):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        field_name = item.target.id.lower()
                        assert field_name not in credential_field_names, (
                            f"Prohibited credential field '{field_name}' in contract model '{node.name}' "
                            f"in file {py_file.name}"
                        )


# =============================================================================
# 7. DETERMINISTIC REPOSITORY SECRET SCAN
# =============================================================================

def test_tracked_files_contain_no_secrets():
    """Scan all tracked files in the repository to ensure no secrets or keys are committed."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    # High-confidence secret signatures that must never exist in tracked source code
    strict_secret_patterns = [
        re.compile(r"-----BEGIN\s+.*PRIVATE\s+KEY-----"),
        re.compile(r"ghp_[A-Za-z0-9]{36}"),
        re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
        re.compile(r"AIzaSy[0-9A-Za-z-_]{33}"),
        re.compile(r"xox[baprs]-[0-9A-Za-z]{10,48}"),
    ]

    for rel_path in tracked_files:
        # Verify no tracked file matches credential file names
        lower_name = os.path.basename(rel_path).lower()
        assert not (lower_name == ".env" or (lower_name.startswith(".env.") and lower_name != ".env.example")), (
            f"Real .env file is tracked: {rel_path}"
        )
        assert not (lower_name.endswith(".key") or lower_name.endswith(".pem") or lower_name.endswith(".p12")), (
            f"Private key file is tracked: {rel_path}"
        )

        full_path = REPO_ROOT / rel_path
        if not full_path.is_file():
            continue

        try:
            content = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Binary file
            continue

        for pattern in strict_secret_patterns:
            match = pattern.search(content)
            assert match is None, (
                f"Secret pattern matched in tracked file '{rel_path}': [REDACTED_MATCH]"
            )
