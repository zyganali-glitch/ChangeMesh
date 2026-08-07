---
name: donor-reuse-preflight
description: Performs the mandatory pinned-source, license, source-to-target, and parity-test preflight before any donor-derived ChangeMesh implementation.
---

# Donor Reuse Preflight

## Inputs

- active master-plan P-xx.00 task;
- `docs/DONOR_REUSE_MANIFEST.md`;
- immutable donor commit;
- exact source-path allowlist;
- ChangeMesh architecture and target contracts.

## Procedure

1. Confirm P-02D is DONE and the component is not PIN_REQUIRED/BLOCKED.
2. Verify donor repository is read-only and current worktree is ChangeMesh.
3. Verify immutable commit and exact source paths.
4. Read only approved source files and minimum related tests/docs.
5. Extract observable invariants; distinguish source behavior from marketing text.
6. Confirm license/notice state and approved reuse method.
7. Compare with existing ChangeMesh code to prevent duplicate implementations.
8. Fix exact target paths/contracts and required transformations.
9. List forbidden provider/framework/product carry-over.
10. Define positive, failure, boundary, security, and forbidden-carry-over tests.
11. Invoke `donor-reuse-auditor` read-only.
12. Record evidence in manifest and active plan; only then unlock implementation.

## Closure

Run P-DΩ and P-Ω.12. Any missing field, source drift, license ambiguity, or unresolved auditor finding is BLOCKED.
