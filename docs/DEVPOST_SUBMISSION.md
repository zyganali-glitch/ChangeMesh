# ChangeMesh — Devpost Submission Text

**Status:** `VERIFIED / FROZEN`  
**Category:** Fortified Enterprise Fleet  
**Tagline:** Rehearse every critical change. Trust only proven agents. Execute with evidence.  
**Canonical Model:** `gemini-3.6-flash` (Vertex AI / official `google-genai` SDK)  
**Deployed GCP Region:** `europe-west3`  
**Live URL:** `https://changemesh-p24-e2e-764732742797.europe-west3.run.app`  

---

## 🎯 1. The Problem We Solve

In modern distributed architectures, database schema migrations and breaking API changes are among the leading causes of production outages (SEV-1/SEV-2), costing enterprises significant operational downtime per incident. 

When emerging autonomous AI agents are given database credentials or CI/CD access, they create severe risks: hallucinated SQL migrations, dropped columns, uncoordinated API breaking changes, and silent customer data exfiltration. Traditional CI tools only test single repositories in isolation and cannot simulate distributed consumer breakage across independent microservices.

---

## ⚡ 2. What ChangeMesh Does

ChangeMesh is a **proof-carrying multi-agent platform** that orchestrates distributed enterprise change with tamper-evident SHA-256 evidence chains and deterministic validation:

1. **Specialized 5-Agent Fleet (ADK):** Deploys Scout, Policy, Migration, Evidence, and Steward agents operating under a strict **4-Lane Authority Model** (Four distinct, sovereign decision lanes: Deterministic Code, Gemini Semantic Judgment, Organizational Policy, and Human Authority).
2. **Pre-Flight Simulation in ShadowLab:** Rehearses migrations against synthetic data shadows to deterministically test backward and forward schema compatibility over supported synthetic fixtures *before* human intervention.
3. **Approval Compression Decision Packets:** Eliminates slow change advisory board meetings by compressing complex multi-service diffs into single-screen, proof-carrying human decision packets.
4. **Draft-Only PR Ceiling:** Enforces bounded real-world actions via draft-only GitHub pull requests, preventing autonomous production merges.
5. **Zero-Custody Target Architecture:** Defines a 4-plane decoupling model (Control, Adapter, Policy Pack, Customer Data) designed to keep proprietary schemas and data inside customer VPC boundaries.

---

## 🛠️ 3. How We Built It (Google Cloud & Gemini Stack)

ChangeMesh is engineered from the ground up for the Google Cloud serverless ecosystem:

- **Canonical Model Authority:** `gemini-3.6-flash` hosted on Vertex AI, invoked via the official `google-genai` Python SDK with strict retry budgets, timeout ceilings, and pre-wire secret scanning.
- **Agent Framework:** Google Agent Development Kit (ADK) agent topology with cryptographic capability passport discovery.
- **Compute & Serverless Deployment:** Deployed natively on Google Cloud Run (`europe-west3`) running containerized Python 3.13 with automatic scale-to-zero enforcement (`min_instances=0`).
- **State Persistence:** Google Cloud Firestore in Native mode enforcing Optimistic Concurrency Control (OCC CAS) version checks to protect repository transitions.
- **Event Mesh Backbone:** Google Cloud Pub/Sub topic and subscription topology with dead-letter queue (DLQ) handoffs and causal timeline ordering.
- **Zero Frontend Build Complexity:** Pure HTML5/CSS3/ES6 served directly by Python without Node.js, npm, or webpack build pipelines.

---

## 🛡️ 4. Challenges We Overcame

1. **Preventing Model Hallucination Drift:** Built a strict 4-lane authority model ensuring deterministic facts (AST diffs, test exit codes) can never be overridden by model semantic judgment.
2. **OCC CAS State Integrity:** Implemented lock-free versioned CAS updates to protect atomic saga transitions under high-concurrency event delivery.
3. **Zero-Custody Data Privacy:** Designed 4-plane architectural decoupling across Control, Adapter, Policy Pack, and Customer Data planes for post-hackathon VPC runner isolation.

---

## 🏆 5. Accomplishments & Grounded Evidence

- **1,800+ Automated Tests:** Comprehensive test matrix covering unit, integration, security, ShadowLab, and governance invariants (runs in ~25s).
- **Sub-10ms Local Execution:** Mean demo execution latency of ~8.25ms with 100% saga completion rate.
- **Scale-to-Zero Serverless:** Configured Cloud Run `min_instances=0` serverless footprint for near-zero idle infrastructure cost.
- **Verified Revision Provenance:** Immutable SHA-256 binding between Git commit, container digest, and deployed Cloud Run revision.

---

## 🔮 6. What's Next for ChangeMesh

- **30 Days:** Standalone Helm chart packaging for customer-hosted VPC runners; Google Cloud Spanner adapter support.
- **60 Days:** GitLab Self-Managed and Terraform state migration handlers; SOC 2 Type I target compliance profiles.
- **90 Days:** Public plugin marketplace for community policy packs; VS Code extension for local ShadowLab rehearsals.
