"""ChangeMesh P-29.04 — Extensibility and Plugin Contract Verification Suite.

Acceptance criteria from master plan:
  - Extensions cannot weaken evidence/authority contracts.
  - Verification that plugin contract defines monotonic safety lock
    (plugins can only add constraints).
  - Verification of interfaces for Change Types, Tool Adapters, and Policy Packs.
  - Verification of strict capability passport requirements on third-party tools.

Required evidence: Plugin contract (docs/P-29.04_EXTENSIBILITY_CONTRACT.md).
Mandatory documentation sync: Architecture.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONTRACT_PATH = REPO_ROOT / "docs" / "P-29.04_EXTENSIBILITY_CONTRACT.md"


class TestExtensibilityPluginContract:
    """Verify plugin interfaces, monotonic safety rules, and capability requirements."""

    def test_contract_file_exists_and_declares_monotonic_safety(self):
        """Plugin contract must declare monotonic safety lock."""
        assert CONTRACT_PATH.is_file(), f"Missing plugin contract: {CONTRACT_PATH}"
        text = CONTRACT_PATH.read_text(encoding="utf-8")

        assert "Monotonic Safety Lock" in text
        assert "cannot weaken core safety" in text or "weaken core safety" in text
        assert "fail closed" in text.lower()

    def test_extension_points_specified(self):
        """Contract must define interfaces for ChangeType, ToolAdapter, and PolicyRule."""
        text = CONTRACT_PATH.read_text(encoding="utf-8")

        assert "IChangeTypeHandler" in text
        assert "IToolAdapter" in text
        assert "IPolicyRule" in text
        assert "CapabilityPassport" in text or "capability_passport" in text

    def test_reversibility_and_compensation_requirements(self):
        """Change type handlers must provide compensation generation and reversibility."""
        text = CONTRACT_PATH.read_text(encoding="utf-8")

        assert "compute_reversibility" in text
        assert "generate_compensation_steps" in text
        assert "BOUNDED_WRITE_WITH_DRAFT_CEILING" in text or "READ_ONLY" in text
