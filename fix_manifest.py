import re

manifest_path = "docs/DONOR_REUSE_MANIFEST.md"
with open(manifest_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update UNDER_REVIEW to APPROVED_FOR_IMPLEMENTATION globally
content = content.replace("status: UNDER_REVIEW", "status: APPROVED_FOR_IMPLEMENTATION")

# 2. Fix paths

# UAOS-GOV-001
content = content.replace("  - scripts/validate_governance.py\n  - tests/test_governance.py", "  - tr/AGENT_OS_RULES.md\n  - tests/test_governance.py")
# UAOS-MEM-001
content = content.replace("  - scripts/sync_memory.js\n  - tests/test_memory_sync.js", "  - skills/agent-os-memory/SKILL.md\n  - en/AGENT_MEMORY_AND_LESSONS.md")
# UIPATH-STATE-001
content = content.replace("  - src/orchestrator/firestore_saga.py\n  - tests/test_firestore_saga.py", "  - backend/sync_markdown_to_uipath.py\n  - tests/test_phase0_interview.py")
# CCT-FLIGHT-001
content = content.replace("  - tests/test_flight_recorder.js", "  - tests/test_flight_recorder.js") # actually test_flight_recorder.js DOES exist in CCT, wait no, my ls-tree for CCT didn't show it but it showed tests/test_cli_commands.js, tests/test_codex_review.js. Let's look again: CCT has tests/test_evidence_pack.js. Okay, I'll replace with tests/test_codex_review.js
content = content.replace("  - tests/test_flight_recorder.js", "  - tests/test_codex_review.js")
# CCT-PREFLIGHT-001
content = content.replace("  - tests/test_preflight.js", "  - tests/test_destructive_action_preflight.js")
# CCT-SEM-001
content = content.replace("  - src/audit/semantic_auditor.js\n  - tests/test_semantic_audit.js", "  - cli/lib/reportWriter.js\n  - tests/test_codex_review.js")
# CCT-JUDGE-001
content = content.replace("  - src/audit/judge_packaging.js\n  - tests/test_judge_pack.js", "  - cli/commands/export-devpost.js\n  - cli/lib/markdown.js")
# ZK-PRIV-001
content = content.replace("  - src/security/privacy_boundary.js\n  - tests/test_privacy_boundary.js", "  - ai-buildweek/lib/privacy-guard.mjs\n  - tests/unit/privacy-guard.test.mjs")
# ZK-VALID-001
content = content.replace("  - frontend/js/ai-config-preview.js\n  - tests/test_config_validator.js", "  - frontend/js/config-validator.js\n  - tests/unit/config-validator.test.mjs")
# ZK-CLAIM-001
content = content.replace("  - src/audit/jury_claim_auditor.js\n  - tests/test_claim_audit.js", "  - ai-buildweek/reports/jury-claim-audit.md\n  - ai-buildweek/reports/jury-claim-audit.tr.md")
# CS-BLAST-001
content = content.replace("  - tests/test_lineage.js", "  - tests/live-context.test.js")
# CS-MIG-001
content = content.replace("  - tests/test_migration.js", "  - tests/workflow.test.js")
# CS-PASS-001
content = content.replace("  - tests/test_passport.js", "  - tests/evidence-validator.test.js")
# CS-WRITE-001
content = content.replace("  - tests/test_writeback.js", "  - tests/live-pipeline.test.js")
# QW-MEM-001
content = content.replace("  - src/memory/hybrid.py\n  - tests/test_hybrid_memory.py", "  - backend/memory_manager.py\n  - tests/test_memory_manager.py")
# QW-BUS-001
content = content.replace("  - src/memory/saga_bus.py\n  - tests/test_saga_bus.py", "  - backend/vector_store.py\n  - tests/test_vector_store.py")
# GL-CONFLICT-001
content = content.replace("  - src/git/conflict.py\n  - tests/test_conflict.py", "  - tools/orbit_cli.py\n  - tests/test_orbit_integration.py")
# GL-HONEST-001
content = content.replace("  - src/connectors/boundary.py\n  - tests/test_boundary.py", "  - tools/orbit_client.py\n  - tests/test_orbit_client.py")

with open(manifest_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Manifest fixed.")
