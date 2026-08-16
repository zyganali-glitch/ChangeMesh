"""ChangeMesh Agent Registry and Capability Passport package.

P-12: Manages capability qualification, proof-carrying Capability Passports,
revision-locked qualification validation, and passport-aware routing.
"""

from domain.contracts.capability import CapabilityPassport
from src.registry.agent_registry import AgentDescriptor, AgentRegistry, InMemoryAgentRegistry
from src.registry.capabilities import (
    AgentCapabilityRequirement,
    CapabilityType,
    get_standard_demo_requirements,
)
from src.registry.passport_issuer import (
    PassportIssuanceRequest,
    PassportIssuer,
    PassportValidationResult,
    PassportVerifier,
)
from src.registry.passport_router import PassportAwareRouter, UnqualifiedAgentDispatchError

__all__ = [
    "CapabilityPassport",
    "CapabilityType",
    "AgentCapabilityRequirement",
    "get_standard_demo_requirements",
    "PassportIssuanceRequest",
    "PassportIssuer",
    "PassportVerifier",
    "PassportValidationResult",
    "AgentDescriptor",
    "AgentRegistry",
    "InMemoryAgentRegistry",
    "PassportAwareRouter",
    "UnqualifiedAgentDispatchError",
]
