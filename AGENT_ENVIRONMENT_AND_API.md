# ChangeMesh — Environment and API State

Record actual environment only; do not fill unknown values with guesses.

## Current status

- Local implementation stack: `Python 3.13.5` (backend/agents) + `Vanilla JS/HTML/CSS` (web dashboard, no build step)
- Python version: `3.13.5` (pinned in `.python-version`)
- Node version: `NOT_REQUIRED` (No Node runtime or build step; dashboard is vanilla static assets served via Python/Cloud Run)
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

### Machine Conventions Contract Boundary (P-05.06)

- **Machine conventions** (`domain/contracts/conventions.py`) define canonical hashing (`HashAlgorithm.SHA256`, 64-character lowercase hex regex `^[0-9a-f]{64}$`), UTC timestamp normalization and naive rejection (`UtcDateTime`), deterministic canonical JSON serialization (`canonical_json_bytes`), and structural secret redaction (`redact_mapping`, `REDACTION_SENTINEL = "[REDACTED]"`).
### Dependency and Lockfile Architecture Boundary (P-06.02 / ADR-0016)

- **Canonical Manifest (Source of Truth):** `pyproject.toml` (PEP 621 / PEP 735). Direct runtime dependencies (`google-adk>=2.6.0`, `google-genai>=0.1.0`, `pydantic>=2.0.0`, `google-cloud-firestore>=2.15.0`, `google-cloud-pubsub>=2.20.0`, `google-cloud-run>=0.10.0`, `google-cloud-logging>=3.10.0`, `google-cloud-trace>=1.15.0`) and direct dev/test dependencies (`pytest>=8.0.0`, `pyyaml>=6.0.0`).
- **Deterministic Lock Artifact:** `uv.lock` (generated via `uv lock` with `uv 0.11.28`). Freezes the exact resolved dependency graph (77 installed packages + root project) with repository URLs and SHA-256 integrity hashes.
- **Compatibility Lockfile Export:** `requirements.txt` is strictly a generated compatibility lock export with exact pins and SHA-256 hashes for standard `pip` environments, Cloud Run buildpacks, and Docker containers without `uv`.
- **Regeneration Command:** `uv lock ; uv export --frozen --all-groups -o requirements.txt`
- **Installation from Lock:** `uv sync --frozen` (or `uv pip install --require-hashes -r requirements.txt` / `pip install --require-hashes -r requirements.txt`).

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
| Install (uv locked) | `uv sync --frozen` | `VERIFIED` | 2026-08-15 |
| Install (pip hash-locked) | `pip install --require-hashes -r requirements.txt` | `VERIFIED` | 2026-08-15 |
| Lock generation | `uv lock` | `VERIFIED` | 2026-08-15 |
| Lock export | `uv export --frozen --all-groups -o requirements.txt` | `VERIFIED` | 2026-08-15 |
| Dependency check | `uv pip check` | `VERIFIED` | 2026-08-15 |
| Unit tests (Contracts) | `python -m pytest tests/test_p05_01_contracts.py` | `VERIFIED` | 2026-08-11 |
| Unit tests (P-05.05 Events) | `python -m pytest tests/test_p05_05_event_envelope.py -v --tb=short` | `VERIFIED` (82 passed) | 2026-08-13 |
| Unit tests (P-05.06 Conventions) | `python -m pytest tests/test_p05_06_contract_conventions.py -v --tb=short` | `VERIFIED` (214 passed) | 2026-08-15 |
| Unit tests (Combined P-05) | `python -m pytest tests/test_p05_01_contracts.py tests/test_p05_02_lifecycle.py tests/test_p05_03_evidence_contracts.py tests/test_p05_04_core_innovation_contracts.py tests/test_p05_05_event_envelope.py tests/test_p05_06_contract_conventions.py -v --tb=short` | `VERIFIED` (590 passed) | 2026-08-15 |
| Unit tests (Full Suite) | `python -m pytest tests/` | `FAIL` (590 passed, 3 errors: missing `project` fixture in `test_gcp_access.py`) | 2026-08-15 |
| Integration tests | `NOT_DEFINED` | `NOT_RUN` | - |
| E2E demo | `NOT_DEFINED` | `NOT_RUN` | - |
| Local web | `NOT_DEFINED` | `NOT_RUN` | - |
| Deploy | `NOT_DEFINED` | `NOT_RUN` | - |
| Teardown | `NOT_DEFINED` | `NOT_RUN` | - |
