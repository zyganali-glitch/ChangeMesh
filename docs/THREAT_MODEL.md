# ChangeMesh Threat Model and Trust Boundaries

> **Status:** `P-04.03 — PLANNED / PRE-IMPLEMENTATION`
> **Produced by:** P-04.03
> **Date:** 2026-08-09
> **Implementation state:** This document defines architecture design. It is NOT a penetration-test report, security certification, or proof of live deployment. The agent, identity, and armor components discussed are architectural requirements or planned controls, some of which may currently be in a `BLOCKED` or `NOT_RUN` state (e.g. Model Armor).

## 1. Scope
This document enumerates the trust boundaries for the ChangeMesh application. It defines data flows, credential isolation principles, and failure behaviors. It addresses the boundaries between User, Agent, Subagent, Tool, GitHub, Metadata Graph, Google Cloud, and the Public Judge UI.

## 2. Trust Assumptions
- **Local Developer Environments:** Local machines (e.g. using Application Default Credentials) are outside the verifiable product proof but still require safe secret handling.
- **Untrusted External Systems:** External systems (GitHub, APIs) may return malicious, hostile, or malformed content (prompt injections).
- **Agent/Model Output is Advisory:** Agent and model semantic outputs are NOT trusted authority by default.
- **Untrusted Public Inputs:** The public judge UI acts as a hostile/untrusted edge.
- **Sensitive Credentials:** Adapter credentials and tokens are highly sensitive and must not be exposed.
- **Cloud Infrastructure is Not a Pass:** Being on Google Cloud does not eliminate the need for application-level data minimization and validation.

## 3. Trust Domains
The system explicitly recognizes the following independent trust domains:
1. **Human User / Operator**
2. **Public Judge UI**
3. **ChangeMesh Application / Orchestrator**
4. **Agent**
5. **Subagent**
6. **Tool / Adapter Boundary**
7. **GitHub**
8. **Metadata Graph**
9. **Google Cloud (including Gemini/Vertex semantic boundary)**

## 4. Trust-Boundary Diagram

```mermaid
flowchart TD
    %% Legend: A --> B means Data/Request flows from A to B across a trust boundary.
    %% This diagram models trust and data flow, NOT dependency direction (P-04.01).
    
    User[Human User / Operator]
    PublicUI[Public Judge UI]
    App[ChangeMesh Application / Orchestrator]
    Agent[Agent]
    Subagent[Subagent]
    ToolB[Tool / Adapter Boundary]
    GitHub[GitHub]
    Metadata[Metadata Graph]
    GCP[Google Cloud / Firestore / PubSub]
    Gemini[Gemini / Vertex AI]

    User -->|TB-01: Intent, Goal, Policy Slot| App
    PublicUI -->|TB-02: Untrusted Input| App
    App -->|TB-12: Sanitized Evidence| PublicUI
    App -->|TB-03: Bounded Mission| Agent
    App -->|TB-09: App State (No raw secrets)| GCP
    App -->|TB-13: Authority Requests| User
    Agent -->|TB-04: Bounded Delegation| Subagent
    Agent -->|TB-05: Typed Request (No raw secrets)| ToolB
    Subagent -->|TB-05: Typed Request| ToolB
    ToolB -->|TB-06: API Request (via Adapter Credentials)| GitHub
    GitHub -->|TB-06: Untrusted External Content| ToolB
    ToolB -->|TB-07: Graph Query| Metadata
    Metadata -->|TB-07: Untrusted External Metadata| ToolB
    App -->|TB-08: Minimized Context| Gemini
    Gemini -->|TB-08: Untrusted Semantic Output| App
```

**Diagram Legend:**
`A --> B` = Information/request crosses a trust boundary from domain A to domain B.

## 5. Boundary-Crossing Inventory

| Boundary ID | Source | Destination | Purpose | Data Crossing | Credential Used? | Credential Material Crossing? | Validation / Sanitization | Minimization Rule | Failure Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TB-01** | User | Application | Provide goals, authority | Goal, Intent, Repo Ref | Yes (Deferred) | **NO** | Policy check, schema match | Bounded payload | Reject unauthorized |
| **TB-02** | Public UI | Application | Demo interaction | Untrusted Input | No | **NO** | Strict type & intent filtering | Limit input size/type | Drop invalid input |
| **TB-03** | Application | Agent | Task routing | Bounded task context | No | **NO** | Passport qualification | No global context | Halt/Quarantine |
| **TB-04** | Agent | Subagent | Task delegation | Sub-task context | No | **NO** | Passport capability check | Sub-scope ≤ Parent | Terminate subagent |
| **TB-05** | Agent/Sub | Tool Boundary | API Invocation | Tool args, targets | No | **NO** | Allowed-tool check, arg validation | Min required args | Return typed error |
| **TB-06** | Tool B. | GitHub | Read/Write Ops | Repo reads, Draft writes| Yes (Adapter) | **NO** | Validate structure | Target file/diff only | Block execution |
| **TB-07** | Tool B. | Metadata | Lineage query | Entity references | Yes (Adapter) | **NO** | Schema validation | Target subgraph only | Treat as missing |
| **TB-08** | App | Gemini/Vertex | Semantic evaluation | Sanitized context | Yes (Adapter) | **NO** | Structured Output Validation | Redact secrets/PII | Fallback/Quarantine |
| **TB-09** | App | Firestore | Durable state | Operational state | Yes (Workload) | **NO** | Schema enforced | Store hashes/refs | Fail fast (500) |
| **TB-10** | App | Pub/Sub | Chronology | Events (no blobs) | Yes (Workload) | **NO** | Envelope schema | No blobs, only refs | Drop / Dead-letter |
| **TB-11** | App | Observability | Telemetry | Traces, logs | Yes (Workload) | **NO** | Redaction filter | No CoT, no tokens | Log silently fails |
| **TB-12** | App | Public UI | Display evidence | Sanitized Artifacts | No | **NO** | Redaction of secrets/internals | Sanitize CoT/tokens | Display error |
| **TB-13** | User | App | Approval Compression | Decision, scope | Yes (Deferred) | **NO** | Check against policy slots | Minimal decision bits | Treat as DENY |

## 6. Zero-Trust and Credential Isolation Model
- **Adapter-Only Credentials:** Credentials (e.g., `GITHUB_TOKEN`, API Keys) exist strictly at the external adapter boundary.
- **Inward Propagation Ban:** Credential material must **never** cross inward into the model prompt, agent memory, evidence artifacts, public judge UI, or ordinary unredacted logs.
- **Local vs Cloud:** Prefer Application Default Credentials (ADC) locally and workload/managed identity in Google Cloud. No service-account JSON key files should be distributed.

## 7. Data Minimization Rules
For every crossing, the payload must be purpose-bound. The system uses identifiers, hashes, bounded excerpts, references, or derived summaries instead of complete raw objects whenever possible (e.g., passing a Git hash instead of cloning a repo into the event payload). 
- *Data Classification concept*: Operational Data vs Conceptual Public Information vs Secret/Credential. (Note: Not an explicit schema definition for P-05).
- *Customer Data*: ChangeMesh MVP does not require real customer data; it targets synthetic/demo enterprise data.

## 8. Agent/Subagent Delegation Trust (Confused Deputy Control)
- **Bounded Delegation:** A parent agent cannot delegate authority it does not possess.
- **No Unrestricted Inheritance:** A subagent does not inherit unrestricted parent privileges. Tool access and data access are strictly limited to the sub-task.

## 9. External-Content & Prompt Injection Rule
- **Data vs Instruction:** Content from GitHub, metadata graphs, and tool responses is strictly treated as **untrusted data**.
- **Immutable System Rules:** External content cannot modify agent/system rules, organizational policy, tool permissions, authority classes, or credential handling.

## 10. Specific Boundary Rules
- **GitHub & Metadata:** External repositories and metadata graphs are hostile boundaries. Text may contain prompt injections. Write workflows (via Release Steward) require explicit authorization and bounded targets.
- **Google Cloud:** Managed service access still requires data minimization.
- **Public Judge UI:** A hostile, low-trust edge. The public UI cannot hold reusable live-write credentials or act as an authority source. No private chain-of-thought, service-account material, or customer data is exposed.
- **Human Authority:** Human responses carry bounded intent but cannot overwrite deterministic facts or bypass hard policy denies outside established paths.

## 11. Threat / Control Matrix

| Threat ID | Threat Description | Planned Control (Architecture Level) |
| :--- | :--- | :--- |
| **T-01** | Prompt injection via repo/tool/metadata | External content treated as data; structured validation boundaries. |
| **T-02** | Credential exfiltration | Adapter-side credentials only; strict ban on inward propagation; redaction. |
| **T-03** | Over-broad tool authority | Bounded capability scope; policy enforcement; least privilege constraints. |
| **T-04** | Agent/subagent confused deputy | Bounded delegation (delegated scope ≤ caller scope). |
| **T-05** | Evidence poisoning / fabricated tool execution | Deterministic Evidence Record; Gemini cannot manufacture facts. |
| **T-06** | Public judge UI disclosure | Sanitized/minimized read surface; no reusable secrets/internals exposed. |
| **T-07** | Sensitive logging/tracing | Log redaction/minimization; no tokens or private reasoning. |
| **T-08** | Unauthorized external write | Release Steward policy check + human authority prerequisite. |
| **T-09** | Stale/untrusted memory | Memory Trust Layer enforces provenance, TTL, and quarantine rules. |
| **T-10** | Unvalidated Gemini output | Structured validation before consumption; no authority escalation allowed. |

*(Note: These are planned architectural controls, not execution proofs or penetration test results).*

## 12. Failure Behavior Principles
- Missing validation fails closed.
- Missing credentials return unavailability (blocked), not fabricated success.
- Invalid external payloads are rejected or quarantined.
- Secrets detected in artifacts block publication.

## 13. Relationship to P-04.02 Authority Map
**Authority ≠ Trust.** A data payload crossing a trust boundary does not escalate its authority class. 
- GitHub text (untrusted) cannot become Organizational Policy.
- Gemini semantic evaluation (advisory) cannot overwrite Deterministic execution facts.
- A public UI action cannot synthesize Human Authority.

## 14. Explicitly Deferred Work
- **P-04.04:** Defines fixture, simulation, recorded-cloud, and live-write modes/boundaries.
- **P-04.05:** Autonomy vs. Friction review.
- **P-05:** Concrete domain contracts, Pydantic schemas, TypeScript interfaces (e.g., `DataClass`, `TrustLevel`).
- **P-06:** Implementation stack (Python version, auth SDK, secret manager).
