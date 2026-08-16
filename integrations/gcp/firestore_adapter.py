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

    def _atomic_cas_update(
        self,
        doc_ref: Any,
        expected_version: int,
        candidate_dict: Dict[str, Any],
        document_path: str,
        record_class: Any,
    ) -> Any:
        """Perform atomic read-and-CAS update using Firestore transaction semantics."""
        now = self._now()

        def _step(txn: Any) -> Dict[str, Any]:
            if hasattr(doc_ref, "get"):
                try:
                    snapshot = doc_ref.get(transaction=txn)
                except TypeError:
                    snapshot = doc_ref.get()
            elif hasattr(txn, "get"):
                snapshot = txn.get(doc_ref)
            else:
                raise RuntimeError("Invalid Firestore transaction/doc_ref interface")

            if not snapshot.exists:
                raise DocumentNotFoundError(
                    f"Document at {document_path} not found",
                    document_path=document_path,
                )

            current_data = snapshot.to_dict() or {}
            actual_version = current_data.get("version", 0)
            if actual_version != expected_version:
                raise OptimisticConcurrencyError(
                    f"Version conflict on {document_path}: "
                    f"expected {expected_version}, found {actual_version}",
                    document_path=document_path,
                    expected_version=expected_version,
                    actual_version=actual_version,
                )

            new_version = actual_version + 1
            updated_dict = dict(candidate_dict)
            updated_dict["version"] = new_version
            if "updated_at" in updated_dict:
                updated_dict["updated_at"] = now

            fs_data = _to_firestore_dict(updated_dict)
            if hasattr(txn, "set"):
                txn.set(doc_ref, fs_data)
            elif hasattr(doc_ref, "set"):
                doc_ref.set(fs_data)
            return updated_dict

        if hasattr(self._db, "transaction"):
            transaction = self._db.transaction()
            try:
                from google.cloud import firestore as gcp_firestore  # type: ignore[import-untyped]

                @gcp_firestore.transactional
                def _runner(txn: Any) -> Dict[str, Any]:
                    return _step(txn)

                result_dict = _runner(transaction)
            except Exception:
                result_dict = _step(transaction)
                if hasattr(transaction, "commit"):
                    transaction.commit()
        else:
            doc = doc_ref.get()
            if not doc.exists:
                raise DocumentNotFoundError(
                    f"Document at {document_path} not found",
                    document_path=document_path,
                )
            current_data = doc.to_dict() or {}
            actual_version = current_data.get("version", 0)
            if actual_version != expected_version:
                raise OptimisticConcurrencyError(
                    f"Version conflict on {document_path}: "
                    f"expected {expected_version}, found {actual_version}",
                    document_path=document_path,
                    expected_version=expected_version,
                    actual_version=actual_version,
                )
            new_version = actual_version + 1
            result_dict = dict(candidate_dict)
            result_dict["version"] = new_version
            if "updated_at" in result_dict:
                result_dict["updated_at"] = now
            doc_ref.set(_to_firestore_dict(result_dict))

        return record_class(**_from_firestore_dict(result_dict))

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
        doc_path = f"/tenants/{tid}/changes/{change.change_id}"
        return self._atomic_cas_update(
            doc_ref=doc_ref,
            expected_version=expected_version,
            candidate_dict=change.model_dump(),
            document_path=doc_path,
            record_class=ChangeRecord,
        )

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
        doc_path = f"/tenants/{tid}/changes/{change_id}/tasks/{task.task_id}"
        return self._atomic_cas_update(
            doc_ref=doc_ref,
            expected_version=expected_version,
            candidate_dict=task.model_dump(),
            document_path=doc_path,
            record_class=TaskRecord,
        )

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
        doc_path = f"/tenants/{tid}/changes/{change_id}/approvals/{approval.card_id}"
        return self._atomic_cas_update(
            doc_ref=doc_ref,
            expected_version=expected_version,
            candidate_dict=approval.model_dump(),
            document_path=doc_path,
            record_class=ApprovalRecord,
        )

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
        doc_path = f"/tenants/{tid}/passports/{passport.passport_id}"
        return self._atomic_cas_update(
            doc_ref=doc_ref,
            expected_version=expected_version,
            candidate_dict=passport.model_dump(),
            document_path=doc_path,
            record_class=PassportRecord,
        )

    # ------------------------------------------------------------------------
    # Idempotency Reservation Operations (P-10.03)
    # ------------------------------------------------------------------------

    def create_idempotency_reservation(
        self, tenant_id: str, change_id: str, reservation: IdempotencyReservationRecord
    ) -> IdempotencyReservationRecord:
        tid = validate_tenant_id(tenant_id)
        if reservation.tenant_id != tid or reservation.change_id != change_id:
            raise TenantIsolationError(
                "Reservation tenant_id or change_id mismatch with operation path"
            )
        scan_for_secrets(reservation.model_dump())
        if not self.get_change(tid, change_id):
            raise DocumentNotFoundError(f"Parent change {change_id!r} not found in tenant {tid!r}")

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("idempotency_reservations")
            .document(reservation.reservation_id)
        )
        if doc_ref.get().exists:
            raise PersistenceSchemaError(
                f"Reservation {reservation.reservation_id!r} already exists"
            )
        doc_ref.set(_to_firestore_dict(reservation.model_dump()))
        return reservation

    def get_idempotency_reservation(
        self, tenant_id: str, change_id: str, reservation_id: str
    ) -> Optional[IdempotencyReservationRecord]:
        tid = validate_tenant_id(tenant_id)
        doc = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("idempotency_reservations")
            .document(reservation_id)
            .get()
        )
        if not doc.exists:
            return None
        return IdempotencyReservationRecord(**_from_firestore_dict(doc.to_dict()))

    def update_idempotency_reservation(
        self,
        tenant_id: str,
        change_id: str,
        reservation: IdempotencyReservationRecord,
        expected_version: int,
    ) -> IdempotencyReservationRecord:
        tid = validate_tenant_id(tenant_id)
        if reservation.tenant_id != tid or reservation.change_id != change_id:
            raise TenantIsolationError(
                "Reservation tenant_id or change_id mismatch with operation path"
            )
        scan_for_secrets(reservation.model_dump())

        doc_ref = (
            self._db.collection("tenants")
            .document(tid)
            .collection("changes")
            .document(change_id)
            .collection("idempotency_reservations")
            .document(reservation.reservation_id)
        )
        doc_path = (
            f"/tenants/{tid}/changes/{change_id}/idempotency_reservations/"
            f"{reservation.reservation_id}"
        )
        return self._atomic_cas_update(
            doc_ref=doc_ref,
            expected_version=expected_version,
            candidate_dict=reservation.model_dump(),
            document_path=doc_path,
            record_class=IdempotencyReservationRecord,
        )

    # ------------------------------------------------------------------------
    # Teardown / Cascading Deletion (P-10.05)
    # ------------------------------------------------------------------------

    def delete_change_cascade(self, tenant_id: str, change_id: str) -> int:
        """Explicitly recursively delete a change document and all child subcollections."""
        tid = validate_tenant_id(tenant_id)
        change_ref = (
            self._db.collection("tenants").document(tid).collection("changes").document(change_id)
        )
        count = 0
        for subcol_name in [
            "tasks",
            "checkpoints",
            "idempotency_reservations",
            "evidence_refs",
            "approvals",
        ]:
            sub_docs = change_ref.collection(subcol_name).stream()
            for doc in sub_docs:
                doc.reference.delete()
                count += 1
        if change_ref.get().exists:
            change_ref.delete()
            count += 1
        return count

    def delete_tenant_cascade(self, tenant_id: str) -> int:
        """Explicitly recursively delete all documents under /tenants/{tenant_id}."""
        tid = validate_tenant_id(tenant_id)
        tenant_ref = self._db.collection("tenants").document(tid)
        count = 0
        changes = tenant_ref.collection("changes").stream()
        for chg in changes:
            count += self.delete_change_cascade(tid, chg.id)
        passports = tenant_ref.collection("passports").stream()
        for p in passports:
            p.reference.delete()
            count += 1
        if tenant_ref.get().exists:
            tenant_ref.delete()
            count += 1
        return count
