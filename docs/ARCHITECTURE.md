# ChangeMesh Architecture

Status: `PLANNED`

Canonical contracts currently live in `README.md`, `AGENT_ARCHITECTURE_AND_PATTERNS.md`, and master-plan phases P-04/P-05.

During P-04 this file must gain component diagram, trust/authority boundaries, agent delegation, event/saga flow, evidence authority map, Google Cloud deployment diagram, fixture/real boundary, failure/compensation flow, and privacy/threat boundaries.

Do not publish a final diagram before implementation contracts are frozen.

Per ADR-0006, all architecture must strictly align with the `docs/CATEGORY_MAPPING.md` which maps the "Fortified Enterprise Fleet" category requirements (Registry, Runtime, Memory Bank, Identity, Gateway, Armor, Observability) to concrete modules.

Per ADR-0007, the MVP architecture local environment lacks Application Default Credentials (ADC), yielding PERMISSION_BLOCKED. Implementation is frozen until credentials are provided.
