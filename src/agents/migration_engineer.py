"""ChangeMesh Migration Engineer — Google ADK Agent Definition.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the canonical Migration Engineer ADK agent.

Responsibilities:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Generates scoped migration artifacts, schema patches, and verification scripts.
- No direct production execution, no unrestricted filesystem writes.
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
    MIGRATION_ENGINEER_INSTRUCTION,
    AgentDefinition,
)
from src.agents.schemas import MigrationEngineerInput, MigrationEngineerOutput


class MigrationEngineer(BaseAgent):
    """ChangeMesh Migration Engineer ADK Agent.

    Generates scoped migration artifacts, schema patches, and verification scripts
    within bounded temporary workspaces.
    """

    # ChangeMesh Agent Definition Metadata (P-07.02)
    agent_id: ClassVar[str] = "agent-migration-engineer"
    role: ClassVar[str] = "migration_engineer"
    agent_revision: ClassVar[str] = "1.0.0"
    revision: ClassVar[str] = "1.0.0"
    agent_description: ClassVar[str] = (
        "Generates scoped migration artifacts, schema patches, and verification scripts "
        "within bounded temporary workspaces."
    )
    declared_capabilities: ClassVar[list[str]] = [
        "migration_artifact_generation",
        "verification_script_synthesis",
        "rehearsal_scaffolding",
    ]
    capabilities: ClassVar[list[str]] = declared_capabilities
    forbidden_actions: ClassVar[list[str]] = [
        "direct_production_execution",
        "unrestricted_filesystem_writes",
        "bypass_policy_review",
        "credential_consumption",
    ]
    instruction_contract: ClassVar[str] = MIGRATION_ENGINEER_INSTRUCTION
    permitted_tool_ids: ClassVar[list[str]] = [
        "tool-sql-dialect-formatter",
        "tool-schema-diff-builder",
        "tool-rehearsal-packager",
    ]
    permitted_data_classifications: ClassVar[list[DataClassLevel]] = [
        DataClassLevel.PUBLIC,
        DataClassLevel.INTERNAL,
        DataClassLevel.CONFIDENTIAL,
    ]

    # ADK BaseAgent fields
    name: str = "migration_engineer"
    description: str = agent_description
    input_schema: Type[BaseModel] = MigrationEngineerInput
    output_schema: Type[BaseModel] = MigrationEngineerOutput

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
        """ADK core execution logic for the Migration Engineer.

        In P-07.02 definition stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
