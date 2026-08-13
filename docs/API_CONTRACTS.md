# ChangeMesh Domain Contract API Reference

> **Status:** `P-05.04 — IMPLEMENTED`
> **Produced by:** P-05.04
> **Date:** 2026-08-13
> **Implementation state:** The foundational domain contracts (P-05.01), evidence contracts (P-05.03), and core innovation contracts (P-05.04: MemoryRecord, CapabilityPassport, RehearsalScenario, RehearsalResult, AutonomyDecision, ApprovalCompressionCard) defined below are implemented and tested. Event envelope (P-05.05) and naming conventions (P-05.06) remain `PENDING`.

## 1. Overview

The `domain/contracts/` package contains the provider-neutral core contract layer for ChangeMesh. These contracts define **what** ChangeMesh does without prescribing **how** the underlying infrastructure delivers it.

**Import path:**

```python
from domain.contracts import (
    DataClassLevel,
    DataClass,
    SuccessCriterion,
    ChangeRequest,
    AgentDescriptor,
    ToolDescriptor,
    ChangeState,
    IllegalTransitionError,
    CHANGE_LIFECYCLE_VERSION,
    can_transition,
    require_transition,
    is_terminal,
    EvidenceRecord,
    EvidenceState,
    ExecutionEvidenceMode,
    Provenance,
    TraceReference,
    ArtifactHash
)
```

**Provider-neutral guarantee:** These contracts import only Python standard library types and Pydantic. They do not import Google ADK, Vertex AI, Firestore, Pub/Sub, GitHub SDK, or any UI/framework types.

**Fail-closed validation:** All contracts use `model_config = ConfigDict(extra="forbid")`, rejecting unknown fields. Required identifiers and schema versions are validated non-blank.

---

## 2. DataClassLevel (Enum)

Bounded set of data-classification levels derived from the ChangeMesh threat model (§7).

| Value | Semantics |
|---|---|
| `PUBLIC` | Open / conceptual information |
| `INTERNAL` | Organization-internal operational data |
| `CONFIDENTIAL` | Sensitive business information requiring restricted organizational access |
| `RESTRICTED` | Regulated data requiring special handling |

**Type:** Inherits from `str` and `Enum`.

**Credentials Boundary:** Credentials, tokens, API keys, and reusable secret material are explicitly outside the ordinary DataClass permission surface and remain adapter-only regardless of DataClass level.

---

## 3. DataClass

Typed data-classification contract.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `classification` | `DataClassLevel` | Yes | Must be a valid enum value |

**Purpose:** Machine-readable classification that agents, tools, and orchestration use to enforce data-handling boundaries.

**Extra fields:** Rejected (`extra="forbid"`).

---

## 4. SuccessCriterion

What must be true for a requested change to count as successful.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `criterion_id` | `str` | Yes | Must not be blank |
| `description` | `str` | Yes | — |
| `verification_method` | `str` | Yes | — |
| `required_evidence_types` | `list[str]` | Yes | — |

**Purpose:** Describes *desired conditions*, not proof that those conditions were met. Evidence of satisfaction belongs to `EvidenceRecord` (P-05.03).

**Identifier:** `criterion_id` — stable, domain-specific identifier.

**Extra fields:** Rejected.

---

## 5. ChangeRequest

Typed user/change intent entering ChangeMesh.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `request_id` | `str` | Yes | Must not be blank |
| `title` | `str` | Yes | — |
| `description` | `str` | Yes | — |
| `target_systems` | `list[str]` | Yes | — |
| `data_classification` | `DataClassLevel` | Yes | Valid enum value |
| `success_criteria` | `list[SuccessCriterion]` | Yes | Each element validated as SuccessCriterion |
| `requested_by` | `str` | Yes | — |
| `requested_at` | `datetime` | Yes | ISO 8601 |

**Purpose:** Intent contract — describes what someone wants to change and why. Not workflow state, execution proof, or approval result.

**Identifier:** `request_id` — stable change-request identity.

**Typed relationship:** `success_criteria` uses the actual `SuccessCriterion` contract, not untyped dictionaries.

**Extra fields:** Rejected.

---

## 6. AgentDescriptor

Declared identity, role, and capabilities of an agent revision.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `agent_id` | `str` | Yes | Must not be blank |
| `agent_revision` | `str` | Yes | Must not be blank |
| `role` | `str` | Yes | — |
| `description` | `str` | Yes | — |
| `declared_capabilities` | `list[str]` | Yes | — |
| `permitted_data_classifications` | `list[DataClassLevel]` | Yes | Valid enum values |
| `permitted_tool_ids` | `list[str]` | Yes | — |

**Purpose:** Metadata describing what an agent is and what it claims to do.

**Identifier:** `agent_id` — stable agent identity. `agent_revision` provides version precision.

**Scope boundary:** `AgentDescriptor` is NOT `CapabilityPassport`. It carries no qualification proof, trust evidence, signature validity, or authorization state. Those belong to P-05.04.

**Extra fields:** Rejected.

---

## 7. ToolDescriptor

Describes a tool's interface and capability boundary.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `tool_id` | `str` | Yes | Must not be blank |
| `tool_revision` | `str` | Yes | Must not be blank |
| `name` | `str` | Yes | — |
| `description` | `str` | Yes | — |
| `declared_actions` | `list[str]` | Yes | — |
| `is_read_only` | `StrictBool` | Yes | Must be strict boolean (e.g., rejects `"true"`) |
| `permitted_data_classifications` | `list[DataClassLevel]` | Yes | Valid enum values |

**Purpose:** Description of a tool — its identity, declared actions, and data scope. Not a live tool client, SDK wrapper, or execution evidence.

**Identifier:** `tool_id` — stable tool identity. `tool_revision` provides version precision.

**Provider-neutral:** No API tokens, SDK clients, executable callbacks, session objects, or provider credentials.

**Extra fields:** Rejected.

---

## 8. Remaining Deferred Contracts

The following are explicitly deferred to later P-05 micro-tasks:

| Contract | Owner Phase | Status |
|---|---|---|
| Event envelope (event ID, change ID, causation, correlation) | P-05.05 | `PENDING` |
| Naming, enum, timestamp, hashing, redaction, serialization conventions | P-05.06 | `PENDING` |

---

## 9. Evidence Contracts (P-05.03)

The following provider-neutral contracts define how evidence facts are recorded without manufacturing execution proof or leaking provider dependencies.

**Immutability guarantee:** All P-05.03 evidence models use `ConfigDict(extra="forbid", frozen=True)`. Once constructed and validated, evidence facts cannot be mutated in-place. Post-construction field assignment raises `ValidationError`. This enforces deterministic fact sovereignty: a validated `FAIL` cannot become `PASS`, a `SIMULATION` mode cannot become `LIVE_WRITE`, and `RECORDED_CLOUD` provenance cannot lose its historical proof.

### `ExecutionEvidenceMode` (Enum)
Canonical collection mode for execution evidence.
- `FIXTURE`, `SIMULATION`, `RECORDED_CLOUD`, `LIVE_WRITE`

### `EvidenceState` (Enum)
Canonical evidence state describing the result of a check or action.
- `PASS`, `WARN`, `FAIL`, `NOT_RUN`, `SIMULATED`, `BLOCKED`, `QUARANTINED`

### `ArtifactHash`
Provider-neutral ArtifactHash contract.
| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `algorithm` | `str` | Yes | Must not be blank |
| `digest` | `str` | Yes | Must not be blank |

### `TraceReference`
Provider-neutral TraceReference contract for correlating an evidence record with an execution trace.
| Field | Type | Required | Validation |
|---|---|---|---|
| `trace_id` | `str` | Yes | Must not be blank |
| `span_id` | `Optional[str]` | No | Must not be blank if present |

### `Provenance`
Provenance contract describing origin, mode, and historical context.
| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `source` | `str` | Yes | Must not be blank |
| `collection_mode` | `ExecutionEvidenceMode` | Yes | Valid enum value |
| `collection_timestamp` | `datetime` | Yes | — |
| `source_execution_identifier` | `Optional[str]` | No | Must not be blank if present; required for `RECORDED_CLOUD` |
| `source_execution_timestamp` | `Optional[datetime]`| No | Required for `RECORDED_CLOUD` |

### `EvidenceRecord`
Canonical provider-neutral evidence fact schema.
| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `evidence_id` | `str` | Yes | Must not be blank |
| `change_request_id` | `str` | Yes | Must not be blank |
| `subject` | `str` | Yes | Must not be blank |
| `state` | `EvidenceState` | Yes | Valid enum value |
| `provenance` | `Provenance` | Yes | Nested validation; `SIMULATED` state demands `FIXTURE` or `SIMULATION` mode |
| `trace` | `Optional[TraceReference]`| No | Nested validation |
| `artifacts` | `tuple[ArtifactHash, ...]` | No | Immutable tuple; must have at least one for `RECORDED_CLOUD`; list input accepted at construction and converted to tuple |

---

## 10. Change Lifecycle State Machine

Typed lifecycle and transitions defining the safe progression of an enterprise change.

### `ChangeState` (Enum)

| State | Role |
|---|---|
| `RECEIVED` | Initial intake of ChangeRequest |
| `DISCOVERING` | Agent/Tool/Impact gathering |
| `QUALIFYING` | Passport/Capability validation |
| `REHEARSING` | ShadowLab validation runs |
| `GROUNDED` | Context loaded and validated |
| `AWAITING_AUTHORITY` | Human policy-approval wait state |
| `AUTHORIZED` | Safe for irreversible execution |
| `EXECUTING` | Running change logic |
| `VERIFYING` | Validating evidence and success criteria |
| `CERTIFYING` | Sealing passport |
| `RETRY_SCHEDULED` | Resuming after failure |
| `COMPENSATING` | Rolling back state |
| `BLOCKED` | **Terminal**: Policy/Safety denial |
| `COMPLETE` | **Terminal**: Successfully certified |
| `FAILED` | **Terminal**: Unrecoverable error |
| `CANCELLED` | **Terminal**: User explicit abort |

### Exposed Operations

| Function | Signature | Purpose |
|---|---|---|
| `can_transition` | `(current: ChangeState, target: ChangeState, *, retry_origin: Optional[ChangeState] = None) -> bool` | Safe boolean check if an edge exists. |
| `require_transition` | `(current: ChangeState, target: ChangeState, *, retry_origin: Optional[ChangeState] = None) -> None` | Enforces transition graph, raising `IllegalTransitionError` if blocked. |
| `is_terminal` | `(state: ChangeState) -> bool` | Identifies if a state has no outgoing edges. |

### Lifecycle Security Invariants
- **Bounded Retry**: `RETRY_SCHEDULED` is a visible recovery state, not an escalation path. Transitions out of retry must explicitly provide the `retry_origin` context. Resumption is strictly bounded to the exact state that originated the retry (e.g. `DISCOVERING` retry resumes at `DISCOVERING`). Bypassing intermediate stages via retry is structurally impossible. All exits from `RETRY_SCHEDULED`, including terminal exits, require a valid retriable origin.
- **`AWAITING_AUTHORITY`**: Represents an explicit organizational-policy `HUMAN_AUTHORITY` slot, not a universal approval gate. `LIVE_WRITE` does not automatically mean `AWAITING_AUTHORITY`. Gemini uncertainty cannot manufacture human authority.
- **`AUTHORIZED`**: Does not represent blanket permission for irreversible mutation. It signifies "Policy-authorized for the next bounded execution step within the current authority envelope."
- **Immutability**: `ALLOWED_TRANSITIONS` and retry context mapping use `MappingProxyType` to prevent runtime mutation. Terminal states cannot be resurrected or retry.
- **Compensation Boundary**: `COMPENSATING` is reachable only from `EXECUTING` or `VERIFYING`. Its exits are strictly bounded to `RETRY_SCHEDULED` (originating from `COMPENSATING`), `FAILED`, `CANCELLED`, or `BLOCKED`.

---

## 11. Core Innovation Contracts (P-05.04)

Six schema-only contracts defining the core innovation surface. All use `ConfigDict(extra="forbid", frozen=True)` for immutability. Provider-neutral (no `google.*`, `opentelemetry.*` imports). Runtime services (Memory Trust Layer, ShadowLab, Agent Registry, Approval Compression runtime) are deferred to P-11–P-14.

### `MemoryTrustStatus` (Enum)

Explicit trust status for a `MemoryRecord`.
- `UNTRUSTED`
- `TRUSTED`
- `QUARANTINED`

### `MemoryRecord`

Typed, versioned memory fact with explicit trust metadata. **Memory is not truth** — it is not an authority source or action authorization.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `memory_id` | `str` | Yes | Must not be blank |
| `scope` | `str` | Yes | Must not be blank |
| `content` | `str` | Yes | Must not be blank |
| `source` | `str` | Yes | Must not be blank |
| `capture_timestamp` | `datetime` | Yes | — |
| `expiry_timestamp` | `datetime` | Yes | Must be > `capture_timestamp` |
| `data_classification` | `DataClassLevel` | Yes | Valid enum value |
| `trust_status` | `MemoryTrustStatus` | No | Defaults to `UNTRUSTED` |
| `trust_evidence_ids` | `tuple[str, ...]` | No | Must have at least 1 non-blank ref if `TRUSTED`; no duplicates |
| `contradiction_ids` | `tuple[str, ...]` | No | Elements must be non-blank; no duplicates |
| `is_quarantined` | `bool` | No | Defaults to `False` |
| `quarantine_reason` | `Optional[str]` | No | Required if `is_quarantined` is True |

**Authority invariant:** `trust_status == TRUSTED` does not grant authority. A trusted memory can be overridden by policy. Memory trust does not substitute for human authority slots.

### `CapabilityPassport`

Versioned, immutable proof-of-capability envelope. **Valid passport is not authorization** — it proves capability, not permission.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `passport_id` | `str` | Yes | Must not be blank |
| `agent_id` | `str` | Yes | Must not be blank |
| `agent_revision` | `str` | Yes | Must not be blank |
| `qualified_capabilities` | `tuple[str, ...]` | Yes | At least one; all non-blank; no duplicates |
| `qualified_tool_ids` | `tuple[str, ...]` | No | All non-blank; no duplicates |
| `permitted_data_classifications` | `tuple[DataClassLevel, ...]` | No | Valid enum values |
| `qualification_evidence_ids` | `tuple[str, ...]` | Yes | At least one; all non-blank; no duplicates |
| `issuer` | `str` | Yes | Must not be blank |
| `issued_at` | `datetime` | Yes | — |
| `expires_at` | `datetime` | Yes | Must be > `issued_at` |
| `is_revoked` | `bool` | No | Defaults to `False` |
| `revoked_at` | `Optional[datetime]` | No | Must be ≥ `issued_at`; required if `is_revoked` is True |
| `revocation_reason` | `Optional[str]` | No | Required if `is_revoked` is True |

### `FaultInjectionSpec`

Declarative fault-injection specification for rehearsal scenarios.

| Field | Type | Required | Validation |
|---|---|---|---|
| `fault_id` | `str` | Yes | Must not be blank |
| `fault_type` | `str` | Yes | Must not be blank |
| `target` | `str` | Yes | Must not be blank |
| `parameters` | `tuple[tuple[str, str], ...]` | No | Keys must not be blank |

### `RehearsalScenario`

Defines a single rehearsal scenario for ShadowLab dry-runs. Data only, no executable callbacks.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `scenario_id` | `str` | Yes | Must not be blank |
| `change_request_id` | `str` | Yes | Must not be blank |
| `description` | `str` | Yes | Must not be blank |
| `target_refs` | `tuple[str, ...]` | Yes | At least one; all non-blank; no duplicates |
| `success_criterion_ids` | `tuple[str, ...]` | No | All non-blank; no duplicates |
| `tool_double_ids` | `tuple[str, ...]` | No | All non-blank; no duplicates |
| `fault_injections` | `tuple[FaultInjectionSpec, ...]` | No | Nested validation |
| `created_at` | `datetime` | Yes | — |
| `scenario_version` | `str` | Yes | Must not be blank |

### `RehearsalResult`

Records the outcome of a rehearsal run. **PASS does not authorize live execution.**

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `result_id` | `str` | Yes | Must not be blank |
| `scenario_id` | `str` | Yes | Must not be blank |
| `change_request_id` | `str` | Yes | Must not be blank |
| `state` | `EvidenceState` | Yes | Valid enum value |
| `provenance` | `Provenance` | Yes | `collection_mode` must be `SIMULATION` |
| `started_at` | `datetime` | Yes | — |
| `completed_at` | `datetime` | Yes | Must be ≥ `started_at` |
| `evidence_record_ids` | `tuple[str, ...]` | No | Required for executed states (`PASS`, `FAIL`, `WARN`, `SIMULATED`); all non-blank; no duplicates |
| `diagnostic_refs` | `tuple[str, ...]` | No | All non-blank; no duplicates |

### `AutonomyClass` (Enum)

Classification of how much human involvement is needed:
- `AUTO_EXECUTE` — No human needed
- `AUTO_EXECUTE_AND_NOTIFY` — Execute then inform
- `REHEARSE_THEN_EXECUTE` — Dry run first
- `HUMAN_AUTHORITY_REQUIRED` — Must get human sign-off before execution
- `BLOCKED` — Cannot proceed

### `AutonomyDecision`

Records why a particular autonomy class was assigned.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `decision_id` | `str` | Yes | Must not be blank |
| `change_request_id` | `str` | Yes | Must not be blank |
| `action_class` | `str` | Yes | Must not be blank |
| `autonomy_class` | `AutonomyClass` | Yes | Valid enum value |
| `policy_source` | `str` | Yes | Must not be blank |
| `policy_revision` | `Optional[str]` | No | Must not be blank if present |
| `decided_at` | `datetime` | Yes | — |
| `rationale` | `str` | Yes | Must not be blank |
| `authority_slot_ref` | `Optional[str]` | No | Required for `HUMAN_AUTHORITY_REQUIRED`; strictly forbidden for all other classes |
| `required_rehearsal_refs` | `tuple[str, ...]` | No | Required for `REHEARSE_THEN_EXECUTE`; at least one; all non-blank; no duplicates |

**Authority invariants:**
- `LIVE_WRITE != HUMAN_AUTHORITY_REQUIRED` — write scope does not automatically trigger a human authority slot.
- Gemini uncertainty is not an autonomy class — model confidence cannot manufacture `HUMAN_AUTHORITY_REQUIRED`.
- `BLOCKED != HUMAN_AUTHORITY_REQUIRED` — blocked changes do not become review requests.

### `ApprovalCompressionCard`

Pre-built decision packet for human authority slots. **Card existence is NOT approval.** The card reduces time-to-decision, it does not contain or record the human decision.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `card_id` | `str` | Yes | Must not be blank |
| `change_request_id` | `str` | Yes | Must match `autonomy_decision.change_request_id` |
| `autonomy_decision` | `AutonomyDecision` | Yes | Must have `autonomy_class == HUMAN_AUTHORITY_REQUIRED` |
| `authority_slot_ref` | `str` | Yes | Must match `autonomy_decision.authority_slot_ref` |
| `decision_question` | `str` | Yes | Must not be blank |
| `decision_options` | `tuple[str, ...]` | Yes | At least 2 unique non-blank options |
| `policy_reason` | `str` | Yes | Must not be blank |
| `action_scope` | `str` | Yes | Must not be blank |
| `completed_work_summary` | `str` | Yes | Must not be blank |
| `rehearsed_work_summary` | `str` | Yes | Must not be blank |
| `remaining_decision_summary` | `str` | Yes | Must not be blank |
| `evidence_refs` | `tuple[str, ...]` | No | All non-blank; no duplicates |
| `created_at` | `datetime` | Yes | — |

**Forbidden fields:** No `approved`, `is_approved`, `human_decision`, `human_response`, `approval_result`, or `auto_approved` field exists. The card is a decision *input*, not a decision *record*.
