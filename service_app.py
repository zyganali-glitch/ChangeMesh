"""ChangeMesh Cloud Run Service Harness.

Bounded runtime harness exposing health, runtime verification, and
bounded execution endpoints for ChangeMesh P-24.05 E2E.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from domain.contracts.change_lifecycle import ChangeState
from src.core.gemini_client import CANONICAL_MODEL_ID
from src.demo.e2e_demo import run_local_e2e_demo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("changemesh-service")

CANONICAL_COMMIT_SHA = "6bdce723c3304fca31f8ae264f026a445c0431e8"


class ChangeMeshServiceHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict[str, Any]) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            self._send_json(
                200,
                {
                    "status": "OK",
                    "service": "changemesh-p24-e2e",
                    "canonical_commit": CANONICAL_COMMIT_SHA,
                    "canonical_model": CANONICAL_MODEL_ID,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "environment": {
                        "project": os.environ.get("GOOGLE_CLOUD_PROJECT", "project-af5e1c99-3bc4-424f-b53"),
                        "region": os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west3"),
                    },
                },
            )
        else:
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
