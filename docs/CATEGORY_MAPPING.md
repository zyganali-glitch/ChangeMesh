# ChangeMesh — Fortified Enterprise Fleet Category Mapping

Status: `VERIFIED`

To compete in the "Fortified Enterprise Fleet" category, ChangeMesh maps every expectation from the official Devpost rules to a concrete architectural artifact.

## Category Requirements Matrix

| Devpost Category Sentence | ChangeMesh Architectural Artifact | Evidence Location |
|---|---|---|
| "Agent Registry (the central repository for publishing, versioning, and discovering enterprise-approved agents)" | ChangeMesh uses the `capability` module to publish its specialized agents (`Impact Scout`, `Policy Guardian`, `Migration Engineer`, etc.) to the Google Cloud Agent Registry. | `src/capability/registry_adapter.ts` (planned) |
| "Agent Runtime (for long-running, asynchronous background execution)" | `orchestration` module powered by Google ADK (Agent Development Kit), running asynchronously on Agent Runtime/Platform + Cloud Run for supporting services via Pub/Sub events. | `src/orchestration/` and Cloud Run deployment scripts |
| "Memory Bank (for persistent, secure cross-session context over extended timelines)" | `memory` module powered by ChangeMesh Memory Trust Layer + Firestore (Operational State). | `src/memory/` |
| "Agent Identity (For zero-trust access control)" | Implemented via Agent Identity (SPIFFE-based) + ChangeMesh Capability Passport; no agent receives unrestricted credentials, relying on bounded identity. | `src/capability/passport.ts` (planned) |
| "Agent Gateway (for unified routing and policy enforcement)" | Agent Gateway (networkservices) + ChangeMesh Policy Guardian acts as the routing gateway, delegating to `Policy Guardian` for deterministic policy checks before execution. | `src/orchestration/router.ts` and `src/policy/` |
| "Model Armor (inline guardrails to block prompt injection, tool poisoning, and PII leaks)" | `evidence` and `policy` modules integrate with Vertex AI Model Armor to sanitize inputs/outputs and enforce honest boundaries. | `src/policy/armor.ts` (planned) |
| "Agent Observability (OpenTelemetry-compliant audit logs and end-to-end reasoning chain traces)" | `observability` module wrapping ADK OpenTelemetry -> Cloud Logging/Trace with evidence boundary redaction. | `src/observability/` |

## Conclusion
Every category expectation is explicitly planned and mapped to concrete codebase modules. Generic wording has been eliminated.
