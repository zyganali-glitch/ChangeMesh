# ChangeMesh — Fortified Enterprise Fleet Category Mapping

Status: `VERIFIED`

To compete in the "Fortified Enterprise Fleet" category, ChangeMesh maps every expectation from the official Devpost rules to a concrete architectural artifact.

> **Path note:** Evidence locations reference planned logical modules or P-04.00 canonical targets. Implementation language is deferred to P-06. See `docs/ARCHITECTURE.md` §3 for the full canonical planned package map.

## Category Requirements Matrix

| Devpost Category Sentence | ChangeMesh Architectural Artifact | Evidence Location |
|---|---|---|
| "Agent Registry (the central repository for publishing, versioning, and discovering enterprise-approved agents)" | ChangeMesh uses the `capability` module to publish its specialized agents (`Impact Scout`, `Policy Guardian`, `Migration Engineer`, etc.) to the Google Cloud Agent Registry. | `capability/` module (planned) |
| "Agent Runtime (for long-running, asynchronous background execution)" | `orchestration` module powered by Google ADK (Agent Development Kit), running asynchronously on Agent Runtime/Platform + Cloud Run for supporting services via Pub/Sub events. | `src/agents/change_orchestrator.py` (routing/coordination), `src/orchestrator/firestore_saga.py` (durable state), and Cloud Run deployment scripts |
| "Memory Bank (for persistent, secure cross-session context over extended timelines)" | `memory` module powered by ChangeMesh Memory Trust Layer + Agent Platform Memory Bank. | `src/memory/trust_layer.py`, `src/memory/shared_memory_bus.py` |
| "Agent Identity (For zero-trust access control)" | Implemented via Agent Identity (SPIFFE-based) + ChangeMesh Capability Passport; no agent receives unrestricted credentials, relying on bounded identity. | `src/evidence/change_passport.py` (CS-PASS-001), `capability/` module |
| "Agent Gateway (for unified routing and policy enforcement)" | Agent Gateway (networkservices) acts as the network governance layer, with Change Orchestrator (Google ADK) delegating to `Policy Guardian` for deterministic policy checks before execution. | `src/agents/change_orchestrator.py` (routing), `src/agents/policy_guardian.py` (policy checks) |
| "Model Armor (inline guardrails to block prompt injection, tool poisoning, and PII leaks)" | `evidence` and `policy` modules integrate with Vertex AI Model Armor to sanitize inputs/outputs and enforce honest boundaries. | `src/agents/policy_guardian.py` (ZK-PRIV-001), `src/core/gemini_structured_output.py` (ZK-VALID-001) |
| "Agent Observability (OpenTelemetry-compliant audit logs and end-to-end reasoning chain traces)" | `observability` module wrapping ADK OpenTelemetry -> Cloud Logging/Trace with evidence boundary redaction. | `observability/` module (planned) |

## Conclusion
Every category expectation is explicitly planned and mapped to concrete codebase modules. Generic wording has been eliminated. Evidence locations align with P-04.00 canonical targets and the P-04.01 planned package map.
