"""ChangeMesh Policy Guardian — Google ADK Agent Definition.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the canonical Policy Guardian ADK agent.

Responsibilities:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Evaluates/enforces organizational policy boundaries and privacy classifications.
- Organizational Policy is the AUTHORITY SOURCE; Policy Guardian is the evaluator/enforcer.
- Cannot manufacture human authority from uncertainty or model opinion.
- Cannot override deterministic execution facts.
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
    POLICY_GUARDIAN_INSTRUCTION,
    AgentDefinition,
)
from src.agents.schemas import PolicyGuardianInput, PolicyGuardianOutput


class PolicyGuardian(BaseAgent):
    """ChangeMesh Policy Guardian ADK Agent.

    Evaluates proposed changes against organizational policy boundaries,
    data privacy rules, and separation-of-duty constraints.
    """

    # ChangeMesh Agent Definition Metadata (P-07.02)
    agent_id: ClassVar[str] = "agent-policy-guardian"
    role: ClassVar[str] = "policy_guardian"
    agent_revision: ClassVar[str] = "1.0.0"
    revision: ClassVar[str] = "1.0.0"
    agent_description: ClassVar[str] = (
        "Evaluates proposed changes against organizational policy boundaries, "
        "data privacy rules, and separation-of-duty constraints."
    )
    declared_capabilities: ClassVar[list[str]] = [
        "organizational_policy_evaluation",
        "privacy_boundary_check",
        "separation_of_duty_enforcement",
        "autonomy_classification_determination",
    ]
    capabilities: ClassVar[list[str]] = declared_capabilities
    forbidden_actions: ClassVar[list[str]] = [
        "author_organizational_policy",
        "manufacture_human_authority",
        "override_deterministic_facts",
        "execute_external_changes",
    ]
    instruction_contract: ClassVar[str] = POLICY_GUARDIAN_INSTRUCTION
    permitted_tool_ids: ClassVar[list[str]] = [
        "tool-policy-ruleset-evaluator",
        "tool-data-class-checker",
        "tool-shadowlab-auth-checker",
    ]
    permitted_data_classifications: ClassVar[list[DataClassLevel]] = [
        DataClassLevel.PUBLIC,
        DataClassLevel.INTERNAL,
        DataClassLevel.CONFIDENTIAL,
        DataClassLevel.RESTRICTED,
    ]

    # ADK BaseAgent fields
    name: str = "policy_guardian"
    description: str = agent_description
    input_schema: Type[BaseModel] = PolicyGuardianInput
    output_schema: Type[BaseModel] = PolicyGuardianOutput

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
        """ADK core execution logic for the Policy Guardian.

        In P-07.02 definition stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
