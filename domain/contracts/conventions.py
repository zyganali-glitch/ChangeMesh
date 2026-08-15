"""ChangeMesh domain contracts — frozen machine conventions.

P-05.06: Canonical naming, enum, timestamp, hashing, redaction, and
serialization conventions for all ChangeMesh domain contracts.

Provider-neutral: no cloud vendor APIs, or runtime
adapter imports.  Standard library + Pydantic only.

These conventions are deterministic, locale-neutral, and testable.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Mapping, Sequence, Union

from pydantic import AfterValidator, BaseModel


# ===========================================================================
# 1. HASH ALGORITHM CONVENTION
# ===========================================================================

class HashAlgorithm(str, Enum):
    """Canonical content/artifact hashing algorithm.

    ChangeMesh freezes ONE canonical algorithm: SHA-256.
    The machine token is ``sha256`` — no aliases accepted.
    """

    SHA256 = "sha256"


# Digest format: exactly 64 lowercase hexadecimal characters.
_SHA256_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def is_valid_sha256_digest(digest: str) -> bool:
    """Return True if *digest* is a valid canonical SHA-256 hex string."""
    return bool(_SHA256_DIGEST_PATTERN.match(digest))


def sha256_hex(data: bytes) -> str:
    """Compute SHA-256 of *data* and return lowercase 64-char hex.

    Pure function.  No I/O, no file reads, no URL fetches, no mutation.
    """
    return hashlib.sha256(data).hexdigest()


# ===========================================================================
# 2. TIMESTAMP CONVENTION
# ===========================================================================

def normalize_utc_datetime(value: datetime) -> datetime:
    """Normalize a timezone-aware datetime to UTC.

    - Naive datetime → raises ``ValueError``.
    - Aware non-UTC → converted to UTC.
    - Aware UTC → returned with UTC tzinfo.

    Does not use system-local timezone.
    """
    if not isinstance(value, datetime):
        raise TypeError(f"Expected datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            "Naive datetime rejected: all domain timestamps must be "
            "timezone-aware"
        )
    return value.astimezone(timezone.utc)


UtcDateTime = Annotated[
    datetime,
    AfterValidator(normalize_utc_datetime),
]


# Canonical wire format: RFC 3339 / ISO-8601 UTC with fixed 6-digit
# microsecond precision and 'Z' suffix.
_CANONICAL_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_utc_timestamp(value: datetime) -> str:
    """Format a timezone-aware datetime to canonical UTC wire string.

    Output: ``YYYY-MM-DDTHH:MM:SS.ffffffZ``  (always 6 microsecond digits).

    Raises ``ValueError`` for naive datetime input.
    """
    utc = normalize_utc_datetime(value)
    # Replace any tzinfo so strftime produces the right digits,
    # then manually append 'Z'.
    naive_utc = utc.replace(tzinfo=None)
    return naive_utc.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def parse_utc_timestamp(value: str) -> datetime:
    """Parse a canonical UTC wire timestamp string to aware datetime.

    Accepts only: ``YYYY-MM-DDTHH:MM:SS.ffffffZ``

    Rejects locale-dependent formats (DD/MM/YYYY, etc.).
    """
    try:
        naive = datetime.strptime(value, _CANONICAL_TS_FORMAT)
    except ValueError:
        raise ValueError(
            f"Invalid canonical timestamp: {value!r}.  "
            f"Expected format: YYYY-MM-DDTHH:MM:SS.ffffffZ"
        )
    return naive.replace(tzinfo=timezone.utc)


# ===========================================================================
# 3. REDACTION CONVENTION
# ===========================================================================

REDACTION_SENTINEL = "[REDACTED]"

# Known secret/credential field-name substrings (matched against
# normalized lowercase machine keys).
SECRET_KEY_PATTERNS: frozenset[str] = frozenset({
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
    "password",
    "private_key",
    "credential",
    "credentials",
    "service_account",
})


def _is_secret_key(key: str) -> bool:
    """Return True if *key* (case-insensitive) matches a known secret pattern."""
    normalized = key.lower()
    return normalized in SECRET_KEY_PATTERNS


def redact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new mapping with known secret values replaced by the sentinel.

    - Does NOT mutate the original input.
    - Recursively processes nested mappings and sequences.
    - Uses structural field-name matching (not free-text PII detection).
    - Case-insensitive key matching against known secret patterns.

    Limitations (documented per P-05.06 §22):
    This is structural field-name redaction, NOT universal PII/DLP
    detection.  It does not discover arbitrary secrets buried inside
    free-form prose values.  Later runtime/security phases may add
    deeper inspection.
    """
    result: dict[str, Any] = {}
    for k, v in mapping.items():
        if _is_secret_key(k):
            result[k] = REDACTION_SENTINEL
        elif isinstance(v, Mapping):
            result[k] = redact_mapping(v)
        elif isinstance(v, (list, tuple)):
            result[k] = _redact_sequence(v)
        else:
            result[k] = v
    return result


def _redact_sequence(seq: Sequence[Any]) -> list[Any]:
    """Recursively redact mappings inside a sequence."""
    out: list[Any] = []
    for item in seq:
        if isinstance(item, Mapping):
            out.append(redact_mapping(item))
        elif isinstance(item, (list, tuple)):
            out.append(_redact_sequence(item))
        else:
            out.append(item)
    return out


# ===========================================================================
# 4. SERIALIZATION CONVENTION
# ===========================================================================

def _prepare_value(value: Any) -> Any:
    """Recursively prepare a value for canonical JSON serialization."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return format_utc_timestamp(value)
    if isinstance(value, BaseModel):
        # Use model_dump to get all fields including defaults
        return _prepare_value(value.model_dump())
    if isinstance(value, Mapping):
        return {str(k): _prepare_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_prepare_value(item) for item in value]
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        import math
        if math.isnan(value) or math.isinf(value):
            raise ValueError(
                f"NaN/Infinity not permitted in canonical JSON: {value!r}"
            )
        return value
    if isinstance(value, bytes):
        raise TypeError(
            f"bytes not supported in canonical JSON serialization: {value!r}"
        )
    raise TypeError(
        f"Unsupported type for canonical JSON serialization: "
        f"{type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Produce deterministic canonical JSON bytes.

    Rules:
    - UTF-8 encoding
    - Keys sorted lexicographically
    - Compact separators (no whitespace)
    - Enum values → canonical machine strings
    - Datetimes → canonical UTC wire format
    - Tuples → JSON arrays
    - None → JSON null
    - NaN/Infinity → rejected
    - Unsupported types → rejected (fail closed)
    - No locale-specific formatting
    """
    prepared = _prepare_value(value)
    return json.dumps(
        prepared,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_model_sha256(model: BaseModel) -> str:
    """Compute canonical SHA-256 of a Pydantic model.

    canonical model → canonical JSON bytes → SHA-256 → lowercase hex.

    Equivalent semantic model instances produce the same digest
    regardless of dictionary construction order.
    """
    return sha256_hex(canonical_json_bytes(model))
