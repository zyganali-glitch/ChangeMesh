# ChangeMesh Judging Map

Status: `IN_PROGRESS (P-08 Phase Closure Repaired & Verified)`

| Requirement / concern | Planned evidence | Current state |
|---|---|---|
| Gemini 3.5+ | exact model config and sanitized trace | `LOCAL_BOUNDED_CLIENT_VERIFIED` (`BoundedGeminiClient` in `src/core/gemini_client.py` with `gemini-3.6-flash`, timeouts, retries, safety settings, non-secret telemetry, budget evaluation) |
| Google agent framework | ADK source/runtime trace | `LOCAL_ADK_VERIFIED` (P-07.01/P-07.02 local ADK agent fleet definitions and in-memory Runner execution verified; cloud deployment `NOT_RUN`) |
| Google Cloud | Cloud Run + Firestore + Pub/Sub | `NOT_RUN` (Local ADC and managed service availability verified in P-02; runtime integration in P-09/P-10/P-28) |
| Autonomous background work | async event timeline and recovery | `NOT_RUN` (Owning phase P-09 Pub/Sub backbone pending) |
| Complex workflow | end-to-end schema-change saga | `NOT_RUN` (Owning phase P-20 saga execution pending) |
| Cross-session context | trusted memory resume | `NOT_RUN` (Owning phase P-11 memory trust layer pending) |
| Agent discovery | registry/capability selection | `NOT_RUN` (Owning phase P-12 capability passport runtime pending) |
| Security/governance | identity/gateway/model-armor or honest boundary, plus four-lane authority map | `LOCAL_BOUNDARIES_VERIFIED / CLOUD_NOT_RUN` (Local 4-lane authority map, ZK-PRIV-001 Policy Guardian pre-SDK privacy gate, and CCT-SEM-001 blind semantic audit fact isolation verified; cloud Agent Identity, Agent Gateway, and Model Armor remain `PERMISSION_BLOCKED / NOT_RUN`) |
| Observability | correlated trace | `LOCAL_TELEMETRY_VERIFIED / CLOUD_NOT_RUN` (Local non-secret `ModelCallTelemetry`, safe correlation IDs, and metrics artifact export verified; OpenTelemetry -> Cloud Logging/Trace deferred to P-22) |
| Real action | GitHub draft PR | `NOT_RUN` (Owning phase P-19/P-23 GitHub adapter pending) |
| Reduced friction | Approval Compression metrics, human-on-the-loop exception path | `NOT_RUN` (Owning phase P-14 approval compression pending) |
| Reproducibility | clean-checkout setup/test | `LOCAL_VERIFIED` (P-06.02 reproducible dependency lockfile and P-06.05 clean-checkout verification passed) |

## Fortified Enterprise Fleet Category Mapping
Please refer to [`CATEGORY_MAPPING.md`](CATEGORY_MAPPING.md) for the exact architectural mapping of each track requirement (Registry, Runtime, Memory, Identity, Gateway, Armor, Observability).

## Outcome Metrics Mapping
The planned evidence strictly aligns with the measurable success metrics defined in [`OUTCOME_CONTRACT.md`](OUTCOME_CONTRACT.md) (Human touches compressed, Autonomous steps, Recovery behavior, Evidence completeness, Time-to-safe-draft-PR).
