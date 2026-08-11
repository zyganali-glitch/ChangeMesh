# ChangeMesh Domain Contract API Reference

> **Status:** `P-05.01 — IMPLEMENTED`
> **Produced by:** P-05.01
> **Date:** 2026-08-11
> **Implementation state:** The five foundational domain contracts defined below are implemented and tested. Additional contracts (EvidenceRecord, lifecycle state machine, CapabilityPassport, event envelope, etc.) remain `PENDING` in P-05.02–P-05.06.

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
| `CONFIDENTIAL` | Sensitive business data, credentials |
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

## 8. Contracts NOT in P-05.01

The following are explicitly deferred to later P-05 micro-tasks:

| Contract | Owner Phase |
|---|---|
| Lifecycle state machine, transitions, terminal states | P-05.02 |
| EvidenceRecord, EvidenceState, Provenance, TraceReference, ArtifactHash | P-05.03 |
| MemoryRecord, CapabilityPassport, RehearsalScenario, RehearsalResult, AutonomyDecision, ApprovalCompressionCard | P-05.04 |
| Event envelope (event ID, change ID, causation, correlation) | P-05.05 |
| Naming, enum, timestamp, hashing, redaction, serialization conventions | P-05.06 |
