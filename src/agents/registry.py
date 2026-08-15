"""ChangeMesh Canonical Agent Fleet Registry.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module maintains the canonical registry of exactly six Google ADK agents in ChangeMesh:
1. Change Orchestrator (change_orchestrator / agent-change-orchestrator)
2. Impact Scout (impact_scout / agent-impact-scout)
3. Policy Guardian (policy_guardian / agent-policy-guardian)
4. Migration Engineer (migration_engineer / agent-migration-engineer)
5. Evidence Auditor (evidence_auditor / agent-evidence-auditor)
6. Release Steward (release_steward / agent-release-steward)

Invariants:
- Exactly six canonical agents total.
- No seventh or invented agent.
- All agents subclass Google ADK BaseAgent.
- All lookups fail closed on unknown identifiers.
"""

from __future__ import annotations

from typing import Type, Union

from google.adk.agents.base_agent import BaseAgent

from src.agents.change_orchestrator import ChangeOrchestrator
from src.agents.definition import AgentDefinition
from src.agents.evidence_auditor import EvidenceAuditor
from src.agents.impact_scout import ImpactScout
from src.agents.migration_engineer import MigrationEngineer
from src.agents.policy_guardian import PolicyGuardian
from src.agents.release_steward import ReleaseSteward

CanonicalAgentClass = Union[
    Type[ChangeOrchestrator],
    Type[ImpactScout],
    Type[PolicyGuardian],
    Type[MigrationEngineer],
    Type[EvidenceAuditor],
    Type[ReleaseSteward],
]

CANONICAL_AGENT_CLASSES: tuple[CanonicalAgentClass, ...] = (
    ChangeOrchestrator,
    ImpactScout,
    PolicyGuardian,
    MigrationEngineer,
    EvidenceAuditor,
    ReleaseSteward,
)

CANONICAL_ROLES: tuple[str, ...] = (
    "change_orchestrator",
    "impact_scout",
    "policy_guardian",
    "migration_engineer",
    "evidence_auditor",
    "release_steward",
)

CANONICAL_AGENT_IDS: tuple[str, ...] = (
    "agent-change-orchestrator",
    "agent-impact-scout",
    "agent-policy-guardian",
    "agent-migration-engineer",
    "agent-evidence-auditor",
    "agent-release-steward",
)

# Build immutable lookup maps
_BY_ROLE: dict[str, CanonicalAgentClass] = {cls.role: cls for cls in CANONICAL_AGENT_CLASSES}
_BY_ID: dict[str, CanonicalAgentClass] = {cls.agent_id: cls for cls in CANONICAL_AGENT_CLASSES}


def get_canonical_agent_class(identifier: str) -> CanonicalAgentClass:
    """Look up a canonical agent class by role or agent_id (fail closed)."""
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("Agent identifier must not be blank")

    clean_id = identifier.strip()
    if clean_id in _BY_ROLE:
        return _BY_ROLE[clean_id]
    if clean_id in _BY_ID:
        return _BY_ID[clean_id]

    raise KeyError(f"Unknown canonical agent identifier: {identifier!r}")


def get_canonical_agent_definition(identifier: str) -> AgentDefinition:
    """Look up a canonical agent definition by role or agent_id (fail closed)."""
    cls = get_canonical_agent_class(identifier)
    return cls.get_definition()


def list_canonical_agent_definitions() -> list[AgentDefinition]:
    """Return the ordered list of all six canonical agent definitions."""
    return [cls.get_definition() for cls in CANONICAL_AGENT_CLASSES]


def list_canonical_agent_classes() -> list[Type[BaseAgent]]:
    """Return the ordered list of all six canonical agent classes."""
    return list(CANONICAL_AGENT_CLASSES)


def get_canonical_roles() -> list[str]:
    """Return the list of all six canonical agent role names."""
    return list(CANONICAL_ROLES)


def get_canonical_agent_ids() -> list[str]:
    """Return the list of all six canonical agent IDs."""
    return list(CANONICAL_AGENT_IDS)
