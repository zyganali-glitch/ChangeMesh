"""ChangeMesh Agent Registry and Capability Passport comprehensive test suite.

P-12: Tests capability vocabulary, proof-carrying passport issuance,
expiration/revocation validation, multi-revision qualification, and router dispatch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from domain.contracts.capability import CapabilityPassport
from domain.contracts.data_class import DataClassLevel
from src.registry.agent_registry import AgentDescriptor, InMemoryAgentRegistry
from src.registry.capabilities import (
    AgentCapabilityRequirement,
    CapabilityType,
    get_standard_demo_requirements,
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


# ============================================================================
# P-12.01: Capability Requirements
# ============================================================================

def test_standard_demo_capability_requirements():
    reqs = get_standard_demo_requirements()
    assert "impact_scout" in reqs
    assert "policy_guardian" in reqs
    assert "migration_engineer" in reqs
    assert "release_steward" in reqs

    scout_req = reqs["impact_scout"]
    assert CapabilityType.AST_STATIC_ANALYSIS in scout_req.required_capabilities
    assert CapabilityType.BLAST_RADIUS_ESTIMATION in scout_req.required_capabilities

    mig_req = reqs["migration_engineer"]
    assert CapabilityType.MIGRATION_SYNTHESIS_SQL in mig_req.required_capabilities


# ============================================================================
# P-12.02: Passport Issuance from Verified Evidence
# ============================================================================

def test_passport_issuance_requires_evidence():
    now = _utc_now()

    # Valid issuance with evidence
    req = PassportIssuanceRequest(
        agent_id="impact_scout",
        agent_revision="sha-scout-v1",
        qualified_capabilities=("AST_STATIC_ANALYSIS", "BLAST_RADIUS_ESTIMATION"),
        qualification_evidence_ids=("ev-scout-test-suite", "ev-scout-ast-bench"),
        issuer="qualification_gate",
    )
    passport = PassportIssuer.issue_passport(req, now=now)
    assert passport.passport_id.startswith("pass-impact_scout-")
    assert passport.is_revoked is False
    assert len(passport.qualification_evidence_ids) == 2

    # Self-attestation without evidence fails closed
    with pytest.raises(ValidationError):
        PassportIssuanceRequest(
            agent_id="unverified_agent",
            agent_revision="rev-1",
            qualified_capabilities=("PR_GENERATION",),
            qualification_evidence_ids=(),  # Invalid: no evidence
            issuer="self",
        )


# ============================================================================
# P-12.03: Validation, Expiry, Revocation, Stale Evidence Rejection
# ============================================================================

def test_passport_validation_scenarios():
    now = _utc_now()

    # 1. Valid Passport
    valid_pass = CapabilityPassport(
        schema_version="1.0.0",
        passport_id="pass-valid-1",
        agent_id="policy_guardian",
        agent_revision="rev-guard-1",
        qualified_capabilities=("POLICY_VERIFICATION", "REVERSIBILITY_ANALYSIS"),
        qualification_evidence_ids=("ev-guard-tests",),
        issuer="gate",
        issued_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=29),
        is_revoked=False,
    )
    res_valid = PassportVerifier.verify(valid_pass, now=now)
    assert res_valid.is_valid is True
    assert res_valid.status == "VALID"

    # 2. Revoked Passport
    revoked_pass = valid_pass.model_copy(
        update={
            "is_revoked": True,
            "revoked_at": now,
            "revocation_reason": "Failed regression audit",
        }
    )
    res_revoked = PassportVerifier.verify(revoked_pass, now=now)
    assert res_revoked.is_valid is False
    assert res_revoked.status == "REVOKED"

    # 3. Expired Passport
    expired_pass = valid_pass.model_copy(
        update={
            "expires_at": now - timedelta(hours=1),
        }
    )
    res_expired = PassportVerifier.verify(expired_pass, now=now)
    assert res_expired.is_valid is False
    assert res_expired.status == "EXPIRED"

    # 4. Revision Mismatch
    res_mismatch = PassportVerifier.verify(valid_pass, expected_revision="rev-guard-2", now=now)
    assert res_mismatch.is_valid is False
    assert res_mismatch.status == "REVISION_MISMATCH"

    # 5. Missing Required Capability
    req = AgentCapabilityRequirement(
        role_id="custom",
        required_capabilities=(CapabilityType.PR_GENERATION,),
    )
    res_unqual = PassportVerifier.verify(valid_pass, requirement=req, now=now)
    assert res_unqual.is_valid is False
    assert res_unqual.status == "UNQUALIFIED"


# ============================================================================
# P-12.04 & P-12.05: Multi-Revision Agent Registry
# ============================================================================

def test_two_migration_engineer_revisions():
    registry = InMemoryAgentRegistry()
    now = _utc_now()
    tid = "tenant-reg-demo"

    # Revision 1: SQL Only
    desc_v1 = AgentDescriptor(
        agent_id="migration_engineer",
        agent_name="Migration Engineer Standard",
        agent_role="Migration Synthesis",
        agent_revision="rev-1.0.0-sqlite-pg",
        description="Qualified for single-node SQLite and PostgreSQL schema migrations",
        declared_capabilities=("MIGRATION_SYNTHESIS_SQL",),
    )
    pass_v1 = CapabilityPassport(
        schema_version="1.0.0",
        passport_id="pass-mig-v1",
        agent_id="migration_engineer",
        agent_revision="rev-1.0.0-sqlite-pg",
        qualified_capabilities=("MIGRATION_SYNTHESIS_SQL",),
        qualification_evidence_ids=("ev-mig-sql-bench",),
        issuer="bench_runner",
        issued_at=now,
        expires_at=now + timedelta(days=30),
        is_revoked=False,
    )
    registry.register_agent(desc_v1)
    registry.register_passport(tid, pass_v1)

    # Revision 2: SQL + Distributed (CockroachDB)
    desc_v2 = AgentDescriptor(
        agent_id="migration_engineer",
        agent_name="Migration Engineer Distributed",
        agent_role="Migration Synthesis",
        agent_revision="rev-2.0.0-cockroach-distributed",
        description="Qualified for distributed schema migrations",
        declared_capabilities=("MIGRATION_SYNTHESIS_SQL", "MIGRATION_SYNTHESIS_DISTRIBUTED"),
    )
    pass_v2 = CapabilityPassport(
        schema_version="1.0.0",
        passport_id="pass-mig-v2",
        agent_id="migration_engineer",
        agent_revision="rev-2.0.0-cockroach-distributed",
        qualified_capabilities=("MIGRATION_SYNTHESIS_SQL", "MIGRATION_SYNTHESIS_DISTRIBUTED"),
        qualification_evidence_ids=("ev-mig-sql-bench", "ev-mig-cockroach-bench"),
        issuer="bench_runner",
        issued_at=now,
        expires_at=now + timedelta(days=30),
        is_revoked=False,
    )
    registry.register_agent(desc_v2)
    registry.register_passport(tid, pass_v2)

    # Finding agents for SQL returns both
    sql_agents = registry.find_qualified_agents(tid, CapabilityType.MIGRATION_SYNTHESIS_SQL)
    assert len(sql_agents) == 2

    # Finding agents for Distributed returns only v2
    dist_agents = registry.find_qualified_agents(tid, CapabilityType.MIGRATION_SYNTHESIS_DISTRIBUTED)
    assert len(dist_agents) == 1
    assert dist_agents[0][0].agent_revision == "rev-2.0.0-cockroach-distributed"


# ============================================================================
# P-12.06: Passport-Aware Router Dispatch
# ============================================================================

def test_passport_aware_router_dispatch():
    registry = InMemoryAgentRegistry()
    now = _utc_now()
    tid = "tenant-router-demo"

    # Register Impact Scout with valid passport
    scout_desc = AgentDescriptor(
        agent_id="impact_scout",
        agent_name="Impact Scout",
        agent_role="Impact Analysis",
        agent_revision="rev-scout-1",
        description="AST and blast radius analysis",
        declared_capabilities=("AST_STATIC_ANALYSIS", "BLAST_RADIUS_ESTIMATION"),
    )
    scout_pass = CapabilityPassport(
        schema_version="1.0.0",
        passport_id="pass-scout-1",
        agent_id="impact_scout",
        agent_revision="rev-scout-1",
        qualified_capabilities=("AST_STATIC_ANALYSIS", "BLAST_RADIUS_ESTIMATION"),
        qualification_evidence_ids=("ev-scout-1",),
        issuer="bench",
        issued_at=now,
        expires_at=now + timedelta(days=30),
        is_revoked=False,
    )
    registry.register_agent(scout_desc)
    registry.register_passport(tid, scout_pass)

    router = PassportAwareRouter(registry)

    # 1. Routing Impact Scout succeeds
    desc, passp = router.route_role(tid, "impact_scout")
    assert desc.agent_id == "impact_scout"
    assert passp.passport_id == "pass-scout-1"

    # 2. Routing an unregistered role fails closed
    with pytest.raises(UnqualifiedAgentDispatchError):
        router.route_role(tid, "release_steward")

    # 3. Routing when passport is revoked fails closed
    revoked_scout = scout_pass.model_copy(
        update={"is_revoked": True, "revoked_at": now, "revocation_reason": "Audit failure"}
    )
    registry.register_passport(tid, revoked_scout)

    with pytest.raises(UnqualifiedAgentDispatchError):
        router.route_role(tid, "impact_scout")
