"""ChangeMesh provider-neutral event publisher protocol and result contracts.

P-09.02: Canonical publish protocol and result definitions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from events.dead_letter import DeadLetterEventRecord
from events.wire import EventWireMessage


class EventPublishResult(BaseModel):
    """Result of publishing an event through an event transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str  # "PUBLISHED" or "FAILED"
    message_id: str
    topic_id: str
    event_id: str
    transport: str  # "GOOGLE_PUBSUB" or "LOCAL"
    error_message: Optional[str] = None
    dead_letter_record: Optional[DeadLetterEventRecord] = None

    @field_validator("status", "message_id", "topic_id", "event_id", "transport")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class EventPublisher(ABC):
    """Abstract publisher interface for ChangeMesh event backbone."""

    @abstractmethod
    def publish(self, message: EventWireMessage) -> EventPublishResult:
        """Publish an EventWireMessage to the designated topic."""
        raise NotImplementedError
