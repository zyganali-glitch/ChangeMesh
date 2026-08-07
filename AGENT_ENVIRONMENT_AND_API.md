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
- Cloud Run: `API_ENABLED`
- Firestore: `API_ENABLED`
- Pub/Sub: `API_ENABLED`
- Agent Runtime: `NOT_VERIFIED`
- Memory Bank: `NOT_VERIFIED`
- Agent Registry: `NOT_VERIFIED`
- Agent Identity: `NOT_VERIFIED`
- Agent Gateway: `NOT_VERIFIED`
- Model Armor: `NOT_VERIFIED`
- GitHub demo repository: `NOT_CREATED`
- Public demo URL: `NOT_AVAILABLE`

## Rules

- Never commit credentials, service-account keys, OAuth tokens, cookies, or personal access tokens.
- Prefer Application Default Credentials locally and workload identity in Google Cloud.
- Record exact service, project, region, resource name, required role, and teardown method.
- Every environment variable is documented with sensitivity, purpose, requirement, and safe example.
- Every external API write defines timeout, retry, idempotency, and evidence behavior.
- Costs and quotas are measured before final demo.

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
| Install | `NOT_DEFINED` | `NOT_RUN` | - |
| Unit tests | `NOT_DEFINED` | `NOT_RUN` | - |
| Integration tests | `NOT_DEFINED` | `NOT_RUN` | - |
| E2E demo | `NOT_DEFINED` | `NOT_RUN` | - |
| Local web | `NOT_DEFINED` | `NOT_RUN` | - |
| Deploy | `NOT_DEFINED` | `NOT_RUN` | - |
| Teardown | `NOT_DEFINED` | `NOT_RUN` | - |
