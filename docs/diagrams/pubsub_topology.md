# ChangeMesh Pub/Sub Event Backbone Topology

**Schema Version:** `1.0.0`
**Canonical Topology Version:** `1.0.0`

## 1. Architectural Diagram

```mermaid
flowchart TD
    subgraph Publishers ["Event Producers"]
        P_ORCH["Change Orchestrator / Saga"]
        P_AGENTS["Specialist Fleet (Impact Scout, Policy Guardian, etc.)"]
        P_AUTH["Authority Gate / Approval Compression"]
        P_REHEARSAL["ShadowLab / Evidence Generator"]
        P_RETRY["Retry Scheduler"]
    end

    subgraph Topics ["Google Pub/Sub Topics (v1)"]
        T_LIFE["changemesh-lifecycle-v1<br/>(CHANGE_LIFECYCLE)"]
        T_WORK["changemesh-agent-work-v1<br/>(AGENT_WORK)"]
        T_AUTH["changemesh-approval-v1<br/>(APPROVAL_AUTHORITY)"]
        T_EVID["changemesh-evidence-v1<br/>(EVIDENCE)"]
        T_RETRY["changemesh-retry-v1<br/>(RETRY)"]
        T_DEAD["changemesh-dead-letter-v1<br/>(DEAD_LETTER)"]
    end

    subgraph Subscriptions ["Pub/Sub Subscriptions (v1)"]
        S_LIFE["changemesh-lifecycle-sub-v1<br/>(Ack: 30s)"]
        S_WORK["changemesh-agent-work-sub-v1<br/>(Ack: 60s)"]
        S_AUTH["changemesh-approval-sub-v1<br/>(Ack: 30s)"]
        S_EVID["changemesh-evidence-sub-v1<br/>(Ack: 30s)"]
        S_RETRY["changemesh-retry-sub-v1<br/>(Ack: 30s)"]
        S_DEAD["changemesh-dead-letter-sub-v1<br/>(Ack: 60s, NO DL Policy)"]
    end

    subgraph Consumers ["Event Consumers / Handlers"]
        C_ORCH["Change Orchestrator / Saga State Machine"]
        C_AGENTS["Agent Fleet Task Workers"]
        C_AUTH["Authority Manager / Human In Loop"]
        C_EVID["Evidence Recorder & PubSub Timeline Projection"]
        C_RETRY["Retry Handler / Dispatcher"]
        C_DEAD["Dead-Letter Diagnostics & Terminal Handoff"]
    end

    %% Publishing edges
    P_ORCH -->|State transitions| T_LIFE
    P_ORCH -->|Dispatch task| T_WORK
    P_AUTH -->|Approval request / decision| T_AUTH
    P_REHEARSAL -->|Rehearsal / audit evidence| T_EVID
    P_ORCH -->|Schedule retry| T_RETRY
    P_RETRY -->|Retry trigger| T_LIFE

    %% Topic to Subscription bindings
    T_LIFE --> S_LIFE
    T_WORK --> S_WORK
    T_AUTH --> S_AUTH
    T_EVID --> S_EVID
    T_RETRY --> S_RETRY
    T_DEAD --> S_DEAD

    %% Subscription to Consumer bindings
    S_LIFE --> C_ORCH
    S_WORK --> C_AGENTS
    S_AUTH --> C_AUTH
    S_EVID --> C_EVID
    S_RETRY --> C_RETRY
    S_DEAD --> C_DEAD

    %% Dead letter routing (Max attempts: 5)
    S_LIFE -.->|5 delivery failures| T_DEAD
    S_WORK -.->|5 delivery failures| T_DEAD
    S_AUTH -.->|5 delivery failures| T_DEAD
    S_EVID -.->|5 delivery failures| T_DEAD
    S_RETRY -.->|5 delivery failures| T_DEAD
```

## 2. Topic and Subscription Matrix

| Topic ID | Logical Kind | Attached Subscription | Default Consumer | Dead Letter Target |
|---|---|---|---|---|
| `changemesh-lifecycle-v1` | `CHANGE_LIFECYCLE` | `changemesh-lifecycle-sub-v1` | Change Orchestrator / Saga | `changemesh-dead-letter-v1` (5 attempts) |
| `changemesh-agent-work-v1` | `AGENT_WORK` | `changemesh-agent-work-sub-v1` | Specialist Agent Fleet | `changemesh-dead-letter-v1` (5 attempts) |
| `changemesh-approval-v1` | `APPROVAL_AUTHORITY` | `changemesh-approval-sub-v1` | Authority Manager | `changemesh-dead-letter-v1` (5 attempts) |
| `changemesh-evidence-v1` | `EVIDENCE` | `changemesh-evidence-sub-v1` | Evidence Ledger & Timeline | `changemesh-dead-letter-v1` (5 attempts) |
| `changemesh-retry-v1` | `RETRY` | `changemesh-retry-sub-v1` | Retry Handler | `changemesh-dead-letter-v1` (5 attempts) |
| `changemesh-dead-letter-v1` | `DEAD_LETTER` | `changemesh-dead-letter-sub-v1` | Dead-Letter Diagnostics | *None (no cycle)* |

## 3. Canonical ChangeState Mapping

| ChangeState | Primary Topic | Secondary Topic | Role / Event Intent |
|---|---|---|---|
| `RECEIVED` | `changemesh-lifecycle-v1` | - | Initial change intake and validation |
| `DISCOVERING` | `changemesh-lifecycle-v1` | `changemesh-agent-work-v1` | Impact scout repository discovery dispatch |
| `QUALIFYING` | `changemesh-lifecycle-v1` | `changemesh-agent-work-v1` | Policy Guardian boundary qualification |
| `REHEARSING` | `changemesh-lifecycle-v1` | `changemesh-evidence-v1` | ShadowLab rehearsal twin execution |
| `GROUNDED` | `changemesh-lifecycle-v1` | - | Evidence grounded; autonomy policy evaluation |
| `AWAITING_AUTHORITY` | `changemesh-lifecycle-v1` | `changemesh-approval-v1` | Human authority escalation notification |
| `AUTHORIZED` | `changemesh-lifecycle-v1` | `changemesh-approval-v1` | Authority confirmed receipt |
| `EXECUTING` | `changemesh-lifecycle-v1` | `changemesh-agent-work-v1` | Release steward / migration engineer dispatch |
| `VERIFYING` | `changemesh-lifecycle-v1` | `changemesh-evidence-v1` | Post-execution verification suite |
| `CERTIFYING` | `changemesh-lifecycle-v1` | `changemesh-evidence-v1` | Evidence auditor blind semantic audit |
| `RETRY_SCHEDULED` | `changemesh-lifecycle-v1` | `changemesh-retry-v1` | Transient failure backoff dispatch |
| `COMPENSATING` | `changemesh-lifecycle-v1` | `changemesh-agent-work-v1` | Saga rollback / compensation execution |
| `BLOCKED` | `changemesh-lifecycle-v1` | `changemesh-evidence-v1` | Policy block terminal evidence |
| `COMPLETE` | `changemesh-lifecycle-v1` | `changemesh-evidence-v1` | Final completion and passport seal |
| `FAILED` | `changemesh-lifecycle-v1` | `changemesh-dead-letter-v1` | Terminal failure and dead-letter handoff |
| `CANCELLED` | `changemesh-lifecycle-v1` | - | Explicit cancellation transition |

## 4. Operational Invariants

1. **Non-Self-Applying:** Topology declarations in `events/topology.py` and `events/topology_manifest.json` do not mutate external cloud infrastructure at load time.
2. **Provider Neutrality:** All topology classes remain in `events/` and `domain/contracts/` with zero Google SDK dependencies.
3. **Dead-Letter Cycle Prohibition:** Subscriptions attached to the dead-letter topic MUST NOT specify a `dead_letter_policy`.
4. **Exhaustive State Coverage:** Every canonical `ChangeState` enum value has an explicit deterministic route in `lifecycle_routes`.
