# ChangeMesh Authority Map

> **Status:** `P-04.02 — PLANNED / PRE-IMPLEMENTATION`
> **Produced by:** P-04.02
> **Date:** 2026-08-09
> **Implementation state:** This is an architecture design. No runtime implementation claims are made.

ChangeMesh cleanly separates authority into four distinct lanes to ensure that deterministic execution facts are never overwritten by model judgment or organizational policy, and that human approval remains strictly bounded.

## 1. Four Authority Classes

1. **Deterministic Code (`DETERMINISTIC_CODE`)**: Owns observed, mechanically verified execution facts and states.
2. **Gemini Semantic Judgment (`GEMINI_SEMANTIC_JUDGMENT`)**: Owns narrowly scoped, advisory semantic interpretations.
3. **Organizational Policy (`ORGANIZATIONAL_POLICY`)**: Owns normative organizational rules and permissions.
4. **Human Authority (`HUMAN_AUTHORITY`)**: Owns irreducible business intent, risk acceptance, and policy-mandated overrides within explicitly permitted slots.

**Important Distinction:** Authority Source ≠ Evaluator / Enforcement Component ≠ Consumer. For instance, Organizational Policy is the source of a rule; the Policy Guardian enforces it; Approval Compression consumes it.

## 2. Authority Table

| Decision Type / Fact | Authority Class | Authority Source | Evaluator / Enforcer | May Read / Consume | Must Never Override |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Deterministic Facts** | | | | | |
| Command actually executed | `DETERMINISTIC_CODE` | Process exit status | Evidence Record | Gemini, Policy, Human | Gemini, Human |
| Tool/API call actually occurred | `DETERMINISTIC_CODE` | Network/connector boundary | Evidence Record | Gemini, Policy, Human | Gemini, Human |
| Test PASS/FAIL | `DETERMINISTIC_CODE` | Test runner | Evidence Record | Gemini, Policy, Human | Gemini, Human |
| Artifact/hash identity | `DETERMINISTIC_CODE` | Hashing algorithm | Evidence Record | Gemini, Policy, Human | Gemini, Human |
| Event chronology | `DETERMINISTIC_CODE` | System clock / sequence | PubSub Timeline | Gemini, Policy, Human | Gemini, Human |
| Durable saga state | `DETERMINISTIC_CODE` | Database transaction | Firestore Saga | Gemini, Policy, Human | Gemini, Human |
| State-transition validity | `DETERMINISTIC_CODE` | Saga rules | Orchestrator | Gemini, Policy, Human | Gemini, Human |
| Structured-output validation | `DETERMINISTIC_CODE` | Schema validator | Gemini Structured Output | Gemini, Policy, Human | Gemini, Human |
| Capability Passport validity/revocation | `DETERMINISTIC_CODE` | Signature/registry | Capability Module | Gemini, Policy, Human | Gemini, Human |
| Memory trust/TTL/quarantine result | `DETERMINISTIC_CODE` | Memory Trust Layer rules | Memory Trust Layer | Gemini, Policy, Human | Gemini, Human |
| Deterministic preflight result | `DETERMINISTIC_CODE` | Preflight checks | ShadowLab Auth | Gemini, Policy, Human | Gemini, Human |
| External-write receipt/result | `DETERMINISTIC_CODE` | Target API response | Release Steward | Gemini, Policy, Human | Gemini, Human |
| Deterministic repository/blast-radius | `DETERMINISTIC_CODE` | Git/GitLab API | Impact Scout | Gemini, Policy, Human | Gemini, Human |
| Mechanically verifiable public-claim parity | `DETERMINISTIC_CODE` | Linter / string matching | Claim Audit | Gemini, Policy, Human | Gemini, Human |
| **Gemini Semantic Judgments** | | | | | |
| Natural-language goal semantic interpretation | `GEMINI_SEMANTIC_JUDGMENT` | Gemini Model | Agent Orchestrator | Policy, Human | Deterministic facts |
| Semantic evidence sufficiency | `GEMINI_SEMANTIC_JUDGMENT` | Gemini Model | Evidence Auditor | Policy, Human | Deterministic facts |
| Semantic explanation/risk interpretation | `GEMINI_SEMANTIC_JUDGMENT` | Gemini Model | Evidence Auditor / Policy Guardian | Policy, Human | Deterministic facts |
| Semantic comparison of candidates | `GEMINI_SEMANTIC_JUDGMENT` | Gemini Model | Impact Scout / Orchestrator | Policy, Human | Deterministic facts |
| **Organizational Policy** | | | | | |
| Permitted autonomous action classes | `ORGANIZATIONAL_POLICY` | Organization Configuration | Policy Guardian | Human, Orchestrator | Deterministic facts |
| Prohibited action classes | `ORGANIZATIONAL_POLICY` | Organization Configuration | Policy Guardian | Human, Orchestrator | Deterministic facts |
| Human-approval requirement | `ORGANIZATIONAL_POLICY` | Organization Configuration | Policy Guardian | Approval Compression | Deterministic facts |
| Required evidence threshold | `ORGANIZATIONAL_POLICY` | Organization Configuration | Policy Guardian | Orchestrator | Deterministic facts |
| Data/privacy restrictions | `ORGANIZATIONAL_POLICY` | Organization Configuration | Policy Guardian | Orchestrator | Deterministic facts |
| Capability/action permissions | `ORGANIZATIONAL_POLICY` | Organization Configuration | Policy Guardian | Orchestrator | Deterministic facts |
| Separation-of-duty requirements | `ORGANIZATIONAL_POLICY` | Organization Configuration | Policy Guardian | Release Steward | Deterministic facts |
| Allowed exception mechanism | `ORGANIZATIONAL_POLICY` | Organization Configuration | Policy Guardian | Approval Compression | Deterministic facts |
| **Human Authority** | | | | | |
| Specific irreversible-action approval | `HUMAN_AUTHORITY` | Human Operator | Approval Compression | Release Steward | Deterministic facts |
| Business-intent clarification | `HUMAN_AUTHORITY` | Human Operator | Approval Compression | Orchestrator | Deterministic facts |
| Choice between legitimate business outcomes | `HUMAN_AUTHORITY` | Human Operator | Approval Compression | Orchestrator | Deterministic facts |
| Policy-permitted residual-risk decision | `HUMAN_AUTHORITY` | Human Operator | Approval Compression | Policy Guardian | Deterministic facts, Hard deny |

## 3. Authority Non-Overwrite Matrix

| Actor / Authority | Cannot overwrite |
| :--- | :--- |
| **Gemini** | deterministic facts, organizational policy, human approval |
| **Human** | deterministic facts, hard policy deny |
| **Organizational policy** | historical execution facts |
| **Orchestrator** | deterministic facts, policy source, human decision |
| **Evidence Auditor** | Evidence Record facts |
| **Release Steward** | authorization state |
| **Approval Compression** | actual human decision |
| **UI** | facts, policy, evidence ownership, authority |

## 4. Conflict Rules

*   **Gemini vs Deterministic Evidence:** Deterministic evidence stays authoritative. Gemini result may be rejected/quarantined/recomputed, but the fact is never rewritten.
*   **Human vs Deterministic Evidence:** Human cannot rewrite evidence (e.g. mark a failed test as passed). Human may only make a separate policy-permitted authority decision.
*   **Human vs Hard Organizational Policy Deny:** Hard policy deny remains blocking unless organizational policy explicitly defines a legitimate exception mechanism.
*   **Orchestrator vs Canonical Owner:** Canonical owner always wins. Orchestrator coordinates but takes no ownership over domain facts.
*   **Unknown Authority:** FAIL CLOSED. No decision is permitted merely because no owner was found.

## 5. Planned Tests (PLANNED / NOT_EXECUTED)

| Test ID | Invariant | Scenario | Expected Result | Future Target |
| :--- | :--- | :--- | :--- | :--- |
| **AUTH-001** | Gemini fact overwrite rejected | Test result is `FAIL`, Gemini says "semantically acceptable". | Fact remains `FAIL`. | P-25 |
| **AUTH-002** | Missing execution evidence | Gemini claims tool ran, but no deterministic record exists. | Tool execution remains `NOT_RUN` / unproven. | P-25 |
| **AUTH-003** | Human fact overwrite rejected | Human attempts to mark failed test as passed. | Rejected; fact immutable. | P-25 |
| **AUTH-004** | Hard policy deny un-bypassable | Policy denies action. Human clicks approve. | Blocked unless explicit policy exception exists. | P-25 |
| **AUTH-005** | Approval Compression cannot self-approve | Approval Compression produces decision package without human response. | Authority remains unresolved. | P-25 |
| **AUTH-006** | Release Steward cannot self-authorize | Release Steward tries external write without required authorization. | Blocked. | P-25 |
| **AUTH-007** | Evidence Auditor facts read-only | Semantic auditor attempts to change Evidence Record. | Rejected. | P-25 |
| **AUTH-008** | Orchestrator cannot own durable state | Orchestrator attempts direct durable-state ownership bypassing Firestore Saga. | Architecture violation. | P-25 |
| **AUTH-009** | Unknown authority fails closed | Decision type has no registered authority. | Blocked, not guessed. | P-25 |
| **AUTH-010** | Duplicate authority detected | Same decision type mapped to Gemini and Human. | Authority-map validation failure. | P-25 |
| **AUTH-011** | Policy source provenance required | Policy evaluator receives unknown/untrusted policy source. | No authorization. | P-25 |
| **AUTH-012** | Semantic output schema validation | Gemini output fails structured validation. | Output rejected; no fact/policy mutation. | P-25 |
| **AUTH-013** | Capability invalid/revoked | Invalid/expired agent capability. | Routing/action blocked regardless of Gemini. | P-25 |
| **AUTH-014** | Memory trust failure | Expired/quarantined memory influences decision. | Cannot become trusted authority input. | P-25 |
| **AUTH-015** | External write evidence | Write authorized but actual write failed. | Write-result fact is FAIL; authorization remains. | P-25 |
