from src.migration.artifact_generator import ArtifactGenerator, MigrationArtifactType
from src.migration.correction_engine import BoundedCorrectionEngine
from src.migration.manifest_generator import ManifestGenerator
from src.migration.plan_generator import MigrationPlanGenerator, MigrationStepType
from src.migration.worktree_guard import WorktreeGuard


def test_worktree_guard_allowed_path():
    root = "/allowed/path"
    guard = WorktreeGuard([root])
    assert guard.validate_write_path("/allowed/path/file.txt")


def test_worktree_guard_outside_path():
    root = "/allowed/path"
    guard = WorktreeGuard([root])
    assert not guard.validate_write_path("/unallowed/path/file.txt")


def test_worktree_guard_path_traversal():
    root = "/allowed/path"
    guard = WorktreeGuard([root])
    # Resolves to /allowed/outside.txt which is outside root unless root is exactly /allowed/path
    # Actually /allowed/path/../outside.txt -> /allowed/outside.txt
    assert not guard.validate_write_path("/allowed/path/../outside.txt")


def test_worktree_guard_governance_paths():
    root = "/allowed/path"
    guard = WorktreeGuard([root])
    assert not guard.validate_write_path("/allowed/path/AGENTS.md")
    assert not guard.validate_write_path("/allowed/path/src/file.py")


def test_worktree_guard_empty_allowlist():
    guard = WorktreeGuard([])
    assert not guard.validate_write_path("/any/path.txt")


def test_plan_generation_rename():
    gen = MigrationPlanGenerator()
    plan = gen.generate_plan(
        change_id="ch-1",
        source_schema="v1",
        target_schema="v2",
        column_renames=[("old_col", "new_col")],
    )

    # 2. Plan has add, dual-write, backfill, client update, verification, rollback, deferred removal
    assert plan.has_dual_write
    assert plan.has_backfill
    assert plan.has_rollback
    assert plan.has_deferred_removal
    assert plan.has_verification

    # 2. Destructive drop is not immediate (should be DEFERRED_REMOVAL)
    has_immediate_destructive = False
    has_deferred = False
    for step in plan.steps:
        if step.is_destructive:
            if step.step_type == MigrationStepType.DEFERRED_REMOVAL:
                has_deferred = True
            else:
                has_immediate_destructive = True

    assert has_deferred
    assert not has_immediate_destructive


def test_plan_generation_addition():
    gen = MigrationPlanGenerator()
    plan = gen.generate_plan(
        change_id="ch-2", source_schema="v1", target_schema="v2", column_additions=["new_col"]
    )
    assert plan.has_rollback
    assert not plan.has_dual_write


def test_artifact_generation():
    gen = MigrationPlanGenerator()
    plan = gen.generate_plan(
        change_id="ch-1",
        source_schema="v1",
        target_schema="v2",
        column_renames=[("old_col", "new_col")],
    )

    artifact_gen = ArtifactGenerator()
    artifacts = artifact_gen.generate_artifacts(plan)

    assert len(artifacts) == 3

    has_migration = False
    has_rollback = False
    has_brief = False

    for art in artifacts:
        assert len(art.content_hash) == 64  # valid sha256
        assert "TODO" not in art.content  # no unresolved placeholders
        assert "SECRET" not in art.content  # no secrets

        if art.artifact_type == MigrationArtifactType.MIGRATION_SCRIPT:
            assert "ALTER TABLE" in art.content
            has_migration = True
        elif art.artifact_type == MigrationArtifactType.ROLLBACK_SCRIPT:
            has_rollback = True
        elif art.artifact_type == MigrationArtifactType.OWNER_BRIEF:
            has_brief = True

    assert has_migration
    assert has_rollback
    assert has_brief


def test_correction_engine():
    gen = MigrationPlanGenerator()
    # Plan without rollback
    plan = gen.generate_plan(
        change_id="ch-3", source_schema="v1", target_schema="v2", column_removals=["old_col"]
    )

    engine = BoundedCorrectionEngine()
    result = engine.attempt_correction(plan, "missing rollback", attempt=1)

    assert result.correction_applied
    assert result.re_rehearsed
    assert result.corrected_plan is not None
    assert result.corrected_plan.has_rollback

    # Max attempts enforced
    result_max = engine.attempt_correction(plan, "missing rollback", attempt=4)
    assert not result_max.correction_applied
    assert result_max.corrected_plan is None

    # Failed correction (unknown reason)
    result_fail = engine.attempt_correction(plan, "unknown error", attempt=1)
    assert not result_fail.correction_applied
    assert result_fail.corrected_plan is None


def test_manifest_generation():
    gen = ManifestGenerator()
    manifest = gen.generate_manifest(
        change_id="ch-1",
        plan_id="p-1",
        file_contents={"file1.txt": "content1", "file2.txt": "content2"},
    )

    assert len(manifest.entries) == 2
    assert manifest.deployment_claim == "NONE"
    assert len(manifest.manifest_hash) == 64


def test_security_and_carryover():
    # Forbidden carry-over check
    gen = MigrationPlanGenerator()
    plan = gen.generate_plan(
        change_id="ch-4", source_schema="v1", target_schema="v2", column_additions=["new_col"]
    )

    artifact_gen = ArtifactGenerator()
    artifacts = artifact_gen.generate_artifacts(plan)

    for art in artifacts:
        assert "ContextSeal" not in art.content
        assert "DataHub" not in art.content, (
            "DataHub is forbidden carry-over, logic shouldn't inject it."
        )
        assert "deployed" not in art.content.lower()
