# ChangeMesh Autonomy and Friction Architecture Review

> **Status:** `P-04.05 COMPLETED — ARCHITECTURE REVIEW ONLY`
> **Date:** 2026-08-11
> **Produced by:** P-04.05
> **Implementation state:** This is an architecture review and checklist. No product code exists yet. All dispositions are architecture-level documentation decisions, not runtime implementations.

## 1. Review Scope

### Files and surfaces reviewed

| Surface | File(s) | Reviewed for |
|---|---|---|
| Supreme constitution | `AGENTS.md` | Interview prohibition, autonomy defaults |
| Rules | `CHANGEMESH_RULES.md` | IL-19 autonomy/friction lock |
| Architecture memory | `AGENT_ARCHITECTURE_AND_PATTERNS.md` | Authority model, autonomy policy, routing |
| Environment memory | `AGENT_ENVIRONMENT_AND_API.md` | Credential isolation |
| Lessons memory | `AGENT_MEMORY_AND_LESSONS.md` | LESSON-01 governance ≠ product friction |
| User preferences | `AGENT_USER_PREFERENCES.md` | Human-on-the-loop preference |
| Master plan | `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md` | P-04.05 acceptance, scope lock |
| Handoff | `docs/HANDOFF.md` | Next task parity |
| Architecture | `docs/ARCHITECTURE.md` | Component ownership, routing, deferred work |
| Authority Map | `docs/AUTHORITY_MAP.md` | Four-lane authority, human slots |
| Threat Model | `docs/THREAT_MODEL.md` | Trust boundaries, delegation bounds |
| Mode Contract | `docs/MODE_CONTRACT.md` | LIVE_WRITE autonomy, no-silent-fallback |
| Evidence Boundary | `docs/EVIDENCE_BOUNDARY.md` | Evidence vs authority distinction |
| Decision Log | `docs/DECISION_LOG.md` | Existing ADRs 0001–0013 |
| Demo Script | `docs/DEMO_SCRIPT.md` | Reference demo human touch count |
| Outcome Contract | `docs/OUTCOME_CONTRACT.md` | Approval Compression metrics |
| Dashboard Reqs | `docs/DASHBOARD_REQUIREMENTS.md` | Approval card, recovery card |
| Judging Map | `docs/JUDGING_MAP.md` | Evidence requirements |
| README | `README.md` | Public autonomy claims |
| Agent rules | `.agents/rules/20-evidence-and-autonomy-boundary.md` | Autonomy enforcement |
| Donor manifest | `docs/DONOR_REUSE_MANIFEST.md` | Forbidden carry-over: routine approval |
| Gemini adapter | `GEMINI.md` | No routine approvals rule |

### Repository-wide term search

The following friction-related terms were searched across all `*.md` files: `approval`, `approve`, `human`, `authority`, `confirmation`, `confirm`, `manual`, `route`, `routing`, `interview`, `question`, `clarification`, `retry`, `resume`, `pause`, `blocked`, `uncertain`, `LIVE_WRITE`, `HUMAN_AUTHORITY_REQUIRED`.

Each hit was evaluated in context. Results are summarized in the friction inventory below.

---

## 2. Autonomy Principles (Frozen)

These principles govern ChangeMesh human-on-the-loop behavior. They are derived from `AGENTS.md`, `CHANGEMESH_RULES.md`, `README.md`, and the authority architecture (P-04.01 through P-04.04).

1. **Autonomous by default:** Human attention is an exception, not routine labor.
2. **Human-on-the-loop:** Ask for authority only at irreducible or policy-defined boundaries.
3. **Deterministic facts are sovereign:** No human, model, or policy can convert `FAIL` or `NOT_RUN` to `PASS`.
4. **Policy evaluates itself:** Organizational policy is machine-evaluable where rules are sufficiently specified. Policy Guardian enforces; it does not author policy and it is not the human.
5. **LIVE_WRITE ≠ HUMAN_AUTHORITY_REQUIRED:** Organizational policy determines whether a bounded live write executes autonomously, requires rehearsal, requires human authority, or is prohibited.
6. **No self-authorization:** Executors (Release Steward) cannot authorize their own actions. Approval Compression cannot self-approve.
7. **Gemini uncertainty ≠ human gate:** Gemini being uncertain does not automatically create a human approval request.
8. **System-owned routing:** The Change Orchestrator / ADK architecture owns agent routing and multi-agent coordination. Humans do not manually select agents.
9. **Bounded retry before escalation:** Deterministic retry, alternate strategy, compensation, ShadowLab correction, and fail-closed behavior are all preferred before unnecessary human escalation.
10. **Safe work continues:** A long-lived change does not freeze all safe work merely because one authority decision is pending. Only the narrowest blocked edge pauses.
11. **Trusted memory reduces questions:** Cross-session memory should avoid re-asking already-valid context. Stale/quarantined memory is rejected, not re-confirmed.
12. **Evidence before escalation:** Prepare a compressed decision packet before interrupting a human.
13. **Frozen charter:** No Phase-0 interview. Questions only for irreducible blocking decisions.

---

## 3. Friction Inventory

### A. Human Approval Audit

| # | Interaction / Gate | File | Current Owner | Sync? | Human Required? | Authority Justification | Disposition |
|---|---|---|---|---|---|---|---|
| A-01 | Irreversible-action approval | `AUTHORITY_MAP.md` §2 | Human Operator via Approval Compression | Async possible | Yes | `HUMAN_AUTHORITY` — policy-defined slot for irreversible business action | `KEEP — REQUIRED AUTHORITY` |
| A-02 | Business-intent clarification | `AUTHORITY_MAP.md` §2 | Human Operator via Approval Compression | Async possible | Yes | `HUMAN_AUTHORITY` — irreducible business choice | `KEEP — REQUIRED AUTHORITY` |
| A-03 | Choice between legitimate business outcomes | `AUTHORITY_MAP.md` §2 | Human Operator via Approval Compression | Async possible | Yes | `HUMAN_AUTHORITY` — genuine ambiguity between valid paths | `KEEP — REQUIRED AUTHORITY` |
| A-04 | Policy-permitted residual-risk decision | `AUTHORITY_MAP.md` §2 | Human Operator via Approval Compression | Async possible | Yes | `HUMAN_AUTHORITY` — risk acceptance within policy exception | `KEEP — REQUIRED AUTHORITY` |
| A-05 | Demo approval card (one touch) | `DEMO_SCRIPT.md` §3:15–3:35 | Human Operator | Async | Yes (if policy requires) | Organizational policy determines if required | `KEEP — CONDITIONAL ON POLICY` |
| A-06 | Human-approval requirement definition | `AUTHORITY_MAP.md` §2 | Organizational Policy → Policy Guardian | N/A (policy is source) | No — policy is source, not human approval gate | `ORGANIZATIONAL_POLICY` evaluates automatically | `AUTOMATE` |
| A-07 | Allowed exception mechanism | `AUTHORITY_MAP.md` §2 | Organizational Policy → Policy Guardian | N/A | No | Policy rule, not human gate | `AUTOMATE` |

**Finding:** All human approval points in the architecture are legitimate `HUMAN_AUTHORITY` slots defined by organizational policy. No unnecessary synchronous approval was found. The two `ORGANIZATIONAL_POLICY` rows (A-06, A-07) correctly identify policy as the source — they are not human approval gates and are already correctly modeled.

### B. Interview / Clarification Audit

| # | Interaction | File | Current State | Disposition |
|---|---|---|---|---|
| B-01 | Phase-0 interview prohibition | `AGENTS.md` §0 | Frozen charter — no Phase-0 interview. Questions only when four conditions met. | `KEEP — CORRECTLY PROHIBITED` |
| B-02 | Product charter interview | `README.md` §"Autonomous by default" | Charter frozen; no interview required. | `KEEP — CORRECTLY PROHIBITED` |
| B-03 | Donor interview prohibition | `docs/DONOR_REUSE_MANIFEST.md`, `docs/P-04.00_ARCHITECTURE_DONOR_PREFLIGHT.md` | "Mandatory interview" listed as forbidden carry-over from donors. | `KEEP — CORRECTLY PROHIBITED` |
| B-04 | User preferences: no generic questions | `AGENT_USER_PREFERENCES.md` | "Do not ask generic discovery questions; ChangeMesh charter is frozen." | `KEEP — CORRECTLY PROHIBITED` |
| B-05 | Master plan interview prohibition | `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md` §0 | "No generic Phase-0 interview is permitted." | `KEEP — CORRECTLY PROHIBITED` |
| B-06 | Business-intent clarification (legitimate) | `AUTHORITY_MAP.md` | `HUMAN_AUTHORITY` — irreducible business-intent decision via Approval Compression | `KEEP — REQUIRED AUTHORITY` |

**Finding:** No residual Phase-0 or generic interview behavior exists in the product architecture. All prohibitions are consistently stated across governance, plan, memory, and preferences. The only legitimate clarification path is through Approval Compression for irreducible business decisions.

### C. Manual Routing Audit

| # | Interaction | File | Current State | Disposition |
|---|---|---|---|---|
| C-01 | Agent routing | `docs/ARCHITECTURE.md` §8 | Change Orchestrator owns routing, coordination, recovery | `KEEP — SYSTEM-OWNED` |
| C-02 | Capability-qualified routing | `AGENT_ARCHITECTURE_AND_PATTERNS.md` §7 | Autonomy policy classes determine routing. Capability Passport required. | `KEEP — SYSTEM-OWNED` |
| C-03 | Subagent delegation | `docs/THREAT_MODEL.md` §8 | Bounded delegation — parent agent assigns, not human | `KEEP — SYSTEM-OWNED` |
| C-04 | Retry/recovery routing | `docs/ARCHITECTURE.md` §8 | Orchestrator owns recovery | `KEEP — SYSTEM-OWNED` |

**Finding:** No manual agent routing exists. The Change Orchestrator owns all routing, delegation, and multi-agent coordination. The Capability Passport provides deterministic qualification. No human is asked to select agents.

### D. Retry and Recovery Audit

| # | Interaction | File | Current State | Disposition |
|---|---|---|---|---|
| D-01 | Saga retry/compensation | `AGENT_ARCHITECTURE_AND_PATTERNS.md` §5.1 | Saga defines retry policy, compensating action, and next-state event per step | `KEEP — BOUNDED AUTONOMOUS` |
| D-02 | ShadowLab correction | `DEMO_SCRIPT.md` §1:35–2:15 | First rehearsal fails; system autonomously switches strategy | `KEEP — AUTONOMOUS CORRECTION` |
| D-03 | Recovery demo | `docs/OUTCOME_CONTRACT.md` §3 | Demonstrate 1 successful recovery in ShadowLab simulation | `KEEP — AUTONOMOUS RECOVERY` |
| D-04 | Development three-attempt protocol | `CHANGEMESH_RULES.md` §6 | Three attempts then stop and escalate | `KEEP — DEVELOPMENT ONLY` |
| D-05 | Adapter mode-lock failure | `docs/MODE_CONTRACT.md` §5 | Failed LIVE_WRITE returns FAIL/NOT_RUN/BLOCKED — no silent fallback | `KEEP — FAIL CLOSED` |

**Finding:** Retry and recovery are system-owned and bounded. Failures return control to the Orchestrator for deterministic retry, compensation, or strategy switching — not to a human. Human escalation only occurs after system-level recovery options are exhausted, per the product invariant "Evidence before escalation."

### E. Gemini Uncertainty Audit

| # | Interaction | File | Current State | Disposition |
|---|---|---|---|---|
| E-01 | Semantic output validation | `AUTHORITY_MAP.md` AUTH-012 | Failed structured validation → output rejected, no fact/policy mutation | `KEEP — FAIL CLOSED` |
| E-02 | Semantic sufficiency assessment | `AUTHORITY_MAP.md` §2 | `GEMINI_SEMANTIC_JUDGMENT` — advisory, does not override facts | `KEEP — ADVISORY ONLY` |
| E-03 | Natural-language goal interpretation | `AUTHORITY_MAP.md` §2 | `GEMINI_SEMANTIC_JUDGMENT` — advisory | `KEEP — ADVISORY ONLY` |
| E-04 | Unknown authority | `AUTHORITY_MAP.md` AUTH-009 | Fail closed — blocked, not guessed | `KEEP — FAIL CLOSED` |

**Finding:** Gemini uncertainty correctly never creates a human gate. Gemini output is advisory for semantic judgment and cannot override deterministic facts or organizational policy. When Gemini is uncertain, the system uses deterministic validation, schema checks, or fails closed — it does not escalate to a human merely because the model is uncertain.

### F. Deterministic-Fact Audit

| # | Fact Type | Authority | Current State | Disposition |
|---|---|---|---|---|
| F-01 | Command execution | `DETERMINISTIC_CODE` | Evidence Record owns; Gemini/Human cannot override | `KEEP — IMMUTABLE` |
| F-02 | Test PASS/FAIL | `DETERMINISTIC_CODE` | Test runner owns; AUTH-001 and AUTH-003 reject overrides | `KEEP — IMMUTABLE` |
| F-03 | Artifact/hash identity | `DETERMINISTIC_CODE` | Hashing algorithm owns | `KEEP — IMMUTABLE` |
| F-04 | Saga state | `DETERMINISTIC_CODE` | Firestore Saga owns via DB transaction | `KEEP — IMMUTABLE` |
| F-05 | Capability Passport validity | `DETERMINISTIC_CODE` | Signature/registry check | `KEEP — IMMUTABLE` |
| F-06 | Memory trust/quarantine | `DETERMINISTIC_CODE` | Memory Trust Layer rules | `KEEP — IMMUTABLE` |
| F-07 | Preflight result | `DETERMINISTIC_CODE` | ShadowLab Auth | `KEEP — IMMUTABLE` |
| F-08 | External-write receipt | `DETERMINISTIC_CODE` | Target API response | `KEEP — IMMUTABLE` |

**Finding:** All deterministic facts are owned by `DETERMINISTIC_CODE` and cannot be overridden by any other authority class. The Evidence Boundary explicitly states: "Human approval does not convert deterministic `FAIL`/`NOT_RUN` into `PASS`." No friction violation found.

### G. Organizational-Policy Audit

| # | Policy Decision | Evaluator | Human? | Disposition |
|---|---|---|---|---|
| G-01 | Permitted autonomous action classes | Policy Guardian | No | `AUTOMATE` |
| G-02 | Prohibited action classes | Policy Guardian | No | `AUTOMATE` |
| G-03 | Human-approval requirement definition | Policy Guardian (enforces) | Only source — not a human gate each time | `AUTOMATE` |
| G-04 | Required evidence threshold | Policy Guardian | No | `AUTOMATE` |
| G-05 | Data/privacy restrictions | Policy Guardian | No | `AUTOMATE` |
| G-06 | Separation-of-duty requirements | Policy Guardian | No | `AUTOMATE` |

**Finding:** Organizational policy is correctly modeled as machine-evaluable where rules are sufficiently specified. Policy Guardian enforces but does not author policy and is not itself the human. No policy evaluation becomes a human review gate.

### H. Waiting-Authority Concurrency Audit

| # | Architecture Statement | Current State | Disposition |
|---|---|---|---|
| H-01 | Saga-style change lifecycle | `AGENT_ARCHITECTURE_AND_PATTERNS.md` §5.1 — each step defines independent contracts | `KEEP — SUPPORTS PARTIAL PROGRESS` |
| H-02 | Async event timeline | `DEMO_SCRIPT.md` §0:55–1:35 — parallel impact/policy analysis while user remains idle | `KEEP — ASYNC CONTINUATION` |
| H-03 | PubSub Timeline | `docs/ARCHITECTURE.md` — chronological execution and causal ordering | `KEEP — ASYNC BACKBONE` |

**Architecture gap found — documented below as architectural invariant:**

The existing architecture supports asynchronous work via PubSub, saga steps, and parallel analysis. However, no explicit invariant states that safe independent work may continue while a narrow authority edge waits. This is addressed by adding a new autonomy invariant (see §5 Architecture Repairs).

**Disposition:** `ASYNC / CONTINUE SAFE WORK` — Add explicit architectural invariant.

### I. Approval Compression Audit

| # | Check | Current State | Disposition |
|---|---|---|---|
| I-01 | Cannot self-approve | AUTH-005: produces package without human response → authority unresolved | `KEEP — INTEGRITY PRESERVED` |
| I-02 | Cannot auto-approve or infer from silence | Mode Contract §5: missing/invalid treated as DENY (TB-13) | `KEEP — INTEGRITY PRESERVED` |
| I-03 | One bounded card in demo | Demo Script §3:15–3:35: "One card only" | `KEEP — MINIMAL TOUCH` |
| I-04 | Exception-based, not universal gate | `CHANGEMESH_RULES.md` IL-19, `README.md` "Autonomous by default" | `KEEP — EXCEPTION-BASED` |

**Finding:** Approval Compression is correctly modeled as a compression mechanism, not an approval bureaucracy. It packages the smallest irreducible decision and cannot self-approve, auto-approve, or infer approval from silence.

### J. Memory Friction Audit

| # | Check | Current State | Disposition |
|---|---|---|---|
| J-01 | Trusted cross-session memory reduces questions | `README.md`, `AGENT_ARCHITECTURE_AND_PATTERNS.md` — typed, governed, cross-session | `KEEP — FRICTION REDUCTION` |
| J-02 | Stale memory rejected | Memory Trust Layer: TTL, quarantine, provenance | `KEEP — SAFETY PRESERVED` |
| J-03 | No human confirmation per read | No architecture statement requires human confirmation for memory reads | `KEEP — NO FRICTION FOUND` |
| J-04 | Quarantined memory cannot be trusted | AUTH-014: expired/quarantined memory cannot become trusted input | `KEEP — SAFETY PRESERVED` |

**Finding:** Memory architecture correctly reduces repeated questioning through trusted cross-session memory while maintaining safety through provenance, TTL, and quarantine. No unnecessary human confirmation gates exist for memory reads.

### K. Capability Qualification Audit

| # | Check | Current State | Disposition |
|---|---|---|---|
| K-01 | Deterministic qualification | Capability Passport: signature/registry check | `KEEP — SYSTEM-OWNED` |
| K-02 | System-owned routing | Change Orchestrator routes to proven revision | `KEEP — SYSTEM-OWNED` |
| K-03 | No manual agent selection for ordinary operation | No architecture document requires user to select agents | `KEEP — NO FRICTION FOUND` |

**Finding:** Capability qualification and agent routing are system-owned. Users do not manually select agent revisions for ordinary operation.

### L. Reference-Demo Friction Audit

| Demo Phase | Human Interaction | Required? | Disposition |
|---|---|---|---|
| 0:00–0:25 — Goal | User provides one high-level goal | Yes — initiating action | `KEEP — NECESSARY INPUT` |
| 0:25–0:55 — Discover/qualify | None — autonomous | N/A | `KEEP — AUTONOMOUS` |
| 0:55–1:35 — Impact/policy | None — user remains idle | N/A | `KEEP — AUTONOMOUS` |
| 1:35–2:15 — ShadowLab | None — autonomous correction | N/A | `KEEP — AUTONOMOUS` |
| 2:15–2:50 — Real action | None (or one if policy requires) | Conditional on policy | `KEEP — POLICY-DETERMINED` |
| 2:50–3:15 — Memory | None — trusted continuation | N/A | `KEEP — AUTONOMOUS` |
| 3:15–3:35 — Approval | One card if policy requires | Conditional on policy | `KEEP — MINIMAL AUTHORITY` |
| 3:35–4:00 — Passport/proof | None — evidence display | N/A | `KEEP — AUTONOMOUS` |

**Finding:** The reference demo architecture achieves a maximum of one compressed human authority decision where organizational policy requires it, plus the initial goal input. This is consistent with the "one minimal authority touch" target. No demo-specific friction shortcuts were found.

---

## 4. Summary of Findings

### Legitimate human authority retained (correct — no change)

- Irreversible-action approval via Approval Compression
- Business-intent clarification via Approval Compression
- Choice between legitimate business outcomes via Approval Compression
- Policy-permitted residual-risk acceptance via Approval Compression
- Initial goal input (user initiates the change)

### No unnecessary approval found

The architecture consistently models human approval as exception-based and authority-bound. Every human interaction point is backed by a `HUMAN_AUTHORITY` slot explicitly defined by organizational policy. No general "ask the human" fallback exists.

### No interview friction found

Phase-0 interview prohibition is consistently stated across five governance surfaces (`AGENTS.md`, `README.md`, `AGENT_USER_PREFERENCES.md`, master plan, `GEMINI.md`). Donor interview behavior is explicitly listed as forbidden carry-over.

### No manual routing found

The Change Orchestrator exclusively owns agent routing, multi-agent coordination, and recovery. No architecture document requires or implies manual agent selection.

### Retry/recovery correctly autonomous

Saga-defined retry, compensation, ShadowLab correction, and fail-closed behavior are system-owned. Human escalation occurs only after bounded system-level recovery is exhausted.

### Architecture gap: waiting-authority concurrency

The architecture supports asynchronous work (PubSub, saga steps, parallel analysis) but did not have an explicit invariant stating that safe independent work continues while a narrow authority edge waits. **This gap is closed by adding an explicit autonomy invariant to `docs/ARCHITECTURE.md`** (see §5).

---

## 5. Architecture Repairs

### Repair 1: Add Autonomy and Friction Invariants to `docs/ARCHITECTURE.md`

**Rationale:** The architecture document defines principles for dependency direction, trust boundaries, authority segregation, and mode contract — but did not have an explicit section on autonomy and friction invariants. This section makes the P-04.05 autonomy principles binding at the architecture level.

**Action:** Added new §12 "Autonomy and Friction Invariants (P-04.05)" to `docs/ARCHITECTURE.md`.

### Repair 2: Mark P-04.05 as DONE in deferred work table

**Action:** Updated §11 deferred work table entry for P-04.05 from `PENDING` to `DONE`.

### Repair 3: Decision Log ADR-0014

**Action:** Added ADR-0014 to `docs/DECISION_LOG.md` freezing the autonomy and friction model.

---

## 6. Acceptance Checklist

| # | Gate | Evidence | Result |
|---|---|---|---|
| 1 | No unnecessary synchronous approval remains | Friction inventory §A: all human gates are legitimate `HUMAN_AUTHORITY` | PASS |
| 2 | No unnecessary interview remains | Friction inventory §B: Phase-0 prohibited across 5 surfaces | PASS |
| 3 | No unnecessary manual routing remains | Friction inventory §C: Orchestrator owns all routing | PASS |
| 4 | Deterministic facts require no human approval | Friction inventory §F: all owned by `DETERMINISTIC_CODE` | PASS |
| 5 | Gemini uncertainty does not create authority | Friction inventory §E: advisory only, fail closed on uncertainty | PASS |
| 6 | Organizational policy can permit autonomous bounded writes | `MODE_CONTRACT.md` §8: "LIVE_WRITE does not automatically require human approval; organizational policy dictates" | PASS |
| 7 | `LIVE_WRITE` is not universally human-gated | `MODE_CONTRACT.md` §8, `README.md` §"Autonomous by default", `EVIDENCE_BOUNDARY.md` | PASS |
| 8 | Release Steward does not self-authorize | `AUTHORITY_MAP.md` AUTH-006, `ARCHITECTURE.md` §9 | PASS |
| 9 | Bounded retry/recovery preferred before escalation | Friction inventory §D: saga retry, ShadowLab correction, fail-closed | PASS |
| 10 | Safe independent work continues while authority edge waits | Architecture repair §12 invariant added | PASS |
| 11 | Trusted memory reduces repeated questioning | Friction inventory §J: cross-session memory, no confirmation per read | PASS |
| 12 | Reference demo preserves minimal human touch | Friction inventory §L: one goal + conditional one authority card | PASS |
| 13 | Safety/evidence/trust boundaries intact | Authority map, threat model, mode contract preserved without weakening | PASS |
| 14 | Mode-contract invariants intact | Four modes, no-silent-fallback, mode-lock preserved | PASS |
| 15 | Evidence honesty intact | Evidence boundary, claim honesty matrix preserved | PASS |
| 16 | No product implementation introduced | Zero `src/**` changes | PASS |

---

## 7. Planned Tests (PLANNED / NOT_EXECUTED)

The following test cases are defined for future implementation phases. They are NOT currently executed.

| Test ID | Invariant | Scenario | Expected Result | Target Phase |
|---|---|---|---|---|
| AUTON-001 | No unnecessary approval | Reversible autonomous action presented to Approval Compression | Action proceeds without human gate | P-14 |
| AUTON-002 | Policy-determined autonomy | LIVE_WRITE classified as `AUTO_EXECUTE` by policy | Executes without human interaction | P-16 |
| AUTON-003 | Gemini uncertainty → fail closed | Model uncertain about migration safety | System retries or fails closed; no human gate created | P-08 |
| AUTON-004 | Safe work continues | One saga edge waits for authority; independent edge proceeds | Independent edge completes while authority edge waits | P-20 |
| AUTON-005 | Trusted memory reduces questions | Valid trusted memory available for previously-answered question | System uses memory instead of re-asking user | P-11 |
| AUTON-006 | System-owned routing | Multiple qualified agent revisions available | Orchestrator selects without user intervention | P-12 |
| AUTON-007 | Bounded retry before escalation | Tool call fails with transient error | System retries within bounded policy before considering escalation | P-20 |
| AUTON-008 | Approval Compression cannot self-approve | Decision package generated without human response | Authority remains unresolved; no auto-approval | P-14 |
