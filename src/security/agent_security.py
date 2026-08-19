"""ChangeMesh Agent Identity, Gateway, and Model Armor.

P-23: Implements agent identity contracts, gateway simulation, model armor
fallbacks, and least-privilege enforcement. When managed services (Agent
Identity, Gateway, Model Armor) are unavailable (PERMISSION_BLOCKED),
provides explicit fallback labels and local enforcement.

P-23.01: Distinct agent identities with least-privilege roles.
P-23.02: Gateway registration and unregistered egress denial.
P-23.03: Model Armor injection/sensitive-data controls.
P-23.04: Explicit fallback labels when managed service unavailable.
P-23.05: Least-privilege and unauthorized-tool enforcement.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import FrozenSet, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from src.orchestrator.state_repository import CANONICAL_SCHEMA_VERSION

logger = logging.getLogger(__name__)


# =========================================================================
# P-23.01 — Agent Identity and Least-Privilege
# =========================================================================


class AgentPermission(str, Enum):
    """Granular permissions for agent operations."""

    READ_STATE = "READ_STATE"
    WRITE_STATE = "WRITE_STATE"
    EMIT_EVENT = "EMIT_EVENT"
    CREATE_CHECKPOINT = "CREATE_CHECKPOINT"
    EXECUTE_TASK = "EXECUTE_TASK"
    APPROVE_AUTHORITY = "APPROVE_AUTHORITY"
    EXTERNAL_WRITE = "EXTERNAL_WRITE"
    DEAD_LETTER = "DEAD_LETTER"
    MANAGE_AGENTS = "MANAGE_AGENTS"


class ManagedServiceStatus(str, Enum):
    """Status of a managed service dependency.

    P-23.04: Explicit fallback labels when managed service unavailable.
    """

    AVAILABLE = "AVAILABLE"
    PERMISSION_BLOCKED = "PERMISSION_BLOCKED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FALLBACK_LOCAL = "FALLBACK_LOCAL"


class AgentIdentity(BaseModel):
    """Distinct agent identity with least-privilege permissions.

    P-23.01: Each identity has only required roles.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    agent_id: str
    agent_revision: str
    role: str
    permissions: FrozenSet[AgentPermission]
    tenant_scope: Optional[str] = None
    is_service_account: bool = False

    @field_validator("agent_id", "agent_revision", "role")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class AgentIdentityRegistry:
    """Registry for agent identities with least-privilege enforcement.

    P-23.01: Avoid shared broad service account.
    P-23.05: Unauthorized agent/tool/data combinations fail closed.
    """

    def __init__(self) -> None:
        self._identities: dict[str, AgentIdentity] = {}

    def register(self, identity: AgentIdentity) -> None:
        self._identities[identity.agent_id] = identity

    def get(self, agent_id: str) -> Optional[AgentIdentity]:
        return self._identities.get(agent_id)

    def check_permission(
        self,
        agent_id: str,
        permission: AgentPermission,
    ) -> bool:
        """Check if agent has a specific permission.

        P-23.05: Returns False (fail closed) for unknown agents.
        """
        identity = self._identities.get(agent_id)
        if identity is None:
            return False  # Fail closed: unknown agent has no permissions
        return permission in identity.permissions

    def require_permission(
        self,
        agent_id: str,
        permission: AgentPermission,
    ) -> None:
        """Require a permission, raising ValueError if denied.

        P-23.05: Unauthorized combinations fail closed.
        """
        if not self.check_permission(agent_id, permission):
            raise ValueError(
                f"Agent {agent_id!r} denied permission {permission.value}: "
                f"least-privilege enforcement"
            )


# =========================================================================
# P-23.02 — Gateway Registration
# =========================================================================


class GatewayEndpoint(BaseModel):
    """Registered gateway endpoint.

    P-23.02: Unregistered egress denied/audited.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    endpoint_id: str
    url_pattern: str
    allowed_methods: FrozenSet[str]
    allowed_agents: FrozenSet[str]
    is_dry_run: bool = True


class GatewayRegistry:
    """Gateway registry with deny-by-default for unregistered endpoints.

    P-23.02: Configure Gateway dry-run first.
    """

    def __init__(
        self,
        *,
        service_status: ManagedServiceStatus = ManagedServiceStatus.FALLBACK_LOCAL,
    ) -> None:
        self._endpoints: dict[str, GatewayEndpoint] = {}
        self.service_status = service_status

    def register_endpoint(self, endpoint: GatewayEndpoint) -> None:
        self._endpoints[endpoint.endpoint_id] = endpoint

    def check_egress(
        self,
        endpoint_id: str,
        agent_id: str,
        method: str = "GET",
    ) -> tuple[bool, str]:
        """Check if egress is allowed.

        Returns (allowed, reason).
        P-23.02: Unregistered egress denied.
        """
        endpoint = self._endpoints.get(endpoint_id)
        if endpoint is None:
            return False, f"Endpoint {endpoint_id!r} not registered: egress denied"

        if agent_id not in endpoint.allowed_agents:
            return False, f"Agent {agent_id!r} not in allowed_agents for {endpoint_id}"

        if method not in endpoint.allowed_methods:
            return False, f"Method {method!r} not allowed for {endpoint_id}"

        if endpoint.is_dry_run:
            return True, f"DRY_RUN: egress would be allowed for {endpoint_id}"

        return True, f"Egress allowed for {endpoint_id}"


# =========================================================================
# P-23.03 — Model Armor (Fallback)
# =========================================================================


class ModelArmorResult(BaseModel):
    """Result of model armor check.

    P-23.03: Malicious input blocked/redacted with evidence.
    P-23.04: Explicit fallback label when managed service unavailable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_safe: bool
    reason: str
    service_status: ManagedServiceStatus
    blocked_patterns: int = 0


class LocalModelArmor:
    """Local fallback model armor when managed service is PERMISSION_BLOCKED.

    P-23.03: Basic injection detection for ingress/egress.
    P-23.04: Local control never presented as managed proof.
    """

    INJECTION_PATTERNS = (
        "ignore previous instructions",
        "ignore all instructions",
        "system prompt",
        "you are now",
        "<script>",
        "DROP TABLE",
        "'; --",
        "UNION SELECT",
    )

    def __init__(
        self,
        *,
        service_status: ManagedServiceStatus = ManagedServiceStatus.FALLBACK_LOCAL,
    ) -> None:
        self.service_status = service_status

    def check_input(self, text: str) -> ModelArmorResult:
        """Check input for injection patterns.

        P-23.04: Always reports service_status accurately.
        """
        text_lower = text.lower()
        blocked = sum(1 for p in self.INJECTION_PATTERNS if p.lower() in text_lower)

        if blocked > 0:
            return ModelArmorResult(
                is_safe=False,
                reason=f"LOCAL_FALLBACK: {blocked} injection pattern(s) detected",
                service_status=self.service_status,
                blocked_patterns=blocked,
            )

        return ModelArmorResult(
            is_safe=True,
            reason="LOCAL_FALLBACK: no injection patterns detected",
            service_status=self.service_status,
        )


# =========================================================================
# P-23.04 — Service Availability Report
# =========================================================================


class ServiceAvailabilityReport(BaseModel):
    """Report on managed service availability.

    P-23.04: Explicit fallback labels.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_identity_status: ManagedServiceStatus = ManagedServiceStatus.PERMISSION_BLOCKED
    gateway_status: ManagedServiceStatus = ManagedServiceStatus.FALLBACK_LOCAL
    model_armor_status: ManagedServiceStatus = ManagedServiceStatus.PERMISSION_BLOCKED
    fallback_active: bool = True
    evidence_label: str = "LOCAL_FALLBACK"
