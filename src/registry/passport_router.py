"""ChangeMesh passport-aware agent dispatch router.

P-12.06: Integrates capability verification into dispatch routing, enforcing
that every dispatched agent revision holds a valid, active CapabilityPassport.
"""

from __future__ import annotations

from typing import Optional, Tuple

from domain.contracts.capability import CapabilityPassport
from src.registry.agent_registry import AgentDescriptor, AgentRegistry
from src.registry.capabilities import AgentCapabilityRequirement, get_standard_demo_requirements
from src.registry.passport_issuer import PassportVerifier
from src.orchestrator.state_repository import validate_tenant_id


class UnqualifiedAgentDispatchError(ValueError):
    """Raised when no qualified agent revision with an active passport exists for a required role."""
    pass


class PassportAwareRouter:
    """Dispatches workflow tasks strictly to agent revisions holding valid CapabilityPassports."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry
        self._requirements = get_standard_demo_requirements()

    def route_role(
        self,
        tenant_id: str,
        role_id: str,
        preferred_revision: Optional[str] = None,
    ) -> Tuple[AgentDescriptor, CapabilityPassport]:
        """Resolve and verify the qualified agent revision for a workflow role.

        Raises:
            UnqualifiedAgentDispatchError: if no active qualified passport satisfies role requirements.
        """
        tid = validate_tenant_id(tenant_id)
        requirement = self._requirements.get(role_id)
        if requirement is None:
            raise UnqualifiedAgentDispatchError(f"Unknown workflow role {role_id!r}")

        # If preferred revision specified, check it first
        if preferred_revision:
            descriptor = self._registry.get_descriptor(role_id, preferred_revision)
            passport = self._registry.get_active_passport(tid, role_id, preferred_revision)
            if descriptor and passport:
                val = PassportVerifier.verify(passport, requirement=requirement, expected_revision=preferred_revision)
                if val.is_valid:
                    return descriptor, passport
            raise UnqualifiedAgentDispatchError(
                f"Preferred agent {role_id} revision {preferred_revision} is unqualified, unverified, or revoked"
            )

        # Enumerate qualified agents for required capabilities
        primary_cap = requirement.required_capabilities[0]
        candidates = self._registry.find_qualified_agents(tid, primary_cap)

        for desc, passp in candidates:
            if desc.agent_id == role_id:
                val = PassportVerifier.verify(passp, requirement=requirement, expected_revision=desc.agent_revision)
                if val.is_valid:
                    return desc, passp

        raise UnqualifiedAgentDispatchError(
            f"No qualified agent holding valid CapabilityPassport found for role {role_id!r} with capabilities {[c.value for c in requirement.required_capabilities]}"
        )
