"""ChangeMesh Evidence Auditor — Google ADK Agent Definition.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the canonical Evidence Auditor ADK agent.

Responsibilities:
- Subclass Google ADK `BaseAgent` (google.adk.agents.BaseAgent).
- Semantic sufficiency reviews of collected execution evidence against success criteria.
- Deterministic evidence records and execution facts are strictly READ-ONLY.
- May never rewrite PASS/FAIL, hashes, execution occurrence, test counts, or timestamps.
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
    EVIDENCE_AUDITOR_INSTRUCTION,
    AgentDefinition,
)
from src.agents.schemas import EvidenceAuditorInput, EvidenceAuditorOutput


class EvidenceAuditor(BaseAgent):
    """ChangeMesh Evidence Auditor ADK Agent.

    Performs semantic sufficiency reviews of collected execution evidence
    against success criteria. Deterministic evidence records are read-only.
    """

    # ChangeMesh Agent Definition Metadata (P-07.02)
    agent_id: ClassVar[str] = "agent-evidence-auditor"
    role: ClassVar[str] = "evidence_auditor"
    agent_revision: ClassVar[str] = "1.0.0"
    revision: ClassVar[str] = "1.0.0"
    agent_description: ClassVar[str] = (
        "Performs semantic sufficiency reviews of collected execution evidence "
        "against success criteria. Deterministic evidence records are read-only."
    )
    declared_capabilities: ClassVar[list[str]] = [
        "semantic_evidence_sufficiency_review",
        "evidence_completeness_verification",
        "claim_justification_analysis",
    ]
    capabilities: ClassVar[list[str]] = declared_capabilities
    forbidden_actions: ClassVar[list[str]] = [
        "rewrite_deterministic_facts",
        "forge_execution_evidence",
        "grant_unauthorized_pass",
        "execute_system_mutations",
    ]
    instruction_contract: ClassVar[str] = EVIDENCE_AUDITOR_INSTRUCTION
    permitted_tool_ids: ClassVar[list[str]] = [
        "tool-evidence-ledger-reader",
        "tool-artifact-hash-verifier",
        "tool-rehearsal-result-reader",
    ]
    permitted_data_classifications: ClassVar[list[DataClassLevel]] = [
        DataClassLevel.PUBLIC,
        DataClassLevel.INTERNAL,
        DataClassLevel.CONFIDENTIAL,
        DataClassLevel.RESTRICTED,
    ]

    # ADK BaseAgent fields
    name: str = "evidence_auditor"
    description: str = agent_description
    input_schema: Type[BaseModel] = EvidenceAuditorInput
    output_schema: Type[BaseModel] = EvidenceAuditorOutput

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
        """ADK core execution logic for the Evidence Auditor.

        In P-07.02 definition stage, yields a turn-complete event without
        invoking external models or network services.
        """
        yield Event(author=self.name, turn_complete=True)
