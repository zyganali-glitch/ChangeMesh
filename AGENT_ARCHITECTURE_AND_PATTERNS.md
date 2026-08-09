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

- `Change Orchestrator (Google ADK)` (`src/agents/change_orchestrator.py`): owns ADK routing, saga coordination, and recovery; durable workflow state is owned by Firestore Saga.
- `Impact Scout` (`src/git/impact_scout.py`): read-only blast-radius collection, repository overlap, and parallel-change conflict detection (CS-BLAST-001, GL-CONFLICT-001 unified).
- `Policy Guardian` (`src/agents/policy_guardian.py`): deterministic and model-assisted policy checks, safety pre-checks (ZK-PRIV-001).
- `Migration Engineer` (`src/agents/migration_engineer.py`): scoped artifact generation and migration boundaries (CS-MIG-001).
- `Evidence Record / Ledger` (`src/evidence/evidence_record.py`): canonical deterministic fact and evidence authority (CCT-EVID-001).
- `Evidence Auditor` (`src/agents/evidence_auditor.py`): independent semantic sufficiency review (CCT-SEM-001).
- `Release Steward` (`src/agents/release_steward.py`): reversible handoff and enforced pipeline writebacks (CS-WRITE-001). Consumes judge format from `docs/JUDGING_MAP.md` (CCT-JUDGE-001 canonical target) but is not the canonical owner of that component.

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

### 5.6 Authority Map Invariants (P-04.02)

ChangeMesh implements a strict, four-lane authority model:
*   **One authority per decision type**: Every decision is owned by exactly one authority class.
*   **Deterministic facts are immutable**: Execution facts cannot be overwritten by Gemini semantic judgment or Human authority.
*   **Policy separation**: Organizational Policy is the source of normative rules; Policy Guardian merely enforces them.
*   **Human authority is bounded**: Human decisions are only permitted within slots explicitly defined by Organizational Policy. Approval Compression packages this authority but cannot synthesize it.
*   **No self-authorization**: Executors (e.g. Release Steward) cannot authorize their own actions.
*   **Detailed canonical map**: The full mapping of decisions to authorities lives in [`docs/AUTHORITY_MAP.md`](docs/AUTHORITY_MAP.md).

### 5.7 Trust Boundary Invariants (P-04.03)

ChangeMesh enforces strict zero-trust boundary rules:
*   **External Content is Untrusted**: Content from GitHub, tools, or metadata graphs is treated as data, never as system instructions.
*   **Credential Isolation**: Credentials exist only at adapters. Credential material must never propagate to model prompts, memory, evidence, or public UI.
*   **Bounded Delegation**: Agents and subagents cannot delegate authority they do not possess.
*   **Public UI is Low-Trust**: The public judge surface receives only sanitized data and holds no reusable external-write credentials.
*   **No Authority Escalation**: Crossing a trust boundary never elevates authority (e.g., untrusted data cannot become policy).
*   **Detailed Threat Model**: Lives in [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

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

## 10. Dependency direction invariants (P-04.01)

Provider-specific outer layers depend inward on ChangeMesh domain contracts. Domain contracts never depend outward on providers.

- `domain/contracts/` → Google SDK, ADK, Firestore, PubSub, GitHub, UI, fixtures: **FORBIDDEN**
- Adapters, UI, fixtures → `domain/contracts/`: **REQUIRED** (inward)
- Production code → fixture/test code: **FORBIDDEN**

Adapters are architecturally replaceable: changing a provider adapter (e.g., GitHub → synthetic, Firestore → test double) must not require changes to domain contracts.

Full dependency matrix and package map: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
