# ChangeMesh Cost and Latency Budget Plan

> **Scope:** P-08.05 Gemini Integration & Bounded Model Telemetry
> **Status:** `ACTIVE / P-08.05 REPAIRED`
> **Date:** 2026-08-16

---

## 1. Overview and Purpose

This document establishes the official ChangeMesh cost measurement, latency bounding, and budget policy framework. It defines the machine-checkable rules enforced by `src/core/gemini_client.py` and records the honest state of model execution telemetry and provider pricing calibration.

---

## 2. Project / Demo Latency and Cost Budget Policy

To satisfy Master Plan micro-task P-08.05 acceptance criteria without inventing external provider facts, ChangeMesh establishes narrow, deterministic **Local Project / Demo Budget Policies**.

> [!IMPORTANT]
> **Policy Boundary Notice:** The latency ceilings and cost thresholds below represent internal ChangeMesh demonstration policy bounds. They are **NOT** Google Cloud provider SLAs, service availability commitments, or contractual pricing guarantees.

### 2.1 Frozen Policy Defaults

| Parameter | Canonical Constant | Default Bound | Purpose |
|---|---|---|---|
| Per-Call Max Latency | `DEMO_MAX_LATENCY_MS` | `30,000.0 ms` (30.0s) | Prevents runaway model stalls during interactive demos; aligns with default call timeout. |
| Per-Call Max Cost | `DEMO_MAX_COST_USD` | `$0.05000000 USD` | Caps single-invocation budget exposure for synthetic demo changes. |
| Per-Call Max Total Tokens | `DEMO_MAX_TOTAL_TOKENS` | `12,288 tokens` | Internal total-token demonstration policy threshold (accommodates default 4,096 output cap up to 8,192 maximum configurable output ceiling plus input context; runtime enforces output bounds [1, 8192] without claiming an artificial prompt cap). |

### 2.2 Deterministic Budget Evaluation

The evaluation function `evaluate_model_call_budget(telemetry, policy)` enforces these bounds deterministically with fail-closed aggregate semantics:

- **Latency Status (`PASS` / `FAIL`):** Evaluated against `policy.max_latency_ms`. Exceeding the bound fails closed (`FAIL`). Always a required evaluation dimension.
- **Cost Status (`PASS` / `FAIL` / `NOT_RUN`):** When explicit rates and measured token counts exist, evaluated against `policy.max_cost_usd`. If no rate card was provided or token counts are missing, cost is **NOT** guessed or treated as zero; it is recorded honestly as `NOT_RUN`.
- **Token Status (`PASS` / `FAIL` / `NOT_RUN`):** Evaluated against `policy.max_total_tokens`. If token counts are unavailable from provider metadata, recorded as `NOT_RUN`.
- **Aggregate Budget Status (`overall_status` & `overall_budget_pass`):**
  - `overall_status = "PASS"` (`overall_budget_pass = True`) **ONLY** when all required configured dimensions (latency, cost, token) are evaluated and report `PASS`.
  - `overall_status = "FAIL"` (`overall_budget_pass = False`) if **ANY** required configured dimension reports `FAIL`.
  - `overall_status = "NOT_RUN"` (`overall_budget_pass = False`) if **ANY** required configured dimension reports `NOT_RUN` (and none `FAIL`). `NOT_RUN` strictly never contributes to an aggregate `PASS`.

---

## 3. Token Measurement and Cost Calculation

Model calls executed via `BoundedGeminiClient` record operational telemetry with exact token counts from underlying SDK `usage_metadata`:

- `prompt_token_count`: Tokens consumed by input prompt and system instruction.
- `response_token_count`: Candidate response token count.
- `total_token_count`: Combined token usage reported by provider.
- `duration_ms`: Wall-clock execution time measured via monotonic clock.
- `attempts` & `retry_count`: Total dispatch attempts and retry occurrences (wrapper-owned backoff).

### Cost Formula
Deterministic token cost is calculated via `GeminiCostRateCard`:
$$\text{Estimated Cost (USD)} = \frac{(\text{prompt\_tokens} \times \text{input\_rate}) + (\text{response\_tokens} \times \text{output\_rate})}{1{,}000{,}000}$$

---

## 4. Rate Provenance Architecture

To resolve the rule that cost estimates require named rate provenance, `GeminiCostRateCard` requires explicit non-empty `rate_card_id` and explicit `provenance_kind`:

| Provenance Kind | Machine Identifier | Meaning | Provider Calibrated? |
|---|---|---|---|
| `RateProvenanceKind.TEST_FORMULA` | `"TEST_FORMULA"` | Explicit benchmark or test formula rates provided by the test harness. | No (`NOT_RUN`) |
| `RateProvenanceKind.CUSTOM_UNVERIFIED` | `"CUSTOM_UNVERIFIED"` | Caller-provided custom rates without verified provider calibration. | No (`NOT_RUN`) |
| `RateProvenanceKind.PROVIDER_CALIBRATED` | `"PROVIDER_CALIBRATED"` | Reserved taxonomy identifier for future verified Google Cloud pricing rate cards. | No (`NOT_RUN`; caller assertion cannot manufacture verified calibration truth) |

### Provider Pricing Calibration Status: `NOT_RUN`
Live Google Cloud provider pricing calibration is intentionally **`NOT_RUN`** for local testing. In accordance with ChangeMesh integrity rules:
- No pricing numbers are invented or hard-coded as Google facts.
- Uncalibrated runs produce `cost_status="NOT_RUN"` when no rate card is supplied, or `cost_status="CALCULATED"` with `provider_pricing_calibrated=False` when using test/custom rate cards.
- Caller selection of `PROVIDER_CALIBRATED` does **not** manufacture verified provider pricing truth (`provider_pricing_calibrated` remains `False`).

---

## 5. Canonical Metrics Evidence Artifact

The canonical P-08.05 metrics evidence artifact is constructed via `build_model_metrics_artifact()` and exported to deterministic UTF-8 JSON via `export_metrics_artifact_json()`.

### Structure:
```json
{
  "artifact_schema_version": "1.0.0",
  "artifact_kind": "MODEL_CALL_METRICS",
  "call_id": "call_...",
  "model_id": "gemini-3.6-flash",
  "provider": "vertexai",
  "api_version": "v1beta1",
  "timestamps": {
    "start_time_iso": "2026-08-16T...",
    "end_time_iso": "2026-08-16T..."
  },
  "performance": {
    "duration_ms": 124.5,
    "attempts": 1,
    "retry_count": 0,
    "final_outcome": "SUCCESS",
    "finish_reason": "STOP"
  },
  "token_usage": {
    "prompt_tokens": 42,
    "response_tokens": 18,
    "total_tokens": 60
  },
  "cost_telemetry": {
    "estimated_cost_usd": 0.0000975,
    "cost_status": "CALCULATED",
    "rate_card_id": "test-card-001",
    "rate_provenance": "TEST_FORMULA",
    "provider_pricing_calibrated": false
  },
  "budget_evaluation": {
    "overall_status": "PASS",
    "overall_budget_pass": true,
    "latency_status": "PASS",
    "latency_ms": 124.5,
    "max_latency_ms": 30000.0,
    "cost_status": "PASS",
    "estimated_cost_usd": 0.0000975,
    "max_cost_usd": 0.05,
    "token_status": "PASS",
    "total_tokens": 60,
    "max_total_tokens": 12288,
    "details": "overall: PASS; latency: 124.5ms / limit 30000.0ms (PASS); cost: $0.00009750 / budget $0.05 (PASS); tokens: 60 / limit 12288 (PASS)"
  }
}
```

### Secrecy Invariant:
Metrics artifacts strictly forbid containing:
- Prompt text or instructions
- Response text or candidate content
- Credentials, API keys, bearer tokens, or sensitive correlation IDs.
