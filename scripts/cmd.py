import argparse
import subprocess
import sys


def run_command(args, env=None, check=False):
    """Run a subprocess command and return its exit code."""
    try:
        result = subprocess.run(args, env=env, check=check)
        return result.returncode
    except subprocess.CalledProcessError as e:
        return e.returncode
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return 1


def format_cmd(args=None):
    print("Running formatter check (ruff format --check)...")
    return run_command(["uv", "run", "ruff", "format", "--check", "."])


def lint_cmd(args=None):
    print("Running linter (ruff check)...")
    return run_command(["uv", "run", "ruff", "check", "."])


def typecheck_cmd(args=None):
    print("Running type-checker (mypy)...")
    return run_command(["uv", "run", "mypy", "domain", "src", "integrations", "tests"])



def unit_cmd(args=None):
    print("Running unit tests...")
    # Exclude test_gcp_access.py from unit tests as it performs real GCP mutations.
    return run_command(["uv", "run", "pytest", "tests/", "--ignore=tests/test_gcp_access.py"])


def integration_cmd(args=None):
    print("Running integration tests...")
    # These tests mutate GCP. Require explicit --live-write-danger flag.
    if args is None or not getattr(args, "live_write_danger", False):
        print(
            "ERROR: Integration tests perform REAL Google Cloud mutations.",
            file=sys.stderr,
        )
        print(
            "You must explicitly authorize this with: --live-write-danger",
            file=sys.stderr,
        )
        return 1

    return run_command(["uv", "run", "python", "tests/test_gcp_access.py"])


def e2e_cmd(args=None):
    print("E2E tests: NOT_RUN. (Owning phase P-24/P-25 pending)")
    return 1


def demo_cmd(args=None):
    print("Demo command: NOT_RUN. (Owning phase P-24 pending)")
    return 1


def deploy_cmd(args=None):
    print("Deploy command: NOT_RUN. (Owning phase P-28 pending)")
    return 1


def teardown_cmd(args=None):
    print("Teardown command: NOT_RUN. (Owning phase P-28 pending)")
    return 1


def build_parser():
    parser = argparse.ArgumentParser(description="ChangeMesh Canonical Command Interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Format
    parser_format = subparsers.add_parser(
        "format", help="Verify source code formatting (check-only)"
    )
    parser_format.set_defaults(func=format_cmd)

    # Lint
    parser_lint = subparsers.add_parser("lint", help="Lint source code")
    parser_lint.set_defaults(func=lint_cmd)

    # Type-check
    parser_typecheck = subparsers.add_parser("type-check", help="Type-check source code")
    parser_typecheck.set_defaults(func=typecheck_cmd)

    # Unit
    parser_unit = subparsers.add_parser("unit", help="Run unit tests (excluding real cloud tests)")
    parser_unit.set_defaults(func=unit_cmd)

    # Integration
    parser_integration = subparsers.add_parser(
        "integration", help="Run integration tests (requires live auth)"
    )
    parser_integration.add_argument(
        "--live-write-danger",
        action="store_true",
        help="Authorize REAL Google Cloud mutations",
    )
    parser_integration.set_defaults(func=integration_cmd)

    # E2E
    parser_e2e = subparsers.add_parser("e2e", help="Run end-to-end tests (deferred)")
    parser_e2e.set_defaults(func=e2e_cmd)

    # Demo
    parser_demo = subparsers.add_parser("demo", help="Run demo (deferred)")
    parser_demo.set_defaults(func=demo_cmd)

    # Deploy
    parser_deploy = subparsers.add_parser("deploy", help="Deploy infrastructure (deferred)")
    parser_deploy.set_defaults(func=deploy_cmd)

    # Teardown
    parser_teardown = subparsers.add_parser("teardown", help="Teardown infrastructure (deferred)")
    parser_teardown.set_defaults(func=teardown_cmd)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
