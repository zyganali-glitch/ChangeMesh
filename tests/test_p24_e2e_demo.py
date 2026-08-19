"""Tests for P-24 — End-to-End Synthetic Enterprise Demo.

P-24.01: Synthetic billing fixture deterministic, documented, fictional.
P-24.02: Canonical input goal with complete success criteria.
P-24.03: Agent revisions with intentional invalid for visible rejection.
P-24.04: Full local E2E from goal to passport.
P-24.05: Cloud E2E (SIMULATED when GCP unavailable).
P-24.06: One-command reproducible demo.
"""

from __future__ import annotations

import datetime
from datetime import timezone

from domain.contracts.change_lifecycle import ChangeState
from src.demo.e2e_demo import (
    build_demo_agent_registry,
    build_demo_change_request,
    build_synthetic_fixture,
    run_local_e2e_demo,
)
from src.security.agent_security import AgentPermission, ManagedServiceStatus

NOW = datetime.datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


# =========================================================================
# P-24.01: SYNTHETIC BILLING FIXTURE
# =========================================================================


class TestSyntheticFixture:
    """P-24.01: Fixture deterministic, documented, fictional."""

    def test_fixture_is_fictional(self):
        fixture = build_synthetic_fixture()
        assert fixture.is_fictional is True
        assert "FICTIONAL" in fixture.company_name

    def test_fixture_has_legacy_conditions(self):
        fixture = build_synthetic_fixture()
        assert len(fixture.intentional_conditions) >= 4
        assert "Legacy dependency" in fixture.intentional_conditions[0]

    def test_fixture_is_deterministic(self):
        f1 = build_synthetic_fixture()
        f2 = build_synthetic_fixture()
        assert f1 == f2


# =========================================================================
# P-24.02: CANONICAL INPUT GOAL
# =========================================================================


class TestCanonicalGoal:
    """P-24.02: Success criteria cover all required aspects."""

    def test_change_request_has_required_criteria(self):
        request = build_demo_change_request(now=NOW)
        criteria_ids = {c.criterion_id for c in request.success_criteria}
        assert "crit-compat" in criteria_ids
        assert "crit-dualwrite" in criteria_ids
        assert "crit-rollback" in criteria_ids
        assert "crit-audit" in criteria_ids

    def test_change_request_targets_multiple_systems(self):
        request = build_demo_change_request(now=NOW)
        assert len(request.target_systems) >= 3
        assert "billing-db" in request.target_systems

    def test_change_request_is_deterministic(self):
        r1 = build_demo_change_request(now=NOW)
        r2 = build_demo_change_request(now=NOW)
        assert r1.request_id == r2.request_id
        assert r1.title == r2.title


# =========================================================================
# P-24.03: AGENT REGISTRY WITH INVALID REVISION
# =========================================================================


class TestDemoAgentRegistry:
    """P-24.03: One revision intentionally invalid for visible rejection."""

    def test_qualified_orchestrator(self):
        registry = build_demo_agent_registry()
        assert registry.check_permission("demo-orchestrator", AgentPermission.EXECUTE_TASK)

    def test_unqualified_agent_denied_execution(self):
        registry = build_demo_agent_registry()
        assert not registry.check_permission("demo-unqualified", AgentPermission.EXECUTE_TASK)
        assert registry.check_permission("demo-unqualified", AgentPermission.READ_STATE)

    def test_three_agents_registered(self):
        registry = build_demo_agent_registry()
        assert registry.get("demo-orchestrator") is not None
        assert registry.get("demo-executor") is not None
        assert registry.get("demo-unqualified") is not None


# =========================================================================
# P-24.04: FULL LOCAL E2E
# =========================================================================


class TestLocalE2E:
    """P-24.04: All stages complete with correct evidence states."""

    def test_e2e_completes_to_complete_state(self):
        result = run_local_e2e_demo(now=NOW)
        assert result.final_state == ChangeState.COMPLETE

    def test_e2e_has_evidence_report(self):
        result = run_local_e2e_demo(now=NOW)
        assert result.evidence_report.total_entries > 0
        assert result.evidence_report.ledger_integrity is True

    def test_e2e_has_dashboard_snapshot(self):
        result = run_local_e2e_demo(now=NOW)
        assert result.dashboard_snapshot is not None
        assert result.dashboard_snapshot.change_view is not None

    def test_e2e_model_armor_safe(self):
        result = run_local_e2e_demo(now=NOW)
        assert result.model_armor_safe is True

    def test_e2e_not_cloud(self):
        result = run_local_e2e_demo(now=NOW)
        assert result.is_cloud is False

    def test_e2e_has_digest(self):
        result = run_local_e2e_demo(now=NOW)
        assert len(result.demo_digest) == 16

    def test_e2e_is_deterministic(self):
        r1 = run_local_e2e_demo(now=NOW)
        r2 = run_local_e2e_demo(now=NOW)
        assert r1.demo_digest == r2.demo_digest
        assert r1.final_state == r2.final_state


# =========================================================================
# P-24.05: CLOUD E2E (SIMULATED)
# =========================================================================


class TestCloudE2E:
    """P-24.05: Cloud E2E path labeled as SIMULATED when GCP unavailable."""

    def test_service_availability_shows_blocked(self):
        result = run_local_e2e_demo(now=NOW)
        sa = result.service_availability
        assert sa.agent_identity_status == ManagedServiceStatus.PERMISSION_BLOCKED
        assert sa.model_armor_status == ManagedServiceStatus.PERMISSION_BLOCKED
        assert sa.fallback_active is True


# =========================================================================
# P-24.06: REPRODUCIBLE DEMO
# =========================================================================


class TestReproducibleDemo:
    """P-24.06: Clean operator can reproduce or inspect recorded run."""

    def test_demo_is_serializable(self):
        result = run_local_e2e_demo(now=NOW)
        json_str = result.model_dump_json()
        assert len(json_str) > 500
        assert "COMPLETE" in json_str
        assert "demo-tenant" in json_str
        assert "fixture-acme-billing" in json_str

    def test_demo_fixture_id_in_result(self):
        result = run_local_e2e_demo(now=NOW)
        assert result.fixture_id == "fixture-acme-billing-v1"
