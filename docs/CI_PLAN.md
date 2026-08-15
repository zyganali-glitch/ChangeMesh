# ChangeMesh — Continuous Integration (CI) Plan

This plan defines the intended execution order and failure behavior for the ChangeMesh canonical command interface within a continuous integration environment.

**Note:** Actual CI pipeline implementation (e.g., GitHub Actions workflows) is deferred to future Master Plan phases. This document serves as the design contract.

## 1. Safe Commands (Ordinary Pull Request Validation)

The following commands are deterministic, local, and safe. They must run on all ordinary pull requests.

1. **`format`**: Verifies source code formatting (`ruff format --check`). Fails if code is unformatted.
2. **`lint`**: Verifies code quality (`ruff check`). Fails if violations exist.
3. **`type-check`**: Verifies type safety (`mypy`). Fails if type errors exist.
4. **`unit`**: Runs local, deterministic unit tests. Explicitly excludes integration tests that require live cloud mutations or credentials.

### Execution Order & Failure Behavior
- **Order:** Run sequentially or in parallel.
- **Failure:** Any non-zero exit code must immediately fail the CI job.
- **Credentials:** No secrets or GCP credentials are required for these checks.

## 2. Guarded Commands (Requires Credentials or Explicit Authority)

The following commands interact with real external infrastructure or mutate state. They must **not** run automatically on ordinary untrusted PRs.

- **`integration`**: Performs REAL Google Cloud mutations.
  - *Current Status:* Fails closed by default. Requires `--live-write-danger` to authorize.
  - *CI Usage:* Should only run on trusted branches (e.g., `main` merges) or on PRs when explicitly triggered by authorized maintainers via labels. Requires secure injection of GCP Workload Identity.

## 3. Deferred Commands (Future Phase Ownership)

The following commands represent capabilities owned by future Master Plan phases.

- **`e2e`**: End-to-end product workflow (P-24/P-25).
- **`demo`**: Synthetic demo implementation (P-24).
- **`deploy`**: Deployment infrastructure (P-28).
- **`teardown`**: Resource teardown (P-28).

### Execution Behavior
- *Current Status:* These commands exist in the canonical interface but currently fail closed (`exit 1`) and print `NOT_RUN`, clearly indicating that the owning phase is pending.
- *CI Usage:* They must remain disabled or explicitly excluded in CI until their respective implementation phases are completed.
- *Future State:* Once implemented, `e2e` and `demo` will likely join guarded CI runs, while `deploy` and `teardown` will be restricted to deployment workflows (e.g., tags or scheduled CD jobs). Live deploy/teardown must never run on ordinary PRs to prevent unauthorized infrastructure changes and cost overruns.
