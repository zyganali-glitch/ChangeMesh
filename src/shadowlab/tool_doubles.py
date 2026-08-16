"""ChangeMesh deterministic tool doubles for ShadowLab rehearsals.

P-13.02: In-memory synthetic doubles for Database, API, and Git boundaries,
supporting controlled fault injection with strict simulation labeling.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Tuple

from domain.contracts.evidence import ExecutionEvidenceMode
from src.shadowlab.scenarios import FaultType, InjectedFault


class SimulatedDatabaseClient:
    """In-memory SQLite database double for synthetic schema migration rehearsals."""

    def __init__(self, injected_fault: Optional[InjectedFault] = None) -> None:
        self.evidence_mode = ExecutionEvidenceMode.SIMULATION
        self._fault = injected_fault
        self._fault_counter = 0
        self._conn = sqlite3.connect(":memory:")
        self._init_sandbox()

    def _init_sandbox(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            "CREATE TABLE users "
            "(id INTEGER PRIMARY KEY, email TEXT, legacy_id TEXT, created_at TEXT)"
        )
        cursor.execute("INSERT INTO users VALUES (1, 'alice@example.com', 'leg-01', '2026-01-01')")
        self._conn.commit()

    def execute_ddl(self, ddl: str, step_name: str = "step_ddl") -> Tuple[bool, str]:
        """Execute DDL statement in the sandbox, respecting injected faults."""
        if self._fault and self._fault.target_step == step_name:
            if self._fault_counter < self._fault.failure_count:
                self._fault_counter += 1
                return (
                    False,
                    f"Injected Fault ({self._fault.fault_type.value}): {self._fault.error_message}",
                )

        try:
            cursor = self._conn.cursor()
            cursor.executescript(ddl)
            self._conn.commit()
            return True, "DDL executed successfully in synthetic sandbox"
        except Exception as exc:
            return False, f"SQLite Execution Error: {exc}"

    def get_table_schema(self, table_name: str) -> List[Tuple[str, str]]:
        cursor = self._conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [(row[1], row[2]) for row in cursor.fetchall()]

    def close(self) -> None:
        self._conn.close()


class SimulatedApiClient:
    """In-memory API client double with HTTP 503 fault injection and retry tracking."""

    def __init__(self, injected_fault: Optional[InjectedFault] = None) -> None:
        self.evidence_mode = ExecutionEvidenceMode.SIMULATION
        self._fault = injected_fault
        self._fault_counter = 0
        self.attempts = 0

    def post(
        self, url: str, payload: Dict[str, str], step_name: str = "step_api_call"
    ) -> Tuple[int, Dict[str, str]]:
        """Simulate an HTTP POST request."""
        self.attempts += 1

        if (
            self._fault
            and self._fault.target_step == step_name
            and self._fault.fault_type == FaultType.HTTP_503_SERVICE_UNAVAILABLE
        ):
            if self._fault_counter < self._fault.failure_count:
                self._fault_counter += 1
                return 503, {"error": self._fault.error_message, "mode": "SIMULATION"}

        return 200, {"status": "ok", "url": url, "mode": "SIMULATION"}


class SimulatedGitClient:
    """In-memory Git client double for synthetic branch and PR operations."""

    def __init__(self) -> None:
        self.evidence_mode = ExecutionEvidenceMode.SIMULATION
        self.branches: Dict[str, List[str]] = {"main": ["initial_commit"]}
        self.pull_requests: List[Dict[str, str]] = []

    def create_branch(self, branch_name: str, from_branch: str = "main") -> bool:
        if from_branch not in self.branches:
            return False
        self.branches[branch_name] = list(self.branches[from_branch])
        return True

    def commit(self, branch_name: str, message: str) -> str:
        if branch_name not in self.branches:
            raise ValueError(f"Branch {branch_name} does not exist")
        commit_sha = f"sim-sha-{len(self.branches[branch_name]) + 1}"
        self.branches[branch_name].append(commit_sha)
        return commit_sha

    def create_pull_request(
        self, title: str, head_branch: str, base_branch: str = "main"
    ) -> Dict[str, str]:
        pr_id = f"sim-pr-{len(self.pull_requests) + 1}"
        pr = {
            "pr_id": pr_id,
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "mode": "SIMULATION",
            "state": "OPEN_DRAFT",
        }
        self.pull_requests.append(pr)
        return pr
