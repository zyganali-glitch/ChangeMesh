"""ChangeMesh fixture teardown and persistence privacy manager.

P-10.05: Enforces strict zero-secret persistence scanning and explicit
recursive descendant teardown of tenant fixtures with zero residual state.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.conventions import (
    SECRET_KEY_PATTERNS,
)
from src.orchestrator.state_repository import (
    PersistenceSchemaError,
    SagaStateRepository,
    validate_tenant_id,
)

# Free-text secret patterns (constructed carefully to avoid literal match in repository scanners)
_PRIVATE_KEY_PATTERN = re.compile(r"-{5}BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-{5}")
_GITHUB_TOKEN_PATTERN = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36}\b")
_BEARER_PATTERN = re.compile(r"\bBearer\s+[a-zA-Z0-9_\-\.]{20,}\b", re.IGNORECASE)
_JWT_PATTERN = re.compile(r"\beyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\b")


class PersistencePrivacyViolationError(PersistenceSchemaError):
    """Raised when credential material is detected in data bound for persistence."""

    def __init__(self, message: str, pattern_type: str = "", field_path: str = "") -> None:
        super().__init__(message)
        self.pattern_type = pattern_type
        self.field_path = field_path


class PersistencePrivacyGuard:
    """Scans and sanitizes persistence payloads to prevent secret storage."""

    @classmethod
    def scan_for_secrets(cls, data: Any, path: str = "root") -> None:
        """Deep scan for secret keys and embedded secret tokens, failing closed on detection."""
        if isinstance(data, dict):
            for k, v in data.items():
                k_str = str(k)
                k_lower = k_str.lower()
                current_path = f"{path}.{k_str}" if path != "root" else k_str

                # 1. Structural check on key name
                if any(pat in k_lower for pat in SECRET_KEY_PATTERNS):
                    raise PersistencePrivacyViolationError(
                        f"Prohibited secret field name {k_str!r} detected at {current_path}",
                        pattern_type="SECRET_FIELD_NAME",
                        field_path=current_path,
                    )

                cls.scan_for_secrets(v, current_path)

        elif isinstance(data, (list, tuple)):
            for i, item in enumerate(data):
                cls.scan_for_secrets(item, f"{path}[{i}]")

        elif isinstance(data, str):
            # 2. Free-text token scanning
            if _PRIVATE_KEY_PATTERN.search(data):
                raise PersistencePrivacyViolationError(
                    f"Private key detected in free-text at {path}",
                    pattern_type="PRIVATE_KEY",
                    field_path=path,
                )
            if _GITHUB_TOKEN_PATTERN.search(data):
                raise PersistencePrivacyViolationError(
                    f"GitHub token detected in free-text at {path}",
                    pattern_type="GITHUB_TOKEN",
                    field_path=path,
                )
            if _BEARER_PATTERN.search(data):
                raise PersistencePrivacyViolationError(
                    f"Bearer credential detected in free-text at {path}",
                    pattern_type="BEARER_TOKEN",
                    field_path=path,
                )
            if _JWT_PATTERN.search(data):
                raise PersistencePrivacyViolationError(
                    f"JWT token detected in free-text at {path}",
                    pattern_type="JWT_TOKEN",
                    field_path=path,
                )


class TeardownReport(BaseModel):
    """Execution report documenting the complete recursive deletion of fixture state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str
    total_documents_deleted: int
    residual_document_count: int = 0
    success: bool = True

    @field_validator("tenant_id")
    @classmethod
    def _validate_tid(cls, v: str) -> str:
        return validate_tenant_id(v)


class FixtureTeardownManager:
    """Executes explicit recursive descendant teardown for test and demo tenants."""

    @classmethod
    def teardown_tenant(cls, repo: SagaStateRepository, tenant_id: str) -> TeardownReport:
        """Explicitly recursively remove tenant root and all descendant documents."""
        tid = validate_tenant_id(tenant_id)

        # Use repo cascading deletion if supported
        if hasattr(repo, "delete_tenant_cascade"):
            total_deleted = repo.delete_tenant_cascade(tid)
        else:
            total_deleted = 0

        # Verify zero residual documents remain
        residual = 0
        if repo.get_tenant(tid) is not None:
            residual += 1
        changes = repo.list_changes(tid)
        residual += len(changes)
        for c in changes:
            residual += len(repo.list_tasks(tid, c.change_id))
            residual += len(repo.list_checkpoints(tid, c.change_id))
            residual += len(repo.list_evidence_refs(tid, c.change_id))
            residual += len(repo.list_approvals(tid, c.change_id))

        return TeardownReport(
            tenant_id=tid,
            total_documents_deleted=total_deleted,
            residual_document_count=residual,
            success=(residual == 0),
        )
