"""ChangeMesh standard capabilities and agent qualification requirements.

P-12.01: Defines the canonical capability vocabulary and role-based capability
requirements for the ChangeMesh multi-agent workflow.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.data_class import DataClassLevel


class CapabilityType(str, Enum):
    """Standardized capability vocabulary for ChangeMesh agents."""

    AST_STATIC_ANALYSIS = "AST_STATIC_ANALYSIS"
    BLAST_RADIUS_ESTIMATION = "BLAST_RADIUS_ESTIMATION"
    MIGRATION_SYNTHESIS_SQL = "MIGRATION_SYNTHESIS_SQL"
    MIGRATION_SYNTHESIS_DISTRIBUTED = "MIGRATION_SYNTHESIS_DISTRIBUTED"
    POLICY_VERIFICATION = "POLICY_VERIFICATION"
    REVERSIBILITY_ANALYSIS = "REVERSIBILITY_ANALYSIS"
    PR_GENERATION = "PR_GENERATION"


class AgentCapabilityRequirement(BaseModel):
    """Specific capability qualifications required for an agent role."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role_id: str
    required_capabilities: Tuple[CapabilityType, ...]
    required_tool_ids: Tuple[str, ...] = ()
    max_data_classification: DataClassLevel = DataClassLevel.RESTRICTED
    min_validity_duration_seconds: int = 3600

    @field_validator("role_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("role_id must not be blank")
        return v

    @field_validator("required_capabilities")
    @classmethod
    def _not_empty(cls, v: Tuple[CapabilityType, ...]) -> Tuple[CapabilityType, ...]:
        if not v:
            raise ValueError("required_capabilities must not be empty")
        return v


def get_standard_demo_requirements() -> Dict[str, AgentCapabilityRequirement]:
    """Return standard capability requirements for the four primary ChangeMesh roles."""
    return {
        "impact_scout": AgentCapabilityRequirement(
            role_id="impact_scout",
            required_capabilities=(
                CapabilityType.AST_STATIC_ANALYSIS,
                CapabilityType.BLAST_RADIUS_ESTIMATION,
            ),
            required_tool_ids=("ast_parser", "dependency_graph"),
            max_data_classification=DataClassLevel.RESTRICTED,
        ),
        "policy_guardian": AgentCapabilityRequirement(
            role_id="policy_guardian",
            required_capabilities=(
                CapabilityType.POLICY_VERIFICATION,
                CapabilityType.REVERSIBILITY_ANALYSIS,
            ),
            required_tool_ids=("policy_engine", "rollback_analyzer"),
            max_data_classification=DataClassLevel.RESTRICTED,
        ),
        "migration_engineer": AgentCapabilityRequirement(
            role_id="migration_engineer",
            required_capabilities=(
                CapabilityType.MIGRATION_SYNTHESIS_SQL,
            ),
            required_tool_ids=("sql_generator", "shadowlab_runner"),
            max_data_classification=DataClassLevel.CONFIDENTIAL,
        ),
        "release_steward": AgentCapabilityRequirement(
            role_id="release_steward",
            required_capabilities=(
                CapabilityType.PR_GENERATION,
            ),
            required_tool_ids=("github_draft_pr", "writeback_receipt_signer"),
            max_data_classification=DataClassLevel.INTERNAL,
        ),
    }
