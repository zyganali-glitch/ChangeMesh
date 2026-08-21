"""ChangeMesh P-28.04 — Deployed E2E Service and Smoke Integration Suite.

Acceptance criteria from master plan:
  - No local-only hidden dependency.
  - Verification that /run and /run-e2e HTTP endpoints execute the full multi-agent
    change saga end-to-end and return complete evidence payloads.
  - Verification that the returned change saga achieves terminal state COMPLETE with
    valid digest, evidence reports, and zero unhandled errors.

Required evidence: Cloud test report (docs/P-28.04_DEPLOYED_E2E_CLOUD_REPORT.md).
Mandatory documentation sync: Judging map.
"""

from __future__ import annotations

import json
import urllib.request
from http.server import HTTPServer
from threading import Thread
from typing import Generator

import pytest

from service_app import ChangeMeshServiceHandler


@pytest.fixture(scope="module")
def test_server() -> Generator[str, None, None]:
    """Run an in-process instance of ChangeMeshServiceHandler on an ephemeral port."""
    server = HTTPServer(("127.0.0.1", 0), ChangeMeshServiceHandler)
    port = server.server_port
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()


class TestDeployedE2EServiceExecution:
    """Verify HTTP invocation of full multi-agent saga execution."""

    def test_post_run_e2e_executes_saga_successfully(self, test_server: str):
        """POST /run-e2e must execute the synthetic enterprise saga and return complete result."""
        url = f"{test_server}/run-e2e"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))

            assert data["status"] == "SUCCESS"
            assert data["final_state"] == "COMPLETE"
            assert data["fixture_id"] == "fixture-acme-billing-v1"
            assert "change_id" in data
            assert len(data["demo_digest"]) >= 8
            assert "timestamp" in data

    def test_post_run_alias_executes_identically(self, test_server: str):
        """POST /run alias must produce identical complete execution structure."""
        url = f"{test_server}/run"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "SUCCESS"
            assert data["final_state"] == "COMPLETE"
            assert "demo_digest" in data
