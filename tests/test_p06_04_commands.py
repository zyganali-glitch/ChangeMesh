import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()


def run_cmd(*args):
    """Run a command using uv run python scripts/cmd.py"""
    base_cmd = ["uv", "run", "python", "scripts/cmd.py"]
    base_cmd.extend(args)
    return subprocess.run(base_cmd, cwd=REPO_ROOT, capture_output=True, text=True)


def test_unknown_command_fails():
    result = run_cmd("unknown_cmd")
    assert result.returncode != 0
    assert "invalid choice: 'unknown_cmd'" in result.stderr


def test_future_commands_fail_closed():
    """Verify that commands owning future phases fail closed cleanly."""
    for cmd in ["e2e", "demo", "deploy", "teardown"]:
        result = run_cmd(cmd)
        assert result.returncode != 0
        assert "NOT_RUN" in result.stdout
        assert "pending" in result.stdout.lower()


def test_integration_live_write_guard():
    """Verify that integration command fails closed by default to prevent accidental mutations."""
    result = run_cmd("integration")
    assert result.returncode != 0
    assert "REAL Google Cloud mutations" in result.stderr
    assert "must explicitly authorize" in result.stderr


def test_command_registry_metadata():
    """Verify that the script defines all required commands in help text."""
    result = run_cmd("--help")
    assert result.returncode == 0
    help_text = result.stdout
    for cmd in [
        "format",
        "lint",
        "type-check",
        "unit",
        "integration",
        "e2e",
        "demo",
        "deploy",
        "teardown",
    ]:
        assert cmd in help_text
