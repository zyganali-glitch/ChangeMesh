"""Tests for P-05.03 evidence contracts."""

import ast
import json
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from domain.contracts.evidence import (
    EvidenceRecord,
    EvidenceState,
    ExecutionEvidenceMode,
    Provenance,
    TraceReference,
    ArtifactHash,
)
import domain.contracts


def test_vocabulary():
    """Assert the exact EvidenceState and ExecutionEvidenceMode vocabularies."""
    assert set(s.value for s in EvidenceState) == {
        "PASS", "WARN", "FAIL", "NOT_RUN", "SIMULATED", "BLOCKED", "QUARANTINED"
    }
    assert set(m.value for m in ExecutionEvidenceMode) == {
        "FIXTURE", "SIMULATION", "RECORDED_CLOUD", "LIVE_WRITE"
    }

    with pytest.raises(ValidationError):
        EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state="UNKNOWN_STATE",
            provenance=Provenance(
                schema_version="1.0",
                source="src",
                collection_mode=ExecutionEvidenceMode.FIXTURE,
                collection_timestamp=datetime.now(timezone.utc)
            )
        )


def test_mandatory_fields():
    """Missing or blank source/schema/mode must reject."""
    with pytest.raises(ValidationError, match="must not be blank|validation error"):
        Provenance(
            schema_version="1.0",
            source="   ",
            collection_mode=ExecutionEvidenceMode.FIXTURE,
            collection_timestamp=datetime.now(timezone.utc)
        )

    with pytest.raises(ValidationError):
        Provenance(
            schema_version="1.0",
            source="src",
            collection_timestamp=datetime.now(timezone.utc)
            # missing collection_mode
        )


def test_mode_state_separation():
    """Prove mode and state are separate typed fields."""
    provenance = Provenance(
        schema_version="1.0",
        source="fixture-runner",
        collection_mode=ExecutionEvidenceMode.FIXTURE,
        collection_timestamp=datetime.now(timezone.utc)
    )
    
    # FIXTURE + PASS
    record1 = EvidenceRecord(
        schema_version="1.0",
        evidence_id="e1",
        change_request_id="c1",
        subject="test",
        state=EvidenceState.PASS,
        provenance=provenance
    )
    assert record1.state == EvidenceState.PASS
    assert record1.provenance.collection_mode == ExecutionEvidenceMode.FIXTURE

    # SIMULATION + PASS
    provenance2 = Provenance(
        schema_version="1.0",
        source="sim-runner",
        collection_mode=ExecutionEvidenceMode.SIMULATION,
        collection_timestamp=datetime.now(timezone.utc)
    )
    record2 = EvidenceRecord(
        schema_version="1.0",
        evidence_id="e2",
        change_request_id="c1",
        subject="test",
        state=EvidenceState.PASS,
        provenance=provenance2
    )
    assert record2.state == EvidenceState.PASS
    assert record2.provenance.collection_mode == ExecutionEvidenceMode.SIMULATION

    # Prove mode survives serialization
    data = record2.model_dump_json()
    loaded = EvidenceRecord.model_validate_json(data)
    assert loaded.provenance.collection_mode == ExecutionEvidenceMode.SIMULATION


def test_simulated_state_ambiguity():
    """SIMULATED is only valid with FIXTURE/SIMULATION."""
    # Valid
    EvidenceRecord(
        schema_version="1.0",
        evidence_id="e1",
        change_request_id="c1",
        subject="test",
        state=EvidenceState.SIMULATED,
        provenance=Provenance(
            schema_version="1.0",
            source="sim",
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            collection_timestamp=datetime.now(timezone.utc)
        )
    )
    
    # LIVE_WRITE + SIMULATED (Invalid)
    with pytest.raises(ValidationError, match="SIMULATED state is only valid with FIXTURE or SIMULATION mode"):
        EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state=EvidenceState.SIMULATED,
            provenance=Provenance(
                schema_version="1.0",
                source="live",
                collection_mode=ExecutionEvidenceMode.LIVE_WRITE,
                collection_timestamp=datetime.now(timezone.utc)
            )
        )


def test_recorded_cloud_requirements():
    """RECORDED_CLOUD needs historical provenance and artifacts."""
    valid_prov = Provenance(
        schema_version="1.0",
        source="cloud",
        collection_mode=ExecutionEvidenceMode.RECORDED_CLOUD,
        collection_timestamp=datetime.now(timezone.utc),
        source_execution_identifier="run-123",
        source_execution_timestamp=datetime.now(timezone.utc)
    )
    
    hash_obj = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    
    # Valid
    EvidenceRecord(
        schema_version="1.0",
        evidence_id="e1",
        change_request_id="c1",
        subject="test",
        state=EvidenceState.PASS,
        provenance=valid_prov,
        artifacts=[hash_obj]
    )
    
    # Missing execution ID
    invalid_prov1 = valid_prov.model_copy(update={"source_execution_identifier": None})
    with pytest.raises(ValidationError, match="RECORDED_CLOUD evidence requires source_execution_identifier"):
        EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state=EvidenceState.PASS,
            provenance=invalid_prov1,
            artifacts=[hash_obj]
        )

    # Missing artifacts
    with pytest.raises(ValidationError, match="RECORDED_CLOUD evidence requires at least one artifact hash"):
        EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state=EvidenceState.PASS,
            provenance=valid_prov,
            artifacts=[]
        )


def test_artifact_hash():
    """Test ArtifactHash schema."""
    h = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert h.algorithm == "sha256"
    
    with pytest.raises(ValidationError):
        ArtifactHash(schema_version="1.0", algorithm=" ", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        
    with pytest.raises(ValidationError):
        ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", extra_field="bad")


def test_trace_reference():
    """Test TraceReference schema."""
    t = TraceReference(trace_id="t1", span_id="s1")
    assert t.trace_id == "t1"
    
    with pytest.raises(ValidationError):
        TraceReference(trace_id="  ")
        
    with pytest.raises(ValidationError):
        TraceReference(trace_id="t1", provider_data={"internal": "bad"})


def test_evidence_record_nested():
    """Valid nested and rejection of unknown fields."""
    with pytest.raises(ValidationError):
        EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state=EvidenceState.PASS,
            provenance=Provenance(
                schema_version="1.0",
                source="src",
                collection_mode=ExecutionEvidenceMode.FIXTURE,
                collection_timestamp=datetime.now(timezone.utc)
            ),
            unknown_field="bad"
        )


def test_authority_claim_honesty():
    """Deterministic states survive serialization untouched."""
    for state in EvidenceState:
        record = EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state=state,
            provenance=Provenance(
                schema_version="1.0",
                source="src",
                collection_mode=ExecutionEvidenceMode.FIXTURE,
                collection_timestamp=datetime.now(timezone.utc)
            )
        )
        data = record.model_dump_json()
        loaded = EvidenceRecord.model_validate_json(data)
        assert loaded.state == state


def test_public_export():
    """Check __all__ in domain.contracts.__init__.py."""
    exports = set(domain.contracts.__all__)
    assert "EvidenceRecord" in exports
    assert "EvidenceState" in exports
    assert "ExecutionEvidenceMode" in exports
    assert "Provenance" in exports
    assert "TraceReference" in exports
    assert "ArtifactHash" in exports
    
    # Check non-leakage (P-05.06 concepts should not be present yet)
    assert "canonical_hash" not in exports
    assert "timestamp_wire_format" not in exports


def test_provider_neutrality():
    """AST check for provider imports in evidence.py."""
    import pathlib
    evidence_path = pathlib.Path(domain.contracts.evidence.__file__)
    tree = ast.parse(evidence_path.read_text())
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert not name.name.startswith("google")
                assert not name.name.startswith("opentelemetry")
                assert not name.name.startswith("pytest")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert not node.module.startswith("google")
                assert not node.module.startswith("opentelemetry")
                assert not node.module.startswith("pytest")


def test_credential_surface():
    """Inspect model fields for obvious credential names."""
    for field_name in EvidenceRecord.model_fields.keys():
        assert "token" not in field_name.lower()
        assert "key" not in field_name.lower()
        assert "secret" not in field_name.lower()
        assert "credential" not in field_name.lower()


# ---------------------------------------------------------------------------
# POST-CONSTRUCTION IMMUTABILITY — REGRESSION TESTS
# ---------------------------------------------------------------------------


def _make_fixture_provenance():
    return Provenance(
        schema_version="1.0",
        source="fixture-runner",
        collection_mode=ExecutionEvidenceMode.FIXTURE,
        collection_timestamp=datetime.now(timezone.utc),
    )


def _make_record(state=EvidenceState.FAIL, mode=ExecutionEvidenceMode.FIXTURE, **kw):
    prov = Provenance(
        schema_version="1.0",
        source="src",
        collection_mode=mode,
        collection_timestamp=datetime.now(timezone.utc),
        **{k: v for k, v in kw.items() if k.startswith("source_execution")},
    )
    artifacts = kw.get("artifacts", ())
    return EvidenceRecord(
        schema_version="1.0",
        evidence_id="e1",
        change_request_id="c1",
        subject="test",
        state=state,
        provenance=prov,
        artifacts=artifacts,
    )


class TestEvidenceRecordImmutability:
    """Post-construction mutation of EvidenceRecord fields must be rejected."""

    def test_state_frozen(self):
        """FAIL -> PASS rewrite must be rejected."""
        record = _make_record(state=EvidenceState.FAIL)
        with pytest.raises(ValidationError):
            record.state = EvidenceState.PASS

    def test_not_run_to_pass_frozen(self):
        """NOT_RUN -> PASS rewrite must be rejected."""
        record = _make_record(state=EvidenceState.NOT_RUN)
        with pytest.raises(ValidationError):
            record.state = EvidenceState.PASS

    def test_blocked_to_pass_frozen(self):
        """BLOCKED -> PASS rewrite must be rejected."""
        record = _make_record(state=EvidenceState.BLOCKED)
        with pytest.raises(ValidationError):
            record.state = EvidenceState.PASS

    def test_quarantined_to_pass_frozen(self):
        """QUARANTINED -> PASS rewrite must be rejected."""
        record = _make_record(state=EvidenceState.QUARANTINED)
        with pytest.raises(ValidationError):
            record.state = EvidenceState.PASS

    def test_evidence_id_frozen(self):
        record = _make_record()
        with pytest.raises(ValidationError):
            record.evidence_id = "different"

    def test_change_request_id_frozen(self):
        record = _make_record()
        with pytest.raises(ValidationError):
            record.change_request_id = "different"

    def test_subject_frozen(self):
        record = _make_record()
        with pytest.raises(ValidationError):
            record.subject = "different"

    def test_provenance_replacement_frozen(self):
        record = _make_record()
        with pytest.raises(ValidationError):
            record.provenance = _make_fixture_provenance()

    def test_artifacts_replacement_frozen(self):
        record = _make_record()
        with pytest.raises(ValidationError):
            record.artifacts = ()


class TestProvenanceImmutability:
    """Post-construction mutation of Provenance fields must be rejected."""

    def test_source_frozen(self):
        prov = _make_fixture_provenance()
        with pytest.raises(ValidationError):
            prov.source = "different-source"

    def test_collection_mode_frozen(self):
        prov = _make_fixture_provenance()
        with pytest.raises(ValidationError):
            prov.collection_mode = ExecutionEvidenceMode.LIVE_WRITE

    def test_collection_timestamp_frozen(self):
        prov = _make_fixture_provenance()
        with pytest.raises(ValidationError):
            prov.collection_timestamp = datetime.now(timezone.utc)

    def test_schema_version_frozen(self):
        prov = _make_fixture_provenance()
        with pytest.raises(ValidationError):
            prov.schema_version = "2.0"


class TestArtifactHashImmutability:
    """Post-construction mutation of ArtifactHash fields must be rejected."""

    def test_digest_frozen(self):
        h = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        with pytest.raises(ValidationError):
            h.digest = "different-digest"

    def test_algorithm_frozen(self):
        h = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        with pytest.raises(ValidationError):
            h.algorithm = "md5"

    def test_schema_version_frozen(self):
        h = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        with pytest.raises(ValidationError):
            h.schema_version = "2.0"


class TestTraceReferenceImmutability:
    """Post-construction mutation of TraceReference fields must be rejected."""

    def test_trace_id_frozen(self):
        t = TraceReference(trace_id="t1", span_id="s1")
        with pytest.raises(ValidationError):
            t.trace_id = "different-trace"

    def test_span_id_frozen(self):
        t = TraceReference(trace_id="t1", span_id="s1")
        with pytest.raises(ValidationError):
            t.span_id = "different-span"


class TestArtifactCollectionImmutability:
    """The artifacts tuple must not expose mutable list API."""

    def test_artifacts_is_tuple(self):
        h = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        record = _make_record(artifacts=[h])
        assert isinstance(record.artifacts, tuple)

    def test_artifacts_has_no_clear(self):
        record = _make_record()
        assert not hasattr(record.artifacts, "clear")

    def test_artifacts_has_no_append(self):
        record = _make_record()
        assert not hasattr(record.artifacts, "append")

    def test_artifacts_has_no_pop(self):
        record = _make_record()
        assert not hasattr(record.artifacts, "pop")

    def test_list_input_converts_to_tuple(self):
        """Pydantic must accept list input and convert to immutable tuple."""
        h = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        record = _make_record(artifacts=[h])
        assert type(record.artifacts) is tuple
        assert len(record.artifacts) == 1


class TestSimulatedModeMutationBypass:
    """A SIMULATION+SIMULATED record must not be mutated to LIVE_WRITE."""

    def test_simulation_to_live_write_rejected(self):
        record = EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state=EvidenceState.SIMULATED,
            provenance=Provenance(
                schema_version="1.0",
                source="sim",
                collection_mode=ExecutionEvidenceMode.SIMULATION,
                collection_timestamp=datetime.now(timezone.utc),
            ),
        )
        # Provenance itself is frozen — cannot change mode
        with pytest.raises(ValidationError):
            record.provenance.collection_mode = ExecutionEvidenceMode.LIVE_WRITE

    def test_live_write_fail_to_pass_rejected(self):
        """LIVE_WRITE+FAIL cannot be mutated to PASS."""
        record = EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state=EvidenceState.FAIL,
            provenance=Provenance(
                schema_version="1.0",
                source="live",
                collection_mode=ExecutionEvidenceMode.LIVE_WRITE,
                collection_timestamp=datetime.now(timezone.utc),
            ),
        )
        with pytest.raises(ValidationError):
            record.state = EvidenceState.PASS


class TestRecordedCloudPostConstructionSafety:
    """A valid RECORDED_CLOUD record cannot lose its provenance/hash proof."""

    def _make_recorded_cloud(self):
        return EvidenceRecord(
            schema_version="1.0",
            evidence_id="e1",
            change_request_id="c1",
            subject="test",
            state=EvidenceState.PASS,
            provenance=Provenance(
                schema_version="1.0",
                source="cloud",
                collection_mode=ExecutionEvidenceMode.RECORDED_CLOUD,
                collection_timestamp=datetime.now(timezone.utc),
                source_execution_identifier="run-123",
                source_execution_timestamp=datetime.now(timezone.utc),
            ),
            artifacts=[
                ArtifactHash(schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
            ],
        )

    def test_source_execution_identifier_frozen(self):
        record = self._make_recorded_cloud()
        with pytest.raises(ValidationError):
            record.provenance.source_execution_identifier = None

    def test_source_execution_timestamp_frozen(self):
        record = self._make_recorded_cloud()
        with pytest.raises(ValidationError):
            record.provenance.source_execution_timestamp = None

    def test_collection_mode_downgrade_frozen(self):
        record = self._make_recorded_cloud()
        with pytest.raises(ValidationError):
            record.provenance.collection_mode = ExecutionEvidenceMode.FIXTURE

    def test_artifacts_replacement_frozen(self):
        record = self._make_recorded_cloud()
        with pytest.raises(ValidationError):
            record.artifacts = ()

    def test_artifact_tuple_has_no_clear(self):
        record = self._make_recorded_cloud()
        assert not hasattr(record.artifacts, "clear")

    def test_nested_artifact_hash_frozen(self):
        """Individual artifact hashes inside the record are also frozen."""
        record = self._make_recorded_cloud()
        with pytest.raises(ValidationError):
            record.artifacts[0].digest = "different"


# ---------------------------------------------------------------------------
# CONSTRUCTION-TIME VALIDATION GAP COVERAGE
# ---------------------------------------------------------------------------


class TestConstructionTimeValidation:
    """Close remaining construction-time proof gaps."""

    def test_unknown_execution_mode_rejects(self):
        with pytest.raises(ValidationError):
            Provenance(
                schema_version="1.0",
                source="src",
                collection_mode="UNKNOWN_MODE",
                collection_timestamp=datetime.now(timezone.utc),
            )

    def test_missing_source_rejects(self):
        """Completely omitted source (not just blank) must reject."""
        with pytest.raises(ValidationError):
            Provenance(
                schema_version="1.0",
                collection_mode=ExecutionEvidenceMode.FIXTURE,
                collection_timestamp=datetime.now(timezone.utc),
            )

    def test_blank_evidence_record_schema_version(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_record.__wrapped__ if hasattr(_make_record, '__wrapped__') else None
            EvidenceRecord(
                schema_version="   ",
                evidence_id="e1",
                change_request_id="c1",
                subject="test",
                state=EvidenceState.PASS,
                provenance=_make_fixture_provenance(),
            )

    def test_blank_evidence_id(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            EvidenceRecord(
                schema_version="1.0",
                evidence_id="  ",
                change_request_id="c1",
                subject="test",
                state=EvidenceState.PASS,
                provenance=_make_fixture_provenance(),
            )

    def test_blank_change_request_id(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            EvidenceRecord(
                schema_version="1.0",
                evidence_id="e1",
                change_request_id="  ",
                subject="test",
                state=EvidenceState.PASS,
                provenance=_make_fixture_provenance(),
            )

    def test_blank_subject(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            EvidenceRecord(
                schema_version="1.0",
                evidence_id="e1",
                change_request_id="c1",
                subject="  ",
                state=EvidenceState.PASS,
                provenance=_make_fixture_provenance(),
            )

    def test_blank_artifact_hash_schema_version(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            ArtifactHash(schema_version="  ", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    def test_blank_artifact_hash_algorithm(self):
        with pytest.raises(ValidationError):
            ArtifactHash(schema_version="1.0", algorithm="  ", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    def test_blank_artifact_hash_digest(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            ArtifactHash(schema_version="1.0", algorithm="sha256", digest="  ")

    def test_recorded_cloud_missing_timestamp_rejects(self):
        """RECORDED_CLOUD without source_execution_timestamp must reject."""
        prov = Provenance(
            schema_version="1.0",
            source="cloud",
            collection_mode=ExecutionEvidenceMode.RECORDED_CLOUD,
            collection_timestamp=datetime.now(timezone.utc),
            source_execution_identifier="run-123",
            # missing source_execution_timestamp
        )
        with pytest.raises(
            ValidationError,
            match="RECORDED_CLOUD evidence requires source_execution_timestamp",
        ):
            EvidenceRecord(
                schema_version="1.0",
                evidence_id="e1",
                change_request_id="c1",
                subject="test",
                state=EvidenceState.PASS,
                provenance=prov,
                artifacts=[
                    ArtifactHash(
                        schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    )
                ],
            )

    def test_recorded_cloud_simulated_rejects(self):
        """RECORDED_CLOUD + SIMULATED must reject at construction."""
        with pytest.raises(
            ValidationError,
            match="SIMULATED state is only valid with FIXTURE or SIMULATION mode",
        ):
            EvidenceRecord(
                schema_version="1.0",
                evidence_id="e1",
                change_request_id="c1",
                subject="test",
                state=EvidenceState.SIMULATED,
                provenance=Provenance(
                    schema_version="1.0",
                    source="cloud",
                    collection_mode=ExecutionEvidenceMode.RECORDED_CLOUD,
                    collection_timestamp=datetime.now(timezone.utc),
                    source_execution_identifier="run-123",
                    source_execution_timestamp=datetime.now(timezone.utc),
                ),
                artifacts=[
                    ArtifactHash(
                        schema_version="1.0", algorithm="sha256", digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    )
                ],
            )

