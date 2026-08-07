# ChangeMesh — Child Plan Template

Use this only when discovered work is too large for one embedded master-plan micro-task.

## 0. Identity

- Plan ID:
- Parent master task:
- Owner:
- Status: `PLANNING`
- Created:
- Last updated:
- Scope:
- Out of scope:
- Allowed files:
- Forbidden files/actions:
- Dependencies:
- Required evidence:
- Required documentation sync:

## 1. Frozen contracts

List exact architecture, product, evidence, autonomy, privacy, and competition contracts that this plan must preserve.

## 2. Micro-tasks

For every micro-task include ID/status, exact action, files, forbidden shortcuts, acceptance criteria, commands/tests, evidence path, documentation updates, dependencies, and next task.

## 3. Gate matrix

| Gate | Command or review | Expected | Result | Evidence |
|---|---|---|---|---|
| Scope | | PASS | NOT_RUN | |
| Tests | | PASS | NOT_RUN | |
| Security | | PASS | NOT_RUN | |
| Integrity | Phase P-Ω | PASS | NOT_RUN | |
| Docs | Live-doc sync | PASS | NOT_RUN | |

## 4. Risks and discovered work

Register new work before implementation.

## 5. Closure

A child plan closes only after all tasks have evidence, no required gate is `FAIL/NOT_RUN`, docs are synchronized, whole-repo consistency passes, and the plan moves to `plans/completed/` in the same closure commit.
