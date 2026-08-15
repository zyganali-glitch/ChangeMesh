"""ChangeMesh Change Orchestrator — Google ADK Agent Skeleton.

P-07.01: Implement Change Orchestrator ADK skeleton with no external writes.
This module defines the canonical Change Orchestrator ADK agent and its initial
local runtime state representation.

Responsibilities for P-07.01:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Accept typed `ChangeRequest` domain contract at the intake boundary.
- Fail closed on non-ChangeRequest / untyped input.
- Create a distinct, non-blank `change_id` (deterministic / injectable).
- Initialize lifecycle state strictly to `ChangeState.RECEIVED`.
- Preserve `request_id` and ensure `ChangeRequest` is not mutated.
- Zero external writes (no Firestore, Pub/Sub, Cloud Run, GitHub, network).
- Zero credentials required.
- Zero Gemini/LLM reasoning or invocation (deferred to P-08).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Callable

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from pydantic import BaseModel, ConfigDict, Field

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.change_request import ChangeRequest
from domain.contracts.conventions import UtcDateTime


class ChangeRuntimeState(BaseModel):
    """Minimal immutable local runtime state for an initialized change.

    Satisfies the P-07.01 local state representation requirements:
    - `change_id`: Distinct durable lifecycle identity.
    - `request_id`: Preserved identity of the originating `ChangeRequest`.
    - `state`: Initial lifecycle state (strictly `ChangeState.RECEIVED`).
    - `created_at`: Normalized UTC creation timestamp.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    change_id: str
    request_id: str
    state: ChangeState = ChangeState.RECEIVED
    created_at: UtcDateTime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChangeOrchestrator(BaseAgent):
    """ChangeMesh Change Orchestrator ADK Agent Skeleton.

    Canonical ADK Agent coordinating the ChangeMesh lifecycle.
    In P-07.01, this implements the intake boundary that receives a typed
    `ChangeRequest`, generates a distinct durable `change_id`, and creates
    the initial `ChangeRuntimeState` in `ChangeState.RECEIVED` with zero
    external writes and zero model invocations.
    """

    name: str = "change_orchestrator"
    description: str = "ChangeMesh Change Orchestrator ADK Agent"

    def initialize_change(
        self,
        request: ChangeRequest,
        *,
        id_generator: Callable[[], str] | None = None,
    ) -> ChangeRuntimeState:
        """Receive a typed ChangeRequest and create initial ChangeRuntimeState.

        Args:
            request: A validated ChangeRequest domain contract instance.
            id_generator: Optional deterministic ID generator callable.
                Defaults to a locally generated unique ID.

        Returns:
            ChangeRuntimeState with distinct change_id, preserved request_id,
            and state set to ChangeState.RECEIVED.

        Raises:
            TypeError: If request is not an instance of ChangeRequest (fail closed).
            ValueError: If generated change_id is blank or equals request_id.
        """
        if not isinstance(request, ChangeRequest):
            raise TypeError(
                f"Expected ChangeRequest domain contract instance, got {type(request).__name__}"
            )

        if id_generator is not None:
            change_id = id_generator()
        else:
            change_id = f"change-{uuid.uuid4().hex}"

        if not isinstance(change_id, str) or not change_id.strip():
            raise ValueError("Generated change_id must not be blank")

        clean_change_id = change_id.strip()

        if clean_change_id == request.request_id:
            raise ValueError(
                f"change_id ({clean_change_id!r}) must be distinct "
                f"from request_id ({request.request_id!r})"
            )

        return ChangeRuntimeState(
            change_id=clean_change_id,
            request_id=request.request_id,
            state=ChangeState.RECEIVED,
        )

    def receive_change_request(
        self,
        request: ChangeRequest,
        *,
        id_generator: Callable[[], str] | None = None,
    ) -> ChangeRuntimeState:
        """Alias for initialize_change."""
        return self.initialize_change(request, id_generator=id_generator)

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """ADK core execution logic for the Change Orchestrator.

        In P-07.01 skeleton stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
