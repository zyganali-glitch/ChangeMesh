"""ChangeMesh deterministic reversibility classifier and policy inputs.

P-14.01: Evaluates schema change operations, DDL structure, and blast radius to produce
an authoritative reversibility classification and deterministic policy inputs.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.data_class import DataClassLevel
from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode

CANONICAL_SCHEMA_VERSION = "1.0.0"


class ReversibilityClass(str, Enum):
    """Canonical 4-class reversibility taxonomy."""

    FULLY_REVERSIBLE_AUTOMATED = "FULLY_REVERSIBLE_AUTOMATED"
    REVERSIBLE_WITH_COMPENSATION = "REVERSIBLE_WITH_COMPENSATION"
    HUMAN_INTERVENTION_REQUIRED = "HUMAN_INTERVENTION_REQUIRED"
    IRREVERSIBLE_DESTRUCTIVE = "IRREVERSIBLE_DESTRUCTIVE"


class PrivilegeLevel(str, Enum):
    """Privilege tiers required for executing actions."""

    READ_ONLY = "READ_ONLY"
    STANDARD_WRITE = "STANDARD_WRITE"
    SCHEMA_MODIFY = "SCHEMA_MODIFY"
    DDL_ADMIN = "DDL_ADMIN"
    DATA_EXPORT = "DATA_EXPORT"
    IAM_ADMIN = "IAM_ADMIN"


class NoveltyTier(str, Enum):
    """Novelty classification of change intent."""

    ROUTINE_KNOWN = "ROUTINE_KNOWN"
    MODERATE_EXTENSION = "MODERATE_EXTENSION"
    NOVEL_UNVERIFIED = "NOVEL_UNVERIFIED"
    ANOMALOUS = "ANOMALOUS"


class RehearsalStatus(str, Enum):
    """Status of required ShadowLab rehearsal."""

    NOT_REQUIRED = "NOT_REQUIRED"
    REHEARSAL_PASSED = "REHEARSAL_PASSED"
    REHEARSAL_FAILED = "REHEARSAL_FAILED"
    REHEARSAL_NOT_RUN = "REHEARSAL_NOT_RUN"


class ReversibilityAssessment(BaseModel):
    """Detailed reversibility analysis outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    change_id: str
    reversibility_class: ReversibilityClass
    blast_radius_score: float  # [0.0, 1.0]
    has_down_migration: bool
    rollback_plan_summary: str
    reversibility_score: float  # [0.0, 1.0]
    rationale: str

    @field_validator("change_id", "rollback_plan_summary", "rationale")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class DeterministicPolicyInputs(BaseModel):
    """The 7 canonical deterministic policy inputs required for autonomy decisions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    change_id: str

    # 1. Blast Radius
    blast_radius_score: float = 0.1
    blast_radius_source: str = "impact_scout:ast_graph"
    blast_radius_reason: str = "Estimated from dependent symbol and endpoint count"

    # 2. Reversibility
    reversibility_class: ReversibilityClass = ReversibilityClass.IRREVERSIBLE_DESTRUCTIVE
    has_down_migration: bool = False
    rollback_summary: str = "No down migration specified"
    reversibility_source: str = "policy_guardian:ddl_classifier"

    # 3. Privilege
    privilege_level: PrivilegeLevel = PrivilegeLevel.SCHEMA_MODIFY
    privilege_source: str = "iam_authorizer:role_binding"

    # 4. Sensitivity
    data_classification: DataClassLevel = DataClassLevel.RESTRICTED
    sensitivity_source: str = "data_governance:classification_scan"

    # 5. Evidence
    evidence_state: EvidenceState = EvidenceState.SIMULATED
    evidence_mode: ExecutionEvidenceMode = ExecutionEvidenceMode.SIMULATION
    evidence_digests: Tuple[str, ...] = ()
    evidence_source: str = "evidence_auditor:ledger"

    # 6. Novelty
    novelty_tier: NoveltyTier = NoveltyTier.ROUTINE_KNOWN
    novelty_source: str = "memory_trust_layer:history"

    # 7. Rehearsal
    rehearsal_status: RehearsalStatus = RehearsalStatus.REHEARSAL_NOT_RUN
    rehearsal_digests: Tuple[str, ...] = ()
    rehearsal_source: str = "shadowlab:synthetic_twin"

    @field_validator("change_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("change_id must not be blank")
        return v

    @field_validator("blast_radius_score")
    @classmethod
    def _bounded_score(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("blast_radius_score must be between 0.0 and 1.0")
        return v


class ReversibilityClassifier:
    """Classifies change scripts and actions into deterministic reversibility tiers."""

    @classmethod
    def classify_sql(
        cls,
        change_id: str,
        sql_up: str,
        sql_down: Optional[str] = None,
        blast_radius_score: float = 0.1,
    ) -> ReversibilityAssessment:
        """Classify a SQL migration script."""
        up_lower = sql_up.lower()
        has_down = bool(sql_down and sql_down.strip())

        # 1. Destructive operations (DROP TABLE, DROP COLUMN, TRUNCATE)
        is_destructive = bool(
            re.search(r"\bdrop\s+(?:table|column|database)\b", up_lower)
            or re.search(r"\btruncate\s+table\b", up_lower)
        )

        if is_destructive:
            if not has_down:
                return ReversibilityAssessment(
                    change_id=change_id,
                    reversibility_class=ReversibilityClass.IRREVERSIBLE_DESTRUCTIVE,
                    blast_radius_score=blast_radius_score,
                    has_down_migration=False,
                    rollback_plan_summary="No down migration available for destructive operation",
                    reversibility_score=0.0,
                    rationale="Destructive SQL statement lacks automated down migration",
                )
            else:
                down_snippet = (sql_down[:60] + "...") if sql_down else "Down migration script"
                return ReversibilityAssessment(
                    change_id=change_id,
                    reversibility_class=ReversibilityClass.HUMAN_INTERVENTION_REQUIRED,
                    blast_radius_score=blast_radius_score,
                    has_down_migration=True,
                    rollback_plan_summary=f"Automated down migration available: {down_snippet}",
                    reversibility_score=0.35,
                    rationale="Destructive SQL with down migration requires human confirmation",
                )

        # 2. High Blast Radius check (> 0.8 requires human authority)
        if blast_radius_score > 0.8:
            return ReversibilityAssessment(
                change_id=change_id,
                reversibility_class=ReversibilityClass.HUMAN_INTERVENTION_REQUIRED,
                blast_radius_score=blast_radius_score,
                has_down_migration=has_down,
                rollback_plan_summary=sql_down or "Default rollback procedure",
                reversibility_score=0.45,
                rationale=f"High blast radius ({blast_radius_score:.2f} > 0.80) crosses threshold",
            )

        # 3. Expand-Contract / Multi-step Compensation
        if "view" in up_lower or "dual_write" in up_lower or not has_down:
            return ReversibilityAssessment(
                change_id=change_id,
                reversibility_class=ReversibilityClass.REVERSIBLE_WITH_COMPENSATION,
                blast_radius_score=blast_radius_score,
                has_down_migration=has_down,
                rollback_plan_summary="Compensation saga: teardown views/dual-write triggers",
                reversibility_score=0.85,
                rationale="Multi-phase change requires saga compensation steps to reverse",
            )

        # 4. Fully Reversible Automated (Additive column, index, views with down script)
        down_snip = (sql_down[:60] + "...") if sql_down else "Single-step rollback"
        return ReversibilityAssessment(
            change_id=change_id,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            blast_radius_score=blast_radius_score,
            has_down_migration=True,
            rollback_plan_summary=f"Automated single-step rollback: {down_snip}",
            reversibility_score=1.0,
            rationale="Additive schema operation with verified down migration",
        )
