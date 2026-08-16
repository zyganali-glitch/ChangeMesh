"""ChangeMesh Core Module.

Contains core components including the canonical BoundedGeminiClient.
"""

from src.core.gemini_client import (
    CANONICAL_LOCATION,
    CANONICAL_MODEL_ID,
    CANONICAL_PROVIDER,
    CANONICAL_SAFETY_SETTINGS,
    DEFAULT_BACKOFF_MULTIPLIER,
    DEFAULT_INITIAL_RETRY_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_PROJECT_ID,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_ATTEMPTS_CEILING,
    MAX_TIMEOUT_SECONDS,
    MAX_TOKEN_CEILING,
    MIN_ATTEMPTS_FLOOR,
    MIN_TIMEOUT_SECONDS,
    MIN_TOKEN_FLOOR,
    RETRYABLE_STATUS_CODES,
    BoundedGeminiClient,
    ModelAPIError,
    ModelCallTelemetry,
    ModelClientError,
    ModelConfigurationError,
    ModelEmptyResponseError,
    ModelInitializationError,
    ModelResponse,
    ModelRetryExhaustedError,
    ModelSafetyBlockedError,
    ModelTimeoutError,
)

__all__ = [
    # Canonical Client
    "BoundedGeminiClient",
    # Constants & Bounds
    "CANONICAL_MODEL_ID",
    "CANONICAL_PROVIDER",
    "CANONICAL_LOCATION",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_TIMEOUT_SECONDS",
    "MIN_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "MIN_TOKEN_FLOOR",
    "MAX_TOKEN_CEILING",
    "DEFAULT_MAX_ATTEMPTS",
    "MAX_ATTEMPTS_CEILING",
    "MIN_ATTEMPTS_FLOOR",
    "DEFAULT_INITIAL_RETRY_DELAY_SECONDS",
    "DEFAULT_BACKOFF_MULTIPLIER",
    "DEFAULT_MAX_RETRY_DELAY_SECONDS",
    "RETRYABLE_STATUS_CODES",
    "CANONICAL_SAFETY_SETTINGS",
    # Telemetry & Response Models
    "ModelCallTelemetry",
    "ModelResponse",
    # Exceptions
    "ModelClientError",
    "ModelConfigurationError",
    "ModelInitializationError",
    "ModelTimeoutError",
    "ModelRetryExhaustedError",
    "ModelAPIError",
    "ModelSafetyBlockedError",
    "ModelEmptyResponseError",
]
