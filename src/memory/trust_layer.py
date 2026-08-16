"""ChangeMesh epistemic memory trust evaluator.

P-11.01 & P-11.02: Evaluates memory records according to deterministic trust policy,
enforcing strict boundary between retrieval relevance and epistemic authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from domain.contracts.conventions import UtcDateTime
from domain.contracts.memory import MemoryRecord, MemoryTrustStatus

CANONICAL_SCHEMA_VERSION = "1.0.0"


class EpistemicTrustClass(str, Enum):
    """Deterministic trust policy classification."""

    ACCEPTED_TRUSTED = "ACCEPTED_TRUSTED"
    UNTRUSTED_CONTEXT = "UNTRUSTED_CONTEXT"
    STALE_EXPIRED = "STALE_EXPIRED"
    CONTRADICTED = "CONTRADICTED"
    QUARANTINED = "QUARANTINED"


class EpistemicTrustEvaluation(BaseModel):
    """Evaluation outcome for a candidate memory record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    memory_id: str
    trust_class: EpistemicTrustClass
    is_usable_as_context: bool
    is_authoritative: bool = False  # Always False: Memory never has authority to execute
    freshness_score: float  # [0.0, 1.0]
    retrieval_relevance_score: float  # [0.0, 1.0]
    evaluation_reason: str
    evaluated_at: UtcDateTime


class MemoryTrustEvaluator:
    """Evaluates memory records against deterministic trust rules."""

    @classmethod
    def evaluate(
        cls,
        record: MemoryRecord,
        retrieval_relevance: float = 1.0,
        now: Optional[datetime] = None,
    ) -> EpistemicTrustEvaluation:
        """Evaluate epistemic trust of a memory record."""
        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Quarantined Check (Fail Closed Highest Priority)
        if record.is_quarantined or record.trust_status == MemoryTrustStatus.QUARANTINED:
            reason = record.quarantine_reason or "unspecified reason"
            return EpistemicTrustEvaluation(
                memory_id=record.memory_id,
                trust_class=EpistemicTrustClass.QUARANTINED,
                is_usable_as_context=False,
                is_authoritative=False,
                freshness_score=0.0,
                retrieval_relevance_score=retrieval_relevance,
                evaluation_reason=f"Memory is quarantined: {reason}",
                evaluated_at=now,
            )

        # 2. Expiration Check
        if record.expiry_timestamp <= now:
            return EpistemicTrustEvaluation(
                memory_id=record.memory_id,
                trust_class=EpistemicTrustClass.STALE_EXPIRED,
                is_usable_as_context=False,
                is_authoritative=False,
                freshness_score=0.0,
                retrieval_relevance_score=retrieval_relevance,
                evaluation_reason=f"Memory expired at {record.expiry_timestamp.isoformat()}",
                evaluated_at=now,
            )

        # 3. Contradiction Check
        if record.contradiction_ids:
            return EpistemicTrustEvaluation(
                memory_id=record.memory_id,
                trust_class=EpistemicTrustClass.CONTRADICTED,
                is_usable_as_context=False,
                is_authoritative=False,
                freshness_score=0.0,
                retrieval_relevance_score=retrieval_relevance,
                evaluation_reason=(
                    f"Memory has {len(record.contradiction_ids)} contradiction reference(s)"
                ),
                evaluated_at=now,
            )

        # Compute Freshness Score
        total_lifespan = (record.expiry_timestamp - record.capture_timestamp).total_seconds()
        elapsed = (now - record.capture_timestamp).total_seconds()
        if total_lifespan > 0 and elapsed >= 0:
            freshness = max(0.0, min(1.0, 1.0 - (elapsed / total_lifespan)))
        else:
            freshness = 0.0

        # 4. Explicit Deterministic Evidence Verification
        if record.trust_status == MemoryTrustStatus.TRUSTED and record.trust_evidence_ids:
            return EpistemicTrustEvaluation(
                memory_id=record.memory_id,
                trust_class=EpistemicTrustClass.ACCEPTED_TRUSTED,
                is_usable_as_context=True,
                is_authoritative=False,  # Memory provides context, not machine authority
                freshness_score=round(freshness, 4),
                retrieval_relevance_score=retrieval_relevance,
                evaluation_reason=(
                    f"Verified with {len(record.trust_evidence_ids)} trust evidence ref(s)"
                ),
                evaluated_at=now,
            )

        # 5. Untrusted Context (Default)
        return EpistemicTrustEvaluation(
            memory_id=record.memory_id,
            trust_class=EpistemicTrustClass.UNTRUSTED_CONTEXT,
            is_usable_as_context=True,  # Usable as advisory context only
            is_authoritative=False,
            freshness_score=round(freshness, 4),
            retrieval_relevance_score=retrieval_relevance,
            evaluation_reason="Unverified provenance; advisory context only",
            evaluated_at=now,
        )
