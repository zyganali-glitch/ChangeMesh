# ChangeMesh Donor Reuse Manifest

> **Status:** `PRE-IMPLEMENTATION / BINDING`  
> **Owner:** Primary ChangeMesh agent  
> **Source policy:** Donor repositories are read-only; immutable commit and exact source paths are mandatory.  
> **Execution gate:** No donor-derived implementation may begin until `P-02D` and the relevant `P-xx.00` preflight pass.

## 1. Purpose

This file is the canonical source-to-target ledger for all pre-existing owner repositories used to inform ChangeMesh. It prevents five failure modes:

1. ignoring useful proven work and rebuilding it badly;
2. copying entire repositories and importing irrelevant debt;
3. losing exact source, license, and build-period provenance;
4. carrying provider/framework-specific assumptions into Google ADK/Gemini;
5. presenting pre-existing behavior as newly created during the competition.

## 2. Mandatory statuses and methods

### Entry status

- `DISCOVERED`
- `PIN_REQUIRED`
- `UNDER_REVIEW`
- `BLOCKED`
- `APPROVED_FOR_IMPLEMENTATION`
- `IMPLEMENTED_PENDING_PARITY`
- `VERIFIED`
- `EXCLUDED`
- `SUPERSEDED`

### Reuse method

- `COPIED`
- `ADAPTED`
- `CLEAN_ROOM_REIMPLEMENTED`
- `IDEA_ONLY`
- `REFERENCE_ONLY`

A blank or inferred field is invalid. Unknown license, source pin, source path, or required test is blocking.

## 3. Donor registry

| Donor ID | Repository | Pinned source | Primary reusable value | Hard prohibition |
|---|---|---|---|---|
| `D-UAOS` | `zyganali-glitch/Universal-Agent-OS` | `6b83b06212101c238ec28076a2ba7ae819f483f2` | live plan, Collective Memory, evidence-first closure, completed-plan archive | no generic Phase-0, no donor runtime/CLI/MCP bulk copy |
| `D-UIPATH` | `zyganali-glitch/universal-agent-os-uipath` | `dc2267939c2aef0aba2737da65f53352c5cf8fb2` | durable process state, independently verified authority decision, real/mock connector honesty | no UiPath runtime, Action Center, Data Service, or Phase-0 dependency |
| `D-CCT` | `zyganali-glitch/codex-control-tower` | `65ee1b72faf9a7202d9166eed43fb671804815a8` | locked evidence states, Flight Recorder, destructive preflight, blind semantic challenge, judge package | no Codex/OpenAI/GPT-specific runtime dependency or model-overwrites-facts behavior |
| `D-ZEROKIT` | `zyganali-glitch/zerokit-ai-control-plane` | `d663db8c706cb914e1af5caf651df08edb5c50c0` | privacy preflight, synthetic-data boundary, strict artifact validation, hash manifest, claim audit | no ZeroKit product/admin semantics or Codex/GPT provider assumptions |
| `D-CONTEXTSEAL` | `zyganali-glitch/ContextSeal` | `0dc924db9d82037d2e813548bdee27af5f180889` | lineage/blast radius, expand–migrate–contract, bounded writeback, passport/evidence contract | no hard DataHub coupling or unapproved live writeback |
| `D-QWEN` | `gitlab.com/zyganali/universal-agent-os-qwen` | `EXCLUDED_UNAVAILABLE` | hybrid recall, freshness/importance/decay, shared memory bus | no Qwen runtime dependency, Phase-0 carry-over, or memory-as-truth |
| `D-GITLAB` | `gitlab.com/zyganali/universal-agent-os-gitlab-edition` | `EXCLUDED_UNAVAILABLE` | real MR overlap/blast-radius, ownership/conflict context, unavailable-tool honesty | no GitLab Duo/Orbit dependency in GitHub-first MVP or fabricated GraphQL evidence |

## 4. Component record schema

Every component record must contain:

```yaml
component_id: DONOR-COMPONENT-NNN
status: DISCOVERED | PIN_REQUIRED | UNDER_REVIEW | BLOCKED | APPROVED_FOR_IMPLEMENTATION | IMPLEMENTED_PENDING_PARITY | VERIFIED | EXCLUDED | SUPERSEDED
donor_id: D-...
repository: owner/repo or GitLab URL
source_commit: immutable SHA
source_paths:
  - exact/path
license_state: VERIFIED_COMPATIBLE | VERIFIED_REQUIRES_NOTICE | OWNER_AUTHORED_RULES_PENDING | UNKNOWN_BLOCKED
source_behavior:
  - observable invariant
reuse_method: COPIED | ADAPTED | CLEAN_ROOM_REIMPLEMENTED | IDEA_ONLY | REFERENCE_ONLY
target_paths_or_contracts:
  - exact/path or contract to be created
required_transformations:
  - provider/framework/product-specific change
forbidden_carry_over:
  - prohibited identifier/dependency/behavior
required_tests:
  - positive
  - failure
  - boundary
  - security
  - forbidden-carry-over
competition_introduction_commit: PENDING until implemented
evidence:
  - source inspection
  - test artifact
reviewer: primary agent + donor-reuse-auditor
last_reviewed: ISO-8601
```

## 5. Initial component inventory

### D-UAOS — Universal Agent OS

#### UAOS-GOV-001 — Live plan and evidence-first closure

- **Status:** `APPROVED_FOR_IMPLEMENTATION`
- **Pinned commit:** `6b83b06212101c238ec28076a2ba7ae819f483f2`
- **Source paths:** `AGENTS.md`; `tr/AGENT_OS_RULES.md`; `tr/AGENT_OS_PLAN_TEMPLATE.md`; `cli/verify.js`; `cli/status.js`.
- **Source behavior:** one official task table, plan-before-code, gate/evidence closure, live documentation, completed-plan archive.
- **Reuse method:** `ADAPTED` for governance text/patterns.
- **License State:** `VERIFIED_COMPATIBLE` (MIT)
- **ChangeMesh target paths:** `AGENTS.md`; `AGENT_OS_RULES.md`; `AGENT_OS_PLAN_TEMPLATE.md`; `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`; `.agents/rules/*`; `.agents/skills/*`.
- **Required transformation:** remove generic Phase-0; preserve frozen charter, autonomy, donor lock, P-Ω.
- **Forbidden carry-over:** donor CLI/runtime/MCP/examples, locale packs, generic product claims, mandatory interview.
- **Required tests:** governance file presence; no Phase-0 instruction; plan task status/evidence parity; live-doc closure; completed-plan archive behavior.

#### UAOS-MEM-001 — Four Collective Memory pillars

- **Status:** `IMPLEMENTED_PENDING_PARITY`.
- **Pinned commit:** same as D-UAOS.
- **Source path:** `skills/agent-os-memory/SKILL.md` plus governance references.
- **Source behavior:** read/update lessons, architecture, environment/API, and user preferences.
- **Reuse method:** `ADAPTED`.
- **ChangeMesh target paths:** four root memory files and `.agents/skills/agentos-memory/SKILL.md`.
- **Required transformation:** store durable project facts only; add donor manifest/handoff; no private chain-of-thought or secrets.
- **Forbidden carry-over:** generic initialization that overwrites ChangeMesh decisions.
- **Required tests:** startup-read references, task-closure updates, no-secret/no-private-reasoning checks.

### D-UIPATH — Universal Agent OS UiPath Edition

#### UIPATH-STATE-001 — Durable process state and resume

- **Status:** `DISCOVERED`.
- **Pinned commit:** `dc2267939c2aef0aba2737da65f53352c5cf8fb2`.
- **Source paths:** `uipath_project/workflows/README.md`; `uipath_project/workflows/phase0_alignment.bpmn`; `HANDOFF.md`.
- **Source behavior:** persisted workflow state, wait/resume, explicit process transitions and handoff.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED`.
- **Planned target:** P-10 Firestore saga and P-20 recovery/resume modules.
- **Required transformation:** ADK + Pub/Sub + Firestore; no UiPath runtime or Phase-0 semantics.
- **Forbidden carry-over:** Maestro/Action Center/Data Service IDs and dependencies.
- **Required tests:** restart resume, no duplicate action, legal/illegal transition, timeout, cancellation, compensation.

#### UIPATH-AUTH-001 — Independent authority verification

- **Status:** `DISCOVERED`.
- **Source paths:** `backend/uipath_api_connector.py`; `tests/test_uipath_connector_modes.py`; `docs/evidence_manifest.md`; `docs/labs_evidence_checklist.md`.
- **Source behavior:** authority result verified through a system/API record rather than trusted from chat; real/mock mode kept explicit.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED` plus `REFERENCE_ONLY` for evidence-document structure.
- **Planned target:** Approval Compression, approval repository, connector mode/evidence boundary.
- **Required transformation:** exception-only human authority; reusable scoped/expiring approval.
- **Forbidden carry-over:** routine approval per step; mock as real; UiPath API contract.
- **Required tests:** forged chat approval rejected; expired/scope-mismatched decision rejected; valid reusable decision accepted; local adapter labeled.

### D-CCT — Codex Control Tower

#### CCT-EVID-001 — Locked deterministic evidence states

- **Status:** `DISCOVERED`.
- **Pinned commit:** `65ee1b72faf9a7202d9166eed43fb671804815a8`.
- **Source paths:** `cli/commands/evidence.js`; `tests/test_evidence_pack.js`; `docs/ARCHITECTURE.md`.
- **Source behavior:** named evidence states; `NOT_RUN` and simulation boundaries; model cannot rewrite local facts.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED` or `ADAPTED` after license review.
- **Planned target:** P-05 EvidenceRecord; P-22 ledger/passport; P-25 tests.
- **Required transformation:** ADK/tool events, Change ID, agent revision, cloud trace references.
- **Forbidden carry-over:** Codex event assumptions, GPT-specific fields, InvoiceFlow fixture names.
- **Required tests:** model disagreement cannot change facts; blocked remains not-run; simulated remains simulated; tamper detection.

#### CCT-FLIGHT-001 — Flight Recorder

- **Status:** `DISCOVERED`.
- **Source paths:** `core/workflows/flight-recorder.md`; `core/templates/FLIGHT_RECORDER_TEMPLATE.md`; `cli/commands/flight-recorder.js`; `apps/dashboard/src/components/FlightRecorderPanel.jsx`.
- **Source behavior:** chronological execution/evidence record and judge-inspectable summary.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED`; UI is `REFERENCE_ONLY`.
- **Planned target:** Pub/Sub causal event timeline, evidence ledger, dashboard.
- **Required transformation:** distributed causal chain, correlation/causation IDs, agent/tool revisions, OpenTelemetry links.
- **Forbidden carry-over:** local-only chronology, Codex-specific event names, copied UI styling without review.
- **Required tests:** duplicate/out-of-order event handling, causal ordering, redaction, restart continuity.

#### CCT-PREFLIGHT-001 — Destructive Action Preflight

- **Status:** `DISCOVERED`.
- **Source paths:** `cli/lib/destructiveActionPreflight.js`; `cli/commands/destructive-preflight.js`; `.codex/hooks/destructive-preflight.js`; `apps/dashboard/src/components/DestructiveActionPreflightPanel.jsx`.
- **Source behavior:** canonicalize target, compare protected boundaries, block before execution, preserve `NOT_RUN`.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED`.
- **Planned target:** ShadowLab scenario authorization and Reversibility Gate.
- **Required transformation:** schema/database/API/GitHub action classes rather than filesystem deletion only.
- **Forbidden carry-over:** Codex hook dependency, shell-command execution, repository-subpath-as-safety-clearance.
- **Required tests:** destructive target blocked pre-tool; no command executed; ambiguous target fails closed; reversible action classified separately.

#### CCT-SEM-001 — Blind semantic challenge and reconciliation

- **Status:** `DISCOVERED`.
- **Source paths:** `docs/ARCHITECTURE.md`; `JUDGE_START_HERE.md`; `docs/JUDGING_MAP.md`; evidence/audit implementation paths to be enumerated by P-02D.06.
- **Source behavior:** independent model assesses whether evidence semantically proves mission; expected result withheld; conflict triggers review but cannot overwrite facts.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED`.
- **Planned target:** Gemini Evidence Auditor.
- **Required transformation:** Gemini 3.5+, ADK-compatible bounded audit bundle, citation enforcement.
- **Forbidden carry-over:** GPT-5.6/Codex runtime, expected-answer labels, model as execution authority.
- **Required tests:** expected-label leakage scan; uncited decisive answer rejection; deterministic reconciliation; controlled mission gap.

#### CCT-JUDGE-001 — Judge and release evidence package

- **Status:** `REFERENCE_ONLY` pending final method review.
- **Source paths:** `JUDGE_START_HERE.md`; `docs/JUDGING_MAP.md`; `docs/DEMO_SCRIPT.md`; `docs/SUBMISSION_MANIFEST.md`; `DEVPOST_SCREENSHOTS.md`; `docs/TRACEABILITY_MATRIX.md`; `docs/BUILD_WEEK_DELTA.md`; `docs/DEVPOST_SUBMISSION.md`.
- **Source behavior:** fast judge route, requirement-to-evidence map, demo timing, immutable release, build-period delta, screenshot/claim discipline.
- **Planned target:** existing ChangeMesh judge/submission documents.
- **Forbidden carry-over:** old links, numbers, model names, evidence results, competition language, screenshots.
- **Required tests:** link/status/version/claim parity; final tag/cloud/video alignment.

### D-ZEROKIT — ZeroKit AI Control Plane

#### ZK-PRIV-001 — Privacy preflight and synthetic-only boundary

- **Status:** `DISCOVERED`.
- **Pinned commit:** `d663db8c706cb914e1af5caf651df08edb5c50c0`.
- **Source paths:** `ai-buildweek/reports/privacy-boundary.md`; `README.md`; relevant workflow path to be confirmed in P-02D.07.
- **Source behavior:** prevent sensitive/real data from entering model workflow; explicitly separate synthetic fixture.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED`.
- **Planned target:** Gemini input minimization, Policy Guardian, demo fixture boundary.
- **Forbidden carry-over:** school-SaaS data, Codex/GPT fields, ZeroKit product semantics.
- **Required tests:** secret/PII fixture blocked/redacted; synthetic mode explicit; model request contains only allowlisted fields.

#### ZK-VALID-001 — Strict generated-artifact validation

- **Status:** `DISCOVERED`.
- **Source paths:** `ai-buildweek/reports/validator-coverage.md`; `frontend/js/ai-config-preview.js`; `ai-buildweek/evidence/school-saas.gpt-5.6.codex.config.manifest.json`.
- **Source behavior:** generated artifact must match explicit schema/allowlist and manifest; malformed/extra fields fail.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED`.
- **Planned target:** domain contracts, Gemini structured output, migration artifacts, evidence/passport validators.
- **Forbidden carry-over:** ZeroKit configuration schema, frontend globals, GPT-specific manifest fields.
- **Required tests:** missing/extra/wrong-type/path traversal/unsafe endpoint/unknown action cases.

#### ZK-CLAIM-001 — Claim audit and build delta

- **Status:** `REFERENCE_ONLY`.
- **Source paths:** `ai-buildweek/reports/jury-claim-audit.md`; `ai-buildweek/reports/build-week-delta.md`; `ai-buildweek/submission/DEVPOST_SUBMISSION_GUIDE.md`; demo/screenshot guides.
- **Source behavior:** map public statements to evidence and distinguish build-period work.
- **Planned target:** competition-claim-audit, build disclosure, Devpost and screenshot review.
- **Forbidden carry-over:** old claims, scores, evidence states, links, provider names.
- **Required tests:** unsupported-claim scanner and cross-document parity.

### D-CONTEXTSEAL — ContextSeal

#### CS-BLAST-001 — Path-preserving lineage and blast radius

- **Status:** `DISCOVERED`.
- **Pinned commit:** `0dc924db9d82037d2e813548bdee27af5f180889`.
- **Source paths:** `src/datahub/live-context.js`; `src/core/risk.js`; `src/core/workflow.js`; lineage evaluation fixtures; `docs/ARCHITECTURE.md`.
- **Source behavior:** preserve multi-hop dependency paths, owners, truncation/incompleteness, and risk context.
- **Proposed method:** `ADAPTED` or `CLEAN_ROOM_REIMPLEMENTED` after license/language decision.
- **Planned target:** Impact Scout graph and merged blast-radius artifact.
- **Required transformation:** GitHub repository findings plus synthetic metadata graph; optional DataHub adapter.
- **Forbidden carry-over:** hard DataHub requirement, silent truncated lineage, ContextSeal terminology.
- **Required tests:** multi-hop path, cycles, truncation, missing owner, duplicate merge, contradictory sources.

#### CS-MIG-001 — Expand–migrate–contract workflow

- **Status:** `DISCOVERED`.
- **Source paths:** `src/core/workflow.js`; `skills/datahub-schema-change-certification/SKILL.md`; `skills/datahub-schema-change-certification/scripts/certify_change.py`; `config/policy.json`.
- **Source behavior:** reject direct breaking mutation; create additive migration, compatibility, verification, rollback, and deferred-removal plan.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED` with possible adapted policy fixtures.
- **Planned target:** Migration Engineer and ShadowLab correction.
- **Forbidden carry-over:** direct live writeback, DataHub-only artifact format, pre-existing demo claims.
- **Required tests:** legacy client, dual write, backfill interruption, rollback, deferred removal, missing dependency.

#### CS-PASS-001 — Change passport and evidence contract

- **Status:** `DISCOVERED`.
- **Source paths:** `src/core/passport.js`; `scripts/validate-evidence.js`; `skills/datahub-schema-change-certification/references/evidence-contract.md`; `skills/datahub-schema-change-certification/templates/certification-report.template.md`; `docs/EVIDENCE_BOUNDARY.md`.
- **Source behavior:** bind change context, policy, evidence, artifact hashes, and review packet into a verifiable package.
- **Proposed method:** `ADAPTED` or `CLEAN_ROOM_REIMPLEMENTED` after convergence with CCT evidence model.
- **Planned target:** Change Evidence Passport.
- **Required transformation:** agent revisions/delegation, ShadowLab, memory trust, OpenTelemetry, external receipts.
- **Forbidden carry-over:** duplicate passport implementation, ContextSeal field names as unreviewed contract.
- **Required tests:** canonical serialization, tamper, missing artifact, wrong revision, stale approval, deterministic verify.

#### CS-WRITE-001 — Bounded writeback and PR bundle

- **Status:** `DISCOVERED`.
- **Source paths:** `src/datahub/writeback.js`; `scripts/build-pr-bundle.js`; `docs/PR_REVIEW_PACKET.md`; `docs/BRANCH_RECONCILIATION_MATRIX.md`.
- **Source behavior:** constrain external write, generate review packet, preserve branch/change reconciliation.
- **Proposed method:** `CLEAN_ROOM_REIMPLEMENTED`.
- **Planned target:** GitHub draft-PR adapter and Release Steward.
- **Forbidden carry-over:** DataHub writeback, automatic merge, unscoped target, missing idempotency.
- **Required tests:** dry run, allowlist, duplicate replay, outside target, conflict, receipt creation.

### D-QWEN — Qwen MemoryAgent

#### QW-MEM-001 — Hybrid retrieval and freshness/importance/decay

- **Status:** `PIN_REQUIRED`.
- **Repository:** `https://gitlab.com/zyganali/universal-agent-os-qwen`.
- **Pinned commit/source paths/license:** **must be resolved by P-02D.09 before use**.
- **Known candidate behavior:** BM25/embedding/keyword recall, freshness, importance, decay.
- **Proposed method:** likely `CLEAN_ROOM_REIMPLEMENTED` or `IDEA_ONLY`; no decision until source pin and license review.
- **Planned target:** Memory Trust Layer retrieval/ranking only; trust authority remains new ChangeMesh logic.
- **Forbidden carry-over:** Qwen runtime/provider, Phase-0, memory-as-truth, unbounded vector/RAG infrastructure.
- **Required tests after pin:** relevance, stale-memory demotion, high-importance retention, deterministic trust override, poisoned-memory quarantine.

#### QW-BUS-001 — Shared multi-agent memory bus

- **Status:** `PIN_REQUIRED`.
- **Known candidate behavior:** multi-agent memory exchange/MCP tools.
- **Planned target:** scoped memory references and saga handoff, not unrestricted shared mutable memory.
- **Required transformations/tests:** exact paths and invariants must be filled in P-02D.09; cross-agent scope, tenant isolation, provenance, replay, and no-secret tests mandatory.

### D-GITLAB — Universal Agent OS GitLab Edition

#### GL-CONFLICT-001 — MR/repository conflict and ownership context

- **Status:** `PIN_REQUIRED`.
- **Repository:** `https://gitlab.com/zyganali/universal-agent-os-gitlab-edition`.
- **Pinned commit/source paths/license:** **must be resolved by P-02D.10 before use**.
- **Known candidate behavior:** real overlapping MR blast radius, ownership and parallel-change risk.
- **Proposed method:** likely `CLEAN_ROOM_REIMPLEMENTED`.
- **Planned target:** Impact Scout and GitHub pre-draft-PR conflict check.
- **Forbidden carry-over:** GitLab Duo/Orbit/GraphQL runtime dependency in MVP, fabricated tool results, GitLab-only IDs.
- **Required tests after pin:** overlap/no-overlap, stale PR data, unavailable API, owner ambiguity, honest `NOT_RUN`.

#### GL-HONEST-001 — Unavailable-tool honesty

- **Status:** `PIN_REQUIRED`.
- **Known candidate behavior:** preserve unavailable external/tool results rather than fabricate success.
- **Planned target:** connector/evidence boundary across GitHub, metadata graph, and optional managed services.
- **Required transformations/tests:** exact source paths and method must be frozen in P-02D.10; unavailable/permission/timeout/rate-limit states remain explicit.

## 6. Cross-donor convergence decisions to be frozen in P-02D

| ChangeMesh responsibility | Primary donor evidence | Secondary donor evidence | Required canonical outcome |
|---|---|---|---|
| Development governance | D-UAOS | D-CCT judge discipline | ChangeMesh AGENTS/rules/plan only |
| Saga state | D-UIPATH | D-CONTEXTSEAL workflow | Firestore/PubSub state machine |
| Evidence states/ledger | D-CCT | D-CONTEXTSEAL, D-ZEROKIT | one EvidenceRecord and ledger authority |
| Passport | D-CONTEXTSEAL | D-CCT evidence pack, D-ZEROKIT manifest | one Change Evidence Passport schema |
| Memory retrieval | D-QWEN | D-UIPATH handoff | retrieval separated from trust |
| Memory trust | new ChangeMesh | D-ZEROKIT privacy, D-CCT fact lock | typed/provenanced/expiring/quarantined memory |
| Preflight/rehearsal | D-CCT | D-ZEROKIT, D-UIPATH | ShadowLab scenario system |
| Autonomy/approval | new ChangeMesh | D-UIPATH, D-CCT, D-CONTEXTSEAL | Reversibility Gate + Approval Compression |
| Blast radius | D-CONTEXTSEAL | D-GITLAB | repo + metadata path-preserving graph |
| Migration | D-CONTEXTSEAL | new ChangeMesh automation | expand–migrate–contract artifacts |
| Semantic audit | D-CCT | D-ZEROKIT validators | Gemini advisory auditor, facts locked |
| GitHub release preparation | D-CONTEXTSEAL | D-GITLAB, D-UIPATH connector modes | draft PR only, idempotent receipts |
| Judge/submission package | D-CCT | D-ZEROKIT, D-CONTEXTSEAL, D-UIPATH | ChangeMesh-only facts/links/evidence |

## 7. Implementation gate checklist

Before a phase's original `.01` task:

- [ ] P-02D is DONE.
- [ ] Relevant donor entry is approved, pinned, and licensed.
- [ ] Exact source files were read at the pinned commit.
- [ ] Source behavior/invariants are written.
- [ ] Reuse method is fixed.
- [ ] Exact target path/contract is fixed.
- [ ] Forbidden carry-over is listed.
- [ ] Positive/failure/boundary/security/forbidden tests are defined.
- [ ] Donor-reuse auditor has no blocking finding.
- [ ] Active `P-xx.00` has evidence and P-DΩ/P-Ω pass.

## 8. Final release gate

No final tag/release until every used component is `VERIFIED`, every source pin and license is recorded, every introduction commit is known, all required notices exist, all parity/intentional-delta tests pass, and public build-period disclosures agree.
