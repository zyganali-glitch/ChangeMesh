"""ChangeMesh Multi-Agent Coordination Engine — Sequential Fallback & Controlled Parallel Branches.

P-07.04: Implement sequential fallback and controlled parallel branches.
This module implements the deterministic, in-process coordination layer for executing
multi-agent branch plans across the canonical specialized ADK fleet.

Responsibilities & Invariants:
- Zero shared mutable state: Parallel branch executions operate strictly on isolated
  immutable inputs (`BranchSpec`) and return immutable typed outputs (`BranchResult`).
  No shared dictionaries, accumulators, or mutable objects are passed to concurrent branches.
- Single-writer aggregation: Aggregate `CoordinationResult` is constructed strictly
  by the orchestrator/coordinator after all branch executions have completed.
- Controlled parallel branches: Fixed, non-recursive, bounded branch plans (`BranchPlan`).
  Tasks are gathered concurrently via `asyncio.gather` with honest deterministic error handling.
- Deterministic final ordering: Regardless of wall-clock completion order, branch results
  in `CoordinationResult` are strictly ordered according to the original `BranchPlan` definition.
- Sequential fallback: When parallel execution is unsafe (e.g. conflicting specialist
  targets or release steward concurrency) or explicitly requested, the coordinator
  executes the exact same branch plan sequentially.
- Parallel vs. Sequential equivalence: Executing the same deterministic branch plan in
  parallel-safe mode vs forced sequential fallback yields 100% equivalent canonical
  business-state projections (`CoordinationResult.get_canonical_state_projection()`).
- No unsafe retry: If a parallel branch fails midway, completed branches are not replayed;
  failure is reported honestly in the final deterministic aggregation (`BranchStatus.FAILED`).
- Non-bypassable routing: Every branch intent is qualified through the deterministic
  `DeterministicRouter` gate (P-07.03), failing closed on invalid capabilities, schemas,
  or non-canonical provenance.
- Zero external writes, zero cloud credentials, zero Gemini model calls.
- Four-lane authority preservation: Concurrency mechanics do not create authorization
  or alter `AutonomyDecision` / `AutonomyClass`.
"""

from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Sequence

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.contracts.autonomy import AutonomyClass, AutonomyDecision
from domain.contracts.conventions import UtcDateTime
from src.agents.definition import AgentDefinition
from src.agents.router import (
    DeterministicRouter,
    RoutingOutcome,
    RoutingRequest,
    RoutingResult,
)
from src.agents.schemas import (
    EvidenceAuditorInput,
    EvidenceAuditorOutput,
    ImpactScoutInput,
    ImpactScoutOutput,
    MigrationEngineerInput,
    MigrationEngineerOutput,
    PolicyGuardianInput,
    PolicyGuardianOutput,
    ReleaseStewardInput,
    ReleaseStewardOutput,
)


class ExecutionStrategy(str, Enum):
    """Execution strategy for a multi-agent branch plan."""

    PARALLEL = "PARALLEL"
    SEQUENTIAL = "SEQUENTIAL"


class BranchStatus(str, Enum):
    """Lifecycle execution status of an individual branch."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class BranchSpec(BaseModel):
    """Specification of a single branch intent in an execution plan.

    Invariants:
    - `branch_id` must be non-blank and unique within a plan.
    - `routing_request` carries immutable change ID, required capabilities, and typed payload.
    - Frozen to prevent runtime mutation during branch execution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    branch_id: str
    routing_request: RoutingRequest
    description: str | None = None

    @field_validator("branch_id")
    @classmethod
    def _validate_branch_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("branch_id must not be blank")
        return v.strip()


class BranchPlan(BaseModel):
    """Bounded, deterministic plan containing one or more branch specifications.

    Invariants:
    - `plan_id` and `change_id` must not be blank.
    - `branches` must contain at least one branch.
    - All `branch_id` values within `branches` must be unique.
    - All `branches` must reference the exact same `change_id` as the plan.
    - Bounded and non-recursive (no nested plans).
    - `branches` is stored as an immutable tuple of deeply isolated `BranchSpec`s.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    plan_id: str
    change_id: str
    branches: Sequence[BranchSpec] = Field(min_length=1)
    strategy: ExecutionStrategy = ExecutionStrategy.PARALLEL
    description: str | None = None

    @field_validator("plan_id", "change_id")
    @classmethod
    def _validate_non_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()

    @field_validator("branches", mode="before")
    @classmethod
    def _validate_branches(cls, v: Any, info) -> tuple[BranchSpec, ...]:
        if not v:
            raise ValueError("BranchPlan must contain at least one branch")

        branch_list: list[BranchSpec] = [
            b if isinstance(b, BranchSpec) else BranchSpec.model_validate(b) for b in v
        ]

        seen_branch_ids: set[str] = set()
        for branch in branch_list:
            if branch.branch_id in seen_branch_ids:
                raise ValueError(f"Duplicate branch_id in plan: {branch.branch_id!r}")
            seen_branch_ids.add(branch.branch_id)

        # Validate change_id alignment if change_id is present in values
        plan_change_id = info.data.get("change_id")
        if plan_change_id:
            for branch in branch_list:
                if branch.routing_request.change_id != plan_change_id:
                    raise ValueError(
                        f"Branch {branch.branch_id!r} change_id "
                        f"({branch.routing_request.change_id!r}) "
                        f"does not match plan change_id ({plan_change_id!r})"
                    )
        return tuple(copy.deepcopy(b) for b in branch_list)


class BranchExecutionTrace(BaseModel):
    """Immutable, credential-free execution trace for a single branch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_id: str
    branch_id: str
    change_id: str
    strategy_used: ExecutionStrategy
    routing_outcome: RoutingOutcome
    selected_agent_id: str | None = None
    selected_role: str | None = None
    status: BranchStatus
    error_message: str | None = None
    started_at: UtcDateTime
    completed_at: UtcDateTime

    @field_validator("trace_id", "branch_id", "change_id")
    @classmethod
    def _validate_non_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class BranchResult(BaseModel):
    """Immutable typed result of an executed branch.

    Carries status, output, routing result, and trace facts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    branch_id: str
    change_id: str
    status: BranchStatus
    strategy_used: ExecutionStrategy
    routing_result: RoutingResult
    output: BaseModel | None = None
    error_message: str | None = None
    trace: BranchExecutionTrace

    @property
    def is_success(self) -> bool:
        """Return True if the branch executed successfully."""
        return self.status == BranchStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        """Return True if the branch failed during execution."""
        return self.status == BranchStatus.FAILED

    @property
    def is_rejected(self) -> bool:
        """Return True if the branch was rejected at routing."""
        return self.status == BranchStatus.REJECTED


class CoordinationTrace(BaseModel):
    """Immutable trace of a multi-agent branch coordination execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    coordination_id: str
    plan_id: str
    change_id: str
    requested_strategy: ExecutionStrategy
    effective_strategy: ExecutionStrategy
    fallback_triggered: bool = False
    fallback_reason: str | None = None
    total_branches: int
    success_count: int
    failure_count: int
    rejection_count: int
    started_at: UtcDateTime
    completed_at: UtcDateTime

    @field_validator("coordination_id", "plan_id", "change_id")
    @classmethod
    def _validate_non_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()


class CoordinationResult(BaseModel):
    """Deterministic single-writer aggregation of branch plan execution.

    Created strictly by the orchestrator/coordinator after all branches finish.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    coordination_id: str
    plan_id: str
    change_id: str
    requested_strategy: ExecutionStrategy
    effective_strategy: ExecutionStrategy
    is_successful: bool
    branch_results: Sequence[BranchResult] = Field(default_factory=tuple)
    trace: CoordinationTrace

    @field_validator("branch_results", mode="before")
    @classmethod
    def _validate_branch_results(cls, v: Any) -> tuple[BranchResult, ...]:
        if isinstance(v, (list, tuple)):
            return tuple(v)
        return (v,)

    @property
    def branch_count(self) -> int:
        """Total number of branches in the plan."""
        return len(self.branch_results)

    def get_branch_result(self, branch_id: str) -> BranchResult | None:
        """Retrieve result for a specific branch by branch_id."""
        for res in self.branch_results:
            if res.branch_id == branch_id:
                return res
        return None

    def get_canonical_state_projection(self) -> dict[str, Any]:
        """Generate a deterministic machine-testable canonical state projection.

        This projection contains all mission-relevant business state:
        - change ID & plan ID
        - overall success status
        - total branch count
        - ordered list of branch business outcomes (status, agent ID, role, output data, errors)

        Observability metadata (e.g. timestamps, trace IDs, strategy tags) are excluded
        so that parallel-safe execution and forced sequential fallback can be proven
        100% equivalent.
        """
        return {
            "change_id": self.change_id,
            "plan_id": self.plan_id,
            "is_successful": self.is_successful,
            "total_branches": len(self.branch_results),
            "branch_outcomes": [
                {
                    "branch_id": br.branch_id,
                    "status": br.status.value,
                    "agent_id": br.routing_result.trace.selected_agent_id,
                    "role": br.routing_result.trace.selected_role,
                    "output_type": type(br.output).__name__ if br.output else None,
                    "output_data": br.output.model_dump(mode="json") if br.output else None,
                    "error_message": br.error_message,
                }
                for br in self.branch_results  # Ordered deterministically
            ],
        }

    def assert_equivalent_state(self, other: CoordinationResult) -> None:
        """Assert that this result is equivalent in canonical business state to another result.

        Raises AssertionError with details if any business-relevant field differs.
        """
        proj_self = self.get_canonical_state_projection()
        proj_other = other.get_canonical_state_projection()
        if proj_self != proj_other:
            raise AssertionError(
                f"Canonical state projections differ between coordination results:\n"
                f"Self ({self.effective_strategy.value}): {proj_self}\n"
                f"Other ({other.effective_strategy.value}): {proj_other}"
            )


def _build_default_output_for_specialist(
    agent_id: str,
    payload: BaseModel,
) -> BaseModel:
    """Build a deterministic, schema-valid synthetic output for a canonical specialist.

    Used when no custom branch runner is supplied, ensuring local ADK execution
    returns typed data adhering to the agent's canonical output_schema.
    """
    change_id = getattr(payload, "change_id", "chg-default")

    if agent_id == "agent-impact-scout" and isinstance(payload, ImpactScoutInput):
        return ImpactScoutOutput(
            schema_version="1.0.0",
            change_id=change_id,
            affected_files=["schema/migrations/001_synthetic.sql"],
            affected_systems=list(payload.target_systems),
            conflict_detected=False,
            risk_level="LOW",
            blast_radius_score=0.1,
            deterministic_evidence_refs=[f"ev-diff-{change_id}"],
        )

    if agent_id == "agent-policy-guardian" and isinstance(payload, PolicyGuardianInput):
        action = payload.requested_actions[0] if payload.requested_actions else "action.default"
        decision = AutonomyDecision(
            schema_version="1.0.0",
            decision_id=f"dec-{change_id}",
            change_request_id=change_id,
            action_class=action,
            autonomy_class=AutonomyClass.AUTO_EXECUTE,
            policy_source="policy.canonical.ruleset",
            policy_revision="1.0.0",
            decided_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
            rationale="All policy rules satisfied deterministically.",
        )
        return PolicyGuardianOutput(
            schema_version="1.0.0",
            change_id=change_id,
            policy_verdict="COMPLIANT",
            autonomy_decision=decision,
            violated_rules=[],
            required_evidence_types=["EVIDENCE_TEST_SUITE_EXECUTION"],
        )

    if agent_id == "agent-migration-engineer" and isinstance(payload, MigrationEngineerInput):
        return MigrationEngineerOutput(
            schema_version="1.0.0",
            change_id=change_id,
            artifact_id=f"art-mig-{change_id}",
            artifact_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            migration_script_content=payload.migration_spec,
            rehearsal_instructions="Verify schema migration idempotency.",
            is_reversible=True,
        )

    if agent_id == "agent-evidence-auditor" and isinstance(payload, EvidenceAuditorInput):
        count = len(payload.success_criteria_ids)
        return EvidenceAuditorOutput(
            schema_version="1.0.0",
            change_id=change_id,
            sufficiency_verdict="SUFFICIENT",
            evaluated_criteria_count=count,
            satisfied_criteria_count=count,
            unmet_criteria_ids=[],
            semantic_review_summary="All required criteria verified deterministically.",
        )

    if agent_id == "agent-release-steward" and isinstance(payload, ReleaseStewardInput):
        return ReleaseStewardOutput(
            schema_version="1.0.0",
            change_id=change_id,
            release_bundle_id=f"bundle-{change_id}",
            draft_pr_spec=f"Draft PR spec for {payload.target_repository}",
            rollback_spec="Revert migration and restore schema snapshot.",
            handoff_ready=True,
            requires_live_confirmation=False,
        )

    raise ValueError(
        f"No default output builder for agent {agent_id!r} with payload {type(payload).__name__}"
    )


class BranchCoordinator:
    """ChangeMesh Multi-Agent Branch Coordinator.

    Coordinates parallel and sequential execution of specialized agent branches
    with zero shared mutable state, non-bypassable routing, single-writer aggregation,
    and fail-closed fallback semantics.
    """

    def __init__(
        self,
        router: DeterministicRouter | None = None,
        *,
        id_generator: Callable[[], str] | None = None,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize BranchCoordinator with optional router and ID generator."""
        self._router = router or DeterministicRouter()
        self._id_generator = id_generator
        self._time_provider = time_provider or (lambda: datetime.now(timezone.utc))

    def _generate_id(self, prefix: str) -> str:
        if self._id_generator is not None:
            return self._id_generator()
        return f"{prefix}-{uuid.uuid4().hex}"

    def _now(self) -> UtcDateTime:
        return self._time_provider()

    def is_parallel_safe(self, plan: BranchPlan) -> tuple[bool, str | None]:
        """Deterministically determine if a BranchPlan is safe for parallel execution.

        Conservative Fail-Closed Rules (P-07.04 local contract):
        1. Plan must contain at least 1 branch.
        2. Evaluate each branch's routing request against the canonical fleet.
        3. If multiple branches resolve to the SAME specialized agent (e.g. 2 x MigrationEngineer),
           running them concurrently risks conflict -> Fallback to SEQUENTIAL.
        4. If `agent-release-steward` is present in a multi-branch plan alongside any other
           specialist, running concurrently is unsafe -> Fallback to SEQUENTIAL.
        5. Otherwise, the plan is safe for parallel execution.

        Returns:
            Tuple of (is_safe: bool, reason: str | None).
        """
        if not isinstance(plan, BranchPlan):
            raise TypeError(f"Expected BranchPlan instance, got {type(plan).__name__}")

        if len(plan.branches) <= 1:
            return True, None

        # Pre-evaluate routing to inspect target specialists
        resolved_agent_ids: list[str] = []
        for branch in plan.branches:
            routing_res = self._router.route(branch.routing_request)
            if routing_res.is_routed and routing_res.trace.selected_agent_id:
                resolved_agent_ids.append(routing_res.trace.selected_agent_id)

        # Rule 3: Check for duplicate specialist agent targets
        seen_agents: set[str] = set()
        for agent_id in resolved_agent_ids:
            if agent_id in seen_agents:
                return (
                    False,
                    f"Conflict risk: multiple branches target the same agent ({agent_id})",
                )
            seen_agents.add(agent_id)

        # Rule 4: Release steward cannot execute in parallel with other active specialists
        if "agent-release-steward" in resolved_agent_ids and len(resolved_agent_ids) > 1:
            return (
                False,
                "Safety rule: release steward cannot run in parallel with other branches",
            )

        return True, None

    async def execute_branch(
        self,
        spec: BranchSpec,
        strategy: ExecutionStrategy,
        branch_runner: Callable[[BranchSpec, RoutingResult], Awaitable[BaseModel]] | None = None,
    ) -> BranchResult:
        """Execute an individual branch in strict isolation with zero shared mutable state.

        Args:
            spec: Immutable BranchSpec describing the branch intent.
            strategy: The active ExecutionStrategy (PARALLEL or SEQUENTIAL).
            branch_runner: Optional custom async callable for branch execution.

        Returns:
            Immutable BranchResult capturing status, output, and execution trace.
        """
        # Deep-isolate spec to guarantee runtime isolation from concurrent branches and caller
        isolated_spec = copy.deepcopy(spec)
        started_at = self._now()
        trace_id = self._generate_id("trace-br")

        # 1. Non-bypassable qualification through DeterministicRouter
        routing_res = self._router.route(isolated_spec.routing_request)

        if not routing_res.is_routed or routing_res.selected_agent_class is None:
            completed_at = self._now()
            trace = BranchExecutionTrace(
                trace_id=trace_id,
                branch_id=isolated_spec.branch_id,
                change_id=isolated_spec.routing_request.change_id,
                strategy_used=strategy,
                routing_outcome=routing_res.outcome,
                selected_agent_id=routing_res.trace.selected_agent_id,
                selected_role=routing_res.trace.selected_role,
                status=BranchStatus.REJECTED,
                error_message=f"Routing rejected: {routing_res.trace.rejection_reason}",
                started_at=started_at,
                completed_at=completed_at,
            )
            return BranchResult(
                branch_id=isolated_spec.branch_id,
                change_id=isolated_spec.routing_request.change_id,
                status=BranchStatus.REJECTED,
                strategy_used=strategy,
                routing_result=routing_res,
                output=None,
                error_message=trace.error_message,
                trace=trace,
            )

        # 2. Execute branch in isolation
        selected_cls: Any = routing_res.selected_agent_class
        selected_def: AgentDefinition = routing_res.selected_definition  # type: ignore[assignment]
        output: BaseModel | None = None
        error_msg: str | None = None
        status = BranchStatus.SUCCESS

        try:
            if branch_runner is not None:
                output = await branch_runner(isolated_spec, routing_res)
            else:
                # Default canonical execution: exercise real ADK BaseAgent in-process
                agent_instance = selected_cls()
                session_service = InMemorySessionService()
                session = await session_service.create_session(
                    session_id=f"session-{isolated_spec.branch_id}",
                    user_id="changemesh-orchestrator",
                    app_name="changemesh",
                )
                runner = Runner(
                    agent=agent_instance,
                    session_service=session_service,
                    app_name="changemesh",
                )
                # Run ADK agent turn
                async for _ in runner.run_async(
                    user_id="changemesh-orchestrator",
                    session_id=session.id,
                    new_message=Content(
                        parts=[Part(text=f"Execute branch {isolated_spec.branch_id}")]
                    ),
                ):
                    pass

                # Build typed synthetic output adhering to selected_def.output_schema
                output = _build_default_output_for_specialist(
                    selected_def.agent_id,
                    isolated_spec.routing_request.payload,
                )

        except Exception as exc:
            status = BranchStatus.FAILED
            error_msg = f"Branch execution failed with {type(exc).__name__}: {exc}"
            output = None

        completed_at = self._now()
        trace = BranchExecutionTrace(
            trace_id=trace_id,
            branch_id=isolated_spec.branch_id,
            change_id=isolated_spec.routing_request.change_id,
            strategy_used=strategy,
            routing_outcome=routing_res.outcome,
            selected_agent_id=routing_res.trace.selected_agent_id,
            selected_role=routing_res.trace.selected_role,
            status=status,
            error_message=error_msg,
            started_at=started_at,
            completed_at=completed_at,
        )

        return BranchResult(
            branch_id=isolated_spec.branch_id,
            change_id=isolated_spec.routing_request.change_id,
            status=status,
            strategy_used=strategy,
            routing_result=routing_res,
            output=output,
            error_message=error_msg,
            trace=trace,
        )

    async def execute_plan(
        self,
        plan: BranchPlan,
        *,
        force_strategy: ExecutionStrategy | None = None,
        branch_runner: Callable[[BranchSpec, RoutingResult], Awaitable[BaseModel]] | None = None,
    ) -> CoordinationResult:
        """Execute a BranchPlan with deterministic single-writer aggregation.

        Args:
            plan: The typed BranchPlan containing branch specifications.
            force_strategy: Optional strategy override (e.g. forced SEQUENTIAL fallback
                or requested PARALLEL).
            branch_runner: Optional custom execution handler for branch tasks.

        Returns:
            CoordinationResult containing deterministically ordered branch results.
        """
        if not isinstance(plan, BranchPlan):
            raise TypeError(f"Expected BranchPlan instance, got {type(plan).__name__}")

        started_at = self._now()
        coordination_id = self._generate_id("coord")

        # Snapshot branches to guarantee complete execution isolation from any caller mutation
        isolated_branches: tuple[BranchSpec, ...] = tuple(copy.deepcopy(b) for b in plan.branches)

        # Strategy resolution & non-bypassable safety check
        # Any request/desire/override for PARALLEL must pass is_parallel_safe()
        requested_strategy = force_strategy if force_strategy is not None else plan.strategy
        fallback_triggered = False
        fallback_reason: str | None = None

        if requested_strategy == ExecutionStrategy.PARALLEL:
            is_safe, reason = self.is_parallel_safe(plan)
            if not is_safe:
                effective_strategy = ExecutionStrategy.SEQUENTIAL
                fallback_triggered = True
                fallback_reason = reason or "Parallel execution unsafe; falling back to sequential."
            else:
                effective_strategy = ExecutionStrategy.PARALLEL
                fallback_triggered = False
                fallback_reason = None
        else:
            effective_strategy = ExecutionStrategy.SEQUENTIAL
            if (
                plan.strategy == ExecutionStrategy.PARALLEL
                and force_strategy == ExecutionStrategy.SEQUENTIAL
            ):
                fallback_triggered = True
                fallback_reason = "Forced sequential execution strategy requested by caller."
            else:
                fallback_triggered = False
                fallback_reason = None

        # Execution phase
        branch_results_by_id: dict[str, BranchResult] = {}

        if effective_strategy == ExecutionStrategy.PARALLEL:
            # Controlled parallel execution with true overlap
            coros = [
                self.execute_branch(b, ExecutionStrategy.PARALLEL, branch_runner)
                for b in isolated_branches
            ]
            raw_results = await asyncio.gather(*coros, return_exceptions=False)
            for res in raw_results:
                branch_results_by_id[res.branch_id] = res
        else:
            # Deterministic sequential execution
            for b in isolated_branches:
                res = await self.execute_branch(b, ExecutionStrategy.SEQUENTIAL, branch_runner)
                branch_results_by_id[res.branch_id] = res

        # Single-writer aggregation: deterministically ordered by plan branch order
        ordered_results: list[BranchResult] = []
        success_count = 0
        failure_count = 0
        rejection_count = 0

        for b in isolated_branches:
            res = branch_results_by_id[b.branch_id]
            ordered_results.append(res)
            if res.status == BranchStatus.SUCCESS:
                success_count += 1
            elif res.status == BranchStatus.FAILED:
                failure_count += 1
            elif res.status == BranchStatus.REJECTED:
                rejection_count += 1

        is_successful = success_count == len(isolated_branches)
        completed_at = self._now()

        trace = CoordinationTrace(
            coordination_id=coordination_id,
            plan_id=plan.plan_id,
            change_id=plan.change_id,
            requested_strategy=requested_strategy,
            effective_strategy=effective_strategy,
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
            total_branches=len(isolated_branches),
            success_count=success_count,
            failure_count=failure_count,
            rejection_count=rejection_count,
            started_at=started_at,
            completed_at=completed_at,
        )

        return CoordinationResult(
            coordination_id=coordination_id,
            plan_id=plan.plan_id,
            change_id=plan.change_id,
            requested_strategy=requested_strategy,
            effective_strategy=effective_strategy,
            is_successful=is_successful,
            branch_results=tuple(ordered_results),
            trace=trace,
        )
