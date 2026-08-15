"""ChangeMesh domain contracts — rehearsal contracts.

P-05.04: RehearsalScenario and RehearsalResult represent typed
ShadowLab rehearsal definitions and their controlled results.

A ShadowLab rehearsal may succeed in SIMULATION.  That does NOT prove:
- real external execution,
- current cloud execution,
- permission to mutate a real target.

RehearsalScenario is data, not executable code.
RehearsalResult reuses existing P-05.03 evidence vocabulary
(EvidenceState, Provenance, ExecutionEvidenceMode).
"""

from typing import Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.conventions import UtcDateTime
from domain.contracts.evidence import (
    EvidenceState,
    ExecutionEvidenceMode,
    Provenance,
)


class FaultInjectionSpec(BaseModel):
    """Declarative fault-injection specification for rehearsal scenarios.

    Fault injection is expressed as typed data, never as executable
    callbacks or shell commands.

    Attributes:
        fault_id: Stable identity for this fault specification.
        fault_type: Category of fault (e.g. ``"latency"``,
            ``"error_response"``, ``"timeout"``).
        target: What the fault applies to (tool, service, etc.).
        parameters: Bounded key-value configuration for the fault.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fault_id: str
    fault_type: str
    target: str
    parameters: Tuple[Tuple[str, str], ...] = ()

    @field_validator("fault_id", "fault_type", "target")
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator("parameters")
    @classmethod
    def _validate_parameters(cls, v: Tuple[Tuple[str, str], ...]) -> Tuple[Tuple[str, str], ...]:
        for key, _ in v:
            if not key or not key.strip():
                raise ValueError("parameters keys must not be blank")
        return v


class RehearsalScenario(BaseModel):
    """Typed ShadowLab rehearsal scenario definition.

    ``RehearsalScenario`` is *data* — it describes what to rehearse,
    not how to execute it.  It contains no Python callbacks, SDK
    clients, executable functions, or credentials.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        scenario_id: Stable scenario identity.
        change_request_id: Associated change/request reference.
        description: Human-readable bounded description.
        target_refs: Target/scope references for the rehearsal.
        success_criterion_ids: References to success criteria
            that define rehearsal success.
        tool_double_ids: References to tool doubles where applicable.
        fault_injections: Declarative fault-injection specifications.
        created_at: Creation timestamp.
        scenario_version: Version identifier for this scenario
            definition.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    scenario_id: str
    change_request_id: str
    description: str
    target_refs: Tuple[str, ...]
    success_criterion_ids: Tuple[str, ...] = ()
    tool_double_ids: Tuple[str, ...] = ()
    fault_injections: Tuple[FaultInjectionSpec, ...] = ()
    created_at: UtcDateTime
    scenario_version: str

    @field_validator(
        "schema_version",
        "scenario_id",
        "change_request_id",
        "scenario_version",
        "description",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator(
        "target_refs",
        "success_criterion_ids",
        "tool_double_ids",
    )
    @classmethod
    def _validate_ref_tuples(cls, v: Tuple[str, ...], info) -> Tuple[str, ...]:
        for ref in v:
            if not ref or not ref.strip():
                raise ValueError(f"{info.field_name} elements must not be blank")
        if len(set(v)) != len(v):
            raise ValueError(f"{info.field_name} must not contain duplicate references")
        return v

    @model_validator(mode="after")
    def _validate_scenario_invariants(self):
        if not self.target_refs:
            raise ValueError("target_refs must not be empty")
        return self


class RehearsalResult(BaseModel):
    """Result of executing a RehearsalScenario in the ShadowLab.

    Reuses existing P-05.03 evidence vocabulary:
    - ``EvidenceState`` for typed result state,
    - ``Provenance`` for collection mode and source,
    - ``ExecutionEvidenceMode`` via Provenance.

    A ShadowLab RehearsalResult MUST represent controlled rehearsal:
    ``provenance.collection_mode == SIMULATION`` is required.

    A simulation PASS remains simulation proof only.

    Attributes:
        schema_version: Explicit contract version (e.g. ``"1.0.0"``).
        result_id: Stable result identity.
        scenario_id: Reference to the rehearsal scenario.
        change_request_id: Associated change/request reference.
        state: Typed result/evidence state.
        provenance: Provenance (must be SIMULATION for ShadowLab).
        started_at: When the rehearsal execution started.
        completed_at: When the rehearsal execution completed.
        evidence_record_ids: References to detailed evidence records.
        diagnostic_refs: Bounded diagnostic/correction references.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    result_id: str
    scenario_id: str
    change_request_id: str
    state: EvidenceState
    provenance: Provenance
    started_at: UtcDateTime
    completed_at: UtcDateTime
    evidence_record_ids: Tuple[str, ...] = ()
    diagnostic_refs: Tuple[str, ...] = ()

    @field_validator(
        "schema_version",
        "result_id",
        "scenario_id",
        "change_request_id",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v

    @field_validator(
        "evidence_record_ids",
        "diagnostic_refs",
    )
    @classmethod
    def _validate_ref_tuples(cls, v: Tuple[str, ...], info) -> Tuple[str, ...]:
        for ref in v:
            if not ref or not ref.strip():
                raise ValueError(f"{info.field_name} elements must not be blank")
        if len(set(v)) != len(v):
            raise ValueError(f"{info.field_name} must not contain duplicate references")
        return v

    @model_validator(mode="after")
    def _validate_rehearsal_invariants(self):
        # ShadowLab hard invariant: must be SIMULATION
        if self.provenance.collection_mode != ExecutionEvidenceMode.SIMULATION:
            raise ValueError(
                "ShadowLab RehearsalResult requires provenance.collection_mode == SIMULATION"
            )

        # Completion cannot precede start
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")

        # Executed results should carry evidence references
        if (
            self.state
            in (
                EvidenceState.PASS,
                EvidenceState.FAIL,
                EvidenceState.WARN,
                EvidenceState.SIMULATED,
            )
            and not self.evidence_record_ids
        ):
            raise ValueError(f"{self.state.value} result must have at least one evidence_record_id")

        # NOT_RUN/BLOCKED must not manufacture execution proof
        if (
            self.state
            in (
                EvidenceState.NOT_RUN,
                EvidenceState.BLOCKED,
            )
            and self.evidence_record_ids
        ):
            raise ValueError(f"{self.state.value} result must not carry evidence_record_ids")

        return self
