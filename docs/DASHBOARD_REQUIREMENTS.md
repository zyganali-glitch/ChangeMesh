# ChangeMesh Demo Dashboard Requirements

Status: `PLANNED`

To prove the metrics defined in `docs/OUTCOME_CONTRACT.md` to the hackathon judges, the ChangeMesh UI/CLI must explicitly visualize the following:

## 1. The Saga Timeline (Time-to-Safe-Draft-PR & Autonomous Steps)
- **Visual:** A Gantt-like timeline or vertical stepper.
- **Data:** Must show asynchronous agent tasks (Impact Scout, Migration Engineer) executing without human intervention.
- **Metric:** The UI must display the total elapsed time from "Goal Accepted" to "Draft PR Created" (target: < 5 minutes).

## 2. The Approval Compression Card (Human Touches)
- **Visual:** A single, dense decision card (Reversibility Gate).
- **Data:** Must summarize what was done, what was simulated, and what requires the single human click.
- **Metric:** Must explicitly state: "5 standard PR/Sync reviews compressed into 1 irreducible decision."

## 3. The ShadowLab Recovery Event (Recovery Behavior)
- **Visual:** An alert/log entry in the timeline showing a failure and a resumption.
- **Data:** E.g., "GitHub API 503 Detected -> Resuming from Memory Bank."
- **Metric:** Proves the transaction is durable.

## 4. The Change Evidence Passport (Evidence Completeness)
- **Visual:** A structured JSON or markdown view of the final crypto-hashed passport.
- **Data:** Must show links to rehearsal traces, memory references, and the human approval signature.

## 5. Causal Event Timeline Integration (P-09.05 IMPLEMENTED)
- **Contract Source:** `src/evidence/pubsub_timeline.py` (`CausalEventTimeline`, `CausalTimelineEntry`).
- **Ordering Guarantee:** Strictly topologically ordered by causal metadata (`causation_id`), ensuring cause precedes effect regardless of wall-clock skew or arrival sequence. Concurrent independent events are tie-broken deterministically by `(timestamp, event_id)`.
- **Integrity & Tamper Protection:** Computes deterministic SHA-256 timeline digest over canonical JSON bytes.
- **Privacy Guarantee:** Payloads are structurally sanitized on ingest using `redact_mapping` with `"[REDACTED]"`.
- **Export Formats:** Full JSON round-trip (`to_dict()`, `from_dict()`, `to_json()`) providing clean DAG depth, producer revision provenance, and topic routing history for dashboard renderers and passport binding.
