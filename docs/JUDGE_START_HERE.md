# ChangeMesh — Judge Quick-Start Guide (Fastest Evaluation Route)

**Competition Category:** Fortified Enterprise Fleet  
**Canonical Model:** `gemini-3.6-flash` (Vertex AI / official `google-genai` SDK)  
**Deployed GCP Region:** `europe-west3`  
**Live Service URL:** `https://changemesh-p24-e2e-764732742797.europe-west3.run.app`  
**Revision Digest:** `changemesh-p24-e2e-00002-bqc`  

---

## 🚀 60-Second Fast Evaluation (Live Cloud Run)

You can evaluate the live ChangeMesh deployment directly over HTTP without installing local tools:

```bash
# 1. Health Probe (Verifies Cloud Run & Environment)
curl -s https://changemesh-p24-e2e-764732742797.europe-west3.run.app/health

# 2. View Real-Time Dashboard Snapshot
curl -s https://changemesh-p24-e2e-764732742797.europe-west3.run.app/api/dashboard/snapshot

# 3. Trigger Live Multi-Agent Saga Execution
curl -s -X POST https://changemesh-p24-e2e-764732742797.europe-west3.run.app/run-e2e
```

**Expected Result:** The endpoint executes the 5-agent change saga (Scout → Policy → Migration → Evidence → Steward) and returns terminal state `COMPLETE` with a deterministic cryptographic `demo_digest`.

---

## 💻 3-Minute Local Evaluation (Zero Node.js / Python 3.13)

ChangeMesh is engineered with zero Node.js or frontend build dependencies. Everything is served natively via standard Python.

```bash
# 1. Clone and Install Dependencies
git clone https://github.com/zyganali-glitch/ChangeMesh.git
cd ChangeMesh
uv sync

# 2. Run Full Canonical Test Suite
uv run pytest -v

# 3. Launch Local Dashboard Server
uv run python service_app.py --port 8080
# Open http://localhost:8080 in your browser
```

---

## 📂 Key Judge Verification Artifacts

| Category | Primary Artifact | Description |
|---|---|---|
| **Judging Map** | [`docs/JUDGING_MAP.md`](JUDGING_MAP.md) | Line-by-line alignment to hackathon scoring criteria |
| **Live Cloud Evidence** | [`docs/P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json`](P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json) | Immutable multi-stage saga execution telemetry |
| **Revision Provenance** | [`docs/P-28.03_REVISION_PROVENANCE_BINDING.json`](P-28.03_REVISION_PROVENANCE_BINDING.json) | Binds Git commit, container digest, and Cloud Run revision |
| **Submission Manifest** | [`docs/SUBMISSION_MANIFEST.md`](SUBMISSION_MANIFEST.md) | Single submission truth: repo, video, model, and accounts |
| **Demo Script** | [`docs/DEMO_SCRIPT.md`](DEMO_SCRIPT.md) | 4-minute timestamped walkthrough script |
