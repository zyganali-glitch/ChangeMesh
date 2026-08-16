"""ChangeMesh canonical demo action autonomy mapping.

P-14.03: Provides deterministic mapping and policy classification for all 7 canonical
demo actions, specifying autonomy class, required privilege, required rehearsal,
and human authority requirements.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict

from pydantic import BaseModel, ConfigDict

from domain.contracts.autonomy import AutonomyClass
from src.gate.reversibility import (
    PrivilegeLevel,
    RehearsalStatus,
    ReversibilityClass,
)

CANONICAL_SCHEMA_VERSION = "1.0.0"


class CanonicalActionType(str, Enum):
    """The 7 canonical actions in the ChangeMesh demo workflow."""

    ANALYSIS = "ANALYSIS"
    BRANCH = "BRANCH"
    DRAFT_PR = "DRAFT_PR"
    STAGING_MUTATION = "STAGING_MUTATION"
    PRODUCTION_ADD_DROP = "PRODUCTION_ADD_DROP"
    PRIVILEGE_EXPANSION = "PRIVILEGE_EXPANSION"
    DATA_EXPORT = "DATA_EXPORT"


class ActionAutonomyPolicy(BaseModel):
    """Deterministic autonomy policy for a specific action type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_type: CanonicalActionType
    autonomy_class: AutonomyClass
    requires_human_authority: bool
    required_privilege: PrivilegeLevel
    expected_reversibility: ReversibilityClass
    rehearsal_requirement: RehearsalStatus
    policy_rationale: str
    authority_slot_ref: str = ""


def get_canonical_action_map() -> Dict[CanonicalActionType, ActionAutonomyPolicy]:
    """Return the complete canonical action autonomy policy table."""
    return {
        CanonicalActionType.ANALYSIS: ActionAutonomyPolicy(
            action_type=CanonicalActionType.ANALYSIS,
            autonomy_class=AutonomyClass.AUTO_EXECUTE,
            requires_human_authority=False,
            required_privilege=PrivilegeLevel.READ_ONLY,
            expected_reversibility=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            rehearsal_requirement=RehearsalStatus.NOT_REQUIRED,
            policy_rationale="Read-only static AST analysis executes fully autonomously",
        ),
        CanonicalActionType.BRANCH: ActionAutonomyPolicy(
            action_type=CanonicalActionType.BRANCH,
            autonomy_class=AutonomyClass.AUTO_EXECUTE,
            requires_human_authority=False,
            required_privilege=PrivilegeLevel.STANDARD_WRITE,
            expected_reversibility=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            rehearsal_requirement=RehearsalStatus.NOT_REQUIRED,
            policy_rationale="Git feature branch creation is non-destructive and fully reversible",
        ),
        CanonicalActionType.DRAFT_PR: ActionAutonomyPolicy(
            action_type=CanonicalActionType.DRAFT_PR,
            autonomy_class=AutonomyClass.AUTO_EXECUTE,
            requires_human_authority=False,
            required_privilege=PrivilegeLevel.STANDARD_WRITE,
            expected_reversibility=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            rehearsal_requirement=RehearsalStatus.NOT_REQUIRED,
            policy_rationale="Draft PR generation carries zero production risk and is reversible",
        ),
        CanonicalActionType.STAGING_MUTATION: ActionAutonomyPolicy(
            action_type=CanonicalActionType.STAGING_MUTATION,
            autonomy_class=AutonomyClass.REHEARSE_THEN_EXECUTE,
            requires_human_authority=False,
            required_privilege=PrivilegeLevel.SCHEMA_MODIFY,
            expected_reversibility=ReversibilityClass.REVERSIBLE_WITH_COMPENSATION,
            rehearsal_requirement=RehearsalStatus.REHEARSAL_PASSED,
            policy_rationale="Staging changes require verified rehearsal before execution",
        ),
        CanonicalActionType.PRODUCTION_ADD_DROP: ActionAutonomyPolicy(
            action_type=CanonicalActionType.PRODUCTION_ADD_DROP,
            autonomy_class=AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
            requires_human_authority=True,
            required_privilege=PrivilegeLevel.DDL_ADMIN,
            expected_reversibility=ReversibilityClass.HUMAN_INTERVENTION_REQUIRED,
            rehearsal_requirement=RehearsalStatus.REHEARSAL_PASSED,
            policy_rationale="Production DDL mutations require explicit human authority decision",
            authority_slot_ref="slot:lead_dba",
        ),
        CanonicalActionType.PRIVILEGE_EXPANSION: ActionAutonomyPolicy(
            action_type=CanonicalActionType.PRIVILEGE_EXPANSION,
            autonomy_class=AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
            requires_human_authority=True,
            required_privilege=PrivilegeLevel.IAM_ADMIN,
            expected_reversibility=ReversibilityClass.HUMAN_INTERVENTION_REQUIRED,
            rehearsal_requirement=RehearsalStatus.NOT_REQUIRED,
            policy_rationale="IAM role expansion requires human security officer confirmation",
            authority_slot_ref="slot:security_officer",
        ),
        CanonicalActionType.DATA_EXPORT: ActionAutonomyPolicy(
            action_type=CanonicalActionType.DATA_EXPORT,
            autonomy_class=AutonomyClass.HUMAN_AUTHORITY_REQUIRED,
            requires_human_authority=True,
            required_privilege=PrivilegeLevel.DATA_EXPORT,
            expected_reversibility=ReversibilityClass.HUMAN_INTERVENTION_REQUIRED,
            rehearsal_requirement=RehearsalStatus.NOT_REQUIRED,
            policy_rationale="Bulk data export requires explicit compliance approval",
            authority_slot_ref="slot:data_officer",
        ),
    }
