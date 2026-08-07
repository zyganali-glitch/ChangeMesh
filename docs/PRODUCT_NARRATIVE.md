# ChangeMesh Product Narrative

Status: `FROZEN`

These narratives serve as the canonical description of ChangeMesh for Devpost, GitHub, and all product materials. They must contain zero generic AI-assistant language ("smart AI that helps you code" or "an assistant that writes software").

## One-Sentence Narrative (Tagline)
ChangeMesh is a policy-governed agent fleet that safely rehearses and executes high-risk enterprise architecture changes.

## Ten-Second Narrative (Elevator Pitch)
ChangeMesh treats an enterprise change—like renaming a core schema field across dozens of microservices—as a long-lived distributed transaction, not a chat session. Using the Google Agent Development Kit and Gemini, it discovers dependencies, rehearses migrations in a shadow environment, and compresses weeks of manual coordination into a single, tamper-evident Change Evidence Passport.

## Thirty-Second Narrative
When you need to rename `customer_id` to `account_id` without breaking downstream pipelines, a single coding agent isn't enough. ChangeMesh deploys a fleet of highly specialized ADK agents to safely coordinate the work across repositories. It grounds itself in institutional memory, enforces data policies, and dry-runs the migration against synthetic data. Instead of generating endless PR reviews and sync meetings, ChangeMesh compresses the entire saga into a single "Approval Card." It escalates only the irreducible human decision at the execution boundary, proving its work via Google Cloud observability traces.

## Independent-Product Narrative (Beyond Hackathon)
While the hackathon wedge proves safe execution of cross-system schema changes, ChangeMesh's long-term product path is Enterprise Reversibility Infrastructure. It will become the standard governance layer for multi-agent systems, providing agent capability certification, memory trust boundaries, and cryptographic proof-of-safety for any long-running autonomous action across regulated enterprise environments.
