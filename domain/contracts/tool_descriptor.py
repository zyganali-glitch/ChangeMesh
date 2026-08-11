"""ChangeMesh domain contracts — tool descriptor."""

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from domain.contracts.data_class import DataClassLevel


class ToolDescriptor(BaseModel):
    """Describes a tool's interface and capability boundary.

    ``ToolDescriptor`` is a *description* of a tool — its identity,
    declared actions, and data scope.  It is **not** a live tool client,
    SDK wrapper, or execution evidence.

    ``AVAILABLE`` status never implies a tool call actually occurred.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        tool_id: Stable tool identity.
        tool_revision: Specific revision of the tool.
        name: Human-readable tool name.
        description: What the tool does.
        declared_actions: Actions / operations the tool supports.
        is_read_only: Whether the tool only reads (``True``) or can
            also write (``False``).
        permitted_data_classifications: Data-sensitivity scope the tool
            may handle (typed ``DataClassLevel`` values).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    tool_id: str
    tool_revision: str
    name: str
    description: str
    declared_actions: list[str]
    is_read_only: StrictBool
    permitted_data_classifications: list[DataClassLevel]

    @field_validator("tool_id", "schema_version", "tool_revision")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v
