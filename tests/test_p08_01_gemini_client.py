"""Tests for P-08.01 Bounded Gemini Model Client.

Validates:
1. Canonical configuration (gemini-3.6-flash, Vertex AI provider, project/location wiring,
   timeouts, retries, token caps, safety settings).
2. Non-bypassability (model immutability, timeout/retry/token bounds enforcement,
   safety immutability, no raw client exposure).
3. Failure behavior (transient retries, retry exhaustion, non-retryable immediate fail-closed,
   safety block, empty response, closed client).
4. Non-secret telemetry (correlation IDs, attempts, duration, token usage,
   0 secrets, 0 prompt text, 0 response text).
5. Client lifecycle (close, context manager, resource cleanup).
6. Architectural boundaries (0 Google SDK imports in domain/contracts,
   single model client owner in src/).
"""

from __future__ import annotations

import ast
import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
import pytest
from google.genai import errors, types

from src.core.gemini_client import (
    CANONICAL_LOCATION,
    CANONICAL_MODEL_ID,
    CANONICAL_PROVIDER,
    CANONICAL_SAFETY_SETTINGS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_PROJECT_ID,
    DEFAULT_TIMEOUT_SECONDS,
    BoundedGeminiClient,
    ModelAPIError,
    ModelCallTelemetry,
    ModelClientError,
    ModelConfigurationError,
    ModelEmptyResponseError,
    ModelRetryExhaustedError,
    ModelSafetyBlockedError,
    ModelTimeoutError,
)


# --- Test Doubles / Fixtures ---
class FakeModels:
    """Configurable FakeModels double for google.genai.Client.models."""

    def __init__(
        self,
        *,
        responses: Optional[list[Any]] = None,
        exceptions: Optional[list[Exception]] = None,
    ) -> None:
        self.responses = list(responses or [])
        self.exceptions = list(exceptions or [])
        self.call_history: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        self.call_history.append({"model": model, "contents": contents, "config": config})
        if self.exceptions:
            exc = self.exceptions.pop(0)
            raise exc
        if self.responses:
            return self.responses.pop(0)
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[types.Part.from_text(text="Default fake generated text.")]
                    ),
                    finish_reason=types.FinishReason.STOP,
                )
            ],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10,
                candidates_token_count=5,
                total_token_count=15,
            ),
        )


class FakeSDKClient:
    """Configurable FakeSDKClient double for google.genai.Client."""

    def __init__(
        self,
        *,
        responses: Optional[list[Any]] = None,
        exceptions: Optional[list[Exception]] = None,
    ) -> None:
        self.models = FakeModels(responses=responses, exceptions=exceptions)
        self.closed: bool = False

    def close(self) -> None:
        self.closed = True


def make_successful_response(
    text: str = "Test model response text.",
    *,
    prompt_tokens: int = 15,
    response_tokens: int = 8,
    total_tokens: int = 23,
    finish_reason: types.FinishReason = types.FinishReason.STOP,
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(parts=[types.Part.from_text(text=text)]),
                finish_reason=finish_reason,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt_tokens,
            candidates_token_count=response_tokens,
            total_token_count=total_tokens,
        ),
    )


# ==============================================================================
# 1. Canonical Configuration Tests
# ==============================================================================
class TestCanonicalConfiguration:
    """Validates canonical model authority, defaults, and immutability."""

    def test_default_initialization_uses_canonical_settings(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        assert client.model_id == CANONICAL_MODEL_ID
        assert client.model_id == "gemini-3.6-flash"
        assert client.provider == CANONICAL_PROVIDER
        assert client.provider == "vertexai"
        assert client.location == CANONICAL_LOCATION
        assert client.location == "global"
        assert client.project == DEFAULT_PROJECT_ID
        assert client.project == "project-af5e1c99-3bc4-424f-b53"
        assert client.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
        assert client.timeout_seconds == 30.0
        assert client.max_attempts == DEFAULT_MAX_ATTEMPTS
        assert client.max_attempts == 3
        assert client.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS
        assert client.max_output_tokens == 4096
        assert not client.is_closed

    def test_custom_project_and_location_wiring(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(
            project="custom-corp-project",
            location="europe-west3",
            _sdk_client=fake_sdk,
        )
        assert client.project == "custom-corp-project"
        assert client.location == "europe-west3"

    def test_env_project_and_location_wiring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-project-123")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)
        assert client.project == "env-project-123"
        assert client.location == "us-central1"

    def test_safety_settings_are_immutable_and_cover_all_harm_categories(self) -> None:
        assert len(CANONICAL_SAFETY_SETTINGS) == 5
        categories = {s.category for s in CANONICAL_SAFETY_SETTINGS}
        assert types.HarmCategory.HARM_CATEGORY_HARASSMENT in categories
        assert types.HarmCategory.HARM_CATEGORY_HATE_SPEECH in categories
        assert types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT in categories
        assert types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT in categories
        assert types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY in categories

        for setting in CANONICAL_SAFETY_SETTINGS:
            assert setting.threshold == types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE


# ==============================================================================
# 2. Non-Bypassability Tests
# ==============================================================================
class TestNonBypassability:
    """Validates that callers cannot override model, weaken bounds, or bypass safety."""

    def test_caller_cannot_override_model_id(self) -> None:
        fake_sdk = FakeSDKClient()
        with pytest.raises(ModelConfigurationError, match="Unapproved model override"):
            BoundedGeminiClient(model_id="gemini-1.5-pro", _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="Unapproved model override"):
            BoundedGeminiClient(model_id="gpt-4o", _sdk_client=fake_sdk)

    def test_env_cannot_specify_unapproved_gemini_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-flash")
        fake_sdk = FakeSDKClient()
        with pytest.raises(
            ModelConfigurationError, match="Unapproved GEMINI_MODEL environment configuration"
        ):
            BoundedGeminiClient(_sdk_client=fake_sdk)

    def test_caller_cannot_disable_or_set_invalid_timeout(self) -> None:
        fake_sdk = FakeSDKClient()
        # Non-positive or below min bound
        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=0.0, _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=-5.0, _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=0.5, _sdk_client=fake_sdk)

        # Above max bound
        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=60.1, _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=float("inf"), _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=float("nan"), _sdk_client=fake_sdk)

    def test_caller_cannot_make_retry_unbounded(self) -> None:
        fake_sdk = FakeSDKClient()
        with pytest.raises(ModelConfigurationError, match="max_attempts"):
            BoundedGeminiClient(max_attempts=0, _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="max_attempts"):
            BoundedGeminiClient(max_attempts=-1, _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="max_attempts"):
            BoundedGeminiClient(max_attempts=4, _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="max_attempts"):
            BoundedGeminiClient(max_attempts=100, _sdk_client=fake_sdk)

    def test_caller_cannot_raise_token_ceiling_outside_policy(self) -> None:
        fake_sdk = FakeSDKClient()
        with pytest.raises(ModelConfigurationError, match="max_output_tokens"):
            BoundedGeminiClient(max_output_tokens=0, _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="max_output_tokens"):
            BoundedGeminiClient(max_output_tokens=-10, _sdk_client=fake_sdk)
        with pytest.raises(ModelConfigurationError, match="max_output_tokens"):
            BoundedGeminiClient(max_output_tokens=8193, _sdk_client=fake_sdk)

    def test_generate_text_rejects_empty_or_malformed_prompt(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="Prompt must be a non-empty string"):
            client.generate_text("")

        with pytest.raises(ModelConfigurationError, match="Prompt must be a non-empty string"):
            client.generate_text("   \n\t  ")

        with pytest.raises(ModelConfigurationError, match="Prompt must be a non-empty string"):
            client.generate_text(None)  # type: ignore[arg-type]

    def test_generate_text_rejects_per_call_override_above_configured_bounds(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(
            timeout_seconds=20.0,
            max_output_tokens=2048,
            _sdk_client=fake_sdk,
        )

        # Timeout above client bound
        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            client.generate_text("Hello", timeout_seconds=25.0)

        # Tokens above client bound
        with pytest.raises(ModelConfigurationError, match="max_output_tokens"):
            client.generate_text("Hello", max_output_tokens=4096)

    def test_underlying_raw_sdk_client_not_exposed_in_public_api(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        # No public client or sdk attribute
        assert not hasattr(client, "client")
        assert not hasattr(client, "sdk_client")
        assert not hasattr(client, "models")


# ==============================================================================
# 3. Successful Generation & Config Dispatch Tests
# ==============================================================================
class TestSuccessfulGeneration:
    """Validates successful model calls, parameter passing, and response models."""

    def test_generate_text_passes_canonical_config_to_sdk(self) -> None:
        fake_sdk = FakeSDKClient(
            responses=[make_successful_response("Analysis verified: schema change is safe.")]
        )
        client = BoundedGeminiClient(
            project="test-proj-456",
            location="global",
            timeout_seconds=15.0,
            max_output_tokens=1024,
            _sdk_client=fake_sdk,
        )

        resp = client.generate_text(
            "Verify the following schema change...",
            system_instruction="You are a schema verification specialist.",
            max_output_tokens=512,
            timeout_seconds=10.0,
        )

        assert resp.text == "Analysis verified: schema change is safe."
        assert resp.model_id == "gemini-3.6-flash"
        assert resp.finish_reason == "STOP"
        assert resp.prompt_tokens == 15
        assert resp.response_tokens == 8
        assert resp.total_tokens == 23

        # Verify call history on fake models
        assert len(fake_sdk.models.call_history) == 1
        call = fake_sdk.models.call_history[0]
        assert call["model"] == "gemini-3.6-flash"
        assert call["contents"] == "Verify the following schema change..."

        config: types.GenerateContentConfig = call["config"]
        assert config.max_output_tokens == 512
        assert config.system_instruction == "You are a schema verification specialist."
        assert config.http_options is not None
        assert config.http_options.timeout == 10000  # 10s -> 10000ms
        assert config.safety_settings is not None
        assert len(config.safety_settings) == 5


# ==============================================================================
# 4. Failure Behavior & Retry Semantics Tests
# ==============================================================================
class TestFailureBehaviorAndRetries:
    """Validates deterministic retry bounds, status handling, and fail-closed semantics."""

    def test_transient_429_retries_and_succeeds_on_second_attempt(self) -> None:
        sleep_calls: list[float] = []
        api_error_429 = errors.APIError(code=429, response_json={"message": "ResourceExhausted"})
        success_resp = make_successful_response("Success after retry.")

        fake_sdk = FakeSDKClient(
            exceptions=[api_error_429],
            responses=[success_resp],
        )

        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda s: sleep_calls.append(s),
        )

        resp = client.generate_text("Test prompt")
        assert resp.text == "Success after retry."
        assert resp.telemetry.attempts == 2
        assert resp.telemetry.final_outcome == "SUCCESS"
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 0.5  # default initial delay

    def test_transient_503_retries_and_fails_after_exhaustion(self) -> None:
        sleep_calls: list[float] = []
        api_error_503 = errors.APIError(code=503, response_json={"message": "ServiceUnavailable"})

        fake_sdk = FakeSDKClient(
            exceptions=[api_error_503, api_error_503, api_error_503],
        )

        client = BoundedGeminiClient(
            max_attempts=3,
            _sdk_client=fake_sdk,
            _sleep_fn=lambda s: sleep_calls.append(s),
        )

        with pytest.raises(ModelRetryExhaustedError, match="retry exhausted after 3 attempts"):
            client.generate_text("Test prompt")

        assert len(sleep_calls) == 2
        assert len(client.telemetry_history) == 1
        record = client.telemetry_history[0]
        assert record.attempts == 3
        assert record.final_outcome == "RETRY_EXHAUSTED"
        assert record.error_status_code == 503

    def test_network_connection_error_retries_to_bound(self) -> None:
        sleep_calls: list[float] = []
        connect_err = httpx.ConnectError("Connection refused by peer")

        fake_sdk = FakeSDKClient(
            exceptions=[connect_err, connect_err, connect_err],
        )

        client = BoundedGeminiClient(
            max_attempts=3,
            _sdk_client=fake_sdk,
            _sleep_fn=lambda s: sleep_calls.append(s),
        )

        with pytest.raises(
            ModelRetryExhaustedError, match="network connection retry exhausted after 3 attempts"
        ):
            client.generate_text("Test prompt")

        assert len(sleep_calls) == 2
        assert client.telemetry_history[0].final_outcome == "RETRY_EXHAUSTED"
        assert client.telemetry_history[0].error_status_code == 503

    def test_non_retryable_400_bad_request_fails_immediately_on_first_attempt(self) -> None:
        sleep_calls: list[float] = []
        api_error_400 = errors.APIError(code=400, response_json={"message": "InvalidArgument"})

        fake_sdk = FakeSDKClient(exceptions=[api_error_400])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda s: sleep_calls.append(s),
        )

        with pytest.raises(ModelAPIError, match="Non-retryable model API error") as exc_info:
            client.generate_text("Test prompt")

        assert exc_info.value.status_code == 400
        assert len(sleep_calls) == 0  # Zero retries
        assert client.telemetry_history[0].attempts == 1
        assert client.telemetry_history[0].final_outcome == "API_ERROR"
        assert client.telemetry_history[0].error_status_code == 400

    def test_non_retryable_403_permission_denied_fails_immediately(self) -> None:
        sleep_calls: list[float] = []
        api_error_403 = errors.APIError(code=403, response_json={"message": "PermissionDenied"})

        fake_sdk = FakeSDKClient(exceptions=[api_error_403])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda s: sleep_calls.append(s),
        )

        with pytest.raises(ModelAPIError) as exc_info:
            client.generate_text("Test prompt")

        assert exc_info.value.status_code == 403
        assert len(sleep_calls) == 0
        assert client.telemetry_history[0].attempts == 1
        assert client.telemetry_history[0].final_outcome == "API_ERROR"

    def test_timeout_fails_closed_with_model_timeout_error(self) -> None:
        sleep_calls: list[float] = []
        timeout_err = httpx.TimeoutException("Read timed out")

        fake_sdk = FakeSDKClient(exceptions=[timeout_err, timeout_err, timeout_err])
        client = BoundedGeminiClient(
            timeout_seconds=5.0,
            max_attempts=3,
            _sdk_client=fake_sdk,
            _sleep_fn=lambda s: sleep_calls.append(s),
        )

        with pytest.raises(ModelTimeoutError, match="exceeded timeout of 5.0s after 3 attempts"):
            client.generate_text("Test prompt")

        assert len(sleep_calls) == 2
        record = client.telemetry_history[0]
        assert record.final_outcome == "TIMEOUT"
        assert record.error_status_code == 504

    def test_safety_blocked_candidate_fails_closed_immediately(self) -> None:
        safety_response = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    finish_reason=types.FinishReason.SAFETY,
                    safety_ratings=[
                        types.SafetyRating(
                            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            probability=types.HarmProbability.HIGH,
                            blocked=True,
                        )
                    ],
                )
            ]
        )

        fake_sdk = FakeSDKClient(responses=[safety_response])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(ModelSafetyBlockedError, match="blocked by safety filter") as exc_info:
            client.generate_text("Test prompt")

        assert exc_info.value.finish_reason == "SAFETY"
        assert exc_info.value.safety_ratings is not None
        record = client.telemetry_history[0]
        assert record.attempts == 1
        assert record.final_outcome == "SAFETY_BLOCKED"
        assert record.finish_reason == "SAFETY"

    def test_safety_blocked_prompt_feedback_fails_closed_immediately(self) -> None:
        feedback_response = types.GenerateContentResponse(
            candidates=[],
            prompt_feedback=types.GenerateContentResponsePromptFeedback(
                block_reason=types.BlockedReason.SAFETY,
                safety_ratings=[
                    types.SafetyRating(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        probability=types.HarmProbability.HIGH,
                        blocked=True,
                    )
                ],
            ),
        )

        fake_sdk = FakeSDKClient(responses=[feedback_response])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(
            ModelSafetyBlockedError, match="prompt blocked by safety filter"
        ) as exc_info:
            client.generate_text("Test prompt")

        assert exc_info.value.block_reason is not None
        record = client.telemetry_history[0]
        assert record.attempts == 1
        assert record.final_outcome == "SAFETY_BLOCKED"

    def test_empty_candidates_response_fails_closed(self) -> None:
        empty_response = types.GenerateContentResponse(candidates=[])

        fake_sdk = FakeSDKClient(responses=[empty_response])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(ModelEmptyResponseError, match="returned no candidate outputs"):
            client.generate_text("Test prompt")

        record = client.telemetry_history[0]
        assert record.final_outcome == "EMPTY_RESPONSE"

    def test_empty_candidate_text_fails_closed(self) -> None:
        empty_text_response = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[types.Part.from_text(text="")]),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        )

        fake_sdk = FakeSDKClient(responses=[empty_text_response])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(ModelEmptyResponseError, match="candidate contained empty text content"):
            client.generate_text("Test prompt")

        record = client.telemetry_history[0]
        assert record.final_outcome == "EMPTY_RESPONSE"


# ==============================================================================
# 5. Telemetry & Secret Isolation Tests
# ==============================================================================
class TestTelemetryAndSecretIsolation:
    """Validates telemetry recording, field completeness, and zero credential leakage."""

    def test_telemetry_captures_operational_metadata_and_tokens(self) -> None:
        sink_records: list[ModelCallTelemetry] = []
        fake_sdk = FakeSDKClient(
            responses=[
                make_successful_response(
                    "Rehearsal outcome PASS",
                    prompt_tokens=42,
                    response_tokens=18,
                    total_tokens=60,
                )
            ]
        )

        client = BoundedGeminiClient(
            project="telemetry-project",
            location="global",
            telemetry_sink=lambda rec: sink_records.append(rec),
            _sdk_client=fake_sdk,
        )

        resp = client.generate_text("Rehearse change plan", call_id="corr-call-999")
        telemetry = resp.telemetry

        assert telemetry.call_id == "corr-call-999"
        assert telemetry.model_id == "gemini-3.6-flash"
        assert telemetry.provider == "vertexai"
        assert telemetry.project == "telemetry-project"
        assert telemetry.location == "global"
        assert telemetry.attempts == 1
        assert telemetry.final_outcome == "SUCCESS"
        assert telemetry.prompt_token_count == 42
        assert telemetry.response_token_count == 18
        assert telemetry.total_token_count == 60
        assert telemetry.finish_reason == "STOP"
        assert telemetry.duration_ms >= 0.0

        # ISO timestamp format check
        datetime.datetime.fromisoformat(telemetry.start_time_iso)
        datetime.datetime.fromisoformat(telemetry.end_time_iso)

        # Sink received exact record
        assert len(sink_records) == 1
        assert sink_records[0] == telemetry

    def test_telemetry_contains_zero_credentials_or_prompt_text(self) -> None:
        fake_sdk = FakeSDKClient(
            responses=[make_successful_response("Sensitive response data: customer record")]
        )
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        secret_prompt = "Prompt containing confidential secret: sk-proj-1234567890"
        resp = client.generate_text(secret_prompt)
        telemetry = resp.telemetry

        # Verify telemetry fields do NOT include prompt or response text
        telemetry_dict = {
            "call_id": telemetry.call_id,
            "model_id": telemetry.model_id,
            "provider": telemetry.provider,
            "project": telemetry.project,
            "location": telemetry.location,
            "start_time_iso": telemetry.start_time_iso,
            "end_time_iso": telemetry.end_time_iso,
            "duration_ms": telemetry.duration_ms,
            "attempts": telemetry.attempts,
            "final_outcome": telemetry.final_outcome,
            "error_class": telemetry.error_class,
            "error_status_code": telemetry.error_status_code,
            "prompt_token_count": telemetry.prompt_token_count,
            "response_token_count": telemetry.response_token_count,
            "total_token_count": telemetry.total_token_count,
            "finish_reason": telemetry.finish_reason,
        }

        serialized = str(telemetry_dict)
        assert "sk-proj" not in serialized
        assert "confidential" not in serialized
        assert "Sensitive response data" not in serialized
        assert "customer record" not in serialized
        assert "bearer" not in serialized.lower()
        assert "token" not in serialized.lower() or "count" in serialized.lower()

    def test_clear_telemetry_history(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        client.generate_text("Prompt 1")
        client.generate_text("Prompt 2")
        assert len(client.telemetry_history) == 2

        client.clear_telemetry_history()
        assert len(client.telemetry_history) == 0


# ==============================================================================
# 6. Client Lifecycle Tests
# ==============================================================================
class TestClientLifecycle:
    """Validates client close, context manager, and post-close failure."""

    def test_close_invokes_underlying_client_close(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)
        assert not client.is_closed
        assert not fake_sdk.closed

        client.close()
        assert client.is_closed
        assert fake_sdk.closed

        # Calling close multiple times is safe and idempotent
        client.close()
        assert client.is_closed

    def test_context_manager_closes_automatically_on_exit(self) -> None:
        fake_sdk = FakeSDKClient()
        with BoundedGeminiClient(_sdk_client=fake_sdk) as client:
            assert not client.is_closed
            assert not fake_sdk.closed
            resp = client.generate_text("Hello in context")
            assert resp.text is not None

        assert client.is_closed
        assert fake_sdk.closed

    def test_generate_text_on_closed_client_fails_closed(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)
        client.close()

        with pytest.raises(ModelClientError, match="Cannot invoke model on closed"):
            client.generate_text("Hello after close")


# ==============================================================================
# 7. Static Architectural Boundary Tests
# ==============================================================================
class TestArchitecturalBoundaries:
    """Validates inward dependency rule, zero SDK leakage into domain contracts,

    and absence of forbidden donor identifiers in new runtime code.
    """

    def test_domain_contracts_have_zero_google_sdk_imports(self) -> None:
        contracts_dir = Path(__file__).resolve().parent.parent / "domain" / "contracts"
        assert contracts_dir.is_dir()

        forbidden_prefixes = ("google", "google.genai", "google.adk", "vertexai")

        for py_file in contracts_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_prefixes:
                            assert not alias.name.startswith(forbidden), (
                                f"Forbidden import '{alias.name}' found in contract: {py_file}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for forbidden in forbidden_prefixes:
                            assert not node.module.startswith(forbidden), (
                                f"Forbidden from-import '{node.module}' in contract: {py_file}"
                            )

    def test_canonical_model_client_is_sole_model_call_owner_in_src(self) -> None:
        src_dir = Path(__file__).resolve().parent.parent / "src"
        assert src_dir.is_dir()

        allowed_genai_client_files = {"gemini_client.py"}

        for py_file in src_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check for direct genai.Client(...)
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr == "Client":
                        if py_file.name not in allowed_genai_client_files:
                            pytest.fail(
                                f"Direct SDK Client call found outside canonical client: {py_file}"
                            )

    def test_zero_forbidden_donor_identifiers_in_src_core(self) -> None:
        core_dir = Path(__file__).resolve().parent.parent / "src" / "core"
        assert core_dir.is_dir()

        forbidden_patterns = (
            "@openai",
            "gpt-5.6-sol",
            "MODEL_SEMANTIC_JUDGMENT",
            "InvoiceFlow",
            "school-saas",
            "validateZeroKitConfig",
        )

        for py_file in core_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                assert pattern not in content, (
                    f"Forbidden donor pattern '{pattern}' found in {py_file}"
                )
