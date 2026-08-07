# ChangeMesh Non-Goals & Product Red Lines

Status: `PLANNED`

To ensure the MVP remains focused, credible, and compliant with enterprise governance standards, we explicitly define the following non-goals and red lines. 

## Red Lines (Strict Prohibitions)
These are actions the agent fleet is technically forbidden or architecturally prevented from doing in the MVP:

1. **No Automatic Production Merge/Deploy:**
   - The final action of the MVP is generating a *Draft Pull Request* with a Change Evidence Passport.
   - The fleet will NEVER automatically merge code into the `main`/`master` branch or trigger production deployments.
2. **No Real Customer Data:**
   - Agents will never ingest, parse, or migrate real Production PII (Personally Identifiable Information).
   - Rehearsals will use explicitly synthetic graph/DataHub models.
3. **No Unlabeled Mocks for Managed Claims:**
   - If a Google Cloud service is unavailable, any local adapter must be explicitly labeled `LOCAL_FIXTURE`.
   - The MVP must not present a simulation as a real Google Cloud runtime execution.

## Non-Goals (Out of Scope for MVP)
These features may be valuable later but distract from the core "proof-carrying enterprise change" wedge:

1. **Generic Agent Marketplace:** We are not building a platform for third-party developers to upload generic chat agents. ChangeMesh is a closed fleet of highly specialized, capability-verified change agents.
2. **Formal Verification:** We do not claim cryptographic formal verification of code correctness. We claim cryptographic *evidence linkage* of agent actions, test results, and policy checks.
3. **Unsupported Compliance Certifications:** We will not claim HIPAA, SOC2, or FedRAMP compliance for the Hackathon MVP, as these require third-party audits. We claim *governance readiness* via Reversibility Gates and Memory Trust Layers.
4. **Generic Workflow Builder:** We are not an alternative to Zapier or Airflow. We manage stateful, multi-agent *change transactions*, not arbitrary cron jobs.
