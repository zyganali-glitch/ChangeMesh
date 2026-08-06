# ChangeMesh Evidence Boundary

## States

- `PASS`: named check/action executed and succeeded
- `WARN`: evidence exists but needs attention
- `FAIL`: named check executed and failed
- `NOT_RUN`: not executed
- `SIMULATED`: executed in ShadowLab or fixture
- `BLOCKED`: policy prevented execution; action remains `NOT_RUN`
- `QUARANTINED`: excluded from decisions pending trust review

## Authorities

| Question | Authority |
|---|---|
| Did command run? | Recorded local/cloud execution evidence |
| Did tool call occur? | Event ledger and correlated trace |
| Did test pass? | Test runner output and artifact hash |
| Is memory valid? | Memory Trust Layer deterministic policy |
| Is agent revision qualified? | Capability Passport validator |
| Is action autonomously allowed? | Reversibility Gate policy |
| Does evidence semantically cover goal? | Independent Gemini assessment, advisory |
| May irreversible work proceed? | Organizational policy and compressed human authority |

## Separation

Fixture data is not customer data. Synthetic graph is not live DataHub. Local simulation is not managed Google proof. Model explanation is not test evidence. Deployment screenshot without revision/logs is weak evidence. Public claims must link current sanitized artifacts.
