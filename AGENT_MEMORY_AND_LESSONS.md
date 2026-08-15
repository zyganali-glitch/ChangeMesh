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
### LESSON-20260815-02 — Developer verification commands must be non-mutating check-only gates, not auto-mutations
- Date/time: 2026-08-15
- Active task: P-06.04
- Symptom: Running `scripts/cmd.py format` mutated 30+ files across frozen domain contracts, creating massive untracked churn. Meanwhile, authorized integration called `pytest tests/test_gcp_access.py`, which caused pytest collection to fail on missing `project` fixtures because `test_gcp_access.py` is a standalone script.
- Root cause: Confusing formatting check commands (`ruff format --check`) with auto-fix formatters (`ruff format`), and confusing pytest collection with standalone script execution.
- Incorrect approach: Allowing developer verification commands to mutate source code, or editing frozen legacy test scripts merely to satisfy pytest collection.
- Correct approach: Use `ruff format --check .` for verification commands. When standalone scripts need execution upon explicit authorization, dispatch them directly with `python <script>` rather than invoking pytest collection.
- Prevention rule: Verification commands must never mutate files. Distinguish command interface verification from underlying check results: a verification command works correctly when it faithfully reports repository debt without rewriting history or modifying frozen domain contracts.
- Status: `ACTIVE`



