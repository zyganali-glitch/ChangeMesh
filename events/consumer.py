"""ChangeMesh provider-neutral event consumer protocol and result contracts.

P-09.02: Canonical consume protocol, schema validation pre-check, delivery classification,
and dispatch mechanics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Mapping, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.event_envelope import EventDeliveryDisposition
from events.dead_letter import DeadLetterEventRecord
from events.wire import EventWireMessage


class EventConsumeResult(BaseModel):
    """Result of processing a received message from an event transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: EventDeliveryDisposition
    event_id: str
    message_id: str
    transport: str
    callback_invoked: bool
    error_message: Optional[str] = None
    dead_letter_record: Optional[DeadLetterEventRecord] = None

    @field_validator("event_id", "message_id", "transport")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class EventConsumer(ABC):
    """Abstract consumer interface for ChangeMesh event backbone."""

    @abstractmethod
    def process_raw_message(
        self,
        raw_data: bytes,
        attributes: Mapping[str, str],
        message_id: str,
        callback: Callable[[EventWireMessage], Any],
    ) -> EventConsumeResult:
        """Validate, classify, and dispatch a raw transport message."""
        raise NotImplementedError
