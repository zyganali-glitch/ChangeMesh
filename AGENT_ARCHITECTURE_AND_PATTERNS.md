# ChangeMesh — Architecture and Patterns

## 1. Product boundary

ChangeMesh is a proof-carrying enterprise change system. It is not a generic chatbot, generic agent marketplace, general-purpose workflow builder, unrestricted coding agent, production auto-deployer, or formal-verification system.

## 2. Target runtime

- Agent orchestration: Google ADK
- Model: Gemini 3.5 or newer through Vertex AI or Gemini API
- API/web deployment: Cloud Run initially
- Async events: Pub/Sub
- Durable operational state: Firestore
- Long-term memory target: Memory Bank with Memory Trust Layer
- Registry target: Agent Registry
- Governance target: Agent Identity, Agent Gateway, Model Armor
- Telemetry: OpenTelemetry-compatible traces and Google Cloud Observability
- Source-control action: GitHub draft PR against a synthetic demo repository

Managed-service integrations remain conditional on real access and must be labeled honestly.

## 3. Agent architecture

- `Change Orchestrator`: owns saga state and routing.
- `Impact Scout`: read-only blast-radius collection.
- `Policy Guardian`: deterministic and model-assisted policy checks.
- `Migration Engineer`: scoped artifact generation.
- `Evidence Auditor`: independent semantic sufficiency review.
- `Release Steward`: reversible handoff and draft release preparation.

No agent receives unrestricted credentials. Every tool call is scoped by role, change ID, action class, and data class.

## 4. Core modules

- `domain/contracts`: versioned schemas and enums
- `orchestration`: ADK composition, routing, saga transitions
- `events`: Pub/Sub envelope, replay, dead-letter handling
- `state`: Firestore repositories and idempotency
- `memory`: trust typing, provenance, TTL, contradiction, quarantine
- `capability`: passport generation, validation, expiry, revocation
- `shadowlab`: scenario definitions, tool doubles, fault injection, results
- `policy`: reversibility and autonomy classification
- `integrations/github`: bounded GitHub adapter
- `integrations/metadata`: synthetic graph and optional DataHub adapter
- `evidence`: append-only evidence ledger and passport seal
- `observability`: trace correlation and redaction
- `web`: judge/operator dashboard

## 5. Architectural patterns

### 5.1 Saga-style change lifecycle

A change is a stateful distributed process. Every step defines input contract, idempotency key, allowed transitions, success/failure evidence, retry policy, compensating action, and next-state event.

### 5.2 Deterministic facts before model judgment

Deterministic code owns whether commands ran, exit codes, file hashes, test counts, state transitions, approval existence, passport integrity, and policy-table results. Gemini may assess semantic coverage but cannot modify those facts.

### 5.3 Fail closed for critical authorization

Unknown capability, expired memory, missing evidence, invalid schema, or uncertain irreversible target must not become authorization.

### 5.4 Additive-first, bounded adapters

External systems are accessed through typed adapters. Demo fixtures and real connectors share interfaces but never share evidence labels.

### 5.5 One-way dependency direction

UI and adapters depend on domain/application contracts. Domain logic does not depend on Google SDK clients, UI frameworks, or repository fixtures.

## 6. State labels

Evidence: `PASS|WARN|FAIL|NOT_RUN|SIMULATED|BLOCKED|QUARANTINED`

Initial lifecycle:

`RECEIVED → DISCOVERING → QUALIFYING → REHEARSING → GROUNDED → AUTHORIZED → EXECUTING → VERIFYING → AWAITING_AUTHORITY? → CERTIFYING → COMPLETE`

Failure branches:

`BLOCKED`, `RETRY_SCHEDULED`, `COMPENSATING`, `FAILED`, `CANCELLED`.

Exact schemas must be frozen during the domain-contract phase.

## 7. Autonomy policy

- `AUTO_EXECUTE`
- `AUTO_EXECUTE_AND_NOTIFY`
- `REHEARSE_THEN_EXECUTE`
- `HUMAN_AUTHORITY_REQUIRED`
- `BLOCKED`

Product must minimize approval count without weakening authority boundaries.

## 8. Evidence and fixture separation

- Fixture data is synthetic.
- ShadowLab output is `SIMULATED`.
- Local adapters cannot prove managed Google services.
- Recorded cloud evidence binds project, region, revision, timestamp, and sanitized trace IDs.
- Public evidence contains no secrets or personal data.

## 9. Architecture-change protocol

Architectural changes require decision-log entry, architecture-memory update, master-plan impact, migration note when contracts change, affected tests, and whole-repo consistency audit.
