"""ChangeMesh deterministic reversibility classifier.

P-14.01: Evaluates schema change operations and blast radius to produce
an authoritative, machine-evaluable reversibility classification.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

CANONICAL_SCHEMA_VERSION = "1.0.0"


class ReversibilityClass(str, Enum):
    """Canonical 4-class reversibility taxonomy."""

    FULLY_REVERSIBLE_AUTOMATED = "FULLY_REVERSIBLE_AUTOMATED"
    REVERSIBLE_WITH_COMPENSATION = "REVERSIBLE_WITH_COMPENSATION"
    HUMAN_INTERVENTION_REQUIRED = "HUMAN_INTERVENTION_REQUIRED"
    IRREVERSIBLE_DESTRUCTIVE = "IRREVERSIBLE_DESTRUCTIVE"


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
                    rollback_plan_summary="No down migration or automated undo script available for destructive operation",
                    reversibility_score=0.0,
                    rationale="Destructive SQL statement (DROP/TRUNCATE) lacks automated down migration",
                )
            else:
                return ReversibilityAssessment(
                    change_id=change_id,
                    reversibility_class=ReversibilityClass.HUMAN_INTERVENTION_REQUIRED,
                    blast_radius_score=blast_radius_score,
                    has_down_migration=True,
                    rollback_plan_summary=f"Automated down migration available: {sql_down[:60]}...",
                    reversibility_score=0.35,
                    rationale="Destructive SQL statement with down migration requires human confirmation slot",
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
                rationale=f"High blast radius score ({blast_radius_score:.2f} > 0.80) crosses organizational authority threshold",
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
        return ReversibilityAssessment(
            change_id=change_id,
            reversibility_class=ReversibilityClass.FULLY_REVERSIBLE_AUTOMATED,
            blast_radius_score=blast_radius_score,
            has_down_migration=True,
            rollback_plan_summary=f"Automated single-step rollback: {sql_down[:60]}",
            reversibility_score=1.0,
            rationale="Additive schema operation with verified instantaneous down migration",
        )
