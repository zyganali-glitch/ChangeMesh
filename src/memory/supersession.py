"""ChangeMesh contradiction and supersession tracking manager.

P-11.03: Tracks memory contradictions and supersessions without deleting
historical audit records, enforcing causal traceability and fail-closed
conflict resolution.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, ConfigDict

from domain.contracts.memory import MemoryRecord, MemoryTrustStatus


class ContradictionDetectionResult(BaseModel):
    """Result of evaluating contradiction between memory records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_conflict: bool
    conflicting_record_ids: Tuple[str, ...] = ()
    superseded_record_ids: Tuple[str, ...] = ()
    is_ambiguous: bool = False
    resolution_rationale: Optional[str] = None


class MemorySupersessionManager:
    """Manages contradiction linking, supersession, and immutable history preservation."""

    @classmethod
    def link_supersession(
        cls,
        existing_record: MemoryRecord,
        new_record: MemoryRecord,
        rationale: str = "Superseded by newer verified architectural decision",
    ) -> Tuple[MemoryRecord, MemoryRecord]:
        """Supersede existing_record with new_record without deleting existing_record.

        Returns:
            (updated_existing_record, finalized_new_record)
        """
        # Update existing record: append new_record.memory_id to contradiction_ids
        updated_contradictions = set(existing_record.contradiction_ids)
        updated_contradictions.add(new_record.memory_id)

        # Existing record is demoted to UNTRUSTED (superseded)
        updated_existing = existing_record.model_copy(
            update={
                "contradiction_ids": tuple(sorted(list(updated_contradictions))),
                "trust_status": MemoryTrustStatus.UNTRUSTED,
            }
        )

        # New record keeps its trust properties and references existing record
        new_contradictions = set(new_record.contradiction_ids)
        new_contradictions.add(existing_record.memory_id)
        finalized_new = new_record.model_copy(
            update={
                "contradiction_ids": tuple(sorted(list(new_contradictions))),
            }
        )

        return updated_existing, finalized_new

    @classmethod
    def evaluate_conflict(
        cls,
        candidate: MemoryRecord,
        existing_records: List[MemoryRecord],
    ) -> ContradictionDetectionResult:
        """Detect direct contradictions in scope and content against active memories."""
        conflicts: List[str] = []
        superseded: List[str] = []

        for record in existing_records:
            if record.memory_id == candidate.memory_id:
                continue

            # Same scope & same topic heuristic
            if record.scope == candidate.scope:
                # If candidate is explicitly marked as a replacement for an older record
                if record.memory_id in candidate.contradiction_ids:
                    superseded.append(record.memory_id)
                elif (
                    candidate.capture_timestamp > record.capture_timestamp
                    and record.trust_status != MemoryTrustStatus.QUARANTINED
                ):
                    # Potential contradiction if content states conflicting facts
                    if cls._has_semantic_conflict(candidate.content, record.content):
                        conflicts.append(record.memory_id)

        if conflicts and not superseded:
            # Ambiguous conflict requiring deterministic resolution
            return ContradictionDetectionResult(
                has_conflict=True,
                conflicting_record_ids=tuple(conflicts),
                is_ambiguous=True,
                resolution_rationale="Ambiguous semantic conflict detected between active memory records",
            )

        if superseded:
            return ContradictionDetectionResult(
                has_conflict=True,
                superseded_record_ids=tuple(superseded),
                is_ambiguous=False,
                resolution_rationale=f"Candidate supersedes {len(superseded)} historical memory record(s)",
            )

        return ContradictionDetectionResult(has_conflict=False)

    @staticmethod
    def _has_semantic_conflict(text_a: str, text_b: str) -> bool:
        """Deterministic check for explicit negation or opposing version constraints."""
        a_lower = text_a.lower()
        b_lower = text_b.lower()

        # Check opposing directives (e.g. "requires postgres 15" vs "requires postgres 16")
        for key in ["postgres", "python", "kubernetes", "node", "redis", "schema_version"]:
            if key in a_lower and key in b_lower and a_lower != b_lower:
                return True
        return False
