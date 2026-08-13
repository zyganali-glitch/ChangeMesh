# ChangeMesh Domain Contract API Reference

> **Status:** `P-05.05 — IMPLEMENTED`
> **Produced by:** P-05.05
> **Date:** 2026-08-13
> **Implementation state:** The foundational domain contracts (P-05.01), evidence contracts (P-05.03), core innovation contracts (P-05.04), and event envelope contract (P-05.05: EventEnvelope, EventDeliveryDisposition, classify_event_delivery) defined below are implemented and tested. Naming conventions (P-05.06) remain `PENDING`.

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
    ArtifactHash,
    EventEnvelope,
    EventDeliveryDisposition,
    classify_event_delivery,
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

---

## 12. Event Envelope Contract (P-05.05)

Provider-neutral event identity and causal metadata envelope. All fields use `ConfigDict(extra="forbid", frozen=True)` for immutability.

### `EventDeliveryDisposition` (Enum)

Deterministic delivery classification for a provider-neutral event.

| Value | Semantics |
|---|---|
| `ACCEPT` | Event is new and causally consistent — admit it |
| `DUPLICATE` | Exact replay of an already-observed event |
| `OUT_OF_ORDER` | Causal predecessor has not yet been observed |
| `CONFLICT` | Structurally contradictory event identity, idempotency, or causal metadata |

**Excluded vocabulary:** `ACK`, `NACK`, `DEAD_LETTER`, `RETRYING`, `PUBLISHED`, `CONSUMED` — these belong to P-09 runtime transport.

**`OUT_OF_ORDER` is not `FAIL`:** It means the causal predecessor required to deterministically admit this event has not yet been observed. P-09/P-20 decide retry/recovery behavior.

**`CONFLICT` fails closed:** No silent merge, latest-wins, rewrite, or auto-correction.

### `EventEnvelope`

Canonical provider-neutral event envelope carrying event identity, change identity, causal chain metadata, correlation identity, producer provenance, and idempotency key.

| Field | Type | Required | Validation |
|---|---|---|---|
| `schema_version` | `str` | Yes | Must not be blank |
| `event_id` | `str` | Yes | Must not be blank |
| `change_id` | `str` | Yes | Must not be blank |
| `causation_id` | `Optional[str]` | No | None for root events; must not be blank if present; must not equal `event_id` (self-causation rejected) |
| `correlation_id` | `str` | Yes | Must not be blank |
| `producer_revision` | `str` | Yes | Must not be blank |
| `timestamp` | `datetime` | Yes | Typed datetime; wall-clock timestamp is metadata, NOT causal authority |
| `idempotency_key` | `str` | Yes | Must not be blank |

**Identity fields:**
- `event_id` — identity of one logical domain event
- `idempotency_key` — identity of the logical operation/publication effect whose duplicate execution must be prevented
- These are conceptually distinct and must not be collapsed or derived from each other

**Causation semantics:**
- Root event: `causation_id = None`
- Child event: `causation_id` points to the observed parent event
- Self-causation (`event_id == causation_id`) is rejected
- A causal child must share `change_id` and `correlation_id` with its observed cause

**Correlation semantics:**
- `correlation_id` is mandatory and identifies the logical distributed correlation chain
- A root may establish its own stable correlation identity
- A causal child must preserve its observed parent's correlation identity

**Producer revision:** Provenance/identity context for auditability. NOT runtime agent authorization, capability passport validity, or human approval.

**Timestamp boundary:** `timestamp` is typed `datetime` metadata. P-05.06 owns canonical serialized format, locale, precision, hashing, and JSON representation. Wall-clock timestamp is NOT causal authority — distributed clocks can skew.

**Credential boundary:** No field may carry tokens, secrets, API keys, private keys, service account material, sessions, or clients.

**Immutability:** Once validated, the envelope is frozen and cannot be mutated in place.

**Extra fields:** Rejected (`extra="forbid"`).

### `classify_event_delivery`

Pure, deterministic delivery classifier.

```python
def classify_event_delivery(
    incoming: EventEnvelope,
    seen_events: Mapping[str, EventEnvelope],
    seen_idempotency: Mapping[tuple[str, str], str],
) -> EventDeliveryDisposition
```

**Parameters:**
- `incoming` — the event envelope to classify
- `seen_events` — mapping of `event_id → EventEnvelope` for already-observed events
- `seen_idempotency` — mapping of `(change_id, idempotency_key) → event_id` for already-observed idempotency scopes

**Deterministic rules applied in order:**

| Rule | Condition | Result |
|---|---|---|
| A — Exact replay | `event_id` exists and stored envelope equals incoming | `DUPLICATE` |
| B — Same ID, different content | `event_id` exists but any immutable field differs | `CONFLICT` |
| C — Idempotency collision | Same `(change_id, idempotency_key)` but different `event_id` | `CONFLICT` |
| D — Root event | `causation_id` is None, no collision | `ACCEPT` |
| D — Cause unseen | `causation_id` set but cause not in `seen_events` | `OUT_OF_ORDER` |
| E — Causal consistency | `change_id` or `correlation_id` differs from observed cause | `CONFLICT` |
| Pass | All checks pass | `ACCEPT` |

**Idempotency scope:** `(change_id, idempotency_key)`. Same textual `idempotency_key` across different `change_id` values are independent identities.

**Purity guarantee:** Does not write state, read databases, call Pub/Sub, acknowledge messages, sleep, retry, create dead-letter records, or mutate its inputs.

**Pub/Sub runtime:** P-09 owns topic/subscription topology, publisher adapters, consumer adapters, delivery, acknowledgements, retries, dead-letter, and infrastructure config. `classify_event_delivery` provides the domain classification semantics that P-09 will consume.
