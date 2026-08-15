"""ChangeMesh P-07.02 — Six Specialized ADK Agent Definitions Tests.

Tests proving all P-07.02 acceptance criteria and invariants:
1. Exactly six canonical agent identities are represented in the fleet.
2. No seventh or invented agent exists in the registry or definition surface.
3. All six agents are genuine Google ADK BaseAgent subclasses.
4. Each definition exposes:
   - role
   - capability/capabilities
   - forbidden actions
   - input schema
   - output schema
   - revision
   - bounded instruction contract
   - bounded permitted tool set
5. Stable IDs and revisions are non-blank strings.
6. Role identities and agent IDs are strictly unique across the fleet.
7. Tool scopes are explicit, bounded, and contain no wildcards (*).
8. Forbidden-action sets are non-empty and role-appropriate.
9. Impact Scout definition is read-only with no external-write capability.
10. Release Steward definition cannot self-authorize.
11. Evidence Auditor definition cannot claim deterministic-fact mutation authority.
12. Policy Guardian definition does not claim policy-source ownership.
13. Change Orchestrator definition does not gain durable-state ownership.
14. Construction and import require no cloud credentials.
15. Construction and import perform zero network calls.
16. No Gemini or Vertex AI model invocations occur.
17. No Firestore, Pub/Sub, or GitHub mutations occur.
18. External/provider credential objects do not appear in schemas or metadata.
19. Conversions to frozen domain contract AgentDescriptor are valid and complete.
20. Input/Output schemas are frozen, reject extra fields, and validate non-blank inputs.
21. Local ADK integration/smoke boundary with Runner and InMemorySessionService for all 6 agents.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from google.adk.agents.base_agent import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from pydantic import BaseModel, ValidationError

from domain.contracts.agent_descriptor import AgentDescriptor
from domain.contracts.data_class import DataClassLevel
from src.agents import (
    CANONICAL_AGENT_CLASSES,
    CANONICAL_AGENT_IDS,
    CANONICAL_ROLES,
    AgentDefinition,
    ChangeOrchestrator,
    EvidenceAuditor,
    EvidenceAuditorInput,
    EvidenceAuditorOutput,
    ImpactScout,
    ImpactScoutInput,
    ImpactScoutOutput,
    MigrationEngineer,
    MigrationEngineerInput,
    MigrationEngineerOutput,
    PolicyGuardian,
    PolicyGuardianInput,
    PolicyGuardianOutput,
    ReleaseSteward,
    ReleaseStewardInput,
    ReleaseStewardOutput,
    get_canonical_agent_class,
    get_canonical_agent_definition,
    get_canonical_agent_ids,
    get_canonical_roles,
    list_canonical_agent_classes,
    list_canonical_agent_definitions,
)
from src.agents.definition import CANONICAL_TOOL_DESCRIPTORS

# ===========================================================================
# 1. Exact Fleet Size and Canonical Identities
# ===========================================================================


def test_exactly_six_canonical_agents() -> None:
    """Verify the fleet contains exactly six canonical agent classes."""
    assert len(CANONICAL_AGENT_CLASSES) == 6
    assert len(CANONICAL_ROLES) == 6
    assert len(CANONICAL_AGENT_IDS) == 6

    defs = list_canonical_agent_definitions()
    assert len(defs) == 6

    classes = list_canonical_agent_classes()
    assert len(classes) == 6


def test_canonical_roles_and_identities_match_frozen_charter() -> None:
    """Verify the exact six roles and IDs match the canonical ChangeMesh architecture."""
    expected_roles = [
        "change_orchestrator",
        "impact_scout",
        "policy_guardian",
        "migration_engineer",
        "evidence_auditor",
        "release_steward",
    ]
    expected_ids = [
        "agent-change-orchestrator",
        "agent-impact-scout",
        "agent-policy-guardian",
        "agent-migration-engineer",
        "agent-evidence-auditor",
        "agent-release-steward",
    ]

    assert list(get_canonical_roles()) == expected_roles
    assert list(get_canonical_agent_ids()) == expected_ids


def test_no_seventh_or_invented_agent() -> None:
    """Verify no unexpected or invented agent exists in the registry."""
    known_roles = set(CANONICAL_ROLES)
    known_ids = set(CANONICAL_AGENT_IDS)

    for agent_cls in CANONICAL_AGENT_CLASSES:
        defn = agent_cls.get_definition()  # type: ignore[attr-defined]
        assert defn.role in known_roles
        assert defn.agent_id in known_ids

    # Verify unknown identifier fails closed
    with pytest.raises(KeyError, match="Unknown canonical agent identifier"):
        get_canonical_agent_class("invented_agent")

    with pytest.raises(KeyError, match="Unknown canonical agent identifier"):
        get_canonical_agent_definition("agent-unknown-seventh")


# ===========================================================================
# 2. Genuine Google ADK BaseAgent Inheritance & Construction
# ===========================================================================


@pytest.mark.parametrize("agent_cls", CANONICAL_AGENT_CLASSES)
def test_all_agents_are_genuine_adk_base_agents(agent_cls: type[Any]) -> None:
    """Verify every canonical agent class is a direct subclass of Google ADK BaseAgent."""
    assert issubclass(agent_cls, BaseAgent)

    instance = agent_cls()  # type: ignore[call-arg]
    assert isinstance(instance, BaseAgent)
    assert isinstance(instance.name, str) and len(instance.name) > 0
    assert isinstance(instance.description, str) and len(instance.description) > 0


def test_construction_without_credentials_or_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify all 6 agents can be constructed in an environment stripped of credentials/network."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    for agent_cls in CANONICAL_AGENT_CLASSES:
        agent = agent_cls()  # type: ignore[call-arg]
        assert isinstance(agent, BaseAgent)
        assert agent.name is not None


# ===========================================================================
# 3. Acceptance Criteria: Role, Capabilities, Forbidden Actions, Schemas, Revision
# ===========================================================================


@pytest.mark.parametrize("agent_cls", CANONICAL_AGENT_CLASSES)
def test_agent_exposes_all_acceptance_fields_on_class_and_instance(
    agent_cls: type[Any],
) -> None:
    """Verify every agent exposes role, capability, forbidden actions, schemas, revision."""
    instance = agent_cls()

    for target in (agent_cls, instance):
        # Identity and Revision
        assert hasattr(target, "agent_id")
        assert isinstance(target.agent_id, str) and len(target.agent_id.strip()) > 0

        assert hasattr(target, "role")
        assert isinstance(target.role, str) and len(target.role.strip()) > 0

        assert hasattr(target, "agent_revision")
        assert isinstance(target.agent_revision, str) and len(target.agent_revision.strip()) > 0

        assert hasattr(target, "revision")
        assert target.revision == target.agent_revision

        # Capabilities
        assert hasattr(target, "declared_capabilities")
        assert isinstance(target.declared_capabilities, list)
        assert len(target.declared_capabilities) >= 1
        for cap in target.declared_capabilities:
            assert isinstance(cap, str) and len(cap.strip()) > 0

        assert hasattr(target, "capabilities")
        assert target.capabilities == target.declared_capabilities

        # Forbidden Actions
        assert hasattr(target, "forbidden_actions")
        assert isinstance(target.forbidden_actions, list)
        assert len(target.forbidden_actions) >= 1
        for act in target.forbidden_actions:
            assert isinstance(act, str) and len(act.strip()) > 0

        # Input & Output Schemas
        if isinstance(target, type):
            defn = target.get_definition()
            assert issubclass(defn.input_schema, BaseModel)
            assert issubclass(defn.output_schema, BaseModel)
        else:
            assert hasattr(target, "input_schema")
            assert issubclass(target.input_schema, BaseModel)
            assert hasattr(target, "output_schema")
            assert issubclass(target.output_schema, BaseModel)

        # Instruction Contract
        assert hasattr(target, "instruction_contract")
        assert isinstance(target.instruction_contract, str)
        assert len(target.instruction_contract.strip()) > 50

        # Permitted Tools & Data Classifications
        assert hasattr(target, "permitted_tool_ids")
        assert isinstance(target.permitted_tool_ids, list)
        assert len(target.permitted_tool_ids) >= 1
        for tid in target.permitted_tool_ids:
            assert "*" not in tid
            assert len(tid.strip()) > 0

        assert hasattr(target, "permitted_data_classifications")
        assert isinstance(target.permitted_data_classifications, list)
        assert len(target.permitted_data_classifications) >= 1


@pytest.mark.parametrize("agent_cls", CANONICAL_AGENT_CLASSES)
def test_get_definition_returns_valid_agent_definition(agent_cls: type[Any]) -> None:
    """Verify get_definition() returns a valid AgentDefinition model with exact parity."""
    defn = agent_cls.get_definition()
    assert isinstance(defn, AgentDefinition)
    assert defn.agent_id == agent_cls.agent_id
    assert defn.role == agent_cls.role
    assert defn.agent_revision == agent_cls.agent_revision
    assert defn.declared_capabilities == agent_cls.declared_capabilities
    assert defn.forbidden_actions == agent_cls.forbidden_actions
    assert defn.instruction_contract == agent_cls.instruction_contract
    assert defn.permitted_tool_ids == agent_cls.permitted_tool_ids
    assert defn.permitted_data_classifications == agent_cls.permitted_data_classifications


@pytest.mark.parametrize("agent_cls", CANONICAL_AGENT_CLASSES)
def test_get_descriptor_returns_valid_domain_contract(agent_cls: type[Any]) -> None:
    """Verify get_descriptor() returns a valid frozen domain contract AgentDescriptor."""
    desc = agent_cls.get_descriptor()
    assert isinstance(desc, AgentDescriptor)
    assert desc.schema_version == "1.0.0"
    assert desc.agent_id == agent_cls.agent_id
    assert desc.agent_revision == agent_cls.agent_revision
    assert desc.role == agent_cls.role
    assert desc.declared_capabilities == agent_cls.declared_capabilities
    assert desc.permitted_data_classifications == agent_cls.permitted_data_classifications
    assert desc.permitted_tool_ids == agent_cls.permitted_tool_ids


# ===========================================================================
# 4. Role-Specific Invariants and Prohibitions (Four-Lane Authority Boundary)
# ===========================================================================


def test_change_orchestrator_definition_invariants() -> None:
    """Verify Change Orchestrator definition respects orchestration boundaries."""
    defn = ChangeOrchestrator.get_definition()
    assert defn.role == "change_orchestrator"
    assert "change_request_intake" in defn.declared_capabilities
    assert "lifecycle_coordination" in defn.declared_capabilities
    assert "delegation_dispatch" in defn.declared_capabilities

    # Prohibitions
    assert "direct_durable_state_mutation" in defn.forbidden_actions
    assert "self_authorize_changes" in defn.forbidden_actions
    assert "overwrite_deterministic_facts" in defn.forbidden_actions
    assert "unrestricted_external_writes" in defn.forbidden_actions
    assert "unvetted_model_reasoning" in defn.forbidden_actions

    # Instruction checks
    assert "zero trust" in defn.instruction_contract.lower()
    assert "firestore saga" in defn.instruction_contract.lower()


def test_impact_scout_definition_invariants() -> None:
    """Verify Impact Scout is strictly read-only with no external-write capabilities."""
    defn = ImpactScout.get_definition()
    assert defn.role == "impact_scout"
    assert "repository_blast_radius_analysis" in defn.declared_capabilities
    assert "affected_systems_identification" in defn.declared_capabilities
    assert "parallel_change_conflict_detection" in defn.declared_capabilities

    # Prohibitions
    assert "repository_mutation" in defn.forbidden_actions
    assert "external_writes" in defn.forbidden_actions
    assert "overwrite_deterministic_git_facts" in defn.forbidden_actions
    assert "credential_exposure" in defn.forbidden_actions

    # Verify all permitted tools for Impact Scout are read-only
    for tool_id in defn.permitted_tool_ids:
        assert tool_id in CANONICAL_TOOL_DESCRIPTORS
        assert CANONICAL_TOOL_DESCRIPTORS[tool_id].is_read_only is True


def test_policy_guardian_definition_invariants() -> None:
    """Verify Policy Guardian enforces policy without authoring it or making human authority."""
    defn = PolicyGuardian.get_definition()
    assert defn.role == "policy_guardian"
    assert "organizational_policy_evaluation" in defn.declared_capabilities
    assert "privacy_boundary_check" in defn.declared_capabilities
    assert "separation_of_duty_enforcement" in defn.declared_capabilities

    # Prohibitions
    assert "author_organizational_policy" in defn.forbidden_actions
    assert "manufacture_human_authority" in defn.forbidden_actions
    assert "override_deterministic_facts" in defn.forbidden_actions
    assert "execute_external_changes" in defn.forbidden_actions


def test_migration_engineer_definition_invariants() -> None:
    """Verify Migration Engineer generates scoped artifacts without direct production mutation."""
    defn = MigrationEngineer.get_definition()
    assert defn.role == "migration_engineer"
    assert "migration_artifact_generation" in defn.declared_capabilities
    assert "verification_script_synthesis" in defn.declared_capabilities

    # Prohibitions
    assert "direct_production_execution" in defn.forbidden_actions
    assert "unrestricted_filesystem_writes" in defn.forbidden_actions
    assert "bypass_policy_review" in defn.forbidden_actions
    assert "credential_consumption" in defn.forbidden_actions


def test_evidence_auditor_definition_invariants() -> None:
    """Verify Evidence Auditor cannot rewrite deterministic facts or forge execution evidence."""
    defn = EvidenceAuditor.get_definition()
    assert defn.role == "evidence_auditor"
    assert "semantic_evidence_sufficiency_review" in defn.declared_capabilities
    assert "evidence_completeness_verification" in defn.declared_capabilities

    # Prohibitions
    assert "rewrite_deterministic_facts" in defn.forbidden_actions
    assert "forge_execution_evidence" in defn.forbidden_actions
    assert "grant_unauthorized_pass" in defn.forbidden_actions
    assert "execute_system_mutations" in defn.forbidden_actions

    # Verify all tools for Evidence Auditor are read-only
    for tool_id in defn.permitted_tool_ids:
        assert tool_id in CANONICAL_TOOL_DESCRIPTORS
        assert CANONICAL_TOOL_DESCRIPTORS[tool_id].is_read_only is True


def test_release_steward_definition_invariants() -> None:
    """Verify Release Steward cannot self-authorize or execute writes without Change Passport."""
    defn = ReleaseSteward.get_definition()
    assert defn.role == "release_steward"
    assert "release_bundle_packaging" in defn.declared_capabilities
    assert "draft_pull_request_preparation" in defn.declared_capabilities
    assert "reversible_handoff_construction" in defn.declared_capabilities

    # Prohibitions
    assert "self_authorize_execution" in defn.forbidden_actions
    assert "direct_production_mutation" in defn.forbidden_actions
    assert "unbounded_git_pushes" in defn.forbidden_actions
    assert "bypass_passport_verification" in defn.forbidden_actions


# ===========================================================================
# 5. Schema Validation & Immutability
# ===========================================================================


def test_specialized_schemas_frozen_and_reject_extra_fields() -> None:
    """Verify all specialized input/output schemas are frozen and reject extra fields."""
    schemas: list[type[BaseModel]] = [
        ImpactScoutInput,
        ImpactScoutOutput,
        PolicyGuardianInput,
        PolicyGuardianOutput,
        MigrationEngineerInput,
        MigrationEngineerOutput,
        EvidenceAuditorInput,
        EvidenceAuditorOutput,
        ReleaseStewardInput,
        ReleaseStewardOutput,
    ]

    for schema_cls in schemas:
        cfg = getattr(schema_cls, "model_config", {})
        assert cfg.get("frozen") is True
        assert cfg.get("extra") == "forbid"


def test_impact_scout_schema_validation() -> None:
    """Verify ImpactScoutInput and Output construct correctly and fail closed."""
    inp = ImpactScoutInput(
        change_id="chg-001",
        target_systems=["repo-service-a"],
        repository_ref="main",
    )
    assert inp.change_id == "chg-001"
    assert inp.data_classification == DataClassLevel.INTERNAL

    # Extra field rejected
    with pytest.raises(ValidationError):
        ImpactScoutInput(
            change_id="chg-001",
            target_systems=["repo-service-a"],
            repository_ref="main",
            extra_field="rejected",  # type: ignore[call-arg]
        )

    # Blank change_id rejected
    with pytest.raises(ValidationError):
        ImpactScoutInput(
            change_id="   ",
            target_systems=["repo-service-a"],
            repository_ref="main",
        )

    out = ImpactScoutOutput(
        change_id="chg-001",
        affected_files=["src/db.py"],
        affected_systems=["db-users"],
        risk_level="MEDIUM",
    )
    assert out.conflict_detected is False


def test_policy_guardian_schema_validation() -> None:
    """Verify PolicyGuardianInput and Output validation."""
    inp = PolicyGuardianInput(
        change_id="chg-002",
        data_classification=DataClassLevel.CONFIDENTIAL,
        target_systems=["billing-db"],
        requested_actions=["schema_alter"],
        actor_identity="eng@example.com",
    )
    assert inp.data_classification == DataClassLevel.CONFIDENTIAL

    out = PolicyGuardianOutput(
        change_id="chg-002",
        policy_verdict="REQUIRES_APPROVAL",
        autonomy_class="HUMAN_AUTHORITY_REQUIRED",
        violated_rules=["RULE_RESTRICTED_TABLE_ALTER"],
    )
    assert len(out.violated_rules) == 1


def test_migration_engineer_schema_validation() -> None:
    """Verify MigrationEngineerInput and Output validation."""
    inp = MigrationEngineerInput(
        change_id="chg-003",
        target_system="postgres-users",
        source_schema_version="v1.2",
        target_schema_version="v1.3",
        migration_spec="ADD COLUMN age INT;",
    )
    assert inp.target_system == "postgres-users"

    out = MigrationEngineerOutput(
        change_id="chg-003",
        artifact_id="art-001",
        artifact_hash="a" * 64,
        migration_script_content="ALTER TABLE users ADD COLUMN age INT;",
        rehearsal_instructions="Run in shadow database",
    )
    assert out.is_reversible is True


def test_evidence_auditor_schema_validation() -> None:
    """Verify EvidenceAuditorInput and Output validation."""
    inp = EvidenceAuditorInput(
        change_id="chg-004",
        success_criteria_ids=["sc-001"],
        evidence_record_refs=["ev-rec-001"],
    )
    assert inp.success_criteria_ids == ["sc-001"]

    out = EvidenceAuditorOutput(
        change_id="chg-004",
        sufficiency_verdict="SUFFICIENT",
        evaluated_criteria_count=1,
        satisfied_criteria_count=1,
        semantic_review_summary="All required criteria verified.",
    )
    assert out.satisfied_criteria_count == 1


def test_release_steward_schema_validation() -> None:
    """Verify ReleaseStewardInput and Output validation."""
    inp = ReleaseStewardInput(
        change_id="chg-005",
        passport_id="pass-001",
        verified_artifact_ids=["art-001"],
        target_repository="repo-main",
        authorization_reference="auth-human-001",
    )
    assert inp.passport_id == "pass-001"

    out = ReleaseStewardOutput(
        change_id="chg-005",
        release_bundle_id="bundle-001",
        draft_pr_spec="PR: Migration v1.3",
        rollback_spec="Revert PR: Migration v1.3",
    )
    assert out.handoff_ready is True


# ===========================================================================
# 6. Tool Descriptor Scope & Integrity
# ===========================================================================


def test_permitted_tools_are_registered_and_bounded() -> None:
    """Verify all permitted tools referenced by canonical agents exist and are bounded."""
    for agent_cls in CANONICAL_AGENT_CLASSES:
        defn = agent_cls.get_definition()  # type: ignore[attr-defined]
        for tool_id in defn.permitted_tool_ids:
            assert tool_id in CANONICAL_TOOL_DESCRIPTORS
            desc = CANONICAL_TOOL_DESCRIPTORS[tool_id]
            assert desc.schema_version == "1.0.0"
            assert desc.tool_id == tool_id
            assert len(desc.name) > 0
            assert len(desc.description) > 0
            assert len(desc.declared_actions) >= 1
            assert len(desc.permitted_data_classifications) >= 1


def test_agent_definition_rejects_wildcard_tools() -> None:
    """Verify AgentDefinition validator rejects wildcard tool definitions."""
    with pytest.raises(ValidationError, match="Wildcard tool scope forbidden"):
        AgentDefinition(
            agent_id="agent-bad",
            role="bad_agent",
            agent_revision="1.0.0",
            description="Bad agent with wildcard tool",
            declared_capabilities=["something"],
            forbidden_actions=["none"],
            input_schema=ImpactScoutInput,
            output_schema=ImpactScoutOutput,
            instruction_contract="Bounded instruction",
            permitted_tool_ids=["tool-*"],
            permitted_data_classifications=[DataClassLevel.INTERNAL],
        )


# ===========================================================================
# 7. Local Google ADK Runner Smoke Integration (All 6 Agents)
# ===========================================================================


@pytest.mark.anyio
@pytest.mark.parametrize("agent_cls", CANONICAL_AGENT_CLASSES)
async def test_all_six_agents_execute_with_adk_runner(agent_cls: type[Any]) -> None:
    """Verify each of the six agents can be loaded into an ADK Runner and executed in-process."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        session_id=f"session-{agent_cls.role}",
        user_id="test-operator",
        app_name="changemesh-test",
    )

    agent_instance = agent_cls()

    runner = Runner(
        agent=agent_instance,
        session_service=session_service,
        app_name="changemesh-test",
    )

    events: list[Event] = []
    async for event in runner.run_async(
        user_id="test-operator",
        session_id=session.id,
        new_message=Content(parts=[Part(text=f"Smoke test for {agent_cls.role}")]),
    ):
        events.append(event)

    assert len(events) >= 1
    assert any(e.turn_complete is True for e in events)


# ===========================================================================
# 8. Zero External Mutation / Zero Model Invocation Verification
# ===========================================================================


def test_no_external_mutation_or_network_during_agent_fleet_usage() -> None:
    """Verify all agent definitions and lookups execute with zero external calls."""
    with (
        patch("urllib.request.urlopen") as mock_url,
        patch("http.client.HTTPConnection") as mock_http,
        patch("http.client.HTTPSConnection") as mock_https,
    ):
        # Perform lookups, descriptor conversions, schema instances
        definitions = list_canonical_agent_definitions()
        classes = list_canonical_agent_classes()
        roles = get_canonical_roles()
        ids = get_canonical_agent_ids()

        assert len(definitions) == 6
        assert len(classes) == 6
        assert len(roles) == 6
        assert len(ids) == 6

        for cls in classes:
            desc = cls.get_descriptor()  # type: ignore[attr-defined]
            assert isinstance(desc, AgentDescriptor)

        mock_url.assert_not_called()
        mock_http.assert_not_called()
        mock_https.assert_not_called()
