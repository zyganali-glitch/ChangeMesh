"""ChangeMesh domain contracts — evidence contracts."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ExecutionEvidenceMode(str, Enum):
    """Canonical collection mode for execution evidence."""

    FIXTURE = "FIXTURE"
    SIMULATION = "SIMULATION"
    RECORDED_CLOUD = "RECORDED_CLOUD"
    LIVE_WRITE = "LIVE_WRITE"


class EvidenceState(str, Enum):
    """Canonical evidence state."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    SIMULATED = "SIMULATED"
    BLOCKED = "BLOCKED"
    QUARANTINED = "QUARANTINED"


from domain.contracts.conventions import (
    HashAlgorithm,
    UtcDateTime,
    is_valid_sha256_digest,
)


class ArtifactHash(BaseModel):
    """Provider-neutral ArtifactHash contract.

    Uses the canonical ``HashAlgorithm`` enum (P-05.06) and validates
    digest format: exactly 64 lowercase hexadecimal characters for
    SHA-256.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    algorithm: HashAlgorithm
    digest: str

    @field_validator("schema_version")
    @classmethod
    def _schema_version_not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("digest")
    @classmethod
    def _validate_digest(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError("digest must not be blank")
        if not is_valid_sha256_digest(v):
            raise ValueError(f"digest must be exactly 64 lowercase hex characters, got {v!r}")
        return v


class TraceReference(BaseModel):
    """Provider-neutral TraceReference contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str
    span_id: str | None = None

    @field_validator("trace_id", "span_id")
    @classmethod
    def _must_not_be_blank(cls, v: str | None, info) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class Provenance(BaseModel):
    """Provenance contract describing origin and mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    source: str
    collection_mode: ExecutionEvidenceMode
    collection_timestamp: UtcDateTime
    source_execution_identifier: str | None = None
    source_execution_timestamp: UtcDateTime | None = None

    @field_validator("schema_version", "source", "source_execution_identifier")
    @classmethod
    def _must_not_be_blank(cls, v: str | None, info) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class EvidenceRecord(BaseModel):
    """Canonical provider-neutral evidence fact schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    evidence_id: str
    change_request_id: str
    subject: str
    state: EvidenceState
    provenance: Provenance
    trace: TraceReference | None = None
    artifacts: tuple[ArtifactHash, ...] = ()

    @field_validator("schema_version", "evidence_id", "change_request_id", "subject")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @model_validator(mode="after")
    def _validate_ambiguity_and_historical(self):
        # SIMULATED ambiguity check
        if self.state == EvidenceState.SIMULATED:
            if self.provenance.collection_mode not in (
                ExecutionEvidenceMode.FIXTURE,
                ExecutionEvidenceMode.SIMULATION,
            ):
                raise ValueError("SIMULATED state is only valid with FIXTURE or SIMULATION mode")

        # RECORDED_CLOUD historical provenance check
        if self.provenance.collection_mode == ExecutionEvidenceMode.RECORDED_CLOUD:
            if not self.provenance.source_execution_identifier:
                raise ValueError("RECORDED_CLOUD evidence requires source_execution_identifier")
            if not self.provenance.source_execution_timestamp:
                raise ValueError("RECORDED_CLOUD evidence requires source_execution_timestamp")
            if not self.artifacts:
                raise ValueError("RECORDED_CLOUD evidence requires at least one artifact hash")

        return self
