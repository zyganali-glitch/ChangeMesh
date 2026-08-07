# P-02D — Evidence Matrix

This matrix tracks the required evidence for the donor reuse closure across all identified components.

| Component ID | Pinned SHA | Method | Target Path / Concept | Status |
|---|---|---|---|---|
| UAOS-GOV-001 | `6b83b06212101c238ec28076a2ba7ae819f483f2` | ADAPTED | `AGENTS.md`, `plans/CHANGEMESH_MASTER_EXECUTION_PLAN.md` | VERIFIED |
| UAOS-MEM-001 | `6b83b06212101c238ec28076a2ba7ae819f483f2` | ADAPTED | `.agents/skills/agentos-memory/SKILL.md` | VERIFIED |
| UIPATH-STATE-001 | `dc2267939c2aef0aba2737da65f53352c5cf8fb2` | CLEAN_ROOM_REIMPLEMENTED | `src/orchestrator/firestore_saga.py` | UNDER_REVIEW |
| UIPATH-AUTH-001 | `dc2267939c2aef0aba2737da65f53352c5cf8fb2` | CLEAN_ROOM_REIMPLEMENTED | `src/auth/approval_compression.py` | UNDER_REVIEW |
| CCT-EVID-001 | `65ee1b72faf9a7202d9166eed43fb671804815a8` | CLEAN_ROOM_REIMPLEMENTED | `src/evidence/evidence_record.py` | UNDER_REVIEW |
| CCT-FLIGHT-001 | `65ee1b72faf9a7202d9166eed43fb671804815a8` | CLEAN_ROOM_REIMPLEMENTED | `src/evidence/pubsub_timeline.py` | UNDER_REVIEW |
| CCT-PREFLIGHT-001 | `65ee1b72faf9a7202d9166eed43fb671804815a8` | CLEAN_ROOM_REIMPLEMENTED | `src/policy/shadowlab_auth.py` | UNDER_REVIEW |
| CCT-SEM-001 | `65ee1b72faf9a7202d9166eed43fb671804815a8` | CLEAN_ROOM_REIMPLEMENTED | `src/agents/evidence_auditor.py` | UNDER_REVIEW |
| CCT-JUDGE-001 | `65ee1b72faf9a7202d9166eed43fb671804815a8` | REFERENCE_ONLY | `docs/JUDGING_MAP.md` | VERIFIED |
| ZK-PRIV-001 | `d663db8c706cb914e1af5caf651df08edb5c50c0` | CLEAN_ROOM_REIMPLEMENTED | `src/policy/policy_guardian.py` | UNDER_REVIEW |
| ZK-VALID-001 | `d663db8c706cb914e1af5caf651df08edb5c50c0` | CLEAN_ROOM_REIMPLEMENTED | `src/core/gemini_structured_output.py` | UNDER_REVIEW |
| ZK-CLAIM-001 | `d663db8c706cb914e1af5caf651df08edb5c50c0` | REFERENCE_ONLY | `src/audit/claim_audit.py` | UNDER_REVIEW |
| CS-BLAST-001 | `0dc924db9d82037d2e813548bdee27af5f180889` | ADAPTED | `src/git/impact_scout.py` | UNDER_REVIEW |
| CS-MIG-001 | `0dc924db9d82037d2e813548bdee27af5f180889` | CLEAN_ROOM_REIMPLEMENTED | `src/agents/migration_engineer.py` | UNDER_REVIEW |
| CS-PASS-001 | `0dc924db9d82037d2e813548bdee27af5f180889` | ADAPTED | `src/evidence/change_passport.py` | UNDER_REVIEW |
| CS-WRITE-001 | `0dc924db9d82037d2e813548bdee27af5f180889` | CLEAN_ROOM_REIMPLEMENTED | `src/agents/release_steward.py` | UNDER_REVIEW |
| QW-MEM-001 | `a43b3411856f41a4be9424d11c01a5e637cdc410` | CLEAN_ROOM_REIMPLEMENTED | `src/memory/trust_layer.py` | UNDER_REVIEW |
| QW-BUS-001 | `a43b3411856f41a4be9424d11c01a5e637cdc410` | CLEAN_ROOM_REIMPLEMENTED | `src/memory/saga_bus.py` | UNDER_REVIEW |
| GL-CONFLICT-001 | `3c4a412b6040d8a8154c15325943c409be9105f2` | CLEAN_ROOM_REIMPLEMENTED | `src/git/conflict_check.py` | UNDER_REVIEW |
| GL-HONEST-001 | `3c4a412b6040d8a8154c15325943c409be9105f2` | CLEAN_ROOM_REIMPLEMENTED | `src/connectors/boundary.py` | UNDER_REVIEW |
