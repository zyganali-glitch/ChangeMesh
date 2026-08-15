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

## ADR-0012 — Zero-trust boundary and credential-isolation model
- Date: 2026-08-09
- Status: Accepted
- Context: P-04.03 required explicitly defining data flows and credential handling to prevent subagents from confused-deputy attacks, protect model contexts from prompt injections, and prevent secret exposure on public UIs.
- Decision: Adopt a zero-trust architecture. External inputs (GitHub, tools, metadata) are untrusted data, not system instructions. Credentials exist solely at adapter boundaries and never propagate to agents, models, memory, evidence, or public UI. Agent and subagent delegation must be strictly bounded. Boundary crossings do not alter authority classes.
- Alternatives:
    - Forwarding credentials through agent prompts (Rejected: high exfiltration risk).
    - Trusting repository instructions (Rejected: prompt-injection vector).
    - Subagent inheriting unrestricted parent privileges (Rejected: violates least privilege).
    - Public UI holding live-write credentials (Rejected: exposes system to hostile edge).
- Consequences:
    - Development must use ADC locally and Workload Identity on Google Cloud.
    - All adapters must sanitize payloads before crossing the boundary inward.
    - Public Judge UI is restricted to sanitized, read-only artifacts.
- Evidence: `docs/THREAT_MODEL.md`

## ADR-0013 — Explicit execution-mode provenance and no-silent-fallback policy
- Date: 2026-08-09
- Status: Accepted
- Context: P-04.04 required defining fixture, simulation, recorded-cloud, and live-write boundaries to ensure public evidence honesty and reproducibility.
- Decision: ChangeMesh recognizes four explicit execution/evidence modes (`FIXTURE`, `SIMULATION`, `RECORDED_CLOUD`, `LIVE_WRITE`). Operation mode is explicitly selected by policy/caller, and adapters are mode-locked (execute requested mode or fail closed). Silent adapter fallback is strictly forbidden. Any mode change requires a new explicit operation and evidence record. Public mode visibility is mandatory in all judge/operator surfaces.
- Alternatives:
    - Automatic live→simulation fallback (Rejected: causes silent loss of real-execution truth).
    - Simulation presented as live (Rejected: dishonest claim).
    - Recorded-cloud presented as current-live (Rejected: dishonest claim).
    - Implicit adapter-selected mode (Rejected: orchestrator/policy must explicitly know execution boundary).
- Consequences: Evidence state (`PASS`/`FAIL`) cannot erase mode provenance. All components must ensure mode labels survive to the Change Passport and dashboard. Live writes remain credential-isolated and do not inherently require human approval unless defined by policy.
- Evidence: `docs/MODE_CONTRACT.md`

## ADR-0014 — Autonomy and friction model freeze
- Date: 2026-08-11
- Status: Accepted
- Context: P-04.05 required a repository-wide architecture review to ensure no unnecessary synchronous approval, interview, or manual routing remained, while preserving legitimate authority, safety, evidence, and trust boundaries.
- Decision: Freeze the autonomy and friction model with these binding invariants: (1) human interaction is exception-based and authority-bound — only in explicitly defined `HUMAN_AUTHORITY` policy slots; (2) organizational policy determines autonomy classification, not executor convenience — `LIVE_WRITE` is not universally human-gated; (3) the Change Orchestrator and Capability Passport system own routing, not humans; (4) bounded retry, compensation, ShadowLab correction, and fail-closed behavior are preferred before human escalation; (5) no Phase-0 interview — information is derived from repository evidence, policy, and memory before asking the user; (6) safe independent work may continue while a narrow authority edge waits, where saga-step dependencies permit; (7) Gemini uncertainty does not create a human gate — it uses validation, retry, or fail-closed; (8) Approval Compression is minimal and cannot self-approve or infer from silence; (9) trusted cross-session memory reduces repeated questioning without bypassing trust checks; (10) deterministic facts require no approval.
- Alternatives:
    - Universal human approval for all external writes (Rejected: contradicts `LIVE_WRITE` policy-determined autonomy and blocks autonomous reversible demo work).
    - Manual agent routing by operator (Rejected: Orchestrator owns routing per P-04.01 architecture).
    - Gemini uncertainty triggers human approval (Rejected: model uncertainty is not authority; use deterministic validation or fail closed).
    - Freeze all work while any authority decision is pending (Rejected: unnecessarily blocks safe independent saga edges).
- Consequences: All subsequent implementation phases (P-05+) must comply with these autonomy invariants. Adding human approval where policy, rehearsal, and reversibility permit autonomous work violates IL-19 and this ADR.
- Evidence: `docs/AUTONOMY_REVIEW.md`, `docs/ARCHITECTURE.md` §12

## ADR-0015 — Language and Runtime Version Pinning and Repository Structure Freeze
- Date: 2026-08-15
- Status: Accepted
- Context: Micro-task P-06.01 requires selecting exact language and runtime versions and freezing the repository structure based on feasibility evidence. Previously, `AGENT_ENVIRONMENT_AND_API.md` marked the implementation stack, Python version, and Node version as `NOT_DECIDED`.
- Decision:
    1. **Language and Runtime:** Python is selected as the sole product backend and agent runtime language, pinned to exact patch version `3.13.5`.
    2. **Node Runtime Requirement:** Node.js is determined to be `NOT_REQUIRED`. The operator and judge dashboard in `web/` will use vanilla HTML5/CSS3/JavaScript without a Node runtime, bundler, or build toolchain, served directly via Python backend or static hosting. No `.nvmrc`, `package.json`, or npm toolchain is introduced.
    3. **Version Marker File:** A minimal machine-readable version marker file `.python-version` containing `3.13.5` is created in the repository root for local tooling and Google Cloud Buildpack version detection.
    4. **Repository Structure:** The repository structure is frozen strictly to the canonical planned package map in `docs/ARCHITECTURE.md` §3.
        - *Current Physical Structure:* `domain/contracts/` (implemented provider-neutral schemas and conventions), `tests/` (unit and contract test suites), `docs/` (architecture, ADRs, policies), `plans/` (master roadmap), `fixtures/` (test data doubles), `.agents/` (Antigravity governance), and root governance documents.
        - *Frozen Target Structure:* `api/` (API entrypoint), `src/agents/` (Google ADK agents), `src/git/` (Impact Scout), `src/evidence/` (Evidence ledger, timeline, passport), `src/orchestrator/` (Firestore saga state persistence), `src/auth/` (Approval compression), `src/policy/` (ShadowLab auth), `src/core/` (Gemini structured output deserialization), `src/audit/` (Claim audit), `src/memory/` (Memory trust layer), `src/connectors/` (Tool boundary), `integrations/github/` (GitHub adapter), `integrations/metadata/` (Metadata graph adapter), `integrations/gcp/` (Google Cloud adapter), `observability/` (OpenTelemetry/Cloud Logging), `web/` (browser-native HTML5/CSS3/JavaScript dashboard UI, no Node build toolchain), `shadowlab/` (rehearsal scenarios), `capability/` (passport generation/validation), `events/` (Pub/Sub event envelopes).
        - *Future Planned-Only Structure:* No empty directories or placeholder files are created in P-06.01. Implementation of these modules belongs strictly to future phases (P-07 through P-24).
- Alternatives Considered:
    - *Python 3.10 / 3.11 / 3.12:* Rejected. Python 3.13 is fully supported across Google Cloud Run (`python313` runtime), Google ADK (2.6+), and Google GenAI SDK (`google-genai`). The local active environment is verified on Python 3.13.5 with 590 passing contract and convention tests.
    - *Node.js / TypeScript frontend build framework (React, Next.js, Vite):* Rejected. A Node-based frontend introduces multi-runtime container bloat, npm dependency drift, and dual build steps in CI/CD and Cloud Run deployment. Vanilla JS/HTML/CSS meets all judge dashboard requirements cleanly.
    - *Creating empty directory scaffolding for P-07+ in P-06.01:* Rejected. Creating placeholder modules violates the no-empty-scaffolding rule and creates deceptive impressions of progress.
- Consequences:
    - Resolves all `NOT_DECIDED` runtime fields in `AGENT_ENVIRONMENT_AND_API.md`.
    - Establishes a deterministic Python 3.13.5 baseline for P-06.02 dependency manifests and lockfiles.
    - Preserves provider neutrality of domain contracts and Google-native product architecture.
- Evidence:
    - Google ADK requires `Python >= 3.10` (PyPI package metadata and official docs, access date 2026-08-15).
    - `google-genai` requires `Python >= 3.10` (PyPI package metadata and official docs, access date 2026-08-15).
    - Google Cloud Run supports `Python 3.13` natively (`python313` runtime ID) and detects `.python-version` via Google Cloud Buildpacks (Google Cloud Run official docs, access date 2026-08-15).
    - Local execution verified on Python 3.13.5 (`python -m pytest tests/` with 590 passing contract tests).
- Relationship to ADK: Google ADK orchestrator and runtime agents (P-07+) will execute natively on Python 3.13.5.
- Relationship to Cloud Run: Deployment containers will target Python 3.13 runtime via Cloud Run buildpack / container configurations.
- Relationship to Existing Planned Architecture Map: 100% compliant with `docs/ARCHITECTURE.md` package map with zero architectural deviations.
- Boundary with P-06.02: P-06.01 solely selects and pins the language/runtime versions and repository structure. P-06.02 owns creating reproducible dependency manifests and lockfiles. `requirements.txt` is not modified and no lockfiles are generated.
- Boundary with P-07: P-06.01 introduces no agent implementation, skeleton code, or runtime services.

