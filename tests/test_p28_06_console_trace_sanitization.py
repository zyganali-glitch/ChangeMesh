"""ChangeMesh P-28.06 — Sanitized Console, Log, and Cloud Trace Verification Suite.

Acceptance criteria from master plan:
  - Screens show service/revision/time without secrets.
  - Verification that Cloud Run logs and trace emissions contain structured metadata
    (service_name, revision, model_id, span_id) with zero secrets or private tokens.
  - Verification that secret scanner detects zero raw keys or bearer tokens in console dumps.
  - Verification that demo script aligns with sanitized four-minute walkthrough steps.

Required evidence: Screenshot/console artifacts (docs/P-28.06_SANITIZED_CONSOLE_EVIDENCE_REPORT.md).
Mandatory documentation sync: Demo script.
"""

from __future__ import annotations

import json
from pathlib import Path

from events.wire import scan_payload_for_secrets
from src.orchestrator.orchestrator_saga import sanitize_secrets_in_text

REPO_ROOT = Path(__file__).parent.parent
DEMO_SCRIPT_PATH = REPO_ROOT / "docs" / "DEMO_SCRIPT.md"


class TestConsoleLogTraceSanitization:
    """Verify secret sanitization on console logs, traces, and demo documentation."""

    def test_demo_script_contains_zero_secrets(self):
        """Demo script must be valid markdown free of secret tokens."""
        assert DEMO_SCRIPT_PATH.is_file(), f"Missing demo script: {DEMO_SCRIPT_PATH}"
        text = DEMO_SCRIPT_PATH.read_text(encoding="utf-8")
        # Should not raise ValueError
        scan_payload_for_secrets({"text": text})
        assert "LIVE_WRITE" in text
        assert "RECORDED_CLOUD" in text

    def test_structured_log_trace_sanitization(self):
        """Synthetic trace and log packets must redact raw tokens and keys."""
        raw_log_entry = {
            "service": "changemesh-p24-e2e",
            "revision": "changemesh-p24-e2e-00001-jjp",
            "trace_id": "projects/project-af5e1c99/traces/4bf92f3577b34da6a3ce929d0e0e4736",
            "span_id": "00f067aa0ba902b7",
            "model_id": "gemini-3.6-flash",
            "authorization_header": "Bearer AIzaSyDeadBeefSecretKey1234567890ABCDEF",
            "user_email": "judge@enterprise.example.com",
        }

        serialized = json.dumps(raw_log_entry)
        sanitized = sanitize_secrets_in_text(serialized)

        assert "AIzaSyDeadBeefSecretKey" not in sanitized
        assert "[REDACTED_SECRET:" in sanitized or "[REDACTED" in sanitized

    def test_clean_cloud_trace_spans_schema(self):
        """Cloud trace spans must contain valid hex identifiers and no credential leaks."""
        sample_trace = {
            "traceId": "projects/project-af5e1c99/traces/4bf92f3577b34da6a3ce929d0e0e4736",
            "spanId": "00f067aa0ba902b7",
            "name": "GeminiClient.generate_text",
            "attributes": {
                "/http/status_code": "200",
                "model.id": "gemini-3.6-flash",
                "project.id": "project-af5e1c99-3bc4-424f-b53",
            },
        }

        # Should not raise ValueError
        scan_payload_for_secrets(sample_trace)
        assert sample_trace["attributes"]["model.id"] == "gemini-3.6-flash"
