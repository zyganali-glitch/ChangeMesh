"""ChangeMesh causal event timeline for dashboard and change passport.

P-09.05 / Donor component: CCT-FLIGHT-001 (Clean-room reimplemented).

Records distributed causal event chains, validates DAG acyclicity, computes
deterministic causal ordering (independent of wall-clock skew), enforces secret
redaction, and produces tamper-protected digests for dashboard/passport audit.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

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
    def _must_not_be_blank(cls, v: str, info) -> str:
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
        """Record an event envelope into the causal timeline."""
        if envelope.change_id != self.change_id:
            raise ValueError(
                f"Envelope change_id {envelope.change_id!r} does not match "
                f"timeline change_id {self.change_id!r}"
            )

        if envelope.event_id in self._entries_by_id:
            raise ValueError(f"Event ID {envelope.event_id!r} already exists in timeline")

        if envelope.causation_id:
            parent = self._entries_by_id.get(envelope.causation_id)
            if not parent:
                raise ValueError(
                    f"Causal predecessor {envelope.causation_id!r} not found in timeline"
                )
            if parent.correlation_id != envelope.correlation_id:
                raise ValueError("Correlation ID mismatch between cause and child")

        if payload is not None:
            scan_payload_for_secrets(payload)

        # Compute causal depth
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
        earlier or identical wall-clock timestamp due to clock skew.
        Ties among causally unlinked events are resolved deterministically by (timestamp, event_id).
        """
        entries = list(self._entries_by_id.values())
        if not entries:
            return ()

        # Build adjacency graph: parent -> set of children
        children_of: Dict[str, List[str]] = {e.event_id: [] for e in entries}
        in_degree: Dict[str, int] = {e.event_id: 0 for e in entries}

        for e in entries:
            if e.causation_id and e.causation_id in self._entries_by_id:
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
        """Deserialize a timeline from a dictionary."""
        schema_version = data.get("schema_version")
        if schema_version != TIMELINE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported timeline schema_version: {schema_version}")

        change_id = data.get("change_id")
        if not change_id or not isinstance(change_id, str):
            raise ValueError("Missing or invalid change_id in timeline data")

        timeline = cls(change_id=change_id)
        events_list = data.get("events", [])
        for item in events_list:
            entry = CausalTimelineEntry.model_validate(item)
            if entry.event_id in timeline._entries_by_id:
                raise ValueError(f"Duplicate event_id {entry.event_id!r} in timeline data")
            timeline._entries_by_id[entry.event_id] = entry

        # Verify digest if provided
        expected_digest = data.get("timeline_digest")
        if expected_digest is not None:
            actual_digest = timeline.compute_timeline_digest()
            if actual_digest != expected_digest:
                raise ValueError(
                    f"Timeline digest mismatch. Expected {expected_digest}, got {actual_digest}"
                )

        # Check for cycles
        timeline.get_causally_ordered_entries()

        return timeline
