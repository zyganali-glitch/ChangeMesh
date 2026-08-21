"""ChangeMesh Cloud Run Service Harness and Judge Dashboard Server.

Bounded runtime harness exposing health, runtime verification,
bounded execution endpoints, and accessible Judge/Operator Dashboard for ChangeMesh.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from src.core.gemini_client import CANONICAL_MODEL_ID
from src.dashboard.data_provider import (
    DashboardLoadingState,
    DashboardSnapshot,
)
from src.demo.e2e_demo import run_local_e2e_demo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("changemesh-service")

CANONICAL_COMMIT_SHA = "6bdce723c3304fca31f8ae264f026a445c0431e8"
STATIC_DIR = Path(__file__).parent / "src" / "dashboard" / "static"


class ChangeMeshServiceHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict[str, Any]) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.is_file():
            self._send_json(404, {"error": "Not Found", "file": str(file_path)})
            return

        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        # 1. Health endpoint
        if self.path == "/health":
            self._send_json(
                200,
                {
                    "status": "OK",
                    "service": "changemesh-p24-e2e",
                    "canonical_commit": CANONICAL_COMMIT_SHA,
                    "canonical_model": CANONICAL_MODEL_ID,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "environment": {
                        "project": os.environ.get(
                            "GOOGLE_CLOUD_PROJECT", "project-af5e1c99-3bc4-424f-b53"
                        ),
                        "region": os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west3"),
                    },
                },
            )
            return

        # 2. Dashboard API endpoint
        if self.path in ("/api/dashboard/snapshot", "/api/snapshot"):
            now = datetime.now(timezone.utc)
            # Produce structured snapshot
            snapshot = DashboardSnapshot(
                schema_version="1.0.0",
                tenant_id="tenant-changemesh-demo",
                loading_state=DashboardLoadingState.LOADED,
                snapshot_digest="2f36878ce9c8329b",
                generated_at=now,
                change_view=None,
                agent_views=(),
                timeline_entries=(),
                capability_views=(),
                memory_trust=None,
                approval_views=(),
                cloud_proof_views=(),
            )
            self._send_json(200, json.loads(snapshot.model_dump_json()))
            return

        # 3. Static Assets Serving
        if self.path == "/static/styles.css":
            self._send_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return

        if self.path == "/static/app.js":
            self._send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return

        # 4. Root & Dashboard HTML
        if self.path in ("/", "/dashboard", "/index.html"):
            index_path = STATIC_DIR / "index.html"
            if index_path.is_file():
                self._send_file(index_path, "text/html; charset=utf-8")
            else:
                self._send_json(
                    200,
                    {
                        "status": "OK",
                        "service": "changemesh-p24-e2e",
                        "canonical_commit": CANONICAL_COMMIT_SHA,
                        "canonical_model": CANONICAL_MODEL_ID,
                    },
                )
            return

        # 5. Fallback 404
        self._send_json(404, {"error": "Not Found", "path": self.path})

    def do_POST(self) -> None:
        if self.path in ("/run", "/run-e2e"):
            try:
                now = datetime.now(timezone.utc)
                result = run_local_e2e_demo(now=now)
                self._send_json(
                    200,
                    {
                        "status": "SUCCESS",
                        "fixture_id": result.fixture_id,
                        "change_id": result.change_id,
                        "final_state": result.final_state.value,
                        "demo_digest": result.demo_digest,
                        "timestamp": now.isoformat(),
                    },
                )
            except Exception as e:
                logger.error("E2E execution failed: %s", e)
                self._send_json(500, {"status": "ERROR", "error": str(e)})
        else:
            self._send_json(404, {"error": "Not Found", "path": self.path})


def run_server(port: int = 8080) -> None:
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, ChangeMeshServiceHandler)
    logger.info("ChangeMesh Cloud Run service listening on port %d...", port)
    httpd.serve_forever()


if __name__ == "__main__":
    port_env = os.environ.get("PORT", "8080")
    run_server(int(port_env))
