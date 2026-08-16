# ChangeMesh — Environment and API State

Record actual environment only; do not fill unknown values with guesses.

## Current status

- Local implementation stack: `Python 3.13.5` (backend/agents) + `Vanilla JS/HTML/CSS` (web dashboard, no build step)
- Python version: `3.13.5` (pinned in `.python-version`)
- Node version: `NOT_REQUIRED` (No Node runtime or build step; dashboard is vanilla static assets served via Python/Cloud Run)
- Google Cloud project: `project-af5e1c99-3bc4-424f-b53`
- Region: `global` (for Vertex AI Gemini), `europe-west3` (for cloud resources)
- Vertex AI access: `ENABLED` (Provisioned via UI)
- Gemini model ID: `gemini-3.6-flash` (canonical single model for all product runtime invocations)
- Python SDK Requirement: `google-genai` (version 2.18.1 locked in `uv.lock`; legacy `vertexai` SDK is deprecated)
- Bounded Model Client: `src/core/gemini_client.py` (`BoundedGeminiClient` IMPLEMENTED in P-08.01)
- Cloud Run: `VERIFIED` (as supporting services)
- Firestore: `VERIFIED` (as Operational State)
- Pub/Sub: `VERIFIED`
- Agent Runtime/Platform: `AVAILABLE / NOT_RUN`
- Memory Bank: `DEFERRED / NOT_RUN` (Requires ReasoningEngine instance, none deployed yet)
- Agent Registry: `AVAILABLE / NOT_RUN`
- Agent Identity: `PERMISSION_BLOCKED / NOT_RUN` (verified via `gcloud agent-identity auth-providers list --location=global`)
- Agent Gateway: `AVAILABLE / NOT_RUN` 
- Model Armor: `PERMISSION_BLOCKED / NOT_RUN` (403 on modelarmor.googleapis.com)
- Observability: `AVAILABLE / NOT_RUN`
- GitHub demo repository: `NOT_CREATED`
- Public demo URL: `NOT_AVAILABLE`

## Rules

### Credential Handling Architecture (P-04.03)

- **Local:** Use Application Default Credentials (ADC) for local development.
- **Cloud:** Target Workload Identity / Managed Identity. No service-account JSON key files should be used or distributed.
- **Isolation:** Credentials (`GITHUB_TOKEN`, API Keys, etc.) exist only at external adapter boundaries.
- **Inward Ban:** Credential material must **never** be propagated into model prompts, agent memory, evidence artifacts, Pub/Sub event payloads, EventEnvelope fields, or the public judge UI.
- **Logging:** Secret environment variables and credential material must never be logged unredacted.

- Never commit credentials, service-account keys, OAuth tokens, cookies, or personal access tokens.
- Prefer Application Default Credentials locally and workload identity in Google Cloud.
- Record exact service, project, region, resource name, required role, and teardown method.
- Every environment variable is documented with sensitivity, purpose, requirement, and safe example.
- Every external API write defines timeout, retry, idempotency, and evidence behavior.
- Costs and quotas are measured before final demo.

### Event Envelope and Backbone Topology Boundary (P-05.05 / P-09.01 / P-09.02)

- **EventEnvelope** is a provider-neutral domain contract defined in `domain/contracts/event_envelope.py`. It carries event identity, change identity, causal chain, correlation, producer revision, and idempotency key.
- **No credentials** are permitted in event metadata or payload boundary. Credential material must never enter an EventEnvelope.
- **Backbone Topology (P-09.01 IMPLEMENTED):** Minimal, versioned (`1.0.0`) canonical topology declared in `events/topology.py` and `events/topology_manifest.json` with 6 logical topics (`changemesh-lifecycle-v1`, `changemesh-agent-work-v1`, `changemesh-approval-v1`, `changemesh-evidence-v1`, `changemesh-retry-v1`, `changemesh-dead-letter-v1`) and 6 attached subscriptions. Subscriptions route dead letters to `changemesh-dead-letter-v1` (5 attempts) with dead-letter subscription cycle prohibition. All 16 `ChangeState` values are mapped deterministically (see diagram `docs/diagrams/pubsub_topology.md`).
- **Publish/Consume Adapters (P-09.02 IMPLEMENTED):** Provider-neutral `EventWireMessage` (`events/wire.py`), `EventPublisher`/`EventConsumer` protocols, `InMemoryDeliveryState` (`events/delivery_state.py`), and Google Pub/Sub adapters in `integrations/gcp/pubsub_adapter.py` (`GooglePubSubPublisher`, `GooglePubSubConsumer`). Pre-dispatch schema validation rejects malformed JSON, unsupported versions, extra fields (`extra='forbid'`), and secret-bearing payloads. Duplicate delivery safety is enforced before application callback invocation.
- **P-09 owns actual publish/consume behavior**, including topic/subscription topology, publisher/consumer adapters, delivery, acknowledgements, retries, dead-letter, and infrastructure config.
- **classify_event_delivery** is a pure function consuming abstract already-seen snapshots. It does not own persistence (P-10).

### Machine Conventions Contract Boundary (P-05.06)

- **Machine conventions** (`domain/contracts/conventions.py`) define canonical hashing (`HashAlgorithm.SHA256`, 64-character lowercase hex regex `^[0-9a-f]{64}$`), UTC timestamp normalization and naive rejection (`UtcDateTime`), deterministic canonical JSON serialization (`canonical_json_bytes`), and structural secret redaction (`redact_mapping`, `REDACTION_SENTINEL = "[REDACTED]"`).

### Dependency and Lockfile Architecture Boundary (P-06.02 / ADR-0016)

- **Canonical Manifest (Source of Truth):** `pyproject.toml` (PEP 621 / PEP 735).
  - Direct runtime dependencies: `google-adk>=2.6.0`, `google-genai>=0.1.0`, `pydantic>=2.0.0`, `google-cloud-firestore>=2.15.0`, `google-cloud-pubsub>=2.20.0`.
  - Direct dev/test dependencies: `pytest>=8.0.0`, `pyyaml>=6.0.0`, `google-auth>=2.0.0`, `google-cloud-run>=0.10.0`.
  - Deferred future (removed from direct): `google-cloud-logging`, `google-cloud-trace` (owned by P-22).
  - Unnecessary / removed as direct: `google-cloud-aiplatform` (legacy SDK superseded by `google-genai`).
- **Resolver & Generator Version Enforcement:** Enforced in `pyproject.toml` via `[tool.uv] required-version = "==0.11.28"`. Fails closed if ambient uv version mismatches.
- **Deterministic Lock Artifact:** `uv.lock` (generated via `uv lock` with `uv 0.11.28`). Freezes the exact resolved dependency graph (74 packages: 73 external installed packages + 1 root project package) with repository URLs and SHA-256 integrity hashes.
- **Runtime Compatibility Export:** `requirements.txt` (generated via `uv export --frozen --no-dev --no-emit-local -o requirements.txt`). Strictly runtime dependencies (68 packages) with exact pins and SHA-256 hashes for standard `pip` environments, Cloud Run buildpacks, and Docker containers without `uv`.
- **Dev/Test Compatibility Export:** `requirements-dev.txt` (generated via `uv export --frozen --all-groups --no-emit-local -o requirements-dev.txt`). Full runtime + dev/test dependencies (73 packages) with exact pins and SHA-256 hashes.
- **Regeneration Command:** `uv lock ; uv export --frozen --no-dev --no-emit-local -o requirements.txt ; uv export --frozen --all-groups --no-emit-local -o requirements-dev.txt`
- **Installation from Lock:**
  - Runtime: `uv pip install --require-hashes -r requirements.txt` or `pip install --require-hashes -r requirements.txt`.
  - Dev/Test: `uv sync --frozen` or `uv pip install --require-hashes -r requirements-dev.txt` or `pip install --require-hashes -r requirements-dev.txt`.

### Local Configuration & Secret-Handling Boundary (P-06.03)

- **Canonical Configuration Template:** `.env.example` at repository root. It defines all registered environment variables with zero secret defaults.
- **Secret-Value Policy:** Secret-bearing variables (`GITHUB_TOKEN`) must have empty values (`GITHUB_TOKEN=`) in the template. No dummy tokens, placeholders, or live credentials.
- **ADC-First Local Policy:** Local development uses Google Cloud Application Default Credentials (ADC) via `gcloud auth application-default login`. Service-account JSON key files are prohibited and not distributed.
- **Tracked vs Ignored Boundary:** `.gitignore` explicitly ignores real `.env`, `.env.*` (while preserving `!.env.example`), `*service-account*.json`, `*credentials*.json`, `application_default_credentials.json`, `*adc.json`, `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*.pkcs12`, `api_key.txt`, `*.secret`, `*.token`, `tmp/`, `artifacts/private/`, `private/`, and `secrets/`.
- **Evidence & Verification:** 14 automated tests in `tests/test_p06_03_config_safety.py` and 0-secret scan across all tracked repository files (`PASS`).

### Canonical Command Interface Boundary (P-06.04)

- **Canonical Dispatcher:** `scripts/cmd.py` implemented with standard library `argparse` exposing all 9 canonical developer workflow commands: `format`, `lint`, `type-check`, `unit`, `integration`, `e2e`, `demo`, `deploy`, `teardown`.
- **Non-Mutating Verification Semantics:** Verification commands (`format`, `lint`, `type-check`) are strictly check-only and never mutate repository files:
  - `format`: Executes `ruff format --check .` (never `ruff format` without `--check`).
  - `lint`: Executes `ruff check .` (never passes `--fix`).
  - `type-check`: Executes `mypy domain tests` with exact exit code propagation.
- **Integration Safety & Script Entry Dispatch:**
  - Default: `uv run python scripts/cmd.py integration` fails closed with exit code 1, emitting an error message to stderr and executing zero cloud/network calls.
  - Authorized path: `uv run python scripts/cmd.py integration --live-write-danger` dispatches the existing standalone script `python tests/test_gcp_access.py` directly, avoiding broken pytest fixture collection.
- **Deferred Future-Phase Guarding:** Lifecycle commands owned by future phases (`e2e`, `demo` -> P-24/P-25; `deploy`, `teardown` -> P-28) fail closed with exit code 1 and emit `NOT_RUN`.
- **Evidence & Verification:** 15 automated unit/contract tests in `tests/test_p06_04_commands.py` (`PASS`). Zero cloud access required for CLI inspection, help, and unit validation.

### Bounded Gemini Model Client Boundary (P-08.01)

- **Canonical Module:** `src/core/gemini_client.py` (exported through `src/core/__init__.py`).
- **Exact Model ID:** `gemini-3.6-flash` (`CANONICAL_MODEL_ID`). Unapproved model overrides or environment configurations fail closed with `ModelConfigurationError`.
- **Pinned API Version:** `v1beta1` (`CANONICAL_API_VERSION = "v1beta1"`). Pinned explicitly in `types.HttpOptions(api_version="v1beta1")` across client initialization and request configurations.
- **Backend/Provider:** Vertex AI (`vertexai=True`, `location="global"` or `GOOGLE_CLOUD_LOCATION`, `project="project-af5e1c99-3bc4-424f-b53"` or `GOOGLE_CLOUD_PROJECT`).
- **Resolved SDK Version:** `google-genai` 2.18.1 (from `uv.lock`).
- **Timeout Policy:** Explicit positive finite bound (`DEFAULT_TIMEOUT_SECONDS = 30.0s`, bounds [1.0s, 60.0s]). Transport converted to integer milliseconds (`types.HttpOptions(timeout=...)`). Exceeded timeouts raise `ModelTimeoutError`.
- **Retry Authority:** Exactly ONE retry authority owned by the ChangeMesh wrapper (`MAX_ATTEMPTS = 3`, exponential backoff with initial delay 0.5s, multiplier 2.0, max delay 2.0s). SDK-level retry is explicitly disabled (`types.HttpRetryOptions(attempts=1)`). Retryable status codes restricted to `{429, 502, 503, 504}` and transient network errors. Non-retryable errors (400, 401, 403, 404, malformed input) fail immediately. Exhaustion raises `ModelRetryExhaustedError`.
- **Token Output Budget:** Explicit positive integer bound (`DEFAULT_MAX_OUTPUT_TOKENS = 4096`, ceiling `MAX_TOKEN_CEILING = 8192`). Callers cannot override the ceiling upward.
- **Safety Policy:** Immutable ChangeMesh dataclass policy (`CANONICAL_SAFETY_POLICY`) covering the 4 active, supported harm categories for Vertex AI / `gemini-3.6-flash` in `google-genai 2.18.1` (`HARM_CATEGORY_HARASSMENT`, `HARM_CATEGORY_HATE_SPEECH`, `HARM_CATEGORY_SEXUALLY_EXPLICIT`, `HARM_CATEGORY_DANGEROUS_CONTENT`) with threshold `HarmBlockThreshold.BLOCK_LOW_AND_ABOVE`. Fresh SDK `types.SafetySetting` instances are constructed internally per request. `HARM_CATEGORY_CIVIC_INTEGRITY` is officially deprecated in SDK 2.18.1 ("Election filter is no longer supported") and is excluded from active canonical policy. Blocked responses raise `ModelSafetyBlockedError` and fail closed.
- **Telemetry Boundary & Secret Isolation:** Typed `ModelCallTelemetry` capturing operational metadata (`call_id`, `model_id`, `provider`, `project`, `location`, `api_version`, timestamps, duration, attempts, outcome, status code, token counts, finish reason). Caller-provided correlation identifiers are validated and sanitized (`sanitize_telemetry_call_id`); secret-bearing, malformed, or unbounded identifiers are safely transformed into non-reversible opaque digests (`call_opaque_<sha256[:16]>`). Project and location are validated against strict regexes and secret checks. STRICTLY ZERO credentials, ZERO API keys, ZERO prompt contents, ZERO response text.
- **Zero Fallback Invariant:** Zero silent fallback to other models, preview versions, other providers, cached answers, or fake PASS sentinels.

### Input Privacy and Minimization Boundary (P-08.03)

- **Canonical owner:** `src/agents/policy_guardian.py` owns the single deterministic privacy pattern table and prompt-context minimizer. `domain/contracts/conventions.py::redact_mapping` remains structural field-name redaction only.
- **Model-call integration:** `BoundedGeminiClient.generate_text` invokes Policy Guardian validation for both `prompt` and `system_instruction` before request construction and before `models.generate_content(...)`. Blocked input produces zero SDK calls.
- **Blocked categories:** private keys, API-key-looking values, GitHub/cloud access keys, JWTs, bearer values, password-bearing connection strings, session cookies, service-account material, non-reserved email addresses, and phone numbers.
- **Review policy:** UUIDs, public IPs, and production-data markers produce deterministic `REVIEW` findings, but `safe_to_send` is false and Gemini is not invoked. Review does not manufacture `HUMAN_AUTHORITY`.
- **Prompt surfaces and fields:** Goal Decomposition (`change_request_id`, `title`, `description`, `target_systems`, `data_classification`, `success_criteria`, `collection_mode`, `declared_mode`); Policy Explanation (`change_id`, `decision_id`, `action_class`, `autonomy_class`, `policy_source`, `rationale`, `violated_rules`, `collection_mode`, `declared_mode`); Semantic Audit (`audit_id`, `change_id`, `claims`, `evidence_summaries`, `collection_mode`, `declared_mode`) with nested claims limited to `claim_id`, `claim_description`, `target_criterion` and evidence summaries limited to `evidence_key`, `summary`, `source`.
- **Mode/provenance:** `collection_mode` and `declared_mode` must match one of `FIXTURE`, `SIMULATION`, `RECORDED_CLOUD`, or `LIVE_WRITE`; mismatches fail closed. Synthetic fixtures are not relabeled as live evidence.
- **Honesty boundary:** This is not Model Armor, generic enterprise DLP, universal PII discovery, a cloud proxy/interceptor, or a production security certification. Model Armor remains `PERMISSION_BLOCKED / NOT_RUN`.

### Blind Semantic Audit Boundary (P-08.04)

- **Canonical owner:** `src/agents/evidence_auditor.py` owns `BlindAuditPackage`, bounded model context construction, expected-answer leakage rejection, citation-scope checks, and deterministic/model reconciliation.
- **Model-visible context:** Only neutral claim identifiers/descriptions/criteria and bounded evidence key/summary/source values cross the semantic audit prompt. Locked `EvidenceState`, deterministic basis, expected assessments, and reconciliation hints remain application-only.
- **Bounds:** Maximum 64 claims, 128 evidence summaries, 4,000 characters per text field, and 32,000 aggregate prompt characters.
- **Authority:** Model output remains `GEMINI_SEMANTIC_JUDGMENT`; `EvidenceState` facts remain sovereign. Disagreement produces a review state and cannot manufacture `HUMAN_AUTHORITY`.
- **Runtime path:** `run_blind_semantic_audit` uses `BoundedGeminiClient`; no second SDK client or provider call exists.

### Gemini Measurement and Budget Boundary (P-08.05)

- **Operational metrics:** `ModelCallTelemetry` records monotonic `duration_ms`, prompt/response/total token counts, attempts, `retry_count`, `cost_status` (`"CALCULATED"` / `"NOT_RUN"`), `rate_card_id`, `rate_provenance`, `finish_reason`, and non-secret outcome metadata.
- **Rate Provenance & Calibration:** `GeminiCostRateCard` requires explicit non-empty `rate_card_id` and explicit structured `RateProvenanceKind` (`TEST_FORMULA`, `CUSTOM_UNVERIFIED`, `PROVIDER_CALIBRATED`). Provider pricing calibration is explicitly `NOT_RUN` (zero price guessing); caller selection of `PROVIDER_CALIBRATED` cannot manufacture calibration truth. Missing rate cards produce `cost_status="NOT_RUN"`.
- **Project / Demo Budget Policy:** Deterministic `ModelCallBudgetPolicy` (`DEMO_MAX_LATENCY_MS = 30000.0`, `DEMO_MAX_COST_USD = 0.05`, `DEMO_MAX_TOTAL_TOKENS = 12288`) and `evaluate_model_call_budget()` enforce local demonstration limits without claiming provider SLAs (see `docs/COST_PLAN.md`). Missing rates or tokens yield fail-closed `overall_status="NOT_RUN"` (`overall_budget_pass=False`).
- **Canonical Metrics Artifact:** `build_model_metrics_artifact()` and `export_metrics_artifact_json()` provide deterministic non-secret execution artifacts with strict secrecy guarantees (zero prompt, response, or credential text).
- **Bounds:** Rate values are finite and non-negative; token counts are non-negative; existing timeout [1s, 60s] and output-token [1, 8192] bounds remain active.

## Environment-variable registry

| Variable | Purpose | Required | Secret | Safe example | Owner phase |
|---|---|---:|---:|---|---|
| `GOOGLE_CLOUD_PROJECT` | Cloud project ID | TBD | No | `project-af5e1c99-3bc4-424f-b53` | P-02/P-28 |
| `GOOGLE_CLOUD_LOCATION` | Deployment region | TBD | No | `global` | P-02/P-28 |
| `GEMINI_MODEL` | Exact model ID | TBD | No | `gemini-3.6-flash` | P-08 |
| `GITHUB_TOKEN` | Optional live draft-PR action | TBD | Yes | never commit | P-19 |
| `DEMO_REPO` | Synthetic target repository | TBD | No | `owner/changemesh-demo-enterprise` | P-24 |

## Command registry

Commands may be recorded as `VERIFIED` after the owning micro-task executes them successfully under its required validation environment. Clean-checkout reproduction from a separate directory was executed and verified under P-06.05 ([`docs/P-06.05_CLEAN_CHECKOUT_LOG.md`](docs/P-06.05_CLEAN_CHECKOUT_LOG.md)), establishing `CLEAN_CHECKOUT_VERIFIED` status for reproducible installation, baseline test suites, and canonical command contracts. Current underlying test counts reflect the latest local canonical P-08.05 verification.

| Purpose | Command | Interface Status | Underlying Check Status | Side-Effect Class / Scope | Last verified |
|---|---|---|---|---|---|
| Install (dev/test uv locked) | `uv sync --frozen` | `CLEAN_CHECKOUT_VERIFIED` | `PASS` | Local venv synchronization | 2026-08-15 |
| Install (runtime hash-locked) | `pip install --require-hashes -r requirements.txt` | `CLEAN_CHECKOUT_VERIFIED` | `PASS` | Local venv installation | 2026-08-15 |
| Install (dev/test hash-locked) | `pip install --require-hashes -r requirements-dev.txt` | `VERIFIED` | `PASS` | Local venv installation | 2026-08-15 |
| Lock generation | `uv lock` | `VERIFIED` | `PASS` | Deterministic lockfile update | 2026-08-15 |
| Lock export (runtime) | `uv export --frozen --no-dev --no-emit-local -o requirements.txt` | `VERIFIED` | `PASS` | Runtime requirements export | 2026-08-15 |
| Lock export (dev/test) | `uv export --frozen --all-groups --no-emit-local -o requirements-dev.txt` | `VERIFIED` | `PASS` | Dev requirements export | 2026-08-15 |
| Dependency check | `uv pip check` | `CLEAN_CHECKOUT_VERIFIED` | `PASS` | Local dependency consistency | 2026-08-15 |
| Unit tests (Contracts) | `python -m pytest tests/test_p05_01_contracts.py` | `VERIFIED` | `PASS` (41 passed) | Local non-mutating test | 2026-08-11 |
| Unit tests (P-05.05 Events) | `python -m pytest tests/test_p05_05_event_envelope.py -v --tb=short` | `VERIFIED` | `PASS` (82 passed) | Local non-mutating test | 2026-08-13 |
| Unit tests (P-05.06 Conventions) | `python -m pytest tests/test_p05_06_contract_conventions.py -v --tb=short` | `VERIFIED` | `PASS` (214 passed) | Local non-mutating test | 2026-08-15 |
| Unit tests (Combined P-05) | `python -m pytest tests/test_p05_01_contracts.py tests/test_p05_02_lifecycle.py tests/test_p05_03_evidence_contracts.py tests/test_p05_04_core_innovation_contracts.py tests/test_p05_05_event_envelope.py tests/test_p05_06_contract_conventions.py -v --tb=short` | `CLEAN_CHECKOUT_VERIFIED` | `PASS` (590 passed) | Local non-mutating test | 2026-08-15 |
| Unit tests (P-06.03 Config Safety) | `python -m pytest tests/test_p06_03_config_safety.py -v --tb=short` | `CLEAN_CHECKOUT_VERIFIED` | `PASS` (14 passed) | Local non-mutating test | 2026-08-15 |
| Unit tests (P-06.04 Commands) | `python -m pytest tests/test_p06_04_commands.py -v --tb=short` | `CLEAN_CHECKOUT_VERIFIED` | `PASS` (15 passed) | Local non-mutating test | 2026-08-15 |
| Unit tests (P-08.01 Gemini Client) | `python -m pytest tests/test_p08_01_gemini_client.py -v --tb=short` | `VERIFIED` | `PASS` (39 passed) | Local non-mutating test | 2026-08-16 |
| Unit tests (P-08.02 Structured Output) | `python -m pytest tests/test_p08_02_structured_output.py -v --tb=short` | `VERIFIED` | `PASS` (40 passed) | Local non-mutating test | 2026-08-16 |
| Unit tests (P-08.03 Input Privacy) | `python -m pytest tests/test_p08_03_input_privacy.py -v --tb=short` | `VERIFIED` | `PASS` (10 passed; PRIV-01–08 plus boundary regressions) | Local non-mutating test | 2026-08-16 |
| Unit tests (P-08.04 Blind Audit) | `python -m pytest tests/test_p08_04_blind_audit.py -v --tb=short` | `VERIFIED` | `PASS` (18 tests) | Local non-mutating test | 2026-08-16 |
| Unit tests (P-08.05 Metrics) | `python -m pytest tests/test_p08_05_metrics.py -v --tb=short` | `VERIFIED` | `PASS` (11 tests) | Local non-mutating test | 2026-08-16 |
| Unit tests (Full Suite) | `python -m pytest tests/` | `CLEAN_CHECKOUT_VERIFIED` | `FAIL` (1028 passed, 1 warning, 3 errors: missing `project` fixture in `test_gcp_access.py`) | Local test suite execution | 2026-08-16 |
| Format | `uv run python scripts/cmd.py format` | `CLEAN_CHECKOUT_VERIFIED` | `FAIL` (Reports unformatted historical files) | Non-mutating (`ruff format --check .`) | 2026-08-15 |
| Lint | `uv run python scripts/cmd.py lint` | `CLEAN_CHECKOUT_VERIFIED` | `FAIL` (Reports historical lint debt) | Non-mutating (`ruff check .`, no `--fix`) | 2026-08-15 |
| Type-check | `uv run python scripts/cmd.py type-check` | `CLEAN_CHECKOUT_VERIFIED` | `FAIL` (Reports 2 errors in `test_gcp_access.py`) | Non-mutating (`mypy domain tests src`) | 2026-08-15 |
| Unit | `uv run python scripts/cmd.py unit` | `VERIFIED` | `PASS` (1028 passed, 1 warning) | Non-mutating (`--ignore=tests/test_gcp_access.py`) | 2026-08-16 |
| Integration | `uv run python scripts/cmd.py integration` | `CLEAN_CHECKOUT_VERIFIED` | `FAIL_CLOSED` (Exit 1, zero cloud access without `--live-write-danger`) | Guarded live writes (`tests/test_gcp_access.py`) | 2026-08-15 |
| E2E | `uv run python scripts/cmd.py e2e` | `CLEAN_CHECKOUT_VERIFIED` | `NOT_RUN` (Exit 1, owning phase P-24/P-25 pending) | Deferred workflow | 2026-08-15 |
| Demo | `uv run python scripts/cmd.py demo` | `CLEAN_CHECKOUT_VERIFIED` | `NOT_RUN` (Exit 1, owning phase P-24 pending) | Deferred demo | 2026-08-15 |
| Deploy | `uv run python scripts/cmd.py deploy` | `CLEAN_CHECKOUT_VERIFIED` | `NOT_RUN` (Exit 1, owning phase P-28 pending) | Deferred infrastructure | 2026-08-15 |
| Teardown | `uv run python scripts/cmd.py teardown` | `CLEAN_CHECKOUT_VERIFIED` | `NOT_RUN` (Exit 1, owning phase P-28 pending) | Deferred teardown | 2026-08-15 |
