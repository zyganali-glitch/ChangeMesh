# ChangeMesh Handoff State

**Completed:**
P-00
P-01
P-02
P-02D
P-03
P-04.00
P-04.01
P-04.02
P-04.03
P-04.04
P-04.05
P-04
P-05.01
P-05.02
P-05.03
P-05.04
P-05.05
P-05.06
P-05
P-06.01
P-06.02
P-06.03
P-06.04
P-06.05
P-06
P-07.01
P-07.02
P-07.03
P-07.04
P-07.05
P-07
P-08.00
P-08.01
P-08.02
P-08.03
P-08.04
P-08.05

**Active Phase:**
P-09

**Next Exact Task:**
P-09.01 — Create topic/subscription topology for change, agent work, approvals, evidence, retries, dead letters

## Current P-08.03 State

P-08.03 is `DONE`. `src/agents/policy_guardian.py` is the single deterministic
privacy/minimization owner. It blocks private keys, API-key-looking values,
GitHub/cloud access keys, JWTs, bearer values, password-bearing connection
strings, cookies, service-account material, real email addresses, and phone
numbers. UUIDs, public IPs, and production-data markers are deterministic
`REVIEW` findings, but review findings are also blocked from Gemini and cannot
create `HUMAN_AUTHORITY`.

Goal Decomposition, Policy Explanation, and Semantic Audit use exact field
allowlists, nested allowlists, and matching `collection_mode`/`declared_mode`
values. `src/core/gemini_client.py` validates both prompt and
`system_instruction` before request construction, so blocked input produces
zero SDK calls. Untrusted external text remains data inside fixed boundary
markers. P-08.02 strict output parsing and P-08.01 single-call ownership remain
intact.

## Current P-08.04 State

P-08.04 is `DONE` (Repaired). `src/agents/evidence_auditor.py` separates
locked deterministic claim facts from the model-visible blind bundle, rejects
expected-answer fields and hints, bounds claim/evidence/prompt size, validates
citations, and reconciles advisory model assessments without rewriting facts or
manufacturing human authority (`relation="DISAGREEMENT_WITH_LOCKED_STATE"`,
`conflict_detected=True`, `review_state="SEMANTIC_DISAGREEMENT"`, `human_review_required=False`).
The dedicated suite has 18 passing tests.

## Current P-08.05 State

P-08.05 is `DONE` (Repaired). `ModelCallTelemetry` records latency, token
counts, attempts, retry count, and formula cost estimates with structured
`RateProvenanceKind`. Defined deterministic `ModelCallBudgetPolicy` (`DEMO_MAX_LATENCY_MS = 30000.0`,
`DEMO_MAX_COST_USD = 0.05`, `DEMO_MAX_TOTAL_TOKENS = 12288`) and `evaluate_model_call_budget()`,
documented in `docs/COST_PLAN.md`. Exported canonical metrics evidence artifacts via
`build_model_metrics_artifact()` and `export_metrics_artifact_json()`. Missing provider
rates remain visible as `cost_status="NOT_RUN"`; provider pricing calibration is explicitly `NOT_RUN`.
The dedicated metrics suite has 11 passing tests. The P-08 phase closure is verified.

## Evidence

- P-08.03 privacy suite: `uv run python -m pytest tests/test_p08_03_input_privacy.py -v --tb=short` -> 10 passed.
- P-08.01 regression: `uv run python -m pytest tests/test_p08_01_gemini_client.py -v --tb=short` -> 39 passed.
- P-08.02 regression: `uv run python -m pytest tests/test_p08_02_structured_output.py -v --tb=short` -> 40 passed.
- P-08.04 dedicated: `uv run python -m pytest tests/test_p08_04_blind_audit.py -v --tb=short` -> 18 passed.
- Combined P-08.01/P-08.02/P-08.04: `uv run python -m pytest tests/test_p08_01_gemini_client.py tests/test_p08_02_structured_output.py tests/test_p08_04_blind_audit.py -q` -> 97 passed.
- P-08.05 metrics: `uv run python -m pytest tests/test_p08_05_metrics.py -v --tb=short` -> 11 passed.
- Complete P-08: `uv run python -m pytest tests/test_p08_01_gemini_client.py tests/test_p08_02_structured_output.py tests/test_p08_03_input_privacy.py tests/test_p08_04_blind_audit.py tests/test_p08_05_metrics.py -q` -> 118 passed.
- Policy Guardian regression: `uv run python -m pytest tests/test_p07_02_agent_definitions.py -q` -> 59 passed, 1 warning.
- Canonical unit: `uv run python scripts/cmd.py unit` -> 1028 passed, 1 warning.
- Full suite: `uv run python -m pytest tests/` -> 1028 passed, 1 warning, 3 errors; **FAIL — known historical baseline GCP fixture debt** (`project` fixture in `tests/test_gcp_access.py`).
- Donor manifest lint: `uv run python tools/governance/donor_manifest_lint.py` -> 20 components passed.
- Targeted Ruff, format, mypy, AST model-owner, domain import, secret scan, and `git diff --check`: `PASS`.

## Provenance

ZK-PRIV-001 is `VERIFIED` as `CLEAN_ROOM_REIMPLEMENTED` from D-ZEROKIT at
immutable SHA `d663db8c706cb914e1af5caf651df08edb5c50c0`, using only
`ai-buildweek/lib/privacy-guard.mjs` and `tests/unit/privacy-guard.test.mjs`.
The actual ChangeMesh competition introduction commit is
`4501c01ad4212a8ddd05024f99b5baab34b585de`.

CCT-SEM-001 is `VERIFIED` as `CLEAN_ROOM_REIMPLEMENTED` from D-CCT at
immutable SHA `65ee1b72faf9a7202d9166eed43fb671804815a8`, using only
`cli/commands/codex-review.js` and `tests/test_codex_review.js`. The actual
ChangeMesh competition introduction commit is
`7cce78daca6ab37c027fea9d4637f3ecca4cfc28`.

## Open Boundaries

- Model Armor remains `PERMISSION_BLOCKED / NOT_RUN`.
- Generic enterprise DLP, universal PII discovery, cloud proxy filtering, full external adapter mode execution, and production provider-pricing calibration remain `NOT_RUN` or `PLANNED` under their owning phases.
- Full repository test status remains the historical `FAIL` above and must not be relabeled `PASS`.
