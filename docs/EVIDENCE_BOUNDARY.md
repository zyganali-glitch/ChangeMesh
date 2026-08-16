# ChangeMesh Evidence Boundary

## Execution/Evidence Mode

- `FIXTURE`: Static, predetermined, or synthetic test inputs/test doubles.
- `SIMULATION`: Dynamic controlled rehearsal without real target mutation.
- `RECORDED_CLOUD`: Read-only replay of evidence captured from an actual Google Cloud execution.
- `LIVE_WRITE`: A real credential-backed action causing a real externally observable mutation.

## Evidence State

- `PASS`: named check/action executed and succeeded
- `WARN`: evidence exists but needs attention
- `FAIL`: named check executed and failed
- `NOT_RUN`: not executed
- `SIMULATED`: executed in ShadowLab or fixture
- `BLOCKED`: policy prevented execution; action remains `NOT_RUN`
- `QUARANTINED`: excluded from decisions pending trust review

## Mode vs Evidence State

Execution/Evidence Mode and Evidence State are orthogonal concepts. They must never be collapsed into one enum. Mode answers *where* and *under what side-effect boundary* an operation occurred, whereas Evidence State answers *what happened* to the named check or action.
For example, `SIMULATED` is a state, not a mode. A simulated test run could be `SIMULATION + PASS` (the check passed in a simulated environment). `SIMULATED` as a state means the EvidenceRecord itself represents a simulated/substitute outcome rather than proof of real target action, and is not a synonym for `PASS`.

**Invariant:** State cannot erase mode provenance. A fixture success remains `FIXTURE PASS` and cannot be claimed as a live execution `PASS`.

**Mandatory Provenance:** Every evidence record must explicitly declare its `source` (a non-blank stable human/machine-readable reference) and its `collection_mode`.
- `SIMULATED` state is only valid with a non-live controlled provenance (`FIXTURE` or `SIMULATION`). `LIVE_WRITE + SIMULATED` or `RECORDED_CLOUD + SIMULATED` will fail validation.
- `RECORDED_CLOUD` mode evidence requires historical provenance: a `source_execution_identifier`, a `source_execution_timestamp`, and at least one immutable `ArtifactHash`. It does not imply current live execution.

## Authorities

Authority in ChangeMesh is strictly separated into four lanes:

1. **Execution facts**: Deterministic code.
2. **Semantic adequacy**: Gemini semantic authority artifact.
3. **Organizational constraints**: Organizational policy authority.
4. **Human decision**: Only for policy-defined human authority slots.

| Question | Authority |
|---|---|
| Did command run? | Recorded local/cloud execution evidence (`DETERMINISTIC_CODE`) |
| Did tool call occur? | Event ledger and correlated trace (`DETERMINISTIC_CODE`) |
| Did test pass? | Test runner output and artifact hash (`DETERMINISTIC_CODE`) |
| Is memory valid? | Memory Trust Layer deterministic policy (`DETERMINISTIC_CODE`) |
| Is agent revision qualified? | Capability Passport validator (`DETERMINISTIC_CODE`) |
| Is action autonomously allowed? | Organizational policy authority (`ORGANIZATIONAL_POLICY`) |
| Does evidence semantically cover goal? | Gemini semantic assessment, advisory (`GEMINI_SEMANTIC_JUDGMENT`) |
| May irreversible work proceed? | Compressed human authority (`HUMAN_AUTHORITY`) |

> [!IMPORTANT]
> Human approval does not convert deterministic `FAIL`/`NOT_RUN` into `PASS` and does not silently bypass hard organizational policy.

## Separation

Fixture data is not customer data. Synthetic graph is not live DataHub. Local simulation is not managed Google proof. Model explanation is not test evidence. Deployment screenshot without revision/logs is weak evidence. Public claims must link current sanitized artifacts.

*Note (ADR-0007): All managed service claims (Agent Runtime/Platform + Cloud Run for supporting services, Firestore as Operational State, Pub/Sub) must point to actual Google Cloud deployment evidence, not local simulators.*

## P-05.03 Domain Contracts vs Runtime

The `EvidenceRecord` domain contract and its supporting schemas (`EvidenceState`, `ExecutionEvidenceMode`, `Provenance`, `TraceReference`, `ArtifactHash`) are implemented as provider-neutral, strict Pydantic schemas.
These schemas guarantee deterministic fact sovereignty: neither a model's judgment nor human approval can overwrite a deterministic execution fact (e.g., turning a `FAIL` or `BLOCKED` into a `PASS`).
All evidence timestamps and artifact hashes conform strictly to `docs/CONTRACT_CONVENTIONS.md` (UTC-aware `UtcDateTime`, SHA-256 64-char hex digests).

The runtime Evidence Ledger service (`src/evidence/evidence_record.py`) and adapters (such as Firestore persistence or Pub/Sub timelines) are explicitly deferred and **not yet implemented**. P-05.03 only defines the immutable evidence contracts.

## P-08.02 Structured Output Boundary and Model/Fact Separation

Under P-08.02 (`src/core/gemini_structured_output.py`), structured model output is treated as untrusted data until strict, deterministic schema validation succeeds.

1. **Implemented Semantic Surfaces:**
   - **Goal Decomposition:** `GoalDecompositionResult` — structured breakdown of specialist tasks, target components, canonical action types, and advisory risk levels.
   - **Policy Explanation:** `PolicyExplanationResult` — structured explanatory narrative of already supplied organizational policy decisions (does NOT author policy or alter autonomy classification).
   - **Semantic Audit:** `SemanticAuditResult` — structured evidence citations, counter-evidence, missing-evidence, and claim assessments evaluating semantic coverage.

2. **Authority Sovereignty:**
   - Validated artifacts belong strictly to `GEMINI_SEMANTIC_JUDGMENT` (`authority_lane`).
   - Model judgments cannot manufacture, overwrite, or promote deterministic `EvidenceState` (`PASS`, `WARN`, `FAIL`, `NOT_RUN`, `SIMULATED`, `BLOCKED`, `QUARANTINED`), command results, exit codes, execution modes, organizational policy decisions, or human approval records.
   - Model disagreement with deterministic facts creates an advisory conflict or requires review; it never changes the underlying deterministic fact.

3. **Fail-Closed Guarantees (OUT-01 through OUT-10):**
   - Missing required fields (including `schema_version` and collection fields) fail closed with zero default injection.
   - Unsupported or mismatched `schema_version` fails closed.
   - Extra fields fail closed (`extra="forbid"`).
   - Wrong types fail closed without silent coercion (`StrictStr`, `StrictInt`).
   - Path traversal tokens (`..`, `../`, `..\\`, `%2e%2e`) and unapproved external URLs fail closed.
   - Decisive verdicts (`SUPPORTS`, `CONTRADICTS`, `INSUFFICIENT`) enforce structural separation (OUT-10) requiring explicit evidence citations or counter/missing-evidence points distinct from generated narrative text.

## P-08.03 Input Minimization and Privacy Boundary

The canonical deterministic owner is `src/agents/policy_guardian.py`. Its single
privacy pattern table blocks private keys, API-key-looking values, GitHub/cloud
access tokens, JWTs, bearer values, password-bearing connection strings, session
cookies, service-account material, non-reserved email addresses, and phone numbers.
UUIDs, public IPs, and production-data markers are `REVIEW` findings, but review
findings are also rejected before Gemini; they never grant `HUMAN_AUTHORITY`.

The three implemented prompt surfaces require exact allowlists and matching
`collection_mode`/`declared_mode` values from `FIXTURE`, `SIMULATION`,
`RECORDED_CLOUD`, or `LIVE_WRITE`. Unknown fields, nested unknown fields, and
mode mismatches fail before prompt materialization. Reserved synthetic email
domains (`example.com`, `example.net`, `example.org`, `example.test`) are allowed.
`BoundedGeminiClient` repeats the deterministic scan for both prompt text and
`system_instruction` before constructing or invoking the SDK request. Findings
retain only category, severity, and offset; matched content is never recorded.

This is implemented deterministic minimization and boundary enforcement, not
generic enterprise DLP, universal PII discovery, proxy interception, or Model Armor.

## P-08.04 Blind Semantic Audit Boundary

`src/agents/evidence_auditor.py` defines the completed P-08.04 implementation:
deterministic claim state is held in an application-only locked
package, while Gemini receives only neutral claims and bounded evidence summaries.
Expected-answer fields (`expected_result`, `should_pass`, and equivalent
deterministic/reconciliation fields) are rejected before prompt construction.
Model assessments remain `GEMINI_SEMANTIC_JUDGMENT`; reconciliation preserves
`EvidenceState` sovereignty. Any semantic disagreement with locked evidence sets
`relation="DISAGREEMENT_WITH_LOCKED_STATE"`, `conflict_detected=True`, and
`review_state="SEMANTIC_DISAGREEMENT"`. It strictly sets `human_review_required=False`
(Gemini uncertainty or model disagreement cannot manufacture `HUMAN_AUTHORITY`).

## P-08.05 Measurement and Project Budget Boundary

`src/core/gemini_client.py` measures bounded latency, token counts, attempts,
retry count, and formula-calculated cost.
1. **Rate Provenance & Calibration:** `GeminiCostRateCard` carries structured `RateProvenanceKind` (`TEST_FORMULA`, `CUSTOM_UNVERIFIED`, `PROVIDER_CALIBRATED`). Provider pricing calibration is explicitly `NOT_RUN` (zero price guessing). Missing rate cards produce `cost_status="NOT_RUN"`.
2. **Project / Demo Budget Policy:** Deterministic `ModelCallBudgetPolicy` (`DEMO_MAX_LATENCY_MS = 30000.0`, `DEMO_MAX_COST_USD = 0.05`, `DEMO_MAX_TOTAL_TOKENS = 12288`) and `evaluate_model_call_budget()` enforce local demonstration limits without claiming provider SLAs.
3. **Canonical Metrics Evidence Artifact:** `build_model_metrics_artifact()` and `export_metrics_artifact_json()` export deterministic, non-secret execution metrics artifacts with strict secrecy guarantees (zero prompt, response, or credential text).
