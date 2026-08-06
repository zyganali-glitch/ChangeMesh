# ChangeMesh Agent OS Rules

## 0. Authority hierarchy

1. `AGENTS.md`
2. `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`
3. `AGENT_ARCHITECTURE_AND_PATTERNS.md`
4. `AGENT_ENVIRONMENT_AND_API.md`
5. `AGENT_MEMORY_AND_LESSONS.md`
6. `docs/DECISION_LOG.md`
7. task-specific implementation files
8. agent suggestions and model output

A lower level cannot silently weaken a higher level.

## 1. Integrity Locks

- **IL-01 — Single Truth:** Master execution plan is official task state.
- **IL-02 — Atomic Status:** header, task, gate, evidence, risk, and handoff update together.
- **IL-03 — Evidence Closure:** no `DONE` without real evidence.
- **IL-04 — Time Integrity:** timestamps and chronology are real and timezone-labeled.
- **IL-05 — Gate Closure:** required `FAIL` or `NOT_RUN` blocks closure.
- **IL-06 — Header Parity:** plan header and task table agree.
- **IL-07 — Discovered Work:** new work is registered before implementation.
- **IL-08 — Live Tracking:** mark `IN_PROGRESS` before editing.
- **IL-09 — Reopen Protocol:** regression reopens task and dependent claims.
- **IL-10 — Cross-Surface Parity:** code, tests, docs, evidence, UI, and cloud agree.
- **IL-11 — Next-Step Validation:** announce only next dependency-satisfied task.
- **IL-12 — Triple Sync:** local, GitHub, and deployed revision parity is explicit.
- **IL-13 — Live Docs:** affected docs update in same closure.
- **IL-14 — Adapter Currency:** use current Antigravity `.agents/rules`, `.agents/skills`, `.agents/agents`.
- **IL-15 — Plan Before Code:** no work outside detailed master plan.
- **IL-16 — Collective Memory Sync:** update relevant memory pillars after every task.
- **IL-17 — Snapshot Lock:** create rollback point before each phase or risky change.
- **IL-18 — Claim/Evidence Lock:** public claims map to evidence or remain `PLANNED/NOT_RUN`.
- **IL-19 — Autonomy/Friction Lock:** no human approval where policy, rehearsal, and reversibility permit autonomous work.
- **IL-20 — Whole-Repo Consistency Lock:** every closure runs Phase `P-Ω`.

## 2. No-new-debt contract

Every task targets `Tech-Debt Delta = 0`: no dead/duplicated code, unbounded retry, hidden fallback, broad shared mutable state, unversioned schema, prompt-only contract where deterministic schema is possible, undocumented cloud resource, or test that passes without asserting mission-critical behavior.

## 3. Agent orchestration rules

- Development subagents are read-only unless active task explicitly grants a disjoint write allowlist.
- Product runtime agents are implemented in Google ADK; Antigravity development subagents are not product evidence.
- Orchestrator may delegate analysis but must verify returned findings.
- Shared governance documents have one writer.
- Sequential fallback is mandatory when parallel work risks conflicts.
- No nested delegation for governance or release decisions.

## 4. Product gates

Applicable features must pass contract/schema, state-transition, idempotency/replay, partial-failure recovery, stale-memory rejection, prompt-injection containment, capability-passport validity, reversibility classification, evidence immutability, semantic-audit authority, cloud revision parity, accessibility/responsive UI, cost/quota, competition mapping, and fixture/real separation gates.

## 5. Documentation triggers

| Change | Mandatory synchronized documents |
|---|---|
| User-visible feature/status | `README.md`, `README.tr.md`, plan, handoff |
| Architecture/module boundary | architecture memory, `docs/ARCHITECTURE.md`, plan |
| API/env/cloud resource | environment memory, setup docs, plan |
| Failure/lesson | lessons memory, handoff, relevant test notes |
| Product decision/tradeoff | `docs/DECISION_LOG.md`, architecture memory |
| Judge-facing claim | README, judging map, evidence boundary, submission draft |
| Demo sequence/UI | demo script, Turkish recording guide, screenshot manifest |
| Version/release/tag | submission manifest, README, judge start file |
| Competition rule change | plan compliance phase, judging map, submission draft |

## 6. Three-attempt protocol

1. Diagnose and apply the smallest grounded fix.
2. Inspect assumptions and use a different technical route.
3. Isolate with a reduced reproduction.
4. If still failing: stop, mark `BLOCKED`, preserve logs, update memory/handoff, and request only the necessary decision.

Repeating near-identical edits is forbidden.

## 7. Final truth

Edited is not validated. Validated is not deployed. Deployed is not production-proven. Simulated is not real. Model confidence is not evidence.
