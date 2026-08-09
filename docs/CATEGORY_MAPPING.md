# ChangeMesh — Fortified Enterprise Fleet Category Mapping

Mapping status: `VERIFIED`

This verifies requirement-to-architecture mapping only; managed-service implementation/execution states are governed by `AGENT_ENVIRONMENT_AND_API.md`.

To compete in the "Fortified Enterprise Fleet" category, ChangeMesh maps every expectation from the official Devpost rules to a concrete architectural artifact.

> **Path note:** Evidence locations reference planned logical modules or P-04.00 canonical targets. Implementation language is deferred to P-06. See `docs/ARCHITECTURE.md` §3 for the full canonical planned package map.

## Category Requirements Matrix

| Devpost Category Sentence | ChangeMesh Architectural Artifact | Evidence Location |
|---|---|---|
| "Agent Registry (the central repository for publishing, versioning, and discovering enterprise-approved agents)" | Target architecture plans to use the `capability` module to publish its specialized agents (`Impact Scout`, `Policy Guardian`, `Migration Engineer`, etc.) to the Google Cloud Agent Registry. Managed Agent Registry is currently `AVAILABLE / NOT_RUN`. | `capability/` module (planned) |
| "Agent Runtime (for long-running, asynchronous background execution)" | Target architecture plans an `orchestration` module powered by Google ADK (Agent Development Kit), running asynchronously on Agent Runtime/Platform + Cloud Run for supporting services via Pub/Sub events. Agent Runtime is currently `AVAILABLE / NOT_RUN`. | `src/agents/change_orchestrator.py` (routing/coordination), `src/orchestrator/firestore_saga.py` (durable state), and Cloud Run deployment scripts |
| "Memory Bank (for persistent, secure cross-session context over extended timelines)" | Target architecture combines ChangeMesh Memory Trust Layer + Agent Platform Memory Bank. Managed Memory Bank is currently `DEFERRED / NOT_RUN`. | `src/memory/trust_layer.py`, `src/memory/shared_memory_bus.py` |
| "Agent Identity (For zero-trust access control)" | Target architecture combines managed Agent Identity with the planned ChangeMesh Capability Passport; no agent receives unrestricted credentials, relying on bounded identity. Managed Agent Identity is currently `PERMISSION_BLOCKED / NOT_RUN`. | `capability/` module (logical planned target) |
| "Agent Gateway (for unified routing and policy enforcement)" | Target architecture plans Agent Gateway (networkservices) as the network governance layer, with Change Orchestrator (Google ADK) delegating to `Policy Guardian` for deterministic policy checks before execution. Managed Agent Gateway is currently `AVAILABLE / NOT_RUN`. Change Orchestrator and Policy Guardian are separate from the gateway. | `src/agents/change_orchestrator.py` (routing), `src/agents/policy_guardian.py` (policy checks), logical planned integration |
| "Model Armor (inline guardrails to block prompt injection, tool poisoning, and PII leaks)" | Target architecture plans a managed Model Armor integration. Current managed service state is `PERMISSION_BLOCKED / NOT_RUN`. Policy Guardian and structured-output validation remain separate ChangeMesh boundaries and are NOT evidence that Model Armor ran. | `src/agents/policy_guardian.py` (ZK-PRIV-001), `src/core/gemini_structured_output.py` (ZK-VALID-001) |
| "Agent Observability (OpenTelemetry-compliant audit logs and end-to-end reasoning chain traces)" | Target architecture plans an `observability` module wrapping ADK OpenTelemetry -> Cloud Logging/Trace with evidence boundary redaction. Observability is currently `AVAILABLE / NOT_RUN`. | `observability/` module (planned) |

## Conclusion
Every category expectation is explicitly planned and mapped to concrete codebase modules. Generic wording has been eliminated. Evidence locations align with P-04.00 canonical targets and the P-04.01 planned package map.
