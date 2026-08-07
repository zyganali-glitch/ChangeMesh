# Apply the ChangeMesh Donor Reuse Update

This package is an additive patch built from the current GitHub master plan whose blob SHA was `a91661a5e3e83195b70d53695e9bce3722501254`.

## Replace these files with the full versions in this package

- `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md`
- `AGENTS.md`
- `AGENT_OS_RULES.md`
- `docs/COMPONENT_PROVENANCE.md`

Each replacement preserves the prior file as an exact prefix and appends stricter donor controls.

## Add these new files

- `docs/DONOR_REUSE_MANIFEST.md`
- `.agents/rules/30-donor-provenance-lock.md`
- `.agents/skills/donor-reuse-preflight/SKILL.md`
- `.agents/agents/donor-reuse-auditor/agent.md`

## Do not overwrite

Do not overwrite `docs/HANDOFF.md`; the repository already contains newer live state. After copying the update, the primary agent must update handoff to mention the new P-02D hard gate while preserving current P-01.01 progress.

## Required first commit

Use a dedicated documentation/governance commit before product code, for example:

```powershell
git add AGENTS.md AGENT_OS_RULES.md plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md docs/COMPONENT_PROVENANCE.md docs/DONOR_REUSE_MANIFEST.md .agents/rules/30-donor-provenance-lock.md .agents/skills/donor-reuse-preflight/SKILL.md .agents/agents/donor-reuse-auditor/agent.md
git commit -m "docs: add binding donor reuse and provenance control plane"
git push
```

Then update `docs/HANDOFF.md` in the normal live-governance flow. The currently active P-01.01 remains active; P-02D begins only after P-02 and blocks P-03.
