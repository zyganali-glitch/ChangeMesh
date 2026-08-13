# ChangeMesh — Environment and API State

Record actual environment only; do not fill unknown values with guesses.

## Current status

- Local implementation stack: `NOT_DECIDED`
- Python version: `NOT_DECIDED`
- Node version: `NOT_DECIDED`
- Google Cloud project: `project-af5e1c99-3bc4-424f-b53`
- Region: `global` (for Vertex AI Gemini), `europe-west3` (for cloud resources)
- Vertex AI access: `ENABLED` (Provisioned via UI)
- Gemini model ID: `gemini-3.6-flash`
- Python SDK Requirement: `google-genai` (Legacy `vertexai` SDK is deprecated and returns 404 for Gemini 3.5+)
- Cloud Run: `VERIFIED` (as supporting services)
- Firestore: `VERIFIED` (as Operational State)
- Pub/Sub: `VERIFIED`
- Agent Runtime/Platform: `AVAILABLE / NOT_RUN`
- Memory Bank: `DEFERRED / NOT_RUN` (Requires ReasoningEngine instance, none deployed yet)
- Agent Registry: `AVAILABLE / NOT_RUN`
- Agent Identity: `PERMISSION_BLOCKED / NOT_RUN` (verified via `gcloud agent-identity auth-providers list --location=global`)
- Agent Gateway: `AVAILABLE / NOT_RUN` 
- Model Armor: `PERMISSION_BLOCKED / NOT_RUN` (403 on modelarmor.googleapis.com)
- Observability: `AVAILABLE / NOT_RUN`
- GitHub demo repository: `NOT_CREATED`
- Public demo URL: `NOT_AVAILABLE`

## Rules

### Credential Handling Architecture (P-04.03)

- **Local:** Use Application Default Credentials (ADC) for local development.
- **Cloud:** Target Workload Identity / Managed Identity. No service-account JSON key files should be used or distributed.
- **Isolation:** Credentials (`GITHUB_TOKEN`, API Keys, etc.) exist only at external adapter boundaries.
- **Inward Ban:** Credential material must **never** be propagated into model prompts, agent memory, evidence artifacts, Pub/Sub event payloads, EventEnvelope fields, or the public judge UI.
- **Logging:** Secret environment variables and credential material must never be logged unredacted.

- Never commit credentials, service-account keys, OAuth tokens, cookies, or personal access tokens.
- Prefer Application Default Credentials locally and workload identity in Google Cloud.
- Record exact service, project, region, resource name, required role, and teardown method.
- Every environment variable is documented with sensitivity, purpose, requirement, and safe example.
- Every external API write defines timeout, retry, idempotency, and evidence behavior.
- Costs and quotas are measured before final demo.

### Event Envelope Contract Boundary (P-05.05)

- **EventEnvelope** is a provider-neutral domain contract defined in `domain/contracts/event_envelope.py`. It carries event identity, change identity, causal chain, correlation, producer revision, and idempotency key.
- **No credentials** are permitted in event metadata or payload boundary. Credential material must never enter an EventEnvelope.
- **P-05.05 does NOT prove Pub/Sub runtime implementation.** The EventEnvelope is a domain schema consumed by future P-09 runtime.
- **P-09 owns actual publish/consume behavior**, including topic/subscription topology, publisher/consumer adapters, delivery, acknowledgements, retries, dead-letter, and infrastructure config.
- **classify_event_delivery** is a pure function consuming abstract already-seen snapshots. It does not own persistence (P-10).

## Environment-variable registry

| Variable | Purpose | Required | Secret | Safe example | Owner phase |
|---|---|---:|---:|---|---|
| `GOOGLE_CLOUD_PROJECT` | Cloud project ID | TBD | No | `project-af5e1c99-3bc4-424f-b53` | P-02/P-28 |
| `GOOGLE_CLOUD_LOCATION` | Deployment region | TBD | No | `global` | P-02/P-28 |
| `GEMINI_MODEL` | Exact model ID | TBD | No | `gemini-3.6-flash` | P-08 |
| `GITHUB_TOKEN` | Optional live draft-PR action | TBD | Yes | never commit | P-19 |
| `DEMO_REPO` | Synthetic target repository | TBD | No | `owner/changemesh-demo-enterprise` | P-24 |

## Command registry

Commands are added only after clean-checkout verification.

| Purpose | Command | Status | Last verified |
|---|---|---|---|
| Install | `pip install -r requirements.txt` | `VERIFIED` | 2026-08-08 |
| Unit tests (Contracts) | `python -m pytest tests/test_p05_01_contracts.py` | `VERIFIED` | 2026-08-11 |
| Unit tests (P-05.05 Events) | `python -m pytest tests/test_p05_05_event_envelope.py -v --tb=short` | `VERIFIED` | 2026-08-13 |
| Unit tests (Combined P-05) | `python -m pytest tests/test_p05_01_contracts.py tests/test_p05_02_lifecycle.py tests/test_p05_03_evidence_contracts.py tests/test_p05_04_core_innovation_contracts.py tests/test_p05_05_event_envelope.py -v --tb=short` | `VERIFIED` | 2026-08-13 |
| Unit tests (Full Suite) | `python -m pytest tests/` | `FAIL` (Missing `project` fixture in GCP tests) | 2026-08-13 |
| Integration tests | `NOT_DEFINED` | `NOT_RUN` | - |
| E2E demo | `NOT_DEFINED` | `NOT_RUN` | - |
| Local web | `NOT_DEFINED` | `NOT_RUN` | - |
| Deploy | `NOT_DEFINED` | `NOT_RUN` | - |
| Teardown | `NOT_DEFINED` | `NOT_RUN` | - |
