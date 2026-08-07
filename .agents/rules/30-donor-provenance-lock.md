---
activation: always_on
---

# ChangeMesh Donor Provenance Lock

Before donor-sensitive work, read:

@../../docs/DONOR_REUSE_MANIFEST.md
@../../docs/COMPONENT_PROVENANCE.md
@../../plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md

Mandatory behavior:

1. P-02D must be DONE.
2. The relevant P-xx.00 donor preflight must be IN_PROGRESS before donor inspection.
3. Donor repositories are read-only.
4. Use immutable commit SHAs and exact allowlisted source paths.
5. Do not copy a directory or repository wholesale.
6. Confirm license, reuse method, target mapping, forbidden carry-over, and tests before implementation.
7. Run the read-only donor-reuse-auditor.
8. Update the manifest and run P-DΩ plus P-Ω.12 before DONE.

Unknown or incomplete donor provenance is BLOCKED. Agent memory and README claims are not source proof.
