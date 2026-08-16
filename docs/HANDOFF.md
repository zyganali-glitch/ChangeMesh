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

**Active Phase:**
P-08

**Next Exact Task:**
P-08.04 — Separate deterministic facts from model-visible evidence and withhold expected semantic classifications from auditor

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
intact. P-08.04 and P-08.05 were not started.

## Evidence

- P-08.03 privacy suite: `uv run python -m pytest tests/test_p08_03_input_privacy.py -v --tb=short` -> 10 passed.
- P-08.01 regression: `uv run python -m pytest tests/test_p08_01_gemini_client.py -v --tb=short` -> 39 passed.
- P-08.02 regression: `uv run python -m pytest tests/test_p08_02_structured_output.py -v --tb=short` -> 40 passed.
- Combined P-08: `uv run python -m pytest tests/test_p08_01_gemini_client.py tests/test_p08_02_structured_output.py tests/test_p08_03_input_privacy.py -v --tb=short` -> 89 passed.
- Policy Guardian regression: `uv run python -m pytest tests/test_p07_02_agent_definitions.py -q` -> 59 passed, 1 warning.
- Canonical unit: `uv run python scripts/cmd.py unit` -> 999 passed, 1 warning.
- Full suite: `uv run python -m pytest tests/` -> 999 passed, 1 warning, 3 errors; **FAIL — known historical baseline GCP fixture debt** (`project` fixture in `tests/test_gcp_access.py`).
- Donor manifest lint: `uv run python tools/governance/donor_manifest_lint.py` -> 20 components passed.
- Targeted Ruff, format, mypy, AST model-owner, domain import, secret scan, and `git diff --check`: `PASS`.

## Provenance

ZK-PRIV-001 is `VERIFIED` as `CLEAN_ROOM_REIMPLEMENTED` from D-ZEROKIT at
immutable SHA `d663db8c706cb914e1af5caf651df08edb5c50c0`, using only
`ai-buildweek/lib/privacy-guard.mjs` and `tests/unit/privacy-guard.test.mjs`.
The actual ChangeMesh competition introduction commit is
`4501c01ad4212a8ddd05024f99b5baab34b585de`.

## Open Boundaries

- Model Armor remains `PERMISSION_BLOCKED / NOT_RUN`.
- Generic enterprise DLP, universal PII discovery, cloud proxy filtering, full external adapter mode execution, and P-08.04 blind reconciliation remain `NOT_RUN` or `PLANNED` under their owning phases.
- Full repository test status remains the historical `FAIL` above and must not be relabeled `PASS`.
