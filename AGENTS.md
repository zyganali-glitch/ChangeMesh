# ChangeMesh — Supreme Development Constitution

This file is the highest operational authority for every coding agent, reviewer, subagent, script, workflow, and plan in this repository.

## 0. Frozen charter — no Phase-0 interview

The product charter has already been agreed and is frozen in `README.md`, `AGENT_ARCHITECTURE_AND_PATTERNS.md`, and `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.

Do **not** start or repeat a generic project interview. Ask the user a question only when all are true:

1. the decision blocks the active micro-task;
2. it cannot be derived from repository evidence, active plan, official requirements, or Collective Memory;
3. choosing a default could create irreversible cost, security exposure, rule violation, or product-direction drift;
4. the question is reduced to the smallest possible decision.

Questions must never substitute for inspecting the repository.

## 1. Mandatory startup sequence

Before code, commands, file edits, or architectural proposals:

1. Read `CHANGEMESH_RULES.md`.
2. Read `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
3. Read all four Collective Memory files.
4. Read `docs/HANDOFF.md`.
5. Inspect actual repository tree and Git status.
6. Identify the next `PENDING` micro-task whose dependencies are satisfied.
7. Mark exactly that task `IN_PROGRESS` before implementation.
8. Create or verify a safe snapshot/commit boundary.

Skipping this sequence makes the task `BLOCKED`.

## 2. Single source of execution truth

`plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md` is the only official execution state.

- Do not create an untracked private plan.
- Do not skip ahead because a later task looks easier.
- Do not mark work `DONE` without named evidence.
- Do not silently expand scope.
- Newly discovered work must be added as `[DISCOVERED]` under the closest parent phase.
- At most two implementation micro-tasks may be `IN_PROGRESS`, only if they modify disjoint surfaces.

## 3. Main-agent ownership

The primary conversational agent is the only writer for the master plan, governance files, Collective Memory, architecture and decision records, README, handoff, and judge-facing claims.

Subagents are reviewers and researchers by default. They may not edit shared governance or plan surfaces. A subagent result is advisory until the primary agent verifies it against repository evidence.

## 4. Product invariants

Every change must preserve:

1. **Autonomous by default:** human attention is an exception, not routine labor.
2. **Human-on-the-loop:** ask for authority only at irreducible or policy-defined boundaries.
3. **Evidence before escalation:** prepare a compressed decision packet first.
4. **Discovery is not trust:** route only to an exact agent revision with valid capability evidence.
5. **Memory is not truth:** decision-relevant memory needs type, source, scope, validity, and evidence.
6. **Simulation is not execution:** ShadowLab output remains `SIMULATED`.
7. **Blocked means not executed:** a blocked action remains `NOT_RUN`.
8. **Model opinion is not machine fact:** semantic evaluation cannot rewrite deterministic evidence.
9. **Google-native runtime:** ADK + Gemini + Google Cloud are product runtime requirements.
10. **No generic-agent drift:** product remains focused on proof-carrying enterprise change.

## 5. Honesty boundary

Use only: `PASS`, `WARN`, `FAIL`, `NOT_RUN`, `SIMULATED`, `BLOCKED`, `QUARANTINED`.

Forbidden:

- presenting planned work as implemented;
- presenting fixture output as production evidence;
- replacing a failed cloud integration with a mock and calling it real;
- changing `FAIL` to `PASS` because a model disagrees;
- claiming security, compliance, or production readiness without named tests;
- hiding skipped checks.

## 6. Scope and safety

- Inspect before editing.
- Prefer additive, modular changes.
- Avoid ambiguous files such as `utils.py`, `helpers.ts`, or `common.js`.
- No destructive command without explicit task scope and preflight.
- No secrets in source, logs, fixtures, screenshots, prompts, evidence packs, or commits.
- No production customer data.
- No automatic merge or production deployment in the competition MVP.
- External writes must be idempotent or protected by a recorded idempotency key.
- After three failed attempts on one root cause, stop, record evidence, and change strategy or escalate.

## 7. Mandatory task closure protocol

A micro-task cannot become `DONE` until the primary agent:

1. runs task-specific tests and gates;
2. records exact commands and results;
3. inspects `git diff` and changed-file scope;
4. checks dead code, unused imports, placeholders, and accidental truncation;
5. re-scans the entire repository for contradictory names, versions, statuses, claims, paths, and architecture;
6. updates master plan status and evidence;
7. updates `README.md` when user-visible behavior, setup, architecture, evidence, or project status changed;
8. updates architecture memory when a contract, dependency, schema, state machine, or module boundary changed;
9. updates environment memory when commands, services, ports, variables, credentials, quotas, cloud resources, or external contracts changed;
10. updates lessons memory when a failure, workaround, risky pattern, or reusable lesson was discovered;
11. updates `docs/DECISION_LOG.md` for meaningful tradeoffs or product decisions;
12. updates `docs/HANDOFF.md` with current state and next exact task;
13. updates all affected judge-facing documents and screenshot manifests;
14. verifies every edited document matches code and evidence;
15. only then marks the task `DONE`.

## 8. Continuous whole-repository integrity phase

Phase `P-Ω` in the master plan is always active.

After every task verify implementation↔tests, implementation↔architecture, implementation↔README, plan↔repository, claims↔evidence, local↔GitHub↔cloud revision, English↔Turkish surfaces, demo↔actual UI/runtime, and Devpost narrative↔final frozen tag.

Any contradiction reopens the relevant task and blocks progression.

## 9. Required completion report

Every completion report must contain:

1. active micro-task ID;
2. files changed;
3. what was actually implemented;
4. commands run and exact outcomes;
5. evidence states;
6. open risks and `NOT_RUN` checks;
7. documentation synchronized;
8. whole-repository integrity result;
9. next eligible micro-task.

Do not provide a confidence-only completion summary.


## 10. Donor Repository Reuse Lock — Binding Addendum

Before any donor-sensitive implementation, the primary agent must:

1. read `docs/DONOR_REUSE_MANIFEST.md` and the master-plan donor amendment;
2. confirm `P-02D` is `DONE`;
3. open the relevant `P-xx.00` donor preflight and mark it `IN_PROGRESS`;
4. inspect the exact immutable donor commit and allowlisted source paths;
5. confirm license state, approved reuse method, exact target mapping, forbidden carry-over, and required tests;
6. run the read-only `donor-reuse-auditor`;
7. update the donor manifest before product code;
8. run P-DΩ and P-Ω before closure.

Donor repositories are read-only. No agent may modify them, import them wholesale, use a moving branch as provenance, or implement from remembered behavior. An incomplete or unpinned donor entry makes the task `BLOCKED`.

Shared donor/governance/provenance files remain single-writer surfaces owned by the primary agent. Subagents may inspect and challenge but may not edit them.
