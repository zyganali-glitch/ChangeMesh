# ChangeMesh — Memory and Lessons

This is the durable minefield and lessons record, not a chronological chat log.

## Entry format

### LESSON-YYYYMMDD-NN — Title
- Date/time:
- Active task:
- Symptom:
- Root cause:
- Incorrect approach:
- Correct approach:
- Prevention rule:
- Tests/evidence:
- Affected files:
- Reusable beyond this task:
- Status: `ACTIVE|SUPERSEDED`
- Superseded by:

## Initial non-negotiable lessons

### LESSON-20260806-01 — Governance must not become product friction
- Active task: Project charter
- Root cause: Reusing the full Universal Agent OS interview and approval model would weaken the hackathon's autonomy objective.
- Prevention rule: Development governance may be strict, but product runtime remains autonomous by default and escalates only irreducible authority decisions.
- Status: `ACTIVE`

### LESSON-20260806-02 — Antigravity is a development surface, not runtime proof
- Root cause: Confusing coding assistant behavior with the submitted autonomous product.
- Prevention rule: Product runtime evidence must come from Google ADK, Gemini API/Vertex AI, and deployed Google Cloud services.
- Status: `ACTIVE`

### LESSON-20260806-03 — Discovery is not capability proof
- Root cause: Registry entries or agent cards can declare skills without demonstrating safe performance.
- Prevention rule: Route critical work only to an exact revision with a valid Capability Passport.
- Status: `ACTIVE`

### LESSON-20260806-04 — Memory is not authoritative by default
- Root cause: Long-term agent memory can be stale, contradictory, sensitive, or poisoned.
- Prevention rule: Decision-relevant memory requires type, provenance, scope, expiry, sensitivity, and evidence; untrusted content is quarantined.
- Status: `ACTIVE`

### LESSON-20260806-05 — A blocked action did not run
- Prevention rule: `BLOCKED` preserves execution state as `NOT_RUN`; never claim a safety control executed the underlying action.
- Status: `ACTIVE`

### LESSON-20260807-06 — Local Google Cloud Authentication Pitfall
- Date/time: 2026-08-07
- Active task: P-02.03
- Symptom: `google.auth.exceptions.DefaultCredentialsError` occurred even after user ran `gcloud auth login`.
- Root cause: `gcloud auth login` only authorizes the CLI, it does not create the `application_default_credentials.json` required by the Python SDK (`google-genai`).
- Incorrect approach: Assuming `gcloud auth login` is sufficient for Vertex AI local execution.
- Correct approach: Must explicitly run `gcloud auth application-default login` to generate the `.json` file for the SDK. Also, when running from PowerShell scripts, bypass execution policy if needed: `gcloud.cmd auth application-default login`.
- Prevention rule: Before running local Vertex AI agent code, verify ADC file exists or prompt user to run `gcloud auth application-default login`.
- Status: `ACTIVE`

### LESSON-20260811-01 — replace_file_content can duplicate content on mixed line endings
- Date/time: 2026-08-11
- Active task: P-04.05
- Symptom: `replace_file_content` inserted a full duplicate of the file header and all ADRs when trying to append a new ADR to `DECISION_LOG.md`.
- Root cause: The file had mixed CRLF/LF line endings. The replacement target content used LF but the file had CRLF up to the replacement point. The tool's best-effort matching duplicated the entire original content.
- Incorrect approach: Attempting a single large replacement block that spans existing trailing content in a file with mixed line endings.
- Correct approach: After any `replace_file_content` on mixed-ending files, immediately inspect the result. Prefer small, targeted replacements. When corruption occurs, fix with a subsequent call targeting the exact corrupted content, then verify again.
- Prevention rule: Always verify file state after any `replace_file_content` that reports inaccuracies. Inspect both head and tail of the file.
- Status: `ACTIVE`

### LESSON-20260813-04 — Pydantic field-type validation fires before model_validator
- Date/time: 2026-08-13
- Active task: P-05.04
- Symptom: Negative tests for `ApprovalCompressionCard` rejection used `match="HUMAN_AUTHORITY_REQUIRED"` but `ValidationError` fired at the `authority_slot_ref: str` field-type check (received `None`) before reaching the `model_validator` that checks autonomy class.
- Root cause: Pydantic validates field types before running `model_validator(mode="after")`. When the `AutonomyDecision` has `authority_slot_ref=None` and the card declares `authority_slot_ref: str`, the type check rejects first.
- Incorrect approach: Expecting the model_validator error message in `pytest.raises(ValidationError, match=...)` when the field-type check fires first.
- Correct approach: For negative tests where rejection is expected at any validation layer, use `pytest.raises(ValidationError)` without `match=` and provide explicit `authority_slot_ref` to ensure the correct validator fires. Alternatively, test the card-specific validator by supplying valid field types to bypass field-level checks.
- Prevention rule: When writing negative tests for Pydantic models with `model_validator`, consider whether field-type validation might trigger first. Construct test data that reaches the intended validator.
- Status: `ACTIVE`

### LESSON-20260815-01 — Avoid dual-runtime (Python + Node) complexity when web dashboard can be vanilla static assets
- Date/time: 2026-08-15
- Active task: P-06.01
- Symptom: Having a Node.js runtime/bundler in an ADK-centered Python project creates multi-runtime container bloat, dual-engine CI/CD pipelines, and npm dependency maintenance overhead.
- Root cause: Prematurely adopting a JS frontend framework (React/Next.js/Vite) before verifying if vanilla web assets are sufficient for the judge/operator dashboard.
- Incorrect approach: Defaulting to Node.js / TypeScript / npm tooling for simple dashboard interfaces in a Python-first AI hackathon project.
- Correct approach: Formally evaluate runtime necessity. Pin Python 3.13.5 as the single unified backend/agent runtime and declare Node `NOT_REQUIRED`, serving the dashboard as vanilla HTML/CSS/JS with zero build steps.
- Prevention rule: Prefer unified single-runtime architectures unless external hard constraints require a second runtime.
- Status: `ACTIVE`

### LESSON-20260815-02 — Developer verification commands must be non-mutating check-only gates, not auto-mutations
- Date/time: 2026-08-15
- Active task: P-06.04
- Symptom: Running `scripts/cmd.py format` mutated 30+ files across frozen domain contracts, creating massive untracked churn. Meanwhile, authorized integration called `pytest tests/test_gcp_access.py`, which caused pytest collection to fail on missing `project` fixtures because `test_gcp_access.py` is a standalone script.
- Root cause: Confusing formatting check commands (`ruff format --check`) with auto-fix formatters (`ruff format`), and confusing pytest collection with standalone script execution.
- Incorrect approach: Allowing developer verification commands to mutate source code, or editing frozen legacy test scripts merely to satisfy pytest collection.
- Correct approach: Use `ruff format --check .` for verification commands. When standalone scripts need execution upon explicit authorization, dispatch them directly with `python <script>` rather than invoking pytest collection.
- Prevention rule: Verification commands must never mutate files. Distinguish command interface verification from underlying check results: a verification command works correctly when it faithfully reports repository debt without rewriting history or modifying frozen domain contracts.
- Status: `ACTIVE`

### LESSON-20260815-03 — Multi-Agent Concurrency and Sequential Fallback Determinism
- Date/time: 2026-08-15
- Active task: P-07.04
- Symptom: Asserting canonical state equivalence between parallel execution and sequential fallback failed because synthetic default payloads used `datetime.now(timezone.utc)` generating different microseconds across runs.
- Root cause: Volatile runtime timestamps inside business payloads break machine equivalence comparisons unless either the payload generator uses deterministic timestamps or the projection layer normalizes temporal metadata.
- Incorrect approach: Allowing arbitrary dynamic timestamps in synthetic test fixture builders, or using wall-clock timing delays (`asyncio.sleep`) to synchronize concurrency tests.
- Correct approach: Use deterministic synchronization (`asyncio.Event` / barriers) for overlap tests; use deterministic base timestamps in synthetic default builders; index `asyncio.gather` results strictly according to caller plan order rather than arrival order to maintain deterministic single-writer aggregation.
- Prevention rule: Machine-testable equivalence between execution strategies requires strict separation of volatile observability metadata (trace IDs, execution durations) from canonical business outcome state.
- Status: `ACTIVE`

### LESSON-20260815-04 — Pydantic frozen models provide shallow immutability; multi-agent isolation requires deep snapshotting and non-bypassable safety gates
- Date/time: 2026-08-15
- Active task: P-07.04 (QA Repair)
- Symptom: Pydantic `ConfigDict(frozen=True)` prevents top-level attribute reassignments on models, but nested collections (e.g. `list[str]` in payloads or `required_capabilities` in `RoutingRequest`) remain mutable in Python. When multiple branch specs share or alias input objects, an in-place mutation inside one branch runner could leak across concurrent or sequential branches or mutate caller data. Additionally, an external `force_strategy=PARALLEL` parameter could potentially bypass `is_parallel_safe()` checks if not routed through the safety gate.
- Root cause: Confusing shallow model immutability with deep object isolation, and allowing caller override parameters to bypass coordinator safety invariants.
- Incorrect approach: Relying solely on `frozen=True` without deep copying nested collections, or allowing `force_strategy=PARALLEL` to skip safety evaluation.
- Correct approach: (1) In `BranchCoordinator.execute_plan()`, evaluate `is_parallel_safe()` for all requests for parallel execution (`plan.strategy == PARALLEL`, `force_strategy == PARALLEL`, or `execute_parallel()`), automatically falling back to sequential execution with `fallback_triggered=True` if unsafe; (2) Store `BranchPlan.branches` as an immutable sequence with deep copy validators; (3) In `execute_branch()`, deep copy the branch spec (`isolated_spec = copy.deepcopy(spec)`) before dispatching to the router and runner.
- Prevention rule: Multi-agent execution engines must guarantee complete deep runtime input isolation and non-bypassable safety gates. Never allow an override parameter or shallow wrapper to suppress safety fallback.
- Status: `ACTIVE`

### LESSON-20260816-01 — Bounded Gemini model client single retry authority and usage metadata compatibility
- Date/time: 2026-08-16
- Active task: P-08.01
- Symptom: (1) Relying on undocumented SDK retry behavior risks hidden retry multiplication between wrapper and transport; (2) In `google-genai` 2.18.1, `GenerateContentResponseUsageMetadata` uses `candidates_token_count` instead of `response_token_count` for candidate token output tracking.
- Root cause: (1) Stacking wrapper retries on top of SDK internal retry loops creates unbounded exponential delays; (2) SDK Pydantic models evolve token count field naming across major/minor SDK versions.
- Incorrect approach: Allowing ambient SDK retry settings to govern reliability, or assuming fixed token field naming without fallback attribute checking.
- Correct approach: (1) Own retry explicitly in `BoundedGeminiClient` with bounded max attempts (3), observable status codes, and injected deterministic sleep functions for instant test execution; (2) Defensively extract candidate output tokens checking both `candidates_token_count` and `response_token_count`.
- Prevention rule: External SDK integrations must enforce exactly one explicit retry authority and defensively handle evolving response metadata schemas.
- Status: `ACTIVE`

### LESSON-20260816-02 — Pydantic v2 Strict types vs JSON String Enum Parsing, Mandatory schema_version, and Zero-Default Deserialization Boundaries
- Date/time: 2026-08-16
- Active task: P-08.02
- Symptom: (1) Setting model-wide `ConfigDict(strict=True)` in Pydantic v2 blocks deserialization of JSON strings into Enum instances (e.g. `"LOW"` -> `SemanticRiskLevel.LOW`) because `strict=True` requires the input value to already be an exact Python Enum instance; (2) Allowing Pydantic default values or `Field(default_factory=list)` on LLM response models masks model omission bugs by silently fabricating empty lists/defaults rather than failing closed; (3) Unversioned structured outputs allow payload schema drift across prompt iterations.
- Root cause: (1) Pydantic v2 strict mode enforces exact Python types on all fields including Enums when configured globally; (2) Default field initializers provide silent fallback injection that violates zero-trust fail-closed parsing contracts; (3) LLM output models require explicit, non-coercing version validation.
- Incorrect approach: Disabling type strictness entirely, writing complex custom pre-validators for all enums, using default factories to hide missing LLM fields, or relying on model prompt compliance without programmatic schema_version validation.
- Correct approach: Use `ConfigDict(extra="forbid", frozen=True)` on all output models; use `StrictInt` and `StrictStr` on scalar fields to strictly forbid silent coercion (e.g. string to int or bool to str); allow Enum fields to parse valid string values natively while rejecting invalid ones; require `schema_version: StrictStr` with no default, and enforce that its explicitly supplied value equals `CANONICAL_STRUCTURED_SCHEMA_VERSION` (`"1.0.0"`) via `validate_canonical_schema_version` on every root schema; make all root and nested collection fields strictly required without default/default_factory values; and apply deterministic security validators (`validate_safe_relative_path`, `validate_safe_endpoint`, `validate_action_type`) to reject path traversal and malicious payloads.
- Prevention rule: When validating JSON model responses, pair `StrictStr`/`StrictInt` with controlled enum vocabularies, `extra="forbid"`, mandatory required `schema_version` matching canonical `"1.0.0"` via validation, zero default/default_factory injections, and deterministic security boundary checks.
- Tests/evidence: `tests/test_p08_02_structured_output.py` (40 tests passed).
- Affected files: `src/core/gemini_structured_output.py`, `tests/test_p08_02_structured_output.py`.
- Reusable beyond this task: Yes (all future LLM structured output parsing and schema validation).
- Status: `ACTIVE`

### LESSON-20260816-03 — Privacy must be enforced before the sole SDK call
- Date/time: 2026-08-16
- Active task: P-08.03
- Symptom: A prompt helper alone could be ignored by another caller, while a direct model-client caller could still submit raw content. A tracked-file secret scanner also correctly rejected literal private-key marker text in detector/test source.
- Root cause: Input minimization and model-call ownership are separate boundaries; detector implementations and fixtures can themselves resemble credential material.
- Incorrect approach: Relying only on prompt-builder conventions, retaining matched excerpts for diagnostics, or placing literal credential markers in tracked tests/source.
- Correct approach: Keep one category-only detector/allowlist owner in `src/agents/policy_guardian.py`, call it from `BoundedGeminiClient` for prompt and system instruction before SDK request construction, reject review findings rather than escalating them, and construct test markers without contiguous credential signatures.
- Prevention rule: Every model path must have a deterministic pre-SDK gate with zero-call negative evidence; privacy findings may retain only non-sensitive reason codes, severity, and offsets.
- Tests/evidence: `tests/test_p08_03_input_privacy.py` (10 passed); combined P-08 suite (89 passed); canonical unit suite (999 passed, 1 warning); tracked secret scan (PASS); full suite remains historical GCP fixture debt.
- Affected files: `src/agents/policy_guardian.py`, `src/core/gemini_client.py`, `src/core/gemini_structured_output.py`, `tests/test_p08_03_input_privacy.py`.
- Reusable beyond this task: Yes (all future model-boundary integrations and privacy tests).
- Status: `ACTIVE`

### LESSON-20260816-04 — Blind-audit reconciliation must retain locked fact map and reject model-manufactured human authority
- Date/time: 2026-08-16
- Active task: P-08.04
- Symptom: The first reconciliation implementation removed the local claim lookup while adding citation-scope validation; additionally, an early pattern attempted to set `human_review_required=True` on model disagreements, violating the 4-lane authority invariant.
- Root cause: Validation and reconciliation used two adjacent lookup responsibilities without one shared canonical map, and model disagreement was erroneously allowed to manufacture a human authority slot.
- Incorrect approach: Treating model claim IDs and deterministic claim state as interchangeable or allowing model disagreement/uncertainty to route itself into a required human approval gate.
- Correct approach: Build one `locked_by_id` map, validate model claims/citations against it, reuse it to produce immutable reconciliation records, record semantic disagreements as advisory conflicts (`relation="DISAGREEMENT_WITH_LOCKED_STATE"`, `conflict_detected=True`, `review_state="SEMANTIC_DISAGREEMENT"`), and strictly set `human_review_required=False`.
- Prevention rule: Blind-audit code must validate identity, citation scope, and fact reconciliation against one locked deterministic map, and model disagreement can never create human authority.
- Tests/evidence: `tests/test_p08_04_blind_audit.py` (18 passed).
- Affected files: `src/agents/evidence_auditor.py`, `tests/test_p08_04_blind_audit.py`.
- Reusable beyond this task: Yes (semantic reconciliation, authority boundaries, and human-on-the-loop exception design).
- Status: `ACTIVE`

### LESSON-20260816-05 — Cost telemetry must never infer provider pricing; project budget policy must be explicit
- Date/time: 2026-08-16
- Active task: P-08.05
- Symptom: Latency, token counts, and retry attempts were measured, but missing pricing/token prerequisites could produce a false aggregate budget PASS, rate card identifiers were silently defaulted, and caller selection of PROVIDER_CALIBRATED could manufacture calibrated pricing claims.
- Root cause: Missing cost/token checks were evaluated as `!= "FAIL"` instead of requiring that all configured dimensions actually ran and passed; rate cards had default `rate_card_id` / `provenance_kind`; and artifact generation derived calibration purely from the caller's enum.
- Incorrect approach: Hard-coding a plausible token price, silently treating absent rates as zero cost or PASS, defaulting rate provenance, allowing caller assertions to manufacture calibration truth, or confusing local project/demo limits with provider SLAs.
- Correct approach:
  1. Accept an explicit immutable `GeminiCostRateCard` requiring non-empty `rate_card_id` and explicit structured `RateProvenanceKind` (`TEST_FORMULA`, `CUSTOM_UNVERIFIED`, `PROVIDER_CALIBRATED`). Calculate cost only when measured token counts and both rates exist, reporting `cost_status="CALCULATED"`, and report `cost_status="NOT_RUN"` otherwise without guessing.
  2. Define deterministic `ModelCallBudgetPolicy` (`DEMO_MAX_LATENCY_MS = 30000.0`, `DEMO_MAX_COST_USD = 0.05`, `DEMO_MAX_TOTAL_TOKENS = 12288`) and `evaluate_model_call_budget()`, enforcing fail-closed aggregate evaluation (`overall_status` = `PASS` / `FAIL` / `NOT_RUN`, where `NOT_RUN` never contributes to aggregate `PASS`).
  3. Export deterministic, non-secret metrics artifacts via `build_model_metrics_artifact()` and `export_metrics_artifact_json()` where `provider_pricing_calibrated` is strictly `False` without verified calibration evidence.
- Prevention rule: Cost estimates require explicit, named rate provenance; missing pricing/tokens must report `NOT_RUN` and fail closed on aggregate budget evaluation (never implicit zero or false PASS); caller assertion != verified provider truth; budget policies must be deterministic and distinct from provider SLAs.
- Tests/evidence: `tests/test_p08_05_metrics.py` (13 passed); P-08 suite (120 passed); canonical unit (1030 passed).
- Affected files: `src/core/gemini_client.py`, `src/core/__init__.py`, `tests/test_p08_05_metrics.py`, `docs/COST_PLAN.md`.
- Reusable beyond this task: Yes (all provider-cost, budget telemetry, and execution evidence).
- Status: `ACTIVE`

### LESSON-20260816-06 — Event retry bounds, failure differentiation, and static scanner collisions
- Date/time: 2026-08-16
- Active task: P-09.03
- Symptom: A naive retry loop could infinitely retry deterministic schema errors (wasting quota and causing queue head-of-line blocking), retry exhaustion might be tempted to claim human escalation, and literal secret tokens in test payloads / regexes triggered repository static security scanners.
- Root cause:
  1. Transient network errors (timeouts, connection resets) and deterministic payload errors (malformed JSON, schema version mismatch, secret payload, causal conflict) require different handling.
  2. Retry exhaustion is a system failure mode, not a business policy escalation boundary.
  3. Static secret scanners scan all tracked files for contiguous credential signatures (e.g. literal private key headers or `ghp_` tokens).
- Incorrect approach:
  1. Blindly retrying every failed event delivery up to `max_attempts`.
  2. Setting `human_authority_required=True` when retries are exhausted.
  3. Putting literal contiguous private keys or token strings in test files or regex definitions.
- Correct approach:
  1. Differentiate failures via `classify_failure`: deterministic invalid errors fail immediately on attempt 1 with zero retries; transient errors retry with bounded exponential backoff up to `max_attempts`.
  2. Terminal exhaustion routes to dead-letter (`DeadLetterEventRecord`) and emits `TerminalFailureHandoff` with `human_authority_required=False`.
  3. Construct test credentials with string concatenation (e.g. `"-" * 5 + "BEGIN..."`, `"ghp_" + "..."`) and regexes with quantified dashes (`-{5}`).
- Prevention rule: Never retry deterministic schema errors; dead-letter handoffs must never manufacture human authority; build test secret fixtures with non-contiguous dynamic strings.
- Tests/evidence: `tests/test_p09_03_retry_dead_letter.py` (8 passed); canonical unit suite (1067 passed, 1 warning).
- Affected files: `events/retry.py`, `events/dead_letter.py`, `events/wire.py`, `tests/test_p09_02_pubsub_adapters.py`, `tests/test_p09_03_retry_dead_letter.py`.
- Reusable beyond this task: Yes (all queueing, event dispatch, dead-letter, and test fixture construction).
- Status: `ACTIVE`

