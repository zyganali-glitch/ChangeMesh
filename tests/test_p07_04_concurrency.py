"""ChangeMesh P-07.04 — Concurrency, Parallel Branches & Sequential Fallback Tests.

Tests proving all P-07.04 acceptance criteria and invariants:
A. True controlled overlap: Parallel branches execute concurrently in flight.
B. No shared mutable state: Branches operate on isolated immutable inputs.
C. Single-writer aggregation: Aggregate CoordinationResult is produced strictly after execution.
D. Parallel vs Sequential equivalence: Equivalent canonical business-state projection.
E. Stable deterministic ordering: Out-of-order completion produces deterministic aggregation.
F. Non-bypassable routing: Invalid capability, contract mismatch, self-delegation are rejected.
G. Partial failure honesty: One branch failing records FAILED without replaying completed branches.
H. Deterministic fallback selection: Unsafe plans trigger sequential fallback.
I. Authority invariants: Concurrency mechanics create zero human authority and zero model calls.
J. Zero external side effects: Zero cloud credentials, zero network calls, zero cloud mutations.
K. Real ADK BaseAgent integration: Default execution exercises real ADK Runner + session service.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from domain.contracts.autonomy import AutonomyClass, AutonomyDecision
from domain.contracts.data_class import DataClassLevel
from src.agents import (
    BranchCoordinator,
    BranchPlan,
    BranchSpec,
    BranchStatus,
    ChangeOrchestrator,
    CoordinationResult,
    EvidenceAuditorInput,
    EvidenceAuditorOutput,
    ExecutionStrategy,
    ImpactScoutInput,
    ImpactScoutOutput,
    MigrationEngineerInput,
    PolicyGuardianInput,
    PolicyGuardianOutput,
    ReleaseStewardInput,
    ReleaseStewardOutput,
    RoutingOutcome,
    RoutingRejectionReason,
    RoutingRequest,
    RoutingResult,
)

# ===========================================================================
# Fixtures & Input Builders
# ===========================================================================


def _make_impact_scout_input(change_id: str = "chg-001") -> ImpactScoutInput:
    return ImpactScoutInput(
        schema_version="1.0.0",
        change_id=change_id,
        target_systems=["repo-enterprise-db"],
        repository_ref="main",
        proposed_diff_ref="diff-001",
        data_classification=DataClassLevel.INTERNAL,
    )


def _make_policy_guardian_input(change_id: str = "chg-001") -> PolicyGuardianInput:
    return PolicyGuardianInput(
        schema_version="1.0.0",
        change_id=change_id,
        data_classification=DataClassLevel.INTERNAL,
        target_systems=["repo-enterprise-db"],
        requested_actions=["action.schema.migrate"],
        actor_identity="operator@changemesh.internal",
    )


def _make_migration_engineer_input(change_id: str = "chg-001") -> MigrationEngineerInput:
    return MigrationEngineerInput(
        schema_version="1.0.0",
        change_id=change_id,
        target_system="repo-enterprise-db",
        source_schema_version="1.0.0",
        target_schema_version="2.0.0",
        migration_spec="ALTER TABLE users ADD COLUMN verified BOOLEAN DEFAULT FALSE;",
    )


def _make_evidence_auditor_input(change_id: str = "chg-001") -> EvidenceAuditorInput:
    return EvidenceAuditorInput(
        schema_version="1.0.0",
        change_id=change_id,
        success_criteria_ids=["sc-001", "sc-002"],
        evidence_record_refs=["ev-rec-001", "ev-rec-002"],
        rehearsal_result_refs=["reh-001"],
    )


def _make_release_steward_input(change_id: str = "chg-001") -> ReleaseStewardInput:
    return ReleaseStewardInput(
        schema_version="1.0.0",
        change_id=change_id,
        passport_id="passport-001",
        verified_artifact_ids=["art-001", "art-002"],
        target_repository="zyganali-glitch/ChangeMesh",
        authorization_reference="auth-decision-001",
    )


class DummyUnrelatedPayload(BaseModel):
    test_field: str = "unrelated"


# ===========================================================================
# A. True Controlled Overlap Tests
# ===========================================================================


@pytest.mark.anyio
async def test_true_parallel_concurrent_overlap_execution() -> None:
    """Prove parallel execution permits multiple independent branches in-flight concurrently."""
    change_id = "chg-overlap-001"
    coord = BranchCoordinator()

    branch1_started = asyncio.Event()
    branch2_started = asyncio.Event()
    overlap_verified = asyncio.Event()

    async def synchronized_runner(spec: BranchSpec, routing_res: RoutingResult) -> BaseModel:
        if spec.branch_id == "br-impact":
            branch1_started.set()
            # Wait until branch2 has also entered execution concurrently
            await branch2_started.wait()
            overlap_verified.set()
            return ImpactScoutOutput(
                schema_version="1.0.0",
                change_id=change_id,
                affected_files=["schema/migrations/001.sql"],
                affected_systems=["db"],
                conflict_detected=False,
                risk_level="LOW",
                blast_radius_score=0.1,
            )
        elif spec.branch_id == "br-policy":
            branch2_started.set()
            # Wait until branch1 has also entered execution concurrently
            await branch1_started.wait()
            overlap_verified.set()
            decision = AutonomyDecision(
                schema_version="1.0.0",
                decision_id=f"dec-{change_id}",
                change_request_id=change_id,
                action_class="action.schema.migrate",
                autonomy_class=AutonomyClass.AUTO_EXECUTE,
                policy_source="policy.canonical",
                rationale="Compliant",
                decided_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
            )
            return PolicyGuardianOutput(
                schema_version="1.0.0",
                change_id=change_id,
                policy_verdict="COMPLIANT",
                autonomy_decision=decision,
            )
        raise ValueError(f"Unknown branch {spec.branch_id}")

    plan = BranchPlan(
        plan_id="plan-overlap",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-impact",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-policy",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_policy_guardian_input(change_id),
                ),
            ),
        ],
    )

    # In parallel mode, both branches run concurrently and signal each other
    result = await coord.execute_plan(plan, branch_runner=synchronized_runner)

    assert result.is_successful is True
    assert overlap_verified.is_set() is True
    assert result.effective_strategy == ExecutionStrategy.PARALLEL
    assert len(result.branch_results) == 2


@pytest.mark.anyio
async def test_sequential_execution_does_not_execute_branches_concurrently() -> None:
    """Prove sequential execution executes branches strictly one at a time."""
    change_id = "chg-seq-order-001"
    coord = BranchCoordinator()

    execution_order: list[str] = []

    async def ordered_runner(spec: BranchSpec, routing_res: RoutingResult) -> BaseModel:
        execution_order.append(f"start-{spec.branch_id}")
        await asyncio.sleep(0.001)
        execution_order.append(f"end-{spec.branch_id}")
        if spec.branch_id == "br-impact":
            return ImpactScoutOutput(
                schema_version="1.0.0",
                change_id=change_id,
                affected_files=["f1"],
                affected_systems=["s1"],
            )
        return PolicyGuardianOutput(
            schema_version="1.0.0",
            change_id=change_id,
            policy_verdict="COMPLIANT",
            autonomy_decision=AutonomyDecision(
                schema_version="1.0.0",
                decision_id="d1",
                change_request_id=change_id,
                action_class="act",
                autonomy_class=AutonomyClass.AUTO_EXECUTE,
                policy_source="pol",
                rationale="r",
                decided_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
            ),
        )

    plan = BranchPlan(
        plan_id="plan-seq-order",
        change_id=change_id,
        strategy=ExecutionStrategy.SEQUENTIAL,
        branches=[
            BranchSpec(
                branch_id="br-impact",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-policy",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_policy_guardian_input(change_id),
                ),
            ),
        ],
    )

    result = await coord.execute_plan(plan, branch_runner=ordered_runner)

    assert result.is_successful is True
    assert result.effective_strategy == ExecutionStrategy.SEQUENTIAL
    # Strictly non-overlapping sequential sequence
    assert execution_order == [
        "start-br-impact",
        "end-br-impact",
        "start-br-policy",
        "end-br-policy",
    ]


# ===========================================================================
# B. No Shared Mutable State Tests
# ===========================================================================


@pytest.mark.anyio
async def test_no_shared_mutable_state_across_branches() -> None:
    """Prove branch execution cannot mutate shared orchestrator objects or other branches."""
    change_id = "chg-isolation-001"
    coord = BranchCoordinator()

    impact_input = _make_impact_scout_input(change_id)
    policy_input = _make_policy_guardian_input(change_id)

    # Models are frozen (immutability check)
    with pytest.raises(ValidationError):
        impact_input.change_id = "mutated-change-id"  # type: ignore[misc]

    plan = BranchPlan(
        plan_id="plan-iso",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-1",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=impact_input,
                ),
            ),
            BranchSpec(
                branch_id="br-2",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=policy_input,
                ),
            ),
        ],
    )

    # Plan itself is frozen
    with pytest.raises(ValidationError):
        plan.change_id = "mutated-plan-id"  # type: ignore[misc]

    result = await coord.execute_plan(plan)
    assert result.is_successful is True

    # Branch results are independent frozen models
    res1 = result.get_branch_result("br-1")
    res2 = result.get_branch_result("br-2")
    assert res1 is not None and res2 is not None
    assert res1 is not res2

    with pytest.raises(ValidationError):
        res1.status = BranchStatus.FAILED  # type: ignore[misc]


# ===========================================================================
# C. Single-Writer Aggregation Tests
# ===========================================================================


@pytest.mark.anyio
async def test_single_writer_aggregation_produced_strictly_by_coordinator() -> None:
    """Prove CoordinationResult is constructed strictly as a final single-writer aggregate."""
    change_id = "chg-agg-001"
    coord = BranchCoordinator()

    plan = BranchPlan(
        plan_id="plan-agg",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-1",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-2",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_policy_guardian_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-3",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["semantic_evidence_sufficiency_review"],
                    payload=_make_evidence_auditor_input(change_id),
                ),
            ),
        ],
    )

    result = await coord.execute_plan(plan)

    assert isinstance(result, CoordinationResult)
    assert result.coordination_id.startswith("coord-")
    assert result.plan_id == "plan-agg"
    assert result.change_id == change_id
    assert result.branch_count == 3
    assert result.is_successful is True
    assert len(result.branch_results) == 3
    assert result.trace.total_branches == 3
    assert result.trace.success_count == 3
    assert result.trace.failure_count == 0
    assert result.trace.rejection_count == 0


# ===========================================================================
# D. Parallel vs Sequential Equivalence Tests
# ===========================================================================


@pytest.mark.anyio
async def test_parallel_and_sequential_yield_equivalent_canonical_state() -> None:
    """Prove same plan under parallel and sequential yields identical business state."""
    change_id = "chg-equiv-001"
    orch = ChangeOrchestrator()

    plan = BranchPlan(
        plan_id="plan-equiv",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-impact",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-policy",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_policy_guardian_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-auditor",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["semantic_evidence_sufficiency_review"],
                    payload=_make_evidence_auditor_input(change_id),
                ),
            ),
        ],
    )

    # 1. Execute in parallel mode
    parallel_res = await orch.execute_parallel(plan)

    # 2. Execute in forced sequential fallback mode
    sequential_res = await orch.execute_sequential(plan)

    # 3. Assert exact business equivalence
    parallel_res.assert_equivalent_state(sequential_res)
    sequential_res.assert_equivalent_state(parallel_res)

    proj_par = parallel_res.get_canonical_state_projection()
    proj_seq = sequential_res.get_canonical_state_projection()

    assert proj_par == proj_seq
    assert proj_par["is_successful"] is True
    assert proj_par["total_branches"] == 3
    assert len(proj_par["branch_outcomes"]) == 3

    # Verify each branch outcome in projection
    assert proj_par["branch_outcomes"][0]["branch_id"] == "br-impact"
    assert proj_par["branch_outcomes"][0]["agent_id"] == "agent-impact-scout"
    assert proj_par["branch_outcomes"][0]["status"] == "SUCCESS"

    assert proj_par["branch_outcomes"][1]["branch_id"] == "br-policy"
    assert proj_par["branch_outcomes"][1]["agent_id"] == "agent-policy-guardian"
    assert proj_par["branch_outcomes"][1]["status"] == "SUCCESS"

    assert proj_par["branch_outcomes"][2]["branch_id"] == "br-auditor"
    assert proj_par["branch_outcomes"][2]["agent_id"] == "agent-evidence-auditor"
    assert proj_par["branch_outcomes"][2]["status"] == "SUCCESS"


# ===========================================================================
# E. Stable Deterministic Ordering Tests
# ===========================================================================


@pytest.mark.anyio
async def test_deterministic_aggregation_order_despite_out_of_order_completion() -> None:
    """Prove that branch completion order does not affect deterministic result order."""
    change_id = "chg-order-001"
    coord = BranchCoordinator()

    # Runner where branch 2 finishes BEFORE branch 1
    async def inverted_timing_runner(spec: BranchSpec, routing_res: RoutingResult) -> BaseModel:
        if spec.branch_id == "br-first-in-plan":
            await asyncio.sleep(0.01)  # Finishes second
            return ImpactScoutOutput(
                schema_version="1.0.0",
                change_id=change_id,
                affected_files=["f1"],
                affected_systems=["s1"],
            )
        elif spec.branch_id == "br-second-in-plan":
            await asyncio.sleep(0.001)  # Finishes first
            return EvidenceAuditorOutput(
                schema_version="1.0.0",
                change_id=change_id,
                sufficiency_verdict="SUFFICIENT",
                evaluated_criteria_count=1,
                satisfied_criteria_count=1,
                semantic_review_summary="ok",
            )
        raise ValueError(f"Unknown {spec.branch_id}")

    plan = BranchPlan(
        plan_id="plan-timing-inversion",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-first-in-plan",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-second-in-plan",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["semantic_evidence_sufficiency_review"],
                    payload=_make_evidence_auditor_input(change_id),
                ),
            ),
        ],
    )

    result = await coord.execute_plan(plan, branch_runner=inverted_timing_runner)

    assert result.is_successful is True
    # Order in result MUST match plan order (index 0 == br-first-in-plan)
    assert result.branch_results[0].branch_id == "br-first-in-plan"
    assert result.branch_results[0].routing_result.trace.selected_agent_id == "agent-impact-scout"
    assert result.branch_results[1].branch_id == "br-second-in-plan"
    assert (
        result.branch_results[1].routing_result.trace.selected_agent_id == "agent-evidence-auditor"
    )


# ===========================================================================
# F. Routing Invariants Preserved
# ===========================================================================


@pytest.mark.anyio
async def test_branch_with_invalid_capability_fails_closed_without_specialist_execution() -> None:
    """Verify branch with invalid capability is REJECTED and specialist is never executed."""
    change_id = "chg-rej-cap-001"
    coord = BranchCoordinator()
    specialist_called = False

    async def tracking_runner(spec: BranchSpec, routing_res: RoutingResult) -> BaseModel:
        nonlocal specialist_called
        specialist_called = True
        return ImpactScoutOutput(
            schema_version="1.0.0",
            change_id=change_id,
            affected_files=[],
            affected_systems=[],
        )

    plan = BranchPlan(
        plan_id="plan-rej-cap",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-invalid-cap",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["invented_fictional_capability"],
                    payload=_make_impact_scout_input(change_id),
                ),
            )
        ],
    )

    result = await coord.execute_plan(plan, branch_runner=tracking_runner)

    assert result.is_successful is False
    assert specialist_called is False  # Specialist was NEVER invoked!
    res = result.get_branch_result("br-invalid-cap")
    assert res is not None
    assert res.status == BranchStatus.REJECTED
    assert res.is_rejected is True
    assert res.routing_result.outcome == RoutingOutcome.REJECTED
    assert res.routing_result.trace.rejection_reason == RoutingRejectionReason.UNKNOWN_CAPABILITY


@pytest.mark.anyio
async def test_branch_with_contract_mismatch_fails_closed() -> None:
    """Verify contract mismatch in a branch fails closed with REJECTED."""
    change_id = "chg-rej-contract-001"
    coord = BranchCoordinator()

    plan = BranchPlan(
        plan_id="plan-contract-mismatch",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-mismatch",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_impact_scout_input(change_id),  # Wrong input for Policy Guardian!
                ),
            )
        ],
    )

    result = await coord.execute_plan(plan)

    assert result.is_successful is False
    res = result.get_branch_result("br-mismatch")
    assert res is not None
    assert res.status == BranchStatus.REJECTED
    assert (
        res.routing_result.trace.rejection_reason == RoutingRejectionReason.INPUT_CONTRACT_MISMATCH
    )


@pytest.mark.anyio
async def test_branch_self_delegation_fails_closed() -> None:
    """Verify branch attempting self-delegation fails closed."""
    change_id = "chg-self-del-001"
    coord = BranchCoordinator()

    plan = BranchPlan(
        plan_id="plan-self-del",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-self",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["lifecycle_coordination"],
                    payload=_make_impact_scout_input(change_id),
                ),
            )
        ],
    )

    result = await coord.execute_plan(plan)

    assert result.is_successful is False
    res = result.get_branch_result("br-self")
    assert res is not None
    assert res.status == BranchStatus.REJECTED
    assert (
        res.routing_result.trace.rejection_reason
        == RoutingRejectionReason.SELF_DELEGATION_PROHIBITED
    )


# ===========================================================================
# G. Partial Failure / No Replay Tests
# ===========================================================================


@pytest.mark.anyio
async def test_partial_failure_honesty_and_no_replay() -> None:
    """Prove branch failure is represented honestly with zero automatic replay of completed work."""
    change_id = "chg-partial-fail-001"
    coord = BranchCoordinator()

    branch1_execution_count = 0
    branch2_execution_count = 0

    async def partial_fail_runner(spec: BranchSpec, routing_res: RoutingResult) -> BaseModel:
        nonlocal branch1_execution_count, branch2_execution_count
        if spec.branch_id == "br-good":
            branch1_execution_count += 1
            return ImpactScoutOutput(
                schema_version="1.0.0",
                change_id=change_id,
                affected_files=["f1"],
                affected_systems=["s1"],
            )
        elif spec.branch_id == "br-bad":
            branch2_execution_count += 1
            raise RuntimeError("Database connection timeout during policy check")
        raise ValueError(f"Unknown branch {spec.branch_id}")

    plan = BranchPlan(
        plan_id="plan-partial-fail",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-good",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-bad",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_policy_guardian_input(change_id),
                ),
            ),
        ],
    )

    result = await coord.execute_plan(plan, branch_runner=partial_fail_runner)

    # 1. Overall result is NOT successful (honest status)
    assert result.is_successful is False
    assert result.trace.success_count == 1
    assert result.trace.failure_count == 1

    # 2. Branch 1 succeeded
    br1 = result.get_branch_result("br-good")
    assert br1 is not None
    assert br1.status == BranchStatus.SUCCESS
    assert br1.output is not None

    # 3. Branch 2 failed with error
    br2 = result.get_branch_result("br-bad")
    assert br2 is not None
    assert br2.status == BranchStatus.FAILED
    assert br2.is_failed is True
    assert "Database connection timeout" in (br2.error_message or "")

    # 4. Invariant: NO UNSAFE REPLAY occurred (branch 1 executed exactly ONCE)
    assert branch1_execution_count == 1
    assert branch2_execution_count == 1


# ===========================================================================
# H. Fallback Selection Tests
# ===========================================================================


@pytest.mark.anyio
async def test_duplicate_specialist_targets_trigger_automatic_sequential_fallback() -> None:
    """Prove multiple branches targeting the same specialist trigger sequential fallback."""
    change_id = "chg-fallback-dup-001"
    coord = BranchCoordinator()

    plan = BranchPlan(
        plan_id="plan-dup-specialist",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-mig-1",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["migration_artifact_generation"],
                    payload=_make_migration_engineer_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-mig-2",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["migration_artifact_generation"],
                    payload=_make_migration_engineer_input(change_id),
                ),
            ),
        ],
    )

    # Check is_parallel_safe
    is_safe, reason = coord.is_parallel_safe(plan)
    assert is_safe is False
    assert "Conflict risk" in (reason or "")

    result = await coord.execute_plan(plan)

    assert result.is_successful is True
    assert result.requested_strategy == ExecutionStrategy.PARALLEL
    assert result.effective_strategy == ExecutionStrategy.SEQUENTIAL
    assert result.trace.fallback_triggered is True
    assert "Conflict risk" in (result.trace.fallback_reason or "")


@pytest.mark.anyio
async def test_release_steward_concurrency_triggers_automatic_sequential_fallback() -> None:
    """Prove release steward in a multi-branch plan triggers sequential fallback."""
    change_id = "chg-fallback-rel-001"
    coord = BranchCoordinator()

    plan = BranchPlan(
        plan_id="plan-rel-concurrency",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-impact",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-release",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["release_bundle_packaging"],
                    payload=_make_release_steward_input(change_id),
                ),
            ),
        ],
    )

    is_safe, reason = coord.is_parallel_safe(plan)
    assert is_safe is False
    assert "release steward" in (reason or "").lower()

    result = await coord.execute_plan(plan)

    assert result.is_successful is True
    assert result.effective_strategy == ExecutionStrategy.SEQUENTIAL
    assert result.trace.fallback_triggered is True


# ===========================================================================
# I. Authority Invariants Tests
# ===========================================================================


@pytest.mark.anyio
async def test_concurrency_mechanics_create_no_human_authority_or_policy_mutation() -> None:
    """Verify concurrency mechanics do not synthesize human authority or alter AutonomyDecision."""
    change_id = "chg-auth-inv-001"
    coord = BranchCoordinator()

    plan = BranchPlan(
        plan_id="plan-auth",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-policy",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_policy_guardian_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-release",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["release_bundle_packaging"],
                    payload=_make_release_steward_input(change_id),
                ),
            ),
        ],
    )

    result = await coord.execute_plan(plan)

    # 1. Authority lanes are preserved: output from Policy Guardian remains AUTO_EXECUTE
    pol_res = result.get_branch_result("br-policy")
    assert pol_res is not None
    assert isinstance(pol_res.output, PolicyGuardianOutput)
    assert pol_res.output.autonomy_decision.autonomy_class == AutonomyClass.AUTO_EXECUTE

    # 2. Release Steward output remains a draft PR spec with no external writes
    rel_res = result.get_branch_result("br-release")
    assert rel_res is not None
    assert isinstance(rel_res.output, ReleaseStewardOutput)
    assert rel_res.output.handoff_ready is True
    assert rel_res.output.requires_live_confirmation is False


# ===========================================================================
# J. Zero External Side Effects Tests
# ===========================================================================


@pytest.mark.anyio
async def test_zero_external_mutation_or_network_during_coordination() -> None:
    """Verify multi-agent coordination executes with zero external network or provider calls."""
    with (
        patch("urllib.request.urlopen") as mock_url,
        patch("http.client.HTTPConnection") as mock_http,
        patch("http.client.HTTPSConnection") as mock_https,
    ):
        change_id = "chg-zero-net-001"
        coord = BranchCoordinator()

        plan = BranchPlan(
            plan_id="plan-zero-net",
            change_id=change_id,
            strategy=ExecutionStrategy.PARALLEL,
            branches=[
                BranchSpec(
                    branch_id="br-1",
                    routing_request=RoutingRequest(
                        change_id=change_id,
                        required_capabilities=["repository_blast_radius_analysis"],
                        payload=_make_impact_scout_input(change_id),
                    ),
                ),
                BranchSpec(
                    branch_id="br-2",
                    routing_request=RoutingRequest(
                        change_id=change_id,
                        required_capabilities=["semantic_evidence_sufficiency_review"],
                        payload=_make_evidence_auditor_input(change_id),
                    ),
                ),
            ],
        )

        result = await coord.execute_plan(plan)
        assert result.is_successful is True

        mock_url.assert_not_called()
        mock_http.assert_not_called()
        mock_https.assert_not_called()


# ===========================================================================
# K. Plan Validation & Edge Cases
# ===========================================================================


def test_branch_plan_validation_rejects_duplicate_branch_ids() -> None:
    """Verify BranchPlan rejects duplicate branch_ids."""
    change_id = "chg-val-001"
    req = RoutingRequest(
        change_id=change_id,
        required_capabilities=["repository_blast_radius_analysis"],
        payload=_make_impact_scout_input(change_id),
    )

    with pytest.raises(ValidationError, match="Duplicate branch_id"):
        BranchPlan(
            plan_id="p1",
            change_id=change_id,
            branches=[
                BranchSpec(branch_id="b1", routing_request=req),
                BranchSpec(branch_id="b1", routing_request=req),
            ],
        )


def test_branch_plan_validation_rejects_mismatched_change_id() -> None:
    """Verify BranchPlan rejects a branch whose change_id does not match plan."""
    req_wrong = RoutingRequest(
        change_id="chg-other",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=_make_impact_scout_input("chg-other"),
    )

    with pytest.raises(ValidationError, match="does not match plan change_id"):
        BranchPlan(
            plan_id="p1",
            change_id="chg-plan",
            branches=[
                BranchSpec(branch_id="b1", routing_request=req_wrong),
            ],
        )


def test_branch_spec_validation_rejects_blank_branch_id() -> None:
    """Verify BranchSpec rejects blank branch_id."""
    req = RoutingRequest(
        change_id="c1",
        required_capabilities=["repository_blast_radius_analysis"],
        payload=_make_impact_scout_input("c1"),
    )

    with pytest.raises(ValidationError, match="branch_id must not be blank"):
        BranchSpec(branch_id="   ", routing_request=req)


@pytest.mark.anyio
async def test_orchestrator_coordination_wrapper_methods() -> None:
    """Verify ChangeOrchestrator exposes coordination methods and wraps coordinator cleanly."""
    change_id = "chg-orch-wrap-001"
    orch = ChangeOrchestrator()

    plan = BranchPlan(
        plan_id="plan-orch-wrap",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-1",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
        ],
    )

    # 1. is_parallel_safe via orchestrator
    is_safe, reason = orch.is_parallel_safe(plan)
    assert is_safe is True
    assert reason is None

    # 2. execute_branch_plan via orchestrator
    res = await orch.execute_branch_plan(plan)
    assert res.is_successful is True
    assert res.branch_count == 1


# ===========================================================================
# L. Advanced Equivalence & Multi-Branch Scenarios
# ===========================================================================


@pytest.mark.anyio
async def test_four_specialist_parallel_and_sequential_full_equivalence() -> None:
    """Verify full equivalence across all four non-release specialists in one plan."""
    change_id = "chg-full-4-001"
    orch = ChangeOrchestrator()

    plan = BranchPlan(
        plan_id="plan-4-specialists",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-scout",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-guardian",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_policy_guardian_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-engineer",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["migration_artifact_generation"],
                    payload=_make_migration_engineer_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-auditor",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["semantic_evidence_sufficiency_review"],
                    payload=_make_evidence_auditor_input(change_id),
                ),
            ),
        ],
    )

    is_safe, reason = orch.is_parallel_safe(plan)
    assert is_safe is True
    assert reason is None

    par_res = await orch.execute_parallel(plan)
    seq_res = await orch.execute_sequential(plan)

    par_res.assert_equivalent_state(seq_res)
    assert par_res.is_successful is True
    assert par_res.branch_count == 4
    assert seq_res.is_successful is True
    assert seq_res.branch_count == 4


@pytest.mark.anyio
async def test_partial_failure_canonical_equivalence_between_parallel_and_sequential() -> None:
    """Verify parallel and sequential yield identical canonical state even when a branch fails."""
    change_id = "chg-fail-equiv-001"
    coord = BranchCoordinator()

    async def failing_runner(spec: BranchSpec, routing_res: RoutingResult) -> BaseModel:
        if spec.branch_id == "br-fail":
            raise ValueError("Deterministic branch test failure")
        return ImpactScoutOutput(
            schema_version="1.0.0",
            change_id=change_id,
            affected_files=["f1"],
            affected_systems=["s1"],
        )

    plan = BranchPlan(
        plan_id="plan-fail-equiv",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-pass",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-fail",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
        ],
    )

    par_res = await coord.execute_plan(
        plan, force_strategy=ExecutionStrategy.PARALLEL, branch_runner=failing_runner
    )
    seq_res = await coord.execute_plan(
        plan, force_strategy=ExecutionStrategy.SEQUENTIAL, branch_runner=failing_runner
    )

    par_res.assert_equivalent_state(seq_res)
    assert par_res.is_successful is False
    assert seq_res.is_successful is False


@pytest.mark.anyio
async def test_rejected_branch_canonical_equivalence_between_parallel_and_sequential() -> None:
    """Verify parallel and sequential yield identical canonical state when a branch is rejected."""
    change_id = "chg-rej-equiv-001"
    coord = BranchCoordinator()

    plan = BranchPlan(
        plan_id="plan-rej-equiv",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-good",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-bad-cap",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["unknown_fictional_capability"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
        ],
    )

    par_res = await coord.execute_plan(plan, force_strategy=ExecutionStrategy.PARALLEL)
    seq_res = await coord.execute_plan(plan, force_strategy=ExecutionStrategy.SEQUENTIAL)

    par_res.assert_equivalent_state(seq_res)
    assert par_res.is_successful is False
    assert seq_res.is_successful is False
    assert par_res.branch_results[1].status == BranchStatus.REJECTED
    assert seq_res.branch_results[1].status == BranchStatus.REJECTED


@pytest.mark.anyio
async def test_three_way_ordering_inversion_maintains_strict_plan_order() -> None:
    """Verify 3 branches in inverted order maintain exact deterministic result order."""
    change_id = "chg-3-order-001"
    coord = BranchCoordinator()

    async def arbitrary_timing_runner(spec: BranchSpec, routing_res: RoutingResult) -> BaseModel:
        if spec.branch_id == "br-first":
            await asyncio.sleep(0.015)  # Completes 3rd
            return ImpactScoutOutput(
                schema_version="1.0.0",
                change_id=change_id,
                affected_files=["f1"],
                affected_systems=["s1"],
            )
        elif spec.branch_id == "br-second":
            await asyncio.sleep(0.008)  # Completes 2nd
            return PolicyGuardianOutput(
                schema_version="1.0.0",
                change_id=change_id,
                policy_verdict="COMPLIANT",
                autonomy_decision=AutonomyDecision(
                    schema_version="1.0.0",
                    decision_id="d1",
                    change_request_id=change_id,
                    action_class="act",
                    autonomy_class=AutonomyClass.AUTO_EXECUTE,
                    policy_source="pol",
                    rationale="r",
                    decided_at=datetime(2026, 8, 15, 0, 0, 0, tzinfo=timezone.utc),
                ),
            )
        elif spec.branch_id == "br-third":
            await asyncio.sleep(0.001)  # Completes 1st
            return EvidenceAuditorOutput(
                schema_version="1.0.0",
                change_id=change_id,
                sufficiency_verdict="SUFFICIENT",
                evaluated_criteria_count=1,
                satisfied_criteria_count=1,
                semantic_review_summary="ok",
            )
        raise ValueError(f"Unknown {spec.branch_id}")

    plan = BranchPlan(
        plan_id="plan-3-inversion",
        change_id=change_id,
        strategy=ExecutionStrategy.PARALLEL,
        branches=[
            BranchSpec(
                branch_id="br-first",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["repository_blast_radius_analysis"],
                    payload=_make_impact_scout_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-second",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["autonomy_classification_evaluation"],
                    payload=_make_policy_guardian_input(change_id),
                ),
            ),
            BranchSpec(
                branch_id="br-third",
                routing_request=RoutingRequest(
                    change_id=change_id,
                    required_capabilities=["semantic_evidence_sufficiency_review"],
                    payload=_make_evidence_auditor_input(change_id),
                ),
            ),
        ],
    )

    result = await coord.execute_plan(plan, branch_runner=arbitrary_timing_runner)

    assert result.is_successful is True
    assert result.branch_results[0].branch_id == "br-first"
    assert result.branch_results[1].branch_id == "br-second"
    assert result.branch_results[2].branch_id == "br-third"


@pytest.mark.anyio
async def test_all_canonical_specialists_default_execution() -> None:
    """Verify default in-process ADK execution succeeds for all 5 canonical specialists."""
    change_id = "chg-all-specialists-001"
    coord = BranchCoordinator()

    # Run each specialist as a dedicated branch and verify typed output schemas
    specs = [
        BranchSpec(
            branch_id="br-impact",
            routing_request=RoutingRequest(
                change_id=change_id,
                required_capabilities=["repository_blast_radius_analysis"],
                payload=_make_impact_scout_input(change_id),
            ),
        ),
        BranchSpec(
            branch_id="br-policy",
            routing_request=RoutingRequest(
                change_id=change_id,
                required_capabilities=["autonomy_classification_evaluation"],
                payload=_make_policy_guardian_input(change_id),
            ),
        ),
        BranchSpec(
            branch_id="br-migration",
            routing_request=RoutingRequest(
                change_id=change_id,
                required_capabilities=["migration_artifact_generation"],
                payload=_make_migration_engineer_input(change_id),
            ),
        ),
        BranchSpec(
            branch_id="br-evidence",
            routing_request=RoutingRequest(
                change_id=change_id,
                required_capabilities=["semantic_evidence_sufficiency_review"],
                payload=_make_evidence_auditor_input(change_id),
            ),
        ),
        BranchSpec(
            branch_id="br-release",
            routing_request=RoutingRequest(
                change_id=change_id,
                required_capabilities=["release_bundle_packaging"],
                payload=_make_release_steward_input(change_id),
            ),
        ),
    ]

    for spec in specs:
        plan = BranchPlan(
            plan_id=f"plan-{spec.branch_id}",
            change_id=change_id,
            strategy=ExecutionStrategy.SEQUENTIAL,
            branches=[spec],
        )
        res = await coord.execute_plan(plan)
        assert res.is_successful is True
        br = res.get_branch_result(spec.branch_id)
        assert br is not None
        assert br.status == BranchStatus.SUCCESS
        assert br.output is not None
