"""ChangeMesh Agent Layer.

Contains Google ADK agent implementations, definitions, schemas, and registry
for the canonical six-agent ChangeMesh fleet.
"""

from src.agents.change_orchestrator import ChangeOrchestrator, ChangeRuntimeState
from src.agents.definition import (
    CHANGE_ORCHESTRATOR_INSTRUCTION,
    EVIDENCE_AUDITOR_INSTRUCTION,
    IMPACT_SCOUT_INSTRUCTION,
    MIGRATION_ENGINEER_INSTRUCTION,
    POLICY_GUARDIAN_INSTRUCTION,
    RELEASE_STEWARD_INSTRUCTION,
    AgentDefinition,
)
from src.agents.evidence_auditor import EvidenceAuditor
from src.agents.impact_scout import ImpactScout
from src.agents.migration_engineer import MigrationEngineer
from src.agents.policy_guardian import PolicyGuardian
from src.agents.registry import (
    CANONICAL_AGENT_CLASSES,
    CANONICAL_AGENT_IDS,
    CANONICAL_ROLES,
    get_canonical_agent_class,
    get_canonical_agent_definition,
    get_canonical_agent_ids,
    get_canonical_roles,
    list_canonical_agent_classes,
    list_canonical_agent_definitions,
)
from src.agents.release_steward import ReleaseSteward
from src.agents.schemas import (
    EvidenceAuditorInput,
    EvidenceAuditorOutput,
    ImpactScoutInput,
    ImpactScoutOutput,
    MigrationEngineerInput,
    MigrationEngineerOutput,
    PolicyGuardianInput,
    PolicyGuardianOutput,
    ReleaseStewardInput,
    ReleaseStewardOutput,
)

__all__ = [
    # Canonical Agent Classes (ADK BaseAgent subclasses)
    "ChangeOrchestrator",
    "ImpactScout",
    "PolicyGuardian",
    "MigrationEngineer",
    "EvidenceAuditor",
    "ReleaseSteward",
    # Runtime State
    "ChangeRuntimeState",
    # Agent Definition Contract
    "AgentDefinition",
    # Instruction Contracts
    "CHANGE_ORCHESTRATOR_INSTRUCTION",
    "IMPACT_SCOUT_INSTRUCTION",
    "POLICY_GUARDIAN_INSTRUCTION",
    "MIGRATION_ENGINEER_INSTRUCTION",
    "EVIDENCE_AUDITOR_INSTRUCTION",
    "RELEASE_STEWARD_INSTRUCTION",
    # Fleet Registry
    "CANONICAL_AGENT_CLASSES",
    "CANONICAL_AGENT_IDS",
    "CANONICAL_ROLES",
    "get_canonical_agent_class",
    "get_canonical_agent_definition",
    "get_canonical_agent_ids",
    "get_canonical_roles",
    "list_canonical_agent_classes",
    "list_canonical_agent_definitions",
    # Specialized Input/Output Schemas
    "ImpactScoutInput",
    "ImpactScoutOutput",
    "PolicyGuardianInput",
    "PolicyGuardianOutput",
    "MigrationEngineerInput",
    "MigrationEngineerOutput",
    "EvidenceAuditorInput",
    "EvidenceAuditorOutput",
    "ReleaseStewardInput",
    "ReleaseStewardOutput",
]
