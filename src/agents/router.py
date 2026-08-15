"""ChangeMesh Deterministic Routing and Delegation Engine.

P-07.03: Implement deterministic routing/delegation for initial workflow.
This module implements the deterministic capability and contract matching engine
for the ChangeMesh agent fleet.

Responsibilities:
- Route delegation requests strictly based on deterministic capability and contract match.
- Orchestrator coordinates routing; cannot delegate to itself.
- Valid delegation targets are strictly the five specialized agents:
  Impact Scout, Policy Guardian, Migration Engineer, Evidence Auditor, Release Steward.
- Exact string matching for declared capabilities (no fuzzy, no substring, no synonyms).
- Exact input contract validation against target agent's canonical input_schema.
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

from domain.contracts.conventions import UtcDateTime
from src.agents.definition import AgentDefinition
from src.agents.registry import (
    get_canonical_agent_class,
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


class DeterministicRouter:
    """Deterministic Agent Router for ChangeMesh.

    Selects a specialized agent from the fleet only when:
    1. The candidate agent is a specialist (Change Orchestrator cannot be delegated to).
    2. The candidate agent's declared_capabilities exactly contain ALL required capabilities.
    3. Exactly one specialist matches the capability requirements (fails closed on
       ambiguous matches).
    4. The supplied payload conforms to the selected agent's canonical input_schema.

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

        # Check for orchestrator-only capability requested (self-delegation prohibition)
        orchestrator_defs = [
            d
            for d in self._definitions
            if d.role == "change_orchestrator" or d.agent_id == "agent-change-orchestrator"
        ]
        orchestrator_caps: set[str] = set()
        for orch_d in orchestrator_defs:
            orchestrator_caps.update(orch_d.declared_capabilities)

        # Find candidate specialists (strictly excluding Change Orchestrator)
        specialist_defs = [
            d
            for d in self._definitions
            if d.role != "change_orchestrator" and d.agent_id != "agent-change-orchestrator"
        ]

        evaluated_candidates = [d.agent_id for d in specialist_defs]

        # Check if requested capabilities exist anywhere in the fleet
        all_fleet_caps: set[str] = set()
        for d in self._definitions:
            all_fleet_caps.update(d.declared_capabilities)

        for req_cap in request.required_capabilities:
            if req_cap not in all_fleet_caps:
                trace = RoutingTraceRecord(
                    trace_id=trace_id,
                    change_id=request.change_id,
                    outcome=RoutingOutcome.REJECTED,
                    required_capabilities=list(request.required_capabilities),
                    payload_type=payload_type_name,
                    capability_match_passed=False,
                    contract_match_passed=False,
                    rejection_reason=RoutingRejectionReason.UNKNOWN_CAPABILITY,
                    evaluated_candidates=evaluated_candidates,
                )
                return RoutingResult(
                    outcome=RoutingOutcome.REJECTED,
                    trace=trace,
                )

        # Check if requested capabilities only belong to orchestrator (self-delegation attempt)
        if any(req_cap in orchestrator_caps for req_cap in request.required_capabilities):
            specialist_caps: set[str] = set()
            for d in specialist_defs:
                specialist_caps.update(d.declared_capabilities)
            if any(req_cap not in specialist_caps for req_cap in request.required_capabilities):
                trace = RoutingTraceRecord(
                    trace_id=trace_id,
                    change_id=request.change_id,
                    outcome=RoutingOutcome.REJECTED,
                    required_capabilities=list(request.required_capabilities),
                    payload_type=payload_type_name,
                    capability_match_passed=False,
                    contract_match_passed=False,
                    rejection_reason=RoutingRejectionReason.SELF_DELEGATION_PROHIBITED,
                    evaluated_candidates=evaluated_candidates,
                )
                return RoutingResult(
                    outcome=RoutingOutcome.REJECTED,
                    trace=trace,
                )

        # Filter specialists where ALL required capabilities match exactly
        matching_specialists: list[AgentDefinition] = []
        for specialist in specialist_defs:
            if all(
                req_cap in specialist.declared_capabilities
                for req_cap in request.required_capabilities
            ):
                matching_specialists.append(specialist)

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

        # Validate input contract match
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

        # Both capability and contract matched!
        try:
            agent_class = get_canonical_agent_class(selected_specialist.agent_id)
        except KeyError:
            agent_class = None

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
