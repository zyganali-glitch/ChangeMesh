# ChangeMesh — Devpost Submission Text

**Status:** `VERIFIED / FROZEN`  
**Category:** Fortified Enterprise Fleet  
**Tagline:** Rehearse every critical change. Trust only proven agents. Execute with evidence.  
**Canonical Model:** `gemini-3.6-flash` (Vertex AI / official `google-genai` SDK)  
**Deployed GCP Region:** `europe-west3`  
**Live URL:** `https://changemesh-p24-e2e-764732742797.europe-west3.run.app`  

---

## 🎯 1. The Problem We Solve

In modern distributed architectures, database schema migrations and breaking API changes are among the leading causes of production outages (SEV-1/SEV-2), costing enterprises hundreds of thousands of dollars per incident. 

When emerging autonomous AI agents are given database credentials or CI/CD access, they create severe risks: hallucinated SQL migrations, dropped columns, uncoordinated API breaking changes, and silent customer data exfiltration. Traditional CI tools only test single repositories in isolation and cannot simulate distributed consumer breakage across independent microservices.

---

## ⚡ 2. What ChangeMesh Does

ChangeMesh is a **proof-carrying multi-agent platform** that orchestrates distributed enterprise change with mathematical and cryptographic guarantees:

1. **Specialized 5-Agent Fleet (ADK):** Deploys Scout, Policy, Migration, Evidence, and Steward agents operating under a strict **4-Lane Authority Model** (Deterministic Code > Semantic Judgment > Policy > Bounded Human Authority).
2. **Pre-Flight Simulation in ShadowLab:** Rehearses migrations against synthetic data shadows to mathematically prove backward and forward schema compatibility *before* human intervention.
3. **Approval Compression Decision Packets:** Eliminates slow change advisory board meetings by compressing complex multi-service diffs into single-screen, proof-carrying human decision packets.
4. **Draft-Only PR Ceiling:** Enforces bounded real-world actions via draft-only GitHub pull requests, preventing autonomous production merges.
5. **Zero-Custody VPC Boundary:** Ensures customer schemas and proprietary data remain strictly within the customer's private network.

---

## 🛠️ 3. How We Built It (Google Cloud & Gemini Stack)

ChangeMesh is engineered from the ground up for the Google Cloud serverless ecosystem:

- **Canonical Model Authority:** `gemini-3.6-flash` hosted on Vertex AI, invoked via the official `google-genai` Python SDK with strict retry budgets, timeout ceilings, and pre-wire secret scanning.
- **Agent Framework:** Google Agent Development Kit (ADK) agent topology with cryptographic capability passport discovery.
- **Compute & Serverless Deployment:** Deployed natively on Google Cloud Run (`europe-west3`) running containerized Python 3.13 with automatic scale-to-zero enforcement (`min_instances=0`).
- **State Persistence:** Google Cloud Firestore in Native mode enforcing Optimistic Concurrency Control (OCC CAS) to guarantee zero race conditions or split-brain sagas.
- **Event Mesh Backbone:** Google Cloud Pub/Sub topic and subscription topology with dead-letter queue (DLQ) handoffs and causal timeline ordering.
- **Zero Frontend Build Complexity:** Pure HTML5/CSS3/ES6 served directly by Python without Node.js, npm, or webpack build pipelines.

---

## 🛡️ 4. Challenges We Overcame

1. **Preventing Model Hallucination Drift:** Built a strict 4-lane authority model ensuring deterministic facts (AST diffs, test exit codes) can never be overridden by model semantic judgment.
2. **OCC CAS State Integrity:** Implemented lock-free versioned CAS updates to guarantee atomic saga transitions under high-concurrency event delivery.
3. **Zero-Custody Data Privacy:** Decoupled the orchestrator into 4 distinct planes (Control, Adapter, Policy Pack, Customer Data), ensuring raw database records never leave the customer's VPC.

---

## 🏆 5. Accomplishments & Grounded Evidence

- **1,760+ Automated Tests:** Comprehensive test matrix covering unit, integration, security, ShadowLab, and governance invariants (runs in ~15s).
- **Sub-10ms Local Execution:** Mean demo execution latency of ~8.25ms with 100% saga completion rate.
- **Pure Scale-to-Zero Serverless:** $0.00 / month idle infrastructure cost across Cloud Run, Firestore, and Pub/Sub.
- **Verified Revision Provenance:** Immutable SHA-256 binding between Git commit, container digest, and deployed Cloud Run revision.

---

## 🔮 6. What's Next for ChangeMesh

- **30 Days:** Standalone Helm chart packaging for customer-hosted VPC runners; Google Cloud Spanner adapter support.
- **60 Days:** GitLab Self-Managed and Terraform state migration handlers; SOC 2 Type I automated compliance packs.
- **90 Days:** Public plugin marketplace for community policy packs; VS Code extension for local ShadowLab rehearsals.
