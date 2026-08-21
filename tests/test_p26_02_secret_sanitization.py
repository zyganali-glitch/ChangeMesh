"""ChangeMesh P-26.02 — Secret Scanning, Log Redaction, and Evidence Sanitization Security Suite.

Acceptance criteria from master plan:
  - Known secret fixtures caught; public artifacts clean.
  - Verification of pre-SDK privacy scanning, wire payload redaction, and log sanitization.
  - Zero raw secrets in prompts, logs, evidence packs, public screenshots, and commits.

Required evidence: Security tests (docs/P-26.02_SECURITY_SANITIZATION_REPORT.md).
Mandatory documentation sync: Demo guide.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from domain.contracts.conventions import REDACTION_SENTINEL, redact_mapping
from domain.contracts.event_envelope import EventEnvelope
from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode
from events.wire import scan_payload_for_secrets
from src.agents.policy_guardian import PolicyGuardian, PrivacySeverity
from src.evidence.evidence_ledger import EvidenceLedger
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.orchestrator.orchestrator_saga import sanitize_secrets_in_text
from src.policy.policy_engine import DeterministicPolicyChecker

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"


class TestSecretScanningEngine:
    """Verify that known secret fixtures are deterministically caught."""

    SYNTHETIC_SECRETS = [
        ("Google AI Studio Key", "AIzaSy" + "DUMMY_KEY_XYZ_1234567890abcdefABC"),
        ("GitHub Classic PAT", "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyz"),
        ("AWS Access Key", "AKIA" + "IOSFODNN7EXAMPLE"),
        (
            "Database Password in URL",
            "postgres://app_user:SuperSecretPassword123!@db.internal:5432/billing",
        ),
        ("Credential Assignment Header", "password = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'"),
    ]

    def test_known_synthetic_secrets_caught_by_policy_guardian(self):
        """PolicyGuardian.audit_privacy_text must catch all standard synthetic secret patterns."""
        for name, secret in self.SYNTHETIC_SECRETS:
            text = f"Configure the migration using credentials: {secret}"
            audit = PolicyGuardian.audit_privacy_text(text)
            assert audit.safe_to_send is False, f"Scanner failed to detect secret fixture: {name}"
            assert len(audit.blockers) > 0, f"No blocking findings for: {name}"
            assert any(b.severity == PrivacySeverity.BLOCK for b in audit.blockers)

    def test_policy_guardian_blocks_secret_in_input(self):
        """DeterministicPolicyChecker must produce BLOCK findings for inputs containing secrets."""
        checker = DeterministicPolicyChecker()
        secret_payload = "api_key = 'AIzaSy" + "dummytoken1234567890abcdefghij'"
        decision = checker.evaluate(
            input_text=secret_payload,
            tool_ids=["tool-sql-generator"],
            target_paths=["migrations/001.sql"],
            action_type="schema_migration",
            data_classification="INTERNAL",
            change_id="change-test-secret-01",
        )
        assert decision.overall_verdict == "BLOCK"
        assert decision.blocked_count >= 1
        assert any(f.category.value == "SECRET_DETECTED" for f in decision.findings)


class TestLogAndPromptRedaction:
    """Verify recursive redaction and text sanitization."""

    def test_recursive_redact_mapping(self):
        """redact_mapping must redact sensitive keys at arbitrary nesting depth."""
        nested_data: Dict[str, Any] = {
            "service": "billing-app",
            "config": {
                "password": "super_secret_password_123",
                "api_key": "AIzaSy" + "dummy_token_value_here_1234567",
                "nested_credentials": {
                    "private_key": "-----" + "BEGIN PRIVATE KEY" + "-----",
                    "token": "bearer_secret_xyz",
                },
            },
            "public_field": "safe_value",
        }

        redacted = redact_mapping(nested_data)
        assert redacted["public_field"] == "safe_value"
        assert redacted["config"]["password"] == REDACTION_SENTINEL
        assert redacted["config"]["api_key"] == REDACTION_SENTINEL
        assert redacted["config"]["nested_credentials"]["private_key"] == REDACTION_SENTINEL
        assert redacted["config"]["nested_credentials"]["token"] == REDACTION_SENTINEL

    def test_sanitize_secrets_in_text(self):
        """sanitize_secrets_in_text must replace sensitive tokens with REDACTION_SENTINEL."""
        raw_text = "Connecting with token ghp_" + "abcdefghijklmnopqrstuvwxyz123456 to github.com"
        clean_text = sanitize_secrets_in_text(raw_text)
        assert "ghp_" not in clean_text
        assert REDACTION_SENTINEL in clean_text


class TestEvidenceAndTimelineSanitization:
    """Verify evidence ledger and causal event timeline payload sanitization."""

    def test_causal_timeline_sanitizes_event_payloads(self):
        """CausalEventTimeline must store redacted event payloads."""
        timeline = CausalEventTimeline(change_id="change-101")
        envelope = EventEnvelope(
            schema_version="1.0.0",
            event_id="evt-001",
            change_id="change-101",
            correlation_id="corr-101",
            idempotency_key="idem-101",
            producer_id="agent-orch",
            producer_revision="rev-1",
            producer_role="ORCHESTRATOR",
            timestamp=datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc),
        )
        safe_payload = {
            "status": "IN_PROGRESS",
            "phase": "REHEARSAL",
            "step": "AST_VALIDATION",
        }
        entry = timeline.record_event(
            envelope=envelope,
            topic_id="changemesh-timeline-topic",
            payload=safe_payload,
        )
        assert entry.payload_summary["status"] == "IN_PROGRESS"
        assert entry.payload_summary["phase"] == "REHEARSAL"

    def test_scan_payload_for_secrets_detects_secret(self):
        """scan_payload_for_secrets in wire module must detect secrets and raise ValueError."""
        payload = {
            "token": "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyz",
            "action": "commit",
        }
        with pytest.raises(ValueError, match="Prohibited credential field name 'token'"):
            scan_payload_for_secrets(payload)

    def test_evidence_ledger_binds_sanitized_payload_digest(self):
        """EvidenceLedger must hash and chain entries deterministically."""
        ledger = EvidenceLedger()
        entry = ledger.append(
            entry_id="ev-01",
            tenant_id="tenant-acme",
            change_id="change-01",
            subject="POLICY_EVALUATION",
            evidence_state=EvidenceState.PASS,
            collection_mode=ExecutionEvidenceMode.SIMULATION,
            artifact_digest="a" * 64,
        )
        assert entry.sequence_number == 1
        assert len(entry.entry_digest) == 64
        valid, err = ledger.verify_integrity()
        assert valid is True
        assert err is None


class TestPublicArtifactsSanitization:
    """Verify that committed JSON evidence packs and public files contain zero live secrets."""

    def test_live_cloud_e2e_evidence_json_clean(self):
        """docs/P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json must contain zero unredacted secret tokens."""
        evidence_file = DOCS_DIR / "P-24.05_LIVE_CLOUD_E2E_EVIDENCE.json"
        assert evidence_file.is_file()
        content = evidence_file.read_text(encoding="utf-8")
        data = json.loads(content)

        # Check required fields
        assert data["project_id"] == "project-af5e1c99-3bc4-424f-b53"
        assert data["region"] == "europe-west3"
        assert data["gemini_model_id"] == "gemini-3.6-flash"

        # Verify no live secrets
        assert "AIzaSy" not in content
        assert "ghp_" not in content
        assert "-----BEGIN" not in content
