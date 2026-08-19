"""Tests for P-22 — Evidence Ledger, Passport, and Observability.

P-22.01: Append-only ledger with tamper-evident structure.
P-22.02: Artifact hashing and provenance.
P-22.03: Passport generation/verification (delegates to existing).
P-22.04: Correlated observability spans.
P-22.05: Sanitized export.
P-22.06: Evidence completeness report.
"""

from __future__ import annotations

import datetime
from datetime import timezone

import pytest

from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode
from src.evidence.evidence_ledger import (
    EvidenceLedger,
    SpanCollector,
    compute_artifact_digest,
    compute_artifact_provenance,
    generate_completeness_report,
)

NOW = datetime.datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


# =========================================================================
# P-22.01: APPEND-ONLY EVIDENCE LEDGER
# =========================================================================


class TestEvidenceLedger:
    """P-22.01: Mutation detectable; ordering/schema explicit."""

    def test_append_creates_entry_with_digest(self):
        ledger = EvidenceLedger()
        entry = ledger.append(
            entry_id="ev-001",
            tenant_id="test-tenant",
            change_id="change-001",
            subject="rehearsal",
            evidence_state=EvidenceState.SIMULATED,
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        assert entry.sequence_number == 1
        assert entry.entry_id == "ev-001"
        assert entry.entry_digest is not None
        assert len(entry.entry_digest) == 64  # SHA-256 hex
        assert entry.previous_entry_digest is None  # First entry
        assert ledger.length == 1

    def test_chain_links_entries(self):
        ledger = EvidenceLedger()
        e1 = ledger.append(
            "ev-001",
            "t",
            "c",
            "subject1",
            EvidenceState.SIMULATED,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        e2 = ledger.append(
            "ev-002",
            "t",
            "c",
            "subject2",
            EvidenceState.PASS,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        assert e2.previous_entry_digest == e1.entry_digest
        assert e2.sequence_number == 2

    def test_integrity_verification_passes(self):
        ledger = EvidenceLedger()
        for i in range(5):
            ledger.append(
                f"ev-{i:03d}",
                "t",
                "c",
                f"subject-{i}",
                EvidenceState.SIMULATED,
                ExecutionEvidenceMode.SIMULATION,
                now=NOW,
            )

        ok, error = ledger.verify_integrity()
        assert ok is True
        assert error is None

    def test_tamper_detection(self):
        """Modifying an entry's content is detected by chain verification."""
        ledger = EvidenceLedger()
        ledger.append(
            "ev-001",
            "t",
            "c",
            "subject1",
            EvidenceState.SIMULATED,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        ledger.append(
            "ev-002",
            "t",
            "c",
            "subject2",
            EvidenceState.PASS,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        # Tamper with first entry (replace with different digest)
        tampered = ledger._entries[0].model_copy(update={"entry_digest": "0" * 64})
        ledger._entries[0] = tampered

        ok, error = ledger.verify_integrity()
        assert ok is False
        assert "mismatch" in error

    def test_empty_ledger_is_valid(self):
        ledger = EvidenceLedger()
        ok, error = ledger.verify_integrity()
        assert ok is True

    def test_entries_are_frozen(self):
        ledger = EvidenceLedger()
        entry = ledger.append(
            "ev-001",
            "t",
            "c",
            "subject",
            EvidenceState.SIMULATED,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        with pytest.raises(Exception):
            entry.entry_id = "modified"


# =========================================================================
# P-22.02: ARTIFACT HASHING AND PROVENANCE
# =========================================================================


class TestArtifactHashing:
    """P-22.02: Hashes reproduce and bind source revision."""

    def test_digest_is_deterministic(self):
        content = b"test artifact content"
        d1 = compute_artifact_digest(content)
        d2 = compute_artifact_digest(content)
        assert d1 == d2
        assert len(d1) == 64

    def test_different_content_different_digest(self):
        d1 = compute_artifact_digest(b"content A")
        d2 = compute_artifact_digest(b"content B")
        assert d1 != d2

    def test_provenance_binds_revision(self):
        prov = compute_artifact_provenance(
            artifact_digest="abc123",
            source_revision="9afef11",
            artifact_path="src/main.py",
        )
        assert len(prov) == 16

    def test_provenance_is_deterministic(self):
        p1 = compute_artifact_provenance("abc", "rev1", "path/file")
        p2 = compute_artifact_provenance("abc", "rev1", "path/file")
        assert p1 == p2

    def test_provenance_changes_with_revision(self):
        p1 = compute_artifact_provenance("abc", "rev1", "path/file")
        p2 = compute_artifact_provenance("abc", "rev2", "path/file")
        assert p1 != p2


# =========================================================================
# P-22.04: CORRELATED OBSERVABILITY SPANS
# =========================================================================


class TestObservabilitySpans:
    """P-22.04: One Change ID traces end-to-end; sensitive payloads excluded."""

    def test_span_creation(self):
        collector = SpanCollector("change-001", "corr-001")
        span = collector.start_span("discover_changes", now=NOW)

        assert span.trace_id == "change-001"
        assert span.correlation_id == "corr-001"
        assert span.operation == "discover_changes"
        assert span.span_id == "span-0001"

    def test_parent_child_spans(self):
        collector = SpanCollector("change-001", "corr-001")
        parent = collector.start_span("saga_run", now=NOW)
        child = collector.start_span("execute_task", parent_span_id=parent.span_id, now=NOW)

        assert child.parent_span_id == parent.span_id
        assert len(collector.spans) == 2

    def test_sanitized_export_excludes_attributes(self):
        """P-22.05: Export binds revision/time without secrets."""
        collector = SpanCollector("change-001", "corr-001")
        collector.start_span("operation", now=NOW)

        export = collector.export_sanitized()
        assert len(export) == 1
        assert "trace_id" in export[0]
        assert "change_id" in export[0]
        assert "attributes" not in export[0]  # Excluded from sanitized export


# =========================================================================
# P-22.06: EVIDENCE COMPLETENESS REPORT
# =========================================================================


class TestEvidenceCompletenessReport:
    """P-22.06: Evidence completeness report for demo."""

    def test_complete_ledger_is_complete(self):
        ledger = EvidenceLedger()
        ledger.append(
            "ev-001",
            "t",
            "c",
            "rehearsal",
            EvidenceState.PASS,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )
        ledger.append(
            "ev-002",
            "t",
            "c",
            "execution",
            EvidenceState.PASS,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        report = generate_completeness_report("c", ledger)
        assert report.is_complete is True
        assert report.pass_count == 2
        assert report.fail_count == 0
        assert report.ledger_integrity is True

    def test_failed_entry_makes_incomplete(self):
        ledger = EvidenceLedger()
        ledger.append(
            "ev-001",
            "t",
            "c",
            "rehearsal",
            EvidenceState.FAIL,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        report = generate_completeness_report("c", ledger)
        assert report.is_complete is False
        assert report.fail_count == 1

    def test_empty_ledger_is_incomplete(self):
        ledger = EvidenceLedger()
        report = generate_completeness_report("c", ledger)
        assert report.is_complete is False
        assert report.total_entries == 0

    def test_report_includes_span_count(self):
        ledger = EvidenceLedger()
        ledger.append(
            "ev-001",
            "t",
            "c",
            "subject",
            EvidenceState.PASS,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        collector = SpanCollector("c", "corr-001")
        collector.start_span("op1", now=NOW)
        collector.start_span("op2", now=NOW)

        report = generate_completeness_report("c", ledger, collector)
        assert report.spans_collected == 2

    def test_simulated_entries_counted(self):
        ledger = EvidenceLedger()
        ledger.append(
            "ev-001",
            "t",
            "c",
            "subject",
            EvidenceState.SIMULATED,
            ExecutionEvidenceMode.SIMULATION,
            now=NOW,
        )

        report = generate_completeness_report("c", ledger)
        assert report.simulated_count == 1
        # SIMULATED with no failures is considered complete for demo purposes
        assert report.is_complete is True
