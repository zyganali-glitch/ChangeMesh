# ChangeMesh Component Provenance

Implementation status: `IN_PROGRESS` (ZK-VALID-001 `VERIFIED`; other components `PLANNED` or `APPROVED_FOR_IMPLEMENTATION`)
Architecture donor preflight gate (P-04.00): `PASS`
Gemini boundary donor preflight gate (P-08.00): `PASS`

ChangeMesh is a new product/repository. Design benefits from ideas in owner's earlier repositories, but final competition implementation must document exactly what is reused, rewritten, or new.

| Donor | Reusable idea | ChangeMesh transformation |
|---|---|---|
| Universal Agent OS | live plans, memory pillars, evidence-first closure | development governance only; remove product interview burden |
| Universal Agent OS UiPath | human authority gate and durable process state | exception-only compressed authority decisions |
| Codex Control Tower | locked facts, flight recorder, blind semantic challenge | provider-neutral evidence ledger with Gemini auditor |
| ZeroKit AI Control Plane | privacy preflight and strict contracts | Policy Guardian and typed artifact validation |
| ContextSeal | blast radius, safe migration, change passport | cross-system enterprise Change Evidence Passport |
| Qwen MemoryAgent | importance, freshness, decay, shared memory | Memory Trust Layer with provenance/quarantine |
| GitLab Edition | conflict and repository blast-radius analysis | Impact Scout with GitHub-first demo adapter |

## Implemented and Verified Donor Components

### ZK-VALID-001 — Config Validator / Strict Output Validation
- **Status:** `VERIFIED`
- **Donor ID:** `D-ZEROKIT` (`zyganali-glitch/zerokit-ai-control-plane`)
- **Immutable Donor SHA:** `d663db8c706cb914e1af5caf651df08edb5c50c0`
- **Source Paths:** `frontend/js/config-validator.js`, `tests/unit/config-validator.test.mjs`
- **License State:** `VERIFIED_COMPATIBLE` (owner-authored)
- **Reuse Method:** `CLEAN_ROOM_REIMPLEMENTED`
- **ChangeMesh Target:** `src/core/gemini_structured_output.py`
- **Competition Introduction Commit:** `27fe08c1271e4aad1527a47d35f9fefc8b361819`
- **Test Evidence:** `tests/test_p08_02_structured_output.py` (40 dedicated unit/boundary/adversarial tests PASS)
- **Materially New Contribution:** Reimplemented in Python using strict Pydantic v2 domain schemas (`extra="forbid"`, `frozen=True`, `StrictStr`, `StrictInt`), 3 semantic surfaces (Goal Decomposition, Policy Explanation, Independent Semantic Audit), exact canonical `schema_version` validation, deterministic path traversal and unsafe endpoint validators, authority lane boundary (`GEMINI_SEMANTIC_JUDGMENT`), and zero default injection. Zero ZeroKit product semantics or frontend global variables carry over.

## Mandatory final disclosure

Record original path, license, source commit, copied/adapted/clean-room status, competition-period introduction commit, tests proving new behavior, and why ChangeMesh contribution is materially new. 

Per the official Hackathon rules, any reused components must:
1. Comply with applicable open-source licenses.
2. Be fully disclosed if pre-existing.
3. Be enhanced/built upon to create materially new software during the Submission Period.

## Binding detailed ledger

The canonical component-level ledger is [`DONOR_REUSE_MANIFEST.md`](DONOR_REUSE_MANIFEST.md). The high-level table above is a summary only and never authorizes implementation.

A component is reusable only when the detailed ledger records:

- immutable donor commit;
- exact source paths;
- verified license/notice state;
- observable source behavior;
- explicit reuse method;
- exact ChangeMesh target path or contract;
- required transformations and forbidden carry-over;
- positive, failure, boundary, security, and forbidden-carry-over tests;
- competition-period introduction commit;
- reviewer and evidence;
- final `VERIFIED` status.

P-02D, each relevant P-xx.00 preflight, P-DΩ, and P-Ω.12 are mandatory. Donor repositories remain read-only.
