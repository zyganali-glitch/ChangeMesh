"""ChangeMesh memory bank interface and in-memory local adapter.

P-11.05: Manages scoped memory indexing, trust evaluation, and safe retrieval.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict

from domain.contracts.memory import MemoryRecord, MemoryTrustStatus
from src.memory.quarantine import MemoryQuarantineEngine
from src.memory.trust_layer import EpistemicTrustClass, EpistemicTrustEvaluation, MemoryTrustEvaluator
from src.orchestrator.state_repository import TenantIsolationError, validate_tenant_id


class MemorySearchResult(BaseModel):
    """Memory record bundled with its deterministic trust evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record: MemoryRecord
    evaluation: EpistemicTrustEvaluation


class MemoryBank(ABC):
    """Abstract interface for ChangeMesh Memory Bank."""

    @abstractmethod
    def store_memory(self, tenant_id: str, record: MemoryRecord) -> MemoryRecord:
        """Store candidate memory record, applying quarantine scanning on ingest."""
        pass

    @abstractmethod
    def get_memory(self, tenant_id: str, memory_id: str) -> Optional[MemoryRecord]:
        """Fetch memory record by ID."""
        pass

    @abstractmethod
    def search_memories(
        self,
        tenant_id: str,
        scope: Optional[str] = None,
        query: Optional[str] = None,
        include_quarantined: bool = False,
    ) -> List[MemorySearchResult]:
        """Search memories with trust evaluation."""
        pass


class InMemoryMemoryBank(MemoryBank):
    """Thread-safe in-memory test double and local adapter for ChangeMesh Memory Bank."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._memories: Dict[str, Dict[str, MemoryRecord]] = {}  # tenant_id -> memory_id -> record

    def store_memory(self, tenant_id: str, record: MemoryRecord) -> MemoryRecord:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            # Scan for prompt injections and quarantine if hostile
            sanitized = MemoryQuarantineEngine.quarantine_if_hostile(record)
            tenant_store = self._memories.setdefault(tid, {})
            tenant_store[sanitized.memory_id] = sanitized
            return sanitized

    def get_memory(self, tenant_id: str, memory_id: str) -> Optional[MemoryRecord]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            return self._memories.get(tid, {}).get(memory_id)

    def search_memories(
        self,
        tenant_id: str,
        scope: Optional[str] = None,
        query: Optional[str] = None,
        include_quarantined: bool = False,
        now: Optional[datetime] = None,
    ) -> List[MemorySearchResult]:
        with self._lock:
            tid = validate_tenant_id(tenant_id)
            if now is None:
                now = datetime.now(timezone.utc)

            tenant_store = self._memories.get(tid, {})
            results: List[MemorySearchResult] = []

            for record in tenant_store.values():
                if scope and record.scope != scope:
                    continue

                if query:
                    # Keyword matching
                    q_words = query.lower().split()
                    c_lower = record.content.lower()
                    if not any(w in c_lower for w in q_words):
                        continue

                # Compute keyword match relevance
                rel_score = 1.0

                evaluation = MemoryTrustEvaluator.evaluate(record, retrieval_relevance=rel_score, now=now)

                if not include_quarantined and evaluation.trust_class == EpistemicTrustClass.QUARANTINED:
                    continue

                results.append(MemorySearchResult(record=record, evaluation=evaluation))

            # Sort by freshness DESC, then relevance DESC
            results.sort(key=lambda r: (r.evaluation.freshness_score, r.evaluation.retrieval_relevance_score), reverse=True)
            return results
