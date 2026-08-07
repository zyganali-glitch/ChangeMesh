# ChangeMesh Judging Map

Status: `PLANNED`

| Requirement / concern | Planned evidence | Current state |
|---|---|---|
| Gemini 3.5+ | exact model config and sanitized trace | `NOT_RUN` |
| Google agent framework | ADK source/runtime trace | `NOT_RUN` |
| Google Cloud | Cloud Run + Firestore + Pub/Sub | `VERIFIED` |
| Autonomous background work | async event timeline and recovery | `NOT_RUN` |
| Complex workflow | end-to-end schema-change saga | `NOT_RUN` |
| Cross-session context | trusted memory resume | `VERIFIED` |
| Agent discovery | registry/capability selection | `VERIFIED` |
| Security/governance | identity/gateway/model-armor or honest boundary | `VERIFIED` |
| Observability | correlated trace | `NOT_RUN` |
| Real action | GitHub draft PR | `NOT_RUN` |
| Reduced friction | Approval Compression metrics | `NOT_RUN` |
| Reproducibility | clean-checkout setup/test | `NOT_RUN` |

## Fortified Enterprise Fleet Category Mapping
Please refer to [`CATEGORY_MAPPING.md`](CATEGORY_MAPPING.md) for the exact architectural mapping of each track requirement (Registry, Runtime, Memory, Identity, Gateway, Armor, Observability).

## Outcome Metrics Mapping
The planned evidence strictly aligns with the measurable success metrics defined in [`OUTCOME_CONTRACT.md`](OUTCOME_CONTRACT.md) (Human touches compressed, Autonomous steps, Recovery behavior, Evidence completeness, Time-to-safe-draft-PR).
