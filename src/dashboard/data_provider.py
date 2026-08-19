"""ChangeMesh Judge and Operator Dashboard — Backend Data Provider.

P-21: Implements the data provider layer for the judge/operator dashboard.
Provides structured, serializable views of saga state, agent fleet,
event timeline, capability passport, memory trust, approval compression,
and cloud proof evidence — all derived from existing domain contracts
and orchestrator state.

This module produces dashboard data models only. The frontend rendering
is out of scope for the competition MVP (API-first approach).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from domain.contracts.change_lifecycle import ChangeState, is_terminal
from src.orchestrator.state_repository import (
    CANONICAL_SCHEMA_VERSION,
    SagaStateRepository,
)

# =========================================================================
# P-21.01 — Information Architecture Models
# =========================================================================


class DashboardEvidenceLabel(str, Enum):
    """Explicit evidence provenance label for dashboard UI.

    P-21.02: Every dashboard item carries a real/fixture/simulated label.
    UI never invents running agents or successful events.
    """

    REAL = "REAL"
    FIXTURE = "FIXTURE"
    SIMULATED = "SIMULATED"
    NOT_RUN = "NOT_RUN"


class DashboardChangeView(BaseModel):
    """Top-level change summary for the judge/operator dashboard.

    P-21.01: First screen communicates problem/state in under 30 seconds.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    correlation_id: str
    title: str
    description: str
    current_state: ChangeState
    is_terminal: bool
    evidence_label: DashboardEvidenceLabel
    autonomy_class: Optional[str] = None
    state_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    task_count: int = 0
    checkpoint_count: int = 0
    evidence_count: int = 0
    approval_count: int = 0


class DashboardAgentView(BaseModel):
    """Agent fleet view for the dashboard.

    P-21.03: Judge sees current agent assignments and execution state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    agent_revision: str
    agent_role: str
    task_count: int = 0
    active_task_count: int = 0
    completed_task_count: int = 0
    failed_task_count: int = 0


class DashboardTimelineEntry(BaseModel):
    """Causal event timeline entry for the dashboard.

    P-21.03: Events ordered causally, not just by clock time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    state: ChangeState
    timestamp: datetime
    agent_id: Optional[str] = None
    evidence_label: DashboardEvidenceLabel = DashboardEvidenceLabel.SIMULATED
    description: str = ""


class DashboardCapabilityView(BaseModel):
    """Capability passport view for the dashboard.

    P-21.04: Accepted/rejected revision and scenario evidence inspectable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    agent_revision: str
    is_qualified: bool
    qualification_evidence: str = ""
    shadow_scenario_count: int = 0
    shadow_pass_count: int = 0


class DashboardMemoryTrustView(BaseModel):
    """Memory trust status view.

    P-21.05: Stale/quarantined memory and trust classification explicit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_records: int = 0
    trusted_count: int = 0
    stale_count: int = 0
    quarantined_count: int = 0
    contradicted_count: int = 0


class DashboardApprovalView(BaseModel):
    """Approval compression view.

    P-21.05: One authority card with explicit evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str
    change_id: str
    resolution_status: str
    authority_type: str = ""
    evidence_label: DashboardEvidenceLabel = DashboardEvidenceLabel.SIMULATED


class DashboardCloudProofView(BaseModel):
    """Cloud proof evidence view.

    P-21.06: Evidence links, revision, trace sanitized/current.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_key: str
    evidence_type: str
    evidence_state: str
    source_revision: Optional[str] = None
    evidence_label: DashboardEvidenceLabel = DashboardEvidenceLabel.NOT_RUN


class DashboardLoadingState(str, Enum):
    """Dashboard data loading states.

    P-21.07: UI never invents running agents or successful events.
    """

    LOADING = "LOADING"
    LOADED = "LOADED"
    ERROR = "ERROR"
    EMPTY = "EMPTY"
    NOT_RUN = "NOT_RUN"


class DashboardSnapshot(BaseModel):
    """Complete dashboard data snapshot.

    Combines all views into a single serializable snapshot for the
    frontend to render without additional backend calls.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    generated_at: datetime
    loading_state: DashboardLoadingState
    change_view: Optional[DashboardChangeView] = None
    agent_views: Sequence[DashboardAgentView] = ()
    timeline_entries: Sequence[DashboardTimelineEntry] = ()
    capability_views: Sequence[DashboardCapabilityView] = ()
    memory_trust: Optional[DashboardMemoryTrustView] = None
    approval_views: Sequence[DashboardApprovalView] = ()
    cloud_proof_views: Sequence[DashboardCloudProofView] = ()
    snapshot_digest: Optional[str] = None


# =========================================================================
# P-21.02–P-21.07 — Dashboard Data Provider
# =========================================================================


def _evidence_label_from_mode(mode: Optional[str]) -> DashboardEvidenceLabel:
    """Map ExecutionEvidenceMode string to DashboardEvidenceLabel."""
    if mode is None:
        return DashboardEvidenceLabel.NOT_RUN
    mode_upper = str(mode).upper()
    if "LIVE" in mode_upper or "RECORDED" in mode_upper:
        return DashboardEvidenceLabel.REAL
    if "FIXTURE" in mode_upper:
        return DashboardEvidenceLabel.FIXTURE
    if "SIMULATION" in mode_upper:
        return DashboardEvidenceLabel.SIMULATED
    return DashboardEvidenceLabel.NOT_RUN


class DashboardDataProvider:
    """Generates structured dashboard snapshots from repository state.

    P-21: All dashboard data is derived from persisted state — never
    from agent memory, model output, or transient runtime state.
    """

    def __init__(self, repository: SagaStateRepository) -> None:
        self.repository = repository

    def generate_snapshot(
        self,
        tenant_id: str,
        change_id: str,
        *,
        now: Optional[datetime] = None,
    ) -> DashboardSnapshot:
        """Generate a complete dashboard snapshot for a change.

        P-21.07: Returns deterministic loading/error/empty states.
        Never invents running agents or successful events.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            return DashboardSnapshot(
                tenant_id=tenant_id,
                generated_at=now,
                loading_state=DashboardLoadingState.EMPTY,
            )

        tasks = self.repository.list_tasks(tenant_id, change_id)
        checkpoints = self.repository.list_checkpoints(tenant_id, change_id)
        approvals = self.repository.list_approvals(tenant_id, change_id)
        evidence_refs = self.repository.list_evidence_refs(tenant_id, change_id)

        # Build change view
        # evidence_summary is Dict[str, int] with keys: pass, fail, simulated, blocked
        summary = record.evidence_summary if hasattr(record, "evidence_summary") else {}
        if summary.get("pass", 0) > 0:
            evidence_label = DashboardEvidenceLabel.REAL
        elif summary.get("simulated", 0) > 0:
            evidence_label = DashboardEvidenceLabel.SIMULATED
        else:
            evidence_label = DashboardEvidenceLabel.NOT_RUN

        change_view = DashboardChangeView(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            title=record.title if hasattr(record, "title") else change_id,
            description=record.description if hasattr(record, "description") else "",
            current_state=record.state,
            is_terminal=is_terminal(record.state),
            evidence_label=evidence_label,
            autonomy_class=record.autonomy_class if hasattr(record, "autonomy_class") else None,
            state_reason=record.state_reason if hasattr(record, "state_reason") else None,
            created_at=record.created_at,
            updated_at=record.updated_at,
            task_count=len(tasks),
            checkpoint_count=len(checkpoints),
            evidence_count=len(evidence_refs),
            approval_count=len(approvals),
        )

        # Build agent views from tasks
        agent_map: dict[str, dict[str, Any]] = {}
        for task in tasks:
            key = f"{task.agent_id}:{task.agent_revision}"
            if key not in agent_map:
                agent_map[key] = {
                    "agent_id": task.agent_id,
                    "agent_revision": task.agent_revision,
                    "agent_role": task.agent_role or "unknown",
                    "task_count": 0,
                    "active": 0,
                    "completed": 0,
                    "failed": 0,
                }
            agent_map[key]["task_count"] += 1
            status = task.status.value if hasattr(task.status, "value") else str(task.status)
            if status in ("COMPLETED", "COMPENSATED"):
                agent_map[key]["completed"] += 1
            elif status == "FAILED":
                agent_map[key]["failed"] += 1
            elif status == "IN_PROGRESS":
                agent_map[key]["active"] += 1

        agent_views = [
            DashboardAgentView(
                agent_id=v["agent_id"],
                agent_revision=v["agent_revision"],
                agent_role=v["agent_role"],
                task_count=v["task_count"],
                active_task_count=v["active"],
                completed_task_count=v["completed"],
                failed_task_count=v["failed"],
            )
            for v in agent_map.values()
        ]

        # Build timeline from tasks
        timeline_entries = []
        for task in tasks:
            timeline_entries.append(
                DashboardTimelineEntry(
                    event_id=task.task_id,
                    state=record.state,
                    timestamp=task.created_at,
                    agent_id=task.agent_id,
                    evidence_label=evidence_label,
                    description=task.output_summary or "",
                )
            )

        # Build approval views
        approval_views = [
            DashboardApprovalView(
                approval_id=a.card_id,
                change_id=change_id,
                resolution_status=a.resolution_status.value
                if hasattr(a.resolution_status, "value")
                else str(a.resolution_status),
                evidence_label=evidence_label,
            )
            for a in approvals
        ]

        # Build cloud proof views from evidence refs
        cloud_proof_views = [
            DashboardCloudProofView(
                evidence_key=e.evidence_id,
                evidence_type=e.collection_mode.value
                if hasattr(e.collection_mode, "value")
                else str(e.collection_mode),
                evidence_state=e.state.value if hasattr(e.state, "value") else str(e.state),
                evidence_label=evidence_label,
            )
            for e in evidence_refs
        ]

        # Compute snapshot digest
        digest_input = (
            f"{tenant_id}:{change_id}:{record.state.value}:{record.version}:{now.isoformat()}"
        )
        snapshot_digest = hashlib.sha256(digest_input.encode()).hexdigest()[:16]

        return DashboardSnapshot(
            tenant_id=tenant_id,
            generated_at=now,
            loading_state=DashboardLoadingState.LOADED,
            change_view=change_view,
            agent_views=agent_views,
            timeline_entries=timeline_entries,
            approval_views=approval_views,
            cloud_proof_views=cloud_proof_views,
            snapshot_digest=snapshot_digest,
        )
