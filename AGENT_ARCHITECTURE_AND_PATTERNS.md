# ChangeMesh — Architecture and Patterns

## 1. Product boundary

ChangeMesh is a proof-carrying enterprise change system. It is not a generic chatbot, generic agent marketplace, general-purpose workflow builder, unrestricted coding agent, production auto-deployer, or formal-verification system.

## 2. Target runtime

- Agent orchestration: Google ADK
- Model: Gemini 3.5 or newer through Vertex AI or Gemini API
- API/web deployment: Agent Runtime/Platform + Cloud Run for supporting services
- Async events: Pub/Sub
- Durable operational state: Firestore (Operational State)
- Long-term memory target: ChangeMesh Memory Trust Layer + Agent Platform Memory Bank
- Registry target: Agent Registry
- Governance target: Agent Identity (SPIFFE-based) + ChangeMesh Capability Passport, Agent Gateway (networkservices), ChangeMesh Policy Guardian, Model Armor
- Telemetry: ADK OpenTelemetry -> Cloud Logging/Trace
- Source-control action: GitHub draft PR against a synthetic demo repository

Managed-service integrations remain conditional on real access and must be labeled honestly.

## 3. Agent architecture and target components

- `Change Orchestrator (Google ADK)` (`src/agents/change_orchestrator.py`): owns saga state and routing.
- `Impact Scout` (`src/git/impact_scout.py`): read-only blast-radius collection (CS-BLAST-001).
- `Policy Guardian` (`src/agents/policy_guardian.py`): deterministic and model-assisted policy checks, safety pre-checks (ZK-PRIV-001).
- `Migration Engineer` (`src/agents/migration_engineer.py`): scoped artifact generation and migration boundaries (CS-MIG-001).
- `Evidence Auditor` (`src/agents/evidence_auditor.py`): independent semantic sufficiency review and evidence extraction (CCT-EVID-001, CCT-SEM-001).
- `Release Steward` (`src/agents/release_steward.py`): reversible handoff, enforced pipeline writebacks, and judge format exports (CS-WRITE-001, CCT-JUDGE-001).

No agent receives unrestricted credentials. Every tool call is scoped by role, change ID, action class, and data class.
Additional core targets:
- `Approval Compression` (`src/auth/approval_compression.py`): defines autonomous vs escalation boundaries (UIPATH-AUTH-001).
- `ShadowLab Auth` (`src/policy/shadowlab_auth.py`): preflight validation and destructive action boundaries (CCT-PREFLIGHT-001).
- `Change Passport` (`src/evidence/change_passport.py`): immutable passporting context (CS-PASS-001).
- `Firestore Saga` (`src/orchestrator/firestore_saga.py`): persistent saga state (UIPATH-STATE-001).
- `Gemini Structured Output` (`src/core/gemini_structured_output.py`): zero trust deserialization and contract validation (ZK-VALID-001).
- `Claim Audit` (`src/audit/claim_audit.py`): hard proof of claims and cross-document parity (ZK-CLAIM-001).
- `PubSub Timeline` (`src/evidence/pubsub_timeline.py`): chronological execution and causal ordering (CCT-FLIGHT-001).

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
