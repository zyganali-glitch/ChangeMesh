"""ChangeMesh Specialized Agent Input and Output Schemas.

P-07.02: Implement six specialized ADK agent definitions with bounded instructions/tool sets.
This module defines the machine-checkable input and output contract schemas for
all specialized agents in the ChangeMesh fleet.

Invariants:
- All models are frozen and reject extra fields (extra="forbid").
- String identifiers and schema versions must not be blank.
- No provider SDK objects, credentials, or mutable runtime handles are included.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.contracts.data_class import DataClassLevel

# ===========================================================================
# 1. Impact Scout Schemas
# ===========================================================================


class ImpactScoutInput(BaseModel):
    """Input boundary schema for the Impact Scout agent.

    Describes the target repository, proposed changes, and data scope
    for blast-radius and conflict analysis.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    target_systems: list[str] = Field(min_length=1)
    repository_ref: str
    proposed_diff_ref: str | None = None
    data_classification: DataClassLevel = DataClassLevel.INTERNAL

    @field_validator("schema_version", "change_id", "repository_ref")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class ImpactScoutOutput(BaseModel):
    """Output boundary schema for the Impact Scout agent.

    Carries blast-radius assessment, affected files/systems, and conflict status.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    affected_files: list[str] = Field(default_factory=list)
    affected_systems: list[str] = Field(default_factory=list)
    conflict_detected: bool = False
    risk_level: str = "LOW"
    blast_radius_score: float = 0.0
    deterministic_evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("schema_version", "change_id", "risk_level")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


# ===========================================================================
# 2. Policy Guardian Schemas
# ===========================================================================


class PolicyGuardianInput(BaseModel):
    """Input boundary schema for the Policy Guardian agent.

    Carries the change parameters and context required for policy compliance
    and autonomy classification evaluation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    data_classification: DataClassLevel
    target_systems: list[str] = Field(min_length=1)
    requested_actions: list[str] = Field(min_length=1)
    actor_identity: str

    @field_validator("schema_version", "change_id", "actor_identity")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class PolicyGuardianOutput(BaseModel):
    """Output boundary schema for the Policy Guardian agent.

    Carries the policy evaluation verdict, autonomy classification, and
    required evidence types.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    policy_verdict: str
    autonomy_class: str
    violated_rules: list[str] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)

    @field_validator("schema_version", "change_id", "policy_verdict", "autonomy_class")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


# ===========================================================================
# 3. Migration Engineer Schemas
# ===========================================================================


class MigrationEngineerInput(BaseModel):
    """Input boundary schema for the Migration Engineer agent.

    Carries the migration specification, schema version transition, and target system.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    target_system: str
    source_schema_version: str
    target_schema_version: str
    migration_spec: str

    @field_validator(
        "schema_version",
        "change_id",
        "target_system",
        "source_schema_version",
        "target_schema_version",
        "migration_spec",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class MigrationEngineerOutput(BaseModel):
    """Output boundary schema for the Migration Engineer agent.

    Carries generated migration artifacts, verification instructions, and reversibility flag.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    artifact_id: str
    artifact_hash: str
    migration_script_content: str
    rehearsal_instructions: str
    is_reversible: bool = True

    @field_validator(
        "schema_version",
        "change_id",
        "artifact_id",
        "artifact_hash",
        "migration_script_content",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


# ===========================================================================
# 4. Evidence Auditor Schemas
# ===========================================================================


class EvidenceAuditorInput(BaseModel):
    """Input boundary schema for the Evidence Auditor agent.

    Carries success criteria and references to collected evidence records
    for semantic sufficiency evaluation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    success_criteria_ids: list[str] = Field(min_length=1)
    evidence_record_refs: list[str] = Field(min_length=1)
    rehearsal_result_refs: list[str] = Field(default_factory=list)

    @field_validator("schema_version", "change_id")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class EvidenceAuditorOutput(BaseModel):
    """Output boundary schema for the Evidence Auditor agent.

    Carries semantic sufficiency verdict and evaluated criteria statistics.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    sufficiency_verdict: str
    evaluated_criteria_count: int = Field(ge=0)
    satisfied_criteria_count: int = Field(ge=0)
    unmet_criteria_ids: list[str] = Field(default_factory=list)
    semantic_review_summary: str

    @field_validator(
        "schema_version", "change_id", "sufficiency_verdict", "semantic_review_summary"
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


# ===========================================================================
# 5. Release Steward Schemas
# ===========================================================================


class ReleaseStewardInput(BaseModel):
    """Input boundary schema for the Release Steward agent.

    Carries passport ID, verified artifact IDs, target repository, and authorization evidence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    passport_id: str
    verified_artifact_ids: list[str] = Field(min_length=1)
    target_repository: str
    authorization_reference: str

    @field_validator(
        "schema_version",
        "change_id",
        "passport_id",
        "target_repository",
        "authorization_reference",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class ReleaseStewardOutput(BaseModel):
    """Output boundary schema for the Release Steward agent.

    Carries release bundle identifier, draft PR specification, and rollback specification.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    release_bundle_id: str
    draft_pr_spec: str
    rollback_spec: str
    handoff_ready: bool = True
    requires_live_confirmation: bool = False

    @field_validator(
        "schema_version",
        "change_id",
        "release_bundle_id",
        "draft_pr_spec",
        "rollback_spec",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()
