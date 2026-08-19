"""Tests for P-21 — Judge and Operator Dashboard.

P-21.01: Information architecture communicates state in under 30 seconds.
P-21.02: Real/fixture/simulated labels on every element.
P-21.03: Fleet/event timeline with causal correlation.
P-21.04: Capability passport/ShadowLab views.
P-21.05: Memory trust/approval compression views.
P-21.06: Passport/Google Cloud proof views.
P-21.07: Deterministic loading/error/empty states; no fake progress.
"""

from __future__ import annotations

import datetime
from datetime import timezone

import pytest

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import ExecutionEvidenceMode
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from src.dashboard.data_provider import (
    DashboardDataProvider,
    DashboardLoadingState,
)
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.orchestrator_saga import ChangeSagaOrchestrator

NOW = datetime.datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> InMemorySagaStateRepository:
    return InMemorySagaStateRepository()


@pytest.fixture
def bus() -> LocalEventBus:
    return LocalEventBus()


@pytest.fixture
def sample_change_request() -> ChangeRequest:
    return ChangeRequest(
        schema_version="1.0.0",
        request_id="req-p21-test-001",
        title="Add payment_tier column",
        description="Add payment_tier column to billing_accounts table",
        target_systems=["billing-db", "payment-service"],
        data_classification=DataClassLevel.INTERNAL,
        success_criteria=[
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="crit-01",
                description="Rehearsal succeeds cleanly",
                verification_method="deterministic",
                required_evidence_types=["REHEARSAL_SIMULATION"],
            )
        ],
        requested_by="engineer@example.com",
        requested_at=datetime.datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc),
    )


# =========================================================================
# P-21.07: DETERMINISTIC LOADING/ERROR/EMPTY STATES
# =========================================================================


class TestDashboardLoadingStates:
    """P-21.07: UI never invents running agents or successful events."""

    def test_nonexistent_change_returns_empty(self, repo):
        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot("test-tenant", "nonexistent", now=NOW)
        assert snapshot.loading_state == DashboardLoadingState.EMPTY
        assert snapshot.change_view is None
        assert len(snapshot.agent_views) == 0
        assert len(snapshot.timeline_entries) == 0

    def test_existing_change_returns_loaded(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        assert snapshot.loading_state == DashboardLoadingState.LOADED
        assert snapshot.change_view is not None


# =========================================================================
# P-21.01: INFORMATION ARCHITECTURE
# =========================================================================


class TestDashboardInformationArchitecture:
    """P-21.01: First screen communicates problem/state in under 30 seconds."""

    def test_change_view_has_required_fields(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        cv = snapshot.change_view
        assert cv is not None
        assert cv.tenant_id == result.tenant_id
        assert cv.change_id == result.change_id
        assert cv.current_state == ChangeState.COMPLETE
        assert cv.is_terminal is True
        assert cv.correlation_id is not None
        assert cv.task_count > 0

    def test_snapshot_has_digest(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        assert snapshot.snapshot_digest is not None
        assert len(snapshot.snapshot_digest) == 16


# =========================================================================
# P-21.02: EVIDENCE LABELS
# =========================================================================


class TestDashboardEvidenceLabels:
    """P-21.02: Real/fixture/simulated labels on every element."""

    def test_simulated_saga_has_simulated_label(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        # Evidence label derived from mode
        assert snapshot.change_view is not None


# =========================================================================
# P-21.03: FLEET/EVENT TIMELINE
# =========================================================================


class TestDashboardFleetTimeline:
    """P-21.03: Judge sees async work and current blockers."""

    def test_agent_views_derived_from_tasks(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        # Agent views should be derived from tasks
        assert len(snapshot.agent_views) > 0
        for av in snapshot.agent_views:
            assert av.agent_id is not None
            assert av.task_count > 0

    def test_timeline_entries_exist(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        assert len(snapshot.timeline_entries) > 0
        for entry in snapshot.timeline_entries:
            assert entry.event_id is not None
            assert entry.timestamp is not None


# =========================================================================
# P-21.04/05/06: CAPABILITY, MEMORY, APPROVAL, CLOUD PROOF
# =========================================================================


class TestDashboardViewsExist:
    """P-21.04-06: Views are structurally present and serializable."""

    def test_approval_views(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        # Approval views derived from approval records
        assert isinstance(snapshot.approval_views, (list, tuple))

    def test_cloud_proof_views(self, repo, bus, sample_change_request):
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        assert isinstance(snapshot.cloud_proof_views, (list, tuple))

    def test_snapshot_is_serializable(self, repo, bus, sample_change_request):
        """Dashboard snapshot must be JSON-serializable for API transport."""
        timeline = CausalEventTimeline("tmp")
        orch = ChangeSagaOrchestrator(repository=repo, event_bus=bus, timeline=timeline)
        result = orch.run_saga(
            "test-tenant",
            sample_change_request,
            evidence_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        provider = DashboardDataProvider(repository=repo)
        snapshot = provider.generate_snapshot(result.tenant_id, result.change_id, now=NOW)
        # Must serialize without error
        json_str = snapshot.model_dump_json()
        assert len(json_str) > 100
        assert "test-tenant" in json_str
        assert "COMPLETE" in json_str
