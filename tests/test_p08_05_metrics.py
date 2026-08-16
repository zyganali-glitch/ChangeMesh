"""P-08.05 latency, token, cost, retry measurement, and budget enforcement tests."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from google.genai import errors, types

from src.core.gemini_client import (
    BoundedGeminiClient,
    GeminiCostRateCard,
    ModelCallBudgetPolicy,
    RateProvenanceKind,
    build_model_metrics_artifact,
    evaluate_model_call_budget,
    export_metrics_artifact_json,
)
from tests.test_p08_01_gemini_client import FakeSDKClient, make_successful_response


def test_metrics_measure_latency_tokens_and_explicit_cost() -> None:
    fake_sdk = FakeSDKClient(
        responses=[
            make_successful_response(
                "bounded response",
                prompt_tokens=42,
                response_tokens=18,
                total_tokens=60,
            )
        ]
    )
    rate_card = GeminiCostRateCard(
        input_usd_per_million_tokens=1.25,
        output_usd_per_million_tokens=2.5,
        rate_card_id="test-card-001",
        provenance_kind=RateProvenanceKind.TEST_FORMULA,
    )
    client = BoundedGeminiClient(
        cost_rate_card=rate_card,
        _sdk_client=fake_sdk,
    )

    response = client.generate_text("bounded prompt")
    telemetry = response.telemetry

    assert telemetry.duration_ms >= 0
    assert telemetry.prompt_token_count == 42
    assert telemetry.response_token_count == 18
    assert telemetry.total_token_count == 60
    assert telemetry.attempts == 1
    assert telemetry.retry_count == 0
    assert telemetry.estimated_cost_usd == 0.0000975
    assert telemetry.cost_status == "CALCULATED"
    assert telemetry.rate_card_id == "test-card-001"
    assert telemetry.rate_provenance == RateProvenanceKind.TEST_FORMULA.value


def test_cost_is_not_guessed_without_explicit_rate_card() -> None:
    fake_sdk = FakeSDKClient(
        responses=[make_successful_response(prompt_tokens=10, response_tokens=5, total_tokens=15)]
    )
    client = BoundedGeminiClient(_sdk_client=fake_sdk)

    telemetry = client.generate_text("bounded prompt").telemetry

    assert telemetry.prompt_token_count == 10
    assert telemetry.response_token_count == 5
    assert telemetry.estimated_cost_usd is None
    assert telemetry.cost_status == "NOT_RUN"
    assert telemetry.rate_card_id is None
    assert telemetry.rate_provenance is None


def test_rate_card_provenance_and_validation() -> None:
    # 1. Explicit TEST_FORMULA provenance
    card_formula = GeminiCostRateCard(
        input_usd_per_million_tokens=1.0,
        output_usd_per_million_tokens=2.0,
        rate_card_id="card-formula",
        provenance_kind=RateProvenanceKind.TEST_FORMULA,
    )
    assert card_formula.provenance_kind == RateProvenanceKind.TEST_FORMULA
    assert card_formula.estimate_usd(1000, 1000) == 0.003

    # 2. Explicit CUSTOM_UNVERIFIED provenance
    card_unverified = GeminiCostRateCard(
        input_usd_per_million_tokens=1.0,
        output_usd_per_million_tokens=2.0,
        rate_card_id="card-unverified",
        provenance_kind=RateProvenanceKind.CUSTOM_UNVERIFIED,
    )
    assert card_unverified.provenance_kind == RateProvenanceKind.CUSTOM_UNVERIFIED

    # 3. Explicit PROVIDER_CALIBRATED taxonomy value accepted by rate card
    card_provider = GeminiCostRateCard(
        input_usd_per_million_tokens=1.0,
        output_usd_per_million_tokens=2.0,
        rate_card_id="card-provider-taxonomy",
        provenance_kind=RateProvenanceKind.PROVIDER_CALIBRATED,
    )
    assert card_provider.provenance_kind == RateProvenanceKind.PROVIDER_CALIBRATED

    # 4. Rates without explicit rate_card_id fail (TypeError)
    with pytest.raises(TypeError):
        GeminiCostRateCard(  # type: ignore[call-arg]
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=2.0,
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        )

    # 5. Rates without explicit provenance_kind fail (TypeError)
    with pytest.raises(TypeError):
        GeminiCostRateCard(  # type: ignore[call-arg]
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=2.0,
            rate_card_id="card-missing-provenance",
        )

    # 6. Blank or whitespace rate_card_id fails (ValueError)
    with pytest.raises(ValueError, match="rate_card_id must be an explicit"):
        GeminiCostRateCard(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=1.0,
            rate_card_id="   ",
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        )

    # 7. Unspecified/defaulted identifier strings fail closed (ValueError)
    for invalid_id in ("rate-card-unspecified", "unspecified", "unknown", "none", "default"):
        with pytest.raises(ValueError, match="rate_card_id must be an explicit"):
            GeminiCostRateCard(
                input_usd_per_million_tokens=1.0,
                output_usd_per_million_tokens=1.0,
                rate_card_id=invalid_id,
                provenance_kind=RateProvenanceKind.TEST_FORMULA,
            )

    # 8. Rejection of invalid rates
    with pytest.raises(ValueError, match="finite non-negative"):
        GeminiCostRateCard(
            input_usd_per_million_tokens=-1.0,
            output_usd_per_million_tokens=1.0,
            rate_card_id="card-invalid",
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        )

    with pytest.raises(ValueError, match="finite non-negative"):
        GeminiCostRateCard(
            input_usd_per_million_tokens=float("nan"),
            output_usd_per_million_tokens=1.0,
            rate_card_id="card-invalid",
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        )

    with pytest.raises(ValueError, match="finite non-negative"):
        GeminiCostRateCard(
            input_usd_per_million_tokens=float("inf"),
            output_usd_per_million_tokens=1.0,
            rate_card_id="card-invalid",
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        )

    # 9. Incomplete tokens return None
    assert card_formula.estimate_usd(None, 5) is None
    assert card_formula.estimate_usd(5, None) is None


def test_caller_cannot_manufacture_provider_pricing_calibrated_truth() -> None:
    """Adversarial check: caller selection of PROVIDER_CALIBRATED cannot manufacture truth."""
    fake_sdk = FakeSDKClient(
        responses=[
            make_successful_response(
                "candidate text",
                prompt_tokens=50,
                response_tokens=25,
                total_tokens=75,
            )
        ]
    )
    # Caller attempts to supply PROVIDER_CALIBRATED rate card
    rate_card = GeminiCostRateCard(
        input_usd_per_million_tokens=0.15,
        output_usd_per_million_tokens=0.60,
        rate_card_id="caller-claimed-provider-card",
        provenance_kind=RateProvenanceKind.PROVIDER_CALIBRATED,
    )
    client = BoundedGeminiClient(
        cost_rate_card=rate_card,
        _sdk_client=fake_sdk,
    )

    telemetry = client.generate_text("prompt").telemetry
    artifact = build_model_metrics_artifact(telemetry)

    # Rate provenance is recorded faithfully as caller-provided enum
    assert telemetry.rate_provenance == "PROVIDER_CALIBRATED"
    assert artifact["cost_telemetry"]["rate_provenance"] == "PROVIDER_CALIBRATED"
    # BUT provider_pricing_calibrated MUST remain strictly False (NOT_RUN)
    assert artifact["cost_telemetry"]["provider_pricing_calibrated"] is False


def test_retry_measurement_reports_attempts_and_retry_count() -> None:
    fake_sdk = FakeSDKClient(
        responses=[make_successful_response(prompt_tokens=4, response_tokens=3, total_tokens=7)],
        exceptions=[errors.APIError(429, {"message": "rate limited"})],
    )
    sleeps: list[float] = []
    client = BoundedGeminiClient(
        _sleep_fn=sleeps.append,
        _sdk_client=fake_sdk,
    )

    telemetry = client.generate_text("retry prompt").telemetry

    assert telemetry.attempts == 2
    assert telemetry.retry_count == 1
    assert telemetry.final_outcome == "SUCCESS"
    assert sleeps == [0.5]


def test_budget_evaluation_within_limits() -> None:
    fake_sdk = FakeSDKClient(
        responses=[
            make_successful_response(
                "within budget response",
                prompt_tokens=100,
                response_tokens=50,
                total_tokens=150,
            )
        ]
    )
    client = BoundedGeminiClient(
        cost_rate_card=GeminiCostRateCard(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=2.0,
            rate_card_id="test-card",
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        ),
        _sdk_client=fake_sdk,
    )

    telemetry = client.generate_text("within budget prompt").telemetry
    evaluation = evaluate_model_call_budget(telemetry)

    assert evaluation.latency_status == "PASS"
    assert evaluation.cost_status == "PASS"
    assert evaluation.token_status == "PASS"
    assert evaluation.overall_status == "PASS"
    assert evaluation.overall_budget_pass is True
    assert "overall: PASS" in evaluation.details
    assert "latency:" in evaluation.details
    assert "cost:" in evaluation.details


def test_budget_evaluation_latency_exceeded() -> None:
    fake_sdk = FakeSDKClient(responses=[make_successful_response("response")])
    client = BoundedGeminiClient(_sdk_client=fake_sdk)
    telemetry = client.generate_text("prompt").telemetry

    # Policy with an impossibly low latency threshold
    strict_policy = ModelCallBudgetPolicy(max_latency_ms=0.0001)
    evaluation = evaluate_model_call_budget(telemetry, strict_policy)

    assert evaluation.latency_status == "FAIL"
    assert evaluation.overall_status == "FAIL"
    assert evaluation.overall_budget_pass is False


def test_budget_evaluation_cost_budget_exceeded() -> None:
    fake_sdk = FakeSDKClient(
        responses=[
            make_successful_response(
                "expensive response",
                prompt_tokens=10000,
                response_tokens=5000,
                total_tokens=15000,
            )
        ]
    )
    client = BoundedGeminiClient(
        cost_rate_card=GeminiCostRateCard(
            input_usd_per_million_tokens=10.0,
            output_usd_per_million_tokens=20.0,
            rate_card_id="high-rate-card",
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        ),
        _sdk_client=fake_sdk,
    )
    telemetry = client.generate_text("prompt").telemetry

    # Strict cost policy: max $0.001 (cost is (10k*10 + 5k*20)/1M = 0.20 USD)
    strict_cost_policy = ModelCallBudgetPolicy(max_cost_usd=0.001)
    evaluation = evaluate_model_call_budget(telemetry, strict_cost_policy)

    assert evaluation.cost_status == "FAIL"
    assert evaluation.overall_status == "FAIL"
    assert evaluation.overall_budget_pass is False


def test_budget_evaluation_missing_rate_remains_not_run_without_false_pass() -> None:
    """Adversarial check: missing rate card yields cost NOT_RUN and aggregate NOT_RUN."""
    fake_sdk = FakeSDKClient(
        responses=[make_successful_response(prompt_tokens=10, response_tokens=5, total_tokens=15)]
    )
    client = BoundedGeminiClient(_sdk_client=fake_sdk)
    telemetry = client.generate_text("prompt").telemetry

    evaluation = evaluate_model_call_budget(telemetry)

    assert evaluation.latency_status == "PASS"
    assert evaluation.cost_status == "NOT_RUN"
    assert evaluation.token_status == "PASS"
    assert evaluation.estimated_cost_usd is None
    # Aggregate state must be NOT_RUN and overall_budget_pass must be False
    assert evaluation.overall_status == "NOT_RUN"
    assert evaluation.overall_status != "PASS"
    assert evaluation.overall_budget_pass is False
    assert "overall: NOT_RUN" in evaluation.details
    assert (
        "cost: NOT_RUN (no rate card provided or incomplete tokens; not guessed)"
        in evaluation.details
    )


def test_budget_evaluation_missing_tokens_when_required_remains_not_run() -> None:
    """Adversarial check: missing token count when token budget required yields NOT_RUN."""
    raw_response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(parts=[types.Part.from_text(text="no tokens response")]),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        usage_metadata=None,
    )
    fake_sdk = FakeSDKClient(responses=[raw_response])
    client = BoundedGeminiClient(
        cost_rate_card=GeminiCostRateCard(
            input_usd_per_million_tokens=1.0,
            output_usd_per_million_tokens=2.0,
            rate_card_id="test-card-tokens",
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        ),
        _sdk_client=fake_sdk,
    )
    telemetry = client.generate_text("prompt").telemetry

    # Token counts are None because response had no usage_metadata
    assert telemetry.prompt_token_count is None
    assert telemetry.response_token_count is None
    assert telemetry.total_token_count is None
    assert telemetry.estimated_cost_usd is None

    evaluation = evaluate_model_call_budget(telemetry)

    assert evaluation.latency_status == "PASS"
    assert evaluation.token_status == "NOT_RUN"
    assert evaluation.cost_status == "NOT_RUN"
    assert evaluation.overall_status == "NOT_RUN"
    assert evaluation.overall_status != "PASS"
    assert evaluation.overall_budget_pass is False
    assert "overall: NOT_RUN" in evaluation.details


def test_metrics_artifact_structure_and_json_serialization() -> None:
    fake_sdk = FakeSDKClient(
        responses=[
            make_successful_response(
                "response content",
                prompt_tokens=20,
                response_tokens=10,
                total_tokens=30,
            )
        ]
    )
    client = BoundedGeminiClient(
        cost_rate_card=GeminiCostRateCard(
            input_usd_per_million_tokens=1.25,
            output_usd_per_million_tokens=2.5,
            rate_card_id="test-card-002",
            provenance_kind=RateProvenanceKind.TEST_FORMULA,
        ),
        _sdk_client=fake_sdk,
    )
    telemetry = client.generate_text("prompt content").telemetry
    artifact = build_model_metrics_artifact(telemetry)

    assert artifact["artifact_schema_version"] == "1.0.0"
    assert artifact["artifact_kind"] == "MODEL_CALL_METRICS"
    assert artifact["model_id"] == "gemini-3.6-flash"
    assert artifact["token_usage"]["total_tokens"] == 30
    assert artifact["cost_telemetry"]["cost_status"] == "CALCULATED"
    assert artifact["cost_telemetry"]["rate_card_id"] == "test-card-002"
    assert artifact["cost_telemetry"]["provider_pricing_calibrated"] is False
    assert artifact["budget_evaluation"]["overall_status"] == "PASS"
    assert artifact["budget_evaluation"]["overall_budget_pass"] is True

    # Deterministic JSON export
    json_str = export_metrics_artifact_json(telemetry)
    parsed = json.loads(json_str)
    assert parsed["artifact_kind"] == "MODEL_CALL_METRICS"
    assert parsed["call_id"] == telemetry.call_id
    assert parsed["cost_telemetry"]["provider_pricing_calibrated"] is False
    assert parsed["budget_evaluation"]["overall_status"] == "PASS"


def test_metrics_are_non_secret_and_do_not_store_prompt_or_response_text() -> None:
    prompt = "sensitive user prompt content with private reasoning"
    response_text = "sensitive model response content with confidential notes"
    fake_sdk = FakeSDKClient(responses=[make_successful_response(response_text)])
    client = BoundedGeminiClient(_sdk_client=fake_sdk)

    telemetry = client.generate_text(prompt).telemetry
    serialized_telemetry = str(asdict(telemetry))
    artifact_json = export_metrics_artifact_json(telemetry)

    assert prompt not in serialized_telemetry
    assert response_text not in serialized_telemetry
    assert prompt not in artifact_json
    assert response_text not in artifact_json
    assert "prompt_token_count" in serialized_telemetry
    assert "retry_count" in serialized_telemetry


def test_existing_latency_and_output_bounds_remain_enforced() -> None:
    client = BoundedGeminiClient(
        timeout_seconds=20,
        max_output_tokens=2048,
        _sdk_client=FakeSDKClient(),
    )

    assert 1 <= client.timeout_seconds <= 60
    assert 1 <= client.max_output_tokens <= 8192
