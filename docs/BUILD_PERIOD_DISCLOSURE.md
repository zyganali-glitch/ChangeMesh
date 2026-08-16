# ChangeMesh Build-Period Disclosure

Status: `IN_PROGRESS`

This document distinguishes pre-existing ideas/components, competition-period ChangeMesh work, third-party libraries, Google managed services, synthetic fixtures, and recorded real executions. It maintains complete, truthful alignment with Git history, immutable donor commits, open-source licenses, and component provenance records.

## Devpost Hackathon Rules Compliance
Per the official rules:
- **New Projects Only:** Projects must be newly created during the Submission Period (Aug 3, 2026 - Aug 31, 2026 PT).
- **Pre-existing Code:** Any pre-existing code, frameworks, or open-source libraries incorporated into the project must be fully disclosed.
- **Intellectual Property:** Submission must be the original work of the entrant, and comply with all applicable open-source licenses.

All components derived from earlier repositories are declared in [`docs/DONOR_REUSE_MANIFEST.md`](DONOR_REUSE_MANIFEST.md) and governed by [`docs/COMPONENT_PROVENANCE.md`](COMPONENT_PROVENANCE.md).

---

## Disclosed Pre-Existing Donor Components & Build-Period Reimplementation Ledger

### ZK-PRIV-001 — Input Privacy and Prompt Minimization Boundary
- **Donor Repository:** `zyganali-glitch/zerokit-ai-control-plane` (Donor ID: `D-ZEROKIT`)
- **Immutable Donor Commit:** `d663db8c706cb914e1af5caf651df08edb5c50c0` (authored prior to competition build period)
- **Source Paths:** `ai-buildweek/lib/privacy-guard.mjs`, `tests/unit/privacy-guard.test.mjs`
- **License / Ownership:** MIT License / Owner-authored
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target Path:** `src/agents/policy_guardian.py`
- **Competition Introduction Commit:** `4501c01ad4212a8ddd05024f99b5baab34b585de`
- **Test Evidence:** `tests/test_p08_03_input_privacy.py` (PRIV-01 through PRIV-08 plus zero SDK invocation and system-instruction boundary tests)
- **Materially New Competition Work:**
  - Python-native canonical Policy Guardian implementation with one category-only detector table and no matched secret excerpts in findings, telemetry, or exceptions.
  - Exact field-level allowlists for Goal Decomposition, Policy Explanation, and Semantic Audit, including nested claim/evidence restrictions and explicit mode/provenance matching.
  - Non-bypassable integration from `BoundedGeminiClient` for prompt and system-instruction validation before the sole Gemini SDK call.
  - Deterministic review-deny behavior that cannot manufacture `HUMAN_AUTHORITY`; Model Armor and generic DLP remain unclaimed.

The donor's synthetic email allowlisting and blocker/review observable behavior
informed this clean-room implementation. ZeroKit product/admin semantics,
provider assumptions, and donor fixture identities were not carried over.

### CCT-SEM-001 — Blind Semantic Audit and Fact Reconciliation Boundary
- **Donor Repository:** `zyganali-glitch/codex-control-tower` (Donor ID: `D-CCT`)
- **Immutable Donor Commit:** `65ee1b72faf9a7202d9166eed43fb671804815a8` (authored prior to competition build period)
- **Source Paths:** `cli/commands/codex-review.js`, `tests/test_codex_review.js`
- **License / Ownership:** Owner-authored / `VERIFIED_COMPATIBLE`
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target Path:** `src/agents/evidence_auditor.py`
- **Competition Introduction Commit:** `PENDING` until the immutable implementation commit is created
- **Test Evidence:** `tests/test_p08_04_blind_audit.py` (18 tests PASS; final provenance closure pending)
- **Materially New Competition Work:**
  - Neutral model-visible claims and bounded evidence are separated from application-only deterministic facts.
  - Expected-answer fields and hints are rejected before prompt construction.
  - Gemini structured audit output is reconciled without rewriting deterministic states or manufacturing authority.
  - Codex/OpenAI/GPT runtime, ChatGPT authentication, donor event types, and donor fixture identities are excluded.

### 1. ZK-VALID-001 — Structured Output & Schema Validation Boundary
- **Donor Repository:** `zyganali-glitch/zerokit-ai-control-plane` (Donor ID: `D-ZEROKIT`)
- **Immutable Donor Commit:** `d663db8c706cb914e1af5caf651df08edb5c50c0` (authored prior to competition build period)
- **Source Paths:** `frontend/js/config-validator.js`, `tests/unit/config-validator.test.mjs`
- **License / Ownership:** MIT License / Owner-authored
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target Path:** `src/core/gemini_structured_output.py`
- **Competition Introduction Commit:** `27fe08c1271e4aad1527a47d35f9fefc8b361819` (authored during competition build period)
- **Test Evidence:** `tests/test_p08_02_structured_output.py` (40 unit, boundary, adversarial, and model integration tests passing)
- **Materially New Competition Work:**
  - Complete clean-room rewrite in Python using strict Pydantic v2 domain schemas (`extra="forbid"`, `frozen=True`, `StrictStr`, `StrictInt`).
  - Zero default injection across all schema fields; explicit canonical `schema_version` validation.
  - Three dedicated semantic reasoning surfaces: Goal Decomposition (`GoalDecompositionResult`), Policy Explanation (`PolicyExplanationResult`), and Semantic Audit (`SemanticAuditResult`).
  - Strict authority lane enforcement (`GEMINI_SEMANTIC_JUDGMENT`), ensuring model judgments cannot manufacture deterministic execution facts, `EvidenceState`, or organizational policy decisions.
  - Deterministic path traversal (`validate_safe_relative_path`), unsafe endpoint (`validate_safe_endpoint`), and action allowlist (`validate_action_type`) security validators.
  - Zero carry-over of ZeroKit configuration schemas (`panel_registry`, `rbac_registry`, `field_registry`), function names, or frontend global variables.
  - Truthful disclosure: The conceptual idea of multi-section strict dictionary validation originated in `D-ZEROKIT` before the competition; the entire Python implementation, domain models, and test suite were written from scratch during the competition period.
