# ChangeMesh Handoff State

**Completed:**
- P-00
- P-01
- P-02
- P-02D
- P-03
- P-04.00
- P-04.01
- P-04.02
- P-04.03
- P-04.04
- P-04.05
- P-04
- P-05.01
- P-05.02
- P-05.03
- P-05.04
- P-05.05
- P-05.06
- P-05
- P-06.01
- P-06.02
- P-06.03
- P-06.04
- P-06.05
- P-06
- P-07.01
- P-07.02
- P-07.03
- P-07.04
- P-07.05
- P-07
- P-08.00
- P-08.01
- P-08.02
- P-08.03
- P-08.04
- P-08.05
- P-08
- P-09.01
- P-09.02
- P-09.03
- P-09.04
- P-09.05
- P-09
- P-10.00
- P-10.01
- P-10.02
- P-10.03
- P-10.04
- P-10
- P-11.00
- P-11.01
- P-11.02
- P-11.03
- P-11.04
- P-11.05
- P-11
- P-12.00
- P-12.01
- P-12.02
- P-12.03
- P-12.04
- P-12.05
- P-12
- P-13.00
- P-13.01
- P-13.02
- P-13.03
- P-13.04
- P-13.05
- P-13.06
- P-13.07
- P-13

**Active Phase:**
P-14 (PENDING / NEXT)

**Next Exact Task:**
P-14.00 — Reversibility Gate donor preflight

## Current P-13 State (Phase Complete)

Phase P-13 is `DONE`.
- **P-13.00:** ShadowLab donor preflight verified `CCT-SHADOW-001` (pinned at `9bf86400f074d4c55da54f3be1ae753443a53bc7`) and `MCP-TOOL-001` (pinned at `99824e867b7e3e7f41ba8a011ea3bfdc7863fb79`).
- **P-13.01:** Defined `ShadowScenario`, `InjectedFault`, `FaultType`, `RehearsalOutcome`, and 7 canonical rehearsal scenarios in `src/shadowlab/scenarios.py`.
- **P-13.02:** Implemented deterministic tool doubles in `src/shadowlab/tool_doubles.py` (`SimulatedDatabaseClient`, `SimulatedApiClient`, `SimulatedGitClient`) enforcing strict `ExecutionEvidenceMode.SIMULATION` labeling.
- **P-13.03:** Executed clean migration and 503 transient recovery scenarios with exponential retry backoff.
- **P-13.04:** Executed partial interruption and saga compensation scenario returning database sandbox to clean initial state.
- **P-13.05:** Implemented stale approval rejection and untrusted prompt-injection quarantine rehearsal scenarios.
- **P-13.06:** Implemented simulation evidence digest computation (`compute_simulation_digest`) binding rehearsal outcomes to execution authorization.
- **P-13.07:** Implemented automatic plan correction loops for missing rollbacks and breaking legacy client changes.
- **Evidence:** `tests/test_p13_shadowlab.py` passes 11 dedicated tests. Canonical unit suite passes 1149 tests (1 warning). Zero domain contract mutations or provider SDK leaks. P-14.00 is next.
- **P-12.00:** Capability Passport donor preflight verified `CCT-PASSPORT-001` (pinned at `9bf86400f074d4c55da54f3be1ae753443a53bc7`) and `CLOVER-REG-001` (pinned at `047051df170e70ca986e30eb4a1df8350172e2cf`).
- **P-12.01:** Defined standard demo capability vocabulary (`CapabilityType`) and role requirements (`AgentCapabilityRequirement`) for `impact_scout`, `policy_guardian`, `migration_engineer`, `release_steward` in `src/registry/capabilities.py`.
- **P-12.02:** Implemented `PassportIssuer` and `PassportIssuanceRequest` in `src/registry/passport_issuer.py` requiring non-empty qualification evidence references and prohibiting self-attestation.
- **P-12.03:** Implemented `PassportVerifier` and `PassportValidationResult` in `src/registry/passport_issuer.py` verifying validity, expiry, revocation, revision matching, and required capabilities.
- **P-12.04:** Registered two `migration_engineer` revisions in `src/registry/agent_registry.py` (`rev-1.0.0-sqlite-pg` and `rev-2.0.0-cockroach-distributed`), demonstrating capability-targeted qualification resolution.
- **P-12.05:** Implemented `AgentRegistry` interface and `InMemoryAgentRegistry` in `src/registry/agent_registry.py`.
- **P-12.06:** Implemented `PassportAwareRouter` in `src/registry/passport_router.py` enforcing passport-aware dispatch and fail-closed `UnqualifiedAgentDispatchError`.
- **Evidence:** `tests/test_p12_capability_passport.py` passes 5 dedicated tests. Canonical unit suite passes 1138 tests (1 warning). Zero domain contract mutations or provider SDK leaks. P-13.00 is next.
- **P-11.00:** Memory Trust donor preflight verified `QW-MEM-001` and `QW-BUS-001` pinned at commit `a43b3411856f41a4be9424d11c01a5e637cdc410`.
- **P-11.01:** Validated `MemoryRecord` in `domain/contracts/memory.py` with immutable fields, explicit `DataClassLevel`, and required trust evidence for `TRUSTED` status.
- **P-11.02:** Implemented `MemoryTrustEvaluator` and `EpistemicTrustEvaluation` in `src/memory/trust_layer.py` with 5 deterministic classifications (`ACCEPTED_TRUSTED`, `UNTRUSTED_CONTEXT`, `STALE_EXPIRED`, `CONTRADICTED`, `QUARANTINED`), freshness scoring, and strict separation between retrieval relevance and epistemic authority.
- **P-11.03:** Implemented `MemorySupersessionManager` in `src/memory/supersession.py` linking contradictions and superseding older records without deleting historical records.
- **P-11.04:** Implemented `MemoryQuarantineEngine` in `src/memory/quarantine.py` detecting 5 adversarial prompt-injection vectors and quarantining hostile inputs.
- **P-11.05:** Implemented `MemoryBank` abstract interface and `InMemoryMemoryBank` local adapter in `src/memory/memory_bank.py`.
- **P-11.06:** Implemented `TwoSessionResumeScenario` in `src/memory/two_session_scenario.py` validating cross-session discovery preservation and automatic prompt-injection quarantine.
- **Evidence:** `tests/test_p11_memory_trust.py` passes 5 dedicated tests. Canonical unit test suite passes 1133 tests (1 warning). Zero domain contract mutations or provider SDK leaks. P-12.00 is next.
- **P-10.01 (Hardened):** Applied 5 design fixes (Server Firestore security enforced at backend repository boundary; OCC error ownership isolated from P-09 retry; idempotency key design finalized in P-10.03; native TTL & recursive descendant teardown semantics; large artifact safety boundary).
- **P-10.02:** Implemented canonical state repository contracts and models in `src/orchestrator/state_repository.py`, thread-safe in-memory double in `src/orchestrator/in_memory_repository.py`, and Google Cloud Firestore adapter in `integrations/gcp/firestore_adapter.py`. Enforces monotonic version tokens and CAS updates raising `OptimisticConcurrencyError`.
- **P-10.03:** Implemented `IdempotencyKeyManager` and `IdempotencyIntent` in `src/orchestrator/idempotency.py` across all 6 scopes (`WORKFLOW_STEP`, `BRANCH_INTENT`, `PR_INTENT`, `APPROVAL`, `PASSPORT`, `EXTERNAL_WRITE`), lease reservation with timeout, and exact replay deduplication returning cached execution results without duplicate write emission.
- **P-10.04:** Implemented `SagaCheckpointManager` and `SagaResumeContext` in `src/orchestrator/saga_checkpoint.py` with SHA-256 state digest integrity verification (`compute_checkpoint_digest`), completed task extraction to prevent duplicate execution, pending task sequencing, and next safe action identification.
- **P-10.05:** Implemented `PersistencePrivacyGuard` and `FixtureTeardownManager` in `src/orchestrator/teardown.py` with strict fail-closed rejection of credential field names and free-text secrets, and explicit recursive descendant document teardown verifying zero residual fixture state (`TeardownReport(residual_document_count=0, success=True)`).
- **Evidence:** Dedicated P-10 test suites (`tests/test_p10_02_state_repository.py`, `tests/test_p10_03_idempotency.py`, `tests/test_p10_04_saga_checkpoint.py`, `tests/test_p10_05_teardown_privacy.py`) pass 19 tests. Canonical unit test suite passes 1128 tests (1 warning). Zero domain contract mutations or Google SDK leaks. P-11.00 is next.

## Current P-10.00 State

P-10.00 is `DONE`. Completed saga persistence donor preflight in [`docs/P-10.00_SAGA_PERSISTENCE_DONOR_PREFLIGHT.md`](P-10.00_SAGA_PERSISTENCE_DONOR_PREFLIGHT.md). Inspected five donor components across nine exact allowlisted source/test files (`UIPATH-STATE-001`, `UIPATH-AUTH-001`, `CS-MIG-001`, `CS-PASS-001`, `CS-WRITE-001`) at immutable pinned commits (`dc2267939c2aef0aba2737da65f53352c5cf8fb2` for D-UIPATH, `0dc924db9d82037d2e813548bdee27af5f180889` for D-CONTEXTSEAL). Defined saga source-target mapping, 6-layer idempotency ownership map, compensation/checkpoint persistence boundaries, future-phase non-leakage matrix, provider-neutrality boundaries, security/privacy constraints, and preserved all P-09 event/delivery/retry/causal invariants. Deferred P-10.01 collection names, indexes, retention, and size ceilings as intentionally undecided. Read-only `donor-reuse-auditor` returned `PASS` with 0 blocking findings and 0 warnings. Canonical unit tests pass 1109 items (1 warning). Full suite preserves historical baseline of 1109 passed, 1 warning, 3 fixture errors in `tests/test_gcp_access.py`. Zero product runtime or test code created.

## Current P-09.05 State

P-09.05 is `DONE`. Implemented clean-room causal event timeline in `src/evidence/pubsub_timeline.py` (`CausalEventTimeline`, `CausalTimelineEntry`) based on approved donor component `CCT-FLIGHT-001`. Ingestion allows child/grandchild arrival before parent without premature rejection. Topological causal DAG sequencing via Kahn's algorithm dynamically computes execution depth and orders predecessors before successors regardless of wall-clock timestamp skew, strictly failing closed on missing/unresolved predecessors, causal cycles, self-causation, or parent-child correlation ID mismatch. Causally unlinked concurrent events are deterministically tie-broken by `(timestamp, event_id)`. Exact duplicate replay returns existing entries idempotently; event-ID conflicts, idempotency collisions, and cross-change events fail closed. Payload secret scanning on ingest strictly fails closed and rejects secret-bearing payloads (`scan_payload_for_secrets`), while `redact_mapping` applies structural field masking with `"[REDACTED]"` as defense-in-depth on accepted payloads (REJECT != REDACT). Implemented full canonical JSON round-trip serialization (`to_dict()`, `from_dict()`, `to_json()`) with restart continuity, strict 12-point `from_dict()` schema validation, and deterministic SHA-256 timeline digest hashing (`compute_timeline_digest()`). Verified zero forbidden carry-over (no Codex events, no UI styling, no Google Cloud SDK types in `src/evidence/`). `tests/test_p09_05_pubsub_timeline.py` passes 14 dedicated tests. Complete P-09 suite passes 79 tests. Canonical unit suite passes 1109 tests (1 warning).

## Current P-09.04 State

P-09.04 is `DONE` (Repaired). Implemented canonical local in-memory event bus adapter in `events/local_bus.py` (`LocalEventBus`, `LocalEventPublisher`, `LocalEventConsumer`) fulfilling identical `EventPublisher` and `EventConsumer` protocols, identical wire serialization and secret scanning, and identical duplicate delivery safety via `InMemoryDeliveryState`. Wired `execute_with_retry()` as the single local retry owner across bus subscriber dispatch and consumer message processing (zero nested/stacked retry loops). Enforces sibling handler isolation (handler 1 success is not replayed if handler 2 retries). Failed local subscriber handlers and consumer callbacks return observable `dead_letter_record` on `EventPublishResult` and `EventConsumeResult` with caller-visible metadata (`event_id`, `change_id`, `correlation_id`, `topic_id`, attempt count, failure classification, `human_authority_required == False`, sanitized diagnostic), without marking unaccepted deliveries in `seen_events`. Differentiates transport identity with `transport="LOCAL"`. Preserved the 4 canonical `ExecutionEvidenceMode` values (`FIXTURE`, `SIMULATION`, `RECORDED_CLOUD`, `LIVE_WRITE`), mapping local execution strictly to `SIMULATION` or `FIXTURE` mode and failing closed with `ValueError` if requested to emit `LIVE_WRITE` or `RECORDED_CLOUD` evidence. This guarantees local simulation cannot be mistaken for Google Pub/Sub proof. All exception logging sanitized via `sanitize_error_message(str(e))`. Zero Google SDK dependencies exist in `events/local_bus.py`. Dedicated contract parity suite `tests/test_p09_04_local_event_bus.py` passes 14 tests. Canonical unit suite passes 1109 tests (1 warning).

## Current P-09.03 State

P-09.03 is `DONE` (Repaired). Implemented canonical bounded retry policy and failure classifier (`events/retry.py`) with `EventRetryPolicy` (`max_attempts` in `[1, 10]`, positive finite backoff, deterministic delays) and `classify_failure()`. Differentiates transient retryable failures from deterministic non-retryable errors (malformed JSON, schema version mismatch, extra envelope fields, secret payload, causal conflict). Deterministic invalid errors fail immediately on attempt 1 with zero retries. On terminal exhaustion or deterministic invalid error, execution constructs and stores canonical `DeadLetterEventRecord` and `TerminalFailureHandoff` using deterministic ID derivation (`compute_dead_letter_id`) and thread-safe process-local replay idempotency (`ProcessLocalDeadLetterState`), guaranteeing that replaying the exact same terminal event returns the identical logical handoff without duplicate emission within the retained FIFO bounded capacity window (`max_records >= 1`, eviction of oldest entries). Preserved the authority invariant: `TerminalFailureHandoff.human_authority_required` is strictly `False` (retry exhaustion never manufactures human authority). Preserved the secrecy invariant: credentials, private keys, and API tokens are sanitized from error messages and handoffs. Dedicated failure-injection suite `tests/test_p09_03_retry_dead_letter.py` passes 10 tests. Canonical unit passes 1109 tests (1 warning).

## Current P-09.02 State

P-09.02 is `DONE` (Repaired). Implemented canonical `EventWireMessage` (`events/wire.py`), `EventPublisher`/`EventConsumer` protocols (`events/publisher.py`, `events/consumer.py`), `InMemoryDeliveryState` (`events/delivery_state.py`), and Google Pub/Sub adapters in `integrations/gcp/pubsub_adapter.py` (`GooglePubSubPublisher`, `GooglePubSubConsumer`, `GooglePubSubDeadLetterConsumer`). Pre-dispatch validation guarantees that malformed JSON, unsupported schema versions, missing/extra envelope fields, and secret-bearing payloads fail closed / are rejected immediately. Duplicate delivery safety is verified (callbacks execute at most once per accepted event; duplicate deliveries return `DUPLICATE` without invoking callbacks). Google Pub/Sub dead-letter subscription deliveries are converted to canonical `DeadLetterEventRecord` and `TerminalFailureHandoff` via `GooglePubSubDeadLetterConsumer`. Canonical identity is reconstructed strictly from raw wire payload or trusted transport attributes (`topic_id` included in wire transport attributes); if required identity fields cannot be recovered, execution strictly FAILS CLOSED without fabricating placeholder identities or default topics. Provider delivery attempt is preserved as approximate metadata when supplied; when absent, attempts are recorded as 0 (unknown) with zero manufactured policy counts. Exception logging is completely sanitized via `sanitize_error_message(str(e))` with zero raw `e` logging. Zero Google SDK types leak into domain contracts. The dedicated suite `tests/test_p09_02_pubsub_adapters.py` passes 23 tests. Canonical unit passes 1109 tests (1 warning).

## Current P-09.01 State

P-09.01 is `DONE`. Minimal, versioned (`1.0.0`) canonical topic and subscription topology is defined in `events/topology.py` and exported to declarative manifest `events/topology_manifest.json`. Declared 6 logical topics (`changemesh-lifecycle-v1`, `changemesh-agent-work-v1`, `changemesh-approval-v1`, `changemesh-evidence-v1`, `changemesh-retry-v1`, `changemesh-dead-letter-v1`) and 6 attached subscriptions. Subscriptions route dead letters to `changemesh-dead-letter-v1` (5 attempts) with dead-letter subscription cycle prohibition. Provider dead-letter attempt range [5, 100] enforced. All 16 `ChangeState` values are mapped deterministically (see diagram `docs/diagrams/pubsub_topology.md`). The dedicated suite `tests/test_p09_01_topology.py` passes 18 tests. Canonical unit passes 1109 tests (1 warning).

## Evidence

- P-09.01 topology: `uv run python -m pytest tests/test_p09_01_topology.py -v --tb=short` -> 18 passed.
- P-09.02 adapters: `uv run python -m pytest tests/test_p09_02_pubsub_adapters.py -v --tb=short` -> 23 passed.
- P-09.03 retry: `uv run python -m pytest tests/test_p09_03_retry_dead_letter.py -v --tb=short` -> 10 passed.
- P-09.04 local bus: `uv run python -m pytest tests/test_p09_04_local_event_bus.py -v --tb=short` -> 14 passed.
- P-09.05 causal timeline: `uv run python -m pytest tests/test_p09_05_pubsub_timeline.py -v --tb=short` -> 14 passed.
- Complete P-09: `uv run python -m pytest tests/test_p09_01_topology.py tests/test_p09_02_pubsub_adapters.py tests/test_p09_03_retry_dead_letter.py tests/test_p09_04_local_event_bus.py tests/test_p09_05_pubsub_timeline.py -q` -> 79 passed.
- Canonical unit: `uv run python scripts/cmd.py unit` -> 1109 passed, 1 warning.
- Full suite: `uv run python -m pytest tests/` -> 1109 passed, 1 warning, 3 errors; **FAIL — known historical baseline GCP fixture debt** (`project` fixture in `tests/test_gcp_access.py`).
- Donor manifest lint: `uv run python tools/governance/donor_manifest_lint.py` -> 20 components passed.
- Targeted Ruff, format, mypy, AST model-owner, domain import, secret scan, and `git diff --check`: `PASS`.

## Provenance

CCT-FLIGHT-001 is `VERIFIED` as `CLEAN_ROOM_REIMPLEMENTED` from D-CCT at
immutable SHA `65ee1b72faf9a7202d9166eed43fb671804815a8`, using only
`cli/commands/flight-recorder.js` and `tests/test_codex_review.js`.

## Open Boundaries

- Model Armor remains `PERMISSION_BLOCKED / NOT_RUN`.
- Generic enterprise DLP, universal PII discovery, cloud proxy filtering, full external adapter mode execution, and production provider-pricing calibration remain `NOT_RUN` or `PLANNED` under their owning phases.
- Full repository test status remains the historical `FAIL` above and must not be relabeled `PASS`.
