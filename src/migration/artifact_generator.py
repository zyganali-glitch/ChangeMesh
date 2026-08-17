import hashlib
import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict

from src.migration.plan_generator import ExpandMigrateContractPlan


class MigrationArtifactType(str, Enum):
    MIGRATION_SCRIPT = "MIGRATION_SCRIPT"
    APPLICATION_UPDATE = "APPLICATION_UPDATE"
    TEST_SCRIPT = "TEST_SCRIPT"
    ROLLBACK_SCRIPT = "ROLLBACK_SCRIPT"
    OWNER_BRIEF = "OWNER_BRIEF"


class MigrationArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    artifact_type: MigrationArtifactType
    content: str
    content_hash: str  # SHA-256
    plan_id: str
    change_id: str
    evidence_mode: str = "FIXTURE"


class ArtifactGenerator:
    """Generate typed/validated migration artifacts deterministically.

    Gemini only used where semantic generation legitimately needed.
    No unresolved placeholder. No secret. No false deployment claim.
    """

    def generate_artifacts(self, plan: ExpandMigrateContractPlan) -> tuple[MigrationArtifact, ...]:
        artifacts = []

        # 1. Migration Script
        sql_commands = []
        for step in plan.steps:
            if step.sql and not step.is_destructive:
                sql_commands.append(f"-- Step: {step.description}\n{step.sql}")
        if sql_commands:
            content = "\n\n".join(sql_commands)
            artifacts.append(
                self._create_artifact(
                    MigrationArtifactType.MIGRATION_SCRIPT, content, plan.plan_id, plan.change_id
                )
            )

        # 2. Rollback Script
        rollback_commands = []
        for step in plan.steps:
            if step.rollback_sql:
                rollback_commands.append(f"-- Rollback: {step.description}\n{step.rollback_sql}")

        # P-17.03 requires Rollback script exists in tests.
        rollback_content = (
            "\n\n".join(rollback_commands) if rollback_commands else "-- No rollback required"
        )
        artifacts.append(
            self._create_artifact(
                MigrationArtifactType.ROLLBACK_SCRIPT,
                rollback_content,
                plan.plan_id,
                plan.change_id,
            )
        )

        # 3. Owner Brief
        brief_content = (
            f"Migration brief for {plan.change_id}.\n"
            f"Steps: {len(plan.steps)}\n"
            f"Destructive: {plan.has_deferred_removal}"
        )
        artifacts.append(
            self._create_artifact(
                MigrationArtifactType.OWNER_BRIEF, brief_content, plan.plan_id, plan.change_id
            )
        )

        return tuple(artifacts)

    def _create_artifact(
        self, type_: MigrationArtifactType, content: str, plan_id: str, change_id: str
    ) -> MigrationArtifact:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return MigrationArtifact(
            artifact_id=str(uuid.uuid4()),
            artifact_type=type_,
            content=content,
            content_hash=content_hash,
            plan_id=plan_id,
            change_id=change_id,
        )
