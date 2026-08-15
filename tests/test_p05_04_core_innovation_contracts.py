"""Tests for P-05.04 core innovation contracts.

Covers MemoryRecord, CapabilityPassport, RehearsalScenario,
RehearsalResult, AutonomyDecision, and ApprovalCompressionCard.

Test categories:
- Positive construction
- Mandatory field / non-blank validation
- Semantic invariants (trust/quarantine, expiry ordering, etc.)
- Authority-boundary proofs (memory != authority, passport != authorization, etc.)
- Immutability regression (frozen fields, frozen collections)
- Provider-neutrality (AST import scan)
- Credential-boundary (no credential fields)
- P-05.05 non-leakage
- Public export surface
"""

import ast
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import domain.contracts
from domain.contracts.autonomy import (
    ApprovalCompressionCard,
    AutonomyClass,
    AutonomyDecision,
)
from domain.contracts.capability import CapabilityPassport
from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import (
    EvidenceState,
    ExecutionEvidenceMode,
    Provenance,
)
from domain.contracts.memory import MemoryRecord, MemoryTrustStatus
from domain.contracts.rehearsal import (
    FaultInjectionSpec,
    RehearsalResult,
    RehearsalScenario,
)

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_LATER = _NOW + timedelta(hours=24)
_MUCH_LATER = _NOW + timedelta(hours=48)


def _make_provenance(mode=ExecutionEvidenceMode.SIMULATION):
    return Provenance(
        schema_version="1.0",
        source="shadowlab-runner",
        collection_mode=mode,
        collection_timestamp=_NOW,
    )


def _make_memory(**overrides):
    defaults = dict(
        schema_version="1.0",
        memory_id="mem-001",
        scope="change-req-1",
        content="Blast radius includes service-A",
        source="impact-scout-v2",
        capture_timestamp=_NOW,
        expiry_timestamp=_LATER,
        data_classification=DataClassLevel.INTERNAL,
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)


def _make_passport(**overrides):
    defaults = dict(
        schema_version="1.0",
        passport_id="pass-001",
        agent_id="impact-scout",
        agent_revision="v2.1.0",
        qualified_capabilities=("blast_radius_analysis",),
        qualification_evidence_ids=("ev-001",),
        issuer="capability-registry",
        issued_at=_NOW,
        expires_at=_LATER,
    )
    defaults.update(overrides)
    return CapabilityPassport(**defaults)


def _make_scenario(**overrides):
    defaults = dict(
        schema_version="1.0",
        scenario_id="scen-001",
        change_request_id="cr-001",
        description="Rehearse schema migration rollback",
        target_refs=("service-A", "db-primary"),
        created_at=_NOW,
        scenario_version="1.0.0",
    )
    defaults.update(overrides)
    return RehearsalScenario(**defaults)


def _make_result(**overrides):
    defaults = dict(
        schema_version="1.0",
        result_id="res-001",
        scenario_id="scen-001",
        change_request_id="cr-001",
        state=EvidenceState.PASS,
        provenance=_make_provenance(),
        started_at=_NOW,
        completed_at=_NOW + timedelta(minutes=5),
        evidence_record_ids=("ev-001",),
    )
    defaults.update(overrides)
    return RehearsalResult(**defaults)


def _make_autonomy_decision(
    autonomy_class=AutonomyClass.AUTO_EXECUTE,
    action_class="READ_ONLY",
    **overrides,
):
    defaults = dict(
        schema_version="1.0",
        decision_id="dec-001",
        change_request_id="cr-001",
        action_class=action_class,
        autonomy_class=autonomy_class,
        policy_source="org-policy-v3",
        decided_at=_NOW,
        rationale="Low-risk read-only action",
    )
    if autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED:
        defaults["authority_slot_ref"] = overrides.pop("authority_slot_ref", "slot-001")
        defaults["rationale"] = overrides.pop("rationale", "Irreversible production change")
    if autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE:
        defaults["required_rehearsal_refs"] = overrides.pop(
            "required_rehearsal_refs", ("scen-001",)
        )
        defaults["rationale"] = overrides.pop("rationale", "Must rehearse before live execution")
    defaults.update(overrides)
    return AutonomyDecision(**defaults)


def _make_card(**overrides):
    decision = overrides.pop("autonomy_decision", None)
    if decision is None:
        decision = _make_autonomy_decision(
            AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
        )
    defaults = dict(
        schema_version="1.0",
        card_id="card-001",
        change_request_id=decision.change_request_id,
        autonomy_decision=decision,
        authority_slot_ref=decision.authority_slot_ref,
        decision_question="Approve production schema migration?",
        decision_options=("Approve", "Reject"),
        policy_reason="Irreversible cross-service schema change",
        action_scope="ALTER TABLE on db-primary",
        completed_work_summary="Impact analysis, qualification, tooling",
        rehearsed_work_summary="ShadowLab migration rehearsal PASS",
        remaining_decision_summary="Irreversible DDL on production",
        created_at=_NOW,
    )
    defaults.update(overrides)
    return ApprovalCompressionCard(**defaults)


# ===========================================================================
# SECTION 1: MEMORYRECORD TESTS
# ===========================================================================


class TestMemoryRecordPositive:
    """Valid MemoryRecord construction."""

    def test_valid_untrusted_memory(self):
        m = _make_memory()
        assert m.memory_id == "mem-001"
        assert m.trust_status == MemoryTrustStatus.UNTRUSTED
        assert m.is_quarantined is False

    def test_valid_trusted_memory(self):
        m = _make_memory(
            trust_status=MemoryTrustStatus.TRUSTED,
            trust_evidence_ids=("ev-001", "ev-002"),
        )
        assert m.trust_status == MemoryTrustStatus.TRUSTED
        assert len(m.trust_evidence_ids) == 2

    def test_valid_quarantined_memory(self):
        m = _make_memory(
            trust_status=MemoryTrustStatus.QUARANTINED,
            is_quarantined=True,
            quarantine_reason="Contradictory provenance",
        )
        assert m.is_quarantined is True
        assert m.trust_status == MemoryTrustStatus.QUARANTINED


class TestMemoryRecordValidation:
    """Negative validation tests for MemoryRecord."""

    def test_schema_version_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_memory(schema_version="  ")

    def test_memory_id_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_memory(memory_id="")

    def test_source_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_memory(source="   ")

    def test_scope_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_memory(scope="")

    def test_blank_content_rejects(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_memory(content="   ")

    def test_blank_trust_evidence_id_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_memory(
                trust_status=MemoryTrustStatus.TRUSTED,
                trust_evidence_ids=("valid-id", "   "),
            )

    def test_duplicate_trust_evidence_id_rejects(self):
        with pytest.raises(ValidationError, match="duplicate"):
            _make_memory(
                trust_status=MemoryTrustStatus.TRUSTED,
                trust_evidence_ids=("id-1", "id-1"),
            )

    def test_blank_contradiction_id_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_memory(contradiction_ids=("   ",))

    def test_expiry_must_follow_capture(self):
        with pytest.raises(ValidationError, match="expiry_timestamp must be after"):
            _make_memory(
                capture_timestamp=_LATER,
                expiry_timestamp=_NOW,
            )

    def test_quarantine_trust_contradiction_rejected(self):
        with pytest.raises(
            ValidationError,
            match="quarantined memory cannot simultaneously be TRUSTED",
        ):
            _make_memory(
                trust_status=MemoryTrustStatus.TRUSTED,
                trust_evidence_ids=("ev-001",),
                is_quarantined=True,
                quarantine_reason="test",
            )

    def test_trusted_without_evidence_rejected(self):
        with pytest.raises(
            ValidationError,
            match="TRUSTED memory must have at least one trust_evidence_id",
        ):
            _make_memory(
                trust_status=MemoryTrustStatus.TRUSTED,
                trust_evidence_ids=(),
            )

    def test_quarantined_without_reason_rejected(self):
        with pytest.raises(
            ValidationError,
            match="quarantined memory must have a quarantine_reason",
        ):
            _make_memory(
                trust_status=MemoryTrustStatus.QUARANTINED,
                is_quarantined=True,
            )

    def test_quarantine_status_flag_mismatch_rejected(self):
        with pytest.raises(ValidationError):
            _make_memory(
                trust_status=MemoryTrustStatus.QUARANTINED,
                is_quarantined=False,
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            _make_memory(credential="token-xyz")

    def test_blank_quarantine_reason_rejected(self):
        with pytest.raises(ValidationError):
            _make_memory(
                trust_status=MemoryTrustStatus.QUARANTINED,
                is_quarantined=True,
                quarantine_reason="   ",
            )


class TestMemoryRecordImmutability:
    """Post-construction mutation regression tests."""

    def test_trust_status_frozen(self):
        m = _make_memory()
        with pytest.raises(ValidationError):
            m.trust_status = MemoryTrustStatus.TRUSTED

    def test_source_frozen(self):
        m = _make_memory()
        with pytest.raises(ValidationError):
            m.source = "different"

    def test_expiry_frozen(self):
        m = _make_memory()
        with pytest.raises(ValidationError):
            m.expiry_timestamp = _MUCH_LATER

    def test_trust_evidence_ids_frozen(self):
        m = _make_memory(
            trust_status=MemoryTrustStatus.TRUSTED,
            trust_evidence_ids=("ev-001",),
        )
        with pytest.raises(ValidationError):
            m.trust_evidence_ids = ()

    def test_quarantine_flag_frozen(self):
        m = _make_memory()
        with pytest.raises(ValidationError):
            m.is_quarantined = True

    def test_collections_immutable(self):
        m = _make_memory(
            trust_status=MemoryTrustStatus.TRUSTED,
            trust_evidence_ids=("ev-001",),
        )
        assert isinstance(m.trust_evidence_ids, tuple)
        assert isinstance(m.contradiction_ids, tuple)
        assert not hasattr(m.trust_evidence_ids, "append")


class TestMemoryCredentialSurface:
    """MemoryRecord must not contain credential fields."""

    def test_no_credential_fields(self):
        for field_name in MemoryRecord.model_fields.keys():
            assert "token" not in field_name.lower()
            assert "key" not in field_name.lower(), f"field {field_name}"
            assert "secret" not in field_name.lower()
            assert "credential" not in field_name.lower()


# ===========================================================================
# SECTION 2: CAPABILITYPASSPORT TESTS
# ===========================================================================


class TestCapabilityPassportPositive:
    """Valid CapabilityPassport construction."""

    def test_valid_passport(self):
        p = _make_passport()
        assert p.passport_id == "pass-001"
        assert p.is_revoked is False
        assert p.revoked_at is None

    def test_valid_revoked_passport(self):
        p = _make_passport(
            is_revoked=True,
            revoked_at=_LATER,
            revocation_reason="Agent revision deprecated",
        )
        assert p.is_revoked is True
        assert p.revocation_reason == "Agent revision deprecated"


class TestCapabilityPassportValidation:
    """Negative validation tests for CapabilityPassport."""

    def test_version_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_passport(schema_version="")

    def test_agent_id_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_passport(agent_id="  ")

    def test_agent_revision_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_passport(agent_revision="")

    def test_qualified_capabilities_required(self):
        with pytest.raises(
            ValidationError,
            match="qualified_capabilities must not be empty",
        ):
            _make_passport(qualified_capabilities=())

    def test_qualification_evidence_required(self):
        with pytest.raises(
            ValidationError,
            match="qualification_evidence_ids must not be empty",
        ):
            _make_passport(qualification_evidence_ids=())

    def test_blank_capability_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_passport(qualified_capabilities=("cap-1", "  "))

    def test_duplicate_capability_rejects(self):
        with pytest.raises(ValidationError, match="duplicate"):
            _make_passport(qualified_capabilities=("cap-1", "cap-1"))

    def test_blank_qualification_evidence_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_passport(qualification_evidence_ids=("ev-1", "   "))

    def test_duplicate_qualification_evidence_rejects(self):
        with pytest.raises(ValidationError, match="duplicate"):
            _make_passport(qualification_evidence_ids=("ev-1", "ev-1"))

    def test_blank_tool_id_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_passport(qualified_tool_ids=("   ",))

    def test_duplicate_tool_id_rejects(self):
        with pytest.raises(ValidationError, match="duplicate"):
            _make_passport(qualified_tool_ids=("tool-1", "tool-1"))

    def test_expiry_ordering(self):
        with pytest.raises(
            ValidationError,
            match="expires_at must be after issued_at",
        ):
            _make_passport(issued_at=_LATER, expires_at=_NOW)

    def test_revocation_metadata_consistency(self):
        """Revoked passport without revoked_at rejects."""
        with pytest.raises(
            ValidationError,
            match="revoked passport must have revoked_at",
        ):
            _make_passport(is_revoked=True, revocation_reason="test")

    def test_revoked_at_before_issued_at_rejects(self):
        with pytest.raises(
            ValidationError,
            match="revoked_at must not predate issued_at",
        ):
            _make_passport(
                issued_at=_NOW,
                is_revoked=True,
                revoked_at=_NOW - timedelta(days=1),
                revocation_reason="test",
            )

    def test_revoked_without_reason_rejects(self):
        with pytest.raises(
            ValidationError,
            match="revoked passport must have revocation_reason",
        ):
            _make_passport(is_revoked=True, revoked_at=_LATER)

    def test_unrevoked_masquerade_rejects(self):
        """Unrevoked passport with revoked_at metadata rejects."""
        with pytest.raises(
            ValidationError,
            match="unrevoked passport must not have revoked_at",
        ):
            _make_passport(is_revoked=False, revoked_at=_LATER)

    def test_no_authorized_field(self):
        """CapabilityPassport must not have an 'authorized' field."""
        assert "authorized" not in CapabilityPassport.model_fields
        with pytest.raises(ValidationError):
            _make_passport(authorized=True)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            _make_passport(action_permission="WRITE")


class TestCapabilityPassportImmutability:
    """Post-construction mutation regression."""

    def test_agent_revision_frozen(self):
        p = _make_passport()
        with pytest.raises(ValidationError):
            p.agent_revision = "v3.0.0"

    def test_qualified_capabilities_frozen(self):
        p = _make_passport()
        with pytest.raises(ValidationError):
            p.qualified_capabilities = ()

    def test_expiry_frozen(self):
        p = _make_passport()
        with pytest.raises(ValidationError):
            p.expires_at = _MUCH_LATER

    def test_revocation_status_frozen(self):
        p = _make_passport()
        with pytest.raises(ValidationError):
            p.is_revoked = True

    def test_collections_immutable(self):
        p = _make_passport()
        assert isinstance(p.qualified_capabilities, tuple)
        assert isinstance(p.qualification_evidence_ids, tuple)
        assert not hasattr(p.qualified_capabilities, "append")


class TestCapabilityPassportAuthorityBoundary:
    """A valid passport alone does not contain or imply authorization."""

    def test_passport_has_no_authorization_field(self):
        """No field named 'authorized', 'permission', etc."""
        forbidden = {"authorized", "permission", "allowed", "granted"}
        for field_name in CapabilityPassport.model_fields.keys():
            assert field_name not in forbidden, (
                f"CapabilityPassport must not have field '{field_name}'"
            )


# ===========================================================================
# SECTION 3: REHEARSAL TESTS
# ===========================================================================


class TestRehearsalScenarioPositive:
    """Valid RehearsalScenario construction."""

    def test_valid_scenario(self):
        s = _make_scenario()
        assert s.scenario_id == "scen-001"

    def test_scenario_with_faults(self):
        fault = FaultInjectionSpec(
            fault_id="f-001",
            fault_type="latency",
            target="db-primary",
            parameters=(("delay_ms", "500"),),
        )
        s = _make_scenario(fault_injections=(fault,))
        assert len(s.fault_injections) == 1


class TestRehearsalScenarioValidation:
    """Negative tests for RehearsalScenario."""

    def test_version_id_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_scenario(schema_version="")

    def test_scenario_id_required(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_scenario(scenario_id="  ")

    def test_blank_description_rejects(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_scenario(description="   ")

    def test_empty_target_refs_rejects(self):
        with pytest.raises(ValidationError, match="target_refs must not be empty"):
            _make_scenario(target_refs=())

    def test_blank_target_ref_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_scenario(target_refs=("t1", "   "))

    def test_duplicate_target_refs_rejects(self):
        with pytest.raises(ValidationError, match="duplicate"):
            _make_scenario(target_refs=("t1", "t1"))

    def test_blank_success_criterion_ref_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_scenario(success_criterion_ids=("   ",))

    def test_blank_tool_double_ref_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_scenario(tool_double_ids=("   ",))

    def test_blank_fault_parameter_key_rejects(self):
        with pytest.raises(ValidationError, match="parameters keys must not be blank"):
            FaultInjectionSpec(
                fault_id="f1", fault_type="type1", target="t1", parameters=(("   ", "val"),)
            )

    def test_no_executable_callbacks(self):
        """RehearsalScenario has no callable or function fields."""
        for field_name, field_info in RehearsalScenario.model_fields.items():
            annotation = field_info.annotation
            assert annotation is not type(lambda: None), (
                f"RehearsalScenario must not have callable field '{field_name}'"
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            _make_scenario(callback=lambda: None)

    def test_scenario_collections_immutable(self):
        s = _make_scenario(target_refs=("a", "b"))
        assert isinstance(s.target_refs, tuple)
        assert not hasattr(s.target_refs, "append")


class TestRehearsalResultPositive:
    """Valid RehearsalResult construction."""

    def test_valid_simulation_pass(self):
        r = _make_result()
        assert r.state == EvidenceState.PASS
        assert r.provenance.collection_mode == ExecutionEvidenceMode.SIMULATION

    def test_simulation_pass_remains_simulation(self):
        """Simulation PASS is explicitly simulation provenance."""
        r = _make_result()
        assert r.provenance.collection_mode == ExecutionEvidenceMode.SIMULATION
        # Round-trip
        data = r.model_dump_json()
        loaded = RehearsalResult.model_validate_json(data)
        assert loaded.provenance.collection_mode == ExecutionEvidenceMode.SIMULATION


class TestRehearsalResultValidation:
    """Negative tests for RehearsalResult."""

    def test_mode_cannot_be_live_write(self):
        with pytest.raises(
            ValidationError,
            match="provenance.collection_mode == SIMULATION",
        ):
            _make_result(
                provenance=_make_provenance(ExecutionEvidenceMode.LIVE_WRITE),
            )

    def test_completion_before_start_rejected(self):
        with pytest.raises(
            ValidationError,
            match="completed_at must not precede started_at",
        ):
            _make_result(
                started_at=_LATER,
                completed_at=_NOW,
            )

    def test_pass_with_blank_evidence_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_result(evidence_record_ids=("   ",))

    def test_duplicate_evidence_refs_rejects(self):
        with pytest.raises(ValidationError, match="duplicate"):
            _make_result(evidence_record_ids=("ev1", "ev1"))

    def test_blank_diagnostic_ref_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_result(diagnostic_refs=("   ",))

    def test_pass_without_evidence_rejected(self):
        with pytest.raises(
            ValidationError,
            match="PASS result must have at least one evidence_record_id",
        ):
            _make_result(evidence_record_ids=())

    def test_fail_without_evidence_rejected(self):
        with pytest.raises(
            ValidationError,
            match="FAIL result must have at least one evidence_record_id",
        ):
            _make_result(
                state=EvidenceState.FAIL,
                evidence_record_ids=(),
            )

    def test_not_run_with_evidence_rejected(self):
        with pytest.raises(
            ValidationError,
            match="NOT_RUN result must not carry evidence_record_ids",
        ):
            _make_result(
                state=EvidenceState.NOT_RUN,
                evidence_record_ids=("ev-001",),
            )

    def test_blocked_with_evidence_rejected(self):
        with pytest.raises(
            ValidationError,
            match="BLOCKED result must not carry evidence_record_ids",
        ):
            _make_result(
                state=EvidenceState.BLOCKED,
                evidence_record_ids=("ev-001",),
            )

    def test_mode_state_orthogonal(self):
        """Mode (SIMULATION) and state (FAIL) are separate."""
        r = _make_result(
            state=EvidenceState.FAIL,
            evidence_record_ids=("ev-001",),
        )
        assert r.state == EvidenceState.FAIL
        assert r.provenance.collection_mode == ExecutionEvidenceMode.SIMULATION


class TestRehearsalResultImmutability:
    """Post-construction mutation regression."""

    def test_state_frozen(self):
        r = _make_result()
        with pytest.raises(ValidationError):
            r.state = EvidenceState.FAIL

    def test_provenance_frozen(self):
        r = _make_result()
        with pytest.raises(ValidationError):
            r.provenance = _make_provenance()

    def test_evidence_record_ids_frozen(self):
        r = _make_result()
        with pytest.raises(ValidationError):
            r.evidence_record_ids = ()

    def test_provenance_mode_frozen(self):
        r = _make_result()
        with pytest.raises(ValidationError):
            r.provenance.collection_mode = ExecutionEvidenceMode.LIVE_WRITE


# ===========================================================================
# SECTION 4: AUTONOMY TESTS
# ===========================================================================


class TestAutonomyClassVocabulary:
    """Exact enum vocabulary."""

    def test_exact_members(self):
        assert set(ac.value for ac in AutonomyClass) == {
            "AUTO_EXECUTE",
            "AUTO_EXECUTE_AND_NOTIFY",
            "REHEARSE_THEN_EXECUTE",
            "HUMAN_AUTHORITY_REQUIRED",
            "BLOCKED",
        }

    def test_unknown_class_rejects(self):
        with pytest.raises(ValidationError):
            _make_autonomy_decision(autonomy_class="MANUAL_REVIEW")

    def test_no_synonym_auto(self):
        with pytest.raises(ValueError):
            AutonomyClass("AUTO")

    def test_no_synonym_denied(self):
        with pytest.raises(ValueError):
            AutonomyClass("DENIED")


class TestAutonomyDecisionPositive:
    """Valid AutonomyDecision construction."""

    def test_auto_execute(self):
        d = _make_autonomy_decision(AutonomyClass.AUTO_EXECUTE)
        assert d.autonomy_class == AutonomyClass.AUTO_EXECUTE
        assert d.authority_slot_ref is None

    def test_auto_execute_and_notify(self):
        d = _make_autonomy_decision(AutonomyClass.AUTO_EXECUTE_AND_NOTIFY)
        assert d.authority_slot_ref is None

    def test_rehearse_then_execute(self):
        d = _make_autonomy_decision(AutonomyClass.REHEARSE_THEN_EXECUTE)
        assert len(d.required_rehearsal_refs) > 0

    def test_human_authority_required(self):
        d = _make_autonomy_decision(AutonomyClass.HUMAN_AUTHORITY_REQUIRED)
        assert d.authority_slot_ref is not None

    def test_blocked(self):
        d = _make_autonomy_decision(AutonomyClass.BLOCKED)
        assert d.autonomy_class == AutonomyClass.BLOCKED


class TestAutonomyDecisionValidation:
    """Negative tests for AutonomyDecision."""

    def test_human_authority_missing_slot_rejects(self):
        with pytest.raises(
            ValidationError,
            match="HUMAN_AUTHORITY_REQUIRED must have a non-blank authority_slot_ref",
        ):
            _make_autonomy_decision(
                AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
                authority_slot_ref=None,
            )

    def test_auto_execute_with_slot_rejects(self):
        with pytest.raises(
            ValidationError,
            match="AUTO_EXECUTE must not have authority_slot_ref",
        ):
            _make_autonomy_decision(
                AutonomyClass.AUTO_EXECUTE,
                authority_slot_ref="slot-001",
            )

    def test_auto_execute_and_notify_with_slot_rejects(self):
        with pytest.raises(
            ValidationError,
            match="AUTO_EXECUTE_AND_NOTIFY must not have authority_slot_ref",
        ):
            _make_autonomy_decision(
                AutonomyClass.AUTO_EXECUTE_AND_NOTIFY,
                authority_slot_ref="slot-001",
            )

    def test_rehearse_missing_rehearsal_rejects(self):
        with pytest.raises(
            ValidationError,
            match="REHEARSE_THEN_EXECUTE must have at least one",
        ):
            _make_autonomy_decision(
                AutonomyClass.REHEARSE_THEN_EXECUTE,
                required_rehearsal_refs=(),
            )

    def test_blocked_with_authority_slot_rejects(self):
        with pytest.raises(ValidationError, match="BLOCKED must not have authority_slot_ref"):
            _make_autonomy_decision(
                AutonomyClass.BLOCKED,
                authority_slot_ref="slot-1",
            )

    def test_rehearse_then_execute_with_authority_slot_rejects(self):
        with pytest.raises(
            ValidationError, match="REHEARSE_THEN_EXECUTE must not have authority_slot_ref"
        ):
            _make_autonomy_decision(
                AutonomyClass.REHEARSE_THEN_EXECUTE,
                authority_slot_ref="slot-1",
                required_rehearsal_refs=("reh-1",),
            )

    def test_rehearse_then_execute_blank_required_rehearsal_ref_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_autonomy_decision(
                AutonomyClass.REHEARSE_THEN_EXECUTE,
                required_rehearsal_refs=("   ",),
            )

    def test_duplicate_required_rehearsal_refs_rejects(self):
        with pytest.raises(ValidationError, match="duplicate"):
            _make_autonomy_decision(
                AutonomyClass.REHEARSE_THEN_EXECUTE,
                required_rehearsal_refs=("reh-1", "reh-1"),
            )


class TestLiveWriteAutonomyRegression:
    """P-05.04 §12: LIVE_WRITE ≠ HUMAN_AUTHORITY_REQUIRED.

    Both autonomous and human-gated LIVE_WRITE must be representable.
    """

    def test_live_write_auto_execute_valid(self):
        """LIVE_WRITE + AUTO_EXECUTE is valid if policy allows."""
        d = _make_autonomy_decision(
            AutonomyClass.AUTO_EXECUTE,
            action_class="LIVE_WRITE",
        )
        assert d.action_class == "LIVE_WRITE"
        assert d.autonomy_class == AutonomyClass.AUTO_EXECUTE

    def test_live_write_human_authority_valid(self):
        """LIVE_WRITE + HUMAN_AUTHORITY_REQUIRED is valid."""
        d = _make_autonomy_decision(
            AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
            action_class="LIVE_WRITE",
        )
        assert d.action_class == "LIVE_WRITE"
        assert d.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED

    def test_no_universal_live_write_gate(self):
        """Verify there is no validator that universally human-gates LIVE_WRITE."""
        # Both must succeed without error
        _make_autonomy_decision(AutonomyClass.AUTO_EXECUTE, action_class="LIVE_WRITE")
        _make_autonomy_decision(AutonomyClass.HUMAN_AUTHORITY_REQUIRED, action_class="LIVE_WRITE")


class TestGeminiNotAuthority:
    """P-05.04 §13: Gemini must not create human authority.

    No confidence/uncertainty fields in AutonomyDecision.
    """

    def test_no_confidence_field(self):
        forbidden = {
            "confidence",
            "model_confidence",
            "uncertainty",
            "gemini_confidence",
            "model_uncertainty",
        }
        for field_name in AutonomyDecision.model_fields.keys():
            assert field_name not in forbidden

    def test_no_auto_escalation_from_confidence(self):
        """Cannot construct with confidence or threshold fields."""
        with pytest.raises(ValidationError):
            _make_autonomy_decision(
                AutonomyClass.AUTO_EXECUTE,
                confidence=0.3,
            )


class TestAutonomyDecisionImmutability:
    """Post-construction mutation regression."""

    def test_auto_to_human_authority_frozen(self):
        d = _make_autonomy_decision(AutonomyClass.AUTO_EXECUTE)
        with pytest.raises(ValidationError):
            d.autonomy_class = AutonomyClass.HUMAN_AUTHORITY_REQUIRED

    def test_blocked_to_auto_frozen(self):
        d = _make_autonomy_decision(AutonomyClass.BLOCKED)
        with pytest.raises(ValidationError):
            d.autonomy_class = AutonomyClass.AUTO_EXECUTE

    def test_policy_source_frozen(self):
        d = _make_autonomy_decision(AutonomyClass.AUTO_EXECUTE)
        with pytest.raises(ValidationError):
            d.policy_source = "different"

    def test_authority_slot_frozen(self):
        d = _make_autonomy_decision(AutonomyClass.HUMAN_AUTHORITY_REQUIRED)
        with pytest.raises(ValidationError):
            d.authority_slot_ref = "different-slot"

    def test_blocked_cannot_become_human_authority(self):
        """BLOCKED cannot silently become human authority."""
        d = _make_autonomy_decision(AutonomyClass.BLOCKED)
        with pytest.raises(ValidationError):
            d.autonomy_class = AutonomyClass.HUMAN_AUTHORITY_REQUIRED


# ===========================================================================
# SECTION 5: APPROVAL COMPRESSION CARD TESTS
# ===========================================================================


class TestApprovalCompressionCardPositive:
    """Valid ApprovalCompressionCard construction."""

    def test_valid_card(self):
        card = _make_card()
        assert card.card_id == "card-001"
        assert card.autonomy_decision.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED


class TestApprovalCompressionCardValidation:
    """Negative tests for ApprovalCompressionCard."""

    def test_auto_execute_rejects(self):
        """Card tied to AUTO_EXECUTE must reject."""
        dec = _make_autonomy_decision(AutonomyClass.AUTO_EXECUTE)
        with pytest.raises(ValidationError):
            _make_card(
                autonomy_decision=dec,
                authority_slot_ref="dummy-slot",
            )

    def test_auto_execute_and_notify_rejects(self):
        """Card tied to AUTO_EXECUTE_AND_NOTIFY must reject."""
        dec = _make_autonomy_decision(
            AutonomyClass.AUTO_EXECUTE_AND_NOTIFY,
        )
        with pytest.raises(ValidationError):
            _make_card(
                autonomy_decision=dec,
                authority_slot_ref="dummy-slot",
            )

    def test_rehearse_then_execute_rejects(self):
        """Card tied to REHEARSE_THEN_EXECUTE must reject."""
        dec = _make_autonomy_decision(
            AutonomyClass.REHEARSE_THEN_EXECUTE,
        )
        with pytest.raises(ValidationError):
            _make_card(
                autonomy_decision=dec,
                authority_slot_ref="dummy-slot",
            )

    def test_blocked_rejects(self):
        """Card tied to BLOCKED must reject."""
        dec = _make_autonomy_decision(AutonomyClass.BLOCKED)
        with pytest.raises(ValidationError):
            _make_card(
                autonomy_decision=dec,
                authority_slot_ref="dummy-slot",
            )

    def test_mismatched_change_request_id_rejects(self):
        dec = _make_autonomy_decision(
            AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
        )
        with pytest.raises(
            ValidationError,
            match="card change_request_id must match",
        ):
            _make_card(
                autonomy_decision=dec,
                change_request_id="different-cr",
            )

    def test_mismatched_authority_slot_rejects(self):
        dec = _make_autonomy_decision(
            AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
        )
        with pytest.raises(
            ValidationError,
            match="card authority_slot_ref must match",
        ):
            _make_card(
                autonomy_decision=dec,
                authority_slot_ref="different-slot",
            )

    def test_blank_decision_question_rejects(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_card(decision_question="  ")

    def test_missing_authority_slot_rejects(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_card(authority_slot_ref="  ")

    def test_insufficient_options_reject(self):
        with pytest.raises(
            ValidationError,
            match="decision_options must have at least 2",
        ):
            _make_card(decision_options=("Approve",))

    def test_empty_options_reject(self):
        with pytest.raises(
            ValidationError,
            match="decision_options must have at least 2",
        ):
            _make_card(decision_options=())

    def test_duplicate_options_reject(self):
        with pytest.raises(
            ValidationError,
            match="decision_options must not contain duplicates",
        ):
            _make_card(decision_options=("Approve", "Approve"))

    def test_blank_decision_option_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_card(decision_options=("Approve", "   "))

    def test_duplicate_options_with_whitespace_rejects(self):
        with pytest.raises(ValidationError, match="duplicates"):
            _make_card(decision_options=("Approve", " Approve "))

    def test_blank_completed_work_summary_rejects(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_card(completed_work_summary="   ")

    def test_blank_rehearsed_work_summary_rejects(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_card(rehearsed_work_summary="   ")

    def test_blank_remaining_decision_summary_rejects(self):
        with pytest.raises(ValidationError, match="must not be blank"):
            _make_card(remaining_decision_summary="   ")

    def test_blank_evidence_ref_rejects(self):
        with pytest.raises(ValidationError, match="elements must not be blank"):
            _make_card(evidence_refs=("   ",))


class TestApprovalCardNoHumanResponse:
    """P-05.04 §16: Card must NOT contain human response fields."""

    def test_extra_approved_field_rejects(self):
        with pytest.raises(ValidationError):
            _make_card(approved=True)

    def test_extra_is_approved_field_rejects(self):
        with pytest.raises(ValidationError):
            _make_card(is_approved=True)

    def test_extra_human_decision_field_rejects(self):
        with pytest.raises(ValidationError):
            _make_card(human_decision="yes")

    def test_extra_human_response_field_rejects(self):
        with pytest.raises(ValidationError):
            _make_card(human_response="approved")

    def test_extra_approval_result_field_rejects(self):
        with pytest.raises(ValidationError):
            _make_card(approval_result="PASS")

    def test_extra_auto_approved_field_rejects(self):
        with pytest.raises(ValidationError):
            _make_card(auto_approved=True)

    def test_no_approval_field_in_model(self):
        """No field named 'approved', 'human_response', etc. exists."""
        forbidden = {
            "approved",
            "is_approved",
            "human_decision",
            "human_response",
            "approval_result",
            "auto_approved",
        }
        for field_name in ApprovalCompressionCard.model_fields.keys():
            assert field_name not in forbidden


class TestApprovalCompressionCardImmutability:
    """Post-construction mutation regression."""

    def test_autonomy_decision_frozen(self):
        card = _make_card()
        with pytest.raises(ValidationError):
            card.autonomy_decision = _make_autonomy_decision(
                AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
            )

    def test_authority_slot_frozen(self):
        card = _make_card()
        with pytest.raises(ValidationError):
            card.authority_slot_ref = "different-slot"

    def test_decision_options_frozen(self):
        card = _make_card()
        with pytest.raises(ValidationError):
            card.decision_options = ("A", "B", "C")

    def test_decision_question_frozen(self):
        card = _make_card()
        with pytest.raises(ValidationError):
            card.decision_question = "Changed question?"

    def test_action_scope_frozen(self):
        card = _make_card()
        with pytest.raises(ValidationError):
            card.action_scope = "different scope"


# ===========================================================================
# SECTION 6: CORE AUTHORITY REGRESSION MATRIX
# ===========================================================================


class TestCoreAuthorityRegressionMatrix:
    """P-05.04 §25: Structural proof of key domain separations."""

    def test_trusted_memory_not_authority(self):
        """A trusted MemoryRecord provides context, not authorization."""
        m = _make_memory(
            trust_status=MemoryTrustStatus.TRUSTED,
            trust_evidence_ids=("ev-001",),
        )
        assert m.trust_status == MemoryTrustStatus.TRUSTED
        # No authorization field exists
        assert "authorized" not in MemoryRecord.model_fields
        assert "permission" not in MemoryRecord.model_fields
        assert "action_allowed" not in MemoryRecord.model_fields

    def test_valid_capability_not_authorization(self):
        """A valid CapabilityPassport proves qualification, not authorization."""
        _make_passport()
        assert "authorized" not in CapabilityPassport.model_fields
        assert "action_permission" not in CapabilityPassport.model_fields

    def test_rehearsal_pass_not_live_authorization(self):
        """A SIMULATION PASS does not become LIVE_WRITE."""
        r = _make_result(state=EvidenceState.PASS)
        assert r.provenance.collection_mode == ExecutionEvidenceMode.SIMULATION
        # Cannot construct with LIVE_WRITE
        with pytest.raises(ValidationError):
            _make_result(
                provenance=_make_provenance(ExecutionEvidenceMode.LIVE_WRITE),
            )

    def test_autonomy_decision_not_human_approval(self):
        """HUMAN_AUTHORITY_REQUIRED != human approval granted."""
        _make_autonomy_decision(AutonomyClass.HUMAN_AUTHORITY_REQUIRED)
        assert "approved" not in AutonomyDecision.model_fields
        assert "human_response" not in AutonomyDecision.model_fields

    def test_card_exists_not_approval(self):
        """ApprovalCompressionCard existence != approval granted."""
        _make_card()
        assert "approved" not in ApprovalCompressionCard.model_fields

    def test_live_write_not_human_authority_required(self):
        """LIVE_WRITE does not universally require human authority."""
        d = _make_autonomy_decision(
            AutonomyClass.AUTO_EXECUTE,
            action_class="LIVE_WRITE",
        )
        assert d.autonomy_class == AutonomyClass.AUTO_EXECUTE

    def test_gemini_uncertainty_not_human_authority(self):
        """No model confidence field in AutonomyDecision."""
        assert "confidence" not in AutonomyDecision.model_fields

    def test_blocked_not_review_requested(self):
        """BLOCKED remains BLOCKED — not converted to human review."""
        d = _make_autonomy_decision(AutonomyClass.BLOCKED)
        assert d.autonomy_class == AutonomyClass.BLOCKED
        # BLOCKED cannot have authority slot
        assert d.authority_slot_ref is None


# ===========================================================================
# SECTION 7: PROVIDER-NEUTRALITY
# ===========================================================================

_FORBIDDEN_PREFIXES = (
    "google",
    "vertexai",
    "firebase",
    "firestore",
    "pubsub",
    "github",
    "opentelemetry",
    "pytest",
    "flask",
    "django",
    "fastapi",
)

_P0504_MODULES = [
    "domain.contracts.memory",
    "domain.contracts.capability",
    "domain.contracts.rehearsal",
    "domain.contracts.autonomy",
]


class TestProviderNeutrality:
    """AST import inspection for all P-05.04 contract modules."""

    @pytest.mark.parametrize("module_name", _P0504_MODULES)
    def test_no_forbidden_imports(self, module_name):
        import importlib

        mod = importlib.import_module(module_name)
        mod_path = pathlib.Path(mod.__file__)
        tree = ast.parse(mod_path.read_text())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in _FORBIDDEN_PREFIXES:
                        assert not alias.name.startswith(prefix), (
                            f"{module_name} imports forbidden '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for prefix in _FORBIDDEN_PREFIXES:
                        assert not node.module.startswith(prefix), (
                            f"{module_name} imports from forbidden '{node.module}'"
                        )


# ===========================================================================
# SECTION 8: CREDENTIAL BOUNDARY
# ===========================================================================


_CREDENTIAL_KEYWORDS = ("token", "secret", "credential", "api_key", "private_key")
_ALL_P0504_MODELS = [
    MemoryRecord,
    CapabilityPassport,
    RehearsalScenario,
    RehearsalResult,
    AutonomyDecision,
    ApprovalCompressionCard,
]


class TestCredentialBoundary:
    """None of the six schemas may contain reusable credentials."""

    @pytest.mark.parametrize("model_cls", _ALL_P0504_MODELS)
    def test_no_credential_fields(self, model_cls):
        for field_name in model_cls.model_fields.keys():
            for kw in _CREDENTIAL_KEYWORDS:
                assert kw not in field_name.lower(), (
                    f"{model_cls.__name__} has forbidden credential-like field '{field_name}'"
                )


# ===========================================================================
# SECTION 9: PUBLIC EXPORT SURFACE
# ===========================================================================


class TestPublicExports:
    """Verify __all__ contains all P-05.04 contracts."""

    def test_p0504_exports_present(self):
        exports = set(domain.contracts.__all__)
        required = {
            "MemoryRecord",
            "MemoryTrustStatus",
            "CapabilityPassport",
            "RehearsalScenario",
            "RehearsalResult",
            "FaultInjectionSpec",
            "AutonomyClass",
            "AutonomyDecision",
            "ApprovalCompressionCard",
        }
        for name in required:
            assert name in exports, f"Missing export: {name}"

    def test_p0501_02_03_exports_preserved(self):
        """Existing exports are not removed."""
        exports = set(domain.contracts.__all__)
        preserved = {
            "DataClassLevel",
            "DataClass",
            "SuccessCriterion",
            "ChangeRequest",
            "AgentDescriptor",
            "ToolDescriptor",
            "ChangeState",
            "IllegalTransitionError",
            "CHANGE_LIFECYCLE_VERSION",
            "can_transition",
            "require_transition",
            "is_terminal",
            "EvidenceRecord",
            "EvidenceState",
            "ExecutionEvidenceMode",
            "Provenance",
            "TraceReference",
            "ArtifactHash",
        }
        for name in preserved:
            assert name in exports, f"Missing preserved export: {name}"


# ===========================================================================
# SECTION 10: P-05.06 NON-LEAKAGE
# ===========================================================================


class TestP0506NonLeakage:
    """P-05.04 must not implement P-05.06 naming/serialization concepts."""

    def test_no_serialization_conventions_in_exports(self):
        exports = set(domain.contracts.__all__)
        forbidden = {
            "canonical_hash",
            "canonical_json",
            "timestamp_wire_format",
            "redaction_policy",
            "naming_convention",
        }
        for name in forbidden:
            assert name not in exports, f"P-05.06 concept '{name}' leaked into exports"

    @pytest.mark.parametrize("module_name", _P0504_MODULES)
    def test_no_event_envelope_fields(self, module_name):
        """P-05.04 modules don't define event-envelope-specific fields."""
        import importlib

        mod = importlib.import_module(module_name)
        mod_path = pathlib.Path(mod.__file__)
        source = mod_path.read_text()
        # These are P-05.05 specific field names
        for concept in ("causation_id", "correlation_id", "idempotency_key"):
            assert concept not in source, f"P-05.05 concept '{concept}' found in {module_name}"


# ===========================================================================
# SECTION 11: VERSIONING
# ===========================================================================


class TestVersioning:
    """All six contracts require explicit non-blank schema_version."""

    @pytest.mark.parametrize(
        "factory,kwargs",
        [
            (_make_memory, {}),
            (_make_passport, {}),
            (_make_scenario, {}),
            (_make_result, {}),
            (
                _make_autonomy_decision,
                {"autonomy_class": AutonomyClass.AUTO_EXECUTE},
            ),
            (_make_card, {}),
        ],
    )
    def test_version_required(self, factory, kwargs):
        with pytest.raises(ValidationError, match="must not be blank"):
            factory(schema_version="  ", **kwargs)

    @pytest.mark.parametrize(
        "factory,kwargs",
        [
            (_make_memory, {}),
            (_make_passport, {}),
            (_make_scenario, {}),
            (_make_result, {}),
            (
                _make_autonomy_decision,
                {"autonomy_class": AutonomyClass.AUTO_EXECUTE},
            ),
            (_make_card, {}),
        ],
    )
    def test_version_present(self, factory, kwargs):
        obj = factory(**kwargs)
        assert obj.schema_version == "1.0"
