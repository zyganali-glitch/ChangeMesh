"""Tests for P-08.02 Gemini Structured Output Boundary & Schema Validation.

Validates:
1. Strict Output Validation Tests (OUT-T01 through OUT-T09):
   - OUT-T01: Missing required field -> REJECTED
   - OUT-T02: Extra field not in schema -> REJECTED (extra="forbid")
   - OUT-T03: Wrong type -> REJECTED (no silent coercion)
   - OUT-T04: Invalid enum value -> REJECTED
   - OUT-T05: Path traversal value -> REJECTED
   - OUT-T06: Unsafe endpoint/external URL -> REJECTED
   - OUT-T07: Unknown action type -> REJECTED
   - OUT-T08: Malformed JSON from model -> REJECTED, no repair
   - OUT-T09: Silent coercion attempt -> REJECTED
2. Three Semantic Reasoning Surfaces (Positive & Boundary Tests):
   - Goal Decomposition (GoalDecompositionResult)
   - Policy Explanation (PolicyExplanationResult)
   - Semantic Audit (SemanticAuditResult)
3. Structural Separation (OUT-10):
   - Structured citations, counter-evidence, and missing-evidence distinct from prose.
4. Authority Boundary Invariants (OUT-08):
   - All models belong strictly to GEMINI_SEMANTIC_JUDGMENT.
   - Attempted injection of deterministic facts or policy authority fails closed.
5. Fail-Closed JSON Parser:
   - Rejects NaN/Infinity, trailing garbage, incomplete syntax, non-dict root.
   - Handles clean markdown code blocks without fuzzy repair.
6. Architectural Integrity & Donor Compliance:
   - 0 Google SDK imports in domain/contracts.
   - Single model client owner in src/core/gemini_client.py.
   - 0 forbidden donor identifiers (ZeroKit schema, Codex identifiers).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from src.core.gemini_client import BoundedGeminiClient
from src.core.gemini_structured_output import (
    CANONICAL_AUTHORITY_LANE,
    CANONICAL_STRUCTURED_SCHEMA_VERSION,
    GoalDecompositionResult,
    PolicyComplianceStatus,
    PolicyExplanationResult,
    PolicyImpactLevel,
    SemanticAssessmentVerdict,
    SemanticAuditResult,
    SemanticRiskLevel,
    StructuredOutputJSONError,
    StructuredOutputSecurityError,
    StructuredOutputValidationError,
    build_goal_decomposition_prompt,
    build_policy_explanation_prompt,
    build_semantic_audit_prompt,
    parse_goal_decomposition_output,
    parse_policy_explanation_output,
    parse_semantic_audit_output,
    parse_structured_json,
    validate_action_type,
    validate_safe_endpoint,
    validate_safe_relative_path,
)
from tests.test_p08_01_gemini_client import (
    FakeSDKClient,
    find_model_call_violations,
    make_successful_response,
)


# ==============================================================================
# Helper Fixtures & Valid Payloads
# ==============================================================================
def make_valid_goal_decomposition_dict() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "change_request_id": "cr-payment-api-001",
        "summary": "Decompose payment API schema upgrade into ordered specialist tasks.",
        "sub_goals": [
            {
                "sub_goal_id": "sub-1",
                "title": "Analyze repository blast radius",
                "description": "Scan affected API endpoints and service dependencies.",
                "target_component": "src/api/payment_v1.py",
                "action_type": "inspect_impact",
                "priority": 1,
            },
            {
                "sub_goal_id": "sub-2",
                "title": "Verify compliance policy",
                "description": "Ensure non-breaking deprecation rules are satisfied.",
                "target_component": "policies/api_lifecycle.yaml",
                "action_type": "evaluate_policy",
                "priority": 2,
            },
        ],
        "affected_components": ["src/api/payment_v1.py", "policies/api_lifecycle.yaml"],
        "recommended_specialists": ["Impact Scout", "Policy Guardian"],
        "estimated_risk_level": "LOW",
        "rationale": "Additive migration path with verified backwards compatibility.",
        "suggested_action_types": ["inspect_impact", "evaluate_policy"],
    }


def make_valid_policy_explanation_dict() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "change_id": "chg-2026-0816-01",
        "decision_id": "dec-auto-001",
        "summary_explanation": (
            "Change qualifies for AUTO_EXECUTE_AND_NOTIFY per internal schema rule POL-04."
        ),
        "rule_explanations": [
            {
                "rule_id": "POL-04",
                "rule_name": "Additive Schema Changes",
                "explanation": (
                    "Field additions without destructive removal are permitted for automation."
                ),
                "impact_level": "LOW",
                "compliance_status": "COMPLIANT",
            }
        ],
        "compliance_considerations": [
            "Requires post-execution notification to payment engineering team.",
        ],
        "remediation_guidance": [],
        "explanation_scope": "Internal payment service API schema change",
    }


def make_valid_semantic_audit_dict() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "audit_id": "audit-sem-901",
        "change_id": "chg-2026-0816-01",
        "overall_verdict": "SUPPORTS",
        "reasoning_narrative": "Evidence demonstrates full test coverage and schema compatibility.",
        "claim_assessments": [
            {
                "claim_id": "claim-backwards-compat",
                "assessment": "SUPPORTS",
                "assessment_narrative": (
                    "Golden integration tests verify legacy payloads continue to serialize cleanly."
                ),
                "cited_evidence_keys": ["ev-test-run-44"],
                "counter_evidence_points": [],
                "missing_evidence_points": [],
            }
        ],
        "evidence_citations": [
            {
                "citation_id": "cit-01",
                "evidence_key": "ev-test-run-44",
                "relevance_summary": "Integration test run output confirming 0 regressions.",
                "supports_claim_ids": ["claim-backwards-compat"],
            }
        ],
        "counter_evidence": [],
        "missing_evidence": [],
    }


# ==============================================================================
# 1. Strict Output Validation Tests (OUT-T01 through OUT-T09)
# ==============================================================================
class TestStrictOutputValidation:
    """Validates the 9 canonical output boundary tests mandated by P-08.00."""

    def test_out_t01_missing_required_field_rejected(self) -> None:
        """OUT-T01: Missing required field in model response -> REJECTED."""
        # Goal Decomposition: missing 'summary'
        data = make_valid_goal_decomposition_dict()
        del data["summary"]
        with pytest.raises(StructuredOutputValidationError, match="summary"):
            parse_goal_decomposition_output(data)

        # Policy Explanation: missing 'decision_id'
        data_policy = make_valid_policy_explanation_dict()
        del data_policy["decision_id"]
        with pytest.raises(StructuredOutputValidationError, match="decision_id"):
            parse_policy_explanation_output(data_policy)

        # Semantic Audit: missing 'overall_verdict'
        data_audit = make_valid_semantic_audit_dict()
        del data_audit["overall_verdict"]
        with pytest.raises(StructuredOutputValidationError, match="overall_verdict"):
            parse_semantic_audit_output(data_audit)

    def test_out_t02_extra_field_rejected_via_strict_schema(self) -> None:
        """OUT-T02: Extra field not in schema -> REJECTED via extra='forbid'."""
        data = make_valid_goal_decomposition_dict()
        data["unauthorized_injected_field"] = "malicious_payload"

        with pytest.raises(StructuredOutputValidationError, match="extra"):
            parse_goal_decomposition_output(data)

        data_policy = make_valid_policy_explanation_dict()
        data_policy["extra_policy_override"] = True
        with pytest.raises(StructuredOutputValidationError, match="extra"):
            parse_policy_explanation_output(data_policy)

    def test_out_t03_wrong_type_rejected(self) -> None:
        """OUT-T03: Wrong type -> REJECTED (no silent coercion)."""
        data = make_valid_goal_decomposition_dict()
        data["sub_goals"][0]["priority"] = "high"

        with pytest.raises(StructuredOutputValidationError, match="priority"):
            parse_goal_decomposition_output(data)

        data_bad_list = make_valid_goal_decomposition_dict()
        data_bad_list["affected_components"] = "src/api/payment_v1.py"  # type: ignore[assignment]
        with pytest.raises(StructuredOutputValidationError, match="affected_components"):
            parse_goal_decomposition_output(data_bad_list)

    def test_out_t04_invalid_enum_value_rejected(self) -> None:
        """OUT-T04: Invalid enum value in model response -> REJECTED."""
        data = make_valid_goal_decomposition_dict()
        data["estimated_risk_level"] = "UNKNOWN_RISK"

        with pytest.raises(StructuredOutputValidationError, match="estimated_risk_level"):
            parse_goal_decomposition_output(data)

        data_audit = make_valid_semantic_audit_dict()
        data_audit["overall_verdict"] = "PARTIALLY_PASSED"
        with pytest.raises(StructuredOutputValidationError, match="overall_verdict"):
            parse_semantic_audit_output(data_audit)

    def test_out_t05_path_traversal_value_rejected(self) -> None:
        """OUT-T05: Path traversal (../, ..\\, etc.) in endpoint/path field -> REJECTED."""
        data = make_valid_goal_decomposition_dict()
        data["sub_goals"][0]["target_component"] = "../../etc/passwd"
        with pytest.raises(StructuredOutputSecurityError, match="path traversal"):
            parse_goal_decomposition_output(data)

        data_win = make_valid_goal_decomposition_dict()
        data_win["sub_goals"][0]["target_component"] = "..\\..\\secret.key"
        with pytest.raises(StructuredOutputSecurityError, match="path traversal"):
            parse_goal_decomposition_output(data_win)

        data_encoded = make_valid_goal_decomposition_dict()
        data_encoded["sub_goals"][0]["target_component"] = "%2e%2e/forbidden.txt"
        with pytest.raises(StructuredOutputSecurityError, match="traversal"):
            parse_goal_decomposition_output(data_encoded)

        with pytest.raises(StructuredOutputSecurityError):
            validate_safe_relative_path("../outside/repo.py")

        with pytest.raises(StructuredOutputSecurityError):
            validate_safe_relative_path("/etc/shadow")

    def test_out_t06_unsafe_endpoint_or_external_url_rejected(self) -> None:
        """OUT-T06: Unsafe endpoint (external URL, dangerous schemes) -> REJECTED."""
        with pytest.raises(StructuredOutputSecurityError, match="unapproved external URL"):
            validate_safe_endpoint("https://evil.attacker.com/api/steal")

        with pytest.raises(StructuredOutputSecurityError, match="unapproved external URL"):
            validate_safe_endpoint("http://phishing.site/webhook")

        with pytest.raises(StructuredOutputSecurityError, match="forbidden protocol"):
            validate_safe_endpoint("javascript:alert(1)")

        with pytest.raises(StructuredOutputSecurityError, match="forbidden protocol"):
            validate_safe_endpoint("data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==")

        assert validate_safe_endpoint("/api/v1/changes") == "/api/v1/changes"
        assert validate_safe_endpoint("healthz") == "healthz"

    def test_out_t07_unknown_action_type_rejected(self) -> None:
        """OUT-T07: Unknown action type in model response -> REJECTED."""
        data = make_valid_goal_decomposition_dict()
        data["sub_goals"][0]["action_type"] = "delete_production_database"

        with pytest.raises(StructuredOutputSecurityError, match="Unknown action type"):
            parse_goal_decomposition_output(data)

        with pytest.raises(StructuredOutputSecurityError, match="Unknown action type"):
            validate_action_type("execute_arbitrary_shell_command")

    def test_out_t08_malformed_json_rejected_no_repair(self) -> None:
        """OUT-T08: Malformed/incomplete JSON from model -> REJECTED, no silent repair."""
        malformed_1 = '{"schema_version": "1.0.0", "change_request_id": "cr-1", "summary": "test"'
        with pytest.raises(StructuredOutputJSONError, match="Failed to parse model output"):
            parse_structured_json(malformed_1)

        with pytest.raises(StructuredOutputJSONError):
            parse_goal_decomposition_output(malformed_1)

        malformed_2 = '{"schema_version": "1.0.0", "change_request_id": "cr-1", }'
        with pytest.raises(StructuredOutputJSONError):
            parse_structured_json(malformed_2)

        prose_only = "Sure, here is your plan: First scan the repository, then apply changes."
        with pytest.raises(StructuredOutputJSONError):
            parse_structured_json(prose_only)

        with pytest.raises(StructuredOutputJSONError):
            parse_structured_json("")

    def test_out_t09_silent_coercion_attempt_rejected(self) -> None:
        """OUT-T09: Silent coercion attempt -> REJECTED."""
        data = make_valid_goal_decomposition_dict()
        data["sub_goals"][0]["priority"] = "1"  # type: ignore[assignment]

        with pytest.raises(StructuredOutputValidationError, match="priority"):
            parse_goal_decomposition_output(data)

        data_bool = make_valid_goal_decomposition_dict()
        data_bool["summary"] = True  # type: ignore[assignment]
        with pytest.raises(StructuredOutputValidationError, match="summary"):
            parse_goal_decomposition_output(data_bool)


# ==============================================================================
# 2. Three Semantic Reasoning Surfaces (Positive Tests)
# ==============================================================================
class TestSemanticSurfacesPositive:
    """Validates successful schema instantiation and parsing across all 3 surfaces."""

    def test_goal_decomposition_surface_positive(self) -> None:
        data = make_valid_goal_decomposition_dict()
        res = parse_goal_decomposition_output(data)

        assert isinstance(res, GoalDecompositionResult)
        assert res.schema_version == CANONICAL_STRUCTURED_SCHEMA_VERSION
        assert res.change_request_id == "cr-payment-api-001"
        assert res.estimated_risk_level == SemanticRiskLevel.LOW
        assert len(res.sub_goals) == 2
        assert res.sub_goals[0].action_type == "inspect_impact"
        assert res.sub_goals[0].priority == 1
        assert res.authority_lane == CANONICAL_AUTHORITY_LANE
        assert res.authority_lane == "GEMINI_SEMANTIC_JUDGMENT"

    def test_policy_explanation_surface_positive(self) -> None:
        data = make_valid_policy_explanation_dict()
        res = parse_policy_explanation_output(data)

        assert isinstance(res, PolicyExplanationResult)
        assert res.change_id == "chg-2026-0816-01"
        assert res.decision_id == "dec-auto-001"
        assert len(res.rule_explanations) == 1
        rule = res.rule_explanations[0]
        assert rule.rule_id == "POL-04"
        assert rule.impact_level == PolicyImpactLevel.LOW
        assert rule.compliance_status == PolicyComplianceStatus.COMPLIANT
        assert res.authority_lane == "GEMINI_SEMANTIC_JUDGMENT"

    def test_semantic_audit_surface_positive(self) -> None:
        data = make_valid_semantic_audit_dict()
        res = parse_semantic_audit_output(data)

        assert isinstance(res, SemanticAuditResult)
        assert res.audit_id == "audit-sem-901"
        assert res.overall_verdict == SemanticAssessmentVerdict.SUPPORTS
        assert len(res.claim_assessments) == 1
        assert len(res.evidence_citations) == 1
        citation = res.evidence_citations[0]
        assert citation.citation_id == "cit-01"
        assert citation.evidence_key == "ev-test-run-44"
        assert citation.supports_claim_ids == ["claim-backwards-compat"]
        assert res.authority_lane == "GEMINI_SEMANTIC_JUDGMENT"

    def test_parsing_from_json_string_and_markdown_code_block(self) -> None:
        data = make_valid_goal_decomposition_dict()
        json_str = json.dumps(data)

        res_raw = parse_goal_decomposition_output(json_str)
        assert res_raw.change_request_id == "cr-payment-api-001"

        md_json = f"```json\n{json_str}\n```"
        res_md = parse_goal_decomposition_output(md_json)
        assert res_md.change_request_id == "cr-payment-api-001"

        md_plain = f"```\n{json_str}\n```"
        res_plain = parse_goal_decomposition_output(md_plain)
        assert res_plain.change_request_id == "cr-payment-api-001"


# ==============================================================================
# 3. Structural Separation & Decisive Citation Invariants (OUT-10)
# ==============================================================================
class TestStructuralSeparationAndAuditInvariants:
    """Validates citations & counter-evidence distinct/mandatory for decisive assessments."""

    def test_supports_verdict_without_citations_fails_closed(self) -> None:
        data = make_valid_semantic_audit_dict()
        data["overall_verdict"] = "SUPPORTS"
        data["evidence_citations"] = []

        with pytest.raises(
            StructuredOutputValidationError, match="requires at least one evidence citation"
        ):
            parse_semantic_audit_output(data)

    def test_contradicts_verdict_without_counter_evidence_fails_closed(self) -> None:
        data = make_valid_semantic_audit_dict()
        data["overall_verdict"] = "CONTRADICTS"
        data["claim_assessments"][0]["assessment"] = "CONTRADICTS"
        data["claim_assessments"][0]["counter_evidence_points"] = ["Observed breaking API change"]
        data["counter_evidence"] = []

        with pytest.raises(
            StructuredOutputValidationError, match="requires counter_evidence items"
        ):
            parse_semantic_audit_output(data)

    def test_insufficient_verdict_without_missing_evidence_fails_closed(self) -> None:
        data = make_valid_semantic_audit_dict()
        data["overall_verdict"] = "INSUFFICIENT"
        data["claim_assessments"][0]["assessment"] = "INSUFFICIENT"
        data["claim_assessments"][0]["missing_evidence_points"] = ["No benchmark logs"]
        data["missing_evidence"] = []

        with pytest.raises(
            StructuredOutputValidationError, match="requires missing_evidence items"
        ):
            parse_semantic_audit_output(data)

    def test_claim_level_invariants_enforced(self) -> None:
        data = make_valid_semantic_audit_dict()
        data["claim_assessments"][0]["cited_evidence_keys"] = []

        with pytest.raises(StructuredOutputValidationError, match="requires at least one cited"):
            parse_semantic_audit_output(data)


# ==============================================================================
# 4. Authority Boundary Invariants (OUT-08)
# ==============================================================================
class TestAuthorityBoundaryInvariants:
    """Validates that Gemini output cannot synthesize facts, policy, or approvals."""

    def test_all_models_have_immutable_gemini_semantic_judgment_authority(self) -> None:
        goal_res = parse_goal_decomposition_output(make_valid_goal_decomposition_dict())
        policy_res = parse_policy_explanation_output(make_valid_policy_explanation_dict())
        audit_res = parse_semantic_audit_output(make_valid_semantic_audit_dict())

        assert goal_res.authority_lane == "GEMINI_SEMANTIC_JUDGMENT"
        assert policy_res.authority_lane == "GEMINI_SEMANTIC_JUDGMENT"
        assert audit_res.authority_lane == "GEMINI_SEMANTIC_JUDGMENT"

    def test_attempted_injection_of_deterministic_facts_fails_closed(self) -> None:
        data_audit = make_valid_semantic_audit_dict()
        data_audit["evidence_state"] = "PASS"
        with pytest.raises(StructuredOutputValidationError, match="extra"):
            parse_semantic_audit_output(data_audit)

        data_audit_fact = make_valid_semantic_audit_dict()
        data_audit_fact["exit_code"] = 0
        with pytest.raises(StructuredOutputValidationError, match="extra"):
            parse_semantic_audit_output(data_audit_fact)

    def test_attempted_injection_of_human_authority_or_policy_fails_closed(self) -> None:
        data_policy = make_valid_policy_explanation_dict()
        data_policy["approval_granted"] = True
        with pytest.raises(StructuredOutputValidationError, match="extra"):
            parse_policy_explanation_output(data_policy)

        data_policy_slot = make_valid_policy_explanation_dict()
        data_policy_slot["authority_slot_ref"] = "slot-emergency-override"
        with pytest.raises(StructuredOutputValidationError, match="extra"):
            parse_policy_explanation_output(data_policy_slot)


# ==============================================================================
# 5. JSON Parser Edge Cases & Security
# ==============================================================================
class TestJSONParserEdgeCases:
    """Validates JSON parsing boundary handling and constant rejections."""

    def test_special_constants_nan_and_infinity_rejected(self) -> None:
        with pytest.raises(StructuredOutputJSONError, match="Invalid JSON constant"):
            parse_structured_json('{"schema_version": "1.0.0", "score": NaN}')

        with pytest.raises(StructuredOutputJSONError, match="Invalid JSON constant"):
            parse_structured_json('{"schema_version": "1.0.0", "score": Infinity}')

    def test_non_dict_json_root_rejected(self) -> None:
        with pytest.raises(StructuredOutputJSONError, match="Expected JSON root to be an object"):
            parse_structured_json("[]")

        with pytest.raises(StructuredOutputJSONError, match="Expected JSON root to be an object"):
            parse_structured_json('"just a string"')

        with pytest.raises(StructuredOutputJSONError, match="Expected JSON root to be an object"):
            parse_structured_json("12345")


# ==============================================================================
# 6. Prompt Construction Tests
# ==============================================================================
class TestPromptConstruction:
    """Validates schema-constrained prompt generation for all 3 surfaces."""

    def test_build_goal_decomposition_prompt(self) -> None:
        prompt = build_goal_decomposition_prompt(
            change_request_id="cr-test-100",
            title="Update User Service",
            description="Migrate user table schema.",
            target_systems=["user-service", "auth-db"],
            data_classification="CONFIDENTIAL",
            success_criteria=["No downtime during migration", "All unit tests pass"],
        )
        assert "Change Request ID: cr-test-100" in prompt
        assert "Update User Service" in prompt
        assert "target_systems" in prompt or "user-service" in prompt
        assert "inspect_impact" in prompt
        assert "schema_version" in prompt

    def test_build_policy_explanation_prompt(self) -> None:
        prompt = build_policy_explanation_prompt(
            change_id="chg-test-200",
            decision_id="dec-test-200",
            action_class="SCHEMA_MIGRATION",
            autonomy_class="REHEARSE_THEN_EXECUTE",
            policy_source="POL-MIG-01",
            rationale="Schema migration requires shadowlab rehearsal.",
            violated_rules=["RULE-NO-DIRECT-PROD-MUTATION"],
        )
        assert "Change ID: chg-test-200" in prompt
        assert "Decision ID: dec-test-200" in prompt
        assert "REHEARSE_THEN_EXECUTE" in prompt
        assert "RULE-NO-DIRECT-PROD-MUTATION" in prompt
        assert "DO NOT author or modify policy" in prompt

    def test_build_semantic_audit_prompt(self) -> None:
        prompt = build_semantic_audit_prompt(
            audit_id="audit-test-300",
            change_id="chg-test-300",
            claims=[
                {
                    "claim_id": "c1",
                    "claim_description": "All schemas backwards compatible",
                    "target_criterion": "crit-1",
                }
            ],
            evidence_summaries=[
                {
                    "evidence_key": "ev-1",
                    "summary": "Integration tests passed 100%",
                    "source": "ci/integration.log",
                }
            ],
        )
        assert "Audit ID: audit-test-300" in prompt
        assert "Claim [c1]" in prompt
        assert "Evidence [ev-1]" in prompt
        assert "SUPPORTS" in prompt
        assert "CONTRADICTS" in prompt


# ==============================================================================
# 7. Architectural Boundary & Donor Integrity Tests
# ==============================================================================
class TestArchitecturalIntegrityAndDonorCompliance:
    """Validates 0 SDK imports in domain, single model call owner, and 0 forbidden donors."""

    def test_domain_contracts_have_zero_google_sdk_imports(self) -> None:
        contracts_dir = Path(__file__).resolve().parent.parent / "domain" / "contracts"
        assert contracts_dir.is_dir()

        forbidden_prefixes = ("google", "google.genai", "google.adk", "vertexai")
        for py_file in contracts_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_prefixes:
                            assert not alias.name.startswith(forbidden), (
                                f"Forbidden import '{alias.name}' in {py_file}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for forbidden in forbidden_prefixes:
                            assert not node.module.startswith(forbidden), (
                                f"Forbidden from-import '{node.module}' in {py_file}"
                            )

    def test_single_model_call_owner_in_src_remains_canonical_gemini_client(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        src_dir = repo_root / "src"
        canonical_client_exact_path = (src_dir / "core" / "gemini_client.py").resolve()

        all_violations: list[str] = []
        for py_file in src_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            violations = find_model_call_violations(
                tree,
                file_path=py_file,
                canonical_client_path=canonical_client_exact_path,
            )
            all_violations.extend(violations)

        assert not all_violations, "Model call violations found in src/:\n" + "\n".join(
            all_violations
        )

    def test_zero_forbidden_donor_identifiers_in_structured_output_module(self) -> None:
        target_file = (
            Path(__file__).resolve().parent.parent / "src" / "core" / "gemini_structured_output.py"
        )
        assert target_file.is_file()
        content = target_file.read_text(encoding="utf-8")

        forbidden_patterns = (
            "@openai",
            "gpt-5.6-sol",
            "MODEL_SEMANTIC_JUDGMENT",
            "InvoiceFlow",
            "school-saas",
            "validateZeroKitConfig",
            "panel_registry",
            "rbac_registry",
            "field_registry",
            "endpoint_map",
        )

        for pattern in forbidden_patterns:
            assert pattern not in content, (
                f"Forbidden donor pattern '{pattern}' found in {target_file}"
            )


# ==============================================================================
# 8. Model Client Integration Tests (Simulated BoundedGeminiClient End-to-End)
# ==============================================================================
class TestModelClientIntegration:
    """Validates end-to-end integration between BoundedGeminiClient and structured parsers."""

    def test_bounded_client_output_parsed_into_typed_goal_decomposition(self) -> None:
        valid_dict = make_valid_goal_decomposition_dict()
        fake_sdk = FakeSDKClient(responses=[make_successful_response(json.dumps(valid_dict))])
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        prompt = build_goal_decomposition_prompt(
            change_request_id="cr-payment-api-001",
            title="Payment API Upgrade",
            description="Upgrade payment endpoint to v2",
            target_systems=["src/api/payment_v1.py"],
            data_classification="INTERNAL",
            success_criteria=["No breaking changes"],
        )

        response = client.generate_text(prompt)
        assert response.text is not None

        parsed = parse_goal_decomposition_output(response.text)
        assert isinstance(parsed, GoalDecompositionResult)
        assert parsed.change_request_id == "cr-payment-api-001"
        assert parsed.authority_lane == "GEMINI_SEMANTIC_JUDGMENT"
        assert len(parsed.sub_goals) == 2

    def test_bounded_client_malformed_output_fails_closed(self) -> None:
        fake_sdk = FakeSDKClient(
            responses=[make_successful_response("Invalid non-JSON response from model.")]
        )
        client = BoundedGeminiClient(_sdk_client=fake_sdk)

        response = client.generate_text("Decompose goal")
        with pytest.raises(StructuredOutputJSONError):
            parse_goal_decomposition_output(response.text)


# ==============================================================================
# 9. Additional Adversarial & Boundary Tests
# ==============================================================================
class TestAdversarialBoundaries:
    """Validates edge cases, nested attacks, and empty collection invariants."""

    def test_empty_sub_goals_list_rejected(self) -> None:
        data = make_valid_goal_decomposition_dict()
        data["sub_goals"] = []
        with pytest.raises(StructuredOutputValidationError, match="sub_goals"):
            parse_goal_decomposition_output(data)

    def test_empty_affected_components_list_rejected(self) -> None:
        data = make_valid_goal_decomposition_dict()
        data["affected_components"] = []
        with pytest.raises(StructuredOutputValidationError, match="affected_components"):
            parse_goal_decomposition_output(data)

    def test_empty_claim_assessments_list_rejected(self) -> None:
        data = make_valid_semantic_audit_dict()
        data["claim_assessments"] = []
        with pytest.raises(StructuredOutputValidationError, match="claim_assessments"):
            parse_semantic_audit_output(data)

    def test_blank_string_in_list_rejected(self) -> None:
        data = make_valid_goal_decomposition_dict()
        data["recommended_specialists"] = ["Impact Scout", "   "]
        with pytest.raises(StructuredOutputValidationError, match="blank"):
            parse_goal_decomposition_output(data)

    def test_priority_bounds_rejected(self) -> None:
        data = make_valid_goal_decomposition_dict()
        data["sub_goals"][0]["priority"] = 0
        with pytest.raises(StructuredOutputValidationError, match="priority"):
            parse_goal_decomposition_output(data)

        data_high = make_valid_goal_decomposition_dict()
        data_high["sub_goals"][0]["priority"] = 101
        with pytest.raises(StructuredOutputValidationError, match="priority"):
            parse_goal_decomposition_output(data_high)

    def test_complex_multi_claim_semantic_audit_with_mixed_verdicts(self) -> None:
        data = {
            "schema_version": "1.0.0",
            "audit_id": "audit-complex-01",
            "change_id": "chg-complex-01",
            "overall_verdict": "CONTRADICTS",
            "reasoning_narrative": (
                "One claim passed but critical backwards compatibility claim contradicted."
            ),
            "claim_assessments": [
                {
                    "claim_id": "claim-unit-tests",
                    "assessment": "SUPPORTS",
                    "assessment_narrative": "Unit tests pass 100%.",
                    "cited_evidence_keys": ["ev-unit-test-log"],
                    "counter_evidence_points": [],
                    "missing_evidence_points": [],
                },
                {
                    "claim_id": "claim-backwards-compat",
                    "assessment": "CONTRADICTS",
                    "assessment_narrative": (
                        "Schema removed required field 'user_id' breaking legacy clients."
                    ),
                    "cited_evidence_keys": ["ev-schema-diff"],
                    "counter_evidence_points": ["Field 'user_id' removed in commit c1"],
                    "missing_evidence_points": [],
                },
            ],
            "evidence_citations": [
                {
                    "citation_id": "cit-1",
                    "evidence_key": "ev-unit-test-log",
                    "relevance_summary": "Test run summary",
                    "supports_claim_ids": ["claim-unit-tests"],
                },
                {
                    "citation_id": "cit-2",
                    "evidence_key": "ev-schema-diff",
                    "relevance_summary": "Schema diff showing field deletion",
                    "supports_claim_ids": ["claim-backwards-compat"],
                },
            ],
            "counter_evidence": ["Field 'user_id' removed in commit c1"],
            "missing_evidence": [],
        }

        res = parse_semantic_audit_output(data)
        assert res.overall_verdict == SemanticAssessmentVerdict.CONTRADICTS
        assert len(res.claim_assessments) == 2
        assert len(res.evidence_citations) == 2
        assert len(res.counter_evidence) == 1
