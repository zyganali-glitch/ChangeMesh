"""ChangeMesh Agent Registry interface and local in-memory implementation.

P-12.04 & P-12.05: Manages agent descriptors, multiple agent revisions,
and active capability passport indexing.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.capability import CapabilityPassport
from domain.contracts.conventions import UtcDateTime
from src.registry.capabilities import CapabilityType
from src.registry.passport_issuer import PassportValidationResult, PassportVerifier
from src.orchestrator.state_repository import TenantIsolationError, validate_tenant_id

CANONICAL_SCHEMA_VERSION = "1.0.0"


class AgentDescriptor(BaseModel):
    """Declarative descriptor for an agent revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    agent_id: str
    agent_name: str
    agent_role: str
    agent_revision: str
    description: str
    declared_capabilities: Tuple[str, ...]

    @field_validator("agent_id", "agent_name", "agent_role", "agent_revision", "description")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class AgentRegistry(ABC):
    """Abstract interface for ChangeMesh Agent Registry."""

    @abstractmethod
    def register_agent(self, descriptor: AgentDescriptor) -> AgentDescriptor:
        """Register an agent revision descriptor."""
        pass

    @abstractmethod
    def register_passport(self, tenant_id: str, passport: CapabilityPassport) -> CapabilityPassport:
        """Register an issued capability passport."""
        pass

    @abstractmethod
    def get_descriptor(self, agent_id: str, agent_revision: str) -> Optional[AgentDescriptor]:
        """Fetch agent descriptor by ID and revision."""
        pass

    @abstractmethod
    def get_active_passport(self, tenant_id: str, agent_id: str, agent_revision: str) -> Optional[CapabilityPassport]:
        """Fetch active, valid passport for exact agent revision."""
        pass

    @abstractmethod
    def find_qualified_agents(
        self,
        tenant_id: str,
        required_capability: CapabilityType,
    ) -> List[Tuple[AgentDescriptor, CapabilityPassport]]:
        """Find all registered agent revisions holding an active passport for the required capability."""
        pass


class InMemoryAgentRegistry(AgentRegistry):
    """Thread-safe in-memory test double and local adapter for Agent Registry."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._descriptors: Dict[Tuple[str, str], AgentDescriptor] = {}  # (agent_id, revision) -> descriptor
        self._passports: Dict[str, Dict[Tuple[str, str], CapabilityPassport]] = {}  # tenant_id -> (agent_id, revision) -> passport

    def register_agent(self, descriptor: AgentDescriptor) -> AgentDescriptor:
        with self._lock:
            key = (descriptor.agent_id, descriptor.agent_revision)
            self._descriptors[key] = descriptor
            return descriptor

    def register_passport(self, tenant_id: str, passport: CapabilityPassport) -> CapabilityPassport:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            tenant_passports = self._passports.setdefault(tid, {})
            key = (passport.agent_id, passport.agent_revision)
            tenant_passports[key] = passport
            return passport

    def get_descriptor(self, agent_id: str, agent_revision: str) -> Optional[AgentDescriptor]:
        with self._lock:
            return self._descriptors.get((agent_id, agent_revision))

    def get_active_passport(self, tenant_id: str, agent_id: str, agent_revision: str) -> Optional[CapabilityPassport]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            passport = self._passports.get(tid, {}).get((agent_id, agent_revision))
            if passport is None:
                return None
            res = PassportVerifier.verify(passport, expected_revision=agent_revision)
            return passport if res.is_valid else None

    def find_qualified_agents(
        self,
        tenant_id: str,
        required_capability: CapabilityType,
    ) -> List[Tuple[AgentDescriptor, CapabilityPassport]]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            results: List[Tuple[AgentDescriptor, CapabilityPassport]] = []
            tenant_passports = self._passports.get(tid, {})

            for (aid, rev), passport in tenant_passports.items():
                descriptor = self._descriptors.get((aid, rev))
                if descriptor is None:
                    continue
                # Verify passport
                val_res = PassportVerifier.verify(passport, expected_revision=rev)
                if val_res.is_valid and required_capability.value in passport.qualified_capabilities:
                    results.append((descriptor, passport))

            return results
