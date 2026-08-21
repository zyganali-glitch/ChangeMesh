"""ChangeMesh P-29.01 — Post-Hackathon Product Architecture Separation Suite.

Acceptance criteria from master plan:
  - Path avoids locking customer data into demo architecture.
  - Verification that product architecture note defines clean 4-plane separation
    (Control Plane, Adapter Plane, Policy Pack Plane, Customer Data Plane).
  - Verification of zero-custody customer data principles.

Required evidence: Product architecture note (docs/P-29.01_PRODUCT_ARCHITECTURE_SEPARATION.md).
Mandatory documentation sync: README future.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ARCH_NOTE_PATH = REPO_ROOT / "docs" / "P-29.01_PRODUCT_ARCHITECTURE_SEPARATION.md"


class TestProductArchitectureSeparation:
    """Verify 4-plane product architecture decoupling."""

    def test_architecture_note_exists_and_declares_four_planes(self):
        """Architecture note must define all 4 architectural planes."""
        assert ARCH_NOTE_PATH.is_file(), f"Missing architecture note: {ARCH_NOTE_PATH}"
        text = ARCH_NOTE_PATH.read_text(encoding="utf-8")

        assert "1. CONTROL PLANE" in text
        assert "2. ADAPTER PLANE" in text
        assert "3. POLICY PACK PLANE" in text
        assert "4. CUSTOMER DATA PLANE" in text

    def test_zero_custody_principles_declared(self):
        """Zero-custody data handling and customer VPC isolation must be explicit."""
        text = ARCH_NOTE_PATH.read_text(encoding="utf-8")

        assert "Zero Raw Customer Data Retention" in text
        assert "Pluggable Adapters" in text
        assert "Customer VPC" in text

    def test_reversibility_and_security_controls(self):
        """Reversibility gates and policy packs must be codified."""
        text = ARCH_NOTE_PATH.read_text(encoding="utf-8")

        assert "Reversibility Gates" in text
        assert "Model Armor" in text
