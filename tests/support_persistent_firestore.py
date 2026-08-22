"""ChangeMesh test support: deterministic file-backed Firestore client double.

Provides real filesystem-persisted document storage for multi-process and
fresh-instance restart tests, allowing GoogleFirestoreSagaRepository and
SagaCheckpointManager to execute against real disk storage without network
or live GCP dependencies.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _json_serialize_helper(obj: Any) -> Any:
    """JSON serializer helper for datetimes, tuples, and enums."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (tuple, set)):
        return list(obj)
    if hasattr(obj, "value"):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class FileBackedFirestoreSnapshot:
    """Document snapshot loaded from or representing a file on disk."""

    def __init__(
        self,
        exists: bool,
        data: Optional[Dict[str, Any]] = None,
        doc_id: str = "",
        reference: Any = None,
    ) -> None:
        self.exists = exists
        self._data = data or {}
        self.id = doc_id
        self.reference = reference

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


class FileBackedFirestoreDocRef:
    """Document reference addressing a specific file in the storage directory."""

    def __init__(self, key: str, root_dir: Path) -> None:
        self._key = key.strip("/")
        self.id = self._key.split("/")[-1]
        self._root_dir = root_dir
        encoded_name = urllib.parse.quote(self._key, safe="") + ".json"
        self._file_path = root_dir / encoded_name

    @property
    def exists(self) -> bool:
        return self._file_path.exists()

    def get(self, transaction: Optional[Any] = None) -> FileBackedFirestoreSnapshot:
        if transaction is not None:
            return transaction.get(self)
        if self._file_path.exists():
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return FileBackedFirestoreSnapshot(
                exists=True,
                data=data,
                doc_id=self.id,
                reference=self,
            )
        return FileBackedFirestoreSnapshot(
            exists=False,
            doc_id=self.id,
            reference=self,
        )

    def set(self, data: Dict[str, Any]) -> None:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self._file_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, default=_json_serialize_helper, indent=2)
        tmp_path.replace(self._file_path)

    def delete(self) -> None:
        if self._file_path.exists():
            self._file_path.unlink()

    def collection(self, name: str) -> FileBackedFirestoreCollection:
        return FileBackedFirestoreCollection(f"{self._key}/{name}", self._root_dir)


class FileBackedFirestoreQuery:
    """Query over files stored on disk."""

    def __init__(
        self,
        path: str,
        root_dir: Path,
        filters: Optional[List[Tuple[str, str, Any]]] = None,
    ) -> None:
        self._path = path.strip("/")
        self._root_dir = root_dir
        self._filters = filters or []

    def where(self, field: str, op: str, value: Any) -> FileBackedFirestoreQuery:
        return FileBackedFirestoreQuery(
            self._path,
            self._root_dir,
            self._filters + [(field, op, value)],
        )

    def stream(self) -> List[FileBackedFirestoreSnapshot]:
        results: List[FileBackedFirestoreSnapshot] = []
        if not self._root_dir.exists():
            return results

        prefix = self._path + "/"
        for file_path in sorted(self._root_dir.glob("*.json")):
            unquoted_key = urllib.parse.unquote(file_path.stem)
            if unquoted_key.startswith(prefix):
                remainder = unquoted_key[len(prefix) :]
                if "/" not in remainder:  # Direct child doc only
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    match = True
                    for field, op, val in self._filters:
                        if op == "==":
                            actual = data.get(field)
                            expected = val.value if hasattr(val, "value") else val
                            if isinstance(expected, datetime):
                                expected = expected.isoformat()
                            if actual != expected:
                                match = False
                                break
                    if match:
                        doc_id = remainder
                        ref = FileBackedFirestoreDocRef(unquoted_key, self._root_dir)
                        results.append(
                            FileBackedFirestoreSnapshot(
                                exists=True,
                                data=data,
                                doc_id=doc_id,
                                reference=ref,
                            )
                        )
        return results


class FileBackedFirestoreCollection:
    """Collection representation resolving child documents in storage directory."""

    def __init__(self, path: str, root_dir: Path) -> None:
        self._path = path.strip("/")
        self._root_dir = root_dir

    def document(self, doc_id: str) -> FileBackedFirestoreDocRef:
        return FileBackedFirestoreDocRef(f"{self._path}/{doc_id}", self._root_dir)

    def where(self, field: str, op: str, value: Any) -> FileBackedFirestoreQuery:
        return FileBackedFirestoreQuery(self._path, self._root_dir, [(field, op, value)])

    def stream(self) -> List[FileBackedFirestoreSnapshot]:
        return FileBackedFirestoreQuery(self._path, self._root_dir, []).stream()


class FileBackedFirestoreTransaction:
    """Transaction implementation providing optimistic version checking on disk."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._read_versions: Dict[str, Any] = {}
        self._writes: Dict[str, Tuple[FileBackedFirestoreDocRef, Dict[str, Any]]] = {}

    def get(self, doc_ref: FileBackedFirestoreDocRef) -> FileBackedFirestoreSnapshot:
        key = doc_ref._key
        file_path = doc_ref._file_path
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._read_versions[key] = data.get("version", 0)
            return FileBackedFirestoreSnapshot(
                exists=True,
                data=data,
                doc_id=doc_ref.id,
                reference=doc_ref,
            )
        self._read_versions[key] = None
        return FileBackedFirestoreSnapshot(
            exists=False,
            doc_id=doc_ref.id,
            reference=doc_ref,
        )

    def set(self, doc_ref: FileBackedFirestoreDocRef, data: Dict[str, Any]) -> None:
        self._writes[doc_ref._key] = (doc_ref, data)

    def commit(self) -> None:
        # Optimistic concurrency check
        for key, read_ver in self._read_versions.items():
            doc_ref = FileBackedFirestoreDocRef(key, self._root_dir)
            current_data = None
            if doc_ref._file_path.exists():
                with open(doc_ref._file_path, "r", encoding="utf-8") as f:
                    current_data = json.load(f)
            current_ver = current_data.get("version", 0) if current_data else None
            if current_ver != read_ver:
                raise RuntimeError(
                    f"Transactional collision on {key}: "
                    f"expected version {read_ver}, found {current_ver}"
                )

        # Write updates atomically
        for _, (doc_ref, write_data) in self._writes.items():
            doc_ref.set(write_data)


class FileBackedFirestoreClient:
    """Firestore client duck-type using local filesystem for persistent testing."""

    def __init__(self, storage_dir: str | Path) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def collection(self, name: str) -> FileBackedFirestoreCollection:
        return FileBackedFirestoreCollection(name, self.storage_dir)

    def transaction(self) -> FileBackedFirestoreTransaction:
        return FileBackedFirestoreTransaction(self.storage_dir)
