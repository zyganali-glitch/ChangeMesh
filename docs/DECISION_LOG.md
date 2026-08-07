# ChangeMesh Decision Log

## ADR-0001 — Frozen project charter; no generic Phase-0
- Date: 2026-08-06
- Status: Accepted
- Decision: Agreed ChangeMesh charter replaces Universal Agent OS interactive Phase-0.
- Reason: Repeating discovery wastes time and can introduce drift.
- Consequence: Agents may ask only minimal blocking questions.

## ADR-0002 — ADK is product runtime
- Date: 2026-08-06
- Status: Accepted
- Decision: Google ADK runs product agents. Antigravity is development environment.
- Reason: Competition requires a real Gemini/Google Cloud autonomous product; development-tool behavior is not runtime proof.

## ADR-0003 — Autonomous by default, human-on-the-loop
- Date: 2026-08-06
- Status: Accepted
- Decision: Human authority only for irreversible, sensitive, privilege-expanding, or policy-defined actions.
- Reason: Reduce friction while meeting enterprise governance.

## ADR-0004 — Initial product wedge
- Date: 2026-08-06
- Status: Accepted
- Decision: Demonstrate high-risk schema/API change coordination using `customer_id → account_id`.
- Reason: Concrete cross-system impact, strong demo, credible product path.

## Template

### ADR-NNNN — Title
- Date:
- Status: Proposed | Accepted | Superseded | Rejected
- Context:
- Decision:
- Alternatives:
- Consequences:
- Evidence:
- Supersedes:

## ADR-0005 — Freeze Devpost Requirements
- Date: 2026-08-07
- Status: Accepted
- Context: Competition details fetched from Devpost.
- Decision: Confirmed requirements: Gemini, ADK, Google Cloud, Fortified Enterprise Fleet track, 2026-08-31 20:00 EDT deadline.
- Consequences: Architecture must strictly use ADK and Gemini API/Vertex AI. No deviation allowed.

## ADR-0006 — Fortified Enterprise Fleet Mapping
- Date: 2026-08-07
- Status: Accepted
- Context: Requirement to map every category expectation to a concrete architectural artifact (P-01.04).
- Decision: Mapped Agent Registry to `capability` module, Agent Runtime to `orchestration`/ADK on Cloud Run, Memory Bank to `memory`/Firestore, Agent Identity to passports, Agent Gateway to `orchestration` router, Model Armor to `policy` boundaries, and Agent Observability to OpenTelemetry traces.
- Consequences: All future development must strictly align with these mappings. Generic wording is eliminated.
- Evidence: `docs/CATEGORY_MAPPING.md`

### DECISION-20260807-01: Google Cloud Region Selection
- Date/time: 2026-08-07 11:38 GMT+3
- Active task: P-02.01
- Decision: Use europe-west3 (Frankfurt) for Google Cloud resources.
- Rationale: User is located in Turkey; europe-west3 provides optimal low latency and broad service availability.
- Status: ACTIVE

### DECISION-20260807-03: Vertex AI SDK and Region Selection
- Date/time: 2026-08-07 13:12 GMT+3
- Active task: P-02.02
- Decision: Use `google-genai` SDK and the `global` region for Vertex AI to access `gemini-3.6-flash`.
- Rationale: The legacy `vertexai.generative_models` SDK is deprecated (removed June 2026). The `us-central1` and `europe-west3` Vertex AI endpoints returned 404 for Gemini 3.5+ until UI initialization. The UI provisioned the `gemini-3.6-flash` model in the `global` region which correctly resolves via the new SDK.
- Status: ACTIVE
