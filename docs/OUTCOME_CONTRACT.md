# ChangeMesh Outcome Contract

This contract defines the strict, measurable success metrics for the ChangeMesh MVP. These metrics directly reflect the value proposition to the primary buyer (VP of Engineering / CTO) by proving that ChangeMesh reduces coordination overhead while maintaining safety.

## 1. Human Touches Compressed
- **Definition:** The total number of human approvals, PR reviews, and Slack alignments avoided per schema change saga.
- **Formula:** `(Expected baseline sync points) - (Actual human-on-the-loop decisions via Reversibility Gate)`
- **Data Source:** Change Evidence Passport (Event ledger vs. Reversibility Gate logs).
- **Demo Target:** Prove that a multi-step change requiring traditionally ~5 approvals is reduced to exactly **1 compressed human authority decision** at the irreversible execution boundary.

## 2. Autonomous Steps
- **Definition:** The number of distinct plan actions executed by the agent fleet without requiring human intervention.
- **Formula:** `Total sub-tasks in saga plan where state is PASS or FAIL without HUMAN_AUTHORITY_REQUIRED`.
- **Data Source:** Cloud Run orchestration trace and Firestore state ledger.
- **Demo Target:** Show at least **10 autonomous steps** (e.g., repo analysis, dependency mapping, impact assessment, mock migration generation, rollback script generation, ShadowLab test run) occurring async before prompting the human operator.

## 3. Recovery Behavior
- **Definition:** The system's ability to detect an environmental failure (e.g., API 503, rate limit) or an internal agent crash, and safely resume without duplicating irreversible work.
- **Formula:** `Count of successful resumptions after injected faults / Total injected faults`.
- **Data Source:** Pub/Sub dead-letter queues and ADK orchestrator retry logs.
- **Demo Target:** Demonstrate exactly **1 successful recovery** in ShadowLab simulation (e.g., mocking a GitHub API timeout during PR generation) that resumes from the Memory Bank without failure.

## 4. Evidence Completeness
- **Definition:** The cryptographic and logical integrity of the final Change Evidence Passport.
- **Formula:** `Sum of (Verified Capabilities + Trusted Memory References + Passed Rehearsals + Recorded Tool Calls) / Required Schema Policy Checks`.
- **Data Source:** Final Change Evidence Passport JSON.
- **Demo Target:** The generated passport contains **100% of the required sections** (mission, agent identities, rehearsal proof, human approval, code diff) and passes the independent Evidence Auditor check.

## 5. Time-to-Safe-Draft-PR
- **Definition:** The elapsed time from the user's initial goal prompt to the creation of a fully tested, rehearsed, and safe Draft PR with migration artifacts.
- **Formula:** `Timestamp(Draft PR Created) - Timestamp(Goal Accepted)`.
- **Data Source:** OpenTelemetry tracing (end-to-end saga span).
- **Demo Target:** Under **5 minutes** for the reference `customer_id` -> `account_id` scenario (compared to days of manual sync).
