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
- Decision: Mapped Agent Registry to `capability` module, Agent Runtime to Agent Runtime/Platform + Cloud Run for supporting services, Memory Bank to ChangeMesh Memory Trust Layer + Agent Platform Memory Bank, Agent Identity to Agent Identity (SPIFFE-based) + ChangeMesh Capability Passport, Agent Gateway to Agent Gateway (networkservices), Change Orchestrator to Google ADK for saga state, Model Armor to `policy` boundaries, and Agent Observability to ADK OpenTelemetry -> Cloud Logging/Trace.
- Consequences: All future development must strictly align with these mappings. Generic wording is eliminated.
- Evidence: `docs/CATEGORY_MAPPING.md`

### DECISION-20260807-01: Google Cloud Region Selection
- Date/time: 2026-08-07 11:38 GMT+3
- Active task: P-02.01
- Decision: Use europe-west3 (Frankfurt) for Google Cloud resources.
- Rationale: User is located in Turkey; europe-west3 provides optimal low latency and broad service availability.
- Status: ACTIVE

## ADR-0007 — MVP Managed-Service Tier and Fallbacks
- Date: 2026-08-07
- Status: Accepted
- Context: P-02.06 required choosing the MVP tier based on real service access and documenting fallbacks for any blocked components.
- Decision: Use real Google Cloud managed services for Cloud Run, Firestore, Pub/Sub, Agent Runtime (AVAILABLE), Agent Registry (AVAILABLE), Agent Gateway (AVAILABLE) and Observability (AVAILABLE). Agent Identity and Model Armor are PERMISSION_BLOCKED. Memory Bank is DEFERRED.
- Alternatives: Local deterministic adapters would have been used for any other unavailable services.
- Consequences: All available components target real GCP infrastructure. Blocked or deferred components (Identity, Armor, Memory Bank) will use local adapters labeled `LOCAL_FIXTURE` or `ADK_ORCHESTRATOR` until access is granted.
- Evidence: `docs/P-02.04_EVIDENCE.md` and `docs/P-02.05_EVIDENCE.md` confirm Application Default Credentials (ADC) is configured, successful execution, and accurate statuses for GCP access.

## ADR-0008 — Product Buyer and Initial Wedge
- Date: 2026-08-07
- Status: Accepted
- Context: P-03.01 required defining the primary buyer, operator, affected teams, and initial wedge.
- Decision: Primary buyer is VP of Engineering / CTO. Operator is Senior Staff / Platform Engineer. Initial wedge is high-risk schema and API changes (e.g., `customer_id` to `account_id`). Generic platform sprawl is rejected.
- Consequences: All marketing, UI, and demo efforts will focus exclusively on the schema change use case and appeal to platform engineering leadership.
- Evidence: `docs/PRODUCT_BRIEF.md`
### DECISION-20260807-03: Vertex AI SDK and Region Selection
- Date/time: 2026-08-07 13:12 GMT+3
- Active task: P-02.02
- Decision: Use `google-genai` SDK and the `global` region for Vertex AI to access `gemini-3.6-flash`.
- Rationale: The legacy `vertexai.generative_models` SDK is deprecated (removed June 2026). The `us-central1` and `europe-west3` Vertex AI endpoints returned 404 for Gemini 3.5+ until UI initialization. The UI provisioned the `gemini-3.6-flash` model in the `global` region which correctly resolves via the new SDK.
- Status: ACTIVE


## ADR-0009 — Architectural Invariants and Rejected Alternatives (P-04.00)
- Date: 2026-08-09
- Status: Accepted
- Context: P-04.00 Architecture donor preflight evaluated D-UAOS, D-UIPATH, D-CCT, D-ZEROKIT, and D-CONTEXTSEAL invariants.
- Decision: Architecture/authority invariants mapped to specific target components. Canonical source-to-target mapping policy established; secondary consumers are distinguished from the canonical target. Conflicts across donors are resolved into a single ChangeMesh authority. 
- Alternatives:
    - Porting UiPath orchestration runtime (Rejected: Incompatible with Google-native ADK + Cloud Run backbone, Google ADK orchestration ownership established).
    - GPT-5.6 / Codex / OpenAI runtime (Rejected: Mandate Gemini 3.5+ via ADK).
    - Unrestricted / untrusted memory (Rejected: Adopting rigid UAOS four-pillar memory architecture with strict trust boundaries).
    - Provider-specific target leakage (Rejected: Must strictly enforce provider-agnostic domain interfaces).
- Consequences: 
    - Deterministic fact authority is strictly separated from the Gemini semantic advisory boundary.
    - Human authority boundaries are clearly defined (exception-only compression).
    - Google ADK owns orchestration without scattered runtime leakage.
    - Enforces strict adherence to ChangeMesh product constraints while borrowing proven invariants from donors.

## ADR-0010 — Provider-neutral domain contracts and inward dependency direction
- Date: 2026-08-09
- Status: Accepted
- Context: P-04.01 established component architecture with explicit dependency directions. The question was whether domain contracts should carry Google SDK types (Firestore, PubSub, ADK, Vertex) for convenience or remain provider-neutral.
- Decision: Domain contracts (`domain/contracts/`) must never depend outward on Google SDK, ADK, Firestore SDK, PubSub SDK, GitHub SDK, UI frameworks, or fixture/test code. Provider-specific outer layers (adapters, UI, fixtures) depend inward on domain contracts. Google-native runtime (ADK + Gemini + Google Cloud) is preserved as the product runtime — provider independence means domain types do not carry provider SDK types, not that Google is removed. Adapters are architecturally replaceable: changing a provider adapter must not require changes to domain contracts.
- Alternatives:
    - Direct SDK coupling in domain types (Rejected: would prevent testability, create provider lock-in at the domain level, and violate clean architecture)
    - Full provider abstraction removing all Google specificity (Rejected: product is Google-native per competition requirements and product charter)
- Consequences:
    - P-04.00 canonical component targets are preserved without modification.
    - All implementation phases (P-05+) must validate that domain contracts carry no provider SDK imports.
    - Adapters implement domain port interfaces and remain swappable.
    - Production runtime never imports fixture/test code.
- Evidence: `docs/ARCHITECTURE.md` §3 (Package Map), §4 (Dependency Matrix), §5 (Provider-Neutral Domain Boundary), §6 (Adapter Replaceability)

## ADR-0011 — Authority segregation and non-overwrite model
- Date: 2026-08-09
- Status: Accepted
- Context: P-04.02 required defining which entity owns which decisions to prevent model hallucinations from bypassing policy, or humans from bypassing hard rules.
- Decision: Establish four distinct authority classes (Deterministic Code, Gemini Semantic Judgment, Organizational Policy, Human Authority). One authority per decision type. Deterministic facts cannot be overwritten by Gemini/human. Organizational policy defines normative permissions. Human authority operates only within policy-defined slots. Executors cannot self-authorize. Unknown/duplicate authority fails closed.
- Alternatives:
    - Shared/ambiguous authority (Rejected: leads to unpredictable override behavior).
    - Gemini as fact authority (Rejected: models cannot own deterministic execution truth).
    - Human omnipotent override (Rejected: breaks enterprise compliance rules).
    - Orchestrator as global authority (Rejected: Orchestrator coordinates, doesn't own facts).
    - Executor self-authorization (Rejected: violates separation of duties).
- Consequences:
    - Clear boundaries for Approval Compression and Policy Guardian.
    - Architecture requires distinct modules for facts, semantic assessments, and policies.
- Evidence: `docs/AUTHORITY_MAP.md`
