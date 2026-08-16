"""P-08.04 blind semantic audit and deterministic fact isolation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode
from src.agents.evidence_auditor import (
    BlindAuditInputError,
    BlindAuditReconciliationError,
    build_blind_audit_package,
    reconcile_semantic_audit,
    run_blind_semantic_audit,
)
from src.core.gemini_client import BoundedGeminiClient
from src.core.gemini_structured_output import (
    StructuredOutputValidationError,
    parse_semantic_audit_output,
)
from tests.test_p08_01_gemini_client import FakeSDKClient, make_successful_response


def make_claim(
    status: EvidenceState | str = EvidenceState.PASS,
    *,
    claim_id: str = "claim-1",
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "claim_description": "The bounded change preserves the stated contract.",
        "target_criterion": "criterion-1",
        "deterministic_status": status.value if isinstance(status, EvidenceState) else status,
        "deterministic_basis": "Recorded deterministic test evidence.",
        "evidence_keys": ["ev-1"],
    }


def make_evidence() -> list[dict[str, str]]:
    return [
        {
            "evidence_key": "ev-1",
            "summary": "The bounded compatibility test covers the stated contract.",
            "source": "tests/compatibility.log",
        }
    ]


def make_package(
    status: EvidenceState | str = EvidenceState.PASS,
    *,
    claim_id: str = "claim-1",
) -> Any:
    return build_blind_audit_package(
        audit_id="audit-804",
        change_id="change-804",
        deterministic_claims=[make_claim(status, claim_id=claim_id)],
        evidence_summaries=make_evidence(),
        collection_mode=ExecutionEvidenceMode.SIMULATION,
        declared_mode=ExecutionEvidenceMode.SIMULATION,
    )


def make_model_result(
    assessment: str,
    *,
    overall_verdict: str | None = None,
    claim_id: str = "claim-1",
) -> Any:
    overall = overall_verdict or assessment
    supports = assessment in {"SUPPORTS", "CONTRADICTS"}
    claim = {
        "claim_id": claim_id,
        "assessment": assessment,
        "assessment_narrative": "Bounded semantic assessment.",
        "cited_evidence_keys": ["ev-1"] if supports else [],
        "counter_evidence_points": ["Bounded counter evidence."]
        if assessment == "CONTRADICTS"
        else [],
        "missing_evidence_points": ["A missing semantic proof."]
        if assessment == "INSUFFICIENT"
        else [],
    }
    return parse_semantic_audit_output(
        {
            "schema_version": "1.0.0",
            "audit_id": "audit-804",
            "change_id": "change-804",
            "overall_verdict": overall,
            "reasoning_narrative": "Bounded semantic audit result.",
            "claim_assessments": [claim],
            "evidence_citations": [
                {
                    "citation_id": "citation-1",
                    "evidence_key": "ev-1",
                    "relevance_summary": "Bounded evidence citation.",
                    "supports_claim_ids": [claim_id],
                }
            ]
            if supports
            else [],
            "counter_evidence": ["Bounded counter evidence."] if overall == "CONTRADICTS" else [],
            "missing_evidence": ["A missing semantic proof."] if overall == "INSUFFICIENT" else [],
        }
    )


def test_audit_01_expected_result_field_is_rejected_before_prompt() -> None:
    evidence = make_evidence()[0]
    evidence["expected_result"] = "SUPPORTS"

    with pytest.raises(BlindAuditInputError, match="EXPECTED_FIELD_LEAKAGE"):
        build_blind_audit_package(
            audit_id="audit-804",
            change_id="change-804",
            deterministic_claims=[make_claim()],
            evidence_summaries=[evidence],
            collection_mode="SIMULATION",
            declared_mode="SIMULATION",
        )


def test_audit_02_should_pass_hint_is_rejected_before_prompt() -> None:
    evidence = make_evidence()[0]
    evidence["should_pass"] = "true"

    with pytest.raises(BlindAuditInputError, match="EXPECTED_FIELD_LEAKAGE"):
        build_blind_audit_package(
            audit_id="audit-804",
            change_id="change-804",
            deterministic_claims=[make_claim()],
            evidence_summaries=[evidence],
            collection_mode="SIMULATION",
            declared_mode="SIMULATION",
        )


def test_blind_prompt_withholds_locked_status_and_expected_fields() -> None:
    package = make_package(EvidenceState.FAIL)
    prompt = package.build_prompt()

    assert "claim-1" in prompt
    assert "deterministic_status" not in prompt
    assert "deterministic_basis" not in prompt
    assert "expected_result" not in prompt
    assert "should_pass" not in prompt
    assert "FAIL" not in prompt
    assert package.locked_claims[0].deterministic_status == EvidenceState.FAIL


def test_blind_bundle_rejects_unbounded_evidence() -> None:
    evidence = make_evidence()[0]
    evidence["summary"] = "x" * 4001

    with pytest.raises(BlindAuditInputError, match="bounded"):
        build_blind_audit_package(
            audit_id="audit-804",
            change_id="change-804",
            deterministic_claims=[make_claim()],
            evidence_summaries=[evidence],
            collection_mode="SIMULATION",
            declared_mode="SIMULATION",
        )


def test_blind_prompt_has_an_aggregate_size_bound() -> None:
    evidence = [
        {
            "evidence_key": f"ev-{index}",
            "summary": "bounded evidence " + ("x" * 3500),
            "source": "tests/compatibility.log",
        }
        for index in range(10)
    ]
    package = build_blind_audit_package(
        audit_id="audit-804",
        change_id="change-804",
        deterministic_claims=[make_claim()],
        evidence_summaries=evidence,
        collection_mode="SIMULATION",
        declared_mode="SIMULATION",
    )

    with pytest.raises(BlindAuditInputError, match="BLIND_PROMPT_EXCEEDS_BOUND"):
        package.build_prompt()


def test_audit_03_uncited_decisive_model_answer_fails_closed() -> None:
    data = make_model_result("SUPPORTS").model_dump()
    data["evidence_citations"] = []

    with pytest.raises(StructuredOutputValidationError, match="evidence citation"):
        parse_semantic_audit_output(data)


def test_audit_04_mission_gap_remains_insufficient() -> None:
    package = make_package(EvidenceState.PASS)
    result = reconcile_semantic_audit(package, make_model_result("INSUFFICIENT"))

    assert result.model_overall_verdict == "INSUFFICIENT"
    assert result.claim_audits[0].deterministic_status == EvidenceState.PASS
    assert result.claim_audits[0].relation == "DISAGREEMENT_WITH_LOCKED_STATE"
    assert result.claim_audits[0].conflict_detected is True
    assert result.review_state == "SEMANTIC_DISAGREEMENT"
    assert result.conflict_detected is True
    # Invariant: Gemini disagreement does NOT manufacture human authority
    assert result.human_review_required is False
    assert result.claim_audits[0].human_review_required is False


@pytest.mark.parametrize(
    "state", [EvidenceState.FAIL, EvidenceState.NOT_RUN, EvidenceState.SIMULATED]
)
def test_audit_05_to_07_model_support_cannot_promote_locked_state(
    state: EvidenceState,
) -> None:
    package = make_package(state)
    result = reconcile_semantic_audit(package, make_model_result("SUPPORTS"))

    assert result.claim_audits[0].deterministic_status == state
    assert result.claim_audits[0].model_assessment == "SUPPORTS"
    assert result.claim_audits[0].relation == "DISAGREEMENT_WITH_LOCKED_STATE"
    assert result.claim_audits[0].conflict_detected is True
    assert result.review_state == "SEMANTIC_DISAGREEMENT"
    assert result.conflict_detected is True
    # Invariant: Gemini cannot create human authority
    assert result.human_review_required is False
    assert result.claim_audits[0].human_review_required is False


def test_model_fact_and_authority_injection_is_rejected() -> None:
    data = make_model_result("SUPPORTS").model_dump()
    data["evidence_state"] = "PASS"
    with pytest.raises(StructuredOutputValidationError, match="extra"):
        parse_semantic_audit_output(data)

    data = make_model_result("SUPPORTS").model_dump()
    data["approval_granted"] = True
    with pytest.raises(StructuredOutputValidationError, match="extra"):
        parse_semantic_audit_output(data)

    data = make_model_result("SUPPORTS").model_dump()
    data["human_review_required"] = True
    with pytest.raises(StructuredOutputValidationError, match="extra"):
        parse_semantic_audit_output(data)


def test_reconciliation_rejects_citation_outside_blind_bundle() -> None:
    package = make_package()
    result = make_model_result("SUPPORTS").model_copy(deep=True)
    result.claim_assessments[0].cited_evidence_keys[0] = "outside-bundle"

    with pytest.raises(BlindAuditReconciliationError, match="OUTSIDE_BUNDLE"):
        reconcile_semantic_audit(package, result)


def test_reconciliation_rejects_duplicate_claim_assessments() -> None:
    package = make_package()
    result = make_model_result("SUPPORTS").model_copy(deep=True)
    result.claim_assessments.append(result.claim_assessments[0])

    with pytest.raises(BlindAuditReconciliationError, match="MODEL_CLAIM_SET_MISMATCH"):
        reconcile_semantic_audit(package, result)


def test_reconciliation_rejects_cross_claim_top_level_citation() -> None:
    package = build_blind_audit_package(
        audit_id="audit-804",
        change_id="change-804",
        deterministic_claims=[
            make_claim(claim_id="claim-1"),
            {
                **make_claim(claim_id="claim-2"),
                "evidence_keys": ["ev-2"],
            },
        ],
        evidence_summaries=[
            *make_evidence(),
            {
                "evidence_key": "ev-2",
                "summary": "Second bounded evidence summary.",
                "source": "tests/second.log",
            },
        ],
        collection_mode="SIMULATION",
        declared_mode="SIMULATION",
    )
    result = make_model_result("SUPPORTS").model_copy(deep=True)
    result.claim_assessments.append(
        result.claim_assessments[0].model_copy(update={"claim_id": "claim-2"})
    )
    result.evidence_citations[0] = result.evidence_citations[0].model_copy(
        update={"supports_claim_ids": ["claim-2"]}
    )

    with pytest.raises(BlindAuditReconciliationError, match="OUTSIDE_CLAIM"):
        reconcile_semantic_audit(package, result)


@pytest.mark.parametrize("state", [EvidenceState.BLOCKED, EvidenceState.QUARANTINED])
def test_blocked_and_quarantined_states_remain_locked(state: EvidenceState) -> None:
    package = make_package(state)
    result = reconcile_semantic_audit(package, make_model_result("INSUFFICIENT"))

    assert result.claim_audits[0].deterministic_status == state
    assert result.claim_audits[0].relation == "COMPATIBLE_WITH_LOCKED_STATE"
    assert result.claim_audits[0].conflict_detected is False
    assert result.review_state == "NO_MODEL_CONFLICT"
    assert result.human_review_required is False


def test_p08_04_target_has_no_forbidden_donor_runtime_identifiers() -> None:
    target = Path(__file__).resolve().parent.parent / "src" / "agents" / "evidence_auditor.py"
    content = target.read_text(encoding="utf-8")
    for forbidden in (
        "@openai",
        "gpt-5.6-sol",
        "MODEL_SEMANTIC_JUDGMENT",
        "InvoiceFlow",
        "Codex CLI",
        "ChatGPT",
    ):
        assert forbidden not in content


def test_real_bounded_client_path_receives_only_blind_context() -> None:
    package = make_package(EvidenceState.NOT_RUN)
    fake_sdk = FakeSDKClient(
        responses=[make_successful_response(json.dumps(make_model_result("SUPPORTS").model_dump()))]
    )
    client = BoundedGeminiClient(_sdk_client=fake_sdk)

    result = run_blind_semantic_audit(package, client)

    assert result.claim_audits[0].deterministic_status == EvidenceState.NOT_RUN
    assert result.conflict_detected is True
    assert result.review_state == "SEMANTIC_DISAGREEMENT"
    assert result.human_review_required is False
    assert len(fake_sdk.models.call_history) == 1
    outbound_prompt = fake_sdk.models.call_history[0]["contents"]
    assert "deterministic_status" not in outbound_prompt
    assert "deterministic_basis" not in outbound_prompt
    assert "NOT_RUN" not in outbound_prompt
