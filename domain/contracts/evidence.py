"""ChangeMesh domain contracts — evidence contracts."""

from enum import Enum
from typing import Any, Optional, Tuple

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


from domain.contracts.agent_descriptor import AgentRevisionProvenance
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
            raise ValueError(
                f"digest must be exactly 64 lowercase hex characters, "
                f"got {v!r}"
            )
        return v


class TraceReference(BaseModel):
    """Provider-neutral TraceReference contract."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str
    span_id: Optional[str] = None

    @field_validator("trace_id", "span_id")
    @classmethod
    def _must_not_be_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class Provenance(BaseModel):
    """Provenance contract describing origin, collection mode, and agent revision.

    When evidence is produced or recorded by an agent, `agent_id` and
    `agent_revision` (or `agent_provenance`) provide exact machine-checkable
    agent revision provenance.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    source: str
    collection_mode: ExecutionEvidenceMode
    collection_timestamp: UtcDateTime
    source_execution_identifier: Optional[str] = None
    source_execution_timestamp: Optional[UtcDateTime] = None
    agent_id: Optional[str] = None
    agent_revision: Optional[str] = None
    agent_role: Optional[str] = None
    agent_provenance: Optional[AgentRevisionProvenance] = None

    @field_validator("schema_version", "source", "source_execution_identifier")
    @classmethod
    def _must_not_be_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("agent_id", "agent_revision")
    @classmethod
    def _validate_agent_id_and_revision(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None:
            if not v or not v.strip():
                raise ValueError(f"{info.field_name} must not be blank")
            cleaned = v.strip()
            if cleaned.lower() in ("unknown", "latest", "current", "null", "none", "*", "undefined"):
                raise ValueError(f"{info.field_name} cannot be an ambiguous escape hatch: {v!r}")
            return cleaned
        return None

    @field_validator("agent_role")
    @classmethod
    def _validate_agent_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or not v.strip():
                raise ValueError("agent_role must not be blank when provided")
            return v.strip()
        return None

    @model_validator(mode="before")
    @classmethod
    def _sync_agent_provenance_before(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ap = data.get("agent_provenance")
            if ap is not None:
                if isinstance(ap, AgentRevisionProvenance):
                    data.setdefault("agent_id", ap.agent_id)
                    data.setdefault("agent_revision", ap.agent_revision)
                    if ap.role and "agent_role" not in data:
                        data["agent_role"] = ap.role
                elif isinstance(ap, dict):
                    data.setdefault("agent_id", ap.get("agent_id"))
                    data.setdefault("agent_revision", ap.get("agent_revision"))
                    if ap.get("role") and "agent_role" not in data:
                        data["agent_role"] = ap.get("role")
            elif data.get("agent_id") is not None and data.get("agent_revision") is not None:
                data["agent_provenance"] = AgentRevisionProvenance(
                    agent_id=data["agent_id"],
                    agent_revision=data["agent_revision"],
                    role=data.get("agent_role"),
                )
        return data

    @model_validator(mode="after")
    def _validate_agent_provenance_completeness(self):
        # Enforce mutual completeness: agent_id requires agent_revision and vice-versa
        has_id = self.agent_id is not None
        has_rev = self.agent_revision is not None
        if has_id != has_rev:
            raise ValueError(
                "Agent revision provenance requires both agent_id and agent_revision; "
                f"got agent_id={self.agent_id!r}, agent_revision={self.agent_revision!r}"
            )
        return self

    def get_agent_provenance(self) -> Optional[AgentRevisionProvenance]:
        """Return structured AgentRevisionProvenance if agent metadata is present."""
        if self.agent_provenance is not None:
            return self.agent_provenance
        if self.agent_id is not None and self.agent_revision is not None:
            return AgentRevisionProvenance(
                agent_id=self.agent_id,
                agent_revision=self.agent_revision,
                role=self.agent_role,
            )
        return None


class EvidenceRecord(BaseModel):
    """Canonical provider-neutral evidence fact schema."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    evidence_id: str
    change_request_id: str
    subject: str
    state: EvidenceState
    provenance: Provenance
    trace: Optional[TraceReference] = None
    artifacts: Tuple[ArtifactHash, ...] = ()

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
            if self.provenance.collection_mode not in (ExecutionEvidenceMode.FIXTURE, ExecutionEvidenceMode.SIMULATION):
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
