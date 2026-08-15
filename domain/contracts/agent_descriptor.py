"""ChangeMesh domain contracts — agent descriptor."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.data_class import DataClassLevel


class AgentRevisionProvenance(BaseModel):
    """Exact machine-checkable agent identity and revision provenance.

    Binds the stable agent identity (`agent_id`) to its exact semantic
    revision (`agent_revision`) and optional role descriptor (`role`).

    Invariants:
    - `agent_id` and `agent_revision` are mandatory non-blank strings.
    - Ambiguous escape hatches (e.g. "unknown", "latest", "current",
      "null", "none", "*", "undefined") are strictly rejected.
    - Provider-neutral: no Google SDKs, ADK, credentials, or sessions.
    - Immutability: frozen and extra-forbid.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    agent_revision: str
    role: Optional[str] = None

    @field_validator("agent_id", "agent_revision")
    @classmethod
    def _validate_non_blank_and_no_escape(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        cleaned = v.strip()
        if cleaned.lower() in ("unknown", "latest", "current", "null", "none", "*", "undefined"):
            raise ValueError(f"{info.field_name} cannot be an ambiguous escape hatch: {v!r}")
        return cleaned

    @field_validator("role")
    @classmethod
    def _validate_role_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or not v.strip():
                raise ValueError("role must not be blank when provided")
            return v.strip()
        return None


class AgentDescriptor(BaseModel):
    """Declared identity, role, and capabilities of an agent revision.

    ``AgentDescriptor`` is metadata describing *what* an agent is and
    *what it claims to do*.  It is **not** a ``CapabilityPassport``
    (P-05.04) — it carries no qualification proof, trust evidence,
    signature validity, or authorization state.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        agent_id: Stable agent identity.
        agent_revision: Specific revision / version of the agent.
        role: Declared role (e.g. ``"impact_scout"``).
        description: What the agent does.
        declared_capabilities: Capabilities the agent claims.
        permitted_data_classifications: Data-class scope the agent may
            handle (typed ``DataClassLevel`` values).
        permitted_tool_ids: Tool-scope boundary.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    agent_id: str
    agent_revision: str
    role: str
    description: str
    declared_capabilities: list[str]
    permitted_data_classifications: list[DataClassLevel]
    permitted_tool_ids: list[str]

    @field_validator("agent_id", "schema_version", "agent_revision")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    def get_revision_provenance(self) -> AgentRevisionProvenance:
        """Return canonical machine-checkable AgentRevisionProvenance."""
        return AgentRevisionProvenance(
            agent_id=self.agent_id,
            agent_revision=self.agent_revision,
            role=self.role,
        )
