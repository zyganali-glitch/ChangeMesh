"""ChangeMesh Impact Scout — Google ADK Agent Definition.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the canonical Impact Scout ADK agent.

Responsibilities:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Read-only repository analysis, blast-radius assessment, and conflict detection.
- Deterministic repository facts are owned by DETERMINISTIC_CODE authority.
- No repository writes or mutations (GitHub/GitLab).
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
    IMPACT_SCOUT_INSTRUCTION,
    AgentDefinition,
)
from src.agents.schemas import ImpactScoutInput, ImpactScoutOutput


class ImpactScout(BaseAgent):
    """ChangeMesh Impact Scout ADK Agent.

    Performs read-only analysis of repository changes, blast-radius assessment,
    affected systems identification, and parallel-change conflict detection.
    """

    # ChangeMesh Agent Definition Metadata (P-07.02)
    agent_id: ClassVar[str] = "agent-impact-scout"
    role: ClassVar[str] = "impact_scout"
    agent_revision: ClassVar[str] = "1.0.0"
    revision: ClassVar[str] = "1.0.0"
    agent_description: ClassVar[str] = (
        "Performs read-only analysis of repository changes, blast-radius assessment, "
        "affected systems identification, and parallel-change conflict detection."
    )
    declared_capabilities: ClassVar[list[str]] = [
        "repository_blast_radius_analysis",
        "affected_systems_identification",
        "parallel_change_conflict_detection",
    ]
    capabilities: ClassVar[list[str]] = declared_capabilities
    forbidden_actions: ClassVar[list[str]] = [
        "repository_mutation",
        "external_writes",
        "overwrite_deterministic_git_facts",
        "credential_exposure",
    ]
    instruction_contract: ClassVar[str] = IMPACT_SCOUT_INSTRUCTION
    permitted_tool_ids: ClassVar[list[str]] = [
        "tool-git-diff-analyzer",
        "tool-metadata-graph-reader",
        "tool-dependency-graph-reader",
    ]
    permitted_data_classifications: ClassVar[list[DataClassLevel]] = [
        DataClassLevel.PUBLIC,
        DataClassLevel.INTERNAL,
        DataClassLevel.CONFIDENTIAL,
    ]

    # ADK BaseAgent fields
    name: str = "impact_scout"
    description: str = agent_description
    input_schema: Type[BaseModel] = ImpactScoutInput
    output_schema: Type[BaseModel] = ImpactScoutOutput

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
        """ADK core execution logic for the Impact Scout.

        In P-07.02 definition stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
