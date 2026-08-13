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
    
    hash_obj = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="abc")
    
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
    h = ArtifactHash(schema_version="1.0", algorithm="sha256", digest="abc")
    assert h.algorithm == "sha256"
    
    with pytest.raises(ValidationError):
        ArtifactHash(schema_version="1.0", algorithm=" ", digest="abc")
        
    with pytest.raises(ValidationError):
        ArtifactHash(schema_version="1.0", algorithm="sha256", digest="abc", extra_field="bad")


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
    
    # Check non-leakage
    assert "MemoryRecord" not in exports
    assert "CapabilityPassport" not in exports


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
