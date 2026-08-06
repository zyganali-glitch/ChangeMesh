---
name: task-closure-integrity
description: Performs mandatory ChangeMesh task closure, live-document synchronization, and whole-repository contradiction audit.
---

# Task Closure Integrity

Use before marking any plan task `DONE`.

1. Confirm task was `IN_PROGRESS`.
2. Run named task tests and capture exact outcomes.
3. Inspect changed files and `git diff`.
4. Search repository for old names, stale status labels, outdated paths, duplicate contracts, and conflicting claims.
5. Evaluate documentation triggers in `docs/DOCUMENT_SYNC_MATRIX.md`.
6. Update plan, README, memory, architecture, environment, decision log, handoff, and competition documents as applicable.
7. Verify public claims against named evidence.
8. Record honest evidence state.
9. Reopen dependent tasks whose evidence became invalid.
10. Report only next dependency-satisfied task.
