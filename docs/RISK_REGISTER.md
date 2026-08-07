# ChangeMesh Risk Register

Status: `PLANNED`

| Risk ID | Category | Description | Mitigation Strategy | Owner Phase | Status |
|---|---|---|---|---|---|
| RISK-01 | Product | Drift towards generic chatbot/workflow platform. | Strictly enforce the Non-Goals defined in `docs/NON_GOALS.md`. Focus only on schema/API change wedge. | P-03 | ACTIVE |
| RISK-02 | Safety | Agent inadvertently mutates production state or live data. | Implement Reversibility Gate and strict Red Lines (`docs/NON_GOALS.md`). Block production merges. | P-04 | ACTIVE |
| RISK-03 | Compliance | Presenting local simulations as real Google Cloud execution. | Strict Evidence Boundary definitions and `LOCAL_FIXTURE` labels for any mock adapters. | P-02 | MITIGATED (MVP fully managed per ADR-0007) |
| RISK-04 | Scope | Hackathon MVP attempts too many workflow types, resulting in shallow demo. | Restrict MVP to one reference scenario (`customer_id` -> `account_id`). | P-03 | ACTIVE |
