"""ChangeMesh Release Steward — Google ADK Agent Definition.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the canonical Release Steward ADK agent.

Responsibilities:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Reversible handoff, release packaging, and bounded draft PR construction.
- Cannot self-authorize; requires verified Change Passport and proper authority path.
- No live production mutation, no direct pushes to protected branches.
- Zero credentials required, zero external writes, zero Gemini model invocations.
"""

from __future__ import annotations

from typing import AsyncGenerator, ClassVar, Type

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from pydantic import BaseModel

from domain.contracts.agent_descriptor import AgentDescriptor
from domain.contracts.data_class import DataClassLevel
from src.agents.definition import (
    RELEASE_STEWARD_INSTRUCTION,
    AgentDefinition,
)
from src.agents.schemas import ReleaseStewardInput, ReleaseStewardOutput


class ReleaseSteward(BaseAgent):
    """ChangeMesh Release Steward ADK Agent.

    Prepares reversible execution handoffs, builds draft pull requests against
    synthetic repositories, and packages release bundles. Cannot self-authorize.
    """

    # ChangeMesh Agent Definition Metadata (P-07.02)
    agent_id: ClassVar[str] = "agent-release-steward"
    role: ClassVar[str] = "release_steward"
    agent_revision: ClassVar[str] = "1.0.0"
    revision: ClassVar[str] = "1.0.0"
    agent_description: ClassVar[str] = (
        "Prepares reversible execution handoffs, builds draft pull requests against "
        "synthetic repositories, and packages release bundles. Cannot self-authorize."
    )
    declared_capabilities: ClassVar[list[str]] = [
        "release_bundle_packaging",
        "draft_pull_request_preparation",
        "reversible_handoff_construction",
    ]
    capabilities: ClassVar[list[str]] = declared_capabilities
    forbidden_actions: ClassVar[list[str]] = [
        "self_authorize_execution",
        "direct_production_mutation",
        "unbounded_git_pushes",
        "bypass_passport_verification",
    ]
    instruction_contract: ClassVar[str] = RELEASE_STEWARD_INSTRUCTION
    permitted_tool_ids: ClassVar[list[str]] = [
        "tool-draft-pr-builder",
        "tool-release-bundle-signer",
        "tool-passport-validator",
    ]
    permitted_data_classifications: ClassVar[list[DataClassLevel]] = [
        DataClassLevel.PUBLIC,
        DataClassLevel.INTERNAL,
        DataClassLevel.CONFIDENTIAL,
    ]

    # ADK BaseAgent fields
    name: str = "release_steward"
    description: str = agent_description
    input_schema: Type[BaseModel] = ReleaseStewardInput
    output_schema: Type[BaseModel] = ReleaseStewardOutput

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

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """ADK core execution logic for the Release Steward.

        In P-07.02 definition stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
