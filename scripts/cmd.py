import argparse
import subprocess
import sys


def run_command(args, env=None, check=True):
    """Run a subprocess command and return its exit code."""
    try:
        result = subprocess.run(args, env=env, check=check)
        return result.returncode
    except subprocess.CalledProcessError as e:
        return e.returncode
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return 1


def format_cmd(args):
    print("Running formatter (ruff format)...")
    return run_command(["uv", "run", "ruff", "format", "."])


def lint_cmd(args):
    print("Running linter (ruff check)...")
    return run_command(["uv", "run", "ruff", "check", "."])


def typecheck_cmd(args):
    print("Running type-checker (mypy)...")
    return run_command(["uv", "run", "mypy", "domain", "tests"])


def unit_cmd(args):
    print("Running unit tests...")
    # Explicitly exclude test_gcp_access.py from unit tests as it performs REAL Google Cloud mutations.
    # Exclude other E2E or integration tests if they exist.
    # We will use pytest's --ignore flag.
    return run_command(["uv", "run", "pytest", "tests/", "--ignore=tests/test_gcp_access.py"])


def integration_cmd(args):
    print("Running integration tests...")
    # These tests mutate GCP. Require explicit --live-write-danger flag.
    if not args.live_write_danger:
        print(
            "ERROR: Integration tests perform REAL Google Cloud mutations.",
            file=sys.stderr,
        )
        print(
            "You must explicitly authorize this with: --live-write-danger",
            file=sys.stderr,
        )
        return 1

    return run_command(["uv", "run", "pytest", "tests/test_gcp_access.py"])


def e2e_cmd(args):
    print("E2E tests: NOT_RUN. (Owning phase P-24/P-25 pending)")
    return 1


def demo_cmd(args):
    print("Demo command: NOT_RUN. (Owning phase P-24 pending)")
    return 1


def deploy_cmd(args):
    print("Deploy command: NOT_RUN. (Owning phase P-28 pending)")
    return 1


def teardown_cmd(args):
    print("Teardown command: NOT_RUN. (Owning phase P-28 pending)")
    return 1


def main():
    parser = argparse.ArgumentParser(description="ChangeMesh Canonical Command Interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Format
    parser_format = subparsers.add_parser("format", help="Format source code")
    parser_format.set_defaults(func=format_cmd)

    # Lint
    parser_lint = subparsers.add_parser("lint", help="Lint source code")
    parser_lint.set_defaults(func=lint_cmd)

    # Type-check
    parser_typecheck = subparsers.add_parser("type-check", help="Type-check source code")
    parser_typecheck.set_defaults(func=typecheck_cmd)

    # Unit
    parser_unit = subparsers.add_parser("unit", help="Run unit tests")
    parser_unit.set_defaults(func=unit_cmd)

    # Integration
    parser_integration = subparsers.add_parser("integration", help="Run integration tests")
    parser_integration.add_argument(
        "--live-write-danger",
        action="store_true",
        help="Authorize REAL Google Cloud mutations",
    )
    parser_integration.set_defaults(func=integration_cmd)

    # E2E
    parser_e2e = subparsers.add_parser("e2e", help="Run end-to-end tests")
    parser_e2e.set_defaults(func=e2e_cmd)

    # Demo
    parser_demo = subparsers.add_parser("demo", help="Run demo")
    parser_demo.set_defaults(func=demo_cmd)

    # Deploy
    parser_deploy = subparsers.add_parser("deploy", help="Deploy infrastructure")
    parser_deploy.set_defaults(func=deploy_cmd)

    # Teardown
    parser_teardown = subparsers.add_parser("teardown", help="Teardown infrastructure")
    parser_teardown.set_defaults(func=teardown_cmd)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
