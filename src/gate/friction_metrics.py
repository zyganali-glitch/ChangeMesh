"""ChangeMesh friction reduction metrics calculator and artifact generator.

P-14.06: Computes deterministic metrics from actual recorded decision traces,
measuring total workflow decisions, autonomous steps, notify-only steps,
rehearsal-gated steps, human authority decisions, and repeated prompts avoided
without making unsupported customer productivity claims.
"""

from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, ConfigDict

from domain.contracts.autonomy import AutonomyClass
from src.gate.policy_guardian_gate import PolicyGateEvaluationResult

CANONICAL_SCHEMA_VERSION = "1.0.0"


class FrictionMetricsArtifact(BaseModel):
    """Immutable demonstrable metrics artifact calculated from real decision traces."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    total_workflow_decisions: int
    autonomous_decisions: int
    notify_only_decisions: int
    rehearse_then_execute_decisions: int
    human_authority_decisions: int
    blocked_decisions: int
    repeated_prompts_avoided: int
    autonomy_ratio: float  # [0.0, 1.0]

    def to_markdown_summary(self) -> str:
        """Render a clean, grounded markdown metrics summary table."""
        pct = self.autonomy_ratio * 100.0
        return (
            "### ChangeMesh Workflow Friction Reduction Metrics\n\n"
            "| Metric | Demonstrable Count |\n"
            "|:---|:---|\n"
            f"| Fully Autonomous (`AUTO_EXECUTE`) | {self.autonomous_decisions} |\n"
            f"| Autonomous + Notify (`AUTO_EXECUTE_AND_NOTIFY`) | {self.notify_only_decisions} |\n"
            f"| Rehearse (`REHEARSE_THEN_EXECUTE`) | {self.rehearse_then_execute_decisions} |\n"
            f"| Human Authority (`HUMAN_AUTHORITY_REQUIRED`) | {self.human_authority_decisions} |\n"
            f"| Blocked / Irreversible (`BLOCKED`) | {self.blocked_decisions} |\n"
            f"| Repeated Prompts Avoided | {self.repeated_prompts_avoided} |\n"
            f"| **Overall Fleet Autonomy Ratio** | **{pct:.1f}%** |\n"
        )


class FrictionMetricsCalculator:
    """Calculates friction metrics from real recorded policy gate evaluation traces."""

    @classmethod
    def calculate(
        cls,
        evaluations: Sequence[PolicyGateEvaluationResult],
        repeated_prompts_avoided: int = 0,
    ) -> FrictionMetricsArtifact:
        total = len(evaluations)
        auto_count = 0
        notify_count = 0
        rehearse_count = 0
        human_count = 0
        blocked_count = 0

        for ev in evaluations:
            if ev.autonomy_class == AutonomyClass.AUTO_EXECUTE:
                auto_count += 1
            elif ev.autonomy_class == AutonomyClass.AUTO_EXECUTE_AND_NOTIFY:
                notify_count += 1
            elif ev.autonomy_class == AutonomyClass.REHEARSE_THEN_EXECUTE:
                rehearse_count += 1
            elif ev.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED:
                human_count += 1
            elif ev.autonomy_class == AutonomyClass.BLOCKED:
                blocked_count += 1

        autonomous_total = auto_count + notify_count
        ratio = (autonomous_total / total) if total > 0 else 0.0

        return FrictionMetricsArtifact(
            total_workflow_decisions=total,
            autonomous_decisions=auto_count,
            notify_only_decisions=notify_count,
            rehearse_then_execute_decisions=rehearse_count,
            human_authority_decisions=human_count,
            blocked_decisions=blocked_count,
            repeated_prompts_avoided=repeated_prompts_avoided,
            autonomy_ratio=round(ratio, 4),
        )
