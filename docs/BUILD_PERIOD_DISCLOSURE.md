# ChangeMesh Build-Period Disclosure & Provenance Record

**Status:** `VERIFIED / FROZEN`  
**Date:** 2026-08-22  
**Competition Category:** Fortified Enterprise Fleet  

This document distinguishes pre-existing ideas/components, competition-period ChangeMesh work, third-party open source libraries, Google Cloud managed services, synthetic test fixtures, and recorded cloud executions. It maintains complete, truthful alignment with Git history, immutable donor commits, open-source licenses, and component provenance records.

---

## 1. Devpost Hackathon Rules Compliance

Per the official competition rules:
- **New Projects Only:** ChangeMesh is newly created during the Submission Period (Aug 3, 2026 – Aug 31, 2026 PT).
- **Pre-existing Code Disclosures:** All conceptual ideas and architectural patterns adapted from earlier personal exploratory projects are fully disclosed with exact immutable commits.
- **Intellectual Property & Licensing:** ChangeMesh is 100% owner-authored and adheres to permissive open-source licenses (MIT License).

All components derived from earlier repositories are declared in [`docs/DONOR_REUSE_MANIFEST.md`](DONOR_REUSE_MANIFEST.md) and governed by [`docs/COMPONENT_PROVENANCE.md`](COMPONENT_PROVENANCE.md).

---

## 2. Disclosed Pre-Existing Donor Components & Build-Period Reimplementation Ledger

### A. ZK-PRIV-001 — Input Privacy and Prompt Minimization Boundary
- **Donor Repository:** `zyganali-glitch/zerokit-ai-control-plane` (Donor ID: `D-ZEROKIT`)
- **Immutable Donor Commit:** `d663db8c706cb914e1af5caf651df08edb5c50c0` (authored prior to competition build period)
- **Source Paths:** `ai-buildweek/lib/privacy-guard.mjs`, `tests/unit/privacy-guard.test.mjs`
- **License / Ownership:** MIT License / Owner-authored
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target Path:** `src/agents/policy_guardian.py`
- **Competition Introduction Commit:** `4501c01ad4212a8ddd05024f99b5baab34b585de`
- **Test Evidence:** `tests/test_p08_03_input_privacy.py` (PRIV-01 through PRIV-08 passing)
- **Materially New Competition Work:**
  - Python-native canonical Policy Guardian implementation with one category-only detector table and zero raw secret logging.
  - Strict field allowlists for Goal Decomposition, Policy Explanation, and Semantic Audit.
  - Non-bypassable integration into `BoundedGeminiClient` before Vertex AI SDK calls.

### B. CCT-SEM-001 — Blind Semantic Audit and Fact Reconciliation Boundary
- **Donor Repository:** `zyganali-glitch/codex-control-tower` (Donor ID: `D-CCT`)
- **Immutable Donor Commit:** `65ee1b72faf9a7202d9166eed43fb671804815a8` (authored prior to competition build period)
- **Source Paths:** `cli/commands/codex-review.js`, `tests/test_codex_review.js`
- **License / Ownership:** Owner-authored / `VERIFIED_COMPATIBLE`
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target Path:** `src/agents/evidence_auditor.py`
- **Competition Introduction Commit:** `7cce78daca6ab37c027fea9d4637f3ecca4cfc28`
- **Test Evidence:** `tests/test_p08_04_blind_audit.py` (18 tests PASS)
- **Materially New Competition Work:**
  - Neutral model-visible claims separated from deterministic application facts.
  - Gemini structured audit outputs reconciled without rewriting deterministic execution states.

### C. ZK-VALID-001 — Structured Output & Schema Validation Boundary
- **Donor Repository:** `zyganali-glitch/zerokit-ai-control-plane` (Donor ID: `D-ZEROKIT`)
- **Immutable Donor Commit:** `d663db8c706cb914e1af5caf651df08edb5c50c0` (authored prior to competition build period)
- **Source Paths:** `frontend/js/config-validator.js`, `tests/unit/config-validator.test.mjs`
- **License / Ownership:** MIT License / Owner-authored
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target Path:** `src/core/gemini_structured_output.py`
- **Competition Introduction Commit:** `27fe08c1271e4aad1527a47d35f9fefc8b361819`
- **Test Evidence:** `tests/test_p08_02_structured_output.py` (40 tests PASS)
- **Materially New Competition Work:**
  - Complete Python rewrite using strict Pydantic v2 domain schemas (`extra="forbid"`, `frozen=True`).
  - Authority lane enforcement (`GEMINI_SEMANTIC_JUDGMENT`), ensuring model judgments cannot manufacture deterministic execution facts.

### D. CCT-FLIGHT-001 — Causal Event Timeline and Execution Integrity Boundary
- **Donor Repository:** `zyganali-glitch/codex-control-tower` (Donor ID: `D-CCT`)
- **Immutable Donor Commit:** `65ee1b72faf9a7202d9166eed43fb671804815a8` (authored prior to competition build period)
- **Source Paths:** `cli/commands/flight-recorder.js`, `tests/test_codex_review.js`
- **License / Ownership:** Owner-authored / `VERIFIED_COMPATIBLE`
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target Path:** `src/evidence/pubsub_timeline.py`
- **Competition Introduction Commit:** `4b66d381e7d8aaae1616cb62d34452fb11d15b32`
- **Test Evidence:** `tests/test_p09_05_pubsub_timeline.py` (8 tests PASS)
- **Materially New Competition Work:**
  - Causal DAG event sequencing using Kahn's algorithm over `causation_id` links, proving causal ordering despite network skew.
  - Ingest-level payload secret scanning and deterministic SHA-256 timeline digest hashing.

---

## 3. Third-Party Open Source Libraries & Licensing

The table below discloses all canonical direct runtime and development/test dependencies declared in `pyproject.toml` and locked in `uv.lock`:

| Package | Category | Version Specifier | Resolved Lock Version | License | Role in ChangeMesh |
|---|---|---|---|---|---|
| `google-adk` | Direct Runtime | `>=2.6.0` | `2.6.0` | Apache-2.0 | Google Agent Development Kit framework topology |
| `google-genai` | Direct Runtime | `>=0.1.0` | `2.18.1` | Apache-2.0 | Official Google GenAI SDK for Gemini 3.6 Flash |
| `pydantic` | Direct Runtime | `>=2.0.0` | `2.12.5` | MIT License | Strict domain schema validation and immutable state |
| `google-cloud-firestore` | Direct Runtime | `>=2.15.0` | `2.23.0` | Apache-2.0 | Cloud Firestore client for OCC CAS persistence |
| `google-cloud-pubsub` | Direct Runtime | `>=2.20.0` | `2.34.0` | Apache-2.0 | Cloud Pub/Sub client for distributed event backbone |
| `pytest` | Direct Dev/Test | `>=8.0.0` | `9.1.1` | MIT License | Canonical test runner executing the complete test suite |
| `pyyaml` | Direct Dev/Test | `>=6.0.0` | `6.0.3` | MIT License | YAML parsing for donor manifest linting |
| `google-auth` | Direct Dev/Test | `>=2.0.0` | `2.49.0` | Apache-2.0 | Google Application Default Credentials library |
| `google-cloud-run` | Direct Dev/Test | `>=0.10.0` | `0.11.4` | Apache-2.0 | Google Cloud Run management client |
| `ruff` | Direct Dev/Test | `>=0.5.0` | `0.15.2` | MIT License | Python code formatting and linting tool |
| `mypy` | Direct Dev/Test | `>=1.10.0` | `1.19.1` | MIT License | Static type checker for Python domain contracts |
| `playwright` | Direct Dev/Test | `>=1.40.0` | `1.58.0` | Apache-2.0 | Headless Chromium browser E2E & accessibility testing |

---

## 4. Google Cloud Managed Services Disclosures

- **Canonical Model:** `gemini-3.6-flash` (Vertex AI API)
- **Compute:** Google Cloud Run (`europe-west3`) running containerized Python 3.13 (`min_instances=0`)
- **Database:** Google Cloud Firestore (Native Mode, OCC CAS transactions)
- **Messaging:** Google Cloud Pub/Sub (Topic & Dead-Letter Queue)
