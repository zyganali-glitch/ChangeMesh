# ChangeMesh Execution and Evidence Mode Contract

> **Status:** `P-04.04 COMPLETED; P-08.03 INPUT PROVENANCE CHECK IMPLEMENTED`
> **Date:** 2026-08-09
> **Implementation state:** The provider-neutral mode/evidence schemas and this mode contract are implemented. P-08.03 additionally enforces matching `collection_mode` and `declared_mode` values before the Gemini prompt boundary. Full external adapter mode execution, receipts, and cloud integrations remain owned by later phases; this document is not proof of live execution.

## 1. Purpose and Scope

ChangeMesh provides deterministic evidence of rehearsal and execution for high-risk enterprise changes. To guarantee honesty and reproducibility, this contract defines the boundaries between fixtures, simulated rehearsals, recorded historical evidence, and actual live writes. 

These are **execution/evidence modes**, not environment names (like dev/staging/prod). They define *where*, with what *provenance*, and with what *side effects* an operation occurred.

## 2. Mode vs. Evidence State

Mode and result state are distinct and orthogonal.

*   **Mode (Execution/Evidence Mode):** Explains provenance and boundaries (e.g., `FIXTURE`, `SIMULATION`, `RECORDED_CLOUD`, `LIVE_WRITE`).
*   **Result State (Evidence State):** Explains the outcome of the operation (e.g., `PASS`, `FAIL`, `NOT_RUN`, `SIMULATED`, `BLOCKED`, `QUARANTINED`).

**Invariant:** A result state cannot erase mode provenance. A `FIXTURE` that returns a successful result is a `FIXTURE PASS`. It is not, and can never be claimed as, a live execution `PASS`.

## 3. The Four Canonical Modes

ChangeMesh recognizes exactly four canonical modes. 

### 3.1 FIXTURE
*   **Definition:** Static, predetermined, or synthetic test inputs, fixtures, test doubles, or known controlled responses.
*   **Allowed side effects:** None. No real target mutation.
*   **Credential behavior:** Normally no real external credential.
*   **Evidence requirements:** Fixture identity/provenance must be visible.
*   **Live-proof capability:** Cannot prove managed service use or real target execution.

### 3.2 SIMULATION
*   **Definition:** Dynamic controlled rehearsal of behavior without real target mutation (e.g., ShadowLab).
*   **Allowed side effects:** None on real external targets. (May mutate synthetic internal rehearsal state).
*   **Credential behavior:** Normally no live-write credentials required or exposed.
*   **Evidence requirements:** Result provenance must remain visibly `SIMULATED`.
*   **Live-proof capability:** Cannot prove real external action or live execution.

### 3.3 RECORDED_CLOUD
*   **Definition:** Read-only presentation or replay of evidence previously captured from an actual Google Cloud execution.
*   **Allowed side effects:** None during replay. (Source execution had real side effects, but replay does not).
*   **Credential behavior:** Replay requires no reusable live-write credentials.
*   **Evidence requirements:** Must carry/link source execution/run identifier, timestamp, and immutable artifact/hash establishing valid provenance.
*   **Live-proof capability:** Cannot prove the service is executing *now*. Proves historical cloud execution if provenance is valid.

### 3.4 LIVE_WRITE
*   **Definition:** A real credential-backed action that causes a real externally observable mutation (e.g., creating a real GitHub Draft PR in a synthetic demo repo).
*   **Allowed side effects:** Real bounded external mutation on explicitly allowed targets.
*   **Credential behavior:** Adapter uses required external credentials securely.
*   **Evidence requirements:** Requires deterministic execution receipt/result confirming actual target response (e.g., GitHub PR identifier, artifact hash).
*   **Live-proof capability:** Yes, within its bounded scope.

## 4. Mode Contract Matrix

| Mode | Real External Call? | Real Mutation? | Synthetic/Controlled? | Credential Use | Required Evidence | Visible Label | Can Prove Live Execution? |
|---|:---:|:---:|:---:|:---:|---:|---:|:---:|
| **FIXTURE** | NO | NO | YES | None/Mock | Fixture Identity | `FIXTURE` | NO |
| **SIMULATION** | NO | NO | YES | None/Mock | Simulated Result | `SIMULATION` | NO |
| **RECORDED_CLOUD** | NO (during replay) | NO (during replay) | NO (source was real) | None (read-only) | Source Provenance | `RECORDED_CLOUD` | NO (current) / YES (historical) |
| **LIVE_WRITE** | YES | YES | Bounded Target | Real | Deterministic Receipt | `LIVE_WRITE` | YES (bounded) |

## 5. Adapter Mode-Lock and No-Silent-Fallback Rules

*   **Mode Selection is Explicit:** The caller (orchestrator/policy) selects the permitted mode before the operation begins.
*   **Adapter Mode Lock:** During operation, the mode is immutable. An adapter executes exactly the requested mode or fails.
*   **No Silent Fallback:** An adapter cannot silently downgrade or upgrade a mode. If a `LIVE_WRITE` fails, it returns `FAIL`, `NOT_RUN`, or `BLOCKED`. It must not silently return a fixture or simulated success. If a simulation is requested but unsupported, the adapter must fail the simulation request, not execute a real write.
*   **Explicit Transition:** To change mode, an explicit new operation with a new visible mode and evidence record must be initiated. A later mode run does not overwrite the evidence of an earlier failure in a different mode.
*   **Mode Mismatch:** If an adapter receives a request for a mode it does not support, it must fail closed (e.g., `BLOCKED` or unsupported error).

## 6. Adapter Support Matrix (Conceptual)

| Adapter Type | FIXTURE | SIMULATION | RECORDED_CLOUD | LIVE_WRITE |
|---|:---:|:---:|:---:|:---:|
| Fixture/Test Double | Supported | - | - | - |
| ShadowLab Twin | - | Supported | - | - |
| Evidence Replay | - | - | Supported | - |
| Real Service Connectors | - | - | - | Supported (if permitted by policy) |

*(Future adapters may support multiple modes only if explicit selection makes confusion impossible).*

## 7. Required Public Claim Honesty

Mode labels must be human-visible in every judge/operator-facing evidence surface (e.g., events, artifacts, demo UI, passports).

### Mode Claim Matrix

| Mode | Allowed Claim | Forbidden Claim |
|---|---|---|
| **FIXTURE** | "Fixture-based check passed." | "Managed service passed." |
| **SIMULATION** | "ShadowLab simulation passed." | "Production migration passed." |
| **RECORDED_CLOUD** | "Recorded evidence from prior real cloud execution." | "This operation ran live now." |
| **LIVE_WRITE** | "Real Draft PR created in controlled demo repo." | "Production deployment completed." |

## 8. Interaction with Existing Architecture

*   **Authority Map (P-04.02):** Mode selection is not Gemini authority. A model may suggest a mode, but cannot assign it if policy forbids it. LIVE_WRITE does not automatically require human approval; organizational policy dictates if it is autonomously allowed (e.g., a reversible Draft PR) or requires a human slot.
*   **Threat Model (P-04.03):** Mode changes cannot bypass trust boundaries. Credentials remain adapter-only for LIVE_WRITE.
*   **Managed-Service Honesty:** Mode labels cannot elevate or inflate canonical service statuses. A `RECORDED_CLOUD` replay of a service does not magically change an environment's canonical status from `NOT_RUN` to `VERIFIED`.

## 9. Reference Demo Mapping

For the ChangeMesh four-minute demo:
1.  **ShadowLab rehearsal:** `SIMULATION` mode (must visibly say simulated/rehearsed).
2.  **Artifact / Draft PR generation:** `LIVE_WRITE` mode (against controlled synthetic/demo repo, no production mutation implied).
3.  **Cloud execution proof:** `RECORDED_CLOUD` mode (if showing stored historical evidence) or explicitly labeled with what actually ran if a current backend event is triggered.

## 10. Claim Honesty Test Cases

*These adapter-wide scenarios remain `PLANNED / NOT_EXECUTED` until their owning adapter phases implement them. P-08.03 currently executes the prompt-boundary mode-mismatch case as PRIV-04.*

*   **MODE-001:** Fixture success presented as live proof. → **Expected: REJECT**
*   **MODE-002:** Simulation success presented without SIMULATION label. → **Expected: REJECT**
*   **MODE-003:** LIVE_WRITE fails and adapter returns fixture success. → **Expected: REJECT / mode violation**
*   **MODE-004:** Recorded-cloud replay presented as current live execution. → **Expected: REJECT**
*   **MODE-005:** Recorded-cloud artifact lacks source provenance/hash. → **Expected: UNPROVEN / REJECT**
*   **MODE-006:** Fixture adapter receives LIVE_WRITE request. → **Expected: BLOCKED / unsupported**
*   **MODE-007:** Real adapter receives SIMULATION request but cannot safely simulate. → **Expected: unsupported; must not execute real write**
*   **MODE-008:** Live Draft PR created with actual deterministic receipt. → **Expected: LIVE_WRITE evidence may record real external action**
*   **MODE-009:** Simulation PASS followed by LIVE_WRITE FAIL. → **Expected: both records remain; simulation does not overwrite live failure**
*   **MODE-010:** Mode change explicitly requested after failure. → **Expected: new operation/evidence record with new visible mode**

## 11. Acceptance Checklist

*   [x] FIXTURE defined.
*   [x] SIMULATION defined.
*   [x] RECORDED_CLOUD defined.
*   [x] LIVE_WRITE defined.
*   [x] Each has explicit visible label.
*   [x] Fixture != simulation.
*   [x] Simulation != live.
*   [x] Recorded-cloud != current live.
*   [x] Live-write requires real external effect.
*   [x] Adapter mode selection explicit.
*   [x] Adapter cannot silently fallback/change mode.
*   [x] Mode changes require new explicit operation/evidence.
*   [x] Mode provenance survives evidence pipeline.
*   [x] Evidence Boundary synchronized.
*   [x] README synchronized.
*   [x] Demo Script synchronized.
*   [x] Mode Contract exists.
*   [x] mode != evidence state.
*   [x] synthetic data != simulated execution.
*   [x] simulation success cannot overwrite live failure.
*   [x] recorded-cloud provenance required.
*   [x] recorded replay cannot claim current execution.
*   [x] LIVE_WRITE does not automatically require human approval.
*   [x] Release Steward cannot self-authorize.
*   [x] Gemini cannot change mode/facts.
*   [x] public claim preserves mode.
*   [x] managed-service status not inflated.
*   [x] credentials remain adapter-only.
*   [x] no production auto-merge/deploy introduced.
*   [x] P-08.03 prompt-boundary mode/provenance mismatch is rejected.
*   [ ] Full external adapter mode runtime and receipt matrix (future owning phases).
