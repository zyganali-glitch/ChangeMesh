"""P-05.06 contract conventions — comprehensive test suite.

Tests for naming, enum, timestamp, hashing, redaction, and
serialization conventions frozen in domain/contracts/conventions.py.
"""

import ast
import hashlib
import importlib
import math
import pathlib
import re
from datetime import datetime, timedelta, timezone
from collections import Counter

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

import domain.contracts
import domain.contracts.conventions as conv
from domain.contracts import (
    ArtifactHash,
    HashAlgorithm,
    sha256_hex,
    is_valid_sha256_digest,
    normalize_utc_datetime,
    format_utc_timestamp,
    parse_utc_timestamp,
    REDACTION_SENTINEL,
    SECRET_KEY_PATTERNS,
    redact_mapping,
    canonical_json_bytes,
    canonical_model_sha256,
)
from domain.contracts import (
    DataClassLevel,
    ChangeState,
    ExecutionEvidenceMode,
    EvidenceState,
    MemoryTrustStatus,
    AutonomyClass,
    EventDeliveryDisposition,
)


# ===========================================================================
# SECTION 1: HASH ALGORITHM CONVENTION
# ===========================================================================


class TestHashAlgorithm:
    """Canonical hash algorithm enum."""

    def test_single_member(self):
        assert len(HashAlgorithm) == 1

    def test_canonical_value(self):
        assert HashAlgorithm.SHA256.value == "sha256"

    def test_is_string_enum(self):
        assert isinstance(HashAlgorithm.SHA256, str)

    def test_rejects_aliases(self):
        """No SHA-256 / SHA256 / sha-256 / Sha256 aliases."""
        accepted_values = {m.value for m in HashAlgorithm}
        for alias in ("SHA256", "SHA-256", "sha-256", "Sha256", "SHA_256"):
            assert alias not in accepted_values


class TestSha256Hex:
    """SHA-256 helper function."""

    def test_empty_bytes_known_vector(self):
        """Standard SHA-256 of empty bytes."""
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_hex(b"") == expected
        assert sha256_hex(b"") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_same_bytes_same_digest(self):
        assert sha256_hex(b"hello") == sha256_hex(b"hello")

    def test_changed_byte_different_digest(self):
        assert sha256_hex(b"hello") != sha256_hex(b"hellp")

    def test_digest_lowercase(self):
        d = sha256_hex(b"test")
        assert d == d.lower()

    def test_digest_length(self):
        assert len(sha256_hex(b"test")) == 64

    def test_digest_hex_only(self):
        d = sha256_hex(b"test")
        assert re.match(r"^[0-9a-f]{64}$", d)


class TestDigestValidation:
    """SHA-256 digest format validation."""

    def test_valid_digest(self):
        d = sha256_hex(b"test")
        assert is_valid_sha256_digest(d)

    def test_short_string_rejected(self):
        assert not is_valid_sha256_digest("abc")

    def test_uppercase_rejected(self):
        d = sha256_hex(b"test").upper()
        assert not is_valid_sha256_digest(d)

    def test_prefix_rejected(self):
        assert not is_valid_sha256_digest("0x" + sha256_hex(b"test"))

    def test_63_chars_rejected(self):
        assert not is_valid_sha256_digest("a" * 63)

    def test_65_chars_rejected(self):
        assert not is_valid_sha256_digest("a" * 65)

    def test_empty_rejected(self):
        assert not is_valid_sha256_digest("")

    def test_non_hex_rejected(self):
        assert not is_valid_sha256_digest("g" * 64)


# ===========================================================================
# SECTION 2: ARTIFACT HASH CANONICAL CONVENTION
# ===========================================================================


_VALID_DIGEST = sha256_hex(b"test-artifact")


class TestArtifactHashConvention:
    """ArtifactHash uses typed HashAlgorithm and validated digest."""

    def test_accepts_canonical(self):
        h = ArtifactHash(
            schema_version="1.0",
            algorithm=HashAlgorithm.SHA256,
            digest=_VALID_DIGEST,
        )
        assert h.algorithm == HashAlgorithm.SHA256
        assert h.digest == _VALID_DIGEST

    def test_accepts_string_sha256(self):
        """String 'sha256' coerces to HashAlgorithm.SHA256."""
        h = ArtifactHash(
            schema_version="1.0",
            algorithm="sha256",
            digest=_VALID_DIGEST,
        )
        assert h.algorithm == HashAlgorithm.SHA256

    def test_rejects_md5(self):
        with pytest.raises(ValidationError):
            ArtifactHash(
                schema_version="1.0", algorithm="md5", digest=_VALID_DIGEST
            )

    def test_rejects_sha1(self):
        with pytest.raises(ValidationError):
            ArtifactHash(
                schema_version="1.0", algorithm="sha1", digest=_VALID_DIGEST
            )

    def test_rejects_sha512(self):
        with pytest.raises(ValidationError):
            ArtifactHash(
                schema_version="1.0", algorithm="sha512", digest=_VALID_DIGEST
            )

    def test_rejects_sha_256_alias(self):
        with pytest.raises(ValidationError):
            ArtifactHash(
                schema_version="1.0", algorithm="SHA-256", digest=_VALID_DIGEST
            )

    def test_rejects_sha_256_lower_alias(self):
        with pytest.raises(ValidationError):
            ArtifactHash(
                schema_version="1.0", algorithm="sha-256", digest=_VALID_DIGEST
            )

    def test_rejects_malformed_digest(self):
        with pytest.raises(ValidationError, match="64 lowercase hex"):
            ArtifactHash(
                schema_version="1.0", algorithm="sha256", digest="abc"
            )

    def test_rejects_short_digest(self):
        with pytest.raises(ValidationError):
            ArtifactHash(
                schema_version="1.0", algorithm="sha256", digest="a" * 63
            )

    def test_rejects_uppercase_digest(self):
        with pytest.raises(ValidationError):
            ArtifactHash(
                schema_version="1.0",
                algorithm="sha256",
                digest=_VALID_DIGEST.upper(),
            )

    def test_immutable(self):
        h = ArtifactHash(
            schema_version="1.0",
            algorithm="sha256",
            digest=_VALID_DIGEST,
        )
        with pytest.raises(ValidationError):
            h.digest = "different"

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            ArtifactHash(
                schema_version="1.0",
                algorithm="sha256",
                digest=_VALID_DIGEST,
                extra_field="bad",
            )


# ===========================================================================
# SECTION 3: TIMESTAMP CONVENTION
# ===========================================================================


class TestTimestampNormalization:
    """UTC-aware timestamp normalization."""

    def test_aware_utc_accepted(self):
        dt = datetime(2026, 8, 13, 20, 0, 0, tzinfo=timezone.utc)
        result = normalize_utc_datetime(dt)
        assert result.tzinfo is not None
        assert result == dt

    def test_aware_non_utc_normalized(self):
        est = timezone(timedelta(hours=-5))
        dt = datetime(2026, 8, 13, 15, 0, 0, tzinfo=est)
        result = normalize_utc_datetime(dt)
        assert result.tzinfo == timezone.utc
        assert result.hour == 20  # 15:00 EST = 20:00 UTC

    def test_naive_rejected(self):
        with pytest.raises(ValueError, match="Naive datetime rejected"):
            normalize_utc_datetime(datetime(2026, 8, 13, 20, 0, 0))


class TestTimestampFormatting:
    """Canonical UTC wire format."""

    def test_format_ends_with_z(self):
        dt = datetime(2026, 8, 13, 20, 8, 25, tzinfo=timezone.utc)
        result = format_utc_timestamp(dt)
        assert result.endswith("Z")

    def test_fixed_microsecond_precision(self):
        dt = datetime(2026, 8, 13, 20, 8, 25, tzinfo=timezone.utc)
        result = format_utc_timestamp(dt)
        assert result == "2026-08-13T20:08:25.000000Z"

    def test_with_microseconds(self):
        dt = datetime(2026, 8, 13, 20, 8, 25, 123456, tzinfo=timezone.utc)
        result = format_utc_timestamp(dt)
        assert result == "2026-08-13T20:08:25.123456Z"

    def test_naive_rejected(self):
        with pytest.raises(ValueError):
            format_utc_timestamp(datetime(2026, 8, 13))

    def test_non_utc_normalized_before_format(self):
        est = timezone(timedelta(hours=-5))
        dt = datetime(2026, 8, 13, 15, 0, 0, tzinfo=est)
        result = format_utc_timestamp(dt)
        assert result == "2026-08-13T20:00:00.000000Z"


class TestTimestampParsing:
    """Strict canonical timestamp parsing."""

    def test_round_trip(self):
        dt = datetime(2026, 8, 13, 20, 8, 25, 123456, tzinfo=timezone.utc)
        wire = format_utc_timestamp(dt)
        parsed = parse_utc_timestamp(wire)
        assert parsed == dt

    def test_result_is_utc_aware(self):
        parsed = parse_utc_timestamp("2026-08-13T20:08:25.000000Z")
        assert parsed.tzinfo == timezone.utc

    def test_locale_format_rejected(self):
        with pytest.raises(ValueError, match="Invalid canonical timestamp"):
            parse_utc_timestamp("13/08/2026 20:08:25")

    def test_no_z_suffix_rejected(self):
        with pytest.raises(ValueError):
            parse_utc_timestamp("2026-08-13T20:08:25.000000")

    def test_no_microseconds_rejected(self):
        with pytest.raises(ValueError):
            parse_utc_timestamp("2026-08-13T20:08:25Z")


class TestCrossTimezoneEquivalence:
    """Equivalent instants in different offsets canonicalize identically."""

    def test_same_instant_different_offsets(self):
        utc_dt = datetime(2026, 8, 13, 20, 0, 0, tzinfo=timezone.utc)
        est_dt = datetime(2026, 8, 13, 15, 0, 0,
                          tzinfo=timezone(timedelta(hours=-5)))
        jst_dt = datetime(2026, 8, 14, 5, 0, 0,
                          tzinfo=timezone(timedelta(hours=9)))

        assert format_utc_timestamp(utc_dt) == format_utc_timestamp(est_dt)
        assert format_utc_timestamp(utc_dt) == format_utc_timestamp(jst_dt)


# ===========================================================================
# SECTION 4: REDACTION CONVENTION
# ===========================================================================


class TestRedactionSentinel:
    """Canonical redaction sentinel."""

    def test_exact_value(self):
        assert REDACTION_SENTINEL == "[REDACTED]"


class TestSecretKeyRedaction:
    """Structural secret-key redaction."""

    @pytest.mark.parametrize("key", [
        "token", "access_token", "refresh_token", "api_key",
        "secret", "password", "private_key", "credential",
        "credentials", "service_account",
    ])
    def test_known_secret_redacted(self, key):
        result = redact_mapping({key: "super-secret-value"})
        assert result[key] == REDACTION_SENTINEL

    def test_ordinary_field_preserved(self):
        result = redact_mapping({"name": "Alice", "age": 30})
        assert result == {"name": "Alice", "age": 30}

    def test_nested_secret_redacted(self):
        data = {"config": {"api_key": "secret123", "host": "example.com"}}
        result = redact_mapping(data)
        assert result["config"]["api_key"] == REDACTION_SENTINEL
        assert result["config"]["host"] == "example.com"

    def test_secret_in_list_of_dicts(self):
        data = {"items": [{"token": "abc"}, {"name": "ok"}]}
        result = redact_mapping(data)
        assert result["items"][0]["token"] == REDACTION_SENTINEL
        assert result["items"][1]["name"] == "ok"

    def test_case_insensitive_matching(self):
        result = redact_mapping({"TOKEN": "secret"})
        assert result["TOKEN"] == REDACTION_SENTINEL

    def test_input_not_mutated(self):
        original = {"token": "secret", "name": "Alice"}
        original_copy = dict(original)
        redact_mapping(original)
        assert original == original_copy

    def test_secret_value_absent_in_result(self):
        result = redact_mapping({"api_key": "MY_SUPER_SECRET"})
        # The secret value must not appear anywhere in the result
        import json
        serialized = json.dumps(result)
        assert "MY_SUPER_SECRET" not in serialized

    def test_redaction_does_not_hash_secret(self):
        """Redaction replaces with sentinel, not a hash."""
        result = redact_mapping({"password": "secret123"})
        assert result["password"] == REDACTION_SENTINEL
        assert result["password"] != sha256_hex(b"secret123")


# ===========================================================================
# SECTION 5: SERIALIZATION CONVENTION
# ===========================================================================


class TestCanonicalJsonBytes:
    """Deterministic canonical JSON serialization."""

    def test_sorted_keys(self):
        result = canonical_json_bytes({"b": 1, "a": 2})
        assert b'"a":2' in result
        assert result.index(b'"a"') < result.index(b'"b"')

    def test_compact_separators(self):
        result = canonical_json_bytes({"a": 1})
        assert b'{"a":1}' == result

    def test_enum_serialized_as_value(self):
        result = canonical_json_bytes({"state": EvidenceState.PASS})
        assert b'"PASS"' in result

    def test_datetime_serialized_canonical(self):
        dt = datetime(2026, 8, 13, 20, 0, 0, tzinfo=timezone.utc)
        result = canonical_json_bytes({"ts": dt})
        assert b'"2026-08-13T20:00:00.000000Z"' in result

    def test_equivalent_timezone_offsets_identical(self):
        utc = datetime(2026, 8, 13, 20, 0, 0, tzinfo=timezone.utc)
        est = datetime(2026, 8, 13, 15, 0, 0,
                       tzinfo=timezone(timedelta(hours=-5)))
        assert canonical_json_bytes({"ts": utc}) == canonical_json_bytes({"ts": est})

    def test_tuple_as_array(self):
        result = canonical_json_bytes({"items": (1, 2, 3)})
        assert b'[1,2,3]' in result

    def test_none_as_null(self):
        result = canonical_json_bytes({"x": None})
        assert b'"x":null' in result

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="NaN"):
            canonical_json_bytes({"x": float("nan")})

    def test_infinity_rejected(self):
        with pytest.raises(ValueError, match="NaN"):
            canonical_json_bytes({"x": float("inf")})

    def test_unsupported_type_rejected(self):
        with pytest.raises(TypeError, match="Unsupported type"):
            canonical_json_bytes({"x": object()})

    def test_bytes_rejected(self):
        with pytest.raises(TypeError, match="bytes"):
            canonical_json_bytes({"x": b"raw"})

    def test_dict_order_does_not_change_bytes(self):
        d1 = {"z": 1, "a": 2, "m": 3}
        d2 = {"a": 2, "m": 3, "z": 1}
        assert canonical_json_bytes(d1) == canonical_json_bytes(d2)

    def test_non_ascii_deterministic(self):
        result = canonical_json_bytes({"name": "Üniversite"})
        assert "Üniversite".encode("utf-8") in result

    def test_utf8_encoding(self):
        result = canonical_json_bytes({"name": "Türkçe"})
        assert isinstance(result, bytes)
        # Should be valid UTF-8
        result.decode("utf-8")


class TestCanonicalModelSha256:
    """Canonical model hash."""

    def test_equivalent_models_same_digest(self):
        class TestModel(BaseModel):
            model_config = ConfigDict(frozen=True)
            a: int
            b: str

        m1 = TestModel(a=1, b="hello")
        m2 = TestModel(a=1, b="hello")
        assert canonical_model_sha256(m1) == canonical_model_sha256(m2)

    def test_different_models_different_digest(self):
        class TestModel(BaseModel):
            model_config = ConfigDict(frozen=True)
            a: int
            b: str

        m1 = TestModel(a=1, b="hello")
        m2 = TestModel(a=2, b="hello")
        assert canonical_model_sha256(m1) != canonical_model_sha256(m2)

    def test_digest_is_valid_sha256(self):
        class TestModel(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: str

        d = canonical_model_sha256(TestModel(x="test"))
        assert is_valid_sha256_digest(d)

    def test_construction_order_irrelevant(self):
        class TestModel(BaseModel):
            model_config = ConfigDict(frozen=True)
            z: int
            a: str

        m1 = TestModel(z=1, a="hello")
        m2 = TestModel(a="hello", z=1)
        assert canonical_model_sha256(m1) == canonical_model_sha256(m2)


# ===========================================================================
# SECTION 6: ENUM VOCABULARY FREEZE
# ===========================================================================


class TestEnumVocabularyFreeze:
    """Verify exact frozen enum vocabularies."""

    def test_execution_evidence_mode_values(self):
        assert set(m.value for m in ExecutionEvidenceMode) == {
            "FIXTURE", "SIMULATION", "RECORDED_CLOUD", "LIVE_WRITE",
        }

    def test_evidence_state_values(self):
        assert set(m.value for m in EvidenceState) == {
            "PASS", "WARN", "FAIL", "NOT_RUN",
            "SIMULATED", "BLOCKED", "QUARANTINED",
        }

    def test_autonomy_class_values(self):
        assert set(m.value for m in AutonomyClass) == {
            "AUTO_EXECUTE", "AUTO_EXECUTE_AND_NOTIFY",
            "REHEARSE_THEN_EXECUTE", "HUMAN_AUTHORITY_REQUIRED",
            "BLOCKED",
        }

    def test_event_delivery_disposition_values(self):
        assert set(m.value for m in EventDeliveryDisposition) == {
            "ACCEPT", "DUPLICATE", "OUT_OF_ORDER", "CONFLICT",
        }

    def test_data_class_level_values(self):
        assert set(m.value for m in DataClassLevel) == {
            "PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED",
        }

    def test_memory_trust_status_values(self):
        assert set(m.value for m in MemoryTrustStatus) == {
            "UNTRUSTED", "TRUSTED", "QUARANTINED",
        }

    def test_hash_algorithm_values(self):
        assert set(m.value for m in HashAlgorithm) == {"sha256"}


class TestEnumNoDuplicateSynonyms:
    """No duplicate aliases within one enum."""

    @pytest.mark.parametrize("enum_cls", [
        DataClassLevel,
        ChangeState,
        ExecutionEvidenceMode,
        EvidenceState,
        MemoryTrustStatus,
        AutonomyClass,
        EventDeliveryDisposition,
        HashAlgorithm,
    ])
    def test_no_duplicate_values_within_enum(self, enum_cls):
        values = [m.value for m in enum_cls]
        counter = Counter(values)
        duplicates = {v: c for v, c in counter.items() if c > 1}
        assert not duplicates, f"Duplicate values in {enum_cls.__name__}: {duplicates}"

    @pytest.mark.parametrize("enum_cls", [
        DataClassLevel,
        ChangeState,
        ExecutionEvidenceMode,
        EvidenceState,
        MemoryTrustStatus,
        AutonomyClass,
        EventDeliveryDisposition,
        HashAlgorithm,
    ])
    def test_no_duplicate_names_within_enum(self, enum_cls):
        names = [m.name for m in enum_cls]
        counter = Counter(names)
        duplicates = {n: c for n, c in counter.items() if c > 1}
        assert not duplicates, f"Duplicate names in {enum_cls.__name__}: {duplicates}"


class TestEnumLocaleNeutrality:
    """All enum values are ASCII, UPPER_SNAKE_CASE."""

    _ALL_ENUMS = [
        DataClassLevel,
        ChangeState,
        ExecutionEvidenceMode,
        EvidenceState,
        MemoryTrustStatus,
        AutonomyClass,
        EventDeliveryDisposition,
        HashAlgorithm,
    ]

    @pytest.mark.parametrize("enum_cls", _ALL_ENUMS)
    def test_values_are_ascii(self, enum_cls):
        for m in enum_cls:
            assert m.value.isascii(), (
                f"{enum_cls.__name__}.{m.name} = {m.value!r} is not ASCII"
            )

    @pytest.mark.parametrize("enum_cls", _ALL_ENUMS)
    def test_member_names_upper_snake(self, enum_cls):
        for m in enum_cls:
            assert re.match(r"^[A-Z][A-Z0-9_]*$", m.name), (
                f"{enum_cls.__name__}.{m.name} does not match UPPER_SNAKE_CASE"
            )


# ===========================================================================
# SECTION 7: NAMING CONVENTION LINT
# ===========================================================================


_CONTRACTS_DIR = pathlib.Path(domain.contracts.__file__).parent

_CONTRACT_MODULES = [
    "domain.contracts.change_request",
    "domain.contracts.success_criterion",
    "domain.contracts.agent_descriptor",
    "domain.contracts.tool_descriptor",
    "domain.contracts.data_class",
    "domain.contracts.evidence",
    "domain.contracts.change_lifecycle",
    "domain.contracts.memory",
    "domain.contracts.capability",
    "domain.contracts.rehearsal",
    "domain.contracts.autonomy",
    "domain.contracts.event_envelope",
    "domain.contracts.conventions",
]


class TestNamingConventions:
    """Domain contract naming lint."""

    @pytest.mark.parametrize("module_name", _CONTRACT_MODULES)
    def test_public_classes_pascal_case(self, module_name):
        mod = importlib.import_module(module_name)
        source = pathlib.Path(mod.__file__).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                assert re.match(r"^[A-Z][a-zA-Z0-9]*$", node.name), (
                    f"{module_name}.{node.name} is not PascalCase"
                )

    @pytest.mark.parametrize("module_name", _CONTRACT_MODULES)
    def test_public_functions_snake_case(self, module_name):
        mod = importlib.import_module(module_name)
        source = pathlib.Path(mod.__file__).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                assert re.match(r"^[a-z][a-z0-9_]*$", node.name), (
                    f"{module_name}.{node.name} is not snake_case"
                )

    def test_schema_version_spelling(self):
        """No schemaVersion/schema_ver/version_schema synonyms."""
        for module_name in _CONTRACT_MODULES:
            mod = importlib.import_module(module_name)
            source = pathlib.Path(mod.__file__).read_text()
            for bad in ("schemaVersion", "schema_ver", "version_schema"):
                assert not re.search(rf"\b{bad}\b", source), (
                    f"Non-canonical schema_version synonym '{bad}' in {module_name}"
                )


class TestCredentialFieldAbsence:
    """No credential fields in domain contracts."""

    _FORBIDDEN_FIELDS = {
        "token", "access_token", "refresh_token", "api_key",
        "secret", "password", "private_key", "credential",
        "credentials", "service_account", "client_secret",
    }

    @pytest.mark.parametrize("module_name", _CONTRACT_MODULES)
    def test_no_credential_fields(self, module_name):
        mod = importlib.import_module(module_name)
        source = pathlib.Path(mod.__file__).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        assert item.target.id not in self._FORBIDDEN_FIELDS, (
                            f"Credential field '{item.target.id}' in {module_name}.{node.name}"
                        )


# ===========================================================================
# SECTION 8: PROVIDER-NEUTRALITY
# ===========================================================================


class TestProviderNeutrality:
    """No provider imports in conventions or domain contracts."""

    _FORBIDDEN_IMPORTS = {
        "google", "vertexai", "pubsub", "firestore",
        "github", "opentelemetry",
    }

    def test_conventions_module_clean(self):
        source = (_CONTRACTS_DIR / "conventions.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for forbidden in self._FORBIDDEN_IMPORTS:
                        assert forbidden not in node.module, (
                            f"Provider import '{node.module}' in conventions.py"
                        )

    @pytest.mark.parametrize("module_name", _CONTRACT_MODULES)
    def test_contract_modules_clean(self, module_name):
        mod = importlib.import_module(module_name)
        source = pathlib.Path(mod.__file__).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for forbidden in self._FORBIDDEN_IMPORTS:
                        assert forbidden not in node.module, (
                            f"Provider import '{node.module}' in {module_name}"
                        )


# ===========================================================================
# SECTION 9: IDENTITY / FIELD NAMING DISTINCTIONS
# ===========================================================================


class TestIdentityDistinctions:
    """Intentional semantic identity distinctions preserved."""

    def test_distinct_id_fields_exist(self):
        """Multiple semantically different *_id fields coexist."""
        from domain.contracts import ChangeRequest, EvidenceRecord, EventEnvelope
        from domain.contracts import MemoryRecord, CapabilityPassport
        from domain.contracts import RehearsalScenario, RehearsalResult
        from domain.contracts import AutonomyDecision, ApprovalCompressionCard

        # request_id is the identity of a ChangeRequest
        assert "request_id" in ChangeRequest.model_fields
        # change_request_id is a reference to that request in other contracts
        assert "change_request_id" in EvidenceRecord.model_fields
        # change_id is the durable change/saga/event identity
        assert "change_id" in EventEnvelope.model_fields
        # event_id is the identity of one logical domain event
        assert "event_id" in EventEnvelope.model_fields
        # Other distinct identities
        assert "memory_id" in MemoryRecord.model_fields
        assert "passport_id" in CapabilityPassport.model_fields
        assert "scenario_id" in RehearsalScenario.model_fields
        assert "result_id" in RehearsalResult.model_fields
        assert "decision_id" in AutonomyDecision.model_fields
        assert "card_id" in ApprovalCompressionCard.model_fields
        assert "evidence_id" in EvidenceRecord.model_fields


# ===========================================================================
# SECTION 10: P-05.05 EVENT ENVELOPE REGRESSION
# ===========================================================================


class TestEventEnvelopeTimestampRegression:
    """P-05.06 conventions must NOT break P-05.05 causal semantics."""

    def test_timestamp_not_causal_authority(self):
        """Reversed timestamps do NOT alter causal result."""
        from domain.contracts import EventEnvelope, classify_event_delivery, EventDeliveryDisposition

        cause = EventEnvelope(
            schema_version="1.0",
            event_id="cause-1",
            change_id="change-1",
            correlation_id="corr-1",
            producer_revision="rev-1",
            timestamp=datetime(2026, 8, 14, 0, 0, 0, tzinfo=timezone.utc),
            idempotency_key="idem-cause",
        )

        # Child has EARLIER timestamp than cause
        child = EventEnvelope(
            schema_version="1.0",
            event_id="child-1",
            change_id="change-1",
            causation_id="cause-1",
            correlation_id="corr-1",
            producer_revision="rev-1",
            timestamp=datetime(2026, 8, 13, 0, 0, 0, tzinfo=timezone.utc),
            idempotency_key="idem-child",
        )

        result = classify_event_delivery(
            child,
            {"cause-1": cause},
            {},
        )
        assert result == EventDeliveryDisposition.ACCEPT

    def test_exact_replay_still_duplicate(self):
        from domain.contracts import EventEnvelope, classify_event_delivery, EventDeliveryDisposition

        env = EventEnvelope(
            schema_version="1.0",
            event_id="evt-1",
            change_id="change-1",
            correlation_id="corr-1",
            producer_revision="rev-1",
            timestamp=datetime(2026, 8, 13, 20, 0, 0, tzinfo=timezone.utc),
            idempotency_key="idem-1",
        )

        result = classify_event_delivery(env, {"evt-1": env}, {})
        assert result == EventDeliveryDisposition.DUPLICATE


# ===========================================================================
# SECTION 11: P-05.03 EVIDENCE REGRESSION
# ===========================================================================


class TestEvidenceRegression:
    """P-05.06 conventions must NOT weaken evidence semantics."""

    def test_fail_cannot_become_pass(self):
        """EvidenceState.FAIL and PASS remain distinct."""
        assert EvidenceState.FAIL != EvidenceState.PASS
        assert EvidenceState.FAIL.value == "FAIL"
        assert EvidenceState.PASS.value == "PASS"

    def test_not_run_cannot_become_pass(self):
        assert EvidenceState.NOT_RUN != EvidenceState.PASS
        assert EvidenceState.NOT_RUN.value == "NOT_RUN"

    def test_simulation_cannot_become_live_write(self):
        assert ExecutionEvidenceMode.SIMULATION != ExecutionEvidenceMode.LIVE_WRITE
        assert ExecutionEvidenceMode.SIMULATION.value == "SIMULATION"
        assert ExecutionEvidenceMode.LIVE_WRITE.value == "LIVE_WRITE"

    def test_state_and_mode_orthogonal(self):
        """EvidenceState and ExecutionEvidenceMode are different enums."""
        state_values = {m.value for m in EvidenceState}
        mode_values = {m.value for m in ExecutionEvidenceMode}
        assert state_values != mode_values


# ===========================================================================
# SECTION 12: REDACTION VS HASHING ORDER
# ===========================================================================


class TestRedactionHashingOrder:
    """Redaction and hashing ordering semantics."""

    def test_sanitized_then_hash_differs_from_original_hash(self):
        """Hash of redacted structure differs from hash of original."""
        original = {"api_key": "secret123", "name": "test"}
        sanitized = redact_mapping(original)

        hash_original = sha256_hex(canonical_json_bytes(original))
        hash_sanitized = sha256_hex(canonical_json_bytes(sanitized))

        assert hash_original != hash_sanitized

    def test_original_artifact_hash_preserved(self):
        """Original bytes → SHA-256 → digest is untouched by redaction."""
        original_bytes = b"original artifact content"
        digest = sha256_hex(original_bytes)
        assert is_valid_sha256_digest(digest)
        # The digest itself contains no secret material to redact
        assert REDACTION_SENTINEL not in digest


# ===========================================================================
# SECTION 13: PUBLIC EXPORTS
# ===========================================================================


class TestPublicExports:
    """All P-05.06 convention symbols are exported."""

    _EXPECTED_EXPORTS = {
        "HashAlgorithm",
        "is_valid_sha256_digest",
        "sha256_hex",
        "normalize_utc_datetime",
        "format_utc_timestamp",
        "parse_utc_timestamp",
        "REDACTION_SENTINEL",
        "SECRET_KEY_PATTERNS",
        "redact_mapping",
        "canonical_json_bytes",
        "canonical_model_sha256",
    }

    def test_all_convention_exports_present(self):
        exports = set(domain.contracts.__all__)
        for name in self._EXPECTED_EXPORTS:
            assert name in exports, f"Missing P-05.06 export: {name}"

    def test_prior_exports_preserved(self):
        """All P-05.01–P-05.05 exports still present."""
        exports = set(domain.contracts.__all__)
        prior = {
            "DataClassLevel", "DataClass", "SuccessCriterion",
            "ChangeRequest", "AgentDescriptor", "ToolDescriptor",
            "ChangeState", "IllegalTransitionError", "CHANGE_LIFECYCLE_VERSION",
            "can_transition", "require_transition", "is_terminal",
            "EvidenceRecord", "EvidenceState", "ExecutionEvidenceMode",
            "Provenance", "TraceReference", "ArtifactHash",
            "MemoryRecord", "MemoryTrustStatus", "CapabilityPassport",
            "RehearsalScenario", "RehearsalResult", "FaultInjectionSpec",
            "AutonomyClass", "AutonomyDecision", "ApprovalCompressionCard",
            "EventEnvelope", "EventDeliveryDisposition", "classify_event_delivery",
        }
        for name in prior:
            assert name in exports, f"Missing prior export: {name}"


# ===========================================================================
# SECTION 14: P-07+ NON-LEAKAGE
# ===========================================================================


class TestP07NonLeakage:
    """P-05.06 must not implement runtime concepts."""

    def test_no_pubsub_in_conventions(self):
        source = (_CONTRACTS_DIR / "conventions.py").read_text()
        for pattern in ("pubsub", "Pub/Sub", "publish(", "subscribe("):
            assert pattern.lower() not in source.lower(), (
                f"Runtime concept '{pattern}' in conventions.py"
            )

    def test_no_firestore_in_conventions(self):
        source = (_CONTRACTS_DIR / "conventions.py").read_text()
        for pattern in ("firestore", "Firestore"):
            assert pattern.lower() not in source.lower(), (
                f"Runtime concept '{pattern}' in conventions.py"
            )

    def test_no_adk_in_conventions(self):
        source = (_CONTRACTS_DIR / "conventions.py").read_text()
        assert "from google" not in source
        assert "import google" not in source
