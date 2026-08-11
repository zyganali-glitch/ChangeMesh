"""ChangeMesh domain contracts — agent descriptor."""

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.data_class import DataClassLevel


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

    @field_validator("agent_id", "schema_version")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v
