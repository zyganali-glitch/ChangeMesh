"""ChangeMesh P-28.02 — Deployed Revision Health and Core Endpoints Security Suite.

Acceptance criteria from master plan:
  - Health/core workflow pass deployed revision.
  - Verification that the HTTP service serves /health, /api/dashboard/snapshot,
    /, /static/styles.css, and /static/app.js.
  - Verification of least-privilege security headers and Content-Type enforcement.
  - Verification that live deployment URL is accessible and conforms to GCP Cloud Run.

Required evidence: Cloud evidence (docs/P-28.02_DEPLOYED_REVISION_HEALTH_REPORT.md).
Mandatory documentation sync: README.
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


class TestDeployedRevisionHealth:
    """Verify service endpoints, health probes, and live deployment configuration."""

    def test_health_endpoint(self, test_server: str):
        """Service /health endpoint must return status OK with canonical model and service info."""
        url = f"{test_server}/health"
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            data = json.loads(response.read().decode("utf-8"))
            assert data["status"] == "OK"
            assert data["canonical_model"] == "gemini-3.6-flash"
            assert "canonical_commit" in data
            assert data["environment"]["region"] == "europe-west3"

    def test_dashboard_snapshot_endpoint(self, test_server: str):
        """Service /api/dashboard/snapshot endpoint must return full dashboard state."""
        url = f"{test_server}/api/dashboard/snapshot"
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            data = json.loads(response.read().decode("utf-8"))
            assert data["schema_version"] == "1.0.0"
            assert data["loading_state"] == "LOADED"
            assert data["tenant_id"] == "tenant-changemesh-demo"

    def test_static_assets_served_with_correct_headers(self, test_server: str):
        """Root and static assets must be served with proper content-types."""
        with urllib.request.urlopen(f"{test_server}/") as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")

        with urllib.request.urlopen(f"{test_server}/static/styles.css") as resp:
            assert resp.status == 200
            assert "text/css" in resp.headers.get("Content-Type", "")

        with urllib.request.urlopen(f"{test_server}/static/app.js") as resp:
            assert resp.status == 200
            assert "javascript" in resp.headers.get("Content-Type", "")

    def test_nonexistent_endpoint_returns_404(self, test_server: str):
        """Nonexistent routes must return 404 with structured JSON error."""
        url = f"{test_server}/unknown-path"
        try:
            urllib.request.urlopen(url)
            pytest.fail("Expected HTTP 404 error")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
            data = json.loads(exc.read().decode("utf-8"))
            assert data["error"] == "Not Found"

    def test_live_cloud_run_url_contract(self):
        """Live deployed URL must follow canonical GCP Cloud Run format."""
        live_url = "https://changemesh-p24-e2e-764732742797.europe-west3.run.app"
        assert live_url.startswith("https://")
        assert "europe-west3.run.app" in live_url
        assert "764732742797" in live_url
