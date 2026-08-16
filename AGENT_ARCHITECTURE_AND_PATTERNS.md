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

- `Change Orchestrator (Google ADK)` (`src/agents/change_orchestrator.py`): ADK intake skeleton implemented (P-07.01); deterministic routing/delegation implemented (P-07.03); multi-agent branch coordination, parallel execution, and sequential fallback implemented (P-07.04 via `src/agents/coordinator.py`); saga coordination, recovery PLANNED; durable workflow state is owned by Firestore Saga.
- `Impact Scout` (`src/git/impact_scout.py`): read-only blast-radius collection, repository overlap, and parallel-change conflict detection (CS-BLAST-001, GL-CONFLICT-001 unified).
- `Policy Guardian` (`src/agents/policy_guardian.py`): deterministic and model-assisted policy checks, safety pre-checks (ZK-PRIV-001).
- `Migration Engineer` (`src/agents/migration_engineer.py`): scoped artifact generation and migration boundaries (CS-MIG-001).
- `Evidence Record / Ledger` (`src/evidence/evidence_record.py`): canonical deterministic fact and evidence authority (CCT-EVID-001).
- `Evidence Auditor` (`src/agents/evidence_auditor.py`): independent semantic sufficiency review (CCT-SEM-001).
- `Release Steward` (`src/agents/release_steward.py`): reversible handoff and enforced pipeline writebacks (CS-WRITE-001). Consumes judge format from `docs/JUDGING_MAP.md` (CCT-JUDGE-001 canonical target) but is not the canonical owner of that component.

No agent receives unrestricted credentials. Every tool call is scoped by role, change ID, action class, and data class.
Additional core targets:
- `Bounded Gemini Model Client` (`src/core/gemini_client.py`): canonical single bounded Gemini client (P-08.01 IMPLEMENTED).
- `Approval Compression` (`src/auth/approval_compression.py`): defines autonomous vs escalation boundaries (UIPATH-AUTH-001).
- `ShadowLab Auth` (`src/policy/shadowlab_auth.py`): preflight validation and destructive action boundaries (CCT-PREFLIGHT-001).
- `Change Passport` (`src/evidence/change_passport.py`): immutable passporting context (CS-PASS-001).
- `Firestore Saga` (`src/orchestrator/firestore_saga.py`): persistent saga state (UIPATH-STATE-001).
- `Gemini Structured Output` (`src/core/gemini_structured_output.py`): zero trust deserialization and contract validation (ZK-VALID-001).
- `Claim Audit` (`src/audit/claim_audit.py`): hard proof of claims and cross-document parity (ZK-CLAIM-001).
- `PubSub Timeline` (`src/evidence/pubsub_timeline.py`): chronological execution and causal ordering (CCT-FLIGHT-001).

## 4. Core modules

- `domain/contracts`: versioned schemas and enums (P-05.01 foundational contracts IMPLEMENTED: ChangeRequest, SuccessCriterion, AgentDescriptor, ToolDescriptor, DataClass; P-05.02 lifecycle IMPLEMENTED; P-05.03 evidence IMPLEMENTED; P-05.04 core innovation contracts IMPLEMENTED: MemoryRecord, CapabilityPassport, RehearsalScenario, RehearsalResult, AutonomyDecision, ApprovalCompressionCard; P-05.05 event envelope IMPLEMENTED: EventEnvelope, EventDeliveryDisposition, classify_event_delivery; P-05.06 machine conventions IMPLEMENTED: HashAlgorithm, UtcDateTime, canonical_json_bytes, redact_mapping, naming/enum conventions; P-07.05 agent revision metadata IMPLEMENTED: AgentRevisionProvenance, Provenance/EventEnvelope integration)
- `src/agents`: Google ADK agent implementations (P-07.01 Change Orchestrator skeleton IMPLEMENTED; P-07.02 specialized agent fleet definitions and bounded contracts IMPLEMENTED; P-07.03 deterministic routing/delegation IMPLEMENTED; P-07.04 sequential fallback and controlled parallel branches IMPLEMENTED; P-07.05 agent revision metadata IMPLEMENTED)
- `src/core`: core system utilities and outer provider clients (P-08.01 `BoundedGeminiClient` in `src/core/gemini_client.py` IMPLEMENTED)
- `api`: API entrypoint for HTTP/REST and webhook invocations (PLANNED)
- `orchestration`: deterministic local routing/delegation IMPLEMENTED under P-07.03; multi-agent branch coordination, parallel execution, single-writer aggregation, sequential fallback, and exact revision tracing IMPLEMENTED under P-07.04/P-07.05 via `src/agents/coordinator.py`; durable saga transitions, Firestore persistence, Pub/Sub orchestration, and recovery remain PLANNED under their later owning phases
- `events`: Pub/Sub envelope, replay, dead-letter handling (PLANNED)
- `state`: Firestore repositories and idempotency (PLANNED)
- `memory`: trust typing, provenance, TTL, contradiction, quarantine (PLANNED)
- `capability`: passport generation, validation, expiry, revocation (PLANNED)
- `shadowlab`: scenario definitions, tool doubles, fault injection, results (PLANNED)
- `policy`: reversibility and autonomy classification (PLANNED)
- `integrations/github`: bounded GitHub adapter (PLANNED)
- `integrations/metadata`: synthetic graph and optional DataHub adapter (PLANNED)
- `integrations/gcp`: Google Cloud provider adapters for Firestore, Pub/Sub, Vertex AI / Gemini SDK (PLANNED)
- `evidence`: append-only evidence ledger and passport seal (PLANNED)
- `observability`: trace correlation and redaction (PLANNED)
- `web`: browser-native HTML5/CSS3/JavaScript judge/operator dashboard with Node NOT_REQUIRED per ADR-0015 (PLANNED)

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

### 5.8 Multi-Agent Coordination and Runtime Isolation Invariants (P-07.04)

*   **Non-Bypassable Sequential Fallback**: Every request for parallel execution (`plan.strategy == PARALLEL`, `force_strategy == PARALLEL`, or `ChangeOrchestrator.execute_parallel()`) must pass `BranchCoordinator.is_parallel_safe()`. If any safety invariant is violated (duplicate specialist targets, Release Steward concurrency), execution automatically falls back to `ExecutionStrategy.SEQUENTIAL` with `fallback_triggered=True` and a recorded deterministic fallback reason.
*   **Deep Runtime Input Isolation**: Branch inputs (`BranchPlan.branches`, `BranchSpec.routing_request`, and payloads) are deep-copied on intake and dispatch (`isolated_spec = copy.deepcopy(spec)`). In-place mutations performed inside one branch runner cannot leak to concurrent branches or modify caller-owned input collections.
*   **Single-Writer Aggregation**: Branch outputs are aggregated strictly by `BranchCoordinator` into deterministic plan order regardless of arrival order.

### 5.9 Agent Revision Metadata and Provenance Invariants (P-07.05)

*   **Unambiguous Machine-Checkable Revision Identity**: Every agent-produced event, evidence, routing trace, and coordination trace must carry exact agent identity (`agent_id`) bound to exact semantic revision (`agent_revision`). Two different agents using `1.0.0` remain machine-distinguishable.
*   **Zero Escape Hatches**: No `unknown`, `latest`, `current`, `null`, `none`, `*`, `undefined`, or blank string may satisfy revision provenance.
*   **Event Conflict Semantics**: Same `event_id` with changed immutable revision provenance deterministically produces `EventDeliveryDisposition.CONFLICT` rather than duplicate replay.
*   **Canonical State Projection**: Multi-agent coordination state projection (`CoordinationResult.get_canonical_state_projection()`) strips wall-clock timestamps while preserving exact `agent_id`, `agent_revision`, and `role`.

### 5.10 Bounded Gemini Model Client Invariants (P-08.01)

*   **Single Model Authority Boundary**: All runtime Gemini invocations must flow through `BoundedGeminiClient` (`src/core/gemini_client.py`). No ad hoc SDK clients in application code.
*   **Exact Canonical Model**: Strict binding to `gemini-3.6-flash`. Unapproved model overrides or ambient environment configurations fail closed with `ModelConfigurationError`.
*   **Single Retry Authority**: ChangeMesh wrapper owns retry explicitly (max 3 attempts with exponential backoff on retryable status codes {429, 502, 503, 504} and network disconnects). Non-retryable errors (400, 401, 403, 404, safety blocks) fail immediately on attempt 1.
*   **Explicit Positive Finite Bounds**: Timeout is bounded [1.0s, 60.0s] (default 30.0s). Max output tokens is bounded [1, 8192] (default 4096).
*   **Immutable Enterprise Safety**: All 5 harm categories are strictly configured to `HarmBlockThreshold.BLOCK_LOW_AND_ABOVE`. Blocked responses raise `ModelSafetyBlockedError` and fail closed.
*   **Non-Secret Operational Telemetry**: Typed `ModelCallTelemetry` records operational metrics while strictly forbidding credential material, prompt contents, and response text.
*   **Zero Silent Fallback**: Zero fallback to other models, preview versions, other providers, cached answers, or fake PASS sentinels.

## 6. State labels

Evidence: `PASS|WARN|FAIL|NOT_RUN|SIMULATED|BLOCKED|QUARANTINED`

Lifecycle States (P-05.02):

`RECEIVED → DISCOVERING → QUALIFYING → REHEARSING → GROUNDED`
*Authority:* `AWAITING_AUTHORITY`, `AUTHORIZED`
*Execution:* `EXECUTING → VERIFYING → CERTIFYING → COMPLETE`
*Branches/Terminals:* `BLOCKED`, `RETRY_SCHEDULED`, `COMPENSATING`, `FAILED`, `CANCELLED`.

Exact schemas are frozen in `domain/contracts/change_lifecycle.py`.

## 7. Autonomy policy

- `AUTO_EXECUTE`
- `AUTO_EXECUTE_AND_NOTIFY`
- `REHEARSE_THEN_EXECUTE`
- `HUMAN_AUTHORITY_REQUIRED`
- `BLOCKED`

Product must minimize approval count without weakening authority boundaries.

### 7.1 Binding Autonomy Invariants (P-04.05 / ADR-0014)

1.  Human interaction is exception-based and authority-bound — only in explicitly defined `HUMAN_AUTHORITY` policy slots.
2.  Organizational policy determines autonomy classification (`AUTO_EXECUTE` through `BLOCKED`), not executor convenience. `LIVE_WRITE` is not universally human-gated.
3.  System-owned routing — Change Orchestrator and Capability Passport own all routing, coordination, and delegation.
4.  Bounded retry before escalation — retry, compensation, ShadowLab correction, and alternate agents are preferred before human escalation.
5.  No Phase-0 interview — information is derived from repository evidence, policy, and memory before asking the user.
6.  Waiting-authority concurrency — safe independent work continues while a narrow authority edge waits, where saga-step dependencies permit.
7.  Gemini uncertainty does not create authority — uses validation, retry, or fail-closed instead of human escalation.
8.  Approval Compression is minimal — one bounded card; cannot self-approve or infer from silence.
9.  Trusted cross-session memory reduces repeated questioning without bypassing trust checks.
10. Deterministic facts require no approval — `DETERMINISTIC_CODE` is sovereign.

Full review and evidence: [`docs/AUTONOMY_REVIEW.md`](docs/AUTONOMY_REVIEW.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §12.

## 8. Evidence and fixture separation

ChangeMesh defines four explicit execution/evidence modes (`FIXTURE`, `SIMULATION`, `RECORDED_CLOUD`, `LIVE_WRITE`), which must be visibly labeled (see `docs/MODE_CONTRACT.md`).

*   **No silent fallback:** Adapters execute the requested mode or fail closed.
*   **Mode lock:** The mode is immutable per operation.
*   **Provenance is immutable:** Simulation success does not overwrite a live failure; recorded-cloud replay is not current live execution.

## 9. Architecture-change protocol

Architectural changes require decision-log entry, architecture-memory update, master-plan impact, migration note when contracts change, affected tests, and whole-repo consistency audit.

## 10. Dependency direction invariants (P-04.01)

Provider-specific outer layers depend inward on ChangeMesh domain contracts. Domain contracts never depend outward on providers.

- `domain/contracts/` → Google SDK, ADK, Firestore, PubSub, GitHub, UI, fixtures: **FORBIDDEN**
- Adapters, UI, fixtures → `domain/contracts/`: **REQUIRED** (inward)
- Production code → fixture/test code: **FORBIDDEN**

Adapters are architecturally replaceable: changing a provider adapter (e.g., GitHub → synthetic, Firestore → test double) must not require changes to domain contracts.

Full dependency matrix and package map: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
