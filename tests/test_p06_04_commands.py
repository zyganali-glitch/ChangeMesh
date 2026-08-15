import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).parent.parent.resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.cmd as cmd  # noqa: E402


def run_cli(*args):
    """Run a command using uv run python scripts/cmd.py"""
    base_cmd = ["uv", "run", "python", "scripts/cmd.py"]
    base_cmd.extend(args)
    return subprocess.run(base_cmd, cwd=REPO_ROOT, capture_output=True, text=True)


def test_command_registry_help_exposes_all_nine_commands():
    """Verify that the script defines all 9 canonical commands in help text."""
    result = run_cli("--help")
    assert result.returncode == 0
    help_text = result.stdout
    canonical_commands = [
        "format",
        "lint",
        "type-check",
        "unit",
        "integration",
        "e2e",
        "demo",
        "deploy",
        "teardown",
    ]
    for c in canonical_commands:
        assert c in help_text, f"Command '{c}' missing from CLI help text."


def test_unknown_command_fails_closed():
    """Verify that an unknown command returns non-zero and prints an error."""
    result = run_cli("unknown_command_xyz")
    assert result.returncode != 0
    assert "invalid choice: 'unknown_command_xyz'" in result.stderr


def test_future_commands_fail_closed_cli():
    """Verify that deferred commands fail closed with NOT_RUN via CLI."""
    for command_name in ["e2e", "demo", "deploy", "teardown"]:
        result = run_cli(command_name)
        assert result.returncode != 0, f"Deferred command '{command_name}' did not exit non-zero"
        assert "NOT_RUN" in result.stdout, (
            f"Deferred command '{command_name}' did not output NOT_RUN"
        )
        assert "pending" in result.stdout.lower()


def test_future_commands_fail_closed_direct():
    """Verify that deferred command functions return non-zero exit code directly."""
    assert cmd.e2e_cmd() == 1
    assert cmd.demo_cmd() == 1
    assert cmd.deploy_cmd() == 1
    assert cmd.teardown_cmd() == 1


def test_integration_default_fails_closed_cli():
    """Verify that integration command fails closed by default to prevent accidental mutations."""
    result = run_cli("integration")
    assert result.returncode != 0
    assert "REAL Google Cloud mutations" in result.stderr
    assert "must explicitly authorize" in result.stderr


def test_integration_default_fails_closed_direct():
    """Verify that integration_cmd fails closed without --live-write-danger."""
    assert cmd.integration_cmd(None) == 1

    mock_args = MagicMock()
    mock_args.live_write_danger = False
    assert cmd.integration_cmd(mock_args) == 1


def test_integration_authorized_dispatches_script_without_pytest(monkeypatch):
    """Verify that authorized integration dispatches python script, NOT pytest collection."""
    dispatched_commands = []

    def mock_run_command(args, env=None, check=False):
        dispatched_commands.append(args)
        return 0

    monkeypatch.setattr(cmd, "run_command", mock_run_command)

    mock_args = MagicMock()
    mock_args.live_write_danger = True

    exit_code = cmd.integration_cmd(mock_args)
    assert exit_code == 0
    assert len(dispatched_commands) == 1
    dispatched = dispatched_commands[0]

    # Must run the script with python, NOT pytest
    assert "python" in dispatched
    assert "pytest" not in dispatched
    assert "tests/test_gcp_access.py" in dispatched


def test_format_command_check_only_semantics(monkeypatch):
    """Verify that format command is check-only and never includes --fix or mutates files."""
    dispatched_commands = []

    def mock_run_command(args, env=None, check=False):
        dispatched_commands.append(args)
        return 0

    monkeypatch.setattr(cmd, "run_command", mock_run_command)

    exit_code = cmd.format_cmd()
    assert exit_code == 0
    assert len(dispatched_commands) == 1
    dispatched = dispatched_commands[0]

    assert "ruff" in dispatched
    assert "format" in dispatched
    assert "--check" in dispatched
    assert "--fix" not in dispatched


def test_lint_command_non_mutating_semantics(monkeypatch):
    """Verify that lint command is non-mutating and never includes --fix."""
    dispatched_commands = []

    def mock_run_command(args, env=None, check=False):
        dispatched_commands.append(args)
        return 0

    monkeypatch.setattr(cmd, "run_command", mock_run_command)

    exit_code = cmd.lint_cmd()
    assert exit_code == 0
    assert len(dispatched_commands) == 1
    dispatched = dispatched_commands[0]

    assert "ruff" in dispatched
    assert "check" in dispatched
    assert "--fix" not in dispatched


def test_typecheck_command_scope_and_propagation(monkeypatch):
    """Verify that type-check command runs mypy on canonical scope and propagates exit code."""
    dispatched_commands = []

    def mock_run_command(args, env=None, check=False):
        dispatched_commands.append(args)
        return 3

    monkeypatch.setattr(cmd, "run_command", mock_run_command)

    exit_code = cmd.typecheck_cmd()
    assert exit_code == 3
    assert len(dispatched_commands) == 1
    dispatched = dispatched_commands[0]

    assert "mypy" in dispatched
    assert "domain" in dispatched
    assert "tests" in dispatched


def test_unit_command_excludes_gcp_access(monkeypatch):
    """Verify that unit command runs pytest while explicitly excluding live GCP access tests."""
    dispatched_commands = []

    def mock_run_command(args, env=None, check=False):
        dispatched_commands.append(args)
        return 0

    monkeypatch.setattr(cmd, "run_command", mock_run_command)

    exit_code = cmd.unit_cmd()
    assert exit_code == 0
    assert len(dispatched_commands) == 1
    dispatched = dispatched_commands[0]

    assert "pytest" in dispatched
    assert "--ignore=tests/test_gcp_access.py" in dispatched


def test_subprocess_exit_code_propagation_on_error(monkeypatch):
    """Verify that run_command propagates exact exit codes from subprocess."""
    mock_completed = MagicMock()
    mock_completed.returncode = 42

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_completed)
    assert cmd.run_command(["dummy"]) == 42


def test_run_command_handles_subprocess_exceptions(monkeypatch):
    """Verify that run_command catches subprocess exceptions gracefully and returns non-zero."""

    def mock_run_raise(*args, **kwargs):
        raise FileNotFoundError("Mock command not found")

    monkeypatch.setattr(subprocess, "run", mock_run_raise)
    assert cmd.run_command(["nonexistent_binary"]) == 1


def test_main_cli_dispatch(monkeypatch):
    """Verify that main() dispatches to the correct subparser function."""
    monkeypatch.setattr(cmd, "unit_cmd", lambda args=None: 0)
    assert cmd.main(["unit"]) == 0

    monkeypatch.setattr(cmd, "format_cmd", lambda args=None: 0)
    assert cmd.main(["format"]) == 0


def test_no_secret_requirement_for_cli_help_or_execution(monkeypatch):
    """Verify that CLI execution requires no ambient secrets or cloud credentials."""
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    parser = cmd.build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0
