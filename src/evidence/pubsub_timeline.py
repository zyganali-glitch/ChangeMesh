"""ChangeMesh causal event timeline for dashboard and change passport.

P-09.05 / Donor component: CCT-FLIGHT-001 (Clean-room reimplemented).

Records distributed causal event chains, validates DAG acyclicity, computes
deterministic causal ordering (independent of wall-clock skew and arrival sequence),
enforces secret scanning and structural redaction, and produces tamper-protected digests
for dashboard/passport audit.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.conventions import (
    UtcDateTime,
    canonical_json_bytes,
    format_utc_timestamp,
    redact_mapping,
    sha256_hex,
)
from domain.contracts.event_envelope import EventEnvelope
from events.wire import scan_payload_for_secrets

TIMELINE_SCHEMA_VERSION = "1.0.0"
ALLOWED_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "change_id", "total_events", "timeline_digest", "events"}
)


class CausalTimelineEntry(BaseModel):
    """Immutable entry in a ChangeMesh causal event timeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = TIMELINE_SCHEMA_VERSION
    event_id: str
    change_id: str
    correlation_id: str
    causation_id: Optional[str] = None
    idempotency_key: str
    topic_id: str
    producer_id: str
    producer_revision: str
    producer_role: Optional[str] = None
    timestamp: UtcDateTime
    depth: int = 0
    transport: str
    payload_summary: Mapping[str, Any]

    @field_validator(
        "schema_version",
        "event_id",
        "change_id",
        "correlation_id",
        "idempotency_key",
        "topic_id",
        "producer_id",
        "producer_revision",
        "transport",
    )
    @classmethod
    def _must_not_be_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v.strip()

    @field_validator("depth")
    @classmethod
    def _depth_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"depth must be non-negative, got {v}")
        return v

    @model_validator(mode="before")
    @classmethod
    def _redact_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_payload = data.get("payload_summary", {})
            if isinstance(raw_payload, dict):
                data["payload_summary"] = redact_mapping(raw_payload)
        return data


class CausalEventTimeline:
    """Causal event timeline manager with DAG ordering, cycle detection, and digest hashing."""

    def __init__(self, change_id: str) -> None:
        if not change_id or not change_id.strip():
            raise ValueError("change_id must not be blank")
        self.change_id = change_id.strip()
        self._entries_by_id: Dict[str, CausalTimelineEntry] = {}

    @property
    def total_events(self) -> int:
        return len(self._entries_by_id)

    def record_event(
        self,
        envelope: EventEnvelope,
        topic_id: str,
        payload: Optional[Mapping[str, Any]] = None,
        transport: str = "LOCAL",
    ) -> CausalTimelineEntry:
        """Record an event envelope into the causal timeline.

        Arrival order is not causal order: child events may be ingested before their
        causal parents. Unresolved references are preserved during ingest and validated
        at causal projection, export, and digest time.
        """
        if envelope.change_id != self.change_id:
            raise ValueError(
                f"Envelope change_id {envelope.change_id!r} does not match "
                f"timeline change_id {self.change_id!r}"
            )

        if payload is not None:
            scan_payload_for_secrets(payload)

        # Idempotent replay vs event_id conflict check
        if envelope.event_id in self._entries_by_id:
            existing = self._entries_by_id[envelope.event_id]
            redacted_payload = redact_mapping(payload) if payload is not None else {}
            if (
                existing.change_id == envelope.change_id
                and existing.correlation_id == envelope.correlation_id
                and existing.causation_id == envelope.causation_id
                and existing.idempotency_key == envelope.idempotency_key
                and existing.topic_id == topic_id.strip()
                and existing.producer_id == envelope.producer_id
                and existing.producer_revision == envelope.producer_revision
                and existing.producer_role == envelope.producer_role
                and existing.timestamp == envelope.timestamp
                and existing.transport == transport.strip()
                and dict(existing.payload_summary) == dict(redacted_payload)
            ):
                return existing  # Exact duplicate -> idempotent

            raise ValueError(
                f"Event ID conflict for {envelope.event_id!r}: content mismatch with existing entry"
            )

        # Idempotency collision check: same (change_id, idempotency_key) with different event_id
        for e in self._entries_by_id.values():
            if e.idempotency_key == envelope.idempotency_key and e.event_id != envelope.event_id:
                raise ValueError(
                    f"Idempotency collision for key {envelope.idempotency_key!r}: "
                    f"already used by event {e.event_id!r}"
                )

        # Compute initial depth if parent is already known, otherwise 0
        depth = 0
        if envelope.causation_id and envelope.causation_id in self._entries_by_id:
            depth = self._entries_by_id[envelope.causation_id].depth + 1

        entry = CausalTimelineEntry(
            schema_version=TIMELINE_SCHEMA_VERSION,
            event_id=envelope.event_id,
            change_id=envelope.change_id,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            idempotency_key=envelope.idempotency_key,
            topic_id=topic_id,
            producer_id=envelope.producer_id,
            producer_revision=envelope.producer_revision,
            producer_role=envelope.producer_role,
            timestamp=envelope.timestamp,
            depth=depth,
            transport=transport,
            payload_summary=payload or {},
        )

        self._entries_by_id[entry.event_id] = entry
        return entry

    def get_causally_ordered_entries(self) -> Sequence[CausalTimelineEntry]:
        """Return all entries sorted in topological causal order.

        Guarantee: If Event B was caused by Event A (B.causation_id == A.event_id),
        Event A is guaranteed to precede Event B in the output, even if B has an
        earlier or identical wall-clock timestamp due to clock skew or arrived earlier.

        Fail-closed rules:
        - If any event references a causation_id that is not in the timeline, raises ValueError.
        - If parent and child correlation IDs mismatch, raises ValueError.
        - If a cycle is detected, raises ValueError.
        - Ties among causally unlinked events are resolved deterministically by
          (timestamp, event_id).
        """
        entries = list(self._entries_by_id.values())
        if not entries:
            return ()

        # Validate causal references, correlation continuity, and self-cycles
        for e in entries:
            if e.causation_id is not None:
                if e.causation_id == e.event_id:
                    raise ValueError(
                        f"Causal cycle detected: event {e.event_id!r} caused by itself"
                    )
                parent = self._entries_by_id.get(e.causation_id)
                if parent is None:
                    raise ValueError(
                        f"Unresolved causal predecessor {e.causation_id!r} for event {e.event_id!r}"
                    )
                if parent.correlation_id != e.correlation_id:
                    raise ValueError(
                        f"Correlation ID mismatch between parent {parent.event_id!r} "
                        f"(correlation {parent.correlation_id!r}) and child {e.event_id!r} "
                        f"(correlation {e.correlation_id!r})"
                    )

        # Build adjacency graph: parent -> set of children
        children_of: Dict[str, List[str]] = {e.event_id: [] for e in entries}
        in_degree: Dict[str, int] = {e.event_id: 0 for e in entries}

        for e in entries:
            if e.causation_id:
                children_of[e.causation_id].append(e.event_id)
                in_degree[e.event_id] += 1

        # Deterministic priority sort key for tie-breaking
        def sort_key(event_id: str) -> tuple[str, str]:
            e = self._entries_by_id[event_id]
            return (format_utc_timestamp(e.timestamp), e.event_id)

        # Kahn's algorithm with deterministic tie-breaking and dynamic depth propagation
        depth_map: Dict[str, int] = {e.event_id: 0 for e in entries}
        ready = sorted([eid for eid, deg in in_degree.items() if deg == 0], key=sort_key)
        ordered_ids: List[str] = []

        while ready:
            current_id = ready.pop(0)
            ordered_ids.append(current_id)

            for child_id in children_of[current_id]:
                depth_map[child_id] = max(depth_map[child_id], depth_map[current_id] + 1)
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    ready.append(child_id)
            ready.sort(key=sort_key)

        # If cycle occurred, fail closed
        if len(ordered_ids) < len(entries):
            raise ValueError("Causal cycle detected in timeline DAG")

        return tuple(
            self._entries_by_id[eid].model_copy(update={"depth": depth_map.get(eid, 0)})
            for eid in ordered_ids
        )

    def compute_timeline_digest(self) -> str:
        """Compute deterministic SHA-256 digest over the causally ordered timeline."""
        ordered = self.get_causally_ordered_entries()
        raw_list = [entry.model_dump(mode="json") for entry in ordered]
        data_bytes = canonical_json_bytes(raw_list)
        return sha256_hex(data_bytes)

    def to_dict(self) -> Mapping[str, Any]:
        """Export timeline to JSON-serializable dictionary with digest."""
        ordered = self.get_causally_ordered_entries()
        return {
            "schema_version": TIMELINE_SCHEMA_VERSION,
            "change_id": self.change_id,
            "total_events": len(ordered),
            "timeline_digest": self.compute_timeline_digest(),
            "events": [e.model_dump(mode="json") for e in ordered],
        }

    def to_json(self) -> str:
        """Serialize timeline to canonical JSON string."""
        data_bytes = canonical_json_bytes(self.to_dict())
        return data_bytes.decode("utf-8")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CausalEventTimeline:
        """Deserialize and strictly validate a sealed timeline from a dictionary.

        Enforces:
        - Exact top-level schema_version == "1.0.0"
        - Exact bounded top-level fields (unknown fields rejected)
        - Valid events list
        - total_events == actual event count
        - Required, non-blank timeline_digest matching recomputed digest
        - Every event.change_id == top-level change_id
        - No duplicate serialized event IDs
        - No idempotency collisions
        - Complete DAG causal validity (unresolved predecessor, cycle, correlation
          mismatch fail closed)
        """
        if not isinstance(data, (dict, Mapping)):
            raise ValueError(f"Expected dictionary for timeline data, got {type(data).__name__}")

        extra_fields = set(data.keys()) - ALLOWED_TOP_LEVEL_KEYS
        if extra_fields:
            raise ValueError(f"Unknown top-level fields in timeline data: {sorted(extra_fields)}")

        schema_version = data.get("schema_version")
        if schema_version != TIMELINE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported timeline schema_version: {schema_version!r}. "
                f"Expected {TIMELINE_SCHEMA_VERSION!r}"
            )

        change_id = data.get("change_id")
        if not change_id or not isinstance(change_id, str) or not change_id.strip():
            raise ValueError("Missing or invalid change_id in timeline data")

        events_list = data.get("events")
        if not isinstance(events_list, list):
            raise ValueError(f"events field must be a list, got {type(events_list).__name__}")

        total_events = data.get("total_events")
        if (
            total_events is None
            or not isinstance(total_events, int)
            or total_events != len(events_list)
        ):
            raise ValueError(
                f"total_events mismatch: declared {total_events}, actual {len(events_list)}"
            )

        expected_digest = data.get("timeline_digest")
        if (
            not expected_digest
            or not isinstance(expected_digest, str)
            or not expected_digest.strip()
        ):
            raise ValueError("Missing or blank timeline_digest in sealed timeline data")

        timeline = cls(change_id=change_id.strip())
        seen_event_ids: Set[str] = set()
        seen_idempotency_keys: Dict[str, str] = {}

        for idx, item in enumerate(events_list):
            if not isinstance(item, (dict, Mapping)):
                raise ValueError(
                    f"Event at index {idx} must be a dictionary, got {type(item).__name__}"
                )
            entry = CausalTimelineEntry.model_validate(item)
            if entry.change_id != timeline.change_id:
                raise ValueError(
                    f"Cross-change event {entry.event_id!r} with change_id {entry.change_id!r} "
                    f"does not match timeline change_id {timeline.change_id!r}"
                )
            if entry.event_id in seen_event_ids:
                raise ValueError(
                    f"Duplicate serialized event_id {entry.event_id!r} in timeline data"
                )
            if entry.idempotency_key in seen_idempotency_keys:
                raise ValueError(
                    f"Idempotency collision for key {entry.idempotency_key!r}: "
                    f"already used by event {seen_idempotency_keys[entry.idempotency_key]!r} "
                    f"and {entry.event_id!r}"
                )

            seen_event_ids.add(entry.event_id)
            seen_idempotency_keys[entry.idempotency_key] = entry.event_id
            timeline._entries_by_id[entry.event_id] = entry

        # Verify causal DAG validity, missing predecessors, correlation mismatches, and cycles
        timeline.get_causally_ordered_entries()

        # Verify digest
        actual_digest = timeline.compute_timeline_digest()
        if actual_digest != expected_digest:
            raise ValueError(
                f"Timeline digest mismatch. Expected {expected_digest}, got {actual_digest}"
            )

        return timeline
