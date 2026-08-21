# Judge: Start Here

Status: `VERIFIED`

## 1. Ten-Second Version

ChangeMesh rehearses critical enterprise changes in a zero-cost digital twin (ShadowLab), routes them only to proven agent revisions with Capability Passports, executes reversible steps autonomously, escalates exactly one compressed decision packet to humans at irreducible boundaries, and seals every step with a cryptographic Evidence Passport.

---

## 2. Fastest One-Command Validation (Zero Install / Zero Cloud Cost)

Run the full, complete read-only release gate across all 1686 canonical unit, integration, resilience, and accessibility tests:

```bash
# 1. Clone repository and run full release gate
git clone https://github.com/zyganali-glitch/ChangeMesh.git
cd ChangeMesh
uv run python scripts/cmd.py validate
```

Or run the synthetic enterprise demo directly:

```bash
uv run python scripts/cmd.py demo
```

---

## 3. Key Judge Verification Touchpoints

1. **Root Release Gate Report:** [`docs/P-25.06_ROOT_VALIDATION_OUTPUT.md`](docs/P-25.06_ROOT_VALIDATION_OUTPUT.md) (All 7 gates passing).
2. **Accessible Judge Dashboard:** Run `uv run python service_app.py` and open `http://localhost:8080` in any browser (WCAG 2.1 AA compliant, zero external CDN dependencies, full EN/TR localization).
3. **Live Google Cloud Run Service:** Deployed on Google Cloud Run at region `europe-west3`, backed by Google Cloud Pub/Sub, Firestore with OCC CAS versioning, and Gemini 3.6 Flash.
4. **Tamper-Evident Evidence Passport:** [`docs/P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json`](docs/P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json) — verifiable SHA-256 cryptographic chain root digest.
5. **Real Bounded GitHub Draft PR:** Pull request created on target repository `zyganali-glitch/changemesh-livewrite-demo#2` with zero direct destructive writes.
6. **ShadowLab Fault & Replay Matrix:** [`docs/P-25.03_SHADOWLAB_SCENARIO_REPORT.md`](docs/P-25.03_SHADOWLAB_SCENARIO_REPORT.md) (57 resilience tests across 503 backoff, saga compensation DDL cleanup, and prompt injection quarantine).
