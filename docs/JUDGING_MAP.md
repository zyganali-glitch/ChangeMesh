# ChangeMesh — Official Judging Criteria & Category Mapping

**Competition Category:** Fortified Enterprise Fleet  
**Status:** `DONE` / `VERIFIED`  
**Total Canonical Test Suite:** 1,800+ tests passing (100% green)  
**Deployed GCP Service:** Cloud Run (`europe-west3`) — `https://changemesh-p24-e2e-764732742797.europe-west3.run.app`  

---

## 1. Hackathon Scoring Criteria to Verified Repository Artifacts

| Competition Criterion / Track Requirement | Exact Verified Repository Evidence | Status | Evidence Document Link |
|---|---|---|---|
| **1. Gemini 3.5+ Native Authority** | Canonical model `gemini-3.6-flash` via official `google-genai` SDK on Vertex AI with bounded retries and latency tracking. | `PASS` | [`src/core/gemini_client.py`](../src/core/gemini_client.py) |
| **2. Google Agent Framework (ADK)** | 5-agent specialized fleet (Scout, Policy, Migration, Evidence, Steward) orchestrating change lifecycles. | `PASS` | [`src/agents/`](../src/agents/) |
| **3. Google Cloud Architecture** | Serverless Cloud Run backend (`europe-west3`), Firestore Native OCC CAS persistence, and Pub/Sub event bus. | `PASS` | [`deploy/gcp_infrastructure_manifest.json`](../deploy/gcp_infrastructure_manifest.json) |
| **4. Autonomous Multi-Agent Saga** | 6-stage deterministic orchestrator with Optimistic Concurrency Control (OCC CAS) and zero unverified writes. | `PASS` | [`src/orchestrator/orchestrator_saga.py`](../src/orchestrator/orchestrator_saga.py) |
| **5. Pre-Flight Simulation (ShadowLab)** | Synthetic data shadow rehearsal testing backward/forward compatibility before human escalation. | `PASS` | [`tests/test_p25_03_shadowlab_suite.py`](../tests/test_p25_03_shadowlab_suite.py) |
| **6. Cross-Session Memory Trust** | Cryptographic memory provenance and validation gates ensuring zero hallucinated state resumption. | `PASS` | [`src/memory/trust_layer.py`](../src/memory/trust_layer.py) |
| **7. Capability Passport & Discovery** | Capability Registry verifying cryptographic agent passports before routing requests. | `PASS` | [`src/registry/agent_registry.py`](../src/registry/agent_registry.py) |
| **8. Security & 4-Lane Authority** | Target zero-custody VPC architecture, 4-lane authority model, and pre-serialization secret scanning. | `PASS` | [`docs/AUTHORITY_MAP.md`](AUTHORITY_MAP.md) |
| **9. Observability & Tracing** | OpenTelemetry structured spans, Cloud Trace correlation, and pre-log secret redaction. | `PASS` | [`docs/P-28.06_SANITIZED_CONSOLE_EVIDENCE_REPORT.md`](P-28.06_SANITIZED_CONSOLE_EVIDENCE_REPORT.md) |
| **10. Human Decision Compression** | Approval compression decision packets with draft-only PR ceilings preventing irreversible outages. | `PASS` | [`src/gate/compression.py`](../src/gate/compression.py) |
| **11. Reproducibility & Lean Footprint** | Zero Node.js / npm dependencies, scale-to-zero serverless ($0.00 idle), and rapid pytest execution. | `PASS` | [`tests/test_p27_05_lean_architecture.py`](../tests/test_p27_05_lean_architecture.py) |

---

## 2. Fast Evaluation Links for Judges

- **Live Service Health:** [`https://changemesh-p24-e2e-764732742797.europe-west3.run.app/health`](https://changemesh-p24-e2e-764732742797.europe-west3.run.app/health)
- **Live Dashboard Snapshot:** [`https://changemesh-p24-e2e-764732742797.europe-west3.run.app/api/dashboard/snapshot`](https://changemesh-p24-e2e-764732742797.europe-west3.run.app/api/dashboard/snapshot)
- **Judge Quick-Start Guide:** [`docs/JUDGE_START_HERE.md`](JUDGE_START_HERE.md)
- **Revision Provenance Binding:** [`docs/P-28.03_REVISION_PROVENANCE_BINDING.json`](P-28.03_REVISION_PROVENANCE_BINDING.json)
