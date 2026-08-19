# ChangeMesh Component Provenance

Implementation status: `IN_PROGRESS` (component-level status governed by `docs/DONOR_REUSE_MANIFEST.md`; `ZK-VALID-001` in P-08.02, `ZK-PRIV-001` in P-08.03, `CCT-SEM-001` in P-08.04, `CCT-FLIGHT-001` in P-09.05)
Architecture donor preflight gate (P-04.00): `PASS`
Gemini boundary donor preflight gate (P-08.00): `PASS`
Saga persistence donor preflight gate (P-10.00): `PASS`

ChangeMesh is a new product/repository. Design benefits from ideas in owner's earlier repositories, but final competition implementation must document exactly what is reused, rewritten, or new.

| Donor | Reusable idea | ChangeMesh transformation |
|---|---|---|
| Universal Agent OS | live plans, memory pillars, evidence-first closure | development governance only; remove product interview burden |
| Universal Agent OS UiPath | human authority gate and durable process state | exception-only compressed authority decisions |
| Codex Control Tower | locked facts, flight recorder, blind semantic challenge | provider-neutral evidence ledger with Gemini auditor |
| ZeroKit AI Control Plane | privacy preflight and strict contracts | Policy Guardian and typed artifact validation |
| ContextSeal | blast radius, safe migration, change passport | cross-system enterprise Change Evidence Passport |
| Qwen MemoryAgent | importance, freshness, decay, shared memory | Memory Trust Layer with provenance/quarantine |
| GitLab Edition | conflict and repository blast-radius analysis | Impact Scout with GitHub-first demo adapter |

## Implemented and Verified Donor Components

### ZK-VALID-001 — Config Validator / Strict Output Validation
- **Status:** `VERIFIED`
- **Donor ID:** `D-ZEROKIT` (`zyganali-glitch/zerokit-ai-control-plane`)
- **Immutable Donor SHA:** `d663db8c706cb914e1af5caf651df08edb5c50c0`
- **Source Paths:** `frontend/js/config-validator.js`, `tests/unit/config-validator.test.mjs`
- **License State:** `VERIFIED_COMPATIBLE` (owner-authored)
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target:** `src/core/gemini_structured_output.py`
- **Competition Introduction Commit:** `27fe08c1271e4aad1527a47d35f9fefc8b361819`
- **Test Evidence:** `tests/test_p08_02_structured_output.py` (40 dedicated unit/boundary/adversarial tests PASS)
- **Materially New Contribution:** Reimplemented in Python using strict Pydantic v2 domain schemas (`extra="forbid"`, `frozen=True`, `StrictStr`, `StrictInt`), 3 semantic surfaces (Goal Decomposition, Policy Explanation, Independent Semantic Audit), exact canonical `schema_version` validation, deterministic path traversal and unsafe endpoint validators, authority lane boundary (`GEMINI_SEMANTIC_JUDGMENT`), and zero default injection. Zero ZeroKit product semantics or frontend global variables carry over.

### ZK-PRIV-001 — Input Privacy and Prompt Minimization Boundary
- **Status:** `VERIFIED`
- **Donor ID:** `D-ZEROKIT` (`zyganali-glitch/zerokit-ai-control-plane`)
- **Immutable Donor SHA:** `d663db8c706cb914e1af5caf651df08edb5c50c0`
- **Source Paths:** `ai-buildweek/lib/privacy-guard.mjs`, `tests/unit/privacy-guard.test.mjs`
- **License State:** `VERIFIED_COMPATIBLE` (owner-authored)
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target:** `src/agents/policy_guardian.py`
- **Competition Introduction Commit:** `4501c01ad4212a8ddd05024f99b5baab34b585de`
- **Test Evidence:** `tests/test_p08_03_input_privacy.py` (PRIV-01 through PRIV-08, review-deny policy, system-instruction bypass, and zero fake-SDK invocation)
- **Materially New Contribution:** Python-native Policy Guardian ownership, one category-only detector table with no matched-content retention, strict allowlists for all three P-08.02 prompt surfaces, explicit execution-mode provenance matching, and non-bypassable integration from `BoundedGeminiClient` before SDK request construction. Secrets and real PII fail closed; review findings are also denied rather than escalated. No ZeroKit product semantics, donor fixture identities, or provider-specific runtime assumptions carry over.

### CCT-SEM-001 — Blind Semantic Audit and Fact Reconciliation Boundary
- **Status:** `VERIFIED`
- **Donor ID:** `D-CCT` (`zyganali-glitch/codex-control-tower`)
- **Immutable Donor SHA:** `65ee1b72faf9a7202d9166eed43fb671804815a8`
- **Source Paths:** `cli/commands/codex-review.js`, `tests/test_codex_review.js`
- **License State:** `VERIFIED_COMPATIBLE` (owner-authored)
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target:** `src/agents/evidence_auditor.py`
- **Competition Introduction Commit:** `7cce78daca6ab37c027fea9d4637f3ecca4cfc28`
- **Test Evidence:** `tests/test_p08_04_blind_audit.py` (18 tests PASS)
- **Materially New Contribution:** Python-native ADK Evidence Auditor boundary with separate locked deterministic claims and model-visible neutral context, expected-answer field rejection, bounded evidence/prompt sizes, Gemini structured output parsing, claim/citation scope enforcement, and deterministic reconciliation preserving `EvidenceState`. No Codex/OpenAI runtime, GPT model, donor event stream, or donor project identity carries over.

### CCT-FLIGHT-001 — Causal Event Timeline and Execution Integrity Boundary
- **Status:** `VERIFIED`
- **Donor ID:** `D-CCT` (`zyganali-glitch/codex-control-tower`)
- **Immutable Donor SHA:** `65ee1b72faf9a7202d9166eed43fb671804815a8`
- **Source Paths:** `cli/commands/flight-recorder.js`, `tests/test_codex_review.js`
- **License State:** `VERIFIED_COMPATIBLE` (owner-authored)
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target:** `src/evidence/pubsub_timeline.py`
- **Competition Introduction Commit:** `4b66d381e7d8aaae1616cb62d34452fb11d15b32`
- **Test Evidence:** `tests/test_p09_05_pubsub_timeline.py` (8 dedicated tests PASS; 54 P-09 dedicated tests PASS)
- **Materially New Contribution:** Python-native causal event timeline implementing Kahn's topological sort algorithm over `causation_id` links, proving causal parent events precede child events regardless of network arrival sequence or wall-clock timestamp skew. Causally unlinked concurrent events are deterministically tie-broken by `(timestamp, event_id)`. Ingest-level payload secret sanitization and fail-closed validation, canonical JSON round-trip serialization with restart continuity, and deterministic SHA-256 timeline digest computation (`compute_timeline_digest()`). Zero Codex event models, frontend styling, or Google Cloud SDK types in core evidence timeline.

### UIPATH-STATE-001 — Lifecycle Saga State Machine & Progression
- **Status:** `IMPLEMENTED_PENDING_PARITY`
- **Donor ID:** `D-UIPATH` (`zyganali-glitch/universal-agent-os-uipath`)
- **Immutable Donor SHA:** `dc2267939c2aef0aba2737da65f53352c5cf8fb2`
- **Source Paths:** `backend/sync_markdown_to_uipath.py`, `tests/test_phase0_interview.py`
- **License State:** `VERIFIED_COMPATIBLE` (owner-authored)
- **Reuse Method:** `IDEA_ONLY`
- **ChangeMesh Target:** `src/orchestrator/state_repository.py`, `src/orchestrator/orchestrator_saga.py`, `src/orchestrator/saga_checkpoint.py`
- **Competition Introduction Commit:** `9c95018d5e0de0924aac7f2a797ee8ef8e7eb54d` (P-10 state repo) / `4dd868657888ea7b11986ef5779a37635d2019fa` (P-20.01 saga orchestrator)
- **Test Evidence:** `tests/test_p10_02_state_repository.py` (13 tests PASS), `tests/test_p20_orchestrator_saga.py` (42 tests PASS)
- **Materially New Contribution:** Replaces simple file-based interview status syncing with a full Python 3.13 Google ADK + Cloud Pub/Sub + Firestore multi-tenant saga engine. Features 8 canonical lifecycle stages, strict enum type enforcement, optimistic concurrency versioning, persistence-first event emission ordering, automatic intake secret scanning, intent binding to synthetic fixtures (preventing fact laundering), exact bounded `ApprovalCompressionCard` projection, and clean stops at human authority boundaries. Zero UiPath runtime code, Action Center, Data Service, or Phase-0 interview models carry over.

## Mandatory final disclosure

Record original path, license, source commit, copied/adapted/clean-room status, competition-period introduction commit, tests proving new behavior, and why ChangeMesh contribution is materially new. 

Per the official Hackathon rules, any reused components must:
1. Comply with applicable open-source licenses.
2. Be fully disclosed if pre-existing.
3. Be enhanced/built upon to create materially new software during the Submission Period.

## Binding detailed ledger

The canonical component-level ledger is [`DONOR_REUSE_MANIFEST.md`](DONOR_REUSE_MANIFEST.md). The high-level table above is a summary only and never authorizes implementation.

A component is reusable only when the detailed ledger records:

- immutable donor commit;
- exact source paths;
- verified license/notice state;
- observable source behavior;
- explicit reuse method;
- exact ChangeMesh target path or contract;
- required transformations and forbidden carry-over;
- positive, failure, boundary, security, and forbidden-carry-over tests;
- competition-period introduction commit;
- reviewer and evidence;
- final `VERIFIED` status.

P-02D, each relevant P-xx.00 preflight, P-DΩ, and P-Ω.12 are mandatory. Donor repositories remain read-only.
