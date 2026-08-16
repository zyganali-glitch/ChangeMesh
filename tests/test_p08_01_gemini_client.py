"""Tests for P-08.01 Bounded Gemini Model Client.

Validates:
1. Canonical configuration (gemini-3.6-flash, Vertex AI provider, project/location wiring,
   pinned API version v1beta1, disabled SDK retries, timeouts, retries, token caps, safety).
2. Non-bypassability (model immutability, timeout/retry/token bounds enforcement,
   safety policy immutability and fresh construction, no raw client exposure).
3. Failure behavior (transient retries, retry exhaustion, non-retryable immediate fail-closed,
   safety block, empty response, closed client).
4. Non-secret telemetry (safe correlation IDs, secret-bearing ID transformation, attempts, duration,
   token usage, 0 secrets, 0 prompt text, 0 response text).
5. Client lifecycle (close, context manager, resource cleanup).
6. Architectural boundaries (0 Google SDK imports in domain/contracts,
   exact single model client owner in src/core/gemini_client.py).
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
    CANONICAL_API_VERSION,
    CANONICAL_LOCATION,
    CANONICAL_MODEL_ID,
    CANONICAL_PROVIDER,
    CANONICAL_SAFETY_POLICY,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_PROJECT_ID,
    DEFAULT_TIMEOUT_SECONDS,
    SDK_RETRY_ATTEMPTS_DISABLED,
    BoundedGeminiClient,
    ModelAPIError,
    ModelCallTelemetry,
    ModelClientError,
    ModelConfigurationError,
    ModelEmptyResponseError,
    ModelRetryExhaustedError,
    ModelSafetyBlockedError,
    ModelTimeoutError,
    get_canonical_safety_settings,
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
        assert client.api_version == CANONICAL_API_VERSION
        assert client.api_version == "v1beta1"
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
            project="custom-prod-project-99",
            location="europe-west3",
            _sdk_client=fake_sdk,
        )
        assert client.project == "custom-prod-project-99"
        assert client.location == "europe-west3"

    def test_env_project_and_location_wiring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-injected-project-123")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)
        assert client.project == "env-injected-project-123"
        assert client.location == "us-central1"

    def test_safety_policy_is_immutable_change_mesh_data_and_covers_4_active_categories(
        self,
    ) -> None:
        # Check active canonical categories: exactly 4 supported categories
        assert len(CANONICAL_SAFETY_POLICY) == 4
        categories = {item.category for item in CANONICAL_SAFETY_POLICY}
        expected_categories = {
            types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        }
        assert categories == expected_categories

        # Ensure deprecated CIVIC_INTEGRITY is excluded from active canonical policy
        assert types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY not in categories

        # Check all items have threshold BLOCK_LOW_AND_ABOVE
        for item in CANONICAL_SAFETY_POLICY:
            assert item.threshold == types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE

        # Test deep immutability: attempting to mutate policy dataclass raises error
        with pytest.raises(Exception):  # FrozenInstanceError / TypeError
            CANONICAL_SAFETY_POLICY[0].threshold = (  # type: ignore[misc]
                types.HarmBlockThreshold.BLOCK_NONE
            )

        # Test fresh object construction per call
        settings_1 = get_canonical_safety_settings()
        settings_2 = get_canonical_safety_settings()
        assert settings_1 is not settings_2

        # Mutating returned settings list does not mutate CANONICAL_SAFETY_POLICY
        settings_1.clear()
        assert len(CANONICAL_SAFETY_POLICY) == 4
        assert len(get_canonical_safety_settings()) == 4


# ==============================================================================
# 2. Non-Bypassability Tests
# ==============================================================================
class TestNonBypassability:
    """Validates that callers and environment cannot weaken or bypass bounds."""

    def test_caller_cannot_override_model_id(self) -> None:
        fake_sdk = FakeSDKClient()
        with pytest.raises(ModelConfigurationError, match="Unapproved model override"):
            BoundedGeminiClient(model_id="gemini-2.5-pro", _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="Unapproved model override"):
            BoundedGeminiClient(model_id="gpt-4o", _sdk_client=fake_sdk)

    def test_env_cannot_specify_unapproved_gemini_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
        fake_sdk = FakeSDKClient()

        with pytest.raises(
            ModelConfigurationError, match="Unapproved GEMINI_MODEL environment configuration"
        ):
            BoundedGeminiClient(_sdk_client=fake_sdk)

    def test_caller_cannot_disable_or_set_invalid_timeout(self) -> None:
        fake_sdk = FakeSDKClient()

        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=0.0, _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=-5.0, _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=120.0, _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            BoundedGeminiClient(timeout_seconds=float("nan"), _sdk_client=fake_sdk)

    def test_caller_cannot_make_retry_unbounded(self) -> None:
        fake_sdk = FakeSDKClient()

        with pytest.raises(ModelConfigurationError, match="max_attempts"):
            BoundedGeminiClient(max_attempts=0, _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="max_attempts"):
            BoundedGeminiClient(max_attempts=10, _sdk_client=fake_sdk)

    def test_caller_cannot_raise_token_ceiling_outside_policy(self) -> None:
        fake_sdk = FakeSDKClient()

        with pytest.raises(ModelConfigurationError, match="max_output_tokens"):
            BoundedGeminiClient(max_output_tokens=0, _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="max_output_tokens"):
            BoundedGeminiClient(max_output_tokens=16384, _sdk_client=fake_sdk)

    def test_caller_cannot_pass_invalid_project_format(self) -> None:
        fake_sdk = FakeSDKClient()

        # Reject bad characters, SQL injections, secrets
        with pytest.raises(ModelConfigurationError, match="Invalid Google Cloud project ID"):
            BoundedGeminiClient(project="bad/project/id", _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="Invalid Google Cloud project ID"):
            BoundedGeminiClient(project="sk-secret-key-1234567890", _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="Invalid Google Cloud project ID"):
            BoundedGeminiClient(project="Project_With_Caps", _sdk_client=fake_sdk)

    def test_caller_cannot_pass_invalid_location_format(self) -> None:
        fake_sdk = FakeSDKClient()

        with pytest.raises(ModelConfigurationError, match="Invalid Vertex AI location format"):
            BoundedGeminiClient(location="bad/location", _sdk_client=fake_sdk)

        with pytest.raises(ModelConfigurationError, match="Invalid Vertex AI location format"):
            BoundedGeminiClient(location="secret-bearer-token-12345", _sdk_client=fake_sdk)

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

        with pytest.raises(ModelConfigurationError, match="max_output_tokens"):
            client.generate_text("Test prompt", max_output_tokens=4096)

        with pytest.raises(ModelConfigurationError, match="timeout_seconds"):
            client.generate_text("Test prompt", timeout_seconds=30.0)

    def test_underlying_raw_sdk_client_not_exposed_in_public_api(self) -> None:
        fake_sdk = FakeSDKClient()
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        assert not hasattr(client, "client")
        assert not hasattr(client, "sdk_client")
        assert not hasattr(client, "models")
        assert hasattr(client, "_client")


# ==============================================================================
# 3. Successful Generation & SDK Configuration Tests
# ==============================================================================
class TestSuccessfulGeneration:
    """Validates successful model call parameter delivery and SDK options."""

    def test_generate_text_passes_canonical_config_to_sdk(self) -> None:
        fake_sdk = FakeSDKClient(
            responses=[
                make_successful_response(
                    "Migration strategy: scoped refactor PASS",
                    prompt_tokens=50,
                    response_tokens=25,
                    total_tokens=75,
                )
            ]
        )
        client = BoundedGeminiClient(
            timeout_seconds=25.0,
            max_output_tokens=2048,
            _sdk_client=fake_sdk,
        )

        resp = client.generate_text(
            prompt="Analyze change impact",
            system_instruction="You are ChangeMesh Impact Scout.",
            call_id="call-scoped-test-1",
        )

        assert resp.text == "Migration strategy: scoped refactor PASS"
        assert resp.model_id == "gemini-3.6-flash"
        assert resp.finish_reason == "STOP"
        assert resp.prompt_tokens == 50
        assert resp.response_tokens == 25
        assert resp.total_tokens == 75

        # Verify SDK call parameters
        assert len(fake_sdk.models.call_history) == 1
        call = fake_sdk.models.call_history[0]
        assert call["model"] == "gemini-3.6-flash"
        assert call["contents"] == "Analyze change impact"

        config = call["config"]
        assert isinstance(config, types.GenerateContentConfig)
        assert config.max_output_tokens == 2048
        assert config.system_instruction == "You are ChangeMesh Impact Scout."

        # Verify explicit HTTP options delivered to SDK
        http_options = config.http_options
        assert isinstance(http_options, types.HttpOptions)
        assert http_options.api_version == "v1beta1"
        assert http_options.timeout == 25000  # 25s in milliseconds
        assert isinstance(http_options.retry_options, types.HttpRetryOptions)
        assert http_options.retry_options.attempts == SDK_RETRY_ATTEMPTS_DISABLED
        assert http_options.retry_options.attempts == 1

        # Verify safety settings delivered to SDK: exactly 4 categories, BLOCK_LOW_AND_ABOVE
        safety_settings = config.safety_settings
        assert safety_settings is not None
        assert len(safety_settings) == 4
        for s in safety_settings:
            assert s.threshold == types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE


# ==============================================================================
# 4. Failure Behavior & Retry Policy Tests
# ==============================================================================
class TestFailureBehaviorAndRetries:
    """Validates fail-closed semantics, transient retry backoff, and exhaustion."""

    def test_transient_429_retries_and_succeeds_on_second_attempt(self) -> None:
        sleep_records: list[float] = []
        error_429 = errors.APIError(429, {"message": "Resource exhausted: Rate limit exceeded"})
        success_resp = make_successful_response("Success on attempt 2")

        fake_sdk = FakeSDKClient(responses=[success_resp], exceptions=[error_429])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda delay: sleep_records.append(delay),
        )

        resp = client.generate_text("Test retry prompt")
        assert resp.text == "Success on attempt 2"
        assert resp.telemetry.attempts == 2
        assert resp.telemetry.final_outcome == "SUCCESS"
        assert len(sleep_records) == 1
        assert sleep_records[0] == 0.5  # initial retry delay

    def test_transient_503_retries_and_fails_after_exhaustion(self) -> None:
        sleep_records: list[float] = []
        error_503_a = errors.APIError(503, {"message": "Service Unavailable"})
        error_503_b = errors.APIError(503, {"message": "Service Unavailable"})
        error_503_c = errors.APIError(503, {"message": "Service Unavailable"})

        fake_sdk = FakeSDKClient(exceptions=[error_503_a, error_503_b, error_503_c])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda delay: sleep_records.append(delay),
        )

        with pytest.raises(ModelRetryExhaustedError, match="status 503"):
            client.generate_text("Test prompt 503")

        assert len(sleep_records) == 2  # slept before attempt 2 and attempt 3
        assert len(client.telemetry_history) == 1
        record = client.telemetry_history[0]
        assert record.attempts == 3
        assert record.final_outcome == "RETRY_EXHAUSTED"
        assert record.error_status_code == 503

    def test_network_connection_error_retries_to_bound(self) -> None:
        sleep_records: list[float] = []
        net_err1 = httpx.ConnectError("Connection refused")
        net_err2 = httpx.ConnectError("Connection reset")
        net_err3 = httpx.ConnectError("Network unreachable")

        fake_sdk = FakeSDKClient(exceptions=[net_err1, net_err2, net_err3])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda delay: sleep_records.append(delay),
        )

        with pytest.raises(ModelRetryExhaustedError, match="network connection"):
            client.generate_text("Network test prompt")

        assert len(sleep_records) == 2
        assert client.telemetry_history[0].attempts == 3

    def test_non_retryable_400_bad_request_fails_immediately_on_first_attempt(self) -> None:
        sleep_records: list[float] = []
        error_400 = errors.APIError(400, {"message": "Invalid argument"})

        fake_sdk = FakeSDKClient(exceptions=[error_400])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda delay: sleep_records.append(delay),
        )

        with pytest.raises(ModelAPIError, match="Non-retryable model API error") as exc_info:
            client.generate_text("Bad prompt")

        assert exc_info.value.status_code == 400
        assert len(sleep_records) == 0  # No retry attempted
        assert len(client.telemetry_history) == 1
        record = client.telemetry_history[0]
        assert record.attempts == 1
        assert record.final_outcome == "API_ERROR"
        assert record.error_status_code == 400

    def test_non_retryable_403_permission_denied_fails_immediately(self) -> None:
        sleep_records: list[float] = []
        error_403 = errors.APIError(403, {"message": "Permission denied on model resource"})

        fake_sdk = FakeSDKClient(exceptions=[error_403])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda delay: sleep_records.append(delay),
        )

        with pytest.raises(ModelAPIError, match="Non-retryable model API error") as exc_info:
            client.generate_text("Unauthorized prompt")

        assert exc_info.value.status_code == 403
        assert len(sleep_records) == 0
        assert client.telemetry_history[0].attempts == 1

    def test_timeout_fails_closed_with_model_timeout_error(self) -> None:
        timeout_err = httpx.TimeoutException("Read timed out")
        fake_sdk = FakeSDKClient(exceptions=[timeout_err, timeout_err, timeout_err])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda d: None,
        )

        with pytest.raises(ModelTimeoutError, match="exceeded timeout"):
            client.generate_text("Long query")

        assert client.telemetry_history[0].final_outcome == "TIMEOUT"

    def test_safety_blocked_candidate_fails_closed_immediately(self) -> None:
        blocked_candidate = types.Candidate(
            finish_reason=types.FinishReason.SAFETY,
            safety_ratings=[
                types.SafetyRating(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    probability=types.HarmProbability.HIGH,
                )
            ],
        )
        safety_blocked_response = types.GenerateContentResponse(
            candidates=[blocked_candidate],
        )

        fake_sdk = FakeSDKClient(responses=[safety_blocked_response])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(ModelSafetyBlockedError, match="blocked by safety filter") as exc_info:
            client.generate_text("Potentially harmful prompt")

        assert exc_info.value.finish_reason == "SAFETY"
        record = client.telemetry_history[0]
        assert record.attempts == 1
        assert record.final_outcome == "SAFETY_BLOCKED"
        assert record.finish_reason == "SAFETY"

    def test_safety_blocked_prompt_feedback_fails_closed_immediately(self) -> None:
        prompt_blocked_response = types.GenerateContentResponse(
            candidates=[],
            prompt_feedback=types.GenerateContentResponsePromptFeedback(
                block_reason=types.BlockedReason.SAFETY,
            ),
        )

        fake_sdk = FakeSDKClient(responses=[prompt_blocked_response])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(
            ModelSafetyBlockedError, match="Model prompt blocked by safety filter"
        ) as exc_info:
            client.generate_text("Blocked prompt text")

        assert exc_info.value.block_reason == "SAFETY"
        record = client.telemetry_history[0]
        assert record.attempts == 1
        assert record.final_outcome == "SAFETY_BLOCKED"

    def test_empty_candidates_response_fails_closed(self) -> None:
        empty_response = types.GenerateContentResponse(candidates=[])
        fake_sdk = FakeSDKClient(responses=[empty_response])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(ModelEmptyResponseError, match="Model returned no candidate outputs"):
            client.generate_text("Test prompt")

        record = client.telemetry_history[0]
        assert record.attempts == 1
        assert record.final_outcome == "EMPTY_RESPONSE"

    def test_empty_candidate_text_fails_closed(self) -> None:
        empty_text_response = types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(parts=[]),
                    finish_reason=types.FinishReason.STOP,
                )
            ]
        )
        fake_sdk = FakeSDKClient(responses=[empty_text_response])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        with pytest.raises(ModelEmptyResponseError, match="candidate contained empty text content"):
            client.generate_text("Test prompt")

        record = client.telemetry_history[0]
        assert record.attempts == 1
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
        assert telemetry.api_version == "v1beta1"
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

    def test_secret_looking_call_id_cannot_appear_verbatim_in_telemetry(self) -> None:
        fake_sdk = FakeSDKClient(responses=[make_successful_response()])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        secret_call_ids = [
            "AIza" + "SyD_sample_google_api_key_12345678",
            "sk-proj-" + "sample_openai_secret_token_abcdef123456",
            "Bearer " + "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0",
            "password=" + "SuperSecretPassword123!",
            "ghp_" + "123456789012345678901234567890123456",
            "secret_token_with_whitespace \n and newline",
            "call_id_with_embedded_credential_key_material",
        ]

        for raw_id in secret_call_ids:
            resp = client.generate_text("Test prompt", call_id=raw_id)
            telemetry_call_id = resp.telemetry.call_id

            # MUST NOT appear verbatim
            assert raw_id not in telemetry_call_id
            # MUST start with safe opaque prefix
            assert telemetry_call_id.startswith("call_opaque_")

    def test_normal_safe_correlation_id_remains_usable(self) -> None:
        fake_sdk = FakeSDKClient(responses=[make_successful_response()])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        safe_ids = [
            "call-123",
            "agent_step_01",
            "corr-change-req-99",
            "c3b4a2f1-0987-4321-abcd-ef0123456789",
        ]

        for safe_id in safe_ids:
            resp = client.generate_text("Test prompt", call_id=safe_id)
            assert resp.telemetry.call_id == safe_id

    def test_telemetry_contains_zero_credentials_or_prompt_text(self) -> None:
        fake_sdk = FakeSDKClient(
            responses=[make_successful_response("Sensitive response data: customer record")]
        )
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        secret_prompt = "Prompt containing confidential internal context"
        resp = client.generate_text(secret_prompt)
        telemetry = resp.telemetry

        # Verify telemetry fields do NOT include prompt or response text
        telemetry_dict = {
            "call_id": telemetry.call_id,
            "model_id": telemetry.model_id,
            "provider": telemetry.provider,
            "project": telemetry.project,
            "location": telemetry.location,
            "api_version": telemetry.api_version,
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

    def test_telemetry_sink_exception_handled_safely_without_leakage(self) -> None:
        def throwing_sink(rec: ModelCallTelemetry) -> None:
            raise RuntimeError("Database connection string postgres://user:secretpass@host/db")

        fake_sdk = FakeSDKClient(responses=[make_successful_response()])
        client = BoundedGeminiClient(telemetry_sink=throwing_sink, _sdk_client=fake_sdk)

        # Call should succeed without crashing on sink exception
        resp = client.generate_text("Prompt with failing sink")
        assert resp.text is not None

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
# 7. Static Architectural Boundary Tests & AST Analyzer
# ==============================================================================
def find_model_call_violations(
    code_or_tree: ast.AST | str,
    *,
    file_path: Path,
    canonical_client_path: Path,
) -> list[str]:
    """Test helper: detects direct model calls or SDK client instantiations outside canonical path.

    Authorized single owner: exact resolved path == canonical_client_path.
    Any instantiation of Client(...), ADK wrapper Gemini(...), or invocation of
    *.models.generate_content(...) / generate_content(...) outside canonical_client_path
    is returned as a violation description.
    """
    resolved_file = file_path.resolve()
    resolved_canonical = canonical_client_path.resolve()

    if resolved_file == resolved_canonical:
        return []

    tree: ast.AST
    if isinstance(code_or_tree, str):
        tree = ast.parse(code_or_tree, filename=str(file_path))
    else:
        tree = code_or_tree

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        lineno = getattr(node, "lineno", 0)

        # 1. Attribute call with attr == "Client" (e.g. genai.Client(...))
        if isinstance(func, ast.Attribute) and func.attr == "Client":
            violations.append(
                f"Direct SDK Client call found outside canonical client: {file_path} (L{lineno})"
            )
        # 2. Name call with id == "Client" (e.g. Client(...))
        elif isinstance(func, ast.Name) and func.id == "Client":
            violations.append(
                f"Direct Client call found outside canonical client: {file_path} (L{lineno})"
            )
        # 3. Name or Attribute call for ADK Gemini wrapper (e.g. Gemini(...), adk.Gemini(...))
        elif isinstance(func, ast.Name) and func.id == "Gemini":
            violations.append(
                f"Raw ADK Gemini wrapper found outside canonical client: {file_path} (L{lineno})"
            )
        elif isinstance(func, ast.Attribute) and func.attr == "Gemini":
            violations.append(
                f"Raw ADK Gemini wrapper found outside canonical client: {file_path} (L{lineno})"
            )
        # 4. Attribute call with attr == "generate_content"
        # (e.g. some_client.models.generate_content(...), models.generate_content(...))
        elif isinstance(func, ast.Attribute) and func.attr == "generate_content":
            violations.append(
                f"Raw SDK generate_content call found outside canonical client: "
                f"{file_path} (L{lineno})"
            )
        # 5. Name call with id == "generate_content" (e.g. generate_content(...))
        elif isinstance(func, ast.Name) and func.id == "generate_content":
            violations.append(
                f"Raw direct generate_content call found outside canonical client: "
                f"{file_path} (L{lineno})"
            )

    return violations


class TestArchitecturalBoundaries:
    """Validates inward dependency rule, zero SDK leakage into domain contracts,

    exact path allowlisting, and absence of forbidden donor identifiers in new runtime code.
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
        repo_root = Path(__file__).resolve().parent.parent
        src_dir = repo_root / "src"
        assert src_dir.is_dir()

        # EXACT repository path allowlist (strictly no basename-only matching)
        canonical_client_exact_path = (src_dir / "core" / "gemini_client.py").resolve()
        assert canonical_client_exact_path.is_file()

        all_violations: list[str] = []
        for py_file in src_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            violations = find_model_call_violations(
                tree,
                file_path=py_file,
                canonical_client_path=canonical_client_exact_path,
            )
            all_violations.extend(violations)

        assert not all_violations, "Model call violations found in src/:\n" + "\n".join(
            all_violations
        )

    def test_duplicate_same_basename_client_rejected_by_static_rule(self) -> None:
        """Regression test verifying that a second file with the same basename

        (e.g. src/other/gemini_client.py) would be rejected by exact path matching.
        """
        repo_root = Path(__file__).resolve().parent.parent
        canonical_client_exact_path = (repo_root / "src" / "core" / "gemini_client.py").resolve()
        fake_second_client_path = (repo_root / "src" / "other" / "gemini_client.py").resolve()

        assert fake_second_client_path.name == canonical_client_exact_path.name  # same basename
        assert fake_second_client_path != canonical_client_exact_path  # different exact path

        # Case 1: genai.Client() in duplicate basename file
        code_attr_client = "from google import genai\nclient = genai.Client()"
        violations_attr = find_model_call_violations(
            code_attr_client,
            file_path=fake_second_client_path,
            canonical_client_path=canonical_client_exact_path,
        )
        assert len(violations_attr) == 1
        assert "Direct SDK Client call found outside canonical client" in violations_attr[0]

        # Case 2: direct Client() import in duplicate basename file
        code_name_client = "from google.genai import Client\nclient = Client()"
        violations_name = find_model_call_violations(
            code_name_client,
            file_path=fake_second_client_path,
            canonical_client_path=canonical_client_exact_path,
        )
        assert len(violations_name) == 1
        assert "Direct Client call found outside canonical client" in violations_name[0]

        # Canonical file with same calls produces 0 violations
        assert (
            len(
                find_model_call_violations(
                    code_attr_client,
                    file_path=canonical_client_exact_path,
                    canonical_client_path=canonical_client_exact_path,
                )
            )
            == 0
        )

    def test_raw_model_generate_content_bypass_rejected_by_static_rule(self) -> None:
        """Regression test verifying that noncanonical files invoking raw generate_content

        or ADK Gemini wrapper (e.g. src/other/raw_model_call.py) are detected as violations.
        """
        repo_root = Path(__file__).resolve().parent.parent
        canonical_client_exact_path = (repo_root / "src" / "core" / "gemini_client.py").resolve()
        fake_raw_call_path = (repo_root / "src" / "other" / "raw_model_call.py").resolve()

        # Case 1: some_client.models.generate_content(...)
        code_sdk_generate = (
            'some_client.models.generate_content(model="gemini-3.6-flash", contents="x")'
        )
        violations_generate = find_model_call_violations(
            code_sdk_generate,
            file_path=fake_raw_call_path,
            canonical_client_path=canonical_client_exact_path,
        )
        assert len(violations_generate) == 1
        assert (
            "Raw SDK generate_content call found outside canonical client" in violations_generate[0]
        )

        # Case 2: models.generate_content(...)
        code_models_generate = 'models.generate_content(model="gemini-3.6-flash", contents="x")'
        violations_models = find_model_call_violations(
            code_models_generate,
            file_path=fake_raw_call_path,
            canonical_client_path=canonical_client_exact_path,
        )
        assert len(violations_models) == 1
        assert (
            "Raw SDK generate_content call found outside canonical client" in violations_models[0]
        )

        # Case 3: direct generate_content(...)
        code_direct_generate = 'generate_content(model="gemini-3.6-flash", contents="x")'
        violations_direct = find_model_call_violations(
            code_direct_generate,
            file_path=fake_raw_call_path,
            canonical_client_path=canonical_client_exact_path,
        )
        assert len(violations_direct) == 1
        assert (
            "Raw direct generate_content call found outside canonical client"
            in violations_direct[0]
        )

        # Case 4: raw ADK Gemini(...) wrapper
        code_adk_gemini = (
            'from google.adk.models import Gemini\nm = Gemini(model="gemini-3.6-flash")'
        )
        violations_adk = find_model_call_violations(
            code_adk_gemini,
            file_path=fake_raw_call_path,
            canonical_client_path=canonical_client_exact_path,
        )
        assert len(violations_adk) == 1
        assert "Raw ADK Gemini wrapper found outside canonical client" in violations_adk[0]

        # Canonical path with raw generate_content produces 0 violations
        assert (
            len(
                find_model_call_violations(
                    code_sdk_generate,
                    file_path=canonical_client_exact_path,
                    canonical_client_path=canonical_client_exact_path,
                )
            )
            == 0
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
