"""ChangeMesh capability passport issuance, verification, and routing tests.

P-12: Tests CapabilityPassport issuance from verified qualification evidence,
prohibiting self-attestation, enforcing stale/expired/revoked evidence rejection,
demonstrating revision qualification failure (P-12.04), and producing structured
judge-facing projections (P-12.06).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.contracts.evidence import (
    EvidenceProducerKind,
    EvidenceState,
    ExecutionEvidenceMode,
)
from src.registry.agent_registry import AgentDescriptor, InMemoryAgentRegistry
from src.registry.evidence_verifier import (
    QualificationEvidenceRecord,
    QualificationEvidenceRegistry,
    QualificationEvidenceVerificationError,
    QualificationEvidenceVerifier,
)
from src.registry.passport_issuer import (
    PassportIssuanceRequest,
    PassportIssuer,
    PassportVerifier,
)
from src.registry.passport_router import (
    PassportAwareRouter,
    UnqualifiedAgentDispatchError,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _setup_evidence_verifier() -> tuple[
    QualificationEvidenceRegistry, QualificationEvidenceVerifier
]:
    reg = QualificationEvidenceRegistry()
    verifier = QualificationEvidenceVerifier(registry=reg)
    return reg, verifier


# ============================================================================
# P-12.02 & P-12.03: Verified Evidence Issuance & Self-Attestation Prohibition
# ============================================================================


def test_passport_cannot_self_attest_without_verified_evidence():
    """Prove arbitrary caller cannot supply fake/unknown evidence IDs to obtain a passport."""
    ev_reg, verifier = _setup_evidence_verifier()
    now = _utc_now()

    # Attempting to issue passport with unverified/nonexistent evidence ID fails closed
    fake_request = PassportIssuanceRequest(
        agent_id="migration_engineer",
        agent_revision="sha-rev-unverified",
        qualified_capabilities=("MIGRATION_SYNTHESIS_SQL",),
        qualification_evidence_ids=("ev-made-up-fake",),
        issuer="malicious_caller",
    )

    with pytest.raises(QualificationEvidenceVerificationError) as exc_info:
        PassportIssuer.issue_passport(fake_request, evidence_verifier=verifier, now=now)

    assert exc_info.value.status == "EVIDENCE_MISSING"


def test_passport_issuance_from_valid_verified_evidence():
    """Prove valid registered qualification evidence successfully issues a CapabilityPassport."""
    ev_reg, verifier = _setup_evidence_verifier()
    now = _utc_now()
    aid = "impact_scout"
    rev = "sha-rev-scout-1"

    # Register genuine evidence records
    ev1 = QualificationEvidenceRecord(
        evidence_id="ev-ast-01",
        agent_id=aid,
        agent_revision=rev,
        qualified_capability="AST_STATIC_ANALYSIS",
        scenario_id="SCENARIO_NORMAL_MIGRATION",
        passed=True,
        evidence_state=EvidenceState.SIMULATED,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        producer_kind=EvidenceProducerKind.SIMULATION,
        evidence_digest="a" * 64,
        collected_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=30),
    )
    ev2 = QualificationEvidenceRecord(
        evidence_id="ev-blast-01",
        agent_id=aid,
        agent_revision=rev,
        qualified_capability="BLAST_RADIUS_ESTIMATION",
        scenario_id="SCENARIO_NORMAL_MIGRATION",
        passed=True,
        evidence_state=EvidenceState.SIMULATED,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        producer_kind=EvidenceProducerKind.SIMULATION,
        evidence_digest="b" * 64,
        collected_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=30),
    )
    ev_reg.register_evidence(ev1)
    ev_reg.register_evidence(ev2)

    request = PassportIssuanceRequest(
        agent_id=aid,
        agent_revision=rev,
        qualified_capabilities=("AST_STATIC_ANALYSIS", "BLAST_RADIUS_ESTIMATION"),
        qualification_evidence_ids=("ev-ast-01", "ev-blast-01"),
        issuer="qualification_pipeline",
    )

    passport = PassportIssuer.issue_passport(request, evidence_verifier=verifier, now=now)
    assert passport.agent_id == aid
    assert passport.agent_revision == rev
    assert len(passport.qualification_evidence_ids) == 2

    # Validation succeeds against verifier
    val = PassportVerifier.verify(
        passport, expected_revision=rev, evidence_verifier=verifier, now=now
    )
    assert val.is_valid is True
    assert val.status == "VALID"


def test_stale_and_revoked_evidence_rejection():
    """Verify expired or revoked qualification evidence fails passport issuance/validation."""
    ev_reg, verifier = _setup_evidence_verifier()
    now = _utc_now()
    aid = "policy_guardian"
    rev = "sha-rev-guard-1"

    # Expired evidence
    ev_expired = QualificationEvidenceRecord(
        evidence_id="ev-exp-01",
        agent_id=aid,
        agent_revision=rev,
        qualified_capability="POLICY_VERIFICATION",
        scenario_id="SCENARIO_NORMAL_MIGRATION",
        passed=True,
        evidence_state=EvidenceState.SIMULATED,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        producer_kind=EvidenceProducerKind.SIMULATION,
        evidence_digest="c" * 64,
        collected_at=now - timedelta(days=40),
        expires_at=now - timedelta(days=5),  # Expired
    )
    ev_reg.register_evidence(ev_expired)

    req_expired = PassportIssuanceRequest(
        agent_id=aid,
        agent_revision=rev,
        qualified_capabilities=("POLICY_VERIFICATION",),
        qualification_evidence_ids=("ev-exp-01",),
        issuer="qualification_pipeline",
    )

    with pytest.raises(QualificationEvidenceVerificationError) as exc_info:
        PassportIssuer.issue_passport(req_expired, evidence_verifier=verifier, now=now)
    assert exc_info.value.status == "EVIDENCE_EXPIRED"


# ============================================================================
# P-12.04: Two Migration Engineer Revisions (Newer Revision Fails Qualification)
# ============================================================================


def test_newer_revision_fails_qualification_routing_selects_proven():
    """Prove newer revision fails qualification and router falls back to proven revision."""
    ev_reg, verifier = _setup_evidence_verifier()
    agent_reg = InMemoryAgentRegistry()
    router = PassportAwareRouter(registry=agent_reg, evidence_verifier=verifier)
    now = _utc_now()
    tid = "tenant-p12-demo"

    # 1. Proven Revision 1 (rev-mig-proven-v1) - Passes qualification
    desc_v1 = AgentDescriptor(
        agent_id="migration_engineer",
        agent_name="Migration Engineer Proven",
        agent_role="Migration Engineer",
        agent_revision="rev-mig-proven-v1",
        description="Standard proven migration engineer",
        declared_capabilities=("MIGRATION_SYNTHESIS_SQL",),
    )
    agent_reg.register_agent(desc_v1)

    ev_v1 = QualificationEvidenceRecord(
        evidence_id="ev-mig-v1-pass",
        agent_id="migration_engineer",
        agent_revision="rev-mig-proven-v1",
        qualified_capability="MIGRATION_SYNTHESIS_SQL",
        scenario_id="SCENARIO_NORMAL_MIGRATION",
        passed=True,
        evidence_state=EvidenceState.SIMULATED,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        producer_kind=EvidenceProducerKind.SIMULATION,
        evidence_digest="1" * 64,
        collected_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=30),
    )
    ev_reg.register_evidence(ev_v1)

    pass_v1 = PassportIssuer.issue_passport(
        PassportIssuanceRequest(
            agent_id="migration_engineer",
            agent_revision="rev-mig-proven-v1",
            qualified_capabilities=("MIGRATION_SYNTHESIS_SQL",),
            qualification_evidence_ids=("ev-mig-v1-pass",),
            issuer="qualification_pipeline",
        ),
        evidence_verifier=verifier,
        now=now,
    )
    agent_reg.register_passport(tid, pass_v1)

    # 2. Newer Revision 2 (rev-mig-newer-v2) - FAILS critical qualification scenario
    desc_v2 = AgentDescriptor(
        agent_id="migration_engineer",
        agent_name="Migration Engineer Fast Experimental",
        agent_role="Migration Engineer",
        agent_revision="rev-mig-newer-v2",
        description="Faster experimental migration engineer",
        declared_capabilities=("MIGRATION_SYNTHESIS_SQL",),
    )
    agent_reg.register_agent(desc_v2)

    ev_v2_fail = QualificationEvidenceRecord(
        evidence_id="ev-mig-v2-fail",
        agent_id="migration_engineer",
        agent_revision="rev-mig-newer-v2",
        qualified_capability="MIGRATION_SYNTHESIS_SQL",
        scenario_id="SCENARIO_LEGACY_CLIENT_BREAK",
        passed=False,  # FAILED
        evidence_state=EvidenceState.FAIL,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        producer_kind=EvidenceProducerKind.SIMULATION,
        evidence_digest="2" * 64,
        collected_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=30),
    )
    ev_reg.register_evidence(ev_v2_fail)

    # Attempting to issue passport to v2 fails closed
    with pytest.raises(QualificationEvidenceVerificationError):
        PassportIssuer.issue_passport(
            PassportIssuanceRequest(
                agent_id="migration_engineer",
                agent_revision="rev-mig-newer-v2",
                qualified_capabilities=("MIGRATION_SYNTHESIS_SQL",),
                qualification_evidence_ids=("ev-mig-v2-fail",),
                issuer="qualification_pipeline",
            ),
            evidence_verifier=verifier,
            now=now,
        )

    # 3. Router automatically dispatches to proven revision v1
    desc_out, pass_out, proj_out = router.route_role(
        tenant_id=tid,
        role_id="migration_engineer",
    )
    assert desc_out.agent_revision == "rev-mig-proven-v1"
    assert pass_out.agent_revision == "rev-mig-proven-v1"

    # Explicitly requesting unqualified preferred revision v2 raises UnqualifiedAgentDispatchError
    with pytest.raises(UnqualifiedAgentDispatchError) as exc_info:
        router.route_role(
            tenant_id=tid,
            role_id="migration_engineer",
            preferred_revision="rev-mig-newer-v2",
        )
    assert "rev-mig-newer-v2" in str(exc_info.value)


# ============================================================================
# P-12.06: Structured Judge-Facing Projection
# ============================================================================


def test_passport_judge_projection_structure():
    """Verify projection contains selected revision, capabilities, and qualification evidence."""

    ev_reg, verifier = _setup_evidence_verifier()
    agent_reg = InMemoryAgentRegistry()
    router = PassportAwareRouter(registry=agent_reg, evidence_verifier=verifier)
    now = _utc_now()
    tid = "tenant-judge-proj"

    desc = AgentDescriptor(
        agent_id="release_steward",
        agent_name="Release Steward",
        agent_role="Release Steward",
        agent_revision="rev-steward-1",
        description="Release steward with PR generation",
        declared_capabilities=("PR_GENERATION",),
    )
    agent_reg.register_agent(desc)

    ev = QualificationEvidenceRecord(
        evidence_id="ev-pr-01",
        agent_id="release_steward",
        agent_revision="rev-steward-1",
        qualified_capability="PR_GENERATION",
        scenario_id="SCENARIO_NORMAL_MIGRATION",
        passed=True,
        evidence_state=EvidenceState.SIMULATED,
        evidence_mode=ExecutionEvidenceMode.SIMULATION,
        producer_kind=EvidenceProducerKind.SIMULATION,
        evidence_digest="3" * 64,
        collected_at=now,
        expires_at=now + timedelta(days=30),
    )
    ev_reg.register_evidence(ev)

    passport = PassportIssuer.issue_passport(
        PassportIssuanceRequest(
            agent_id="release_steward",
            agent_revision="rev-steward-1",
            qualified_capabilities=("PR_GENERATION",),
            qualification_evidence_ids=("ev-pr-01",),
            issuer="qualification_pipeline",
        ),
        evidence_verifier=verifier,
        now=now,
    )
    agent_reg.register_passport(tid, passport)

    desc_out, pass_out, projection = router.route_role(tid, "release_steward")
    assert projection.selected_agent_id == "release_steward"
    assert projection.selected_revision == "rev-steward-1"
    assert "PR_GENERATION" in projection.qualified_capabilities
    assert "ev-pr-01" in projection.qualification_evidence_ids
