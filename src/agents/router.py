"""ChangeMesh Deterministic Routing and Delegation Engine.

P-07.03: Implement deterministic routing/delegation for initial workflow.
This module implements the deterministic capability and contract matching engine
for the ChangeMesh agent fleet.

Responsibilities:
- Route delegation requests strictly based on deterministic capability and contract match.
- Orchestrator coordinates routing; cannot delegate to itself.
- Valid delegation targets are strictly the five specialized agents:
  Impact Scout, Policy Guardian, Migration Engineer, Evidence Auditor, Release Steward.
- Exact string matching for declared capabilities against canonical P-07.02 definitions
  (no fuzzy, no substring, no synonyms, no invented capabilities).
- Exact input contract validation against target agent's canonical input_schema.
- Canonical provenance is non-bypassable: caller/injected definitions cannot invent
  agents, forge capabilities, or spoof canonical identity/schema relationships.
- Fail closed on: blank capability, unknown capability, no match, contract mismatch,
  self-delegation attempt, ambiguous multiple matching specialists, untyped payload.
- Produce a deterministic, machine-testable local RoutingTraceRecord.
- Zero Gemini/LLM reasoning or model calls.
- Zero external writes, network calls, or cloud credentials.
- Routing is not authorization: does not create AutonomyDecision,
  human authority, or write permissions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Sequence, Type

from google.adk.agents.base_agent import BaseAgent
from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.contracts.agent_descriptor import AgentRevisionProvenance
from domain.contracts.conventions import UtcDateTime
from src.agents.definition import AgentDefinition
from src.agents.registry import (
    CANONICAL_SPECIALIST_AGENT_IDS,
    CANONICAL_SPECIALIST_ROLES,
    get_canonical_agent_class,
    get_canonical_agent_definition,
    list_canonical_agent_definitions,
)


class RoutingOutcome(str, Enum):
    """Status outcome of a deterministic routing request."""

    ROUTED = "ROUTED"
    REJECTED = "REJECTED"


class RoutingRejectionReason(str, Enum):
    """Machine-checkable reason codes for routing rejections."""

    BLANK_CAPABILITY = "BLANK_CAPABILITY"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    NO_MATCHING_SPECIALIST = "NO_MATCHING_SPECIALIST"
    INPUT_CONTRACT_MISMATCH = "INPUT_CONTRACT_MISMATCH"
    SELF_DELEGATION_PROHIBITED = "SELF_DELEGATION_PROHIBITED"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    INVALID_REQUEST = "INVALID_REQUEST"


class RoutingRequest(BaseModel):
    """Deterministic routing request carrying capability requirements and payload.

    Invariants:
    - change_id must not be blank.
    - required_capabilities must be non-empty and contain non-blank capability strings.
    - payload must be a typed Pydantic BaseModel instance.
    - Frozen and rejects extra fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    change_id: str
    required_capabilities: list[str] = Field(min_length=1)
    payload: BaseModel
    request_id: str | None = None

    @field_validator("change_id")
    @classmethod
    def _validate_change_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("change_id must not be blank")
        return v.strip()

    @field_validator("required_capabilities")
    @classmethod
    def _validate_required_capabilities(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("required_capabilities must not be empty")
        for cap in v:
            if not isinstance(cap, str) or not cap.strip():
                raise ValueError("Capability requirement must not be blank")
        return list(v)

    @field_validator("request_id")
    @classmethod
    def _validate_request_id(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("request_id must not be blank when provided")
        return v.strip() if v is not None else None


class RoutingTraceRecord(BaseModel):
    """Deterministic machine-testable trace record of a routing decision.

    Captures complete evaluation facts without credentials or mutable state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_id: str
    change_id: str
    outcome: RoutingOutcome
    required_capabilities: list[str]
    payload_type: str
    selected_agent_id: str | None = None
    selected_role: str | None = None
    selected_agent_revision: str | None = None
    capability_match_passed: bool
    contract_match_passed: bool
    rejection_reason: RoutingRejectionReason | None = None
    evaluated_candidates: list[str] = Field(default_factory=list)
    timestamp: UtcDateTime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("trace_id", "change_id")
    @classmethod
    def _validate_non_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()

    def get_selected_revision_provenance(self) -> AgentRevisionProvenance | None:
        """Return structured AgentRevisionProvenance for the selected specialist, if routed."""
        if self.selected_agent_id and self.selected_agent_revision:
            return AgentRevisionProvenance(
                agent_id=self.selected_agent_id,
                agent_revision=self.selected_agent_revision,
                role=self.selected_role,
            )
        return None


class RoutingResult(BaseModel):
    """Result of a deterministic routing evaluation.

    Encapsulates outcome, selected agent metadata/class, payload, and the immutable trace.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    outcome: RoutingOutcome
    trace: RoutingTraceRecord
    selected_agent_class: Type[BaseAgent] | None = None
    selected_definition: AgentDefinition | None = None
    payload: BaseModel | None = None

    @property
    def is_routed(self) -> bool:
        """Return True if routing succeeded and an agent was selected."""
        return self.outcome == RoutingOutcome.ROUTED

    @property
    def is_successful(self) -> bool:
        """Alias for is_routed."""
        return self.is_routed

    def get_selected_revision_provenance(self) -> AgentRevisionProvenance | None:
        """Return structured AgentRevisionProvenance for the selected specialist, if routed."""
        return self.trace.get_selected_revision_provenance()


def _is_canonical_specialist_definition(definition: AgentDefinition) -> bool:
    """Verify that an AgentDefinition matches genuine canonical P-07.02 metadata."""
    if not isinstance(definition, AgentDefinition):
        return False
    if definition.agent_id not in CANONICAL_SPECIALIST_AGENT_IDS:
        return False
    if definition.role not in CANONICAL_SPECIALIST_ROLES:
        return False

    try:
        canonical_def = get_canonical_agent_definition(definition.agent_id)
    except (KeyError, ValueError):
        return False

    return (
        definition.role == canonical_def.role
        and definition.agent_revision == canonical_def.agent_revision
        and list(definition.declared_capabilities) == list(canonical_def.declared_capabilities)
        and definition.input_schema is canonical_def.input_schema
        and definition.output_schema is canonical_def.output_schema
        and list(definition.forbidden_actions) == list(canonical_def.forbidden_actions)
        and definition.instruction_contract == canonical_def.instruction_contract
        and list(definition.permitted_tool_ids) == list(canonical_def.permitted_tool_ids)
        and list(definition.permitted_data_classifications)
        == list(canonical_def.permitted_data_classifications)
    )


class DeterministicRouter:
    """Deterministic Agent Router for ChangeMesh.

    Selects a specialized agent from the fleet only when:
    1. The candidate agent is strictly one of the five canonical specialists
       (Change Orchestrator cannot be delegated to; invented agents are rejected).
    2. The candidate definition matches genuine canonical P-07.02 metadata
       (caller-supplied definitions cannot invent capabilities, roles, or schemas).
    3. The candidate agent's canonical declared_capabilities exactly contain ALL
       required capabilities.
    4. Exactly one canonical specialist matches the capability requirements
       (fails closed on ambiguous matches).
    5. The supplied payload conforms to the selected specialist's canonical input_schema.
    6. The selected_agent_class is a non-None genuine canonical BaseAgent subclass.

    Zero Gemini/LLM reasoning, zero network calls, zero external writes.
    """

    def __init__(
        self,
        agent_definitions: Sequence[AgentDefinition] | None = None,
        *,
        trace_id_generator: Callable[[], str] | None = None,
    ) -> None:
        """Initialize the router with agent definitions (defaults to canonical fleet)."""
        if agent_definitions is not None:
            self._definitions = list(agent_definitions)
        else:
            self._definitions = list_canonical_agent_definitions()
        self._trace_id_generator = trace_id_generator

    def _generate_trace_id(self) -> str:
        if self._trace_id_generator is not None:
            return self._trace_id_generator()
        return f"trace-{uuid.uuid4().hex}"

    def route(self, request: RoutingRequest) -> RoutingResult:
        """Evaluate routing request deterministically and return RoutingResult."""
        if not isinstance(request, RoutingRequest):
            raise TypeError(f"Expected RoutingRequest instance, got {type(request).__name__}")

        trace_id = self._generate_trace_id()
        payload_type_name = type(request.payload).__name__

        # Validate capabilities are not blank
        for cap in request.required_capabilities:
            if not cap or not cap.strip():
                trace = RoutingTraceRecord(
                    trace_id=trace_id,
                    change_id=request.change_id,
                    outcome=RoutingOutcome.REJECTED,
                    required_capabilities=list(request.required_capabilities),
                    payload_type=payload_type_name,
                    capability_match_passed=False,
                    contract_match_passed=False,
                    rejection_reason=RoutingRejectionReason.BLANK_CAPABILITY,
                    evaluated_candidates=[],
                )
                return RoutingResult(
                    outcome=RoutingOutcome.REJECTED,
                    trace=trace,
                )

        # Derivation of canonical truth: strictly from canonical registry
        orchestrator_def = get_canonical_agent_definition("agent-change-orchestrator")
        orchestrator_caps = set(orchestrator_def.declared_capabilities)

        canonical_specialist_caps: set[str] = set()
        for s_id in CANONICAL_SPECIALIST_AGENT_IDS:
            s_def = get_canonical_agent_definition(s_id)
            canonical_specialist_caps.update(s_def.declared_capabilities)

        all_canonical_fleet_caps = orchestrator_caps | canonical_specialist_caps

        # Check if requested capabilities exist anywhere in canonical fleet truth
        for req_cap in request.required_capabilities:
            if req_cap not in all_canonical_fleet_caps:
                trace = RoutingTraceRecord(
                    trace_id=trace_id,
                    change_id=request.change_id,
                    outcome=RoutingOutcome.REJECTED,
                    required_capabilities=list(request.required_capabilities),
                    payload_type=payload_type_name,
                    capability_match_passed=False,
                    contract_match_passed=False,
                    rejection_reason=RoutingRejectionReason.UNKNOWN_CAPABILITY,
                    evaluated_candidates=[],
                )
                return RoutingResult(
                    outcome=RoutingOutcome.REJECTED,
                    trace=trace,
                )

        # Check for orchestrator-only capability requested (self-delegation prohibition)
        if any(req_cap in orchestrator_caps for req_cap in request.required_capabilities):
            if any(
                req_cap not in canonical_specialist_caps
                for req_cap in request.required_capabilities
            ):
                trace = RoutingTraceRecord(
                    trace_id=trace_id,
                    change_id=request.change_id,
                    outcome=RoutingOutcome.REJECTED,
                    required_capabilities=list(request.required_capabilities),
                    payload_type=payload_type_name,
                    capability_match_passed=False,
                    contract_match_passed=False,
                    rejection_reason=RoutingRejectionReason.SELF_DELEGATION_PROHIBITED,
                    evaluated_candidates=[],
                )
                return RoutingResult(
                    outcome=RoutingOutcome.REJECTED,
                    trace=trace,
                )

        # Filter candidate definitions from self._definitions:
        # Candidate must be a verified canonical specialist (reject invented & spoofed definitions).
        evaluated_candidates: list[str] = []
        matching_specialists: list[AgentDefinition] = []

        for d in self._definitions:
            # Self-delegation target check: ignore orchestrator as target
            if d.role == "change_orchestrator" or d.agent_id == "agent-change-orchestrator":
                continue

            evaluated_candidates.append(d.agent_id)

            # Strict provenance verification against canonical P-07.02 definition
            if not _is_canonical_specialist_definition(d):
                # Spoofed or invented definition: cannot be routed
                continue

            # Fetch canonical definition
            canonical_def = get_canonical_agent_definition(d.agent_id)

            # Exact capability matching against canonical declared capabilities
            if all(
                req_cap in canonical_def.declared_capabilities
                for req_cap in request.required_capabilities
            ):
                matching_specialists.append(canonical_def)

        # Handle 0 matches
        if len(matching_specialists) == 0:
            trace = RoutingTraceRecord(
                trace_id=trace_id,
                change_id=request.change_id,
                outcome=RoutingOutcome.REJECTED,
                required_capabilities=list(request.required_capabilities),
                payload_type=payload_type_name,
                capability_match_passed=False,
                contract_match_passed=False,
                rejection_reason=RoutingRejectionReason.NO_MATCHING_SPECIALIST,
                evaluated_candidates=evaluated_candidates,
            )
            return RoutingResult(
                outcome=RoutingOutcome.REJECTED,
                trace=trace,
            )

        # Handle ambiguous matches (> 1 matches)
        if len(matching_specialists) > 1:
            trace = RoutingTraceRecord(
                trace_id=trace_id,
                change_id=request.change_id,
                outcome=RoutingOutcome.REJECTED,
                required_capabilities=list(request.required_capabilities),
                payload_type=payload_type_name,
                capability_match_passed=False,
                contract_match_passed=False,
                rejection_reason=RoutingRejectionReason.AMBIGUOUS_MATCH,
                evaluated_candidates=[s.agent_id for s in matching_specialists],
            )
            return RoutingResult(
                outcome=RoutingOutcome.REJECTED,
                trace=trace,
            )

        # Exactly 1 specialist matched capability requirements
        selected_specialist = matching_specialists[0]

        # Verify selected agent is strictly one of the five canonical specialists
        if selected_specialist.agent_id not in CANONICAL_SPECIALIST_AGENT_IDS:
            trace = RoutingTraceRecord(
                trace_id=trace_id,
                change_id=request.change_id,
                outcome=RoutingOutcome.REJECTED,
                required_capabilities=list(request.required_capabilities),
                payload_type=payload_type_name,
                capability_match_passed=False,
                contract_match_passed=False,
                rejection_reason=RoutingRejectionReason.NO_MATCHING_SPECIALIST,
                evaluated_candidates=evaluated_candidates,
            )
            return RoutingResult(
                outcome=RoutingOutcome.REJECTED,
                trace=trace,
            )

        # Resolve canonical agent class (must be non-None BaseAgent subclass)
        try:
            agent_class = get_canonical_agent_class(selected_specialist.agent_id)
        except (KeyError, ValueError):
            agent_class = None

        if agent_class is None or not issubclass(agent_class, BaseAgent):
            trace = RoutingTraceRecord(
                trace_id=trace_id,
                change_id=request.change_id,
                outcome=RoutingOutcome.REJECTED,
                required_capabilities=list(request.required_capabilities),
                payload_type=payload_type_name,
                capability_match_passed=False,
                contract_match_passed=False,
                rejection_reason=RoutingRejectionReason.NO_MATCHING_SPECIALIST,
                evaluated_candidates=evaluated_candidates,
            )
            return RoutingResult(
                outcome=RoutingOutcome.REJECTED,
                trace=trace,
            )

        # Validate input contract match against CANONICAL input_schema
        if not isinstance(request.payload, selected_specialist.input_schema):
            trace = RoutingTraceRecord(
                trace_id=trace_id,
                change_id=request.change_id,
                outcome=RoutingOutcome.REJECTED,
                required_capabilities=list(request.required_capabilities),
                payload_type=payload_type_name,
                selected_agent_id=selected_specialist.agent_id,
                selected_role=selected_specialist.role,
                selected_agent_revision=selected_specialist.agent_revision,
                capability_match_passed=True,
                contract_match_passed=False,
                rejection_reason=RoutingRejectionReason.INPUT_CONTRACT_MISMATCH,
                evaluated_candidates=[selected_specialist.agent_id],
            )
            return RoutingResult(
                outcome=RoutingOutcome.REJECTED,
                trace=trace,
                selected_definition=selected_specialist,
            )

        # Both capability and contract matched with full canonical provenance!
        trace = RoutingTraceRecord(
            trace_id=trace_id,
            change_id=request.change_id,
            outcome=RoutingOutcome.ROUTED,
            required_capabilities=list(request.required_capabilities),
            payload_type=payload_type_name,
            selected_agent_id=selected_specialist.agent_id,
            selected_role=selected_specialist.role,
            selected_agent_revision=selected_specialist.agent_revision,
            capability_match_passed=True,
            contract_match_passed=True,
            rejection_reason=None,
            evaluated_candidates=[selected_specialist.agent_id],
        )

        return RoutingResult(
            outcome=RoutingOutcome.ROUTED,
            trace=trace,
            selected_agent_class=agent_class,
            selected_definition=selected_specialist,
            payload=request.payload,
        )
