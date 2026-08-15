"""ChangeMesh Change Orchestrator — Google ADK Agent Skeleton.

P-07.01: Implement Change Orchestrator ADK skeleton with no external writes.
P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the canonical Change Orchestrator ADK agent and its initial
local runtime state representation.

Responsibilities:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Accept typed `ChangeRequest` domain contract at the intake boundary.
- Fail closed on non-ChangeRequest / untyped input.
- Create a distinct, non-blank `change_id` (deterministic / injectable).
- Initialize lifecycle state strictly to `ChangeState.RECEIVED`.
- Preserve `request_id` and ensure `ChangeRequest` is not mutated.
- Expose explicit role, capabilities, forbidden actions, input/output schema, revision.
- Zero external writes (no Firestore, Pub/Sub, Cloud Run, GitHub, network).
- Zero credentials required.
- Zero Gemini/LLM reasoning or invocation (deferred to P-08).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Callable, ClassVar, Type

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from pydantic import BaseModel, ConfigDict, Field

from domain.contracts.agent_descriptor import AgentDescriptor
from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.change_request import ChangeRequest
from domain.contracts.conventions import UtcDateTime
from domain.contracts.data_class import DataClassLevel
from src.agents.definition import (
    CHANGE_ORCHESTRATOR_INSTRUCTION,
    AgentDefinition,
)


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
    In P-07.01/P-07.02, this implements the intake boundary that receives a typed
    `ChangeRequest`, generates a distinct durable `change_id`, and creates
    the initial `ChangeRuntimeState` in `ChangeState.RECEIVED` with zero
    external writes and zero model invocations.
    """

    # ChangeMesh Agent Definition Metadata (P-07.02)
    agent_id: ClassVar[str] = "agent-change-orchestrator"
    role: ClassVar[str] = "change_orchestrator"
    agent_revision: ClassVar[str] = "1.0.0"
    revision: ClassVar[str] = "1.0.0"
    agent_description: ClassVar[str] = (
        "ChangeMesh Change Orchestrator ADK Agent — coordinates change verification "
        "lifecycle, delegating to specialized agents with zero direct durable state mutation."
    )
    declared_capabilities: ClassVar[list[str]] = [
        "change_request_intake",
        "lifecycle_coordination",
        "delegation_dispatch",
    ]
    capabilities: ClassVar[list[str]] = declared_capabilities
    forbidden_actions: ClassVar[list[str]] = [
        "direct_durable_state_mutation",
        "self_authorize_changes",
        "overwrite_deterministic_facts",
        "unrestricted_external_writes",
        "unvetted_model_reasoning",
    ]
    instruction_contract: ClassVar[str] = CHANGE_ORCHESTRATOR_INSTRUCTION
    permitted_tool_ids: ClassVar[list[str]] = [
        "tool-saga-reader",
        "tool-agent-registry-reader",
        "tool-event-publisher",
    ]
    permitted_data_classifications: ClassVar[list[DataClassLevel]] = [
        DataClassLevel.PUBLIC,
        DataClassLevel.INTERNAL,
        DataClassLevel.CONFIDENTIAL,
        DataClassLevel.RESTRICTED,
    ]

    # ADK BaseAgent fields
    name: str = "change_orchestrator"
    description: str = agent_description
    input_schema: Type[BaseModel] = ChangeRequest
    output_schema: Type[BaseModel] = ChangeRuntimeState

    @classmethod
    def get_definition(cls) -> AgentDefinition:
        """Return the complete runtime AgentDefinition contract for this agent."""
        return AgentDefinition(
            agent_id=cls.agent_id,
            role=cls.role,
            agent_revision=cls.agent_revision,
            description=cls.agent_description,
            declared_capabilities=cls.declared_capabilities,
            forbidden_actions=cls.forbidden_actions,
            input_schema=cls.model_fields["input_schema"].default,
            output_schema=cls.model_fields["output_schema"].default,
            instruction_contract=cls.instruction_contract,
            permitted_tool_ids=cls.permitted_tool_ids,
            permitted_data_classifications=cls.permitted_data_classifications,
        )

    @classmethod
    def get_descriptor(cls) -> AgentDescriptor:
        """Return the frozen domain contract AgentDescriptor for this agent."""
        return cls.get_definition().to_descriptor()

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

        In P-07.01/P-07.02 skeleton stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
