"""ChangeMesh domain contracts — evidence contracts."""

from enum import Enum
from typing import Any, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.agent_descriptor import AgentRevisionProvenance
from domain.contracts.conventions import (
    HashAlgorithm,
    UtcDateTime,
    is_valid_sha256_digest,
)


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
    span_id: Optional[str] = None

    @field_validator("trace_id", "span_id")
    @classmethod
    def _must_not_be_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class EvidenceProducerKind(str, Enum):
    """Canonical classification for the entity or system producing evidence."""

    AGENT = "AGENT"
    NON_AGENT = "NON_AGENT"
    SYSTEM = "SYSTEM"
    FIXTURE = "FIXTURE"
    SIMULATION = "SIMULATION"
    RECORDED_CLOUD = "RECORDED_CLOUD"


class Provenance(BaseModel):
    """Provenance contract describing origin, collection mode, producer kind, and agent revision.

    When evidence is produced or recorded by an agent (producer_kind=AGENT or agent_id/provenance),
    `agent_id` and `agent_revision` (and `agent_provenance`) provide exact machine-checkable
    agent revision provenance with zero escape hatches.

    When evidence is produced by a non-agent source (producer_kind in NON_AGENT, FIXTURE, etc.),
    agent provenance fields MUST be None.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    source: str
    collection_mode: ExecutionEvidenceMode
    collection_timestamp: UtcDateTime
    source_execution_identifier: Optional[str] = None
    source_execution_timestamp: Optional[UtcDateTime] = None
    producer_kind: EvidenceProducerKind = EvidenceProducerKind.NON_AGENT
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
            if cleaned.lower() in (
                "unknown",
                "latest",
                "current",
                "null",
                "none",
                "*",
                "undefined",
            ):
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
                ap_id: Optional[str] = None
                ap_rev: Optional[str] = None
                ap_role: Optional[str] = None
                if isinstance(ap, AgentRevisionProvenance):
                    ap_id = ap.agent_id
                    ap_rev = ap.agent_revision
                    ap_role = ap.role
                elif isinstance(ap, dict):
                    ap_id = ap.get("agent_id")
                    ap_rev = ap.get("agent_revision")
                    ap_role = ap.get("role")
                else:
                    ap_id = getattr(ap, "agent_id", None)
                    ap_rev = getattr(ap, "agent_revision", None)
                    ap_role = getattr(ap, "role", None)

                # Contradiction checks between flattened fields and structured agent_provenance
                if (
                    "agent_id" in data
                    and data["agent_id"] is not None
                    and data["agent_id"] != ap_id
                ):
                    raise ValueError(
                        f"agent_id ({data['agent_id']!r}) does not match "
                        f"agent_provenance.agent_id ({ap_id!r})"
                    )
                if (
                    "agent_revision" in data
                    and data["agent_revision"] is not None
                    and data["agent_revision"] != ap_rev
                ):
                    raise ValueError(
                        f"agent_revision ({data['agent_revision']!r}) does not match "
                        f"agent_provenance.agent_revision ({ap_rev!r})"
                    )
                if (
                    "agent_role" in data
                    and data["agent_role"] is not None
                    and ap_role is not None
                    and data["agent_role"] != ap_role
                ):
                    raise ValueError(
                        f"agent_role ({data['agent_role']!r}) does not match "
                        f"agent_provenance.role ({ap_role!r})"
                    )

                data["agent_id"] = ap_id
                data["agent_revision"] = ap_rev
                if ap_role and "agent_role" not in data:
                    data["agent_role"] = ap_role
                if "producer_kind" not in data:
                    data["producer_kind"] = EvidenceProducerKind.AGENT.value

            elif (
                data.get("agent_id") is not None
                or data.get("agent_revision") is not None
                or data.get("agent_role") is not None
            ):
                if "producer_kind" not in data:
                    data["producer_kind"] = EvidenceProducerKind.AGENT.value
                if data.get("agent_id") is not None and data.get("agent_revision") is not None:
                    data["agent_provenance"] = AgentRevisionProvenance(
                        agent_id=data["agent_id"],
                        agent_revision=data["agent_revision"],
                        role=data.get("agent_role"),
                    )
            elif "producer_kind" not in data:
                # Infer default non-agent producer kind based on collection mode
                mode = data.get("collection_mode")
                if (
                    mode == ExecutionEvidenceMode.FIXTURE
                    or mode == ExecutionEvidenceMode.FIXTURE.value
                ):
                    data["producer_kind"] = EvidenceProducerKind.FIXTURE.value
                elif (
                    mode == ExecutionEvidenceMode.SIMULATION
                    or mode == ExecutionEvidenceMode.SIMULATION.value
                ):
                    data["producer_kind"] = EvidenceProducerKind.SIMULATION.value
                elif (
                    mode == ExecutionEvidenceMode.RECORDED_CLOUD
                    or mode == ExecutionEvidenceMode.RECORDED_CLOUD.value
                ):
                    data["producer_kind"] = EvidenceProducerKind.RECORDED_CLOUD.value
                else:
                    data["producer_kind"] = EvidenceProducerKind.NON_AGENT.value
        return data

    @model_validator(mode="after")
    def _validate_provenance_consistency(self):
        if self.producer_kind == EvidenceProducerKind.AGENT:
            if self.agent_id is None or self.agent_revision is None:
                raise ValueError(
                    "Agent-produced evidence (producer_kind=AGENT) requires exact "
                    "agent_id and agent_revision"
                )
            if self.agent_provenance is None:
                raise ValueError(
                    "Agent-produced evidence (producer_kind=AGENT) requires structured "
                    "agent_provenance"
                )
            if self.agent_id != self.agent_provenance.agent_id:
                raise ValueError(
                    f"agent_id ({self.agent_id!r}) does not match "
                    f"agent_provenance.agent_id ({self.agent_provenance.agent_id!r})"
                )
            if self.agent_revision != self.agent_provenance.agent_revision:
                raise ValueError(
                    f"agent_revision ({self.agent_revision!r}) does not match "
                    f"agent_provenance.agent_revision ({self.agent_provenance.agent_revision!r})"
                )
            if self.agent_role is not None and self.agent_provenance.role is not None:
                if self.agent_role != self.agent_provenance.role:
                    raise ValueError(
                        f"agent_role ({self.agent_role!r}) does not match "
                        f"agent_provenance.role ({self.agent_provenance.role!r})"
                    )
        else:
            if (
                self.agent_id is not None
                or self.agent_revision is not None
                or self.agent_role is not None
                or self.agent_provenance is not None
            ):
                raise ValueError(
                    f"Non-agent evidence (producer_kind={self.producer_kind.value}) cannot specify "
                    f"agent_id={self.agent_id!r}, agent_revision={self.agent_revision!r}, "
                    f"agent_role={self.agent_role!r}, or agent_provenance={self.agent_provenance!r}"
                )
        return self

    @property
    def is_agent_produced(self) -> bool:
        """Return True if this provenance represents an agent-origin action."""
        return self.producer_kind == EvidenceProducerKind.AGENT

    def get_agent_provenance(self) -> Optional[AgentRevisionProvenance]:
        """Return structured AgentRevisionProvenance if agent metadata is present."""
        if self.producer_kind == EvidenceProducerKind.AGENT:
            return self.agent_provenance
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
