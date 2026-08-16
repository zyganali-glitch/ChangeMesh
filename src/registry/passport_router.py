"""ChangeMesh passport-aware agent dispatch router.

P-12.04 & P-12.06: Integrates capability verification into dispatch routing, enforcing
that every dispatched agent revision holds a valid, active CapabilityPassport,
rejecting unqualified/failed revisions with recorded reasons, and exposing a structured
judge-facing projection.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, ConfigDict

from domain.contracts.capability import CapabilityPassport
from src.orchestrator.state_repository import validate_tenant_id
from src.registry.agent_registry import AgentDescriptor, AgentRegistry
from src.registry.capabilities import get_standard_demo_requirements
from src.registry.evidence_verifier import QualificationEvidenceVerifier
from src.registry.passport_issuer import PassportVerifier

CANONICAL_SCHEMA_VERSION = "1.0.0"


class UnqualifiedAgentDispatchError(ValueError):
    """Raised when no qualified agent revision with an active passport exists for a role."""

    pass


class RejectedCandidateProjection(BaseModel):
    """Structured record of an evaluated candidate agent revision rejected during routing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    agent_revision: str
    rejection_reason: str
    status: str


class PassportJudgeProjection(BaseModel):
    """Minimal structured judge-facing projection of capability selection and audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    role_id: str
    selected_agent_id: str
    selected_revision: str
    qualified_capabilities: Tuple[str, ...]
    qualification_evidence_ids: Tuple[str, ...]
    rejected_candidates: Tuple[RejectedCandidateProjection, ...] = ()


class PassportAwareRouter:
    """Dispatches workflow tasks strictly to agent revisions holding valid CapabilityPassports."""

    def __init__(
        self,
        registry: AgentRegistry,
        evidence_verifier: Optional[QualificationEvidenceVerifier] = None,
    ) -> None:
        self._registry = registry
        self._evidence_verifier = evidence_verifier or QualificationEvidenceVerifier()
        self._requirements = get_standard_demo_requirements()

    def route_role(
        self,
        tenant_id: str,
        role_id: str,
        preferred_revision: Optional[str] = None,
    ) -> Tuple[AgentDescriptor, CapabilityPassport, PassportJudgeProjection]:
        """Resolve and verify the qualified agent revision for a workflow role.

        Raises:
            UnqualifiedAgentDispatchError: if no active qualified passport satisfies requirements.
        """
        tid = validate_tenant_id(tenant_id)
        requirement = self._requirements.get(role_id)
        if requirement is None:
            raise UnqualifiedAgentDispatchError(f"Unknown workflow role {role_id!r}")

        rejected: List[RejectedCandidateProjection] = []

        # If preferred revision specified, evaluate it first
        if preferred_revision:
            descriptor = self._registry.get_descriptor(role_id, preferred_revision)
            passport = self._registry.get_active_passport(tid, role_id, preferred_revision)
            if descriptor and passport:
                val = PassportVerifier.verify(
                    passport=passport,
                    evidence_verifier=self._evidence_verifier,
                    requirement=requirement,
                    expected_revision=preferred_revision,
                )
                if val.is_valid:
                    projection = PassportJudgeProjection(
                        tenant_id=tid,
                        role_id=role_id,
                        selected_agent_id=descriptor.agent_id,
                        selected_revision=descriptor.agent_revision,
                        qualified_capabilities=passport.qualified_capabilities,
                        qualification_evidence_ids=passport.qualification_evidence_ids,
                        rejected_candidates=tuple(rejected),
                    )
                    return descriptor, passport, projection
                else:
                    rejected.append(
                        RejectedCandidateProjection(
                            agent_id=role_id,
                            agent_revision=preferred_revision,
                            rejection_reason=val.failure_reason or "Passport validation failed",
                            status=val.status,
                        )
                    )
            else:
                rejected.append(
                    RejectedCandidateProjection(
                        agent_id=role_id,
                        agent_revision=preferred_revision,
                        rejection_reason="No active passport or descriptor registered",
                        status="UNREGISTERED",
                    )
                )

            raise UnqualifiedAgentDispatchError(
                f"Preferred agent {role_id} revision {preferred_revision} "
                f"is unqualified, unverified, or revoked: "
                f"{rejected[-1].rejection_reason}"
            )

        # Enumerate qualified agents for required capabilities
        primary_cap = requirement.required_capabilities[0]
        candidates = self._registry.find_qualified_agents(tid, primary_cap)

        for desc, passp in candidates:
            if desc.agent_id == role_id:
                val = PassportVerifier.verify(
                    passport=passp,
                    evidence_verifier=self._evidence_verifier,
                    requirement=requirement,
                    expected_revision=desc.agent_revision,
                )
                if val.is_valid:
                    projection = PassportJudgeProjection(
                        tenant_id=tid,
                        role_id=role_id,
                        selected_agent_id=desc.agent_id,
                        selected_revision=desc.agent_revision,
                        qualified_capabilities=passp.qualified_capabilities,
                        qualification_evidence_ids=passp.qualification_evidence_ids,
                        rejected_candidates=tuple(rejected),
                    )
                    return desc, passp, projection
                else:
                    rejected.append(
                        RejectedCandidateProjection(
                            agent_id=desc.agent_id,
                            agent_revision=desc.agent_revision,
                            rejection_reason=val.failure_reason or "Capability mismatch",
                            status=val.status,
                        )
                    )

        req_caps = [c.value for c in requirement.required_capabilities]
        raise UnqualifiedAgentDispatchError(
            f"No qualified agent holding valid CapabilityPassport found for role {role_id!r} "
            f"with capabilities {req_caps}"
        )
