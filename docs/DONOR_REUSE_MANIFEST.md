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
| `D-QWEN` | `gitlab.com/zyganali/universal-agent-os-qwen` | `a43b3411856f41a4be9424d11c01a5e637cdc410` | hybrid recall, freshness/importance/decay, shared memory bus | no Qwen runtime dependency, Phase-0 carry-over, or memory-as-truth |
| `D-GITLAB` | `gitlab.com/zyganali/universal-agent-os-gitlab-edition` | `3c4a412b6040d8a8154c15325943c409be9105f2` | real MR overlap/blast-radius, ownership/conflict context, unavailable-tool honesty | no GitLab Duo/Orbit dependency in GitHub-first MVP or fabricated GraphQL evidence |

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

### UAOS-GOV-001

```yaml
component_id: UAOS-GOV-001
status: VERIFIED
donor_id: D-UAOS
repository: zyganali-glitch/Universal-Agent-OS
source_commit: 6b83b06212101c238ec28076a2ba7ae819f483f2
source_paths:
  - cli/verify.js
  - cli/status.js
  - tr/AGENT_OS_RULES.md
  - tests/test_governance.py
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - one official task table, plan-before-code, gate/evidence closure, live documentation, completed-plan archive
reuse_method: ADAPTED
target_paths_or_contracts:
  - AGENTS.md
  - CHANGEMESH_RULES.md
  - CHANGEMESH_PLAN_TEMPLATE.md
  - plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md
  - .agents/rules/00-changemesh-constitution.md
  - .agents/rules/10-live-plan-and-docs-lock.md
  - .agents/skills/changemesh-memory/SKILL.md
  - .agents/skills/donor-reuse-preflight/SKILL.md
  - .agents/skills/task-closure-integrity/SKILL.md
  - .agents/skills/competition-claim-audit/SKILL.md
required_transformations:
  - remove generic Phase-0; preserve frozen charter, autonomy, donor lock, P-Ω
forbidden_carry_over:
  - donor CLI/runtime/MCP/examples, locale packs, generic product claims, mandatory interview
required_tests:
  - governance file presence
  - no Phase-0 instruction
  - plan task status/evidence parity
  - live-doc closure
  - completed-plan archive behavior
  - forged plan updates rejected
  - unauthorized modification blocked
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### UAOS-MEM-001

```yaml
component_id: UAOS-MEM-001
status: VERIFIED
donor_id: D-UAOS
repository: zyganali-glitch/Universal-Agent-OS
source_commit: 6b83b06212101c238ec28076a2ba7ae819f483f2
source_paths:
  - skills/agent-os-memory/SKILL.md
  - en/AGENT_MEMORY_AND_LESSONS.md
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - read/update lessons, architecture, environment/API, and user preferences
reuse_method: ADAPTED
target_paths_or_contracts:
  - AGENT_MEMORY_AND_LESSONS.md
  - AGENT_ARCHITECTURE_AND_PATTERNS.md
  - AGENT_ENVIRONMENT_AND_API.md
  - AGENT_USER_PREFERENCES.md
  - .agents/skills/changemesh-memory/SKILL.md
required_transformations:
  - store durable project facts only; add donor manifest/handoff; no private chain-of-thought or secrets
forbidden_carry_over:
  - generic initialization that overwrites ChangeMesh decisions
required_tests:
  - startup-read references
  - task-closure updates
  - no-secret/no-private-reasoning checks
  - no generic initialization overwrite (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### UIPATH-STATE-001

```yaml
component_id: UIPATH-STATE-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-UIPATH
repository: zyganali-glitch/universal-agent-os-uipath
source_commit: dc2267939c2aef0aba2737da65f53352c5cf8fb2
source_paths:
  - backend/sync_markdown_to_uipath.py
  - tests/test_phase0_interview.py
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - persisted workflow state, wait/resume, explicit process transitions and handoff (concept only, not fully implemented in donor backend)
reuse_method: IDEA_ONLY / REFERENCE_ONLY
target_paths_or_contracts:
  - src/orchestrator/firestore_saga.py
required_transformations:
  - ADK + Pub/Sub + Firestore; no UiPath runtime or Phase-0 semantics
forbidden_carry_over:
  - Maestro/Action Center/Data Service IDs and dependencies
required_tests:
  - restart resume
  - no duplicate action
  - legal/illegal transition
  - timeout
  - cancellation
  - compensation
  - no UiPath dependency carry-over
  - unauthorized state transition (security test)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### UIPATH-AUTH-001

```yaml
component_id: UIPATH-AUTH-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-UIPATH
repository: zyganali-glitch/universal-agent-os-uipath
source_commit: dc2267939c2aef0aba2737da65f53352c5cf8fb2
source_paths:
  - backend/uipath_api_connector.py
  - tests/test_uipath_connector_modes.py
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - authority result verified through a system/API record rather than trusted from chat; real/mock mode kept explicit
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/auth/approval_compression.py
required_transformations:
  - exception-only human authority; reusable scoped/expiring approval
forbidden_carry_over:
  - routine approval per step; mock as real; UiPath API contract
required_tests:
  - forged chat approval rejected
  - expired/scope-mismatched decision rejected
  - valid reusable decision accepted
  - local adapter labeled
  - no UiPath API contract / routine approval (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CCT-EVID-001

```yaml
component_id: CCT-EVID-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-CCT
repository: zyganali-glitch/codex-control-tower
source_commit: 65ee1b72faf9a7202d9166eed43fb671804815a8
source_paths:
  - cli/commands/evidence.js
  - tests/test_evidence_pack.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - named evidence states; NOT_RUN and simulation boundaries; model cannot rewrite local facts
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/evidence/evidence_record.py
required_transformations:
  - ADK/tool events, Change ID, agent revision, cloud trace references
forbidden_carry_over:
  - Codex event assumptions, GPT-specific fields, InvoiceFlow fixture names
required_tests:
  - model disagreement cannot change facts
  - blocked remains not-run
  - simulated remains simulated
  - tamper detection
  - no Codex/GPT/InvoiceFlow fixtures (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CCT-FLIGHT-001

```yaml
component_id: CCT-FLIGHT-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-CCT
repository: zyganali-glitch/codex-control-tower
source_commit: 65ee1b72faf9a7202d9166eed43fb671804815a8
source_paths:
  - cli/commands/flight-recorder.js
  - tests/test_codex_review.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - chronological execution/evidence record and judge-inspectable summary
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/evidence/pubsub_timeline.py
required_transformations:
  - distributed causal chain, correlation/causation IDs, agent/tool revisions, OpenTelemetry links
forbidden_carry_over:
  - local-only chronology, Codex-specific event names, copied UI styling without review
required_tests:
  - duplicate/out-of-order event handling
  - causal ordering
  - redaction
  - restart continuity
  - tamper protection and immutability validation
  - no Codex events/UI styling (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CCT-PREFLIGHT-001

```yaml
component_id: CCT-PREFLIGHT-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-CCT
repository: zyganali-glitch/codex-control-tower
source_commit: 65ee1b72faf9a7202d9166eed43fb671804815a8
source_paths:
  - cli/lib/destructiveActionPreflight.js
  - tests/test_destructive_action_preflight.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - canonicalize target, compare protected boundaries, block before execution, preserve NOT_RUN
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/policy/shadowlab_auth.py
required_transformations:
  - schema/database/API/GitHub action classes rather than filesystem deletion only
forbidden_carry_over:
  - Codex hook dependency, shell-command execution, repository-subpath-as-safety-clearance
required_tests:
  - destructive target blocked pre-tool
  - no command executed
  - ambiguous target fails closed
  - reversible action classified separately
  - no Codex hook dependencies (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CCT-SEM-001

```yaml
component_id: CCT-SEM-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-CCT
repository: zyganali-glitch/codex-control-tower
source_commit: 65ee1b72faf9a7202d9166eed43fb671804815a8
source_paths:
  - cli/commands/codex-review.js
  - tests/test_codex_review.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - independent model assesses whether evidence semantically proves mission; expected result withheld; conflict triggers review but cannot overwrite facts
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/agents/evidence_auditor.py
required_transformations:
  - Gemini 3.5+, ADK-compatible bounded audit bundle, citation enforcement
forbidden_carry_over:
  - GPT-5.6/Codex runtime, expected-answer labels, model as execution authority
required_tests:
  - expected-label leakage scan
  - uncited decisive answer rejection
  - deterministic reconciliation
  - controlled mission gap
  - no GPT-5.6/Codex runtime (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CCT-JUDGE-001

```yaml
component_id: CCT-JUDGE-001
status: VERIFIED
donor_id: D-CCT
repository: zyganali-glitch/codex-control-tower
source_commit: 65ee1b72faf9a7202d9166eed43fb671804815a8
source_paths:
  - cli/commands/export-devpost.js
  - cli/lib/markdown.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - fast judge route, requirement-to-evidence map, demo timing, immutable release, build-period delta, screenshot/claim discipline
reuse_method: REFERENCE_ONLY
target_paths_or_contracts:
  - docs/JUDGING_MAP.md
required_transformations:
  - ChangeMesh-only facts/links/evidence
forbidden_carry_over:
  - old links, numbers, model names, evidence results, competition language, screenshots
required_tests:
  - link/status/version/claim parity
  - final tag/cloud/video alignment
  - no old claims
  - no invalid evidence
  - malformed screenshot fails
  - path traversal (security)
  - malicious command injection (security)
  - no provider names/old competition language (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### ZK-PRIV-001

```yaml
component_id: ZK-PRIV-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-ZEROKIT
repository: zyganali-glitch/zerokit-ai-control-plane
source_commit: d663db8c706cb914e1af5caf651df08edb5c50c0
source_paths:
  - ai-buildweek/lib/privacy-guard.mjs
  - tests/unit/privacy-guard.test.mjs
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - prevent sensitive/real data from entering model workflow; explicitly separate synthetic fixture
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/policy/policy_guardian.py
required_transformations:
  - Gemini input minimization, Policy Guardian, demo fixture boundary
forbidden_carry_over:
  - school-SaaS data, Codex/GPT fields, ZeroKit product semantics
required_tests:
  - secret/PII fixture blocked/redacted
  - synthetic mode explicit
  - model request contains only allowlisted fields
  - no school-SaaS data or ZeroKit semantics (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### ZK-VALID-001

```yaml
component_id: ZK-VALID-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-ZEROKIT
repository: zyganali-glitch/zerokit-ai-control-plane
source_commit: d663db8c706cb914e1af5caf651df08edb5c50c0
source_paths:
  - frontend/js/config-validator.js
  - tests/unit/config-validator.test.mjs
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - generated artifact must match explicit schema/allowlist and manifest; malformed/extra fields fail
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/core/gemini_structured_output.py
required_transformations:
  - domain contracts, Gemini structured output, migration artifacts, evidence/passport validators
forbidden_carry_over:
  - ZeroKit configuration schema, frontend globals, GPT-specific manifest fields
required_tests:
  - missing/extra/wrong-type/path traversal/unsafe endpoint/unknown action cases
  - positive validation test
  - no ZeroKit product semantics (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### ZK-CLAIM-001

```yaml
component_id: ZK-CLAIM-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-ZEROKIT
repository: zyganali-glitch/zerokit-ai-control-plane
source_commit: d663db8c706cb914e1af5caf651df08edb5c50c0
source_paths:
  - ai-buildweek/reports/jury-claim-audit.md
  - ai-buildweek/reports/jury-claim-audit.tr.md
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - map public statements to evidence and distinguish build-period work
reuse_method: REFERENCE_ONLY
target_paths_or_contracts:
  - src/audit/claim_audit.py
required_transformations:
  - competition-claim-audit, build disclosure, Devpost and screenshot review
forbidden_carry_over:
  - old claims, scores, evidence states, links, provider names
required_tests:
  - unsupported-claim scanner and cross-document parity
  - ambiguous claim fails
  - prompt injection on claim parsing (security)
  - XSS from external devpost text (security)
  - no old claims, scores, or provider names (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CS-BLAST-001

```yaml
component_id: CS-BLAST-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-CONTEXTSEAL
repository: zyganali-glitch/ContextSeal
source_commit: 0dc924db9d82037d2e813548bdee27af5f180889
source_paths:
  - src/datahub/live-context.js
  - src/core/risk.js
  - src/core/workflow.js
  - tests/live-context.test.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - preserve multi-hop dependency paths, owners, truncation/incompleteness, and risk context
reuse_method: ADAPTED
target_paths_or_contracts:
  - src/git/impact_scout.py (unified)
required_transformations:
  - GitHub repository findings plus synthetic metadata graph; optional DataHub adapter
forbidden_carry_over:
  - hard DataHub requirement, silent truncated lineage, ContextSeal terminology
required_tests:
  - multi-hop path
  - cycles
  - truncation
  - missing owner
  - duplicate merge
  - contradictory sources
  - unauthorized access across repository boundary (security test)
  - no DataHub/ContextSeal terminology (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CS-MIG-001

```yaml
component_id: CS-MIG-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-CONTEXTSEAL
repository: zyganali-glitch/ContextSeal
source_commit: 0dc924db9d82037d2e813548bdee27af5f180889
source_paths:
  - src/core/workflow.js
  - skills/datahub-schema-change-certification/scripts/certify_change.py
  - tests/workflow.test.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - reject direct breaking mutation; create additive migration, compatibility, verification, rollback, and deferred-removal plan
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/agents/migration_engineer.py
required_transformations:
  - Migration Engineer and ShadowLab correction
forbidden_carry_over:
  - direct live writeback, DataHub-only artifact format, pre-existing demo claims
required_tests:
  - legacy client
  - dual write
  - backfill interruption
  - rollback
  - deferred removal
  - missing dependency
  - unauthorized schema change rejection
  - no DataHub artifacts/demo claims (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CS-PASS-001

```yaml
component_id: CS-PASS-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-CONTEXTSEAL
repository: zyganali-glitch/ContextSeal
source_commit: 0dc924db9d82037d2e813548bdee27af5f180889
source_paths:
  - src/core/passport.js
  - scripts/validate-evidence.js
  - tests/evidence-validator.test.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - bind change context, policy, evidence, artifact hashes, and review packet into a verifiable package
reuse_method: ADAPTED
target_paths_or_contracts:
  - src/evidence/change_passport.py
required_transformations:
  - agent revisions/delegation, ShadowLab, memory trust, OpenTelemetry, external receipts
forbidden_carry_over:
  - duplicate passport implementation, ContextSeal field names as unreviewed contract
required_tests:
  - canonical serialization
  - tamper
  - missing artifact
  - wrong revision
  - stale approval
  - deterministic verify
  - no ContextSeal field names carry-over
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### CS-WRITE-001

```yaml
component_id: CS-WRITE-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-CONTEXTSEAL
repository: zyganali-glitch/ContextSeal
source_commit: 0dc924db9d82037d2e813548bdee27af5f180889
source_paths:
  - src/datahub/writeback.js
  - scripts/build-pr-bundle.js
  - tests/live-pipeline.test.js
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - constrain external write, generate review packet, preserve branch/change reconciliation
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/agents/release_steward.py
required_transformations:
  - GitHub draft-PR adapter and Release Steward
forbidden_carry_over:
  - DataHub writeback, automatic merge, unscoped target, missing idempotency
required_tests:
  - dry run
  - allowlist
  - duplicate replay
  - outside target
  - conflict
  - receipt creation
  - no DataHub writeback/automatic merge (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### QW-MEM-001

```yaml
component_id: QW-MEM-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-QWEN
repository: gitlab.com/zyganali/universal-agent-os-qwen
source_commit: a43b3411856f41a4be9424d11c01a5e637cdc410
source_paths:
  - backend/memory_manager.py
  - tests/test_memory_manager.py
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - BM25/embedding/keyword recall, freshness, importance, decay
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - src/memory/trust_layer.py
required_transformations:
  - trust authority remains new ChangeMesh logic
forbidden_carry_over:
  - Qwen runtime/provider
  - Phase-0
  - memory-as-truth
  - unbounded vector/RAG infrastructure
required_tests:
  - relevance
  - stale-memory demotion
  - high-importance retention
  - deterministic trust override
  - poisoned-memory quarantine
  - no Qwen runtime/Phase-0/RAG infrastructure (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### QW-BUS-001

```yaml
component_id: QW-BUS-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-QWEN
repository: gitlab.com/zyganali/universal-agent-os-qwen
source_commit: a43b3411856f41a4be9424d11c01a5e637cdc410
source_paths:
  - backend/vector_store.py
  - tests/test_vector_store.py
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - multi-agent memory exchange/MCP tools
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - backend/vector_store.py
  - tests/test_vector_store.py
required_transformations:
  - scoped memory references and saga handoff
forbidden_carry_over:
  - unrestricted shared mutable memory
required_tests:
  - cross-agent scope
  - tenant isolation
  - provenance
  - replay
  - no-secret tests mandatory
  - no unrestricted shared mutable memory (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### GL-CONFLICT-001

```yaml
component_id: GL-CONFLICT-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-GITLAB
repository: gitlab.com/zyganali/universal-agent-os-gitlab-edition
source_commit: 3c4a412b6040d8a8154c15325943c409be9105f2
source_paths:
  - tools/orbit_cli.py
  - tests/test_orbit_integration.py
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - real overlapping MR blast radius, ownership and parallel-change risk
reuse_method: ADAPTED
target_paths_or_contracts:
  - src/git/impact_scout.py (unified)
required_transformations:
  - Impact Scout and GitHub pre-draft-PR conflict check
forbidden_carry_over:
  - GitLab Duo/Orbit/GraphQL runtime dependency in MVP
  - fabricated tool results
  - GitLab-only IDs
required_tests:
  - overlap/no-overlap
  - stale PR data
  - unavailable API
  - owner ambiguity
  - honest NOT_RUN
  - malicious MR payload spoofing (security)
  - path traversal in impact_scout (security)
  - no GitLab Duo/Orbit/GraphQL dependency carry-over
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

### GL-HONEST-001

```yaml
component_id: GL-HONEST-001
status: APPROVED_FOR_IMPLEMENTATION
donor_id: D-GITLAB
repository: gitlab.com/zyganali/universal-agent-os-gitlab-edition
source_commit: 3c4a412b6040d8a8154c15325943c409be9105f2
source_paths:
  - tools/orbit_client.py
  - tests/test_orbit_client.py
license_state: VERIFIED_COMPATIBLE
source_behavior:
  - preserve unavailable external/tool results rather than fabricate success
reuse_method: CLEAN_ROOM_REIMPLEMENTED
target_paths_or_contracts:
  - tools/orbit_client.py
  - tests/test_orbit_client.py
required_transformations:
  - connector/evidence boundary across GitHub, metadata graph, and optional managed services
forbidden_carry_over:
  - fabricated API responses
required_tests:
  - unavailable/permission/timeout/rate-limit states remain explicit
  - positive test for available API
  - no fabricated API responses (forbidden carry-over)
competition_introduction_commit: PENDING
evidence:
  - source inspection
reviewer: primary agent + donor-reuse-auditor
last_reviewed: 2026-08-07T17:25:00Z
```

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
