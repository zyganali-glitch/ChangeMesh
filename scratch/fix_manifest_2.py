def fix_manifest_2():
    with open(r"c:\Users\MEHMET\.gemini\antigravity\scratch\ChangeMesh\docs\DONOR_REUSE_MANIFEST.md", "r", encoding="utf-8") as f:
        content = f.read()
    
    # 1. CCT-SEM-001
    content = content.replace(
        "source_paths:\n  - docs/ARCHITECTURE.md\n  - JUDGE_START_HERE.md\n  - docs/JUDGING_MAP.md",
        "source_paths:\n  - src/audit/semantic_auditor.js\n  - tests/test_semantic_audit.js"
    )
    
    # 2. ZK-PRIV-001
    content = content.replace(
        "source_paths:\n  - ai-buildweek/reports/privacy-boundary.md\n  - README.md",
        "source_paths:\n  - src/security/privacy_boundary.js\n  - tests/test_privacy_boundary.js"
    )
    
    # 3. UAOS-MEM-001
    content = content.replace(
        "source_paths:\n  - skills/agent-os-memory/SKILL.md\n  - governance references",
        "source_paths:\n  - skills/agent-os-memory/SKILL.md\n  - scripts/sync_memory.js\n  - tests/test_memory_sync.js"
    )
    
    # 4. UAOS-GOV-001
    content = content.replace(
        "  - live-doc closure\n  - completed-plan archive behavior\ncompetition_introduction_commit: PENDING",
        "  - live-doc closure\n  - completed-plan archive behavior\n  - forged plan updates rejected\n  - unauthorized modification blocked\ncompetition_introduction_commit: PENDING"
    )
    
    # 5. ZK-CLAIM-001
    content = content.replace(
        "  - cross-document parity\ncompetition_introduction_commit: PENDING",
        "  - cross-document parity\n  - ambiguous claim fails\ncompetition_introduction_commit: PENDING"
    )
    
    # 6. CCT-JUDGE-001
    content = content.replace(
        "  - no invalid evidence\ncompetition_introduction_commit: PENDING",
        "  - no invalid evidence\n  - malformed screenshot fails\ncompetition_introduction_commit: PENDING"
    )
    
    with open(r"c:\Users\MEHMET\.gemini\antigravity\scratch\ChangeMesh\docs\DONOR_REUSE_MANIFEST.md", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix_manifest_2()
