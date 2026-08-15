# ChangeMesh Evidence Boundary

## Execution/Evidence Mode

- `FIXTURE`: Static, predetermined, or synthetic test inputs/test doubles.
- `SIMULATION`: Dynamic controlled rehearsal without real target mutation.
- `RECORDED_CLOUD`: Read-only replay of evidence captured from an actual Google Cloud execution.
- `LIVE_WRITE`: A real credential-backed action causing a real externally observable mutation.

## Evidence State

- `PASS`: named check/action executed and succeeded
- `WARN`: evidence exists but needs attention
- `FAIL`: named check executed and failed
- `NOT_RUN`: not executed
- `SIMULATED`: executed in ShadowLab or fixture
- `BLOCKED`: policy prevented execution; action remains `NOT_RUN`
- `QUARANTINED`: excluded from decisions pending trust review

## Mode vs Evidence State

Execution/Evidence Mode and Evidence State are orthogonal concepts. They must never be collapsed into one enum. Mode answers *where* and *under what side-effect boundary* an operation occurred, whereas Evidence State answers *what happened* to the named check or action.
For example, `SIMULATED` is a state, not a mode. A simulated test run could be `SIMULATION + PASS` (the check passed in a simulated environment). `SIMULATED` as a state means the EvidenceRecord itself represents a simulated/substitute outcome rather than proof of real target action, and is not a synonym for `PASS`.

**Invariant:** State cannot erase mode provenance. A fixture success remains `FIXTURE PASS` and cannot be claimed as a live execution `PASS`.

**Mandatory Provenance:** Every evidence record must explicitly declare its `source` (a non-blank stable human/machine-readable reference) and its `collection_mode`.
- `SIMULATED` state is only valid with a non-live controlled provenance (`FIXTURE` or `SIMULATION`). `LIVE_WRITE + SIMULATED` or `RECORDED_CLOUD + SIMULATED` will fail validation.
- `RECORDED_CLOUD` mode evidence requires historical provenance: a `source_execution_identifier`, a `source_execution_timestamp`, and at least one immutable `ArtifactHash`. It does not imply current live execution.

## Authorities

Authority in ChangeMesh is strictly separated into four lanes:

1. **Execution facts**: Deterministic code.
2. **Semantic adequacy**: Gemini semantic authority artifact.
3. **Organizational constraints**: Organizational policy authority.
4. **Human decision**: Only for policy-defined human authority slots.

| Question | Authority |
|---|---|
| Did command run? | Recorded local/cloud execution evidence (`DETERMINISTIC_CODE`) |
| Did tool call occur? | Event ledger and correlated trace (`DETERMINISTIC_CODE`) |
| Did test pass? | Test runner output and artifact hash (`DETERMINISTIC_CODE`) |
| Is memory valid? | Memory Trust Layer deterministic policy (`DETERMINISTIC_CODE`) |
| Is agent revision qualified? | Capability Passport validator (`DETERMINISTIC_CODE`) |
| Is action autonomously allowed? | Organizational policy authority (`ORGANIZATIONAL_POLICY`) |
| Does evidence semantically cover goal? | Gemini semantic assessment, advisory (`GEMINI_SEMANTIC_JUDGMENT`) |
| May irreversible work proceed? | Compressed human authority (`HUMAN_AUTHORITY`) |

> [!IMPORTANT]
> Human approval does not convert deterministic `FAIL`/`NOT_RUN` into `PASS` and does not silently bypass hard organizational policy.

## Separation

Fixture data is not customer data. Synthetic graph is not live DataHub. Local simulation is not managed Google proof. Model explanation is not test evidence. Deployment screenshot without revision/logs is weak evidence. Public claims must link current sanitized artifacts.

*Note (ADR-0007): All managed service claims (Agent Runtime/Platform + Cloud Run for supporting services, Firestore as Operational State, Pub/Sub) must point to actual Google Cloud deployment evidence, not local simulators.*

## P-05.03 Domain Contracts vs Runtime

The `EvidenceRecord` domain contract and its supporting schemas (`EvidenceState`, `ExecutionEvidenceMode`, `Provenance`, `TraceReference`, `ArtifactHash`) are implemented as provider-neutral, strict Pydantic schemas.
These schemas guarantee deterministic fact sovereignty: neither a model's judgment nor human approval can overwrite a deterministic execution fact (e.g., turning a `FAIL` or `BLOCKED` into a `PASS`).
All evidence timestamps and artifact hashes conform strictly to `docs/CONTRACT_CONVENTIONS.md` (UTC-aware `UtcDateTime`, SHA-256 64-char hex digests).

The runtime Evidence Ledger service (`src/evidence/evidence_record.py`) and adapters (such as Firestore persistence or Pub/Sub timelines) are explicitly deferred and **not yet implemented**. P-05.03 only defines the immutable evidence contracts.
