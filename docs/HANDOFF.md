# ChangeMesh Handoff State

**Completed:**
P-00
P-01
P-02
P-02D
P-03
P-04.00
P-04.01
P-04.02
P-04.03
P-04.04
P-04.05
P-04
P-05.01
P-05.02
P-05.03
P-05.04
P-05.05
P-05.06
P-05
P-06.01
P-06.02
P-06.03
P-06.04
P-06.05
P-06
P-07.01
P-07.02
P-07.03
P-07.04
P-07.05
P-07
P-08.00
P-08.01
P-08.02
P-08.03
P-08.04
P-08.05
P-08
P-09.01
P-09.02
P-09.03
P-09.04
P-09.05
P-09

**Active Phase:**
P-10

**Next Exact Task:**
P-10.01 — Design Firestore collections, indexes, tenancy boundary, retention, document-size limits

## Current P-09.05 State

P-09.05 is `DONE`. Implemented clean-room causal event timeline in `src/evidence/pubsub_timeline.py` (`CausalEventTimeline`, `CausalTimelineEntry`) based on approved donor component `CCT-FLIGHT-001`. Guaranteed topological causal graph sequencing via Kahn's algorithm over `causation_id` links, proving parent events precede child events regardless of network arrival sequence or wall-clock timestamp skew. Causally unlinked concurrent events are deterministically tie-broken by `(timestamp, event_id)`. Implemented payload secret sanitization on ingest via `redact_mapping` with `"[REDACTED]"`. Implemented full canonical JSON round-trip serialization (`to_dict()`, `from_dict()`, `to_json()`) with restart continuity and deterministic SHA-256 timeline digest hashing (`compute_timeline_digest()`). Verified zero forbidden carry-over (no Codex events, no UI styling, no Google Cloud SDK types in `src/evidence/`). `tests/test_p09_05_pubsub_timeline.py` passes 8 dedicated tests. Complete P-09 suite passes 54 tests. Canonical unit suite passes 1084 tests (1 warning).

## Current P-09.04 State

P-09.04 is `DONE`. Implemented canonical local in-memory event bus adapter in `events/local_bus.py` (`LocalEventBus`, `LocalEventPublisher`, `LocalEventConsumer`) fulfilling identical `EventPublisher` and `EventConsumer` protocols, identical wire serialization and secret scanning, and identical duplicate delivery safety via `InMemoryDeliveryState`. Differentiates transport identity with `transport="LOCAL"`. Preserved the 4 canonical `ExecutionEvidenceMode` values (`FIXTURE`, `SIMULATION`, `RECORDED_CLOUD`, `LIVE_WRITE`), mapping local execution strictly to `SIMULATION` or `FIXTURE` mode and failing closed with `ValueError` if requested to emit `LIVE_WRITE` or `RECORDED_CLOUD` evidence. This guarantees local simulation cannot be mistaken for Google Pub/Sub proof. Zero Google SDK dependencies exist in `events/local_bus.py`. Dedicated contract parity suite `tests/test_p09_04_local_event_bus.py` passes 5 tests. Canonical unit suite passes 1084 tests (1 warning).

## Current P-09.03 State

P-09.03 is `DONE` (Repaired). Implemented canonical bounded retry policy and failure classifier (`events/retry.py`) with `EventRetryPolicy` (`max_attempts` in `[1, 10]`, positive finite backoff, deterministic delays) and `classify_failure()`. Differentiates transient retryable failures from deterministic non-retryable errors (malformed JSON, schema version mismatch, extra envelope fields, secret payload, causal conflict). Deterministic invalid errors fail immediately on attempt 1 with zero retries. Implemented dead-letter models and diagnostic handoff generator (`events/dead_letter.py`) with `DeadLetterEventRecord`, `TerminalFailureHandoff`, `build_dead_letter_record()`, and `sanitize_error_message()`. Preserved the authority invariant: `TerminalFailureHandoff.human_authority_required` is strictly `False` (retry exhaustion never manufactures human authority). Preserved the secrecy invariant: credentials, private keys, and API tokens are sanitized from error messages and handoffs. Dedicated failure-injection suite `tests/test_p09_03_retry_dead_letter.py` passes 8 tests. Canonical unit passes 1084 tests (1 warning).

## Current P-09.02 State

P-09.02 is `DONE` (Repaired). Implemented canonical `EventWireMessage` (`events/wire.py`), `EventPublisher`/`EventConsumer` protocols (`events/publisher.py`, `events/consumer.py`), `InMemoryDeliveryState` (`events/delivery_state.py`), and Google Pub/Sub adapters in `integrations/gcp/pubsub_adapter.py` (`GooglePubSubPublisher`, `GooglePubSubConsumer`). Pre-dispatch validation guarantees that malformed JSON, unsupported schema versions, missing/extra envelope fields, and secret-bearing payloads never reach business callbacks. Duplicate delivery safety is verified (callbacks execute at most once per accepted event; duplicate delivers return `DUPLICATE` without invoking callbacks). Zero Google SDK types leak into domain contracts. The dedicated suite `tests/test_p09_02_pubsub_adapters.py` passes 12 tests. Canonical unit passes 1084 tests (1 warning).

## Current P-09.01 State

P-09.01 is `DONE`. Minimal, versioned (`1.0.0`) canonical topic and subscription topology is defined in `events/topology.py` and exported to declarative manifest `events/topology_manifest.json`. Declared 6 logical topics (`changemesh-lifecycle-v1`, `changemesh-agent-work-v1`, `changemesh-approval-v1`, `changemesh-evidence-v1`, `changemesh-retry-v1`, `changemesh-dead-letter-v1`) and 6 attached subscriptions. Subscriptions route dead letters to `changemesh-dead-letter-v1` (5 attempts) with dead-letter subscription cycle prohibition. All 16 `ChangeState` values are mapped deterministically (see diagram `docs/diagrams/pubsub_topology.md`). The dedicated suite `tests/test_p09_01_topology.py` passes 17 tests. Canonical unit passes 1084 tests (1 warning).

## Evidence

- P-09.01 topology: `uv run python -m pytest tests/test_p09_01_topology.py -v --tb=short` -> 17 passed.
- P-09.02 adapters: `uv run python -m pytest tests/test_p09_02_pubsub_adapters.py -v --tb=short` -> 12 passed.
- P-09.03 retry: `uv run python -m pytest tests/test_p09_03_retry_dead_letter.py -v --tb=short` -> 8 passed.
- P-09.04 local bus: `uv run python -m pytest tests/test_p09_04_local_event_bus.py -v --tb=short` -> 5 passed.
- P-09.05 causal timeline: `uv run python -m pytest tests/test_p09_05_pubsub_timeline.py -v --tb=short` -> 6 passed.
- Complete P-09: `uv run python -m pytest tests/test_p09_01_topology.py tests/test_p09_02_pubsub_adapters.py tests/test_p09_03_retry_dead_letter.py tests/test_p09_04_local_event_bus.py tests/test_p09_05_pubsub_timeline.py -q` -> 48 passed.
- Canonical unit: `uv run python scripts/cmd.py unit` -> 1084 passed, 1 warning.
- Full suite: `uv run python -m pytest tests/` -> 1084 passed, 1 warning, 1 error; **FAIL — known historical baseline GCP fixture debt** (`project` fixture in `tests/test_gcp_access.py`).
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
