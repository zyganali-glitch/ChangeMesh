"""ChangeMesh event wire format and validation.

P-09.02: Canonical wire message schema, deterministic serialization, and
strict pre-dispatch schema and privacy validation.

Provider-neutral: Standard library + Pydantic + domain contracts only.
Zero imports of google.cloud.pubsub or provider SDKs.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.conventions import (
    SECRET_KEY_PATTERNS,
    UtcDateTime,
    canonical_json_bytes,
    format_utc_timestamp,
)
from domain.contracts.event_envelope import EventEnvelope

# Wire protocol version
WIRE_SCHEMA_VERSION = "1.0.0"

# Common patterns for detecting credentials/secrets inside payloads
_SECRET_PATTERNS = [
    re.compile(r"-{5}BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-{5}", re.IGNORECASE),
    re.compile(
        r"(?:api[_-]?key|apikey|secret[_-]?key|client[_-]?secret)"
        r"\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),  # GitHub tokens
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),  # JWTs
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{15,}\b", re.IGNORECASE),
    re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{4,}['\"]", re.IGNORECASE),
]


def scan_payload_for_secrets(data: Any, path: str = "") -> None:
    """Recursively scan payload data and raise ValueError if credential patterns are found."""
    if isinstance(data, str):
        for pattern in _SECRET_PATTERNS:
            if pattern.search(data):
                raise ValueError(
                    f"Secret or credential material detected in payload field {path!r}: "
                    "Credential material is forbidden in event payloads."
                )
    elif isinstance(data, dict):
        _all_forbidden = SECRET_KEY_PATTERNS | frozenset({"bearer", "client_secret", "oauth_token"})
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(forbidden in k_lower for forbidden in _all_forbidden):
                raise ValueError(
                    f"Prohibited credential field name {k!r} at {path!r} in event payload."
                )
            scan_payload_for_secrets(v, f"{path}.{k}" if path else str(k))
    elif isinstance(data, (list, tuple)):
        for idx, item in enumerate(data):
            scan_payload_for_secrets(item, f"{path}[{idx}]")


class EventWireMessage(BaseModel):
    """Canonical wire representation of a ChangeMesh event.

    Contains the frozen EventEnvelope, the domain payload mapping,
    the target topic ID, publication timestamp metadata, and derived
    deterministic wire attributes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    wire_version: str = WIRE_SCHEMA_VERSION
    topic_id: str
    envelope: EventEnvelope
    payload: Mapping[str, Any] = {}
    published_at: Optional[UtcDateTime] = None

    @field_validator("wire_version", "topic_id")
    @classmethod
    def _validate_non_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()

    @field_validator("wire_version")
    @classmethod
    def _validate_wire_version(cls, v: str) -> str:
        if v != WIRE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported wire_version {v!r}. Expected {WIRE_SCHEMA_VERSION!r}.")
        return v

    @model_validator(mode="after")
    def _validate_envelope_schema_version(self) -> EventWireMessage:
        if self.envelope.schema_version != "1.0.0":
            raise ValueError(
                f"Unsupported envelope schema_version {self.envelope.schema_version!r}. "
                "Expected '1.0.0'."
            )
        return self

    @model_validator(mode="after")
    def _validate_payload_secrecy(self) -> EventWireMessage:
        """Enforce zero credentials in event payload."""
        scan_payload_for_secrets(self.payload)
        return self

    def get_transport_attributes(self) -> Mapping[str, str]:
        """Derive standard string attributes for Pub/Sub message metadata."""
        attrs: dict[str, str] = {
            "wire_version": self.wire_version,
            "schema_version": self.envelope.schema_version,
            "topic_id": self.topic_id,
            "event_id": self.envelope.event_id,
            "change_id": self.envelope.change_id,
            "correlation_id": self.envelope.correlation_id,
            "producer_id": self.envelope.producer_id,
            "producer_revision": self.envelope.producer_revision,
            "idempotency_key": self.envelope.idempotency_key,
            "envelope_timestamp": format_utc_timestamp(self.envelope.timestamp),
        }
        if self.envelope.causation_id is not None:
            attrs["causation_id"] = self.envelope.causation_id
        if self.envelope.producer_role is not None:
            attrs["producer_role"] = self.envelope.producer_role
        if self.published_at is not None:
            attrs["published_at"] = format_utc_timestamp(self.published_at)
        return attrs

    def to_bytes(self) -> bytes:
        """Serialize message to canonical JSON bytes."""
        envelope_dict = self.envelope.model_dump(mode="json")
        data: dict[str, Any] = {
            "wire_version": self.wire_version,
            "topic_id": self.topic_id,
            "envelope": envelope_dict,
            "payload": self.payload,
        }
        if self.published_at is not None:
            data["published_at"] = format_utc_timestamp(self.published_at)
        return canonical_json_bytes(data)

    @classmethod
    def from_bytes(cls, raw_bytes: bytes) -> EventWireMessage:
        """Deserialize and validate raw JSON bytes into an EventWireMessage.

        Rejects malformed JSON, unsupported schema versions, missing fields,
        extra unapproved fields, and secret-bearing payloads.
        """
        if not raw_bytes:
            raise ValueError("Cannot deserialize empty byte sequence into EventWireMessage")
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Malformed JSON event payload: {e}") from e

        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object at top level, got {type(parsed).__name__}")

        # Validate wire version before model initialization
        wv = parsed.get("wire_version")
        if wv != WIRE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported wire_version {wv!r}. Expected {WIRE_SCHEMA_VERSION!r}")

        return cls.model_validate(parsed)
