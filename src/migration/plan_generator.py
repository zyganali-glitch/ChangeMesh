import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict


class MigrationStepType(str, Enum):
    ADD_COLUMN = "ADD_COLUMN"
    CREATE_TABLE = "CREATE_TABLE"
    DUAL_WRITE_ENABLE = "DUAL_WRITE_ENABLE"
    BACKFILL = "BACKFILL"
    CLIENT_UPDATE = "CLIENT_UPDATE"
    VERIFICATION = "VERIFICATION"
    ROLLBACK = "ROLLBACK"
    DEFERRED_REMOVAL = "DEFERRED_REMOVAL"


class MigrationStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str
    step_type: MigrationStepType
    description: str
    sql: str | None = None
    is_destructive: bool = False
    rollback_sql: str | None = None
    depends_on: tuple[str, ...] = ()


class ExpandMigrateContractPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    plan_id: str
    source_schema: str
    target_schema: str
    steps: tuple[MigrationStep, ...]
    has_dual_write: bool
    has_backfill: bool
    has_rollback: bool
    has_deferred_removal: bool
    has_verification: bool
    evidence_mode: str = "FIXTURE"


class MigrationPlanGenerator:
    """Generate expand-migrate-contract plans from typed findings.

    Plans MUST include: add, dual-write, backfill, client update,
    verification, rollback, deferred removal.
    Does NOT silently convert destructive rename/drop into immediate
    destructive action.
    """

    def generate_plan(
        self,
        change_id: str,
        source_schema: str,
        target_schema: str,
        column_renames: list[tuple[str, str]] | None = None,
        column_additions: list[str] | None = None,
        column_removals: list[str] | None = None,
        table_name: str = "target_table",
    ) -> ExpandMigrateContractPlan:
        steps = []

        has_dual_write = False
        has_backfill = False
        has_rollback = False
        has_deferred_removal = False
        has_verification = False

        if column_renames:
            for old_col, new_col in column_renames:
                # Add new column
                add_step = MigrationStep(
                    step_id=f"add_{new_col}",
                    step_type=MigrationStepType.ADD_COLUMN,
                    description=f"Add new column {new_col}",
                    sql=f"ALTER TABLE {table_name} ADD COLUMN {new_col} TYPE_HERE;",
                    rollback_sql=f"ALTER TABLE {table_name} DROP COLUMN {new_col};",
                )
                steps.append(add_step)

                # Dual write
                dual_write_step = MigrationStep(
                    step_id=f"dual_write_{new_col}",
                    step_type=MigrationStepType.DUAL_WRITE_ENABLE,
                    description=f"Enable dual write for {old_col} and {new_col}",
                    depends_on=(add_step.step_id,),
                )
                steps.append(dual_write_step)
                has_dual_write = True

                # Backfill
                backfill_step = MigrationStep(
                    step_id=f"backfill_{new_col}",
                    step_type=MigrationStepType.BACKFILL,
                    description=f"Backfill {new_col} from {old_col}",
                    sql=f"UPDATE {table_name} SET {new_col} = {old_col} WHERE {new_col} IS NULL;",
                    depends_on=(dual_write_step.step_id,),
                )
                steps.append(backfill_step)
                has_backfill = True

                # Client Update
                client_update_step = MigrationStep(
                    step_id=f"client_update_{new_col}",
                    step_type=MigrationStepType.CLIENT_UPDATE,
                    description=f"Update clients to read from {new_col}",
                    depends_on=(backfill_step.step_id,),
                )
                steps.append(client_update_step)

                # Verification
                verification_step = MigrationStep(
                    step_id=f"verify_{new_col}",
                    step_type=MigrationStepType.VERIFICATION,
                    description=f"Verify backfill for {new_col}",
                    depends_on=(client_update_step.step_id,),
                )
                steps.append(verification_step)
                has_verification = True

                # Rollback
                rollback_step = MigrationStep(
                    step_id=f"rollback_{new_col}",
                    step_type=MigrationStepType.ROLLBACK,
                    description=f"Rollback plan for {new_col}",
                    depends_on=(),
                )
                steps.append(rollback_step)
                has_rollback = True

                # Deferred Removal
                removal_step = MigrationStep(
                    step_id=f"deferred_remove_{old_col}",
                    step_type=MigrationStepType.DEFERRED_REMOVAL,
                    description=f"Deferred removal of {old_col}",
                    sql=f"ALTER TABLE {table_name} DROP COLUMN {old_col};",
                    is_destructive=True,
                    depends_on=(verification_step.step_id,),
                )
                steps.append(removal_step)
                has_deferred_removal = True

        if column_additions:
            for col in column_additions:
                add_step = MigrationStep(
                    step_id=f"add_{col}",
                    step_type=MigrationStepType.ADD_COLUMN,
                    description=f"Add new column {col}",
                    sql=f"ALTER TABLE {table_name} ADD COLUMN {col} TYPE_HERE;",
                    rollback_sql=f"ALTER TABLE {table_name} DROP COLUMN {col};",
                )
                steps.append(add_step)

                client_update_step = MigrationStep(
                    step_id=f"client_update_{col}",
                    step_type=MigrationStepType.CLIENT_UPDATE,
                    description=f"Update clients to write to {col}",
                    depends_on=(add_step.step_id,),
                )
                steps.append(client_update_step)

                rollback_step = MigrationStep(
                    step_id=f"rollback_{col}",
                    step_type=MigrationStepType.ROLLBACK,
                    description=f"Rollback plan for {col}",
                    depends_on=(),
                )
                steps.append(rollback_step)
                has_rollback = True

        if column_removals:
            for col in column_removals:
                client_update_step = MigrationStep(
                    step_id=f"client_update_remove_{col}",
                    step_type=MigrationStepType.CLIENT_UPDATE,
                    description=f"Update clients to stop reading/writing {col}",
                )
                steps.append(client_update_step)

                removal_step = MigrationStep(
                    step_id=f"deferred_remove_{col}",
                    step_type=MigrationStepType.DEFERRED_REMOVAL,
                    description=f"Deferred removal of {col}",
                    sql=f"ALTER TABLE {table_name} DROP COLUMN {col};",
                    is_destructive=True,
                    depends_on=(client_update_step.step_id,),
                )
                steps.append(removal_step)
                has_deferred_removal = True

        return ExpandMigrateContractPlan(
            change_id=change_id,
            plan_id=str(uuid.uuid4()),
            source_schema=source_schema,
            target_schema=target_schema,
            steps=tuple(steps),
            has_dual_write=has_dual_write,
            has_backfill=has_backfill,
            has_rollback=has_rollback,
            has_deferred_removal=has_deferred_removal,
            has_verification=has_verification,
        )
