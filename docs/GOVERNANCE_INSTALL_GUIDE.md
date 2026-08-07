# ChangeMesh Governance Installation Guide

## Do not install Universal Agent OS wholesale

The generic package contains mandatory Phase-0 interview, locale packs, examples, bootstrap scripts, and broad framework-maintenance surfaces that ChangeMesh does not need. Use the curated project-specific payload in this starter pack.

## Mandatory root files

- `AGENTS.md`
- `CHANGEMESH_RULES.md`
- `CHANGEMESH_PLAN_TEMPLATE.md`
- `GEMINI.md`
- four Collective Memory files
- `README.md`
- `README.tr.md`

Place these directories unchanged:

- `.agents/rules/`
- `.agents/skills/`
- `.agents/agents/`
- `plans/`
- `plans/completed/`
- `docs/`

## Donor mapping

| ChangeMesh file | Universal Agent OS donor concept | Action |
|---|---|---|
| `AGENTS.md` | root/tr `AGENTS.md` | Adapted; Phase-0 removed, integrity locks retained |
| `CHANGEMESH_RULES.md` | `tr/CHANGEMESH_RULES.md` | Adapted to ChangeMesh contracts |
| `CHANGEMESH_PLAN_TEMPLATE.md` | `tr/CHANGEMESH_PLAN_TEMPLATE.md` | Simplified child-plan template |
| Four memory files | Collective Memory pillars | Retained and pre-seeded |
| `.agents/skills/changemesh-memory` | `skills/agent-os-memory/SKILL.md` | Migrated to current Antigravity path |
| `.agents/rules/*` | legacy `.agent/rules/global-governance.md` | Updated to current `.agents/rules` standard |
| `plans/` and `plans/completed/` | Agent OS plan portfolio | Retained |

## Optional adapters

Add only when actually using the platform:

- `.github/copilot-instructions.md`
- `.codex/AGENTS.md`
- `CLAUDE.md`
- `.cursor/rules/...`

Do not add unused adapters merely for appearance.

## Do not copy by default

- full `en/` and `tr/` locale packs;
- generic donor README;
- examples;
- donor VS Code extension;
- donor CLI/MCP server;
- GitLab package files;
- installer scripts;
- donor changelog/version/license files;
- generic Phase-0 onboarding material.

They add noise, duplicate authority, or inaccurate claims.

## First setup

1. Create empty `ChangeMesh` folder.
2. Initialize Git.
3. Extract starter pack into root.
4. Create GitHub repository with same name.
5. Commit governance baseline before implementation.
6. Open folder as Antigravity Project.
7. Confirm `.agents/rules`, `.agents/skills`, and `.agents/agents` are discovered.
8. Open Antigravity Customizations → Rules and set all three ChangeMesh workspace rules to **Always On**.
9. Tell main agent: `Read the ChangeMesh constitution and continue from the next eligible micro-task in the master execution plan. Do not run Phase-0.`

## First acceptance check

- mandatory files exist;
- master plan is `PLANNING`;
- no feature falsely labeled implemented;
- handoff points to `P-00.01`;
- Git status clean after baseline commit.
