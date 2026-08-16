"""ChangeMesh Google Cloud Firestore provider adapter.

P-10.02: Provider-specific persistence adapter for Google Cloud Firestore
fulfilling the provider-neutral SagaStateRepository protocol.

Google Cloud Firestore SDK types are strictly confined to this adapter.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from domain.contracts.change_lifecycle import ChangeState
from src.orchestrator.state_repository import (
    ApprovalRecord,
    ApprovalResolutionStatus,
    ChangeRecord,
    CheckpointRecord,
    DocumentNotFoundError,
    EvidenceRefRecord,
    OptimisticConcurrencyError,
    PassportRecord,
    PersistenceSchemaError,
    SagaStateRepository,
    TaskRecord,
    TenantIsolationError,
    TenantRecord,
    scan_for_secrets,
    validate_tenant_id,
)

logger = logging.getLogger(__name__)


def _to_firestore_dict(model_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert model dictionary to Firestore-compatible dictionary with native datetimes."""
    out: Dict[str, Any] = {}
    for k, v in model_dict.items():
        if isinstance(v, dict):
            out[k] = _to_firestore_dict(v)
        elif isinstance(v, (list, tuple)):
            out[k] = [_to_firestore_dict(item) if isinstance(item, dict) else item for item in v]
        elif isinstance(v, datetime):
            # Keep timezone-aware datetime for Firestore native timestamp conversion
            out[k] = v
        else:
            out[k] = v
    return out


def _from_firestore_dict(doc_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert Firestore document map to Pydantic-compatible dictionary."""
    if doc_dict is None:
        return {}
    out: Dict[str, Any] = {}
    for k, v in doc_dict.items():
        if hasattr(v, "to_datetime"):
            # Firestore DatetimeWithNanoseconds
            out[k] = v.to_datetime().astimezone(timezone.utc)
        elif isinstance(v, dict):
            out[k] = _from_firestore_dict(v)
        elif isinstance(v, list):
            out[k] = [
                _from_firestore_dict(item)
                if isinstance(item, dict)
                else (
                    item.to_datetime().astimezone(timezone.utc)
                    if hasattr(item, "to_datetime")
                    else item
                )
                for item in v
            ]
        else:
            out[k] = v
    return out


class GoogleFirestoreSagaRepository(SagaStateRepository):
    """Google Cloud Firestore persistence adapter for ChangeMesh durable saga state."""

    def __init__(
        self,
        project_id: str,
        database: str = "(default)",
        firestore_client: Optional[Any] = None,
    ) -> None:
        if not project_id or not project_id.strip():
            raise ValueError("project_id must not be blank")
        self.project_id = project_id.strip()
        self.database = database

        if firestore_client is None:
            from google.cloud import firestore  # type: ignore[import-untyped,attr-defined]

            self._db = firestore.Client(project=self.project_id, database=self.database)
        else:
            self._db = firestore_client

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------------
    # Tenant Operations
    # ------------------------------------------------------------------------

    def create_tenant(self, tenant: TenantRecord) -> TenantRecord:
        tid = validate_tenant_id(tenant.tenant_id)
        scan_for_secrets(tenant.model_dump())
        doc_ref = self._db.collection("tenants").document(tid)
        doc = doc_ref.get()
        if doc.exists:
            raise PersistenceSchemaError(f"Tenant {tid!r} already exists")
        data = _to_firestore_dict(tenant.model_dump())
        doc_ref.set(data)
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[TenantRecord]:
        tid = validate_tenant_id(tenant_id)
        doc = self._db.collection("tenants").document(tid).get()
        if not doc.exists:
            return None
        raw = _from_firestore_dict(doc.to_dict())
        return TenantRecord(**raw)

    # ------------------------------------------------------------------------
    # Change Operations
    # ------------------------------------------------------------------------

    def create_change(self, tenant_id: str, change: ChangeRecord) -> ChangeRecord:
        tid = validate_tenant_id(tenant_id)
        if change.tenant_id != tid:
            raise TenantIsolationError(
                f"Change tenant_id {change.tenant_id!r} does not match operation tenant_id {tid!r}"
            )
        scan_for_secrets(change.model_dump())
        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change.change_id)
        )
        doc = doc_ref.get()
        if doc.exists:
            raise PersistenceSchemaError(
                f"Change {change.change_id!r} already exists in tenant {tid!r}"
            )
        doc_ref.set(_to_firestore_dict(change.model_dump()))
        return change

    def get_change(self, tenant_id: str, change_id: str) -> Optional[ChangeRecord]:
        tid = validate_tenant_id(tenant_id)
        if not change_id or not change_id.strip():
            raise ValueError("change_id must not be blank")
        doc = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .get()
        )
        if not doc.exists:
            return None
        raw = _from_firestore_dict(doc.to_dict())
        record = ChangeRecord(**raw)
        if record.tenant_id != tid:
            raise TenantIsolationError("Tenant ID mismatch in stored document")
        return record

    def update_change(
        self, tenant_id: str, change: ChangeRecord, expected_version: int
    ) -> ChangeRecord:
        tid = validate_tenant_id(tenant_id)
        if change.tenant_id != tid:
            raise TenantIsolationError("Change tenant_id mismatch with operation path")
        scan_for_secrets(change.model_dump())

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change.change_id)
        )
        doc = doc_ref.get()
        if not doc.exists:
            raise DocumentNotFoundError(
                f"Change {change.change_id!r} not found",
                document_path=f"/tenants/{tid}/changes/{change.change_id}",
            )
        current_data = doc.to_dict()
        actual_version = current_data.get("version", 0)
        if actual_version != expected_version:
            raise OptimisticConcurrencyError(
                f"Version conflict on change {change.change_id!r}: expected {expected_version}, found {actual_version}",
                document_path=f"/tenants/{tid}/changes/{change.change_id}",
                expected_version=expected_version,
                actual_version=actual_version,
            )
        new_version = actual_version + 1
        updated = change.model_copy(update={"version": new_version, "updated_at": self._now()})
        doc_ref.set(_to_firestore_dict(updated.model_dump()))
        return updated

    def list_changes(
        self, tenant_id: str, state: Optional[ChangeState] = None
    ) -> List[ChangeRecord]:
        tid = validate_tenant_id(tenant_id)
        query = self._db.collection("tenants").document(tid).collection("changes")
        if state is not None:
            query = query.where("state", "==", state.value)
        docs = query.stream()
        results: List[ChangeRecord] = []
        for doc in docs:
            raw = _from_firestore_dict(doc.to_dict())
            results.append(ChangeRecord(**raw))
        results.sort(key=lambda c: c.updated_at, reverse=True)
        return results

    # ------------------------------------------------------------------------
    # Task Operations
    # ------------------------------------------------------------------------

    def create_task(self, tenant_id: str, change_id: str, task: TaskRecord) -> TaskRecord:
        tid = validate_tenant_id(tenant_id)
        if task.tenant_id != tid or task.change_id != change_id:
            raise TenantIsolationError("Task tenant_id or change_id mismatch with operation path")
        scan_for_secrets(task.model_dump())
        if not self.get_change(tid, change_id):
            raise DocumentNotFoundError(f"Parent change {change_id!r} not found")

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("tasks")
            .document(task.task_id)
        )
        if doc_ref.get().exists:
            raise PersistenceSchemaError(f"Task {task.task_id!r} already exists")
        doc_ref.set(_to_firestore_dict(task.model_dump()))
        return task

    def get_task(self, tenant_id: str, change_id: str, task_id: str) -> Optional[TaskRecord]:
        tid = validate_tenant_id(tenant_id)
        doc = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("tasks")
            .document(task_id)
            .get()
        )
        if not doc.exists:
            return None
        return TaskRecord(**_from_firestore_dict(doc.to_dict()))

    def list_tasks(self, tenant_id: str, change_id: str) -> List[TaskRecord]:
        tid = validate_tenant_id(tenant_id)
        docs = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("tasks")
            .stream()
        )
        tasks = [TaskRecord(**_from_firestore_dict(d.to_dict())) for d in docs]
        tasks.sort(key=lambda t: t.sequence_number)
        return tasks

    def update_task(
        self, tenant_id: str, change_id: str, task: TaskRecord, expected_version: int
    ) -> TaskRecord:
        tid = validate_tenant_id(tenant_id)
        if task.tenant_id != tid or task.change_id != change_id:
            raise TenantIsolationError("Task tenant_id or change_id mismatch with operation path")
        scan_for_secrets(task.model_dump())

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("tasks")
            .document(task.task_id)
        )
        doc = doc_ref.get()
        if not doc.exists:
            raise DocumentNotFoundError(f"Task {task.task_id!r} not found")
        doc_data = doc.to_dict() or {}
        actual_version = doc_data.get("version", 0)
        if actual_version != expected_version:
            raise OptimisticConcurrencyError(
                f"Version conflict on task {task.task_id!r}: expected {expected_version}, found {actual_version}",
                document_path=f"/tenants/{tid}/changes/{change_id}/tasks/{task.task_id}",
                expected_version=expected_version,
                actual_version=actual_version,
            )
        new_version = actual_version + 1
        updated = task.model_copy(update={"version": new_version, "updated_at": self._now()})
        doc_ref.set(_to_firestore_dict(updated.model_dump()))
        return updated

    # ------------------------------------------------------------------------
    # Checkpoint Operations
    # ------------------------------------------------------------------------

    def create_checkpoint(
        self, tenant_id: str, change_id: str, checkpoint: CheckpointRecord
    ) -> CheckpointRecord:
        tid = validate_tenant_id(tenant_id)
        if checkpoint.tenant_id != tid or checkpoint.change_id != change_id:
            raise TenantIsolationError(
                "Checkpoint tenant_id or change_id mismatch with operation path"
            )
        scan_for_secrets(checkpoint.model_dump())
        if not self.get_change(tid, change_id):
            raise DocumentNotFoundError(f"Parent change {change_id!r} not found")

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("checkpoints")
            .document(checkpoint.checkpoint_id)
        )
        if doc_ref.get().exists:
            raise PersistenceSchemaError(f"Checkpoint {checkpoint.checkpoint_id!r} already exists")
        doc_ref.set(_to_firestore_dict(checkpoint.model_dump()))
        return checkpoint

    def get_checkpoint(
        self, tenant_id: str, change_id: str, checkpoint_id: str
    ) -> Optional[CheckpointRecord]:
        tid = validate_tenant_id(tenant_id)
        doc = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("checkpoints")
            .document(checkpoint_id)
            .get()
        )
        if not doc.exists:
            return None
        return CheckpointRecord(**_from_firestore_dict(doc.to_dict()))

    def list_checkpoints(self, tenant_id: str, change_id: str) -> List[CheckpointRecord]:
        tid = validate_tenant_id(tenant_id)
        docs = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("checkpoints")
            .stream()
        )
        cps = [CheckpointRecord(**_from_firestore_dict(d.to_dict())) for d in docs]
        cps.sort(key=lambda c: c.sequence_number, reverse=True)
        return cps

    def get_latest_checkpoint(self, tenant_id: str, change_id: str) -> Optional[CheckpointRecord]:
        cps = self.list_checkpoints(tenant_id, change_id)
        return cps[0] if cps else None

    # ------------------------------------------------------------------------
    # Evidence Reference Operations
    # ------------------------------------------------------------------------

    def create_evidence_ref(
        self, tenant_id: str, change_id: str, ref: EvidenceRefRecord
    ) -> EvidenceRefRecord:
        tid = validate_tenant_id(tenant_id)
        if ref.tenant_id != tid or ref.change_id != change_id:
            raise TenantIsolationError(
                "EvidenceRef tenant_id or change_id mismatch with operation path"
            )
        scan_for_secrets(ref.model_dump())
        if not self.get_change(tid, change_id):
            raise DocumentNotFoundError(f"Parent change {change_id!r} not found")

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("evidence_refs")
            .document(ref.evidence_id)
        )
        if doc_ref.get().exists:
            raise PersistenceSchemaError(f"Evidence reference {ref.evidence_id!r} already exists")
        doc_ref.set(_to_firestore_dict(ref.model_dump()))
        return ref

    def get_evidence_ref(
        self, tenant_id: str, change_id: str, evidence_id: str
    ) -> Optional[EvidenceRefRecord]:
        tid = validate_tenant_id(tenant_id)
        doc = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("evidence_refs")
            .document(evidence_id)
            .get()
        )
        if not doc.exists:
            return None
        return EvidenceRefRecord(**_from_firestore_dict(doc.to_dict()))

    def list_evidence_refs(self, tenant_id: str, change_id: str) -> List[EvidenceRefRecord]:
        tid = validate_tenant_id(tenant_id)
        docs = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("evidence_refs")
            .stream()
        )
        refs = [EvidenceRefRecord(**_from_firestore_dict(d.to_dict())) for d in docs]
        refs.sort(key=lambda r: r.collected_at)
        return refs

    # ------------------------------------------------------------------------
    # Approval Operations
    # ------------------------------------------------------------------------

    def create_approval(
        self, tenant_id: str, change_id: str, approval: ApprovalRecord
    ) -> ApprovalRecord:
        tid = validate_tenant_id(tenant_id)
        if approval.tenant_id != tid or approval.change_id != change_id:
            raise TenantIsolationError(
                "Approval tenant_id or change_id mismatch with operation path"
            )
        scan_for_secrets(approval.model_dump())
        if not self.get_change(tid, change_id):
            raise DocumentNotFoundError(f"Parent change {change_id!r} not found")

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("approvals")
            .document(approval.card_id)
        )
        if doc_ref.get().exists:
            raise PersistenceSchemaError(f"Approval card {approval.card_id!r} already exists")
        doc_ref.set(_to_firestore_dict(approval.model_dump()))
        return approval

    def get_approval(
        self, tenant_id: str, change_id: str, card_id: str
    ) -> Optional[ApprovalRecord]:
        tid = validate_tenant_id(tenant_id)
        doc = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("approvals")
            .document(card_id)
            .get()
        )
        if not doc.exists:
            return None
        return ApprovalRecord(**_from_firestore_dict(doc.to_dict()))

    def list_approvals(
        self, tenant_id: str, change_id: str, status: Optional[ApprovalResolutionStatus] = None
    ) -> List[ApprovalRecord]:
        tid = validate_tenant_id(tenant_id)
        query = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("approvals")
        )
        if status is not None:
            query = query.where("resolution_status", "==", status.value)
        docs = query.stream()
        apps = [ApprovalRecord(**_from_firestore_dict(d.to_dict())) for d in docs]
        apps.sort(key=lambda a: a.card_created_at, reverse=True)
        return apps

    def update_approval(
        self, tenant_id: str, change_id: str, approval: ApprovalRecord, expected_version: int
    ) -> ApprovalRecord:
        tid = validate_tenant_id(tenant_id)
        if approval.tenant_id != tid or approval.change_id != change_id:
            raise TenantIsolationError(
                "Approval tenant_id or change_id mismatch with operation path"
            )
        scan_for_secrets(approval.model_dump())

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("approvals")
            .document(approval.card_id)
        )
        doc = doc_ref.get()
        if not doc.exists:
            raise DocumentNotFoundError(f"Approval card {approval.card_id!r} not found")
        doc_data = doc.to_dict() or {}
        actual_version = doc_data.get("version", 0)
        if actual_version != expected_version:
            raise OptimisticConcurrencyError(
                f"Version conflict on approval {approval.card_id!r}: expected {expected_version}, found {actual_version}",
                document_path=f"/tenants/{tid}/changes/{change_id}/approvals/{approval.card_id}",
                expected_version=expected_version,
                actual_version=actual_version,
            )
        new_version = actual_version + 1
        updated = approval.model_copy(update={"version": new_version, "updated_at": self._now()})
        doc_ref.set(_to_firestore_dict(updated.model_dump()))
        return updated

    # ------------------------------------------------------------------------
    # Capability Passport Operations
    # ------------------------------------------------------------------------

    def create_passport(self, tenant_id: str, passport: PassportRecord) -> PassportRecord:
        tid = validate_tenant_id(tenant_id)
        if passport.tenant_id != tid:
            raise TenantIsolationError("Passport tenant_id mismatch with operation path")
        scan_for_secrets(passport.model_dump())

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("passports")
            .document(passport.passport_id)
        )
        if doc_ref.get().exists:
            raise PersistenceSchemaError(f"Passport {passport.passport_id!r} already exists")
        doc_ref.set(_to_firestore_dict(passport.model_dump()))
        return passport

    def get_passport(self, tenant_id: str, passport_id: str) -> Optional[PassportRecord]:
        tid = validate_tenant_id(tenant_id)
        doc = (
            self._db.collection("tenants")
            .document(tid)
            .collection("passports")
            .document(passport_id)
            .get()
        )
        if not doc.exists:
            return None
        return PassportRecord(**_from_firestore_dict(doc.to_dict()))

    def get_active_passport(
        self, tenant_id: str, agent_id: str, agent_revision: str
    ) -> Optional[PassportRecord]:
        tid = validate_tenant_id(tenant_id)
        now = self._now()
        docs = (
            self._db.collection("tenants")
            .document(tid)
            .collection("passports")
            .where("agent_id", "==", agent_id)
            .where("agent_revision", "==", agent_revision)
            .where("is_revoked", "==", False)
            .stream()
        )
        for doc in docs:
            p = PassportRecord(**_from_firestore_dict(doc.to_dict()))
            if p.expires_at > now:
                return p
        return None

    def update_passport(
        self, tenant_id: str, passport: PassportRecord, expected_version: int
    ) -> PassportRecord:
        tid = validate_tenant_id(tenant_id)
        if passport.tenant_id != tid:
            raise TenantIsolationError("Passport tenant_id mismatch with operation path")
        scan_for_secrets(passport.model_dump())

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("passports")
            .document(passport.passport_id)
        )
        doc = doc_ref.get()
        if not doc.exists:
            raise DocumentNotFoundError(f"Passport {passport.passport_id!r} not found")
        doc_data = doc.to_dict() or {}
        actual_version = doc_data.get("version", 0)
        if actual_version != expected_version:
            raise OptimisticConcurrencyError(
                f"Version conflict on passport {passport.passport_id!r}: expected {expected_version}, found {actual_version}",
                document_path=f"/tenants/{tid}/passports/{passport.passport_id}",
                expected_version=expected_version,
                actual_version=actual_version,
            )
        new_version = actual_version + 1
        updated = passport.model_copy(update={"version": new_version, "updated_at": self._now()})
        doc_ref.set(_to_firestore_dict(updated.model_dump()))
        return updated
