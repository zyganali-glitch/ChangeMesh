# ChangeMesh Demo Video Manifest & Recording Freeze

**Status:** `FROZEN / READY FOR RECORDING`  
**Date:** 2026-08-22  
**Task:** `P-31.01` — Freeze demo dataset, accounts, browser layout, cloud revision, fallback recording plan  
**Document:** `docs/DEMO_MANIFEST.md`  
**Test Suite:** `tests/test_p31_01_demo_manifest.py` (3 tests passing)  
**Acceptance Criteria:** `No last-minute hidden state changes.`

---

## 📦 1. Frozen Demo Dataset Specification

- **Baseline Schema (v1.0.0):**
  - Table: `customer_profiles`
  - Field: `billing_address` (`VARCHAR(255)`)
- **Target Breaking Migration (v2.0.0):**
  - Field: `billing_address` converted to structured JSON (`street`, `city`, `postal_code`, `country_code`).
  - Downstream Consumers: 3 independent microservices (`invoicing-service`, `fraud-detector`, `crm-sync`).
- **ShadowLab Synthetic Simulation Pack:**
  - 1,000 synthetic customer records with realistic multi-region address profiles.
  - Zero PII / Zero production customer data.

---

## 👤 2. Demo Persona & Identity Ceiling

- **Operator Persona:** Platform Lead (`lead-platform@changemesh-enterprise.internal`)
- **Agent Roles Displayed:**
  - Scout Agent: Discovery & AST Diff extraction
  - Policy Guardian Agent: Invariant verification & secret sanitization
  - Migration Agent: ShadowLab synthetic rehearsal orchestrator
  - Evidence Auditor: Proof ledger hashing & SHA-256 seal
  - Steward Agent: Decision packet delivery & draft PR management
- **Bounded Real Action Ceiling:** GitHub Draft Pull Request only (zero direct commits to `main`).

---

## 🖥️ 3. Browser Layout & Viewport Configuration

- **Target Resolution:** 1920 x 1080 (16:9 Standard Full HD)
- **Display Scaling:** 100% Zoom (Browser & OS)
- **Theme:** Enterprise Dark Mode (`#0a0e17` background, `#00e5ff` cyan highlights)
- **Evidence Mode Indicators Visible:**
  - `SIMULATION` (Purple badge for ShadowLab runs)
  - `RECORDED_CLOUD` (Cyan badge for verified GCP executions)
  - `LIVE_WRITE` (Amber badge for draft PR creation)

---

## ☁️ 4. Frozen Cloud Revision Binding

- **GCP Project ID:** `project-af5e1c99-3bc4-424f-b53`
- **Region:** `europe-west3` (Frankfurt)
- **Service Name:** `changemesh-p24-e2e`
- **Deployed Revision:** `changemesh-p24-e2e-00002-bqc`
- **Live Endpoint:** `https://changemesh-p24-e2e-764732742797.europe-west3.run.app`
- **Canonical Model:** `gemini-3.6-flash` via Vertex AI

---

## 🛡️ 5. Fallback Recording & Fault Contingency Plan

> **Transparency Invariant:** No silent fallbacks. If a contingency is triggered during demonstration, the mode change must be visually and verbally explicit (e.g. clearly labeled as `SIMULATION` or `FIXTURE` mode rather than live cloud execution).

| Failure Mode | Detection Signal | Automated Contingency Procedure | Mode Disclosure |
|---|---|---|---|
| Cloud Run Cold Start / Network Latency (>3s) | HTTP 504 / timeout on curl | Switch explicitly to local Python server (`http://localhost:8080`) | Labeled as `SIMULATION` / Local Demo |
| Vertex AI Quota / 429 Backoff Spike | Exponential backoff notification | Switch explicitly to deterministic fixture replay (`tests/fixtures/`) | Labeled as `FIXTURE` Replay |
| OBS Screen Recording Frame Drop | OBS dropped frame alert | Re-record individual scene chunk using standardized timestamps | Seamless retake |
