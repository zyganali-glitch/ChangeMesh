"""ChangeMesh thread-safe in-memory saga state repository.

P-10.02: Deterministic test double and local execution engine fulfilling
SagaStateRepository with lock-based compare-and-set (CAS) optimistic
concurrency control and fail-closed tenancy isolation.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from domain.contracts.change_lifecycle import ChangeState
from src.orchestrator.state_repository import (
    ApprovalRecord,
    ApprovalResolutionStatus,
    ChangeRecord,
    CheckpointRecord,
    DocumentNotFoundError,
    EvidenceRefRecord,
    IdempotencyReservationRecord,
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


class InMemorySagaStateRepository(SagaStateRepository):
    """Thread-safe, in-memory implementation of SagaStateRepository."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tenants: Dict[str, TenantRecord] = {}
        self._changes: Dict[str, Dict[str, ChangeRecord]] = {}
        self._tasks: Dict[str, Dict[str, Dict[str, TaskRecord]]] = {}
        self._checkpoints: Dict[str, Dict[str, Dict[str, CheckpointRecord]]] = {}
        self._idempotency_reservations: Dict[
            str, Dict[str, Dict[str, IdempotencyReservationRecord]]
        ] = {}
        self._evidence_refs: Dict[str, Dict[str, Dict[str, EvidenceRefRecord]]] = {}
        self._approvals: Dict[str, Dict[str, Dict[str, ApprovalRecord]]] = {}
        self._passports: Dict[str, Dict[str, PassportRecord]] = {}

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------------
    # Tenant Operations
    # ------------------------------------------------------------------------

    def create_tenant(self, tenant: TenantRecord) -> TenantRecord:
        with self._lock:
            tid = validate_tenant_id(tenant.tenant_id)
            scan_for_secrets(tenant.model_dump())
            if tid in self._tenants:
                raise PersistenceSchemaError(f"Tenant {tid!r} already exists")
            self._tenants[tid] = tenant
            self._changes[tid] = {}
            self._tasks[tid] = {}
            self._checkpoints[tid] = {}
            self._idempotency_reservations[tid] = {}
            self._evidence_refs[tid] = {}
            self._approvals[tid] = {}
            self._passports[tid] = {}
            return tenant

    def get_tenant(self, tenant_id: str) -> Optional[TenantRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            return self._tenants.get(tid)

    # ------------------------------------------------------------------------
    # Change Operations
    # ------------------------------------------------------------------------

    def create_change(self, tenant_id: str, change: ChangeRecord) -> ChangeRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if change.tenant_id != tid:
                raise TenantIsolationError(
                    f"Change tenant_id {change.tenant_id!r} does not match operation tenant_id {tid!r}"
                )
            scan_for_secrets(change.model_dump())
            if tid not in self._changes:
                self._changes[tid] = {}
            if change.change_id in self._changes[tid]:
                raise PersistenceSchemaError(
                    f"Change {change.change_id!r} already exists in tenant {tid!r}"
                )
            self._changes[tid][change.change_id] = change
            # Initialize child collections
            if tid not in self._tasks:
                self._tasks[tid] = {}
            self._tasks[tid][change.change_id] = {}

            if tid not in self._checkpoints:
                self._checkpoints[tid] = {}
            self._checkpoints[tid][change.change_id] = {}

            if tid not in self._idempotency_reservations:
                self._idempotency_reservations[tid] = {}
            self._idempotency_reservations[tid][change.change_id] = {}

            if tid not in self._evidence_refs:
                self._evidence_refs[tid] = {}
            self._evidence_refs[tid][change.change_id] = {}

            if tid not in self._approvals:
                self._approvals[tid] = {}
            self._approvals[tid][change.change_id] = {}

            return change

    def get_change(self, tenant_id: str, change_id: str) -> Optional[ChangeRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if not change_id or not change_id.strip():
                raise ValueError("change_id must not be blank")
            tenant_changes = self._changes.get(tid)
            if tenant_changes is None:
                return None
            record = tenant_changes.get(change_id)
            if record is not None and record.tenant_id != tid:
                raise TenantIsolationError("Tenant ID mismatch in stored record")
            return record

    def update_change(
        self, tenant_id: str, change: ChangeRecord, expected_version: int
    ) -> ChangeRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if change.tenant_id != tid:
                raise TenantIsolationError(
                    f"Change tenant_id {change.tenant_id!r} does not match operation tenant_id {tid!r}"
                )
            scan_for_secrets(change.model_dump())
            current = self.get_change(tid, change.change_id)
            if current is None:
                raise DocumentNotFoundError(
                    f"Change {change.change_id!r} not found in tenant {tid!r}",
                    document_path=f"/tenants/{tid}/changes/{change.change_id}",
                )
            if current.version != expected_version:
                raise OptimisticConcurrencyError(
                    f"Version conflict on change {change.change_id!r}: expected {expected_version}, found {current.version}",
                    document_path=f"/tenants/{tid}/changes/{change.change_id}",
                    expected_version=expected_version,
                    actual_version=current.version,
                )
            if change.created_at != current.created_at:
                raise PersistenceSchemaError("Cannot mutate immutable created_at timestamp")
            if change.correlation_id != current.correlation_id:
                raise PersistenceSchemaError("Cannot mutate immutable correlation_id")

            new_version = current.version + 1
            updated_doc = change.model_copy(
                update={"version": new_version, "updated_at": self._now()}
            )
            self._changes[tid][change.change_id] = updated_doc
            return updated_doc

    def list_changes(
        self, tenant_id: str, state: Optional[ChangeState] = None
    ) -> List[ChangeRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            changes = list(self._changes.get(tid, {}).values())
            if state is not None:
                changes = [c for c in changes if c.state == state]
            # Order by updated_at DESC
            changes.sort(key=lambda c: c.updated_at, reverse=True)
            return changes

    # ------------------------------------------------------------------------
    # Task Operations
    # ------------------------------------------------------------------------

    def create_task(self, tenant_id: str, change_id: str, task: TaskRecord) -> TaskRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if task.tenant_id != tid or task.change_id != change_id:
                raise TenantIsolationError(
                    "Task tenant_id or change_id mismatch with operation path"
                )
            scan_for_secrets(task.model_dump())
            if not self.get_change(tid, change_id):
                raise DocumentNotFoundError(
                    f"Parent change {change_id!r} not found in tenant {tid!r}"
                )

            change_tasks = self._tasks[tid].setdefault(change_id, {})
            if task.task_id in change_tasks:
                raise PersistenceSchemaError(f"Task {task.task_id!r} already exists")
            change_tasks[task.task_id] = task
            return task

    def get_task(self, tenant_id: str, change_id: str, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            return self._tasks.get(tid, {}).get(change_id, {}).get(task_id)

    def list_tasks(self, tenant_id: str, change_id: str) -> List[TaskRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            tasks = list(self._tasks.get(tid, {}).get(change_id, {}).values())
            tasks.sort(key=lambda t: t.sequence_number)
            return tasks

    def update_task(
        self, tenant_id: str, change_id: str, task: TaskRecord, expected_version: int
    ) -> TaskRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if task.tenant_id != tid or task.change_id != change_id:
                raise TenantIsolationError(
                    "Task tenant_id or change_id mismatch with operation path"
                )
            scan_for_secrets(task.model_dump())
            current = self.get_task(tid, change_id, task.task_id)
            if current is None:
                raise DocumentNotFoundError(f"Task {task.task_id!r} not found")
            if current.version != expected_version:
                raise OptimisticConcurrencyError(
                    f"Version conflict on task {task.task_id!r}: expected {expected_version}, found {current.version}",
                    document_path=f"/tenants/{tid}/changes/{change_id}/tasks/{task.task_id}",
                    expected_version=expected_version,
                    actual_version=current.version,
                )
            new_version = current.version + 1
            updated = task.model_copy(update={"version": new_version, "updated_at": self._now()})
            self._tasks[tid][change_id][task.task_id] = updated
            return updated

    # ------------------------------------------------------------------------
    # Checkpoint Operations
    # ------------------------------------------------------------------------

    def create_checkpoint(
        self, tenant_id: str, change_id: str, checkpoint: CheckpointRecord
    ) -> CheckpointRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if checkpoint.tenant_id != tid or checkpoint.change_id != change_id:
                raise TenantIsolationError(
                    "Checkpoint tenant_id or change_id mismatch with operation path"
                )
            scan_for_secrets(checkpoint.model_dump())
            if not self.get_change(tid, change_id):
                raise DocumentNotFoundError(
                    f"Parent change {change_id!r} not found in tenant {tid!r}"
                )

            cps = self._checkpoints[tid].setdefault(change_id, {})
            if checkpoint.checkpoint_id in cps:
                raise PersistenceSchemaError(
                    f"Checkpoint {checkpoint.checkpoint_id!r} already exists"
                )
            cps[checkpoint.checkpoint_id] = checkpoint
            return checkpoint

    def get_checkpoint(
        self, tenant_id: str, change_id: str, checkpoint_id: str
    ) -> Optional[CheckpointRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            return self._checkpoints.get(tid, {}).get(change_id, {}).get(checkpoint_id)

    def list_checkpoints(self, tenant_id: str, change_id: str) -> List[CheckpointRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            cps = list(self._checkpoints.get(tid, {}).get(change_id, {}).values())
            cps.sort(key=lambda c: c.sequence_number, reverse=True)
            return cps

    def get_latest_checkpoint(self, tenant_id: str, change_id: str) -> Optional[CheckpointRecord]:
        with self._lock:
            cps = self.list_checkpoints(tenant_id, change_id)
            return cps[0] if cps else None

    # ------------------------------------------------------------------------
    # Evidence Reference Operations
    # ------------------------------------------------------------------------

    def create_evidence_ref(
        self, tenant_id: str, change_id: str, ref: EvidenceRefRecord
    ) -> EvidenceRefRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if ref.tenant_id != tid or ref.change_id != change_id:
                raise TenantIsolationError(
                    "EvidenceRef tenant_id or change_id mismatch with operation path"
                )
            scan_for_secrets(ref.model_dump())
            if not self.get_change(tid, change_id):
                raise DocumentNotFoundError(
                    f"Parent change {change_id!r} not found in tenant {tid!r}"
                )

            refs = self._evidence_refs[tid].setdefault(change_id, {})
            if ref.evidence_id in refs:
                raise PersistenceSchemaError(
                    f"Evidence reference {ref.evidence_id!r} already exists"
                )
            refs[ref.evidence_id] = ref
            return ref

    def get_evidence_ref(
        self, tenant_id: str, change_id: str, evidence_id: str
    ) -> Optional[EvidenceRefRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            return self._evidence_refs.get(tid, {}).get(change_id, {}).get(evidence_id)

    def list_evidence_refs(self, tenant_id: str, change_id: str) -> List[EvidenceRefRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            refs = list(self._evidence_refs.get(tid, {}).get(change_id, {}).values())
            refs.sort(key=lambda r: r.collected_at)
            return refs

    # ------------------------------------------------------------------------
    # Approval Operations
    # ------------------------------------------------------------------------

    def create_approval(
        self, tenant_id: str, change_id: str, approval: ApprovalRecord
    ) -> ApprovalRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if approval.tenant_id != tid or approval.change_id != change_id:
                raise TenantIsolationError(
                    "Approval tenant_id or change_id mismatch with operation path"
                )
            scan_for_secrets(approval.model_dump())
            if not self.get_change(tid, change_id):
                raise DocumentNotFoundError(
                    f"Parent change {change_id!r} not found in tenant {tid!r}"
                )

            apps = self._approvals[tid].setdefault(change_id, {})
            if approval.card_id in apps:
                raise PersistenceSchemaError(f"Approval card {approval.card_id!r} already exists")
            apps[approval.card_id] = approval
            return approval

    def get_approval(
        self, tenant_id: str, change_id: str, card_id: str
    ) -> Optional[ApprovalRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            return self._approvals.get(tid, {}).get(change_id, {}).get(card_id)

    def list_approvals(
        self, tenant_id: str, change_id: str, status: Optional[ApprovalResolutionStatus] = None
    ) -> List[ApprovalRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            apps = list(self._approvals.get(tid, {}).get(change_id, {}).values())
            if status is not None:
                apps = [a for a in apps if a.resolution_status == status]
            apps.sort(key=lambda a: a.card_created_at, reverse=True)
            return apps

    def update_approval(
        self, tenant_id: str, change_id: str, approval: ApprovalRecord, expected_version: int
    ) -> ApprovalRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if approval.tenant_id != tid or approval.change_id != change_id:
                raise TenantIsolationError(
                    "Approval tenant_id or change_id mismatch with operation path"
                )
            scan_for_secrets(approval.model_dump())
            current = self.get_approval(tid, change_id, approval.card_id)
            if current is None:
                raise DocumentNotFoundError(f"Approval card {approval.card_id!r} not found")
            if current.version != expected_version:
                raise OptimisticConcurrencyError(
                    f"Version conflict on approval {approval.card_id!r}: expected {expected_version}, found {current.version}",
                    document_path=f"/tenants/{tid}/changes/{change_id}/approvals/{approval.card_id}",
                    expected_version=expected_version,
                    actual_version=current.version,
                )
            new_version = current.version + 1
            updated = approval.model_copy(
                update={"version": new_version, "updated_at": self._now()}
            )
            self._approvals[tid][change_id][approval.card_id] = updated
            return updated

    # ------------------------------------------------------------------------
    # Capability Passport Operations
    # ------------------------------------------------------------------------

    def create_passport(self, tenant_id: str, passport: PassportRecord) -> PassportRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if passport.tenant_id != tid:
                raise TenantIsolationError("Passport tenant_id mismatch with operation path")
            scan_for_secrets(passport.model_dump())
            pps = self._passports.setdefault(tid, {})
            if passport.passport_id in pps:
                raise PersistenceSchemaError(f"Passport {passport.passport_id!r} already exists")
            pps[passport.passport_id] = passport
            return passport

    def get_passport(self, tenant_id: str, passport_id: str) -> Optional[PassportRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            return self._passports.get(tid, {}).get(passport_id)

    def get_active_passport(
        self, tenant_id: str, agent_id: str, agent_revision: str
    ) -> Optional[PassportRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            now = self._now()
            for p in self._passports.get(tid, {}).values():
                if p.agent_id == agent_id and p.agent_revision == agent_revision:
                    if not p.is_revoked and p.expires_at > now:
                        return p
            return None

    def update_passport(
        self, tenant_id: str, passport: PassportRecord, expected_version: int
    ) -> PassportRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if passport.tenant_id != tid:
                raise TenantIsolationError("Passport tenant_id mismatch with operation path")
            scan_for_secrets(passport.model_dump())
            current = self.get_passport(tid, passport.passport_id)
            if current is None:
                raise DocumentNotFoundError(f"Passport {passport.passport_id!r} not found")
            if current.version != expected_version:
                raise OptimisticConcurrencyError(
                    f"Version conflict on passport {passport.passport_id!r}: expected {expected_version}, found {current.version}",
                    document_path=f"/tenants/{tid}/passports/{passport.passport_id}",
                    expected_version=expected_version,
                    actual_version=current.version,
                )
            new_version = current.version + 1
            updated = passport.model_copy(
                update={"version": new_version, "updated_at": self._now()}
            )
            self._passports[tid][passport.passport_id] = updated
            return updated

    # ------------------------------------------------------------------------
    # Idempotency Reservation Operations (Used by P-10.03)
    # ------------------------------------------------------------------------

    def create_idempotency_reservation(
        self, tenant_id: str, change_id: str, reservation: IdempotencyReservationRecord
    ) -> IdempotencyReservationRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if reservation.tenant_id != tid or reservation.change_id != change_id:
                raise TenantIsolationError(
                    "Reservation tenant_id or change_id mismatch with operation path"
                )
            scan_for_secrets(reservation.model_dump())
            if not self.get_change(tid, change_id):
                raise DocumentNotFoundError(
                    f"Parent change {change_id!r} not found in tenant {tid!r}"
                )

            res_map = self._idempotency_reservations[tid].setdefault(change_id, {})
            if reservation.reservation_id in res_map:
                raise PersistenceSchemaError(
                    f"Reservation {reservation.reservation_id!r} already exists"
                )
            res_map[reservation.reservation_id] = reservation
            return reservation

    def get_idempotency_reservation(
        self, tenant_id: str, change_id: str, reservation_id: str
    ) -> Optional[IdempotencyReservationRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            return (
                self._idempotency_reservations.get(tid, {}).get(change_id, {}).get(reservation_id)
            )

    def update_idempotency_reservation(
        self,
        tenant_id: str,
        change_id: str,
        reservation: IdempotencyReservationRecord,
        expected_version: int,
    ) -> IdempotencyReservationRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if reservation.tenant_id != tid or reservation.change_id != change_id:
                raise TenantIsolationError(
                    "Reservation tenant_id or change_id mismatch with operation path"
                )
            scan_for_secrets(reservation.model_dump())
            current = self.get_idempotency_reservation(tid, change_id, reservation.reservation_id)
            if current is None:
                raise DocumentNotFoundError(f"Reservation {reservation.reservation_id!r} not found")
            if current.version != expected_version:
                raise OptimisticConcurrencyError(
                    f"Version conflict on reservation {reservation.reservation_id!r}: expected {expected_version}, found {current.version}",
                    document_path=f"/tenants/{tid}/changes/{change_id}/idempotency_reservations/{reservation.reservation_id}",
                    expected_version=expected_version,
                    actual_version=current.version,
                )
            new_version = current.version + 1
            updated = reservation.model_copy(update={"version": new_version})
            self._idempotency_reservations[tid][change_id][reservation.reservation_id] = updated
            return updated

    # ------------------------------------------------------------------------
    # Teardown / Cascading Deletion (P-10.05)
    # ------------------------------------------------------------------------

    def delete_change_cascade(self, tenant_id: str, change_id: str) -> int:
        """Explicitly recursively delete a change document and all child subcollections."""
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            count = 0
            if tid in self._changes and change_id in self._changes[tid]:
                del self._changes[tid][change_id]
                count += 1
            if tid in self._tasks and change_id in self._tasks[tid]:
                count += len(self._tasks[tid][change_id])
                del self._tasks[tid][change_id]
            if tid in self._checkpoints and change_id in self._checkpoints[tid]:
                count += len(self._checkpoints[tid][change_id])
                del self._checkpoints[tid][change_id]
            if (
                tid in self._idempotency_reservations
                and change_id in self._idempotency_reservations[tid]
            ):
                count += len(self._idempotency_reservations[tid][change_id])
                del self._idempotency_reservations[tid][change_id]
            if tid in self._evidence_refs and change_id in self._evidence_refs[tid]:
                count += len(self._evidence_refs[tid][change_id])
                del self._evidence_refs[tid][change_id]
            if tid in self._approvals and change_id in self._approvals[tid]:
                count += len(self._approvals[tid][change_id])
                del self._approvals[tid][change_id]
            return count

    def delete_tenant_cascade(self, tenant_id: str) -> int:
        """Explicitly recursively delete all documents under /tenants/{tenant_id}."""
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            count = 0
            # Delete all changes and their subcollections
            if tid in self._changes:
                change_ids = list(self._changes[tid].keys())
                for cid in change_ids:
                    count += self.delete_change_cascade(tid, cid)
            # Delete passports
            if tid in self._passports:
                count += len(self._passports[tid])
                del self._passports[tid]
            # Delete tenant root
            if tid in self._tenants:
                del self._tenants[tid]
                count += 1
            # Clean empty maps
            self._changes.pop(tid, None)
            self._tasks.pop(tid, None)
            self._checkpoints.pop(tid, None)
            self._idempotency_reservations.pop(tid, None)
            self._evidence_refs.pop(tid, None)
            self._approvals.pop(tid, None)
            return count
