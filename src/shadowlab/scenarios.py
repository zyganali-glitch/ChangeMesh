"""ChangeMesh ShadowLab scenario schema and standard test scenarios.

P-13.01: Defines declarative synthetic rehearsal scenarios with injected faults,
preconditions, expected policy outcomes, retry limits, and simulation labeling.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Dict, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from domain.contracts.evidence import EvidenceState, ExecutionEvidenceMode

CANONICAL_SCHEMA_VERSION = "1.0.0"


class FaultType(str, Enum):
    """Types of faults injected during ShadowLab rehearsals."""

    NONE = "NONE"
    HTTP_503_SERVICE_UNAVAILABLE = "HTTP_503_SERVICE_UNAVAILABLE"
    DATABASE_LOCK_TIMEOUT = "DATABASE_LOCK_TIMEOUT"
    PARTIAL_APPLY_INTERRUPT = "PARTIAL_APPLY_INTERRUPT"
    STALE_APPROVAL_REJECTION = "STALE_APPROVAL_REJECTION"
    PROMPT_INJECTION_ATTEMPT = "PROMPT_INJECTION_ATTEMPT"
    MISSING_ROLLBACK_STEP = "MISSING_ROLLBACK_STEP"
    LEGACY_CLIENT_SCHEMA_BREAK = "LEGACY_CLIENT_SCHEMA_BREAK"


class InjectedFault(BaseModel):
    """Specification of an intentional fault injected into a rehearsal step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fault_type: FaultType
    target_step: str
    failure_count: int = 1  # Number of times step fails before succeeding (for transient faults)
    error_message: str = "Injected synthetic fault for resilience rehearsal"

    @field_validator("target_step", "error_message")
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class ShadowScenario(BaseModel):
    """Declarative rehearsal scenario for ShadowLab execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    scenario_id: str
    name: str
    description: str
    preconditions: Dict[str, str] = {}
    injected_fault: Optional[InjectedFault] = None
    expected_policy_outcome: str  # "ALLOW", "DENY_RETRY", "DENY_COMPENSATE", "QUARANTINE"
    max_retry_limit: int = 3
    pass_criteria: str

    @field_validator(
        "scenario_id", "name", "description", "expected_policy_outcome", "pass_criteria"
    )
    @classmethod
    def _not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return v


class RehearsalOutcome(BaseModel):
    """Immutable result of a ShadowLab synthetic twin rehearsal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    scenario_id: str
    evidence_mode: ExecutionEvidenceMode = ExecutionEvidenceMode.SIMULATION
    evidence_state: EvidenceState  # PASS, FAIL, SIMULATED, etc.
    passed: bool
    steps_executed: int
    retries_attempted: int
    fault_recovered: bool
    compensation_executed: bool
    evidence_digest: str  # SHA-256 of execution trace
    simulation_logs: Tuple[str, ...]
    details: str


def compute_simulation_digest(scenario_id: str, logs: Sequence[str]) -> str:
    """Compute deterministic SHA-256 digest over simulation logs."""
    content = f"scenario:{scenario_id}\n" + "\n".join(logs)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_standard_shadow_scenarios() -> Dict[str, ShadowScenario]:
    """Canonical battery of 7 ShadowLab rehearsal scenarios."""
    return {
        "SCENARIO_NORMAL_MIGRATION": ShadowScenario(
            scenario_id="SCENARIO_NORMAL_MIGRATION",
            name="Clean Schema Migration Rehearsal",
            description="Rehearses non-breaking column addition with backwards compatibility",
            preconditions={"postgres_version": "15.4", "table_exists": "users"},
            injected_fault=InjectedFault(fault_type=FaultType.NONE, target_step="none"),
            expected_policy_outcome="ALLOW",
            max_retry_limit=1,
            pass_criteria="Schema migration succeeds cleanly with zero errors",
        ),
        "SCENARIO_503_TRANSIENT_RECOVERY": ShadowScenario(
            scenario_id="SCENARIO_503_TRANSIENT_RECOVERY",
            name="API 503 Transient Failure & Exponential Backoff Rehearsal",
            description="API returns 503 Service Unavailable twice, succeeds on 3rd retry",
            preconditions={"api_endpoint": "https://api.github.com"},
            injected_fault=InjectedFault(
                fault_type=FaultType.HTTP_503_SERVICE_UNAVAILABLE,
                target_step="step_api_call",
                failure_count=2,
                error_message="HTTP 503 Backend Service Temporarily Unavailable",
            ),
            expected_policy_outcome="ALLOW",
            max_retry_limit=3,
            pass_criteria="Retries with exponential backoff and completes on retry #3",
        ),
        "SCENARIO_PARTIAL_INTERRUPTION_COMPENSATION": ShadowScenario(
            scenario_id="SCENARIO_PARTIAL_INTERRUPTION_COMPENSATION",
            name="Partial Apply Interruption & Saga Compensation Rehearsal",
            description="Step 2 encounters database lock timeout; orchestrator triggers step 1 compensation",
            preconditions={"database": "postgres", "lock_contention": "high"},
            injected_fault=InjectedFault(
                fault_type=FaultType.DATABASE_LOCK_TIMEOUT,
                target_step="step_create_index",
                failure_count=99,
                error_message="Deadlock detected / Lock wait timeout exceeded",
            ),
            expected_policy_outcome="DENY_COMPENSATE",
            max_retry_limit=1,
            pass_criteria="Rolls back step 1 and returns clean compensated state",
        ),
        "SCENARIO_STALE_APPROVAL": ShadowScenario(
            scenario_id="SCENARIO_STALE_APPROVAL",
            name="Stale Approval Token Rejection Rehearsal",
            description="Approval token generated for older plan hash is submitted",
            preconditions={"approval_token": "token-hash-old"},
            injected_fault=InjectedFault(
                fault_type=FaultType.STALE_APPROVAL_REJECTION,
                target_step="step_reversibility_gate",
                failure_count=1,
                error_message="Approval token hash does not match current plan hash",
            ),
            expected_policy_outcome="DENY_RETRY",
            max_retry_limit=1,
            pass_criteria="Blocks execution and requests refreshed human approval",
        ),
        "SCENARIO_PROMPT_INJECTION": ShadowScenario(
            scenario_id="SCENARIO_PROMPT_INJECTION",
            name="Untrusted Schema Comment Prompt Injection Rehearsal",
            description="Database comment contains adversarial jailbreak directive",
            preconditions={"untrusted_field": "comment"},
            injected_fault=InjectedFault(
                fault_type=FaultType.PROMPT_INJECTION_ATTEMPT,
                target_step="step_ingest_schema",
                failure_count=1,
                error_message="Prompt injection pattern detected in untrusted input",
            ),
            expected_policy_outcome="QUARANTINE",
            max_retry_limit=1,
            pass_criteria="Quarantines hostile memory and prevents privilege escalation",
        ),
        "SCENARIO_MISSING_ROLLBACK": ShadowScenario(
            scenario_id="SCENARIO_MISSING_ROLLBACK",
            name="Irreversible Migration Rejection Rehearsal",
            description="Plan drops column without down-migration script or backup",
            preconditions={"operation": "DROP COLUMN"},
            injected_fault=InjectedFault(
                fault_type=FaultType.MISSING_ROLLBACK_STEP,
                target_step="step_plan_audit",
                failure_count=1,
                error_message="Plan violates Reversibility Policy: missing down migration",
            ),
            expected_policy_outcome="DENY_RETRY",
            max_retry_limit=2,
            pass_criteria="Rejects irreversible change and triggers automatic plan correction",
        ),
        "SCENARIO_LEGACY_CLIENT_BREAK": ShadowScenario(
            scenario_id="SCENARIO_LEGACY_CLIENT_BREAK",
            name="Legacy Client Breaking Change Rehearsal",
            description="Column rename breaks queries from active v1 mobile client",
            preconditions={"client_version": "v1.2.0"},
            injected_fault=InjectedFault(
                fault_type=FaultType.LEGACY_CLIENT_SCHEMA_BREAK,
                target_step="step_blast_radius",
                failure_count=1,
                error_message="Breaking contract change detected for active client v1.2.0",
            ),
            expected_policy_outcome="DENY_RETRY",
            max_retry_limit=2,
            pass_criteria="Detects client breakage and expands migration to expand-contract pattern",
        ),
    }
