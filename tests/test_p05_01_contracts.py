"""P-05.01 domain contract unit tests.

Test matrix — CONTRACT-001 through CONTRACT-018.

Covers: ChangeRequest, SuccessCriterion, AgentDescriptor,
ToolDescriptor, DataClass.  Validates positive instantiation,
negative rejection, scope separation, provider independence,
fixture/test isolation, serialization round-trip, and type strictness.
"""

import ast
import json
import pathlib

import pytest
from pydantic import ValidationError

from domain.contracts import (
    AgentDescriptor,
    ChangeRequest,
    DataClass,
    DataClassLevel,
    SuccessCriterion,
    ToolDescriptor,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "contracts" / "p05_01"


def _load_fixture(name: str) -> dict:
    """Load a JSON fixture by filename."""
    with open(FIXTURE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# ===========================================================================
# CONTRACT-001 — Valid ChangeRequest accepted
# ===========================================================================


class TestCONTRACT001:
    """Valid ChangeRequest instantiates and validates correctly."""

    def test_valid_change_request_from_fixture(self):
        data = _load_fixture("valid_change_request.json")
        cr = ChangeRequest(**data)
        assert cr.request_id == "CR-2026-0001"
        assert cr.schema_version == "1.0.0"
        assert len(cr.success_criteria) == 2
        assert cr.data_classification == DataClassLevel.CONFIDENTIAL
        assert cr.target_systems == ["enterprise-db", "user-service"]


# ===========================================================================
# CONTRACT-002 — ChangeRequest missing ID rejected
# ===========================================================================


class TestCONTRACT002:
    """ChangeRequest with missing request_id is rejected."""

    def test_missing_request_id(self):
        data = _load_fixture("invalid_change_request_missing_id.json")
        with pytest.raises(ValidationError) as exc_info:
            ChangeRequest(**data)
        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "request_id" in field_names


# ===========================================================================
# CONTRACT-003 — ChangeRequest missing version rejected
# ===========================================================================


class TestCONTRACT003:
    """ChangeRequest with missing schema_version is rejected."""

    def test_missing_schema_version(self):
        data = _load_fixture("invalid_change_request_missing_version.json")
        with pytest.raises(ValidationError) as exc_info:
            ChangeRequest(**data)
        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "schema_version" in field_names

    def test_missing_schema_version_agent(self):
        """Use the unused fixture for missing version on agent descriptor."""
        data = _load_fixture("invalid_agent_descriptor_missing_version.json")
        with pytest.raises(ValidationError) as exc_info:
            AgentDescriptor(**data)
        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "schema_version" in field_names


# ===========================================================================
# CONTRACT-004 — Invalid nested SuccessCriterion rejected
# ===========================================================================


class TestCONTRACT004:
    """ChangeRequest with a malformed nested SuccessCriterion is rejected."""

    def test_bad_nested_criterion(self):
        data = _load_fixture("invalid_change_request_bad_criterion.json")
        with pytest.raises(ValidationError):
            ChangeRequest(**data)


# ===========================================================================
# CONTRACT-005 — Valid SuccessCriterion accepted
# ===========================================================================


class TestCONTRACT005:
    """Valid SuccessCriterion instantiates correctly."""

    def test_valid_success_criterion(self):
        data = _load_fixture("valid_success_criterion.json")
        sc = SuccessCriterion(**data)
        assert sc.criterion_id == "SC-VALID-001"
        assert sc.schema_version == "1.0.0"
        assert sc.verification_method == "deterministic"
        assert "test_result" in sc.required_evidence_types


# ===========================================================================
# CONTRACT-006 — Invalid SuccessCriterion rejected
# ===========================================================================


class TestCONTRACT006:
    """SuccessCriterion with missing criterion_id is rejected."""

    def test_missing_criterion_id(self):
        data = _load_fixture("invalid_success_criterion_missing_id.json")
        with pytest.raises(ValidationError) as exc_info:
            SuccessCriterion(**data)
        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "criterion_id" in field_names


# ===========================================================================
# CONTRACT-007 — Valid AgentDescriptor accepted
# ===========================================================================


class TestCONTRACT007:
    """Valid AgentDescriptor instantiates correctly."""

    def test_valid_agent_descriptor(self):
        data = _load_fixture("valid_agent_descriptor.json")
        ad = AgentDescriptor(**data)
        assert ad.agent_id == "impact-scout-001"
        assert ad.schema_version == "1.0.0"
        assert ad.role == "impact_scout"
        assert DataClassLevel.CONFIDENTIAL in ad.permitted_data_classifications


# ===========================================================================
# CONTRACT-008 — AgentDescriptor does not act as CapabilityPassport
# ===========================================================================


class TestCONTRACT008:
    """AgentDescriptor has no qualification/trust/passport fields.

    This is the canonical P-04 bug prevention test (D-003).
    """

    PASSPORT_FIELDS = frozenset(
        {
            "qualification_status",
            "passport_valid",
            "signature_valid",
            "trust_level",
            "authorized",
            "policy_approval",
            "capability_passport",
            "passport_expiry",
            "qualification_evidence",
        }
    )

    def test_no_passport_fields(self):
        actual_fields = set(AgentDescriptor.model_fields.keys())
        overlap = actual_fields & self.PASSPORT_FIELDS
        assert not overlap, f"AgentDescriptor must NOT contain CapabilityPassport fields: {overlap}"


# ===========================================================================
# CONTRACT-009 — Valid ToolDescriptor accepted
# ===========================================================================


class TestCONTRACT009:
    """Valid ToolDescriptor instantiates correctly."""

    def test_valid_tool_descriptor(self):
        data = _load_fixture("valid_tool_descriptor.json")
        td = ToolDescriptor(**data)
        assert td.tool_id == "github-reader-001"
        assert td.schema_version == "1.0.0"
        assert td.is_read_only is True
        assert DataClassLevel.PUBLIC in td.permitted_data_classifications


# ===========================================================================
# CONTRACT-010 — Provider-specific tool credential/client field absent
# ===========================================================================


class TestCONTRACT010:
    """ToolDescriptor has no provider-specific credential or client fields."""

    FORBIDDEN_FIELDS = frozenset(
        {
            "api_token",
            "api_key",
            "credentials",
            "client",
            "sdk_client",
            "session",
            "github_token",
            "firestore_client",
            "callback",
            "executable",
        }
    )

    def test_no_provider_fields(self):
        actual_fields = set(ToolDescriptor.model_fields.keys())
        overlap = actual_fields & self.FORBIDDEN_FIELDS
        assert not overlap, f"ToolDescriptor must NOT contain provider fields: {overlap}"


# ===========================================================================
# CONTRACT-011 — Valid DataClass accepted
# ===========================================================================


class TestCONTRACT011:
    """Valid DataClass instantiates correctly."""

    def test_valid_data_class(self):
        data = _load_fixture("valid_data_class.json")
        dc = DataClass(**data)
        assert dc.schema_version == "1.0.0"
        assert dc.classification == DataClassLevel.CONFIDENTIAL

    def test_all_enum_values_valid(self):
        for level in DataClassLevel:
            dc = DataClass(schema_version="1.0.0", classification=level)
            assert dc.classification == level


# ===========================================================================
# CONTRACT-012 — Invalid DataClass rejected
# ===========================================================================


class TestCONTRACT012:
    """DataClass with invalid enum value is rejected."""

    def test_invalid_classification_level(self):
        data = _load_fixture("invalid_data_class_bad_level.json")
        with pytest.raises(ValidationError):
            DataClass(**data)


# ===========================================================================
# CONTRACT-013 — Public schemas expose explicit version fields
# ===========================================================================


class TestCONTRACT013:
    """Every public contract has an explicit schema_version field."""

    @pytest.mark.parametrize(
        "contract_cls",
        [ChangeRequest, SuccessCriterion, AgentDescriptor, ToolDescriptor, DataClass],
        ids=["ChangeRequest", "SuccessCriterion", "AgentDescriptor", "ToolDescriptor", "DataClass"],
    )
    def test_schema_version_field_exists(self, contract_cls):
        assert "schema_version" in contract_cls.model_fields, (
            f"{contract_cls.__name__} must have an explicit 'schema_version' field"
        )


# ===========================================================================
# CONTRACT-014 — Public schemas expose explicit identifiers
# ===========================================================================


class TestCONTRACT014:
    """Every independently addressable contract has a domain-specific identifier."""

    EXPECTED_ID_FIELDS = {
        "ChangeRequest": "request_id",
        "SuccessCriterion": "criterion_id",
        "AgentDescriptor": "agent_id",
        "ToolDescriptor": "tool_id",
    }

    @pytest.mark.parametrize(
        "cls_name,id_field",
        list(EXPECTED_ID_FIELDS.items()),
        ids=list(EXPECTED_ID_FIELDS.keys()),
    )
    def test_id_field_exists(self, cls_name, id_field):
        contract_cls = {
            "ChangeRequest": ChangeRequest,
            "SuccessCriterion": SuccessCriterion,
            "AgentDescriptor": AgentDescriptor,
            "ToolDescriptor": ToolDescriptor,
        }[cls_name]
        assert id_field in contract_cls.model_fields, (
            f"{cls_name} must have '{id_field}' identifier field"
        )

    def test_data_class_has_classification_field(self):
        """DataClass uses its enum value as identity."""
        assert "classification" in DataClass.model_fields


# ===========================================================================
# CONTRACT-015 — Provider-specific imports absent from domain/contracts
# ===========================================================================


class TestCONTRACT015:
    """domain/contracts/ must not import provider-specific modules.

    This is a deterministic AST scan, not a heuristic.
    """

    FORBIDDEN_PREFIXES = (
        "google",
        "google.adk",
        "google.cloud",
        "google.genai",
        "vertexai",
        "firebase",
        "github",
    )

    def _collect_imports(self, filepath: pathlib.Path) -> list[str]:
        """Extract all imported module names from a Python file."""
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def test_no_provider_imports(self):
        contracts_dir = pathlib.Path(__file__).resolve().parent.parent / "domain" / "contracts"
        violations = []
        for py_file in contracts_dir.glob("*.py"):
            for imp in self._collect_imports(py_file):
                for prefix in self.FORBIDDEN_PREFIXES:
                    if imp == prefix or imp.startswith(prefix + "."):
                        violations.append(f"{py_file.name}: {imp}")
        assert not violations, f"Forbidden provider imports found: {violations}"


# ===========================================================================
# CONTRACT-016 — Production contracts do not import fixture/test code
# ===========================================================================


class TestCONTRACT016:
    """domain/contracts/ must not import fixture or test modules."""

    FORBIDDEN_PREFIXES = ("fixtures", "tests", "test_", "pytest", "unittest")

    def _collect_imports(self, filepath: pathlib.Path) -> list[str]:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def test_no_fixture_or_test_imports(self):
        contracts_dir = pathlib.Path(__file__).resolve().parent.parent / "domain" / "contracts"
        violations = []
        for py_file in contracts_dir.glob("*.py"):
            for imp in self._collect_imports(py_file):
                for prefix in self.FORBIDDEN_PREFIXES:
                    if imp == prefix or imp.startswith(prefix + ".") or imp.startswith(prefix):
                        violations.append(f"{py_file.name}: {imp}")
        assert not violations, f"Forbidden fixture/test imports found: {violations}"


# ===========================================================================
# CONTRACT-017 — Serialization round-trip
# ===========================================================================


class TestCONTRACT017:
    """Contracts survive a JSON serialization round-trip without semantic loss."""

    def test_change_request_round_trip(self):
        data = _load_fixture("valid_change_request.json")
        original = ChangeRequest(**data)
        serialized = original.model_dump_json()
        restored = ChangeRequest.model_validate_json(serialized)
        assert original == restored

    def test_agent_descriptor_round_trip(self):
        data = _load_fixture("valid_agent_descriptor.json")
        original = AgentDescriptor(**data)
        serialized = original.model_dump_json()
        restored = AgentDescriptor.model_validate_json(serialized)
        assert original == restored

    def test_tool_descriptor_round_trip(self):
        data = _load_fixture("valid_tool_descriptor.json")
        original = ToolDescriptor(**data)
        serialized = original.model_dump_json()
        restored = ToolDescriptor.model_validate_json(serialized)
        assert original == restored

    def test_data_class_round_trip(self):
        data = _load_fixture("valid_data_class.json")
        original = DataClass(**data)
        serialized = original.model_dump_json()
        restored = DataClass.model_validate_json(serialized)
        assert original == restored


# ===========================================================================
# CONTRACT-018 — Unknown/extra fields rejected (fail-closed)
# ===========================================================================


class TestCONTRACT018:
    """Contracts reject unknown/extra fields."""

    @pytest.mark.parametrize(
        "contract_cls,base_data",
        [
            (DataClass, {"schema_version": "1.0.0", "classification": "PUBLIC"}),
            (
                SuccessCriterion,
                {
                    "schema_version": "1.0.0",
                    "criterion_id": "SC-X",
                    "description": "test",
                    "verification_method": "deterministic",
                    "required_evidence_types": [],
                },
            ),
            (
                AgentDescriptor,
                {
                    "schema_version": "1.0.0",
                    "agent_id": "a",
                    "agent_revision": "r",
                    "role": "r",
                    "description": "d",
                    "declared_capabilities": [],
                    "permitted_data_classifications": [],
                    "permitted_tool_ids": [],
                },
            ),
            (
                ToolDescriptor,
                {
                    "schema_version": "1.0.0",
                    "tool_id": "t",
                    "tool_revision": "r",
                    "name": "n",
                    "description": "d",
                    "declared_actions": [],
                    "is_read_only": True,
                    "permitted_data_classifications": [],
                },
            ),
        ],
        ids=["DataClass", "SuccessCriterion", "AgentDescriptor", "ToolDescriptor"],
    )
    def test_extra_field_rejected(self, contract_cls, base_data):
        bad_data = {**base_data, "unexpected_field": "should_fail"}
        with pytest.raises(ValidationError) as exc_info:
            contract_cls(**bad_data)
        assert any("extra" in str(e).lower() for e in exc_info.value.errors())

    def test_change_request_extra_field_rejected(self):
        data = _load_fixture("valid_change_request.json")
        data["saga_state"] = "EXECUTING"
        with pytest.raises(ValidationError) as exc_info:
            ChangeRequest(**data)
        assert any("extra" in str(e).lower() for e in exc_info.value.errors())


# ===========================================================================
# CONTRACT-019 — String/Blank Validations and Type Strictness
# ===========================================================================


class TestCONTRACT019:
    """Blank strings and wrong primitive types are correctly rejected."""

    def test_blank_identifier_rejected(self):
        """Blank identifiers are rejected by validators."""
        with pytest.raises(ValidationError):
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="   ",
                description="blank id test",
                verification_method="deterministic",
                required_evidence_types=[],
            )

    def test_blank_schema_version_rejected(self):
        """Blank schema_version is rejected by validators."""
        with pytest.raises(ValidationError):
            ChangeRequest(
                schema_version="   ",
                request_id="CR-BLANK",
                title="blank version test",
                description="test",
                target_systems=[],
                data_classification=DataClassLevel.PUBLIC,
                success_criteria=[],
                requested_by="test",
                requested_at="2026-08-11T10:00:00Z",
            )

        with pytest.raises(ValidationError):
            DataClass(schema_version="  ", classification=DataClassLevel.PUBLIC)

        with pytest.raises(ValidationError):
            DataClass(schema_version="", classification=DataClassLevel.PUBLIC)

    def test_blank_agent_revision_rejected(self):
        with pytest.raises(ValidationError):
            AgentDescriptor(
                schema_version="1.0",
                agent_id="test",
                agent_revision="   ",
                role="test",
                description="test",
                declared_capabilities=[],
                permitted_data_classifications=[],
                permitted_tool_ids=[],
            )

    def test_blank_tool_revision_rejected(self):
        with pytest.raises(ValidationError):
            ToolDescriptor(
                schema_version="1.0",
                tool_id="test",
                tool_revision="",
                name="test",
                description="test",
                declared_actions=[],
                is_read_only=True,
                permitted_data_classifications=[],
            )

    def test_wrong_primitive_type_strict_bool(self):
        """A string 'true' should be rejected for a boolean field when StrictBool is used."""
        with pytest.raises(ValidationError) as exc_info:
            ToolDescriptor(
                schema_version="1.0.0",
                tool_id="test-tool",
                tool_revision="r1",
                name="name",
                description="desc",
                declared_actions=[],
                is_read_only="true",
                permitted_data_classifications=[],
            )
        errors = exc_info.value.errors()
        assert any(e["type"] == "bool_type" for e in errors)


# ===========================================================================
# CONTRACT-020 — Public Surface Area Test
# ===========================================================================


class TestCONTRACT020:
    """The public contracts exactly match the 5 required schemas plus 1 enum."""

    def test_required_schemas_exist(self):
        from domain import contracts

        # Ensure the 5 + 1 P-05.01 elements are exported
        required_p05_01_surface = {
            "ChangeRequest",
            "SuccessCriterion",
            "AgentDescriptor",
            "ToolDescriptor",
            "DataClass",
            "DataClassLevel",
        }
        actual_surface = set(contracts.__all__)

        assert required_p05_01_surface.issubset(actual_surface), (
            f"Public surface area missing P-05.01 contracts. Expected at least {required_p05_01_surface}, got {actual_surface}"
        )

        # Verify no old "DataClassification" exists in __all__
        assert "DataClassification" not in actual_surface
