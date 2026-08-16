"""ChangeMesh Canonical Bounded Gemini Model Client.

Single bounded model client boundary for all ChangeMesh runtime Gemini invocations.
Enforces exact model (gemini-3.6-flash), pinned API version (v1beta1), positive finite timeouts,
bounded retries (wrapper-only authority), token output caps, immutable safety settings,
non-secret telemetry with safe correlation identifiers, and fail-closed error handling.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Final, Optional

import httpx
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

# --- Frozen Model Authority & Configuration Constants ---
CANONICAL_MODEL_ID: Final[str] = "gemini-3.6-flash"
CANONICAL_API_VERSION: Final[str] = "v1beta1"
CANONICAL_PROVIDER: Final[str] = "vertexai"
CANONICAL_LOCATION: Final[str] = "global"
DEFAULT_PROJECT_ID: Final[str] = "project-af5e1c99-3bc4-424f-b53"

# --- Explicit SDK Retry Setting ---
SDK_RETRY_ATTEMPTS_DISABLED: Final[int] = 1

# --- Frozen Policy Bounds ---
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
MIN_TIMEOUT_SECONDS: Final[float] = 1.0
MAX_TIMEOUT_SECONDS: Final[float] = 60.0

DEFAULT_MAX_OUTPUT_TOKENS: Final[int] = 4096
MIN_TOKEN_FLOOR: Final[int] = 1
MAX_TOKEN_CEILING: Final[int] = 8192

DEFAULT_MAX_ATTEMPTS: Final[int] = 3
MAX_ATTEMPTS_CEILING: Final[int] = 3
MIN_ATTEMPTS_FLOOR: Final[int] = 1

DEFAULT_INITIAL_RETRY_DELAY_SECONDS: Final[float] = 0.5
DEFAULT_BACKOFF_MULTIPLIER: Final[float] = 2.0
DEFAULT_MAX_RETRY_DELAY_SECONDS: Final[float] = 2.0

RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 502, 503, 504})


# --- Immutable Canonical Safety Configuration ---
# Active, supported text harm categories for Vertex AI / gemini-3.6-flash in google-genai 2.18.1.
# Note: HARM_CATEGORY_CIVIC_INTEGRITY is officially deprecated in SDK 2.18.1
# ("Election filter is no longer supported") and is excluded from active canonical safety policy.
@dataclass(frozen=True)
class CanonicalSafetyPolicyItem:
    """Immutable ChangeMesh canonical safety policy item."""

    category: types.HarmCategory
    threshold: types.HarmBlockThreshold
    method: types.HarmBlockMethod = types.HarmBlockMethod.SEVERITY


CANONICAL_SAFETY_POLICY: Final[tuple[CanonicalSafetyPolicyItem, ...]] = (
    CanonicalSafetyPolicyItem(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
    CanonicalSafetyPolicyItem(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
    CanonicalSafetyPolicyItem(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
    CanonicalSafetyPolicyItem(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
)


def get_canonical_safety_settings() -> list[types.SafetySetting]:
    """Construct fresh SDK SafetySetting objects from the immutable canonical policy."""
    return [
        types.SafetySetting(
            category=item.category,
            threshold=item.threshold,
            method=item.method,
        )
        for item in CANONICAL_SAFETY_POLICY
    ]


# --- Telemetry Identifier & Secret Isolation Patterns ---
_PROJECT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]{4,28}[a-z0-9]$")
_LOCATION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9-]{2,30}$")
_SAFE_CALL_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_SUSPICIOUS_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)(?:key|token|secret|password|bearer|auth|credential)"),
    re.compile(r"(?i)(?:AIza[0-9A-Za-z-_]{35})"),
    re.compile(r"(?i)(?:sk-[a-zA-Z0-9]{20,})"),
    re.compile(r"(?i)(?:ghp_[a-zA-Z0-9]{36})"),
    re.compile(r"(?i)(?:ey[a-zA-Z0-9_-]{20,}\.ey[a-zA-Z0-9_-]{20,})"),
)


def sanitize_telemetry_call_id(raw_call_id: Optional[str]) -> str:
    """Sanitize or transform caller-provided correlation ID for safe telemetry.

    Ensures no secret-bearing, malformed, or unbounded strings appear verbatim
    in telemetry records. Safe correlation IDs are preserved, while secret-looking
    or malformed strings are safely transformed into non-reversible opaque digests.
    """
    if not raw_call_id or not isinstance(raw_call_id, str) or not raw_call_id.strip():
        return uuid.uuid4().hex

    stripped = raw_call_id.strip()

    is_format_safe = bool(_SAFE_CALL_ID_PATTERN.match(stripped))
    has_suspicious_pattern = any(p.search(stripped) for p in _SUSPICIOUS_SECRET_PATTERNS)

    if is_format_safe and not has_suspicious_pattern:
        return stripped

    # Transform unsafe or secret-bearing identifier into non-reversible opaque hash digest
    digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()[:16]
    return f"call_opaque_{digest}"


# --- Exception Hierarchy ---
class ModelClientError(Exception):
    """Base exception for all BoundedGeminiClient failures."""


class ModelConfigurationError(ModelClientError):
    """Raised when model client configuration is invalid or attempts unapproved overrides."""


class ModelInitializationError(ModelClientError):
    """Raised when underlying SDK client fails initialization or authentication."""


class ModelTimeoutError(ModelClientError):
    """Raised when a model call exceeds the explicit timeout bound."""


class ModelRetryExhaustedError(ModelClientError):
    """Raised when bounded transient retries are exhausted without success."""


class ModelAPIError(ModelClientError):
    """Raised for non-retryable provider/API errors (e.g. 400 Bad Request, 403 Forbidden)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.original_error = original_error


class ModelSafetyBlockedError(ModelClientError):
    """Raised when model response is blocked by safety filters."""

    def __init__(
        self,
        message: str,
        *,
        finish_reason: Optional[str] = None,
        block_reason: Optional[str] = None,
        safety_ratings: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.finish_reason = finish_reason
        self.block_reason = block_reason
        self.safety_ratings = safety_ratings


class ModelEmptyResponseError(ModelClientError):
    """Raised when model generates empty content or no candidates without explicit error."""


# --- Telemetry & Response Models ---
@dataclass(frozen=True)
class ModelCallTelemetry:
    """Non-secret telemetry record capturing model invocation operational metadata.

    Strictly forbids storing credential material, prompt contents, or response text.
    """

    call_id: str
    model_id: str
    provider: str
    project: Optional[str]
    location: Optional[str]
    api_version: str
    start_time_iso: str
    end_time_iso: str
    duration_ms: float
    attempts: int
    final_outcome: str  # e.g. "SUCCESS", "TIMEOUT", "RETRY_EXHAUSTED", "SAFETY_BLOCKED"
    error_class: Optional[str] = None
    error_status_code: Optional[int] = None
    prompt_token_count: Optional[int] = None
    response_token_count: Optional[int] = None
    total_token_count: Optional[int] = None
    finish_reason: Optional[str] = None


@dataclass(frozen=True)
class ModelResponse:
    """Bounded model response container."""

    text: str
    model_id: str
    finish_reason: str
    prompt_tokens: Optional[int]
    response_tokens: Optional[int]
    total_tokens: Optional[int]
    telemetry: ModelCallTelemetry


class BoundedGeminiClient:
    """Single canonical bounded model client for ChangeMesh Gemini invocations.

    Guarantees:
    - Exactly one canonical model: 'gemini-3.6-flash'.
    - Pinned API version: 'v1beta1'.
    - Provider path: Vertex AI / Google GenAI SDK.
    - Explicit positive finite timeouts (1.0s to 60.0s, default 30.0s).
    - Explicit bounded retries (wrapper is sole retry authority, max 3; SDK retry disabled).
    - Strict output token caps (1 to 8192, default 4096).
    - Strict immutable enterprise safety settings across all supported harm categories.
    - Zero secret/credential/prompt/response content leakage into telemetry.
    - Fail-closed semantics with zero silent fallback.
    - Private underlying SDK client, never exposed to callers.
    """

    def __init__(
        self,
        *,
        project: Optional[str] = None,
        location: Optional[str] = None,
        model_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_attempts: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        telemetry_sink: Optional[Callable[[ModelCallTelemetry], None]] = None,
        _sdk_client: Optional[Any] = None,
        _sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        """Initialize the bounded model client with verified constraints."""
        # 1. Model Authority Check
        if model_id is not None and model_id != CANONICAL_MODEL_ID:
            raise ModelConfigurationError(
                f"Unapproved model override '{model_id}'. "
                f"Only canonical model '{CANONICAL_MODEL_ID}' is permitted."
            )
        env_model = os.environ.get("GEMINI_MODEL")
        if env_model and env_model != CANONICAL_MODEL_ID:
            raise ModelConfigurationError(
                f"Unapproved GEMINI_MODEL environment configuration '{env_model}'. "
                f"Only canonical model '{CANONICAL_MODEL_ID}' is permitted."
            )
        self._model_id: str = CANONICAL_MODEL_ID

        # 2. Project Resolution and Format Validation
        resolved_project = project or os.environ.get("GOOGLE_CLOUD_PROJECT") or DEFAULT_PROJECT_ID
        if (
            not resolved_project
            or not isinstance(resolved_project, str)
            or not resolved_project.strip()
        ):
            raise ModelConfigurationError("Project ID cannot be empty.")
        clean_project = resolved_project.strip()
        if not _PROJECT_ID_PATTERN.match(clean_project) or any(
            p.search(clean_project) for p in _SUSPICIOUS_SECRET_PATTERNS
        ):
            raise ModelConfigurationError(
                f"Invalid Google Cloud project ID format '{clean_project}'."
            )
        self._project: str = clean_project

        # 3. Location Resolution and Format Validation
        resolved_location = (
            location or os.environ.get("GOOGLE_CLOUD_LOCATION") or CANONICAL_LOCATION
        )
        if (
            not resolved_location
            or not isinstance(resolved_location, str)
            or not resolved_location.strip()
        ):
            raise ModelConfigurationError("Location cannot be empty.")
        clean_location = resolved_location.strip()
        if not _LOCATION_PATTERN.match(clean_location) or any(
            p.search(clean_location) for p in _SUSPICIOUS_SECRET_PATTERNS
        ):
            raise ModelConfigurationError(f"Invalid Vertex AI location format '{clean_location}'.")
        self._location: str = clean_location

        # 4. Timeout Validation
        if timeout_seconds is None:
            self._timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
        else:
            if (
                isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or math.isnan(timeout_seconds)
                or math.isinf(timeout_seconds)
                or timeout_seconds < MIN_TIMEOUT_SECONDS
                or timeout_seconds > MAX_TIMEOUT_SECONDS
            ):
                raise ModelConfigurationError(
                    f"timeout_seconds ({timeout_seconds}) must be a finite number "
                    f"between {MIN_TIMEOUT_SECONDS}s and {MAX_TIMEOUT_SECONDS}s."
                )
            self._timeout_seconds = float(timeout_seconds)

        # 5. Max Attempts Validation
        if max_attempts is None:
            self._max_attempts: int = DEFAULT_MAX_ATTEMPTS
        else:
            if (
                isinstance(max_attempts, bool)
                or not isinstance(max_attempts, int)
                or max_attempts < MIN_ATTEMPTS_FLOOR
                or max_attempts > MAX_ATTEMPTS_CEILING
            ):
                raise ModelConfigurationError(
                    f"max_attempts ({max_attempts}) must be an integer between "
                    f"{MIN_ATTEMPTS_FLOOR} and {MAX_ATTEMPTS_CEILING}."
                )
            self._max_attempts = max_attempts

        # 6. Max Output Tokens Validation
        if max_output_tokens is None:
            self._max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
        else:
            if (
                isinstance(max_output_tokens, bool)
                or not isinstance(max_output_tokens, int)
                or max_output_tokens < MIN_TOKEN_FLOOR
                or max_output_tokens > MAX_TOKEN_CEILING
            ):
                raise ModelConfigurationError(
                    f"max_output_tokens ({max_output_tokens}) must be an integer between "
                    f"{MIN_TOKEN_FLOOR} and {MAX_TOKEN_CEILING}."
                )
            self._max_output_tokens = max_output_tokens

        # 7. Telemetry & Internal Utilities
        self._telemetry_sink: Optional[Callable[[ModelCallTelemetry], None]] = telemetry_sink
        self._sleep_fn: Callable[[float], None] = _sleep_fn or time.sleep
        self._telemetry_history: list[ModelCallTelemetry] = []
        self._closed: bool = False

        # 8. Underlying Client Initialization (Private / Injected)
        if _sdk_client is not None:
            self._client: Any = _sdk_client
        else:
            try:
                self._client = genai.Client(
                    vertexai=True,
                    project=self._project,
                    location=self._location,
                    http_options=types.HttpOptions(
                        api_version=CANONICAL_API_VERSION,
                        retry_options=types.HttpRetryOptions(attempts=SDK_RETRY_ATTEMPTS_DISABLED),
                    ),
                )
            except Exception as exc:
                raise ModelInitializationError(
                    f"Failed to initialize underlying google.genai.Client: {exc}"
                ) from exc

    # --- Read-Only Properties ---
    @property
    def model_id(self) -> str:
        """Canonical model ID."""
        return self._model_id

    @property
    def api_version(self) -> str:
        """Pinned canonical API version."""
        return CANONICAL_API_VERSION

    @property
    def provider(self) -> str:
        """Provider backend identifier."""
        return CANONICAL_PROVIDER

    @property
    def project(self) -> str:
        """Google Cloud project ID."""
        return self._project

    @property
    def location(self) -> str:
        """Vertex AI location."""
        return self._location

    @property
    def timeout_seconds(self) -> float:
        """Configured timeout bound in seconds."""
        return self._timeout_seconds

    @property
    def max_attempts(self) -> int:
        """Configured max attempts bound."""
        return self._max_attempts

    @property
    def max_output_tokens(self) -> int:
        """Configured output token budget ceiling."""
        return self._max_output_tokens

    @property
    def is_closed(self) -> bool:
        """Whether client has been closed."""
        return self._closed

    @property
    def telemetry_history(self) -> tuple[ModelCallTelemetry, ...]:
        """Immutable view of recorded telemetry history."""
        return tuple(self._telemetry_history)

    def clear_telemetry_history(self) -> None:
        """Clear recorded telemetry history."""
        self._telemetry_history.clear()

    # --- Main Execution Interface ---
    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        call_id: Optional[str] = None,
    ) -> ModelResponse:
        """Generate text from Gemini using canonical bounds and failure semantics.

        Args:
            prompt: Input text prompt.
            system_instruction: Optional system instruction text.
            max_output_tokens: Optional per-call token limit (cannot exceed client ceiling).
            timeout_seconds: Optional per-call timeout in seconds (cannot exceed client bound).
            call_id: Optional correlation identifier for telemetry.

        Returns:
            ModelResponse containing text, metadata, and telemetry.

        Raises:
            ModelClientError: On any failure, policy violation, or timeout.
        """
        if self._closed:
            raise ModelClientError("Cannot invoke model on closed BoundedGeminiClient.")

        if not isinstance(prompt, str) or not prompt.strip():
            raise ModelConfigurationError("Prompt must be a non-empty string.")

        if system_instruction is not None and not isinstance(system_instruction, str):
            raise ModelConfigurationError("system_instruction must be a string if provided.")

        # Resolve and validate per-call output tokens (cannot raise ceiling)
        if max_output_tokens is None:
            effective_max_tokens = self._max_output_tokens
        else:
            if (
                isinstance(max_output_tokens, bool)
                or not isinstance(max_output_tokens, int)
                or max_output_tokens < MIN_TOKEN_FLOOR
                or max_output_tokens > self._max_output_tokens
            ):
                raise ModelConfigurationError(
                    f"max_output_tokens ({max_output_tokens}) must be between {MIN_TOKEN_FLOOR} "
                    f"and client configured bound {self._max_output_tokens}."
                )
            effective_max_tokens = max_output_tokens

        # Resolve and validate per-call timeout (cannot raise ceiling)
        if timeout_seconds is None:
            effective_timeout = self._timeout_seconds
        else:
            if (
                isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or math.isnan(timeout_seconds)
                or math.isinf(timeout_seconds)
                or timeout_seconds < MIN_TIMEOUT_SECONDS
                or timeout_seconds > self._timeout_seconds
            ):
                raise ModelConfigurationError(
                    f"timeout_seconds ({timeout_seconds}) must be between {MIN_TIMEOUT_SECONDS}s "
                    f"and client configured bound {self._timeout_seconds}s."
                )
            effective_timeout = float(timeout_seconds)

        effective_call_id = sanitize_telemetry_call_id(call_id)

        start_time = datetime.datetime.now(datetime.timezone.utc)
        start_monotonic = time.monotonic()
        attempt = 0

        while attempt < self._max_attempts:
            attempt += 1
            try:
                # Fresh safety settings constructed internally per request from immutable policy
                config = types.GenerateContentConfig(
                    max_output_tokens=effective_max_tokens,
                    safety_settings=get_canonical_safety_settings(),
                    system_instruction=system_instruction if system_instruction else None,
                    http_options=types.HttpOptions(
                        api_version=CANONICAL_API_VERSION,
                        timeout=int(effective_timeout * 1000),
                        retry_options=types.HttpRetryOptions(attempts=SDK_RETRY_ATTEMPTS_DISABLED),
                    ),
                )

                response = self._client.models.generate_content(
                    model=self._model_id,
                    contents=prompt,
                    config=config,
                )

                if response is None:
                    raise ModelEmptyResponseError("Underlying model returned None response.")

                # Check prompt-level safety feedback
                if hasattr(response, "prompt_feedback") and response.prompt_feedback:
                    block_reason = getattr(response.prompt_feedback, "block_reason", None)
                    if block_reason:
                        block_reason_str = (
                            str(
                                block_reason.value
                                if hasattr(block_reason, "value")
                                else block_reason
                            )
                            if block_reason
                            else "SAFETY"
                        )
                        end_time = datetime.datetime.now(datetime.timezone.utc)
                        duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                        self._record_telemetry(
                            call_id=effective_call_id,
                            start_time=start_time,
                            end_time=end_time,
                            duration_ms=duration_ms,
                            attempts=attempt,
                            final_outcome="SAFETY_BLOCKED",
                            error_class="ModelSafetyBlockedError",
                            finish_reason=block_reason_str,
                        )
                        raise ModelSafetyBlockedError(
                            f"Model prompt blocked by safety filter: {block_reason_str}",
                            block_reason=block_reason_str,
                            safety_ratings=getattr(
                                response.prompt_feedback, "safety_ratings", None
                            ),
                        )

                # Check candidates
                candidates = getattr(response, "candidates", None)
                if not candidates:
                    end_time = datetime.datetime.now(datetime.timezone.utc)
                    duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                    self._record_telemetry(
                        call_id=effective_call_id,
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=duration_ms,
                        attempts=attempt,
                        final_outcome="EMPTY_RESPONSE",
                        error_class="ModelEmptyResponseError",
                    )
                    raise ModelEmptyResponseError("Model returned no candidate outputs.")

                candidate = candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)
                finish_reason_str = (
                    str(finish_reason.value if hasattr(finish_reason, "value") else finish_reason)
                    if finish_reason
                    else "STOP"
                )

                # Check candidate safety block
                is_safety_finish = (
                    finish_reason == types.FinishReason.SAFETY
                    or finish_reason_str.upper()
                    in {
                        "SAFETY",
                        "RECITATION",
                        "BLOCKLIST",
                        "PROHIBITED_CONTENT",
                        "SPII",
                        "IMAGE_SAFETY",
                    }
                )
                if is_safety_finish:
                    end_time = datetime.datetime.now(datetime.timezone.utc)
                    duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                    self._record_telemetry(
                        call_id=effective_call_id,
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=duration_ms,
                        attempts=attempt,
                        final_outcome="SAFETY_BLOCKED",
                        error_class="ModelSafetyBlockedError",
                        finish_reason=finish_reason_str,
                    )
                    raise ModelSafetyBlockedError(
                        f"Model candidate blocked by safety filter with finish reason "
                        f"'{finish_reason_str}'.",
                        finish_reason=finish_reason_str,
                        safety_ratings=getattr(candidate, "safety_ratings", None),
                    )

                # Extract response text
                text = ""
                if (
                    hasattr(candidate, "content")
                    and candidate.content
                    and getattr(candidate.content, "parts", None)
                ):
                    text_parts = [
                        getattr(p, "text", "")
                        for p in candidate.content.parts
                        if getattr(p, "text", None)
                    ]
                    text = "".join(text_parts)
                elif hasattr(response, "text") and response.text:
                    text = response.text

                if not text:
                    end_time = datetime.datetime.now(datetime.timezone.utc)
                    duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                    self._record_telemetry(
                        call_id=effective_call_id,
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=duration_ms,
                        attempts=attempt,
                        final_outcome="EMPTY_RESPONSE",
                        error_class="ModelEmptyResponseError",
                        finish_reason=finish_reason_str,
                    )
                    raise ModelEmptyResponseError(
                        "Model response candidate contained empty text content."
                    )

                # Extract token usage metadata
                prompt_tokens: Optional[int] = None
                response_tokens: Optional[int] = None
                total_tokens: Optional[int] = None
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    usage = response.usage_metadata
                    prompt_tokens = getattr(usage, "prompt_token_count", None)
                    response_tokens = getattr(usage, "candidates_token_count", None)
                    if response_tokens is None:
                        response_tokens = getattr(usage, "response_token_count", None)
                    total_tokens = getattr(usage, "total_token_count", None)

                end_time = datetime.datetime.now(datetime.timezone.utc)
                duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                telemetry = self._record_telemetry(
                    call_id=effective_call_id,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    attempts=attempt,
                    final_outcome="SUCCESS",
                    prompt_token_count=prompt_tokens,
                    response_token_count=response_tokens,
                    total_token_count=total_tokens,
                    finish_reason=finish_reason_str,
                )

                return ModelResponse(
                    text=text,
                    model_id=self._model_id,
                    finish_reason=finish_reason_str,
                    prompt_tokens=prompt_tokens,
                    response_tokens=response_tokens,
                    total_tokens=total_tokens,
                    telemetry=telemetry,
                )

            except (ModelSafetyBlockedError, ModelEmptyResponseError):
                # Deterministic content outcomes fail immediately without retry
                raise

            except (httpx.TimeoutException, TimeoutError) as exc:
                if attempt < self._max_attempts:
                    delay = min(
                        DEFAULT_INITIAL_RETRY_DELAY_SECONDS
                        * (DEFAULT_BACKOFF_MULTIPLIER ** (attempt - 1)),
                        DEFAULT_MAX_RETRY_DELAY_SECONDS,
                    )
                    self._sleep_fn(delay)
                    continue

                end_time = datetime.datetime.now(datetime.timezone.utc)
                duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                self._record_telemetry(
                    call_id=effective_call_id,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    attempts=attempt,
                    final_outcome="TIMEOUT",
                    error_class=type(exc).__name__,
                    error_status_code=504,
                )
                raise ModelTimeoutError(
                    f"Model call exceeded timeout of {effective_timeout}s after "
                    f"{attempt} attempts: {exc}"
                ) from exc

            except errors.APIError as exc:
                status_code = getattr(exc, "code", None)
                is_retryable = status_code in RETRYABLE_STATUS_CODES
                if is_retryable and attempt < self._max_attempts:
                    delay = min(
                        DEFAULT_INITIAL_RETRY_DELAY_SECONDS
                        * (DEFAULT_BACKOFF_MULTIPLIER ** (attempt - 1)),
                        DEFAULT_MAX_RETRY_DELAY_SECONDS,
                    )
                    self._sleep_fn(delay)
                    continue

                end_time = datetime.datetime.now(datetime.timezone.utc)
                duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                if is_retryable:
                    self._record_telemetry(
                        call_id=effective_call_id,
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=duration_ms,
                        attempts=attempt,
                        final_outcome="RETRY_EXHAUSTED",
                        error_class=type(exc).__name__,
                        error_status_code=status_code,
                    )
                    raise ModelRetryExhaustedError(
                        f"Model call retry exhausted after {attempt} attempts "
                        f"with status {status_code}: {exc}"
                    ) from exc
                else:
                    self._record_telemetry(
                        call_id=effective_call_id,
                        start_time=start_time,
                        end_time=end_time,
                        duration_ms=duration_ms,
                        attempts=attempt,
                        final_outcome="API_ERROR",
                        error_class=type(exc).__name__,
                        error_status_code=status_code,
                    )
                    raise ModelAPIError(
                        f"Non-retryable model API error (status {status_code}): {exc}",
                        status_code=status_code,
                        original_error=exc,
                    ) from exc

            except (httpx.ConnectError, httpx.NetworkError, ConnectionError) as exc:
                if attempt < self._max_attempts:
                    delay = min(
                        DEFAULT_INITIAL_RETRY_DELAY_SECONDS
                        * (DEFAULT_BACKOFF_MULTIPLIER ** (attempt - 1)),
                        DEFAULT_MAX_RETRY_DELAY_SECONDS,
                    )
                    self._sleep_fn(delay)
                    continue

                end_time = datetime.datetime.now(datetime.timezone.utc)
                duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                self._record_telemetry(
                    call_id=effective_call_id,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    attempts=attempt,
                    final_outcome="RETRY_EXHAUSTED",
                    error_class=type(exc).__name__,
                    error_status_code=503,
                )
                raise ModelRetryExhaustedError(
                    f"Model call network connection retry exhausted after {attempt} attempts: {exc}"
                ) from exc

            except Exception as exc:
                end_time = datetime.datetime.now(datetime.timezone.utc)
                duration_ms = (time.monotonic() - start_monotonic) * 1000.0
                self._record_telemetry(
                    call_id=effective_call_id,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    attempts=attempt,
                    final_outcome="API_ERROR",
                    error_class=type(exc).__name__,
                )
                raise ModelAPIError(
                    f"Unexpected model call failure: {exc}", original_error=exc
                ) from exc

        # Fallback if loop finishes unexpectedly without raising or returning
        end_time = datetime.datetime.now(datetime.timezone.utc)
        duration_ms = (time.monotonic() - start_monotonic) * 1000.0
        self._record_telemetry(
            call_id=effective_call_id,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            attempts=attempt,
            final_outcome="RETRY_EXHAUSTED",
            error_class="ModelRetryExhaustedError",
        )
        raise ModelRetryExhaustedError(f"Model call retry exhausted after {attempt} attempts.")

    def _record_telemetry(
        self,
        *,
        call_id: str,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        duration_ms: float,
        attempts: int,
        final_outcome: str,
        error_class: Optional[str] = None,
        error_status_code: Optional[int] = None,
        prompt_token_count: Optional[int] = None,
        response_token_count: Optional[int] = None,
        total_token_count: Optional[int] = None,
        finish_reason: Optional[str] = None,
    ) -> ModelCallTelemetry:
        record = ModelCallTelemetry(
            call_id=call_id,
            model_id=self._model_id,
            provider=CANONICAL_PROVIDER,
            project=self._project,
            location=self._location,
            api_version=CANONICAL_API_VERSION,
            start_time_iso=start_time.isoformat(),
            end_time_iso=end_time.isoformat(),
            duration_ms=round(duration_ms, 2),
            attempts=attempts,
            final_outcome=final_outcome,
            error_class=error_class,
            error_status_code=error_status_code,
            prompt_token_count=prompt_token_count,
            response_token_count=response_token_count,
            total_token_count=total_token_count,
            finish_reason=finish_reason,
        )
        self._telemetry_history.append(record)
        if self._telemetry_sink:
            try:
                self._telemetry_sink(record)
            except Exception as sink_err:
                logger.warning("Telemetry sink failed with exception %s", type(sink_err).__name__)
        return record

    # --- Lifecycle Management ---
    def close(self) -> None:
        """Close client and release underlying SDK resources."""
        if not self._closed:
            self._closed = True
            if hasattr(self._client, "close") and callable(self._client.close):
                try:
                    self._client.close()
                except Exception as exc:
                    logger.warning(
                        "Error while closing google.genai.Client: %s", type(exc).__name__
                    )

    def __enter__(self) -> BoundedGeminiClient:
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and close client."""
        self.close()
