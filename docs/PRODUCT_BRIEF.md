# ChangeMesh Product Brief

## Product Thesis
ChangeMesh treats an enterprise change as a **long-lived distributed transaction**, not a chat session. It enables enterprise agent fleets to work autonomously for hours or weeks across repositories, dependencies, and environments, escalating only the smallest irreducible set of human authority decisions.

## Primary Buyer
**VP of Engineering / CTO**
- **Core concerns:** Developer velocity, incident reduction, governance, and minimizing the cost of cross-team coordination.
- **Value prop:** ChangeMesh reduces the friction of enterprise modernization and high-risk refactoring by turning manual, error-prone coordination into policy-governed, autonomous agent tasks with cryptographic evidence of safety.

## Primary Operator
**Senior Staff Engineer / Platform Engineer**
- **Core concerns:** Executing complex, multi-repository changes safely without breaking downstream clients or spending weeks in sync meetings.
- **Value prop:** ChangeMesh acts as an autonomous execution fleet that handles the tedious work of discovering dependencies, rehearsing migrations, and preparing rollbacks. The operator only needs to review the final "Approval Compression Card" at the Reversibility Gate before allowing irreversible actions.

## Affected Teams
- **Downstream Consumers:** Frontend, Mobile, Data Engineering, and Analytics teams.
- **Core concerns:** API stability, data integrity, and clear migration paths.
- **Value prop:** ChangeMesh's "Migration Engineer" and "Impact Scout" subagents ensure downstream systems are either updated simultaneously or provided with backward-compatible adapters during the transition, preventing broken builds and data pipelines.

## Initial Product Wedge
**High-Risk Schema and API Changes**
- **Reference Scenario:** Renaming a core domain concept, such as `customer_id` to `account_id`, across a microservice architecture.
- **Why this wedge?** It demonstrates concrete cross-system impact, requires multi-agent coordination (discovery, policy check, migration generation, rollback proof), and provides a strong, credible product path that is easily demoed.
- **Explicit Non-Goal:** Generic platform sprawl. ChangeMesh is not a generic chatbot, generic workflow builder, or generic agent marketplace. It is strictly focused on proof-carrying enterprise change.
