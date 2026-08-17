import pytest

from src.audit.audit_bundle import AuditBundleBuilder
from src.audit.claim_derivation import ClaimDerivationEngine, ClaimType, NeutralClaim
from src.audit.reconciliation import DeterministicReconciler, ReconciliationOutcome
from src.audit.semantic_auditor import SemanticAuditor, SemanticVerdict


def test_neutral_claims_have_no_expected_verdict():
    engine = ClaimDerivationEngine()
    criteria = [{"id": "c1", "statement": "Button is blue"}]
    claims = engine.derive_claims(criteria, ["ev1"])

    assert len(claims) == 1
    assert claims[0].statement == "Button is blue"

    violations = engine.validate_neutrality(claims)
    assert not violations


def test_forbidden_fields_rejected():
    engine = ClaimDerivationEngine()
    claims = (
        NeutralClaim(
            claim_id="1",
            claim_type=ClaimType.MISSION_CLAIM,
            statement="The expected_result is true",
            evidence_keys=("ev1",),
        ),
    )
    violations = engine.validate_neutrality(claims)
    assert violations
    assert "expected_result" in violations[0]


def test_bundle_enforces_bounds():
    builder = AuditBundleBuilder()
    claims = tuple(
        NeutralClaim(
            claim_id=str(i), claim_type=ClaimType.MISSION_CLAIM, statement="test", evidence_keys=()
        )
        for i in range(100)
    )

    with pytest.raises(ValueError, match="Too many claims"):
        builder.build_bundle("c1", claims, {})


def test_bundle_excludes_non_allowlisted_evidence():
    builder = AuditBundleBuilder()
    claims = ()
    evidence = {"ev1": "data", "ev2": "secret"}
    bundle = builder.build_bundle("c1", claims, evidence, allowlist=frozenset({"ev1"}))

    assert "ev1" in bundle.evidence_summaries
    assert "ev2" not in bundle.evidence_summaries
    assert not bundle.contains_credentials


def test_uncited_decisive_output_fails_closed():
    # In fixture mode, empty evidence leads to INSUFFICIENT
    auditor = SemanticAuditor()
    claim = NeutralClaim(
        claim_id="1", claim_type=ClaimType.MISSION_CLAIM, statement="test", evidence_keys=("ev1",)
    )
    builder = AuditBundleBuilder()
    bundle = builder.build_bundle("c1", (claim,), {})  # Missing evidence

    report = auditor.audit_claims(bundle)
    assert report.results[0].verdict == SemanticVerdict.INSUFFICIENT


def test_insufficient_for_missing_evidence():
    auditor = SemanticAuditor()
    claim = NeutralClaim(
        claim_id="1", claim_type=ClaimType.MISSION_CLAIM, statement="test", evidence_keys=("ev1",)
    )
    res = auditor._fixture_evaluate_claim(claim, {})
    assert res.verdict == SemanticVerdict.INSUFFICIENT


def test_reconciliation_preserves_deterministic_state():
    reconciler = DeterministicReconciler()
    from src.audit.semantic_auditor import ClaimAuditResult, SemanticVerdict

    audit_res = ClaimAuditResult(
        claim_id="1", verdict=SemanticVerdict.CONTRADICTS, reasoning="...", citations=("ev1",)
    )

    rec_res = reconciler.reconcile(audit_res, "PASS", "c1")
    assert rec_res.deterministic_state == "PASS"
    assert rec_res.outcome == ReconciliationOutcome.ADVISORY_REVIEW
    assert rec_res.disagreement_detected
    assert rec_res.deterministic_state_preserved


def test_controlled_gap():
    auditor = SemanticAuditor()
    claim = NeutralClaim(
        claim_id="1", claim_type=ClaimType.MISSION_CLAIM, statement="test", evidence_keys=("ev1",)
    )

    # Pre-correction missing evidence
    res1 = auditor._fixture_evaluate_claim(claim, {})
    assert res1.verdict == SemanticVerdict.INSUFFICIENT

    # Post-correction
    res2 = auditor._fixture_evaluate_claim(claim, {"ev1": "data"})
    assert res2.verdict == SemanticVerdict.SUPPORTS
    assert "ev1" in res2.citations
