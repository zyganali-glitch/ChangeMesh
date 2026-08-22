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

### LESSON-20260816-07 — Out-of-order causal event arrival vs DAG projection, log secrecy, and handler failure semantics
- Date/time: 2026-08-16
- Active task: P-09.05 / P-09.04
- Symptom: Distributed event delivery can deliver child/grandchild before parent; rejecting child on ingest causes distributed deadlock. Logging raw exceptions can leak credentials contained in third-party error messages. Swallowing handler errors records false delivery acceptance.
- Root cause:
  1. Ingestion layer receives distributed events out of wall-clock order; causal relationship must be verified at DAG projection/export rather than rejecting on ingest.
  2. Exception strings from network libraries or auth callbacks can contain raw secrets/tokens; logger calls with raw `e` violate secrecy invariants.
  3. LocalEventBus dispatch must not record an event as accepted in delivery state if subscriber handler raises an exception.
- Incorrect approach:
  1. Rejecting events during ingestion if `causation_id` is not yet known.
  2. Formatting logger messages with raw exception `e`.
  3. Marking delivery state accepted before or regardless of subscriber handler success.
- Correct approach:
  1. Store ingested events in `CausalEventTimeline`; perform DAG topological sort (Kahn's algorithm) with dynamic depth computation in `get_causally_ordered_entries()`, strictly failing closed if any predecessor is unresolved, if correlation IDs mismatch, or if a cycle exists.
  2. Wrap all exception logger calls with `sanitize_error_message(str(e))`.
  3. In `LocalEventBus.publish_message()`, record accepted in `_delivery_state` only when all subscriber handlers complete successfully without exception.
- Prevention rule: Ingest out-of-order safely, fail closed at DAG projection; sanitize all exception logs with regexes; record delivery state only upon verified handler success.
- Tests/evidence: `tests/test_p09_05_pubsub_timeline.py` (14 passed), `tests/test_p09_04_local_event_bus.py` (14 passed), all P-09 tests (76 passed), canonical unit (1106 passed).
- Affected files: `src/evidence/pubsub_timeline.py`, `events/local_bus.py`, `integrations/gcp/pubsub_adapter.py`, `events/retry.py`.
- Reusable beyond this task: Yes (all distributed event timelines, saga event logging, and local bus dispatches).
- Status: `ACTIVE`

### LESSON-20260816-08 — Single Local Retry Owner, Observable Terminal Dead-Letter Handoffs, Process-Local Replay Idempotency, and Reject != Redact Ingestion Truth
- Date/time: 2026-08-16
- Active task: P-09 Final Closure Repair
- Symptom:
  1. Multiple uncoordinated retry loops in local bus and consumers create stacked retry delays and test flakiness.
  2. Terminal dead-letter failures construct handoffs internally but discard them, leaving callers blind to failure diagnostics.
  3. Replaying the same terminal failure event produces duplicate dead-letter handoff records.
  4. Confusing secret payload rejection on ingest with structural redaction on accepted payloads obscures security boundaries.
- Root cause:
  1. Lack of a single designated local retry owner (`execute_with_retry()`) wired across local publishers and consumers.
  2. `EventPublishResult` and `EventConsumeResult` lacked `dead_letter_record` fields for caller visibility.
  3. Dead-letter construction lacked process-local identity indexing `(change_id, original_event_id) -> record`.
  4. Describing payload masking as the primary defense rather than stating that secret payloads fail closed on ingest via `scan_payload_for_secrets` (REJECT != REDACT).
- Incorrect approach:
  1. Adding nested retry loops across local dispatch layers or relying on unbounded retries.
  2. Swallowing terminal failure handoffs without attaching them to caller-visible result objects.
  3. Re-emitting fresh dead-letter records on duplicate replayed terminal events.
  4. Accepting secret-bearing messages and relying solely on downstream field redaction.
- Correct approach:
  1. Designate `execute_with_retry()` as the single local retry owner in `LocalEventBus` and `LocalEventConsumer`; isolate sibling handler retries.
  2. Expose `dead_letter_record: Optional[DeadLetterEventRecord]` on `EventPublishResult` and `EventConsumeResult` with caller-visible metadata (`event_id`, `change_id`, `correlation_id`, `topic_id`, attempts made, failure classification, `human_authority_required=False`, and sanitized diagnostics).
  3. Implement thread-safe `ProcessLocalDeadLetterState` with `compute_dead_letter_id`, guaranteeing that replaying the exact same terminal event returns the identical logical handoff without duplicate emission.
  4. Strictly reject secret-bearing payloads on ingest via `scan_payload_for_secrets`, using `redact_mapping` only as structural defense-in-depth on accepted payloads.
  5. Implement `GooglePubSubDeadLetterConsumer` to convert dead-letter subscription messages into canonical handoffs.
### LESSON-20260817-01 — Explicit ExecutionEvidenceMode Separation, Fail-Closed Live Writes, IN_PROGRESS Lock Exclusion, and Durable Idempotency Grounding in External Adapters
- Date/time: 2026-08-17
- Active task: P-19 Surgical Repair
- Symptom: (1) `BoundedGitHubAdapter.is_live` was inferred purely from token presence (`bool(self._token)`), and `execute()` defaulted to `LIVE_WRITE` mode without performing real API mutation, fabricating synthetic URLs and SHA values; (2) In-memory process dictionaries (`_created_prs`, `_commits`) lost state on process restart; (3) `IN_PROGRESS` reservation status was not handled in `_execute_live_write()`, allowing concurrent workers to fall through into live transport execution; (4) Payload digest included ephemeral `request_id` instead of pure semantic mutation fields; (5) `EXACT_REPLAY` loosely synthesized branch URLs rather than strictly revalidating persisted real provider evidence; (6) Fixture execution emitted provider-like identifiers (`pull/1`, `fixture-sha`).
- Root cause: (1) Inverting mode selection by inferring `LIVE_WRITE` from credential existence rather than requiring explicit `ExecutionEvidenceMode.LIVE_WRITE` in the request; (2) Treating envelope identity as mutation semantics; (3) Missing explicit `IN_PROGRESS` reservation status gate; (4) Missing live receipt revalidation on replay; (5) Emitting realistic-looking identifiers during simulation.
- Incorrect approach: Defaulting to `LIVE_WRITE` whenever a token is provided; manufacturing simulated identifiers under a `LIVE_WRITE` label; allowing `IN_PROGRESS` to execute transport; mixing `request_id` into mutation digests.
- Correct approach:
  1. Require explicit `request.evidence_mode == ExecutionEvidenceMode.LIVE_WRITE` to attempt live writes. FIXTURE and SIMULATION modes must perform zero network calls and strictly return non-live evidence modes (`FIXTURE`/`SIMULATION`) with `None` for provider identifiers (no `github.com/.../pull/` URLs and no provider commit SHAs).
  2. Enforce fail-closed validation for `LIVE_WRITE`: require non-empty adapter-owned credentials, valid repository target (`owner/repo`), valid non-empty branch/commit/PR inputs, and active real transport. Missing prerequisites fail closed without fabricating success or identifiers.
  3. Validate real response identifiers (valid GitHub PR URL pattern, valid commit hex SHA, valid branch ref URL). Missing or malformed responses fail closed and cannot produce `LIVE_WRITE` receipts.
  4. Ground `LIVE_WRITE` idempotency in durable `SagaStateRepository` via `IdempotencyKeyManager.reserve_intent` / `commit_intent`. Only `GRANTED` reservation status may invoke the transport; `IN_PROGRESS` fails closed with zero transport calls without releasing the active worker's lease; `EXACT_REPLAY` revalidates cached real identifiers and fails closed if malformed.
  5. Build `payload_digest` strictly from semantic mutation fields (action, repository, branch, pr_title, pr_body, files, commit_message), excluding ephemeral `request_id`.
  6. Strictly sanitize credentials from models, receipts, logs, metadata, and error messages.
- Prevention rule: External adapters must never infer live write mode from credentials, must never return fabricated identifiers labeled as `LIVE_WRITE`, must block `IN_PROGRESS` reservations from transport execution, and must ground live mutation idempotency in durable persistence.
- Tests/evidence: `tests/test_p19_release_steward.py` (26 passed); canonical unit suite (1246 passed, 1 warning).
- Affected files: `integrations/github/github_adapter.py`, `src/release/receipt_manager.py`, `tests/test_p19_release_steward.py`.
- Reusable beyond this task: Yes (all external write adapters, GitHub/cloud integrations, and receipt managers).
- Status: `ACTIVE`

### LESSON-20260817-02 — Mandatory Durable Idempotency Grounding, Protected Branch Update Prevention, Post-Mutation Ambiguity Reservation Retention, and Read-Based Reconciliation
- Date/time: 2026-08-17
- Active task: P-19.01 Safety Hardening
- Symptom: (1) An external write adapter could execute `LIVE_WRITE` mutations with a real transport without passing a `SagaStateRepository`, bypassing P-10 durable idempotency; (2) `CREATE_COMMIT` lacked branch validation, allowing direct commits to protected branches (`main`, `master`, `prod`, `production`, `release`) or None; (3) If the external provider mutation succeeded but the local durable `commit_intent` persistence failed, releasing the reservation could allow a retry to issue a duplicate external mutation; (4) Retries after lease expiry or process restart lacked read-based provider reconciliation (`find_existing`) before attempting re-mutation.
- Root cause: (1) `is_live` property and `_execute_live_write` did not enforce `state_repository is not None`; (2) Protected branch validation was applied only to `CREATE_BRANCH` rather than both `CREATE_BRANCH` and `CREATE_COMMIT`; (3) Transport execution error handling did not differentiate pre-transport failure (where `release_intent` is correct) from post-provider-success commit persistence failure (where the reservation must be held); (4) Adapter lacked a narrow read/reconciliation hook to inspect existing provider entities before executing fresh mutations.
- Incorrect approach: (1) Allowing live external writes without a durable saga state repository; (2) Releasing idempotency leases after provider-side success when local commit fails; (3) Blindly re-executing transport mutations on retry without first checking if the entity was already created on the provider.
- Correct approach:
  1. Require `state_repository is not None` and valid `tenant_id`/`change_id` for all `LIVE_WRITE` operations. Missing repository or binding fails closed with zero transport calls.
  2. Validate `request.branch` for `CREATE_COMMIT`, strictly failing closed with 0 transport calls if empty or in `PROTECTED_BRANCHES` (`{"main", "master", "prod", "production", "release"}`).
  3. Differentiate failure boundaries: pre-transport exceptions release the reservation via `release_intent`. If provider mutation succeeds (`transport_res.success == True`) but durable `commit_intent` fails, the reservation is held (never released) and an explicit fail-closed indeterminate error is returned requiring reconciliation before retry.
  4. Implement `find_existing()` in `GitHubTransport` Protocol and invoke provider reconciliation before fresh mutations on granted reservations. If the entity exists, validate real identifiers, commit verified real evidence to the durable repository, and return success with zero duplicate mutation calls. If reconciliation check fails/errors, fail closed with zero mutation calls.
- Prevention rule: Never permit live writes without durable state persistence; never release reservation leases after provider-side success; always perform read-based provider reconciliation before re-mutating external state.
- Tests/evidence: `tests/test_p19_release_steward.py` (37 passed); canonical unit suite (1257 passed, 1 warning).
- Affected files: `integrations/github/github_adapter.py`, `tests/test_p19_release_steward.py`.
- Reusable beyond this task: Yes (all external write integrations and dual-write reconciliation boundaries).
- Status: `ACTIVE`

### LESSON-20260818-01 — Mandatory Typed Reconciliation Capability, Provider-Observable Idempotency Markers, and Ambiguous Post-Write Multi-Process Recovery
- Date/time: 2026-08-18
- Active task: P-19.01 Final Narrow Reconciliation-Safety Repair
- Symptom: (1) An external write adapter treated reconciliation capability as optional via `hasattr()` guards, allowing transports lacking `find_existing` to proceed directly to mutation; (2) Untyped/None reconciliation returns could mask network or parse failures as "not found", causing duplicate mutations; (3) Draft PRs lacked a deterministic provider-observable idempotency identity across process restarts; (4) Post-write commit failure followed by genuine lease expiry lacked an end-to-end multi-process integration test verifying that fresh workers query provider state and recover with exactly 1 total mutation.
- Root cause: (1) Permitting mutation without guaranteed reconciliation capability; (2) Overloading `None` for both "checked and confirmed absent" and "unable to check"; (3) Missing non-secret embedded intent markers in provider payloads.
- Incorrect approach: (1) Silently bypassing reconciliation if `find_existing` is absent on the transport; (2) Treating reconciliation errors or exceptions as `NOT_FOUND`; (3) Using `None` as a polymorphic return type for missing, absent, or error states.
- Correct approach:
  1. Enforce that any transport used for `LIVE_WRITE` MUST possess a callable `find_existing` reconciliation method. Missing, `None`, or non-callable capability releases the reservation and fails closed with zero mutation.
  2. Implement strongly-typed reconciliation contracts (`ReconciliationStatus` with `FOUND`, `NOT_FOUND`, `UNKNOWN`, `ERROR`, `GitHubReconciliationQuery`, and `GitHubReconciliationResult`).
  3. Treat only authoritative `NOT_FOUND` as permission to execute a single fresh mutation. Reconciliation query exceptions and `UNKNOWN`/`ERROR` statuses release the reservation and fail closed with zero mutations.
  4. Embed deterministic non-secret intent markers (`<!-- changemesh-intent: key={idempotency_key} digest={payload_digest} -->`) in Draft PR bodies for provider-observable cross-process reconciliation.
  5. Validate full 10-step ambiguous post-write lease expiry and recovery sequence through P-10 state machinery, proving that total transport `execute()` mutation calls remain exactly 1 for the entire scenario.
- Prevention rule: External live write transports must strictly mandate typed reconciliation capability; non-authoritative reconciliation results must fail closed with zero mutations; provider payloads must carry deterministic intent markers.
- Tests/evidence: `tests/test_p19_release_steward.py` (45 passed); canonical unit suite (1265 passed, 1 warning).
- Affected files: `integrations/github/github_adapter.py`, `tests/test_p19_release_steward.py`.
- Reusable beyond this task: Yes (all external mutation boundaries, GitHub/cloud adapters, and dual-write recovery workflows).
- Status: `ACTIVE`

### LESSON-20260818-02 — 5-Point Strict Reconciled Evidence-Identity Verification and Untrusted Caller Idempotency Key Non-Secret Isolation
- Date/time: 2026-08-18
- Active task: P-19.01 Evidence-Identity and Non-Secret Idempotency Repair
- Symptom: (1) An external write adapter accepted `ReconciliationStatus.FOUND` based solely on provider URL formatting without verifying that the found entity matched the expected canonical idempotency key and semantic payload digest; (2) Raw caller idempotency keys (which could contain bearer tokens or arbitrary untrusted tokens) were passed directly into `action_type`, PR body markers, reconciliation queries, and error messages.
- Root cause: (1) Delegating semantic matching verification entirely to the transport double rather than enforcing strict adapter-side cryptographic and semantic binding; (2) Treating caller-supplied idempotency keys as safe internal identifiers instead of untrusted user input.
- Incorrect approach: (1) Assuming `FOUND` implies identity match; (2) Placing raw caller strings into persisted document IDs, markdown markers, and error strings.
- Correct approach:
  1. Enforce strict 5-point adapter-side verification on `FOUND`: (a) valid provider identifier format; (b) `matched_payload_digest` presence; (c) `matched_payload_digest == payload_digest`; (d) `matched_idempotency_key` presence; (e) `matched_idempotency_key == canonical_idempotency_id`. Any mismatch releases the reservation, returns fail-closed `success=False`, performs zero mutation, and never commits durable state.
  2. Treat caller keys as untrusted metadata: derive non-secret SHA-256 fingerprint `fp_{hash[:16]}` for `action_type`. Derive canonical P-10 safe identity `canonical_idempotency_id = IdempotencyKeyManager.compute_canonical_idempotency_key(intent)` (`idem_external_write_<hash>`).
  3. Use only safe canonical identities for PR markers (`<!-- changemesh-intent: key={canonical_idempotency_id} digest={payload_digest} -->`), reconciliation queries, expected match keys, and response identities.
  4. Never leak raw caller strings into persistence records, external bodies, error messages, receipts, or logs.
- Prevention rule: Never accept reconciled provider state without verifying exact 5-point semantic and cryptographic bindings; never propagate raw caller idempotency keys into external payloads, markers, persistence, or diagnostics.
- Tests/evidence: `tests/test_p19_release_steward.py` (61 passed); canonical unit suite (1281 passed, 1 warning).
- Affected files: `integrations/github/github_adapter.py`, `tests/test_p19_release_steward.py`, `docs/P-OMEGA_AUDIT_REPORT.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`, `docs/HANDOFF.md`.
- Reusable beyond this task: Yes (all external write adapters, provider reconciliation bridges, and multi-tenant key management).
- Status: `ACTIVE`

### LESSON-20260818-03 — Structural Isolation of Untrusted Caller Idempotency Keys at Receipt and Evidence Boundaries
- Date/time: 2026-08-18
- Active task: P-19 Narrow Receipt/Evidence-Boundary Repair
- Symptom: `ReceiptManager.create_receipt` recorded `req_meta = {"idempotency_key": str(github_request.idempotency_key or "none")}`, propagating raw caller-supplied idempotency keys into evidence receipts.
- Root cause: Treating caller request metadata as safe receipt evidence rather than consuming the safe canonical adapter output identity (`github_response.idempotency_key`). Regex sanitization is insufficient because ordinary caller tokens and novel secret formats propagate unredacted.
- Incorrect approach: (1) Copying untrusted `github_request.idempotency_key` into receipt metadata; (2) Re-hashing or reconstructing identities inside `ReceiptManager`.
- Correct approach:
  1. Structurally consume only safe adapter output: `req_meta = {"idempotency_key": str(github_response.idempotency_key or "none")}`.
  2. For successful `LIVE_WRITE`, replay, and reconciled actions, the receipt records the safe canonical P-10 identity already produced by the adapter.
  3. If response has no safe identity (e.g. `None` on failed responses or fixtures), record `"none"`.
  4. Never access or copy raw caller request keys anywhere in `ReceiptManager`.
- Prevention rule: Evidence and receipt managers must never propagate raw caller request metadata; receipt identity must be structurally sourced only from validated, safe canonical adapter output.
- Tests/evidence: `tests/test_p19_release_steward.py` (69 passed); canonical unit suite (1289 passed, 1 warning).
- Affected files: `src/release/receipt_manager.py`, `tests/test_p19_release_steward.py`, `docs/P-OMEGA_AUDIT_REPORT.md`, `docs/HANDOFF.md`.
- Reusable beyond this task: Yes (all audit receipts, evidence passports, and external action logs).
- Status: `ACTIVE`

### LESSON-20260818-04 — Production Urllib Transport Reconciliation Grounding, Zero Self-Attestation, and Exhaustive Provider Queries
- Date/time: 2026-08-18
- Active task: P-19.03 Live GitHub Transport Safety Repair
- Symptom: `UrllibGitHubTransport.find_existing` copied `query.idempotency_key` and `query.payload_digest` directly into reconciliation results for branch and commit ref lookups without provider proof (forbidden self-attestation); draft PR queries lacked pagination causing false NOT_FOUND on PRs beyond page 1; execution fell back to guessing 'main' when repository metadata failed.
- Root cause: (1) Conflating provider existence check with cryptographic binding proof; (2) Single-page API requests assuming PRs are in the first 100 items; (3) Silent default-branch fallback violating no-silent-fallback rules.
- Incorrect approach: (1) Echoing expected query keys/digests in transport results; (2) Treating unpaginated REST queries as exhaustive; (3) Guessing 'main' if repository metadata lookup fails.
- Correct approach:
  1. `find_existing` MUST only return values actually observed from provider state. Branch ref 200 returns `UNKNOWN` with `matched_idempotency_key=None, matched_payload_digest=None`. Commit ref distinguishes unrelated HEAD (`NOT_FOUND`), matching message without marker (`UNKNOWN`, fail closed), and exact marker in commit message (`FOUND` with observed marker).
  2. Draft PR queries paginate across all pages (`page=1, 2, ...` with `per_page=100`), ensuring all provider PRs are scanned.
  3. Fail closed if repository metadata cannot authoritatively provide `default_branch` with zero mutations.
  4. Sanitize tokens in all transport error messages and exceptions.
- Prevention rule: Transport layers must never echo expected query keys as provider evidence; provider reconciliation queries must be exhaustive; metadata lookup failures must fail closed.
- Tests/evidence: `tests/test_p19_release_steward.py` (82 passed); canonical unit suite (1302 passed, 1 warning).
- Affected files: `integrations/github/github_adapter.py`, `tests/test_p19_release_steward.py`, `docs/P-OMEGA_AUDIT_REPORT.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`, `docs/HANDOFF.md`.
- Reusable beyond this task: Yes (all production transports, provider reconciliation bridges, and REST API adapters).
- Status: `ACTIVE`

### LESSON-20260818-05 — Module Reload Enum Identity Corruption and Strict Lifecycle Contract Safety
- Date/time: 2026-08-18
- Active task: P-20.01 End-to-End Saga Orchestration
- Symptom: `IllegalTransitionError: Invalid current state type: <enum 'ChangeState'>` occurred when tests used `importlib.reload(change_lifecycle)`.
- Root cause: `importlib.reload` on foundational enum/contract modules creates distinct new class identities in `sys.modules`, corrupting `isinstance()` identity checks.
- Incorrect approach: Duck-typing foreign objects matching `.value` in domain contracts; this weakens domain contract freeze.
- Correct approach:
  1. Never reload foundational domain contract modules inside test cases; use static AST inspection of the raw source file to verify imports without mutating runtime types.
  2. Maintain strict `isinstance(state, ChangeState)` across `is_terminal`, `can_transition`, `require_transition`, rejecting foreign objects and impostors even if `.value` matches.
- Prevention rule: Never call `importlib.reload` on core domain types in unit tests; keep domain contract type checks strictly typed.
- Tests/evidence: `tests/test_p05_02_lifecycle.py` (25 passed); `tests/test_p20_orchestrator_saga.py` (17 passed); canonical unit suite (1329 passed, 1 warning).
- Affected files: `domain/contracts/change_lifecycle.py`, `tests/test_p05_02_lifecycle.py`, `tests/test_p20_orchestrator_saga.py`, `AGENT_MEMORY_AND_LESSONS.md`.
- Reusable beyond this task: Yes (all lifecycle transitions, saga orchestrators, and enum contract validators).
- Status: `ACTIVE`

### LESSON-20260819-06 — Persistence-First Consistency Before Event Publication and Authority Branching Discipline
- Date/time: 2026-08-19
- Active task: P-20.00 / P-20.01 Surgical Repair
- Symptom: (1) Orchestrator published wire events and updated causal timeline before committing state to `SagaStateRepository`, leaving contradictory event evidence if persistence failed; (2) `AutonomyClass.BLOCKED` was incorrectly routed to `AWAITING_AUTHORITY`; (3) Free-form text and caller request descriptions leaked raw tokens into storage and wire envelopes; (4) Local operations were susceptible to false `LIVE_WRITE` labeling.
- Root cause: (1) Inverted state mutation / notification order; (2) Incomplete branching on Policy Guardian gate evaluation result; (3) Lack of early sanitization at the intake boundary; (4) Global mode inheritance without per-stage honesty checks.
- Incorrect approach: (1) Publishing events before database transaction succeeds; (2) Creating fake approval cards for blocked changes; (3) Allowing callers to force reversibility downgrade; (4) Claiming `LIVE_WRITE` for local in-memory operations.
- Correct approach:
  1. Commit state to `SagaStateRepository` with optimistic concurrency check FIRST. If persistence fails, abort immediately without publishing wire messages or appending to timeline.
  2. Explicitly branch on `gate_result.autonomy_class`: if `BLOCKED`, transition to `ChangeState.BLOCKED` with ZERO approval cards and zero downstream execution. If `HUMAN_AUTHORITY_REQUIRED`, transition to `ChangeState.AWAITING_AUTHORITY` and derive `ApprovalRecord` fields directly from `gate_result.compression_card`.
  3. Derive reversibility deterministically via `ReversibilityClassifier.classify_sql`; remove caller overrides.
  4. Sanitize free-form input and wire payload mappings (`sanitize_secrets_in_text`, `redact_mapping`, `scan_payload_for_secrets`) before storage or wire emission.
  5. Local operations are strictly `SIMULATION` or `FIXTURE`; claiming `LIVE_WRITE` for local operations raises `ValueError`.
- Prevention rule: Authoritative state persistence must always precede event publication; hard blockers never produce approval cards; secrets must be minimized before storage/wire emission; mode honesty is strictly enforced.
- Tests/evidence: `tests/test_p20_orchestrator_saga.py` (17 passed); canonical unit suite (1329 passed, 1 warning).
- Affected files: `src/orchestrator/orchestrator_saga.py`, `src/agents/change_orchestrator.py`, `tests/test_p20_orchestrator_saga.py`, `docs/P-20.00_ORCHESTRATOR_SAGA_DONOR_PREFLIGHT.md`.
- Reusable beyond this task: Yes (all saga orchestrators, event-driven workflows, and authority boundaries).
- Status: `ACTIVE`

### LESSON-20260819-07 — Bounded Operation Target Validation and Opposite-Intent Action Fail-Closed Binding
- Date/time: 2026-08-19
- Active task: P-20.00 / P-20.01 Final Closure Repair
- Symptom: (1) Requests targeting only ancillary systems (`target_systems=["payment-service"]`) could be admitted for the schema migration without targeting the required database (`billing-db`); (2) Generic action matching on terms like `"migration"` permitted opposite-action text (e.g. `"Remove payment_tier from billing_accounts migration"`) to match the positive `ADD COLUMN` operation.
- Root cause: (1) Target check only validated subset of allowed targets rather than enforcing presence of the mandatory mutation target; (2) Action matching accepted generic words without requiring explicit positive additive semantics or checking for contradictory/opposite action keywords.
- Incorrect approach: Allowing subset-only target matching and generic action tokens; attempting complex NLP parsing for bounded synthetic operations.
- Correct approach:
  1. Enforce that `request.target_systems` must contain at least one required database target (`billing-db` or `billing_db`).
  2. Reject opposite/contradictory keywords (`remove`, `delete`, `drop`, `rename`, `replace`, `disable`, `rollback`, `truncate`) and destructive keywords (`drop table`, etc.) explicitly.
  3. Require explicit positive additive keywords (`add column`, `add`, `addition`, `additive`, `adding`) and reject generic action tokens (`migration`, `alter table`) alone.
- Prevention rule: Bounded fixture operations must require their mandatory mutation targets and fail closed on opposite/contradictory action semantics.
- Tests/evidence: `tests/test_p20_orchestrator_saga.py` (36 passed); canonical unit suite (1348 passed, 1 warning).
- Affected files: `src/orchestrator/orchestrator_saga.py`, `tests/test_p20_orchestrator_saga.py`, `docs/COMPONENT_PROVENANCE.md`, `docs/P-20.00_ORCHESTRATOR_SAGA_DONOR_PREFLIGHT.md`, `docs/P-OMEGA_AUDIT_REPORT.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`, `docs/HANDOFF.md`, `README.md`.
- Reusable beyond this task: Yes (all bounded fixture operations, intent binding validators, and synthetic demo workflows).
- Status: `ACTIVE`

### LESSON-20260822-01 — ShadowLab Fault, Attack, Replay, and Restart Matrix Isolation
- Date/time: 2026-08-22
- Active task: P-25.03
- Symptom: Rehearsal suites often rely on generic mocks that do not verify actual fault recovery (e.g., verifying backoff delays math or actual compensation DDL rollbacks), or confuse same-process in-memory restart with durable checkpoint restoration.
- Root cause: Missing adversarial validation for prompt injection, memory poisoning, and mode relabeling within the rehearsal twin.
- Correct approach:
  1. Test fault paths by asserting real failure on early attempts before recovery (e.g., HTTP 503 attempt 1 & 2 fail, attempt 3 succeeds with deterministic backoff delays `(100ms, 200ms)`).
  2. Test attack vectors against code-owned deterministic engines (`MemoryQuarantineEngine`, `DeterministicPolicyChecker`, `InjectionDetector`), ensuring adversarial directives never grant authority.
  3. Test replay determinism via exact 64-character SHA-256 simulation digests and prove zero cross-run state accumulation in tool doubles.
  4. Test restart continuation strictly against persisted repository checkpoints (`SagaCheckpointManager` + `InMemorySagaStateRepository`), proving non-duplication of completed tasks.
  5. Enforce immutable `ExecutionEvidenceMode.SIMULATION` output across all ShadowLab scenarios.
- Prevention rule: Synthetic twin rehearsals must test real failure dynamics, remain strictly labeled as `SIMULATION`, and prove durable checkpoint recovery.
- Tests/evidence: `tests/test_p25_03_shadowlab_suite.py` (57 passed); full repo suite (1652 passed, 1 warning).
- Affected files: `tests/test_p25_03_shadowlab_suite.py`, `docs/P-25.03_SHADOWLAB_SCENARIO_REPORT.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all twin simulations, fault rehearsal engines, and resilience benchmarks).
- Status: `ACTIVE`

### LESSON-20260822-02 — Zero-Dependency Accessible Dashboard and Bilingual Translation Parity
- Date/time: 2026-08-22
- Active task: P-25.04
- Symptom: Hackathon browser dashboards often introduce fragile node/npm build dependencies, external CDN font/CSS links that fail in offline/restricted environments, or incomplete English/Turkish localization parity.
- Root cause: Treating the judge dashboard as a heavyweight SPA rather than clean, native, self-contained HTML5/CSS3/ES6 assets.
- Correct approach:
  1. Deliver the dashboard as pure vanilla static assets (`src/dashboard/static/index.html`, `styles.css`, `app.js`) served directly by the Python/Cloud Run service app with zero node build steps or runtime.
  2. Maintain 100% offline/PWA compatibility with zero external CDN/font calls.
  3. Enforce WCAG 2.1 AA color contrast (exceeding 7.0:1 on text), clear keyboard focus visibility, skip-navigation links, and semantic ARIA landmark regions.
  4. Ensure symmetric bilingual translation dictionary parity between English and Turkish surfaces.
- Prevention rule: Judge dashboard must remain zero-dependency, WCAG AA compliant, fully responsive, and bilingual.
- Tests/evidence: `tests/test_p25_04_browser_accessibility.py` (24 passed); full repo suite (1676 passed, 1 warning).
- Affected files: `src/dashboard/static/index.html`, `src/dashboard/static/styles.css`, `src/dashboard/static/app.js`, `service_app.py`, `tests/test_p25_04_browser_accessibility.py`, `docs/P-25.04_BROWSER_ACCESSIBILITY_REPORT.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all judge interfaces, demo web frontends, and accessible dashboards).
- Status: `ACTIVE`

### LESSON-20260822-03 — Automated Markdown Link and Secret Prevention CI Enforcement
- Date/time: 2026-08-22
- Active task: P-25.05
- Symptom: Markdown links across nested directories (e.g. `docs/SUBMISSION_MANIFEST.md` referring to `docs/P-06.05_CLEAN_CHECKOUT_LOG.md`) can easily create broken relative paths (`docs/docs/...`) if not validated by automated tests.
- Root cause: Manual authoring of relative paths without a programmatic link-checker gate.
- Correct approach:
  1. Implement automated test scanning all markdown files (`README.md`, `docs/*.md`) for internal relative file links and verifying their existence against the local filesystem.
  2. Implement repository-wide regex scanner in CI to continuously verify zero real secrets (private keys, live service account tokens, API keys) in code, fixtures, and docs.
  3. Validate master plan task status tokens against a strict closed set of approved tokens.
- Prevention rule: All relative documentation links and secret scanners must run as part of standard automated pytest gates.
- Tests/evidence: `tests/test_p25_05_governance_matrix.py` (10 passed); full repo suite (1686 passed, 1 warning).
- Affected files: `tests/test_p25_05_governance_matrix.py`, `docs/P-25.05_GOVERNANCE_TEST_REPORT.md`, `docs/SUBMISSION_MANIFEST.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all documentation suites, submission packages, and repository governance).
- Status: `ACTIVE`

### LESSON-20260822-04 — One-Command Root Read-Only Release Validation Gate
- Date/time: 2026-08-22
- Active task: P-25.06
- Symptom: Reviewers and judges are forced to manually orchestrate disparate linting, type-checking, donor auditing, and unit test commands, creating evaluation friction and risk of missed gates.
- Root cause: Absence of a unified, platform-portable root validation harness.
- Correct approach:
  1. Provide a single canonical entry point (`uv run python scripts/cmd.py validate` and `scripts/validate.py`) executing all 7 gates sequentially.
  2. Enforce clean ASCII output format without platform-dependent terminal encoding issues (e.g. Windows cp1254).
  3. Output a structured ASCII audit table with Gate Name, Surface, Mode, Status (`PASS`/`NOT_RUN`/`FAIL`), Duration, and Overall Verdict.
  4. Ensure live cloud mutations remain protected and default to `NOT_RUN`.
- Prevention rule: Root release gate must be runnable in one command with zero configuration and zero external cost.
- Tests/evidence: `scripts/validate.py`, `docs/P-25.06_ROOT_VALIDATION_OUTPUT.md`, full suite (1686 passed, 1 warning).
- Affected files: `scripts/cmd.py`, `scripts/validate.py`, `JUDGE_START_HERE.md`, `docs/P-25.06_ROOT_VALIDATION_OUTPUT.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all root validation commands, CI pipelines, and judge evaluation harnesses).
- Status: `ACTIVE`

### LESSON-20260822-05 — Comprehensive STRIDE and OWASP LLM Threat Modeling
- Date/time: 2026-08-22
- Active task: P-26.01
- Symptom: AI agent architectures are frequently deployed with vague security statements that fail to map specific LLM vulnerabilities (indirect injection, memory poisoning, confused deputy, tool abuse) to concrete code controls.
- Root cause: Treating threat modeling as an afterthought rather than a structural contract.
- Correct approach:
  1. Map all 9 canonical agent threat vectors systematically across STRIDE and OWASP Top 10 for LLMs.
  2. Bind every single threat to concrete code implementations (`InjectionDetector`, `MemoryQuarantineEngine`, `CapabilityPassport`, `DeterministicPolicyChecker`, `EvidenceLedger`).
  3. Formally document residual risks and link directly to automated regression test suites.
  4. Include an honest, transparent non-certification boundary statement for evaluators.
- Prevention rule: Every autonomous capability must have an explicit threat model entry with automated test proof.
- Tests/evidence: `docs/THREAT_MODEL.md`, `docs/P-26.01_THREAT_MODEL_REVIEW.md`, `tests/test_p25_03_shadowlab_suite.py`, `tests/test_p25_05_governance_matrix.py`.
- Affected files: `docs/THREAT_MODEL.md`, `docs/P-26.01_THREAT_MODEL_REVIEW.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all autonomous agent fleets, enterprise AI governance, and hackathon threat models).
- Status: `ACTIVE`

### LESSON-20260822-06 — Defense-in-Depth Secret Scanning and Wire Payload Sanitization
- Date/time: 2026-08-22
- Active task: P-26.02
- Symptom: AI applications risk credential leakage across prompt interpolation, JSON logging, wire event dispatch, or public evidence artifacts.
- Root cause: Relying on a single perimeter check rather than continuous multi-layered sanitization.
- Correct approach:
  1. Enforce pre-SDK privacy scanning via `PolicyGuardian.audit_privacy_text()` before model prompts are formatted.
  2. Implement recursive dictionary scrubbing (`redact_mapping`) at all persistence and wire boundaries.
  3. Validate wire messages with `scan_payload_for_secrets` to fail closed before Pub/Sub emission.
  4. Perform automated CI audits on public JSON evidence packs to guarantee zero unredacted tokens.
- Prevention rule: Every prompt, message envelope, log line, and evidence entry must undergo deterministic secret scrubbing.
- Tests/evidence: `tests/test_p26_02_secret_sanitization.py` (8 passed); full repo suite (1686 passed, 1 warning).
- Affected files: `tests/test_p26_02_secret_sanitization.py`, `docs/P-26.02_SECURITY_SANITIZATION_REPORT.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all multi-tenant agent systems, event-driven architectures, and security audits).
- Status: `ACTIVE`

### LESSON-20260822-07 — Zero-Node Container Minimization and Supply Chain Audits
- Date/time: 2026-08-22
- Active task: P-26.03
- Symptom: Enterprise applications often accumulate unpinned transitive dependencies, complex Node.js build dependencies, or bloated container base images with unnecessary attack surfaces.
- Root cause: Treating packaging as an infrastructure detail rather than an auditable security contract.
- Correct approach:
  1. Mandate minimal `python:3.13-slim` base images and verify zero secrets are copied during container build.
  2. Enforce 100% locked dependency hashes via `uv.lock`.
  3. Eliminate Node.js runtime and build tools entirely (zero `package.json` / `node_modules`).
  4. Write programmatic vulnerability audit scripts (`scripts/audit_dependencies.py`) integrated into CI.
- Prevention rule: Production containers must remain minimal, lockfile-pinned, and free of unnecessary build toolchains.
- Tests/evidence: `scripts/audit_dependencies.py`, `tests/test_p26_03_dependency_audit.py` (4 passed); full suite (1686 passed).
- Affected files: `scripts/audit_dependencies.py`, `tests/test_p26_03_dependency_audit.py`, `docs/P-26.03_DEPENDENCY_CONTAINER_VULNERABILITY_REPORT.md`, `docs/SUBMISSION_MANIFEST.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all containerized microservices, Python agent runtimes, and Cloud Run deployments).
- Status: `ACTIVE`

### LESSON-20260822-08 — Structural Draft-Only PR Ceilings and External-Write Lockdown
- Date/time: 2026-08-22
- Active task: P-26.04
- Symptom: Unconstrained AI agents can inadvertently trigger auto-merges, push directly to production branches, or run destructive DDL statements against enterprise databases.
- Root cause: Relying on soft system prompts rather than structural type-level and policy-level boundaries.
- Correct approach:
  1. Enforce enum-level exclusion of destructive operations (`GitHubAction` excludes MERGE, DELETE_REPO, FORCE_PUSH).
  2. Implement protected branch validation blocking direct commits to `main`, `master`, `prod`.
  3. Lock down governance paths (`domain/contracts/`, `.github/`, `.env`) with deterministic policy gates.
  4. Classify destructive DDLs without rollback plans as `IRREVERSIBLE_DESTRUCTIVE` and halt at human approval boundaries.
- Prevention rule: Autonomous code agents must be structurally bounded to draft-only pull requests and non-destructive rehearsal.
- Tests/evidence: `tests/test_p26_04_authorization_boundaries.py` (8 passed); full repo suite (1686 passed).
- Affected files: `tests/test_p26_04_authorization_boundaries.py`, `docs/P-26.04_AUTHORIZATION_BOUNDARIES_REPORT.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all autonomous DevOps fleets, GitHub integrations, and database migration agents).
- Status: `ACTIVE`

### LESSON-20260822-09 — Honest Non-Certification Disclosures and Claim Audits
- Date/time: 2026-08-22
- Active task: P-26.05
- Symptom: AI hackathon and enterprise projects frequently make exaggerated, unverified security assertions ("100% secure", "unhackable", "fully certified") that damage evaluator trust.
- Root cause: Lack of systematic static claim auditing across documentation and marketing copy.
- Correct approach:
  1. Build a static claim auditor (`scripts/audit_security_claims.py`) that scans all markdown files for prohibited absolute claims.
  2. Maintain explicit, prominent non-certification notices clarifying that ChangeMesh provides automated governance readiness but does not replace accredited third-party audits (SOC 2, HIPAA, PCI).
  3. Re-affirm deterministic code primacy over model outputs in all public documentation.
- Prevention rule: Every public artifact must disclose honest boundaries, residual risks, and non-certification notices.
- Tests/evidence: `scripts/audit_security_claims.py`, `tests/test_p26_05_security_limitations.py` (3 passed); full suite (1686 passed).
- Affected files: `README.md`, `scripts/audit_security_claims.py`, `tests/test_p26_05_security_limitations.py`, `docs/P-26.05_HONEST_SECURITY_LIMITATIONS_REPORT.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all competition documentation, enterprise marketing copy, and AI evaluation briefs).
- Status: `ACTIVE`

### LESSON-20260822-10 — Sub-10ms In-Process Saga Execution and Time Budgets
- Date/time: 2026-08-22
- Active task: P-27.01
- Symptom: Multi-agent orchestrations can become sluggish or unpredictable during evaluations if IO and coordination overheads are unbounded.
- Root cause: Inefficient event propagation, excessive serialization cycles, or unbounded network retries.
- Correct approach:
  1. Profile end-to-end multi-agent execution using in-process event buses and immutable Pydantic models.
  2. Implement bounded exponential backoff `(100ms, 200ms, 400ms, 800ms)` capped at max 4 attempts.
  3. Validate that mean demo latency remains well below recording budgets (< 10ms observed vs 2.0s ceiling).
- Prevention rule: Every multi-agent lifecycle stage must have a documented timeout ceiling and bounded retry policy.
- Tests/evidence: `scripts/measure_performance.py`, `tests/test_p27_01_performance_metrics.py` (3 passed); full suite (1709 passed).
- Affected files: `scripts/measure_performance.py`, `tests/test_p27_01_performance_metrics.py`, `docs/P-27.01_LATENCY_AND_PERFORMANCE_REPORT.md`, `AGENT_ENVIRONMENT_AND_API.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all low-latency agent architectures, saga orchestrators, and performance tuning).
- Status: `ACTIVE`

### LESSON-20260822-11 — Sub-Cent Unit Economics and Zero-Cost Serverless Idle Architecture
- Date/time: 2026-08-22
- Active task: P-27.02
- Symptom: AI agents can incur runaway model token expenses or accumulate heavy idle cloud hosting bills if services are provisioned with fixed instances.
- Root cause: Overly verbose system prompt loops, lack of token tracking, and non-serverless deployment targets.
- Correct approach:
  1. Leverage concise, structured prompts with strict Pydantic JSON schemas, restricting per-saga token usage to ~6,800 tokens (< $0.001 per run on Gemini 3.6 Flash).
  2. Deploy Cloud Run with `min-instances = 0` and serverless Firestore/Pub/Sub to ensure $0.00 / month idle expenditure.
  3. Validate all cloud operations fit comfortably within permanent Google Cloud free tier boundaries.
- Prevention rule: Every AI architecture must calculate per-transaction token economics and maintain scale-to-zero idle configurations.
- Tests/evidence: `scripts/estimate_cost.py`, `tests/test_p27_02_cost_estimation.py` (3 passed); full suite (1709 passed).
- Affected files: `scripts/estimate_cost.py`, `tests/test_p27_02_cost_estimation.py`, `docs/P-27.02_COST_AND_TOKEN_ESTIMATION_REPORT.md`, `README.md`, `AGENT_ENVIRONMENT_AND_API.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all serverless AI applications, cost modeling, and cloud optimization).
- Status: `ACTIVE`

### LESSON-20260822-12 — Programmatic Budget Caps and Serverless Lifecycle Governance
- Date/time: 2026-08-22
- Active task: P-27.03
- Symptom: Hackathon and prototype cloud deployments often suffer from unexpected billing spikes due to accidental instance provisioning or unmanaged log/data retention.
- Root cause: Missing declarative budget thresholds and absent data retention lifecycle policies.
- Correct approach:
  1. Define explicit multi-tiered budget alerts in `deploy/budget_and_retention_config.json` with a $25.00 hard monthly cap.
  2. Enforce Cloud Run `min_instances = 0` and request timeouts capped at 300s to guarantee zero idle billing.
  3. Bound Firestore and Cloud Logging data retention to 30 days.
  4. Implement automated teardown routines to cleanly decommission test infrastructure.
- Prevention rule: Every cloud architecture must possess declarative budget alert specifications and lifecycle policies.
- Tests/evidence: `deploy/budget_and_retention_config.json`, `tests/test_p27_03_budget_and_retention.py` (4 passed); full suite (1709 passed).
- Affected files: `deploy/budget_and_retention_config.json`, `tests/test_p27_03_budget_and_retention.py`, `docs/P-27.03_BUDGET_AND_RETENTION_CONFIG_REPORT.md`, `AGENT_ENVIRONMENT_AND_API.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all Google Cloud deployments, serverless governance, and billing safeguards).
- Status: `ACTIVE`

### LESSON-20260822-13 — Model Quota Degradation, Rate-Limiting, and OCC CAS Resilience
- Date/time: 2026-08-22
- Active task: P-27.04
- Symptom: Distributed agent architectures can cascade into retry storms or corrupt database state when model quotas or upstream rate limits (HTTP 429) are encountered.
- Root cause: Multiple uncontrolled retry authorities (SDK-level retries conflicting with orchestrator retries) and non-atomic state updates.
- Correct approach:
  1. Disable underlying SDK retries (`attempts = 1`) and make `BoundedGeminiClient` the single deterministic retry authority.
  2. Treat HTTP 429 and 503 as retryable with exponential backoff bounded at max 3 attempts.
  3. When quota is exhausted, fail closed with `ModelRetryExhaustedError` and maintain OCC CAS version integrity in the state repository without corrupting partial progress.
- Prevention rule: Never allow multiple retry loops to overlap; maintain optimistic concurrency CAS versions across all failure states.
- Tests/evidence: `tests/test_p27_04_quota_degradation.py` (4 passed); full suite (1709 passed).
- Affected files: `tests/test_p27_04_quota_degradation.py`, `docs/P-27.04_QUOTA_DEGRADATION_REPORT.md`, `AGENT_MEMORY_AND_LESSONS.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all LLM client wrappers, rate limiting, and fault-tolerant sagas).
- Status: `ACTIVE`

### LESSON-20260822-14 — Lean AI Architecture and Supply Chain Waste Elimination
- Date/time: 2026-08-22
- Active task: P-27.05
- Symptom: AI hackathon applications frequently suffer from bloat, broken Node.js build pipelines, unpinned dependencies, and unpredictable runtime resource consumption.
- Root cause: Over-engineering frontend stacks with heavy JavaScript toolchains (Webpack, React, Vite) and multi-model abstraction monoliths.
- Correct approach:
  1. Eliminate Node.js runtime and npm build pipelines entirely by serving clean, vanilla ES6/HTML5/CSS3 directly from Python/Cloud Run.
  2. Implement push-based event topologies with Pub/Sub instead of busy-wait polling loops.
  3. Standardize on a single canonical Google Gemini model (`gemini-3.6-flash`) via the official `google-genai` SDK.
  4. Enforce scale-to-zero serverless hosting (`min-instances = 0`) to achieve $0.00 / month idle expenditure.
- Prevention rule: Never introduce unneeded frontend build toolchains or multi-model sprawl when native browser standards and focused SDKs fulfill the product requirements.
- Tests/evidence: `tests/test_p27_05_lean_architecture.py` (3 passed); full suite (1726 passed).
- Affected files: `tests/test_p27_05_lean_architecture.py`, `docs/P-27.05_LEAN_ARCHITECTURE_AND_COST_COMPARISON.md`, `AGENT_ARCHITECTURE_AND_PATTERNS.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all production agent architectures, lean web apps, and AI hackathon submissions).
- Status: `ACTIVE`

### LESSON-20260822-15 — Declarative Cloud Topology and Least-Privilege IAM Scoping
- Date/time: 2026-08-22
- Active task: P-28.01
- Symptom: Multi-service cloud deployments frequently develop regional drift (e.g. databases in one region, compute in another) or accumulate overly permissive IAM roles (`roles/owner` or `roles/editor`).
- Root cause: Ad-hoc manual console provisioning without an immutable JSON infrastructure blueprint.
- Correct approach:
  1. Maintain a single declarative manifest (`deploy/gcp_infrastructure_manifest.json`) codifying all target resource IDs, regions (`europe-west3`), ports (8080), and memory/CPU limits.
  2. Scope IAM roles strictly to least privilege: `aiplatform.user`, `datastore.user`, `pubsub.publisher`, `pubsub.subscriber`, and `cloudtrace.agent`.
  3. Validate manifest syntax and role restrictions through automated pytest regression suites.
- Prevention rule: Every cloud deployment must possess a declarative infrastructure manifest with validated least-privilege IAM bindings.
- Tests/evidence: `deploy/gcp_infrastructure_manifest.json`, `tests/test_p28_01_infrastructure_config.py` (4 passed); full suite (1726 passed).
- Affected files: `deploy/gcp_infrastructure_manifest.json`, `tests/test_p28_01_infrastructure_config.py`, `docs/P-28.01_INFRASTRUCTURE_DEPLOYMENT_CONFIG_REPORT.md`, `AGENT_ARCHITECTURE_AND_PATTERNS.md`, `AGENT_ENVIRONMENT_AND_API.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all Google Cloud infrastructure management, Terraform blueprints, and enterprise IAM audits).
- Status: `ACTIVE`

### LESSON-20260822-16 — Deployed Revision Health and Public Cloud Run Verification
- Date/time: 2026-08-22
- Active task: P-28.02
- Symptom: Deployed cloud revisions may break or serve stale assets if endpoint routes, content types, and revision hashes are not tested systematically.
- Root cause: Testing only local mock functions rather than actual HTTP request/response lifecycles.
- Correct approach:
  1. Test the HTTP server handler using ephemeral port test servers (`HTTPServer(("127.0.0.1", 0), ChangeMeshServiceHandler)`).
  2. Verify `/health` probe returns 200 OK, canonical model ID (`gemini-3.6-flash`), and region (`europe-west3`).
  3. Validate Content-Type headers for HTML, CSS, JS, and JSON endpoints.
  4. Ensure live Cloud Run public endpoint matches the canonical deployment revision.
- Prevention rule: Every deployed cloud service must have automated HTTP endpoint contract and health probe tests.
- Tests/evidence: `tests/test_p28_02_deployed_health.py` (5 passed); full suite (1731 passed).
- Affected files: `tests/test_p28_02_deployed_health.py`, `docs/P-28.02_DEPLOYED_REVISION_HEALTH_REPORT.md`, `README.md`, `AGENT_ENVIRONMENT_AND_API.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all Cloud Run services, microservice health checking, and API routing).
- Status: `ACTIVE`

### LESSON-20260822-17 — Cryptographic Provenance Binding and Revision Traceability
- Date/time: 2026-08-22
- Active task: P-28.03
- Symptom: Evaluators and enterprise judges cannot easily verify whether a live demo or cloud endpoint corresponds to the exact Git commit in the repository.
- Root cause: Missing cross-referencing between source Git commit SHAs, container image digests, and cloud revision IDs.
- Correct approach:
  1. Generate an immutable JSON provenance binding artifact (`docs/P-28.03_REVISION_PROVENANCE_BINDING.json`).
  2. Bind the exact 40-character Git commit SHA, the Container Registry SHA-256 digest, the Cloud Run revision ID, and the canonical Gemini model ID (`gemini-3.6-flash`).
  3. Validate provenance integrity in automated pytest regression suites and cross-link from `docs/SUBMISSION_MANIFEST.md`.
- Prevention rule: Every public release must publish an explicit provenance binding linking source commit, container digest, and cloud revision.
- Tests/evidence: `docs/P-28.03_REVISION_PROVENANCE_BINDING.json`, `tests/test_p28_03_revision_provenance.py` (3 passed); full suite (1731 passed).
- Affected files: `docs/P-28.03_REVISION_PROVENANCE_BINDING.json`, `tests/test_p28_03_revision_provenance.py`, `docs/SUBMISSION_MANIFEST.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all software provenance, SLSA compliance, and verifiable builds).
- Status: `ACTIVE`

### LESSON-20260822-18 — Containerized E2E Service Execution and Portability
- Date/time: 2026-08-22
- Active task: P-28.04
- Symptom: Distributed services can fail when invoked over HTTP inside container environments due to undeclared local file assumptions or broken schema deserialization.
- Root cause: Testing functions directly in Python unit tests rather than dispatching HTTP requests against the container's service endpoints.
- Correct approach:
  1. Expose explicit `/run` and `/run-e2e` execution endpoints on the service HTTP server.
  2. Ensure the demo returns deterministic status, `fixture_id`, and `demo_digest`.
  3. Validate that all required dependencies are packaged cleanly without external disk leaks.
- Prevention rule: Container service endpoints must be verified via end-to-end HTTP request testing before declaring deployment readiness.
- Tests/evidence: `tests/test_p28_04_deployed_e2e.py` (2 passed); full suite (1733 passed).
- Affected files: `tests/test_p28_04_deployed_e2e.py`, `docs/P-28.04_DEPLOYED_E2E_CLOUD_REPORT.md`, `docs/JUDGING_MAP.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all microservice API testing, container readiness probes, and cloud demo verification).
- Status: `ACTIVE`

### LESSON-20260822-19 — Post-Judging Teardown Protocols and Evidence Preservation
- Date/time: 2026-08-22
- Active task: P-28.05
- Symptom: De-provisioning hackathon cloud infrastructure can accidentally wipe benchmark logs or create dangling resources incurring unwanted recurring costs.
- Root cause: Absence of clear boundaries between ephemeral compute/test states and immutable proof packs.
- Correct approach:
  1. Enforce Cloud Run `min-instances = 0` to ensure automatic scale-to-zero when traffic ceases.
  2. Commit immutable evidence packs (`docs/P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json`, `docs/P-28.03_REVISION_PROVENANCE_BINDING.json`) directly into version control.
  3. Define declarative teardown scripts in `deploy/budget_and_retention_config.json` that purge transient database collections without mutating canonical files.
- Prevention rule: Never couple evidence availability to persistent live compute; store proof as immutable repo artifacts while allowing compute to scale to zero.
- Tests/evidence: `tests/test_p28_05_teardown_verification.py` (3 passed); full suite (1736 passed).
- Affected files: `tests/test_p28_05_teardown_verification.py`, `docs/P-28.05_TEARDOWN_IDLE_VERIFICATION_REPORT.md`, `AGENT_ENVIRONMENT_AND_API.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all hackathon submissions, cloud cost containment, and serverless lifecycle management).
- Status: `ACTIVE`

### LESSON-20260822-20 — Sanitized Log/Trace Telemetry and Demo Script Alignment
- Date/time: 2026-08-22
- Active task: P-28.06
- Symptom: Demo video recordings, screenshots, and live console logs can inadvertently expose credentials, bearer tokens, or internal URLs.
- Root cause: Relying on unstructured `print()` or unredacted JSON logging during demo execution.
- Correct approach:
  1. Emit structured log entries and OpenTelemetry/Cloud Trace spans with strict pre-serialization secret scrubbing (`sanitize_secrets_in_text` and `scan_payload_for_secrets`).
  2. Structure the demo script (`docs/DEMO_SCRIPT.md`) with explicit timing timestamps and mode labels (`SIMULATION`, `LIVE_WRITE`, `RECORDED_CLOUD`).
  3. Validate absence of secrets in all demo walkthrough documentation and logs via automated pytest suites.
- Prevention rule: Every public log, trace, and walkthrough artifact must pass automated secret scanning before recording demo footage.
- Tests/evidence: `docs/P-28.06_SANITIZED_CONSOLE_EVIDENCE_REPORT.md`, `tests/test_p28_06_console_trace_sanitization.py` (3 passed); full suite (1739 passed).
- Affected files: `docs/P-28.06_SANITIZED_CONSOLE_EVIDENCE_REPORT.md`, `tests/test_p28_06_console_trace_sanitization.py`, `docs/DEMO_SCRIPT.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all video demo scripts, public log exports, and OpenTelemetry trace sanitization).
- Status: `ACTIVE`

### LESSON-20260822-21 — 4-Plane Enterprise Product Architecture and Zero-Custody Boundaries
- Date/time: 2026-08-22
- Active task: P-29.01
- Symptom: Enterprise customers resist multi-agent platforms that require uploading raw database schemas or private business records into a hosted multi-tenant cloud control plane.
- Root cause: Monolithic demo architectures coupling orchestration logic directly to local storage or cloud databases.
- Correct approach:
  1. Decouple the system into four explicit planes: Control Plane (managed orchestrator), Adapter Plane (edge runner sidecars), Policy Pack Plane (compiled deterministic rules), and Customer Data Plane (customer VPC).
  2. Enforce zero-custody boundaries: the control plane processes only cryptographic fingerprints, change descriptors, and verification digests.
  3. Ensure execution sidecars run within the customer's private cloud network.
- Prevention rule: Every commercial enterprise agent architecture must guarantee zero custody of raw customer data.
- Tests/evidence: `docs/P-29.01_PRODUCT_ARCHITECTURE_SEPARATION.md`, `tests/test_p29_01_product_architecture.py` (3 passed); full suite (1742 passed).
- Affected files: `docs/P-29.01_PRODUCT_ARCHITECTURE_SEPARATION.md`, `tests/test_p29_01_product_architecture.py`, `AGENT_ARCHITECTURE_AND_PATTERNS.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all enterprise SaaS, agentic control planes, and SOC2 compliant data architectures).
- Status: `ACTIVE`

### LESSON-20260822-22 — Ideal Customer Profile (ICP) Scoping and Honest Commercial Traction
- Date/time: 2026-08-22
- Active task: P-29.02
- Symptom: AI competition projects often present vague, generic buyer profiles ("for all developers") and invent fictitious enterprise customer traction or inflated ARR claims.
- Root cause: Conflating speculative marketing copy with grounded enterprise commercial analysis.
- Correct approach:
  1. Define a precise, budget-bearing buyer persona: VP of Platform Engineering / Head of Infrastructure in regulated industries (FinTech, B2B SaaS).
  2. Quantify real financial pain points: $100k+ downtime costs per breaking schema migration incident.
  3. Clearly separate MVP developer-preview maturity from future commercial production goals with explicit zero-invented-traction disclosures.
- Prevention rule: Every commercial productization brief must identify specific budget holders and provide strict non-traction disclosures.
- Tests/evidence: `docs/P-29.02_IDEAL_CUSTOMER_PROFILE_BRIEF.md`, `tests/test_p29_02_icp_brief.py` (3 passed); full suite (1745 passed).
- Affected files: `docs/P-29.02_IDEAL_CUSTOMER_PROFILE_BRIEF.md`, `tests/test_p29_02_icp_brief.py`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all commercial briefs, GTM plans, and investor/judge pitches).
- Status: `ACTIVE`

### LESSON-20260822-23 — 3-Tier Deployment Models and Zero-Ingress VPC Architecture
- Date/time: 2026-08-22
- Active task: P-29.03
- Symptom: Enterprise security teams reject SaaS platforms requiring inbound firewall openings or direct database connection strings into customer VPCs.
- Root cause: Assuming all customers can use public multi-tenant SaaS.
- Correct approach:
  1. Codify three explicit deployment tiers: Model A (Multi-tenant SaaS), Model B (Hybrid VPC Runner), and Model C (Air-Gapped Sovereign Cloud).
  2. Implement an outbound-only runner architecture for Model B: the runner in the customer VPC dials outbound to the control plane, eliminating inbound attack vectors.
  3. Ensure payload minimization carries only AST diffs and cryptographic evidence digests.
- Prevention rule: Hybrid deployment architectures must use outbound-only agent connections and zero inbound VPC firewall openings.
- Tests/evidence: `docs/P-29.03_DEPLOYMENT_PRIVACY_MODELS_ADR.md`, `tests/test_p29_03_privacy_models.py` (3 passed); full suite (1748 passed).
- Affected files: `docs/P-29.03_DEPLOYMENT_PRIVACY_MODELS_ADR.md`, `tests/test_p29_03_privacy_models.py`, `AGENT_ARCHITECTURE_AND_PATTERNS.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all enterprise hybrid architectures, customer runner daemons, and SOC2/HIPAA compliance architectures).
- Status: `ACTIVE`

### LESSON-20260822-24 — Monotonic Safety Locks in Agentic Plugin Architectures
- Date/time: 2026-08-22
- Active task: P-29.04
- Symptom: Third-party extensions, custom tools, or user-supplied policy plugins can introduce backdoors or weaken orchestrator safety and verification guarantees.
- Root cause: Untrusted plugins overriding core security handlers or bypassing human approval gates.
- Correct approach:
  1. Enforce a monotonic safety invariant: plugins may only introduce additional constraints, richer evidence artifacts, or specialized change type handlers; they can never weaken base invariants.
  2. Require custom tool adapters to declare capability passports verified by cryptographic digest.
  3. Ensure all custom change handlers implement deterministic reversibility assessment and compensation generators before execution.
- Prevention rule: Extensibility points must be monotonic and strictly additive to safety constraints.
- Tests/evidence: `docs/P-29.04_EXTENSIBILITY_CONTRACT.md`, `tests/test_p29_04_extensibility_contract.py` (3 passed); full suite (1751 passed).
- Affected files: `docs/P-29.04_EXTENSIBILITY_CONTRACT.md`, `tests/test_p29_04_extensibility_contract.py`, `AGENT_ARCHITECTURE_AND_PATTERNS.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all plugin systems, MCP servers, SDK extensions, and tool runtime sandboxing).
- Status: `ACTIVE`

### LESSON-20260822-25 — 90-Day Post-Competition Roadmap Boundaries
- Date/time: 2026-08-22
- Active task: P-29.05
- Symptom: Hackathon projects often blur current deliverables with future aspirational features, confusing judges and eroding evaluation credibility.
- Root cause: Failing to separate current frozen code from future commercial roadmap horizons.
- Correct approach:
  1. Clearly establish 30-day, 60-day, and 90-day post-competition milestones in a dedicated document (`docs/P-29.05_90_DAY_ROADMAP.md`).
  2. Ground future deliverables in concrete enterprise building blocks (VPC runner packaging, SOC 2 compliance, plugin marketplaces).
  3. Reiterate strict code freeze on current competition MVP.
- Prevention rule: Every commercial roadmap must cleanly separate current verified evidence from future post-freeze milestones.
- Tests/evidence: `docs/P-29.05_90_DAY_ROADMAP.md`, `tests/test_p29_05_roadmap_integrity.py` (3 passed); full suite (1754 passed).
- Affected files: `docs/P-29.05_90_DAY_ROADMAP.md`, `tests/test_p29_05_roadmap_integrity.py`, `README.md`, `docs/HANDOFF.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`.
- Reusable beyond this task: Yes (all hackathon post-freeze planning, commercial GTM roadmaps, and investor presentations).
- Status: `ACTIVE`

























