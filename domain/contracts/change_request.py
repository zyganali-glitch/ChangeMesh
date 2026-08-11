"""ChangeMesh domain contracts — change request."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.data_class import DataClassLevel
from domain.contracts.success_criterion import SuccessCriterion


class ChangeRequest(BaseModel):
    """Typed user/change intent entering ChangeMesh.

    ``ChangeRequest`` is an *intent* contract — it describes what
    someone wants to change and why.  It is **not** workflow state,
    execution proof, or approval result.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        request_id: Stable change-request identifier.
        title: Brief human-readable title.
        description: Detailed change description / goal.
        target_systems: Systems or repositories targeted by this change.
        data_classification: Data-sensitivity scope for the change
            (typed ``DataClassLevel``, not an arbitrary string).
        success_criteria: Typed criteria using the ``SuccessCriterion``
            contract (not untyped dictionaries).
        requested_by: Who or what originated the request.
        requested_at: Timestamp when the request was created.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    request_id: str
    title: str
    description: str
    target_systems: list[str]
    data_classification: DataClassLevel
    success_criteria: list[SuccessCriterion]
    requested_by: str
    requested_at: datetime

    @field_validator("request_id", "schema_version")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v
