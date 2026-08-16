"""P-08.05 latency, token, cost, and retry measurement tests."""

from __future__ import annotations

from dataclasses import asdict

import pytest
from google.genai import errors

from src.core.gemini_client import (
    BoundedGeminiClient,
    GeminiCostRateCard,
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
    client = BoundedGeminiClient(
        cost_rate_card=GeminiCostRateCard(
            input_usd_per_million_tokens=1.25,
            output_usd_per_million_tokens=2.5,
        ),
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
    assert telemetry.cost_status == "PASS"


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


def test_rate_card_rejects_invalid_or_unknown_pricing() -> None:
    with pytest.raises(ValueError, match="finite non-negative"):
        GeminiCostRateCard(input_usd_per_million_tokens=-1, output_usd_per_million_tokens=1)

    with pytest.raises(ValueError, match="finite non-negative"):
        GeminiCostRateCard(
            input_usd_per_million_tokens=float("nan"), output_usd_per_million_tokens=1
        )

    assert (
        GeminiCostRateCard(
            input_usd_per_million_tokens=1,
            output_usd_per_million_tokens=1,
        ).estimate_usd(None, 5)
        is None
    )


def test_metrics_are_non_secret_and_do_not_store_prompt_or_response_text() -> None:
    prompt = "bounded prompt content"
    response_text = "bounded response content"
    fake_sdk = FakeSDKClient(responses=[make_successful_response(response_text)])
    client = BoundedGeminiClient(_sdk_client=fake_sdk)

    telemetry = client.generate_text(prompt).telemetry
    serialized = str(asdict(telemetry))

    assert prompt not in serialized
    assert response_text not in serialized
    assert "prompt_token_count" in serialized
    assert "retry_count" in serialized


def test_existing_latency_and_output_bounds_remain_enforced() -> None:
    client = BoundedGeminiClient(
        timeout_seconds=20,
        max_output_tokens=2048,
        _sdk_client=FakeSDKClient(),
    )

    assert 1 <= client.timeout_seconds <= 60
    assert 1 <= client.max_output_tokens <= 8192
