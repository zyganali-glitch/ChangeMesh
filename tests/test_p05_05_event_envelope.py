"""P-05.05 event-envelope contract tests.

Tests the EventEnvelope schema, EventDeliveryDisposition enum, and
classify_event_delivery pure deterministic classifier.

Covers:
- Positive contract construction (root and child events)
- JSON round-trip
- Required field presence
- Frozen model immutability
- Extra field rejection
- Blank / whitespace field rejection
- Self-causation rejection
- Deterministic duplicate classification (Rules A-D)
- Deterministic out-of-order / causation classification
- Causal consistency enforcement
- Redelivery deterministic reclassification
- Identity-conflict non-mutation proof
- Provider-neutrality (AST import scan)
- Credential-surface absence
- P-05.06 non-leakage boundary
"""

import ast
import copy
import pathlib
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

import domain.contracts
import domain.contracts.event_envelope
from domain.contracts import (
    EventEnvelope,
    EventDeliveryDisposition,
    classify_event_delivery,
)


# ===========================================================================
# HELPERS
# ===========================================================================

_NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
_LATER = _NOW + timedelta(hours=1)
_EARLIER = _NOW - timedelta(hours=1)


def _make_envelope(
    *,
    schema_version: str = "1.0",
    event_id: str = "evt-001",
    change_id: str = "chg-001",
    causation_id=None,
    correlation_id: str = "corr-001",
    producer_revision: str = "agent-v1.2.3",
    timestamp=None,
    idempotency_key: str = "idem-001",
    **overrides,
) -> EventEnvelope:
    if timestamp is None:
        timestamp = _NOW
    return EventEnvelope(
        schema_version=schema_version,
        event_id=event_id,
        change_id=change_id,
        causation_id=causation_id,
        correlation_id=correlation_id,
        producer_revision=producer_revision,
        timestamp=timestamp,
        idempotency_key=idempotency_key,
        **overrides,
    )


def _make_root():
    """Create a standard root event (causation_id=None)."""
    return _make_envelope()


def _make_child():
    """Create a standard child event with causation_id set."""
    return _make_envelope(
        event_id="evt-002",
        causation_id="evt-001",
        idempotency_key="idem-002",
    )


# ===========================================================================
# SECTION 1: POSITIVE CONTRACT TESTS
# ===========================================================================


class TestPositiveConstruction:
    """Valid root and child EventEnvelope creation."""

    def test_valid_root_event(self):
        env = _make_root()
        assert env.schema_version == "1.0"
        assert env.event_id == "evt-001"
        assert env.change_id == "chg-001"
        assert env.causation_id is None
        assert env.correlation_id == "corr-001"
        assert env.producer_revision == "agent-v1.2.3"
        assert env.timestamp == _NOW
        assert env.idempotency_key == "idem-001"

    def test_valid_child_event(self):
        env = _make_child()
        assert env.event_id == "evt-002"
        assert env.causation_id == "evt-001"
        assert env.change_id == "chg-001"
        assert env.correlation_id == "corr-001"

    def test_optional_causation_none_accepted(self):
        env = _make_envelope(causation_id=None)
        assert env.causation_id is None

    def test_model_json_round_trip(self):
        env = _make_root()
        data = env.model_dump_json()
        loaded = EventEnvelope.model_validate_json(data)
        assert loaded == env
        assert loaded.event_id == env.event_id
        assert loaded.timestamp == env.timestamp

    def test_child_json_round_trip(self):
        env = _make_child()
        data = env.model_dump_json()
        loaded = EventEnvelope.model_validate_json(data)
        assert loaded == env
        assert loaded.causation_id == "evt-001"

    def test_exact_required_fields(self):
        """EventEnvelope has exactly the P-05.05 required fields."""
        fields = set(EventEnvelope.model_fields.keys())
        expected = {
            "schema_version",
            "event_id",
            "change_id",
            "causation_id",
            "correlation_id",
            "producer_revision",
            "timestamp",
            "idempotency_key",
        }
        assert fields == expected


# ===========================================================================
# SECTION 2: FROZEN MODEL / IMMUTABILITY
# ===========================================================================


class TestImmutability:
    """Post-construction mutation must fail for all fields."""

    @pytest.mark.parametrize("field,value", [
        ("schema_version", "2.0"),
        ("event_id", "evt-999"),
        ("change_id", "chg-999"),
        ("causation_id", "evt-000"),
        ("correlation_id", "corr-999"),
        ("producer_revision", "agent-v9.9.9"),
        ("timestamp", _LATER),
        ("idempotency_key", "idem-999"),
    ])
    def test_mutation_rejected(self, field, value):
        env = _make_root()
        with pytest.raises(ValidationError):
            setattr(env, field, value)


# ===========================================================================
# SECTION 3: EXTRA FIELDS REJECTED
# ===========================================================================


class TestExtraFieldsRejected:
    """ConfigDict(extra='forbid') rejects unknown fields."""

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            _make_envelope(payload={"data": "value"})

    def test_unknown_field_token(self):
        with pytest.raises(ValidationError, match="extra"):
            _make_envelope(token="secret-123")

    def test_unknown_field_ack_id(self):
        with pytest.raises(ValidationError, match="extra"):
            _make_envelope(ack_id="ack-abc")


# ===========================================================================
# SECTION 4: BLANK / WHITESPACE FIELD REJECTION
# ===========================================================================


class TestBlankFieldRejection:
    """Mandatory non-blank fields reject empty and whitespace-only strings."""

    @pytest.mark.parametrize("field", [
        "schema_version",
        "event_id",
        "change_id",
        "correlation_id",
        "producer_revision",
        "idempotency_key",
    ])
    @pytest.mark.parametrize("bad_value", ["", " ", "\t", "  \t  "])
    def test_blank_mandatory_field(self, field, bad_value):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_envelope(**{field: bad_value})

    @pytest.mark.parametrize("bad_value", ["", " ", "\t", "  \t  "])
    def test_blank_causation_id_when_present(self, bad_value):
        """causation_id rejects blank when explicitly supplied."""
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_envelope(
                event_id="evt-child",
                causation_id=bad_value,
            )


# ===========================================================================
# SECTION 5: SELF-CAUSATION REJECTION
# ===========================================================================


class TestSelfCausation:
    """An event cannot causally produce itself."""

    def test_self_causation_rejected(self):
        with pytest.raises(ValidationError, match="Self-causation"):
            _make_envelope(event_id="evt-X", causation_id="evt-X")

    def test_different_ids_accepted(self):
        env = _make_envelope(event_id="evt-A", causation_id="evt-B")
        assert env.event_id == "evt-A"
        assert env.causation_id == "evt-B"


# ===========================================================================
# SECTION 6: EventDeliveryDisposition ENUM
# ===========================================================================


class TestDeliveryDisposition:
    """EventDeliveryDisposition has exactly four values."""

    def test_exact_values(self):
        values = {e.value for e in EventDeliveryDisposition}
        assert values == {"ACCEPT", "DUPLICATE", "OUT_OF_ORDER", "CONFLICT"}

    def test_is_string_enum(self):
        assert issubclass(EventDeliveryDisposition, str)

    def test_no_transport_states(self):
        values = {e.value for e in EventDeliveryDisposition}
        for forbidden in ("ACK", "NACK", "DEAD_LETTER", "RETRYING",
                          "PUBLISHED", "CONSUMED"):
            assert forbidden not in values


# ===========================================================================
# SECTION 7: DUPLICATE CLASSIFICATION TESTS
# ===========================================================================


class TestDuplicateClassification:
    """Deterministic duplicate / conflict classification (Rules A-F)."""

    def test_a_unseen_root_accept(self):
        """A. unseen root => ACCEPT."""
        root = _make_root()
        result = classify_event_delivery(root, {}, {})
        assert result == EventDeliveryDisposition.ACCEPT

    def test_b_exact_replay_duplicate(self):
        """B. same event_id + exactly same envelope => DUPLICATE."""
        root = _make_root()
        seen = {root.event_id: root}
        idem = {(root.change_id, root.idempotency_key): root.event_id}
        result = classify_event_delivery(root, seen, idem)
        assert result == EventDeliveryDisposition.DUPLICATE

    def test_c_same_id_changed_producer_conflict(self):
        """C. same event_id + changed producer_revision => CONFLICT."""
        original = _make_root()
        altered = _make_envelope(producer_revision="agent-v9.9.9")
        seen = {original.event_id: original}
        result = classify_event_delivery(altered, seen, {})
        assert result == EventDeliveryDisposition.CONFLICT

    def test_d_same_id_changed_timestamp_conflict(self):
        """D. same event_id + changed timestamp => CONFLICT."""
        original = _make_root()
        altered = _make_envelope(timestamp=_LATER)
        seen = {original.event_id: original}
        result = classify_event_delivery(altered, seen, {})
        assert result == EventDeliveryDisposition.CONFLICT

    def test_e_same_id_changed_idempotency_key_conflict(self):
        """E. same event_id + changed idempotency_key => CONFLICT."""
        original = _make_root()
        altered = _make_envelope(idempotency_key="idem-different")
        seen = {original.event_id: original}
        result = classify_event_delivery(altered, seen, {})
        assert result == EventDeliveryDisposition.CONFLICT

    def test_f_same_change_idem_different_event_conflict(self):
        """F. same (change_id, idempotency_key) + different event_id => CONFLICT."""
        original = _make_root()
        collider = _make_envelope(event_id="evt-different")
        idem = {(original.change_id, original.idempotency_key): original.event_id}
        result = classify_event_delivery(collider, {}, idem)
        assert result == EventDeliveryDisposition.CONFLICT

    def test_g_same_idem_key_different_change_not_duplicate(self):
        """G. same textual idempotency_key + different change_id =>
        not duplicate solely for that reason."""
        evt_a = _make_envelope(
            event_id="evt-a",
            change_id="change-A",
            idempotency_key="qualify-step",
        )
        evt_b = _make_envelope(
            event_id="evt-b",
            change_id="change-B",
            idempotency_key="qualify-step",
        )
        seen = {evt_a.event_id: evt_a}
        idem = {(evt_a.change_id, evt_a.idempotency_key): evt_a.event_id}
        result = classify_event_delivery(evt_b, seen, idem)
        assert result == EventDeliveryDisposition.ACCEPT

    def test_same_idem_key_different_change_explicit_independence(self):
        """Prove: change-A/'qualify-step' and change-B/'qualify-step'
        are independent identities."""
        evt_a = _make_envelope(
            event_id="evt-a", change_id="change-A", idempotency_key="qualify-step"
        )
        evt_b = _make_envelope(
            event_id="evt-b", change_id="change-B", idempotency_key="qualify-step"
        )
        # Both ACCEPTed independently
        r1 = classify_event_delivery(evt_a, {}, {})
        assert r1 == EventDeliveryDisposition.ACCEPT

        seen = {evt_a.event_id: evt_a}
        idem = {(evt_a.change_id, evt_a.idempotency_key): evt_a.event_id}
        r2 = classify_event_delivery(evt_b, seen, idem)
        assert r2 == EventDeliveryDisposition.ACCEPT


# ===========================================================================
# SECTION 8: OUT-OF-ORDER / CAUSATION TESTS
# ===========================================================================


class TestOutOfOrderCausation:
    """Deterministic out-of-order and causal consistency classification."""

    def test_a_child_cause_unseen_out_of_order(self):
        """A. child cause unseen => OUT_OF_ORDER."""
        child = _make_child()
        result = classify_event_delivery(child, {}, {})
        assert result == EventDeliveryDisposition.OUT_OF_ORDER

    def test_b_child_cause_seen_accept(self):
        """B. child cause seen => ACCEPT."""
        root = _make_root()
        child = _make_child()
        seen = {root.event_id: root}
        result = classify_event_delivery(child, seen, {})
        assert result == EventDeliveryDisposition.ACCEPT

    def test_c_child_change_id_mismatch_conflict(self):
        """C. child cause seen but change_id mismatch => CONFLICT."""
        root = _make_root()
        child = _make_envelope(
            event_id="evt-002",
            change_id="chg-DIFFERENT",
            causation_id="evt-001",
            idempotency_key="idem-002",
        )
        seen = {root.event_id: root}
        result = classify_event_delivery(child, seen, {})
        assert result == EventDeliveryDisposition.CONFLICT

    def test_d_child_correlation_id_mismatch_conflict(self):
        """D. child cause seen but correlation_id mismatch => CONFLICT."""
        root = _make_root()
        child = _make_envelope(
            event_id="evt-002",
            correlation_id="corr-DIFFERENT",
            causation_id="evt-001",
            idempotency_key="idem-002",
        )
        seen = {root.event_id: root}
        result = classify_event_delivery(child, seen, {})
        assert result == EventDeliveryDisposition.CONFLICT

    def test_e_timestamp_not_causal_authority(self):
        """E. child timestamp earlier than cause but causal predecessor known
        => do not use timestamp alone to override causal semantics."""
        root = _make_envelope(timestamp=_LATER)
        child = _make_envelope(
            event_id="evt-002",
            causation_id="evt-001",
            timestamp=_EARLIER,  # earlier than cause!
            idempotency_key="idem-002",
        )
        seen = {root.event_id: root}
        result = classify_event_delivery(child, seen, {})
        # Must ACCEPT based on causation, not reject due to timestamp
        assert result == EventDeliveryDisposition.ACCEPT

    def test_timestamp_equal_to_cause_accepted(self):
        """Same timestamp as cause — accepted via causation, not timestamp."""
        root = _make_envelope(timestamp=_NOW)
        child = _make_envelope(
            event_id="evt-002",
            causation_id="evt-001",
            timestamp=_NOW,  # exactly equal
            idempotency_key="idem-002",
        )
        seen = {root.event_id: root}
        result = classify_event_delivery(child, seen, {})
        assert result == EventDeliveryDisposition.ACCEPT

    def test_timestamp_reversed_ordering_accepted(self):
        """Cause has later timestamp than child — still ACCEPT via causation."""
        root = _make_envelope(timestamp=_LATER)
        child = _make_envelope(
            event_id="evt-002",
            causation_id="evt-001",
            timestamp=_EARLIER,
            idempotency_key="idem-002",
        )
        seen = {root.event_id: root}
        result = classify_event_delivery(child, seen, {})
        assert result == EventDeliveryDisposition.ACCEPT


# ===========================================================================
# SECTION 9: REDELIVERY DETERMINISTIC RECLASSIFICATION
# ===========================================================================


class TestRedeliveryReclassification:
    """Prove deterministic reclassification on redelivery."""

    def test_full_redelivery_lifecycle(self):
        """1. child arrives first => OUT_OF_ORDER
        2. causal predecessor becomes part of seen snapshot
        3. same child is evaluated again => ACCEPT
        4. after child itself is recorded, same child again => DUPLICATE"""

        root = _make_root()
        child = _make_child()

        # Step 1: child arrives, cause unseen
        r1 = classify_event_delivery(child, {}, {})
        assert r1 == EventDeliveryDisposition.OUT_OF_ORDER

        # Step 2: root becomes visible
        seen = {root.event_id: root}
        idem = {(root.change_id, root.idempotency_key): root.event_id}

        # Step 3: same child re-evaluated
        r2 = classify_event_delivery(child, seen, idem)
        assert r2 == EventDeliveryDisposition.ACCEPT

        # Step 4: child now also recorded
        seen[child.event_id] = child
        idem[(child.change_id, child.idempotency_key)] = child.event_id

        r3 = classify_event_delivery(child, seen, idem)
        assert r3 == EventDeliveryDisposition.DUPLICATE


# ===========================================================================
# SECTION 10: IDENTITY-CONFLICT NON-MUTATION PROOF
# ===========================================================================


class TestConflictNonMutation:
    """Prove classifier does not mutate either side on conflict."""

    def test_conflict_does_not_mutate_existing(self):
        original = _make_root()
        altered = _make_envelope(producer_revision="agent-v9.9.9")

        # Deep-copy for comparison
        original_copy = copy.deepcopy(original)
        altered_copy = copy.deepcopy(altered)

        seen = {original.event_id: original}
        result = classify_event_delivery(altered, seen, {})

        assert result == EventDeliveryDisposition.CONFLICT
        # Neither side mutated
        assert original == original_copy
        assert altered == altered_copy
        # Stored envelope unchanged
        assert seen[original.event_id] == original_copy

    def test_conflict_does_not_mutate_incoming(self):
        original = _make_root()
        altered = _make_envelope(timestamp=_LATER)
        altered_snapshot = altered.model_dump()

        seen = {original.event_id: original}
        classify_event_delivery(altered, seen, {})

        assert altered.model_dump() == altered_snapshot


# ===========================================================================
# SECTION 11: PROVIDER-NEUTRALITY (AST IMPORT SCAN)
# ===========================================================================


class TestProviderNeutrality:
    """AST scan of event_envelope.py for forbidden provider imports."""

    def test_no_forbidden_imports(self):
        source_path = pathlib.Path(
            domain.contracts.event_envelope.__file__
        )
        tree = ast.parse(source_path.read_text())
        forbidden_prefixes = (
            "google",
            "pubsub",
            "firestore",
            "vertexai",
            "github",
            "opentelemetry",
            "pytest",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in forbidden_prefixes:
                        assert not alias.name.startswith(prefix), (
                            f"Forbidden import '{alias.name}' in event_envelope.py"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for prefix in forbidden_prefixes:
                        assert not node.module.startswith(prefix), (
                            f"Forbidden import-from '{node.module}' in event_envelope.py"
                        )

    def test_no_fixture_or_test_imports(self):
        source_path = pathlib.Path(
            domain.contracts.event_envelope.__file__
        )
        tree = ast.parse(source_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "fixture" not in alias.name.lower(), (
                        f"Fixture import '{alias.name}' in event_envelope.py"
                    )
                    assert "test" not in alias.name.lower() or alias.name == "datetime", (
                        f"Test import '{alias.name}' in event_envelope.py"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "fixture" not in node.module.lower()
                    assert "test" not in node.module.lower() or node.module == "datetime"


# ===========================================================================
# SECTION 12: CREDENTIAL-SURFACE ABSENCE
# ===========================================================================


class TestCredentialSurface:
    """No credential-related fields in EventEnvelope."""

    def test_no_credential_fields(self):
        forbidden = {
            "token", "secret", "credential", "api_key", "private_key",
            "service_account", "session", "client", "password",
            "access_token", "refresh_token",
        }
        field_names = set(EventEnvelope.model_fields.keys())
        for name in forbidden:
            assert name not in field_names, (
                f"Credential field '{name}' found in EventEnvelope"
            )

    def test_no_credential_substrings_in_field_names(self):
        credential_substrings = (
            "token", "secret", "credential", "api_key", "private_key",
            "service_account", "password",
        )
        for field_name in EventEnvelope.model_fields.keys():
            for sub in credential_substrings:
                assert sub not in field_name.lower(), (
                    f"Credential substring '{sub}' in field '{field_name}'"
                )


# ===========================================================================
# SECTION 13: P-05.06 NON-LEAKAGE
# ===========================================================================


class TestP0506NonLeakage:
    """P-05.05 must NOT prematurely freeze P-05.06 concerns."""

    def test_no_hash_algorithm_field(self):
        """No canonical hash algorithm defined."""
        fields = set(EventEnvelope.model_fields.keys())
        for name in ("hash_algorithm", "digest_algorithm", "hash"):
            assert name not in fields

    def test_no_serialization_format_field(self):
        """No canonical JSON/byte format frozen."""
        fields = set(EventEnvelope.model_fields.keys())
        for name in ("wire_format", "serialization_format",
                      "canonical_json", "byte_format"):
            assert name not in fields

    def test_no_redaction_field(self):
        """No redaction algorithm defined."""
        fields = set(EventEnvelope.model_fields.keys())
        for name in ("redaction_policy", "redacted_fields", "redaction"):
            assert name not in fields

    def test_source_module_no_hash_implementation(self):
        """event_envelope.py source does not contain hash algorithm code."""
        source = pathlib.Path(
            domain.contracts.event_envelope.__file__
        ).read_text()
        # Exclude comments/docstrings by checking for actual code patterns
        for pattern in ("hashlib", "sha256", "sha512", "md5("):
            assert pattern not in source, (
                f"P-05.06 hash implementation '{pattern}' in event_envelope.py"
            )


# ===========================================================================
# SECTION 14: PUBLIC EXPORTS
# ===========================================================================


class TestPublicExports:
    """P-05.05 exports are present in domain.contracts.__all__."""

    def test_event_envelope_exported(self):
        assert "EventEnvelope" in domain.contracts.__all__

    def test_delivery_disposition_exported(self):
        assert "EventDeliveryDisposition" in domain.contracts.__all__

    def test_classify_function_exported(self):
        assert "classify_event_delivery" in domain.contracts.__all__

    def test_prior_exports_preserved(self):
        """P-05.01 through P-05.04 exports are still present."""
        exports = set(domain.contracts.__all__)
        p05_01 = {"DataClassLevel", "DataClass", "SuccessCriterion",
                   "ChangeRequest", "AgentDescriptor", "ToolDescriptor"}
        p05_02 = {"ChangeState", "IllegalTransitionError",
                   "CHANGE_LIFECYCLE_VERSION", "can_transition",
                   "require_transition", "is_terminal"}
        p05_03 = {"EvidenceRecord", "EvidenceState",
                   "ExecutionEvidenceMode", "Provenance",
                   "TraceReference", "ArtifactHash"}
        p05_04 = {"MemoryRecord", "MemoryTrustStatus",
                   "CapabilityPassport", "RehearsalScenario",
                   "RehearsalResult", "FaultInjectionSpec",
                   "AutonomyClass", "AutonomyDecision",
                   "ApprovalCompressionCard"}
        for name in p05_01 | p05_02 | p05_03 | p05_04:
            assert name in exports, f"Prior export '{name}' missing"


# ===========================================================================
# SECTION 15: VERSIONING
# ===========================================================================


class TestVersioning:
    """EventEnvelope requires explicit non-blank schema_version."""

    def test_version_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_envelope(schema_version="  ")

    def test_version_present(self):
        env = _make_envelope()
        assert env.schema_version == "1.0"
