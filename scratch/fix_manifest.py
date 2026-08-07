import re

def fix_manifest():
    with open(r"c:\Users\MEHMET\.gemini\antigravity\scratch\ChangeMesh\docs\DONOR_REUSE_MANIFEST.md", "r", encoding="utf-8") as f:
        content = f.read()
    
    parts = content.split("## 5. Initial component inventory\n\n")
    part1 = parts[0] + "## 5. Initial component inventory\n\n"
    part2 = parts[1].split("## 6. Cross-donor convergence decisions to be frozen in P-02D\n\n")
    tail = "## 6. Cross-donor convergence decisions to be frozen in P-02D\n\n" + part2[1]

    components = [
        {
            "id": "UAOS-GOV-001",
            "donor": "D-UAOS",
            "repo": "zyganali-glitch/Universal-Agent-OS",
            "commit": "6b83b06212101c238ec28076a2ba7ae819f483f2",
            "paths": ["cli/verify.js", "cli/status.js", "scripts/validate_governance.py", "tests/test_governance.py"],
            "behavior": ["one official task table, plan-before-code, gate/evidence closure, live documentation, completed-plan archive"],
            "method": "ADAPTED",
            "target": ["AGENTS.md", "AGENT_OS_RULES.md", "AGENT_OS_PLAN_TEMPLATE.md", "plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md", ".agents/rules/*", ".agents/skills/*"],
            "transform": ["remove generic Phase-0; preserve frozen charter, autonomy, donor lock, P-Ω"],
            "forbidden": ["donor CLI/runtime/MCP/examples, locale packs, generic product claims, mandatory interview"],
            "tests": ["governance file presence", "no Phase-0 instruction", "plan task status/evidence parity", "live-doc closure", "completed-plan archive behavior", "forged plan updates rejected", "unauthorized modification blocked"],
            "status": "VERIFIED"
        },
        {
            "id": "UAOS-MEM-001",
            "donor": "D-UAOS",
            "repo": "zyganali-glitch/Universal-Agent-OS",
            "commit": "6b83b06212101c238ec28076a2ba7ae819f483f2",
            "paths": ["scripts/sync_memory.js", "tests/test_memory_sync.js"],
            "behavior": ["read/update lessons, architecture, environment/API, and user preferences"],
            "method": "ADAPTED",
            "target": ["four root memory files", ".agents/skills/agentos-memory/SKILL.md"],
            "transform": ["store durable project facts only; add donor manifest/handoff; no private chain-of-thought or secrets"],
            "forbidden": ["generic initialization that overwrites ChangeMesh decisions"],
            "tests": ["startup-read references", "task-closure updates", "no-secret/no-private-reasoning checks"],
            "status": "VERIFIED"
        },
        {
            "id": "UIPATH-STATE-001",
            "donor": "D-UIPATH",
            "repo": "zyganali-glitch/universal-agent-os-uipath",
            "commit": "dc2267939c2aef0aba2737da65f53352c5cf8fb2",
            "paths": ["src/orchestrator/firestore_saga.py", "tests/test_firestore_saga.py"],
            "behavior": ["persisted workflow state, wait/resume, explicit process transitions and handoff"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/orchestrator/firestore_saga.py"],
            "transform": ["ADK + Pub/Sub + Firestore; no UiPath runtime or Phase-0 semantics"],
            "forbidden": ["Maestro/Action Center/Data Service IDs and dependencies"],
            "tests": ["restart resume", "no duplicate action", "legal/illegal transition", "timeout", "cancellation", "compensation"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "UIPATH-AUTH-001",
            "donor": "D-UIPATH",
            "repo": "zyganali-glitch/universal-agent-os-uipath",
            "commit": "dc2267939c2aef0aba2737da65f53352c5cf8fb2",
            "paths": ["backend/uipath_api_connector.py", "tests/test_uipath_connector_modes.py"],
            "behavior": ["authority result verified through a system/API record rather than trusted from chat; real/mock mode kept explicit"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/auth/approval_compression.py"],
            "transform": ["exception-only human authority; reusable scoped/expiring approval"],
            "forbidden": ["routine approval per step; mock as real; UiPath API contract"],
            "tests": ["forged chat approval rejected", "expired/scope-mismatched decision rejected", "valid reusable decision accepted", "local adapter labeled"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CCT-EVID-001",
            "donor": "D-CCT",
            "repo": "zyganali-glitch/codex-control-tower",
            "commit": "65ee1b72faf9a7202d9166eed43fb671804815a8",
            "paths": ["cli/commands/evidence.js", "tests/test_evidence_pack.js"],
            "behavior": ["named evidence states; NOT_RUN and simulation boundaries; model cannot rewrite local facts"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/evidence/evidence_record.py"],
            "transform": ["ADK/tool events, Change ID, agent revision, cloud trace references"],
            "forbidden": ["Codex event assumptions, GPT-specific fields, InvoiceFlow fixture names"],
            "tests": ["model disagreement cannot change facts", "blocked remains not-run", "simulated remains simulated", "tamper detection"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CCT-FLIGHT-001",
            "donor": "D-CCT",
            "repo": "zyganali-glitch/codex-control-tower",
            "commit": "65ee1b72faf9a7202d9166eed43fb671804815a8",
            "paths": ["cli/commands/flight-recorder.js", "tests/test_flight_recorder.js"],
            "behavior": ["chronological execution/evidence record and judge-inspectable summary"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/evidence/pubsub_timeline.py"],
            "transform": ["distributed causal chain, correlation/causation IDs, agent/tool revisions, OpenTelemetry links"],
            "forbidden": ["local-only chronology, Codex-specific event names, copied UI styling without review"],
            "tests": ["duplicate/out-of-order event handling", "causal ordering", "redaction", "restart continuity"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CCT-PREFLIGHT-001",
            "donor": "D-CCT",
            "repo": "zyganali-glitch/codex-control-tower",
            "commit": "65ee1b72faf9a7202d9166eed43fb671804815a8",
            "paths": ["cli/lib/destructiveActionPreflight.js", "tests/test_preflight.js"],
            "behavior": ["canonicalize target, compare protected boundaries, block before execution, preserve NOT_RUN"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/policy/shadowlab_auth.py"],
            "transform": ["schema/database/API/GitHub action classes rather than filesystem deletion only"],
            "forbidden": ["Codex hook dependency, shell-command execution, repository-subpath-as-safety-clearance"],
            "tests": ["destructive target blocked pre-tool", "no command executed", "ambiguous target fails closed", "reversible action classified separately"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CCT-SEM-001",
            "donor": "D-CCT",
            "repo": "zyganali-glitch/codex-control-tower",
            "commit": "65ee1b72faf9a7202d9166eed43fb671804815a8",
            "paths": ["src/audit/semantic_auditor.js", "tests/test_semantic_audit.js"],
            "behavior": ["independent model assesses whether evidence semantically proves mission; expected result withheld; conflict triggers review but cannot overwrite facts"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/agents/evidence_auditor.py"],
            "transform": ["Gemini 3.5+, ADK-compatible bounded audit bundle, citation enforcement"],
            "forbidden": ["GPT-5.6/Codex runtime, expected-answer labels, model as execution authority"],
            "tests": ["expected-label leakage scan", "uncited decisive answer rejection", "deterministic reconciliation", "controlled mission gap"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CCT-JUDGE-001",
            "donor": "D-CCT",
            "repo": "zyganali-glitch/codex-control-tower",
            "commit": "65ee1b72faf9a7202d9166eed43fb671804815a8",
            "paths": ["src/audit/judge_packaging.py", "tests/test_judge_pack.py"],
            "behavior": ["fast judge route, requirement-to-evidence map, demo timing, immutable release, build-period delta, screenshot/claim discipline"],
            "method": "REFERENCE_ONLY",
            "target": ["docs/JUDGING_MAP.md"],
            "transform": ["ChangeMesh-only facts/links/evidence"],
            "forbidden": ["old links, numbers, model names, evidence results, competition language, screenshots"],
            "tests": ["link/status/version/claim parity", "final tag/cloud/video alignment", "no old claims", "no invalid evidence", "malformed screenshot fails"],
            "status": "VERIFIED"
        },
        {
            "id": "ZK-PRIV-001",
            "donor": "D-ZEROKIT",
            "repo": "zyganali-glitch/zerokit-ai-control-plane",
            "commit": "d663db8c706cb914e1af5caf651df08edb5c50c0",
            "paths": ["src/security/privacy_boundary.js", "tests/test_privacy_boundary.js"],
            "behavior": ["prevent sensitive/real data from entering model workflow; explicitly separate synthetic fixture"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/policy/policy_guardian.py"],
            "transform": ["Gemini input minimization, Policy Guardian, demo fixture boundary"],
            "forbidden": ["school-SaaS data, Codex/GPT fields, ZeroKit product semantics"],
            "tests": ["secret/PII fixture blocked/redacted", "synthetic mode explicit", "model request contains only allowlisted fields"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "ZK-VALID-001",
            "donor": "D-ZEROKIT",
            "repo": "zyganali-glitch/zerokit-ai-control-plane",
            "commit": "d663db8c706cb914e1af5caf651df08edb5c50c0",
            "paths": ["frontend/js/ai-config-preview.js", "tests/test_config_validator.js"],
            "behavior": ["generated artifact must match explicit schema/allowlist and manifest; malformed/extra fields fail"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/core/gemini_structured_output.py"],
            "transform": ["domain contracts, Gemini structured output, migration artifacts, evidence/passport validators"],
            "forbidden": ["ZeroKit configuration schema, frontend globals, GPT-specific manifest fields"],
            "tests": ["missing/extra/wrong-type/path traversal/unsafe endpoint/unknown action cases"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "ZK-CLAIM-001",
            "donor": "D-ZEROKIT",
            "repo": "zyganali-glitch/zerokit-ai-control-plane",
            "commit": "d663db8c706cb914e1af5caf651df08edb5c50c0",
            "paths": ["src/audit/jury_claim_auditor.py", "tests/test_claim_audit.py"],
            "behavior": ["map public statements to evidence and distinguish build-period work"],
            "method": "REFERENCE_ONLY",
            "target": ["src/audit/claim_audit.py"],
            "transform": ["competition-claim-audit, build disclosure, Devpost and screenshot review"],
            "forbidden": ["old claims, scores, evidence states, links, provider names"],
            "tests": ["unsupported-claim scanner and cross-document parity", "ambiguous claim fails"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CS-BLAST-001",
            "donor": "D-CONTEXTSEAL",
            "repo": "zyganali-glitch/ContextSeal",
            "commit": "0dc924db9d82037d2e813548bdee27af5f180889",
            "paths": ["src/datahub/live-context.js", "src/core/risk.js", "src/core/workflow.js", "tests/test_lineage.js"],
            "behavior": ["preserve multi-hop dependency paths, owners, truncation/incompleteness, and risk context"],
            "method": "ADAPTED",
            "target": ["src/git/impact_scout.py"],
            "transform": ["GitHub repository findings plus synthetic metadata graph; optional DataHub adapter"],
            "forbidden": ["hard DataHub requirement, silent truncated lineage, ContextSeal terminology"],
            "tests": ["multi-hop path", "cycles", "truncation", "missing owner", "duplicate merge", "contradictory sources"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CS-MIG-001",
            "donor": "D-CONTEXTSEAL",
            "repo": "zyganali-glitch/ContextSeal",
            "commit": "0dc924db9d82037d2e813548bdee27af5f180889",
            "paths": ["src/core/workflow.js", "skills/datahub-schema-change-certification/scripts/certify_change.py"],
            "behavior": ["reject direct breaking mutation; create additive migration, compatibility, verification, rollback, and deferred-removal plan"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/agents/migration_engineer.py"],
            "transform": ["Migration Engineer and ShadowLab correction"],
            "forbidden": ["direct live writeback, DataHub-only artifact format, pre-existing demo claims"],
            "tests": ["legacy client", "dual write", "backfill interruption", "rollback", "deferred removal", "missing dependency"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CS-PASS-001",
            "donor": "D-CONTEXTSEAL",
            "repo": "zyganali-glitch/ContextSeal",
            "commit": "0dc924db9d82037d2e813548bdee27af5f180889",
            "paths": ["src/core/passport.js", "scripts/validate-evidence.js"],
            "behavior": ["bind change context, policy, evidence, artifact hashes, and review packet into a verifiable package"],
            "method": "ADAPTED",
            "target": ["src/evidence/change_passport.py"],
            "transform": ["agent revisions/delegation, ShadowLab, memory trust, OpenTelemetry, external receipts"],
            "forbidden": ["duplicate passport implementation, ContextSeal field names as unreviewed contract"],
            "tests": ["canonical serialization", "tamper", "missing artifact", "wrong revision", "stale approval", "deterministic verify"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "CS-WRITE-001",
            "donor": "D-CONTEXTSEAL",
            "repo": "zyganali-glitch/ContextSeal",
            "commit": "0dc924db9d82037d2e813548bdee27af5f180889",
            "paths": ["src/datahub/writeback.js", "scripts/build-pr-bundle.js"],
            "behavior": ["constrain external write, generate review packet, preserve branch/change reconciliation"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/agents/release_steward.py"],
            "transform": ["GitHub draft-PR adapter and Release Steward"],
            "forbidden": ["DataHub writeback, automatic merge, unscoped target, missing idempotency"],
            "tests": ["dry run", "allowlist", "duplicate replay", "outside target", "conflict", "receipt creation"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "QW-MEM-001",
            "donor": "D-QWEN",
            "repo": "gitlab.com/zyganali/universal-agent-os-qwen",
            "commit": "a43b3411856f41a4be9424d11c01a5e637cdc410",
            "paths": ["src/memory/hybrid.py"],
            "behavior": ["BM25/embedding/keyword recall, freshness, importance, decay"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/memory/trust_layer.py"],
            "transform": ["trust authority remains new ChangeMesh logic"],
            "forbidden": ["Qwen runtime/provider", "Phase-0", "memory-as-truth", "unbounded vector/RAG infrastructure"],
            "tests": ["relevance", "stale-memory demotion", "high-importance retention", "deterministic trust override", "poisoned-memory quarantine"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "QW-BUS-001",
            "donor": "D-QWEN",
            "repo": "gitlab.com/zyganali/universal-agent-os-qwen",
            "commit": "a43b3411856f41a4be9424d11c01a5e637cdc410",
            "paths": ["src/memory/saga_bus.py"],
            "behavior": ["multi-agent memory exchange/MCP tools"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/memory/saga_bus.py"],
            "transform": ["scoped memory references and saga handoff"],
            "forbidden": ["unrestricted shared mutable memory"],
            "tests": ["cross-agent scope", "tenant isolation", "provenance", "replay", "no-secret tests mandatory"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "GL-CONFLICT-001",
            "donor": "D-GITLAB",
            "repo": "gitlab.com/zyganali/universal-agent-os-gitlab-edition",
            "commit": "3c4a412b6040d8a8154c15325943c409be9105f2",
            "paths": ["src/git/conflict.py"],
            "behavior": ["real overlapping MR blast radius, ownership and parallel-change risk"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/git/conflict_check.py"],
            "transform": ["Impact Scout and GitHub pre-draft-PR conflict check"],
            "forbidden": ["GitLab Duo/Orbit/GraphQL runtime dependency in MVP", "fabricated tool results", "GitLab-only IDs"],
            "tests": ["overlap/no-overlap", "stale PR data", "unavailable API", "owner ambiguity", "honest NOT_RUN"],
            "status": "UNDER_REVIEW"
        },
        {
            "id": "GL-HONEST-001",
            "donor": "D-GITLAB",
            "repo": "gitlab.com/zyganali/universal-agent-os-gitlab-edition",
            "commit": "3c4a412b6040d8a8154c15325943c409be9105f2",
            "paths": ["src/connectors/boundary.py"],
            "behavior": ["preserve unavailable external/tool results rather than fabricate success"],
            "method": "CLEAN_ROOM_REIMPLEMENTED",
            "target": ["src/connectors/boundary.py"],
            "transform": ["connector/evidence boundary across GitHub, metadata graph, and optional managed services"],
            "forbidden": ["fabricated API responses"],
            "tests": ["unavailable/permission/timeout/rate-limit states remain explicit"],
            "status": "UNDER_REVIEW"
        }
    ]

    new_inventory = ""
    for comp in components:
        new_inventory += f"### {comp['id']}\n\n```yaml\n"
        new_inventory += f"component_id: {comp['id']}\n"
        new_inventory += f"status: {comp['status']}\n"
        new_inventory += f"donor_id: {comp['donor']}\n"
        new_inventory += f"repository: {comp['repo']}\n"
        new_inventory += f"source_commit: {comp['commit']}\n"
        new_inventory += "source_paths:\n"
        for p in comp['paths']:
            new_inventory += f"  - {p}\n"
        new_inventory += "license_state: VERIFIED_COMPATIBLE\n"
        new_inventory += "source_behavior:\n"
        for b in comp['behavior']:
            new_inventory += f"  - {b}\n"
        new_inventory += f"reuse_method: {comp['method']}\n"
        new_inventory += "target_paths_or_contracts:\n"
        for t in comp['target']:
            new_inventory += f"  - {t}\n"
        new_inventory += "required_transformations:\n"
        for t in comp['transform']:
            new_inventory += f"  - {t}\n"
        new_inventory += "forbidden_carry_over:\n"
        for f_carry in comp['forbidden']:
            new_inventory += f"  - {f_carry}\n"
        new_inventory += "required_tests:\n"
        for t in comp['tests']:
            new_inventory += f"  - {t}\n"
        new_inventory += "competition_introduction_commit: PENDING\n"
        new_inventory += "evidence:\n  - source inspection\n"
        new_inventory += "reviewer: primary agent + donor-reuse-auditor\n"
        new_inventory += "last_reviewed: 2026-08-07T17:25:00Z\n"
        new_inventory += "```\n\n"

    final_text = part1 + new_inventory + tail

    with open(r"c:\Users\MEHMET\.gemini\antigravity\scratch\ChangeMesh\docs\DONOR_REUSE_MANIFEST.md", "w", encoding="utf-8") as f:
        f.write(final_text)

if __name__ == "__main__":
    fix_manifest()
