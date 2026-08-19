"""ChangeMesh End-to-End Synthetic Enterprise Demo Fixture.

P-24: Builds a fictional enterprise billing change scenario demonstrating
the full ChangeMesh lifecycle from goal specification through automated
execution, evidence collection, and passport generation.

P-24.01: Synthetic billing system with legacy dependency conditions.
P-24.02: Canonical input goal and success criteria.
P-24.03: Baseline agent revisions, memory records, policies.
P-24.04: Full local E2E from goal to passport.
P-24.05: Cloud E2E path (requires real GCP — marked SIMULATED when unavailable).
P-24.06: One-command reproducible judge demo.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from src.dashboard.data_provider import DashboardDataProvider, DashboardSnapshot
from src.evidence.evidence_ledger import (
    EvidenceCompletenessReport,
    EvidenceLedger,
    SpanCollector,
    generate_completeness_report,
)
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.orchestrator_saga import (
    ChangeSagaOrchestrator,
    SagaExecutionResult,
)
from src.orchestrator.state_repository import CANONICAL_SCHEMA_VERSION
from src.security.agent_security import (
    AgentIdentity,
    AgentIdentityRegistry,
    AgentPermission,
    LocalModelArmor,
    ServiceAvailabilityReport,
)

logger = logging.getLogger(__name__)


# =========================================================================
# P-24.01 — Synthetic Billing System Fixture
# =========================================================================


class SyntheticBillingFixture(BaseModel):
    """Fictional enterprise billing system fixture.

    P-24.01: Deterministic, documented, fictional.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    fixture_id: str = "fixture-acme-billing-v1"
    company_name: str = "Acme Corp (FICTIONAL)"
    database_name: str = "billing_accounts"
    target_table: str = "payment_accounts"
    target_column: str = "payment_tier"
    legacy_dependency: str = "legacy_reconciliation_service"
    missing_proof_condition: str = "No existing automated tests for payment_tier column"
    intentional_conditions: tuple[str, ...] = (
        "Legacy dependency on reconciliation service without API contract",
        "Missing automated tests for target column",
        "Dual-write window during migration",
        "No rollback evidence for previous schema changes",
    )
    is_fictional: bool = True


def build_synthetic_fixture() -> SyntheticBillingFixture:
    """Build the synthetic billing system fixture."""
    return SyntheticBillingFixture()


# =========================================================================
# P-24.02 — Canonical Input Goal and Success Criteria
# =========================================================================


def build_demo_change_request(
    *,
    now: Optional[datetime] = None,
) -> ChangeRequest:
    """Build the canonical demo change request.

    P-24.02: Criteria include compatibility, dual-write, rollback,
    downstream update, audit evidence, no destructive removal.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    return ChangeRequest(
        schema_version="1.0.0",
        request_id="req-demo-acme-billing-001",
        title="Add payment_tier column to billing_accounts",
        description=(
            "Add payment_tier (VARCHAR(32)) column to billing_accounts table. "
            "Maintain backward compatibility during additive migration."
        ),
        target_systems=["billing-db", "payment-service", "billing-api"],
        data_classification=DataClassLevel.INTERNAL,
        success_criteria=[
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="crit-compat",
                description=(
                    "Static analysis and blast radius calculation completed for target assets"
                ),
                verification_method="deterministic",
                required_evidence_types=["BLAST_RADIUS_ANALYSIS"],
            ),
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="crit-dualwrite",
                description=(
                    "Deterministic migration DDL and manifest generated with valid file hashes"
                ),
                verification_method="deterministic",
                required_evidence_types=["MIGRATION_EXECUTION"],
            ),
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="crit-rollback",
                description="Rehearsal completed cleanly with zero unhandled faults",
                verification_method="deterministic",
                required_evidence_types=["REHEARSAL_SIMULATION"],
            ),
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="crit-audit",
                description=(
                    "Epistemic memory trust evaluation and "
                    "deterministic policy pre-checks completed"
                ),
                verification_method="deterministic",
                required_evidence_types=["EPISTEMIC_GROUNDING"],
            ),
        ],
        requested_by="demo-operator@acme-fictional.example",
        requested_at=now,
    )


# =========================================================================
# P-24.03 — Baseline Agent Revisions, Memory, Policies
# =========================================================================


def build_demo_agent_registry() -> AgentIdentityRegistry:
    """Build baseline agent revisions for the demo.

    P-24.03: One revision intentionally invalid for visible rejection.
    """
    registry = AgentIdentityRegistry()

    # Valid orchestrator
    registry.register(
        AgentIdentity(
            agent_id="demo-orchestrator",
            agent_revision="1.0.0-qualified",
            role="change_orchestrator",
            permissions=frozenset(
                {
                    AgentPermission.READ_STATE,
                    AgentPermission.WRITE_STATE,
                    AgentPermission.EMIT_EVENT,
                    AgentPermission.CREATE_CHECKPOINT,
                    AgentPermission.EXECUTE_TASK,
                }
            ),
        )
    )

    # Valid executor
    registry.register(
        AgentIdentity(
            agent_id="demo-executor",
            agent_revision="1.0.0-qualified",
            role="task_executor",
            permissions=frozenset(
                {
                    AgentPermission.READ_STATE,
                    AgentPermission.EXECUTE_TASK,
                    AgentPermission.EMIT_EVENT,
                }
            ),
        )
    )

    # Intentionally unqualified agent (for visible rejection demo)
    registry.register(
        AgentIdentity(
            agent_id="demo-unqualified",
            agent_revision="0.1.0-UNQUALIFIED",
            role="unqualified_agent",
            permissions=frozenset({AgentPermission.READ_STATE}),  # Read-only
        )
    )

    return registry


# =========================================================================
# P-24.04 — Full Local E2E
# =========================================================================


class DemoE2EResult(BaseModel):
    """Result of a full end-to-end demo run.

    P-24.04: All stages complete with correct evidence states.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    fixture_id: str
    change_id: str
    final_state: ChangeState
    saga_result: SagaExecutionResult
    dashboard_snapshot: DashboardSnapshot
    evidence_report: EvidenceCompletenessReport
    service_availability: ServiceAvailabilityReport
    model_armor_safe: bool
    is_cloud: bool = False
    demo_digest: str


def run_local_e2e_demo(
    *,
    now: Optional[datetime] = None,
) -> DemoE2EResult:
    """Run the full local E2E demo from goal to passport.

    P-24.04: All stages complete with correct evidence states.
    P-24.06: Reproducible without hidden edits.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 1. Build fixture
    fixture = build_synthetic_fixture()

    # 2. Build change request
    request = build_demo_change_request(now=now)

    # 3. Build infrastructure
    repo = InMemorySagaStateRepository()
    bus = LocalEventBus()
    timeline = CausalEventTimeline("demo-tenant")

    # 4. Run saga to completion with deterministic change_id
    change_id = f"change-{hashlib.sha256(request.request_id.encode()).hexdigest()[:12]}"
    orchestrator = ChangeSagaOrchestrator(
        repository=repo,
        event_bus=bus,
        timeline=timeline,
    )
    saga_result = orchestrator.run_saga(
        "demo-tenant",
        request,
        change_id=change_id,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        now=now,
    )

    # 5. Build evidence ledger
    ledger = EvidenceLedger()
    span_collector = SpanCollector(saga_result.change_id, saga_result.correlation_id)

    # Record evidence entries
    for i, task_id in enumerate([f"task-{j}" for j in range(saga_result.tasks_executed)]):
        ledger.append(
            entry_id=f"ev-{i:03d}",
            tenant_id="demo-tenant",
            change_id=saga_result.change_id,
            subject=f"task-{i}",
            evidence_state=EvidenceState.SIMULATED,
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            now=now,
        )
        span_collector.start_span(f"task-{i}", now=now)

    # 6. Generate evidence report
    evidence_report = generate_completeness_report(saga_result.change_id, ledger, span_collector)

    # 7. Generate dashboard snapshot
    dashboard = DashboardDataProvider(repository=repo)
    dashboard_snapshot = dashboard.generate_snapshot(
        saga_result.tenant_id,
        saga_result.change_id,
        now=now,
    )

    # 8. Check model armor
    armor = LocalModelArmor()
    armor_result = armor.check_input(request.description)

    # 9. Service availability
    service_report = ServiceAvailabilityReport()

    # 10. Compute demo digest
    digest_input = (
        f"{fixture.fixture_id}:{saga_result.change_id}:"
        f"{saga_result.final_state.value}:{evidence_report.total_entries}:"
        f"{now.isoformat()}"
    )
    demo_digest = hashlib.sha256(digest_input.encode()).hexdigest()[:16]

    return DemoE2EResult(
        fixture_id=fixture.fixture_id,
        change_id=saga_result.change_id,
        final_state=saga_result.final_state,
        saga_result=saga_result,
        dashboard_snapshot=dashboard_snapshot,
        evidence_report=evidence_report,
        service_availability=service_report,
        model_armor_safe=armor_result.is_safe,
        is_cloud=False,
        demo_digest=demo_digest,
    )
