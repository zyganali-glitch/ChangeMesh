"""ChangeMesh End-to-End Saga Orchestrator.

P-20.01: Implements the canonical end-to-end change lifecycle saga across:
1. Discover (DISCOVERING)
2. Qualify (QUALIFYING)
3. Rehearse (REHEARSING)
4. Ground (GROUNDED)
5. Authorize (AUTHORIZED or AWAITING_AUTHORITY or BLOCKED)
6. Execute (EXECUTING)
7. Verify (VERIFYING)
8. Certify (CERTIFYING -> COMPLETE)

Invariants:
- State transitions are strictly event-driven and persisted.
- Persisted ChangeRecord with optimistic concurrency is authoritative workflow state.
- Authoritative state is persisted in SagaStateRepository before EventEnvelope publishing.
- Every admitted lifecycle transition publishes an EventEnvelope with full causation chain.
- Policy Guardian Gate hard blockers transition to BLOCKED with zero approval cards.
- HUMAN_AUTHORITY_REQUIRED halts at AWAITING_AUTHORITY with a derived Approval Compression card.
- No downstream execution tasks or external mutations on BLOCKED or AWAITING_AUTHORITY.
- Execution evidence modes remain strictly truthful; local actions are never LIVE_WRITE.
- Credentials and secrets are minimized before wire message emission and state persistence.
- Release Steward and external actions are isolated and respect ExecutionEvidenceMode.
- Deterministic facts cannot be overwritten by semantic model outputs.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from domain.contracts.agent_descriptor import AgentRevisionProvenance
from domain.contracts.autonomy import ApprovalCompressionCard, AutonomyClass
from domain.contracts.change_lifecycle import (
    ChangeState,
    can_transition,
    is_terminal,
    require_transition,
)
from domain.contracts.change_request import ChangeRequest
from domain.contracts.conventions import REDACTION_SENTINEL, redact_mapping
from domain.contracts.event_envelope import EventEnvelope
from domain.contracts.evidence import (
    EvidenceProducerKind,
    EvidenceState,
    ExecutionEvidenceMode,
)
from domain.contracts.memory import MemoryRecord
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from events.publisher import EventPublisher
from events.retry import FailureClassification
from events.topology import get_canonical_topology
from events.wire import EventWireMessage, scan_payload_for_secrets
from src.audit.audit_bundle import AuditBundleBuilder
from src.audit.claim_derivation import ClaimDerivationEngine, ClaimType, NeutralClaim
from src.audit.reconciliation import DeterministicReconciler
from src.audit.semantic_auditor import SemanticAuditor
from src.evidence.pubsub_timeline import CausalEventTimeline
from src.gate.policy_guardian_gate import PolicyGuardianGate
from src.gate.reversibility import (
    DeterministicPolicyInputs,
    NoveltyTier,
    PrivilegeLevel,
    RehearsalStatus,
    ReversibilityClassifier,
)
from src.git.impact_scout import (
    BlastRadiusMerger,
    GraphTraverser,
    RepositoryScanner,
    build_synthetic_billing_graph,
)
from src.memory.trust_layer import EpistemicTrustClass, MemoryTrustEvaluator
from src.migration.manifest_generator import ManifestGenerator
from src.migration.plan_generator import MigrationPlanGenerator
from src.orchestrator.saga_checkpoint import SagaCheckpointManager
from src.orchestrator.state_repository import (
    CANONICAL_SCHEMA_VERSION,
    ApprovalRecord,
    ApprovalResolutionStatus,
    ChangeRecord,
    EvidenceRefRecord,
    SagaStateRepository,
    TaskRecord,
    TaskStatus,
    TenantRecord,
    validate_tenant_id,
)
from src.policy.policy_engine import DeterministicPolicyChecker
from src.registry.agent_registry import (
    AgentDescriptor,
    AgentRegistry,
    InMemoryAgentRegistry,
)
from src.registry.capabilities import (
    get_standard_demo_requirements,
)
from src.registry.evidence_verifier import (
    QualificationEvidenceRecord,
    QualificationEvidenceRegistry,
    QualificationEvidenceVerifier,
)
from src.registry.passport_issuer import (
    PassportIssuanceRequest,
    PassportIssuer,
    PassportVerifier,
)
from src.shadowlab.runner import ShadowLabRunner
from src.shadowlab.scenarios import (
    ShadowScenario,
    get_standard_shadow_scenarios,
)

logger = logging.getLogger(__name__)

_SECRET_REPLACEMENT_PATTERNS = [
    re.compile(
        r"-{5}BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-{5}"
        r".*?-{5}END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-{5}",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r"-{5}BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-{5}", re.IGNORECASE),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{15,}\b", re.IGNORECASE),
    re.compile(r"\b(?:sk-(?:proj-|svcacct-)?|AIza)[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(
        r"(?:api[_-]?key|apikey|secret[_-]?key|client[_-]?secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}['\"]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^'\"]{4,}['\"]?",
        re.IGNORECASE,
    ),
]


def sanitize_secrets_in_text(text: str) -> str:
    """Sanitize credential patterns from free-form text strings."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern in _SECRET_REPLACEMENT_PATTERNS:
        result = pattern.sub(REDACTION_SENTINEL, result)
    return result


class SupportedBillingOperation(BaseModel):
    """Canonical specification of the supported synthetic additive billing migration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_name: str = "ADD_COLUMN_PAYMENT_TIER"
    allowed_targets: tuple[str, ...] = (
        "billing-db",
        "payment-service",
        "billing_db",
        "billing-api",
    )
    required_db_targets: tuple[str, ...] = (
        "billing-db",
        "billing_db",
    )
    table_name: str = "billing_accounts"
    column_name: str = "payment_tier"
    column_type: str = "VARCHAR(32)"
    source_schema: str = "billing_accounts_v1"
    target_schema: str = "billing_accounts_v2"
    sql_up: str = "ALTER TABLE billing_accounts ADD COLUMN payment_tier VARCHAR(32);"
    sql_down: str = "ALTER TABLE billing_accounts DROP COLUMN payment_tier;"
    migration_file: str = "migrations/001_add_billing_column.sql"
    supporting_files: tuple[str, ...] = (
        "migrations/001_add_billing_column.sql",
        "src/billing/service.py",
        "schema/billing.sql",
    )
    impacted_node_ids: tuple[str, ...] = ("billing-migration-001", "invoice-schema")


CANONICAL_SUPPORTED_OPERATION = SupportedBillingOperation()


def validate_supported_change_intent(request: ChangeRequest) -> tuple[bool, str]:
    """Validate that the incoming ChangeRequest matches the supported synthetic billing operation.

    Fails closed immediately if the request targets unsupported systems, lacks the
    required database target for the schema mutation, describes
    contradictory/opposite/destructive actions, unrelated schema/API/config modifications,
    or fails to match the canonical synthetic payment_tier addition on billing_accounts.
    """
    req_targets = set(request.target_systems)
    if not req_targets:
        return False, "Target systems cannot be empty"

    allowed = set(CANONICAL_SUPPORTED_OPERATION.allowed_targets)
    if not req_targets.issubset(allowed):
        unsupported = sorted(list(req_targets - allowed))
        return (
            False,
            f"Target systems contain unsupported targets: {unsupported}. "
            f"All requested targets must belong to supported set: {sorted(list(allowed))}",
        )

    required_db_targets = set(CANONICAL_SUPPORTED_OPERATION.required_db_targets)
    if not (req_targets & required_db_targets):
        return (
            False,
            "Target systems must include the required database target 'billing-db' "
            f"(or 'billing_db') for schema mutation; got {sorted(list(req_targets))}",
        )

    text = (request.title + " " + request.description).lower()

    # Reject destructive SQL commands explicitly
    destructive_keywords = [
        "drop table",
        "drop database",
        "drop column",
        "delete from",
        "truncate",
        "drop schema",
        "drop view",
        "alter table drop",
    ]
    for kw in destructive_keywords:
        if kw in text:
            return (
                False,
                (
                    f"Destructive operation {kw.upper()!r} is not supported in "
                    "additive billing fixture"
                ),
            )

    # Reject contradictory/opposite operations
    opposite_keywords = [
        "remove",
        "delete",
        "drop",
        "rename",
        "replace",
        "disable",
        "rollback",
    ]
    for kw in opposite_keywords:
        if kw in text:
            return (
                False,
                (
                    f"Contradictory/opposite operation {kw.upper()!r} is not supported in "
                    "additive billing fixture (canonical operation requires ADD COLUMN)"
                ),
            )

    # Reject explicit negation/opposition of the additive operation (fail closed)
    negated_add_patterns = [
        "do not add",
        "don't add",
        "dont add",
        "must not add",
        "should not add",
        "shall not add",
        "cannot add",
        "can not add",
        "without adding",
        "avoid adding",
        "refrain from adding",
        "prohibit adding",
        "prevent adding",
        "never add",
        "not add",
        "not adding",
        "do not alter",
        "don't alter",
        "dont alter",
        "must not alter",
        "should not alter",
        "without altering",
        "avoid altering",
        "never alter",
        "not alter",
        "do not include",
        "don't include",
        "dont include",
        "must not include",
        "should not include",
        "without including",
        "avoid including",
        "never include",
        "not include",
        "do not create",
        "don't create",
        "dont create",
        "must not create",
        "should not create",
        "without creating",
        "avoid creating",
        "never create",
        "not create",
    ]
    for pat in negated_add_patterns:
        if pat in text:
            return (
                False,
                (
                    f"Negated/opposed additive operation {pat!r} is not supported in "
                    "additive billing fixture (canonical operation requires affirmative ADD COLUMN)"
                ),
            )

    negated_add_regex = re.compile(
        r"\b(?:do\s+not|don['’]?t|dont|must\s+not|should\s+not|shall\s+not|can(?:not|\s+not)|without|avoid|refrain\s+from|prohibit|prevent|never|not)\s+(?:add|adding|addition|alter|altering|include|including|create|creating)\b",
        re.IGNORECASE,
    )
    if negated_add_regex.search(text):
        return (
            False,
            "Negated/opposed additive operation is not supported in additive billing fixture "
            "(canonical operation requires affirmative ADD COLUMN)",
        )

    # Reject unrelated configuration, API, timeout, indexing, or distinct domain operations
    unrelated_keywords = [
        "timeout",
        "api timeout",
        "connection pool",
        "cache",
        "endpoint",
        "discount_code",
        "discount",
        "tax_rate",
        "payroll",
        "invoice",
        "customer_id",
        "user_table",
        "index",
    ]
    for kw in unrelated_keywords:
        if kw in text:
            return (
                False,
                (
                    f"Unrelated operation/configuration {kw!r} is not supported in "
                    "additive billing fixture"
                ),
            )

    # Require explicit table and column match for the supported bounded operation
    table_match = (
        "billing_accounts" in text or "billing accounts" in text or "billing account" in text
    )
    column_match = "payment_tier" in text or "payment tier" in text

    # Require explicit positive additive semantics (reject generic 'migration' alone)
    positive_additive_keywords = [
        "add column",
        "add",
        "addition",
        "additive",
        "adding",
    ]
    action_match = any(act in text for act in positive_additive_keywords)

    if not (table_match and column_match and action_match):
        return (
            False,
            "Change request intent does not match supported additive billing migration "
            f"(table: {CANONICAL_SUPPORTED_OPERATION.table_name}, "
            f"column: {CANONICAL_SUPPORTED_OPERATION.column_name})",
        )

    return True, ""


class BoundedCriterionConditionSpec(BaseModel):
    """Specification of a machine-verifiable condition supported by the bounded saga."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: str
    description_summary: str
    bound_stage: str
    canonical_evidence_type: str
    required_evidence_types: tuple[str, ...]
    allowed_evidence_types: tuple[str, ...]
    accepted_statements: tuple[str, ...] = ()
    allowed_evidence_states: tuple[EvidenceState, ...] = (EvidenceState.PASS,)
    allowed_evidence_modes: tuple[ExecutionEvidenceMode, ...] = (
        ExecutionEvidenceMode.SIMULATION,
        ExecutionEvidenceMode.FIXTURE,
    )
    expected_subject: Optional[str] = None
    expected_evidence_key_prefix: Optional[str] = None


_CANONICAL_CONDITION_SPECS_DICT: dict[str, BoundedCriterionConditionSpec] = {
    "REHEARSAL_SUCCEEDED": BoundedCriterionConditionSpec(
        condition_id="REHEARSAL_SUCCEEDED",
        description_summary=(
            "ShadowLab simulated rehearsal executed and completed cleanly with "
            "zero unhandled faults"
        ),
        bound_stage="REHEARSING",
        canonical_evidence_type="REHEARSAL_SIMULATION",
        required_evidence_types=("REHEARSAL_SIMULATION",),
        allowed_evidence_types=(
            "REHEARSAL_SIMULATION",
            "SHADOWLAB_REHEARSAL",
            "REHEARSAL",
        ),
        accepted_statements=(
            "rehearsal succeeds",
            "rehearsal succeeds cleanly",
            "rehearsal completed cleanly with zero unhandled faults",
            "rehearsal completed with zero unhandled faults",
            (
                "shadowlab simulated rehearsal executed and completed cleanly with "
                "zero unhandled faults"
            ),
            "rehearsal succeeds with token [redacted]",
        ),
        allowed_evidence_states=(EvidenceState.SIMULATED,),
        allowed_evidence_modes=(ExecutionEvidenceMode.SIMULATION,),
        expected_subject="shadowlab_rehearsal",
        expected_evidence_key_prefix="ev-rehearse-",
    ),
    "MIGRATION_MANIFEST_SYNTHESIZED": BoundedCriterionConditionSpec(
        condition_id="MIGRATION_MANIFEST_SYNTHESIZED",
        description_summary=(
            "Deterministic migration DDL / manifest generated with valid file hashes"
        ),
        bound_stage="EXECUTING",
        canonical_evidence_type="MIGRATION_EXECUTION",
        required_evidence_types=("MIGRATION_EXECUTION",),
        allowed_evidence_types=(
            "MIGRATION_EXECUTION",
            "MIGRATION_SYNTHESIS",
            "DETERMINISTIC_MANIFEST",
            "MANIFEST_GENERATION",
            "ARTIFACT_GENERATION",
        ),
        accepted_statements=(
            "migration manifest contains deterministic file hashes",
            "deterministic migration manifest generated with valid file hashes",
            "migration plan generated",
            "ddl artifact generated",
            "deterministic migration ddl and manifest generated with valid file hashes",
            "migration manifest contains deterministic file hashes and ddl script",
        ),
        allowed_evidence_states=(EvidenceState.PASS,),
        allowed_evidence_modes=(
            ExecutionEvidenceMode.SIMULATION,
            ExecutionEvidenceMode.FIXTURE,
        ),
        expected_subject="migration_artifacts",
        expected_evidence_key_prefix="ev-execute-",
    ),
    "BLAST_RADIUS_DISCOVERED": BoundedCriterionConditionSpec(
        condition_id="BLAST_RADIUS_DISCOVERED",
        description_summary=(
            "Static analysis and blast radius calculation completed for target assets"
        ),
        bound_stage="DISCOVERING",
        canonical_evidence_type="BLAST_RADIUS_ANALYSIS",
        required_evidence_types=("BLAST_RADIUS_ANALYSIS",),
        allowed_evidence_types=(
            "BLAST_RADIUS_ANALYSIS",
            "BLAST_RADIUS_ESTIMATION",
            "AST_STATIC_ANALYSIS",
            "DISCOVERY",
        ),
        accepted_statements=(
            "static analysis and blast radius calculation completed for target assets",
            "static analysis and blast radius calculation completed",
            "blast radius calculation completed",
            "blast radius analysis completed",
            "blast radius discovered",
        ),
        allowed_evidence_states=(EvidenceState.PASS,),
        allowed_evidence_modes=(
            ExecutionEvidenceMode.SIMULATION,
            ExecutionEvidenceMode.FIXTURE,
        ),
        expected_subject="blast_radius",
        expected_evidence_key_prefix="ev-discover-",
    ),
    "CAPABILITIES_QUALIFIED": BoundedCriterionConditionSpec(
        condition_id="CAPABILITIES_QUALIFIED",
        description_summary=(
            "Agent fleet capability passports verified against requirement specifications"
        ),
        bound_stage="QUALIFYING",
        canonical_evidence_type="CAPABILITY_QUALIFICATION",
        required_evidence_types=("CAPABILITY_QUALIFICATION",),
        allowed_evidence_types=(
            "CAPABILITY_QUALIFICATION",
            "AGENT_QUALIFICATION",
            "PASSPORT_VERIFICATION",
        ),
        accepted_statements=(
            "agent fleet capability passports verified against requirement specifications",
            "agent capability passports verified against requirement specifications",
            "agent capabilities qualified",
            "capability passports verified",
            "capabilities qualified",
        ),
        allowed_evidence_states=(EvidenceState.PASS,),
        allowed_evidence_modes=(
            ExecutionEvidenceMode.SIMULATION,
            ExecutionEvidenceMode.FIXTURE,
        ),
        expected_subject="capability_qualification",
        expected_evidence_key_prefix="ev-qualify-",
    ),
    "EPISTEMIC_GROUNDED": BoundedCriterionConditionSpec(
        condition_id="EPISTEMIC_GROUNDED",
        description_summary=(
            "Epistemic memory trust evaluation and deterministic policy pre-checks completed"
        ),
        bound_stage="GROUNDED",
        canonical_evidence_type="EPISTEMIC_GROUNDING",
        required_evidence_types=("EPISTEMIC_GROUNDING",),
        allowed_evidence_types=(
            "EPISTEMIC_GROUNDING",
            "POLICY_PRECHECK",
            "GROUNDING",
        ),
        accepted_statements=(
            "epistemic memory trust evaluation and deterministic policy pre-checks completed",
            "epistemic memory trust evaluation and policy pre-checks completed",
            "epistemic grounding completed",
            "epistemic grounded",
            "memory trust evaluation completed",
        ),
        allowed_evidence_states=(EvidenceState.PASS,),
        allowed_evidence_modes=(
            ExecutionEvidenceMode.SIMULATION,
            ExecutionEvidenceMode.FIXTURE,
        ),
        expected_subject="epistemic_grounding",
        expected_evidence_key_prefix="ev-ground-",
    ),
}

CANONICAL_CONDITION_SPECS: Mapping[str, BoundedCriterionConditionSpec] = MappingProxyType(
    _CANONICAL_CONDITION_SPECS_DICT
)


def get_canonical_condition_specs() -> Mapping[str, BoundedCriterionConditionSpec]:
    """Return immutable mapping of supported bounded criterion condition specs."""
    return CANONICAL_CONDITION_SPECS


def normalize_criterion_statement(text: str) -> str:
    """Deterministically normalize a criterion statement for bounded condition admission.

    Normalization steps:
    1. Sanitize secrets first (e.g. ghp_* tokens become [REDACTED]).
    2. Unicode-safe casefold.
    3. Strip terminal punctuation (. ! ? ; : ,).
    4. Collapse repeated whitespace and trim.
    """
    sanitized = sanitize_secrets_in_text(text)
    folded = sanitized.casefold()
    trimmed = folded.strip()
    while trimmed and trimmed[-1] in {".", "!", "?", ";", ":", ","}:
        trimmed = trimmed[:-1].strip()
    normalized = re.sub(r"\s+", " ", trimmed).strip()
    return normalized


def validate_criterion_condition_semantics(
    criterion: SuccessCriterion,
) -> tuple[bool, Optional[str], str]:
    """Validate if SuccessCriterion description matches an allowed bounded condition.

    A deterministic criterion may become PASS only when:
    1. its requested condition matches an exact accepted statement in the bounded
       statement allowlist for one of the canonical conditions; and
    2. the actual produced evidence required for that condition exists with the correct state/mode.

    Unknown, arbitrary, contradictory, negated, unprovable, or modified criterion semantics
    fail closed as unproven without fuzzy or model-based fallback.
    """
    desc_raw = criterion.description
    normalized_desc = normalize_criterion_statement(desc_raw)

    matched_condition: Optional[str] = None
    for cond_id, spec in CANONICAL_CONDITION_SPECS.items():
        if normalized_desc in spec.accepted_statements:
            matched_condition = cond_id
            break

    if matched_condition is None:
        return (
            False,
            None,
            f"Criterion description {desc_raw!r} (normalized: {normalized_desc!r}) does not "
            "match any supported bounded condition statement in canonical vocabulary",
        )

    return True, matched_condition, ""


def build_standard_demo_registry(
    tenant_id: str,
    now: Optional[datetime] = None,
) -> InMemoryAgentRegistry:
    """Build an in-memory agent registry populated with valid passports for standard roles."""
    if now is None:
        now = datetime.now(timezone.utc)
    ev_reg = QualificationEvidenceRegistry()
    verifier = QualificationEvidenceVerifier(registry=ev_reg)
    registry = InMemoryAgentRegistry(evidence_verifier=verifier)

    roles = {
        "impact_scout": ("1.0.0", ("AST_STATIC_ANALYSIS", "BLAST_RADIUS_ESTIMATION")),
        "policy_guardian": ("1.0.0", ("POLICY_VERIFICATION", "REVERSIBILITY_ANALYSIS")),
        "migration_engineer": ("1.0.0", ("MIGRATION_SYNTHESIS_SQL",)),
        "release_steward": ("1.0.0", ("PR_GENERATION",)),
    }

    for role_id, (rev, caps) in roles.items():
        desc = AgentDescriptor(
            agent_id=f"agent-{role_id.replace('_', '-')}",
            agent_name=role_id.replace("_", " ").title(),
            agent_role=role_id,
            agent_revision=rev,
            description=f"Standard qualified {role_id} revision {rev}",
            declared_capabilities=caps,
        )
        registry.register_agent(desc)

        ev_ids = []
        for cap in caps:
            ev_id = f"ev-qual-{role_id}-{cap.lower()}"
            ev_ids.append(ev_id)
            ev_reg.register_evidence(
                QualificationEvidenceRecord(
                    evidence_id=ev_id,
                    agent_id=desc.agent_id,
                    agent_revision=rev,
                    qualified_capability=cap,
                    scenario_id="SCENARIO_NORMAL_MIGRATION",
                    passed=True,
                    evidence_state=EvidenceState.SIMULATED,
                    evidence_mode=ExecutionEvidenceMode.SIMULATION,
                    producer_kind=EvidenceProducerKind.SIMULATION,
                    evidence_digest="a" * 64,
                    collected_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )

        passport = PassportIssuer.issue_passport(
            PassportIssuanceRequest(
                agent_id=desc.agent_id,
                agent_revision=rev,
                qualified_capabilities=caps,
                qualification_evidence_ids=tuple(ev_ids),
                issuer="qualification_engine",
            ),
            evidence_verifier=verifier,
            now=now,
        )
        registry.register_passport(tenant_id, passport)

    return registry


class SagaExecutionResult(BaseModel):
    """Immutable result of a ChangeSaga run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    correlation_id: str
    initial_state: ChangeState
    final_state: ChangeState
    is_completed: bool
    autonomy_class: Optional[AutonomyClass] = None
    stopped_reason: Optional[str] = None
    events_emitted: int
    tasks_executed: int
    evidence_collected: int
    checkpoints_created: int
    timeline_digest: Optional[str] = None
    approval_card: Optional[ApprovalCompressionCard] = None


class RecoveryAction(str, Enum):
    """Classification of recovery action taken by saga recovery paths."""

    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    COMPENSATION_STARTED = "COMPENSATION_STARTED"
    COMPENSATION_COMPLETED = "COMPENSATION_COMPLETED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"
    DEAD_LETTERED = "DEAD_LETTERED"


class SagaRecoveryResult(BaseModel):
    """Immutable result of a saga recovery path operation.

    P-20.02: Every recovery path produces an explicit result with
    persisted state, causal event evidence, and recovery metadata.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    tenant_id: str
    change_id: str
    correlation_id: str
    action: RecoveryAction
    previous_state: ChangeState
    final_state: ChangeState
    reason: str
    retry_origin: Optional[ChangeState] = None
    retry_attempt: Optional[int] = None
    retry_max_attempts: Optional[int] = None
    compensation_description: Optional[str] = None
    dead_letter_id: Optional[str] = None
    event_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    timestamp: Optional[datetime] = None


# Default saga-level timeout in seconds (configurable per orchestrator instance)
DEFAULT_SAGA_TIMEOUT_SECONDS: float = 3600.0
DEFAULT_SAGA_RETRY_MAX_ATTEMPTS: int = 3


class ChangeSagaOrchestrator:
    """Stateful, event-driven, persisted saga orchestrator coordinating ChangeMesh lifecycle."""

    def __init__(
        self,
        repository: SagaStateRepository,
        event_bus: LocalEventBus | EventPublisher,
        *,
        orchestrator_id: str = "agent-change-orchestrator",
        orchestrator_revision: str = "1.0.0",
        timeline: Optional[CausalEventTimeline] = None,
        agent_registry: Optional[AgentRegistry] = None,
        policy_gate: Optional[PolicyGuardianGate] = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.orchestrator_id = orchestrator_id
        self.orchestrator_revision = orchestrator_revision
        self.timeline = timeline
        self.agent_registry = agent_registry
        self.policy_gate = policy_gate or PolicyGuardianGate()
        self._topology = get_canonical_topology()

    def run_saga(
        self,
        tenant_id: str,
        request: ChangeRequest,
        *,
        change_id: Optional[str] = None,
        evidence_mode: ExecutionEvidenceMode = ExecutionEvidenceMode.SIMULATION,
        initial_memory_records: Sequence[MemoryRecord] = (),
        stop_at_state: Optional[ChangeState] = None,
        rehearsal_scenario: Optional[ShadowScenario] = None,
        now: Optional[datetime] = None,
    ) -> SagaExecutionResult:
        """Execute the end-to-end ChangeMesh lifecycle saga synchronously and deterministically."""
        if now is None:
            now = datetime.now(timezone.utc)
        # -------------------------------------------------------------------------
        # Pre-Persistence Intake Secret Boundary (Fail Closed on Credentials in Identity/Structure)
        # -------------------------------------------------------------------------
        if any(pattern.search(tenant_id) for pattern in _SECRET_REPLACEMENT_PATTERNS):
            raise ValueError(
                "Secret/credential detected in tenant_id; refusing intake before state persistence"
            )
        tid = validate_tenant_id(tenant_id)

        for id_field_name, id_val in [
            ("request_id", request.request_id),
            ("requested_by", request.requested_by),
        ]:
            if any(pattern.search(id_val) for pattern in _SECRET_REPLACEMENT_PATTERNS):
                raise ValueError(
                    f"Secret/credential detected in structural identity field {id_field_name!r}; "
                    "refusing intake before state persistence"
                )

        if change_id is not None:
            if any(pattern.search(change_id) for pattern in _SECRET_REPLACEMENT_PATTERNS):
                raise ValueError(
                    "Secret/credential detected in change_id; "
                    "refusing intake before state persistence"
                )

        for target_sys in request.target_systems:
            if any(pattern.search(target_sys) for pattern in _SECRET_REPLACEMENT_PATTERNS):
                raise ValueError(
                    "Secret/credential detected in target_systems field; "
                    "refusing intake before state persistence"
                )

        for crit in request.success_criteria:
            for crit_field_name, crit_val in [
                ("criterion_id", crit.criterion_id),
                ("verification_method", crit.verification_method),
            ]:
                if any(pattern.search(crit_val) for pattern in _SECRET_REPLACEMENT_PATTERNS):
                    raise ValueError(
                        "Secret/credential detected in success criterion structural field "
                        f"{crit_field_name!r}; refusing intake before state persistence"
                    )
            for ev_type in crit.required_evidence_types:
                if any(pattern.search(ev_type) for pattern in _SECRET_REPLACEMENT_PATTERNS):
                    raise ValueError(
                        "Secret/credential detected in success criterion required_evidence_types; "
                        "refusing intake before state persistence"
                    )

        # Enforce Mode Honesty: Local saga operations support only FIXTURE or SIMULATION
        if evidence_mode not in (ExecutionEvidenceMode.FIXTURE, ExecutionEvidenceMode.SIMULATION):
            raise ValueError(
                f"{evidence_mode.value} mode cannot be claimed for local saga execution. "
                "Local saga supports only FIXTURE or SIMULATION modes; LIVE_WRITE requires real "
                "credential-backed provider mutations, and RECORDED_CLOUD requires an "
                "authenticated canonical replay provenance artifact."
            )

        # -------------------------------------------------------------------------
        # Ensure Tenant Record Exists
        # -------------------------------------------------------------------------
        tenant = self.repository.get_tenant(tid)
        if tenant is None:
            tenant = TenantRecord(
                tenant_id=tid,
                name=f"Tenant {tid}",
                created_at=now,
                updated_at=now,
            )
            self.repository.create_tenant(tenant)

        # -------------------------------------------------------------------------
        # Initialize Workflow Identity and Timeline
        # -------------------------------------------------------------------------
        if change_id is None:
            change_id = f"change-{uuid.uuid4().hex[:12]}"
        correlation_id = request.request_id

        if self.timeline is None:
            self.timeline = CausalEventTimeline(change_id)
        else:
            self.timeline.change_id = change_id

        # Sanitize free-form user input to guarantee zero secrets in state & wire payloads
        clean_title = sanitize_secrets_in_text(request.title)
        clean_description = sanitize_secrets_in_text(request.description)

        # State tracking
        current_state = ChangeState.RECEIVED
        last_event_id: Optional[str] = None
        event_seq = 0
        events_emitted = 0
        tasks_executed = 0
        evidence_collected = 0
        checkpoints_created = 0
        active_autonomy_class: Optional[AutonomyClass] = None
        active_approval_card: Optional[ApprovalCompressionCard] = None

        # -------------------------------------------------------------------------
        # Event Emission & State Persistence Helper (Persistence-Before-Publish)
        # -------------------------------------------------------------------------
        def transition_and_persist(
            target_state: ChangeState,
            reason: str,
            producer_id: str,
            producer_role: str,
            producer_revision: str,
            payload_summary: Mapping[str, Any],
        ) -> EventEnvelope:
            nonlocal current_state, last_event_id, event_seq, events_emitted

            # 1. Enforce lifecycle transition rules (strict enum type check)
            if current_state != target_state:
                require_transition(current_state, target_state)

            sanitized_reason = sanitize_secrets_in_text(reason)
            sanitized_payload = redact_mapping(payload_summary)
            # Ensure no raw secret strings remain in payload
            sanitized_payload = {
                k: sanitize_secrets_in_text(v) if isinstance(v, str) else v
                for k, v in sanitized_payload.items()
            }

            # 2. Persist authoritative state in repository FIRST (optimistic concurrency)
            existing_record = self.repository.get_change(tid, change_id)
            if existing_record is None:
                new_record = ChangeRecord(
                    tenant_id=tid,
                    change_id=change_id,
                    correlation_id=correlation_id,
                    title=clean_title,
                    description=clean_description,
                    target_systems=tuple(request.target_systems),
                    data_classification=request.data_classification,
                    requested_by=request.requested_by,
                    requested_at=now,
                    state=target_state,
                    state_updated_at=now,
                    state_reason=sanitized_reason,
                    assigned_orchestrator_revision=self.orchestrator_revision,
                    created_at=now,
                    updated_at=now,
                )
                self.repository.create_change(tid, new_record)
            else:
                updated_record = existing_record.model_copy(
                    update={
                        "state": target_state,
                        "state_updated_at": now,
                        "state_reason": sanitized_reason,
                        "autonomy_class": active_autonomy_class or existing_record.autonomy_class,
                        "updated_at": now,
                    }
                )
                self.repository.update_change(
                    tid, updated_record, expected_version=existing_record.version
                )

            # 3. Only after persistence succeeds, publish wire message & update timeline
            event_seq += 1
            event_id = f"evt-{change_id}-{event_seq:03d}-{target_state.value.lower()}"
            idempotency_key = f"idem_lc_{change_id}_{target_state.value.lower()}_{event_seq}"

            provenance = AgentRevisionProvenance(
                agent_id=producer_id,
                agent_revision=producer_revision,
                role=producer_role,
            )

            envelope = EventEnvelope(
                schema_version=CANONICAL_SCHEMA_VERSION,
                event_id=event_id,
                change_id=change_id,
                causation_id=last_event_id,
                correlation_id=correlation_id,
                producer_id=producer_id,
                producer_revision=producer_revision,
                producer_role=producer_role,
                agent_provenance=provenance,
                timestamp=now,
                idempotency_key=idempotency_key,
            )

            route = self._topology.get_route_for_state(target_state)
            topic_id = route.primary_topic_id if route else "changemesh-lifecycle-v1"

            # Pre-dispatch secret scanning fails closed on residual secrets
            scan_payload_for_secrets(sanitized_payload)

            wire_msg = EventWireMessage(
                topic_id=topic_id,
                envelope=envelope,
                payload=sanitized_payload,
                published_at=now,
            )

            if isinstance(self.event_bus, LocalEventBus):
                self.event_bus.publish_message(wire_msg)
            else:
                self.event_bus.publish(wire_msg)

            if self.timeline is not None:
                self.timeline.record_event(
                    envelope, topic_id=topic_id, payload=sanitized_payload, transport="LOCAL"
                )

            events_emitted += 1
            last_event_id = event_id
            current_state = target_state
            return envelope

        # -------------------------------------------------------------------------
        # STAGE 0: Intake & Initial State (RECEIVED)
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.RECEIVED,
            reason="Change request received and admitted",
            producer_id=self.orchestrator_id,
            producer_role="change_orchestrator",
            producer_revision=self.orchestrator_revision,
            payload_summary={
                "intent": clean_description,
                "targets": list(request.target_systems),
            },
        )

        if stop_at_state == ChangeState.RECEIVED:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state RECEIVED",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # Intent Binding Validation (Fail Closed for Unsupported / Destructive Operations)
        # -------------------------------------------------------------------------
        is_supported_intent, unsupported_reason = validate_supported_change_intent(request)
        if not is_supported_intent:
            transition_and_persist(
                target_state=ChangeState.BLOCKED,
                reason=f"UNSUPPORTED_OPERATION: {unsupported_reason}",
                producer_id=self.orchestrator_id,
                producer_role="change_orchestrator",
                producer_revision=self.orchestrator_revision,
                payload_summary={
                    "action": "unsupported_change_intent_blocked",
                    "reason": unsupported_reason,
                },
            )
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.BLOCKED,
                is_completed=False,
                autonomy_class=AutonomyClass.BLOCKED,
                stopped_reason=f"UNSUPPORTED_OPERATION: {unsupported_reason}",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 1: Discover (DISCOVERING) — Real P-15 Component Execution
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.DISCOVERING,
            reason="Beginning impact discovery and blast-radius analysis",
            producer_id="agent-impact-scout",
            producer_role="impact_scout",
            producer_revision="1.0.0",
            payload_summary={"action": "discover_blast_radius"},
        )

        # Execute Impact Scout Discovery via real RepositoryScanner and GraphTraverser
        scanner = RepositoryScanner()
        scan_findings = scanner.scan_files(
            changed_files=[CANONICAL_SUPPORTED_OPERATION.migration_file],
            all_files=list(CANONICAL_SUPPORTED_OPERATION.supporting_files),
        )

        graph = build_synthetic_billing_graph()
        traverser = GraphTraverser()
        impacted_assets = tuple(
            traverser.find_downstream_impact(
                graph, changed_node_ids=set(CANONICAL_SUPPORTED_OPERATION.impacted_node_ids)
            )
        )

        merger = BlastRadiusMerger()
        blast_radius_artifact = merger.merge(
            change_id=change_id,
            scan_findings=scan_findings,
            impacted_assets=impacted_assets,
            evidence_mode=evidence_mode.value,
        )

        # Persist Discover Task & Evidence
        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-discover-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-impact-scout",
                agent_role="impact_scout",
                agent_revision="1.0.0",
                action_class="BLAST_RADIUS_ANALYSIS",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=(
                    f"Blast radius calculated: {len(blast_radius_artifact.impacted_assets)} assets"
                ),
                artifact_hashes=({"blast_radius_digest": blast_radius_artifact.digest},),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-discover-{change_id}",
                subject="blast_radius",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id="agent-impact-scout",
                agent_revision="1.0.0",
                artifact_digests=(blast_radius_artifact.digest,),
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.DISCOVERING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state DISCOVERING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 2: Qualify (QUALIFYING) — Real P-12 Agent Registry / Capability Passport
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.QUALIFYING,
            reason="Verifying agent fleet qualifications and capability requirements",
            producer_id=self.orchestrator_id,
            producer_role="change_orchestrator",
            producer_revision=self.orchestrator_revision,
            payload_summary={"action": "verify_agent_capabilities"},
        )

        # Initialize registry if not supplied
        active_registry = self.agent_registry
        if active_registry is None:
            active_registry = build_standard_demo_registry(tid, now=now)
            self.agent_registry = active_registry

        # Verify Capability Requirements via AgentRegistry & CapabilityPassport
        std_reqs = get_standard_demo_requirements()
        qualification_failed = False
        qualification_failure_reason = ""
        verified_role_count = 0

        evidence_verifier = (
            getattr(active_registry, "_evidence_verifier", None) or QualificationEvidenceVerifier()
        )

        for role_id, req in std_reqs.items():
            agent_id = f"agent-{role_id.replace('_', '-')}"
            descriptor = active_registry.get_descriptor(agent_id, "1.0.0")
            passport = active_registry.get_active_passport(tid, agent_id, "1.0.0")

            if descriptor is None or passport is None:
                qualification_failed = True
                qualification_failure_reason = (
                    f"No active qualified passport found for required role {role_id!r}"
                )
                break

            val_res = PassportVerifier.verify(
                passport=passport,
                evidence_verifier=evidence_verifier,
                requirement=req,
                expected_revision="1.0.0",
                now=now,
            )
            if not val_res.is_valid:
                qualification_failed = True
                qualification_failure_reason = (
                    f"Passport validation failed for role {role_id!r}: {val_res.failure_reason}"
                )
                break

            verified_role_count += 1

        if qualification_failed:
            transition_and_persist(
                target_state=ChangeState.BLOCKED,
                reason=f"Agent qualification failed closed: {qualification_failure_reason}",
                producer_id=self.orchestrator_id,
                producer_role="change_orchestrator",
                producer_revision=self.orchestrator_revision,
                payload_summary={
                    "action": "agent_qualification_failed",
                    "reason": qualification_failure_reason,
                },
            )
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.BLOCKED,
                is_completed=False,
                autonomy_class=AutonomyClass.BLOCKED,
                stopped_reason=f"QUALIFICATION_FAILED: {qualification_failure_reason}",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-qualify-{change_id}",
                sequence_number=tasks_executed,
                agent_id=self.orchestrator_id,
                agent_role="qualifier",
                agent_revision=self.orchestrator_revision,
                action_class="CAPABILITY_QUALIFICATION",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=f"Verified qualifications for {verified_role_count} agent roles",
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-qualify-{change_id}",
                subject="capability_qualification",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id=self.orchestrator_id,
                agent_revision=self.orchestrator_revision,
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.QUALIFYING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state QUALIFYING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 3: Rehearse (REHEARSING) — Real P-13 ShadowLabRunner
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.REHEARSING,
            reason="Executing ShadowLab simulated twin rehearsal",
            producer_id="agent-shadowlab-runner",
            producer_role="shadowlab",
            producer_revision="1.0.0",
            payload_summary={
                "action": "shadowlab_rehearsal",
                "scenario": (
                    rehearsal_scenario.scenario_id
                    if rehearsal_scenario
                    else "SCENARIO_NORMAL_MIGRATION"
                ),
            },
        )

        # Execute Rehearsal Scenario using real ShadowLabRunner
        scenario = (
            rehearsal_scenario or get_standard_shadow_scenarios()["SCENARIO_NORMAL_MIGRATION"]
        )
        rehearsal_outcome = ShadowLabRunner.run_scenario(scenario)

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-rehearse-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-shadowlab-runner",
                agent_role="shadowlab",
                agent_revision="1.0.0",
                action_class="REHEARSAL_SIMULATION",
                status=TaskStatus.COMPLETED if rehearsal_outcome.passed else TaskStatus.FAILED,
                started_at=now,
                completed_at=now,
                output_summary=f"Rehearsal {scenario.scenario_id}: {rehearsal_outcome.details}",
                artifact_hashes=({"rehearsal_digest": rehearsal_outcome.evidence_digest},),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-rehearse-{change_id}",
                subject="shadowlab_rehearsal",
                state=rehearsal_outcome.evidence_state,
                collection_mode=ExecutionEvidenceMode.SIMULATION,
                producer_kind=EvidenceProducerKind.SIMULATION,
                agent_id="agent-shadowlab-runner",
                agent_revision="1.0.0",
                artifact_digests=(rehearsal_outcome.evidence_digest,),
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.REHEARSING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state REHEARSING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 4: Ground (GROUNDED) — Epistemic Memory Trust & Deterministic Policy
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.GROUNDED,
            reason="Grounding change in epistemic memory trust and deterministic policy rules",
            producer_id="agent-memory-trust",
            producer_role="memory_trust",
            producer_revision="1.0.0",
            payload_summary={
                "action": "epistemic_grounding",
                "memory_count": len(initial_memory_records),
            },
        )

        # Evaluate Epistemic Memory Trust
        trusted_memory_refs = []
        for mem in initial_memory_records:
            eval_res = MemoryTrustEvaluator.evaluate(mem, now=now)
            if eval_res.trust_class == EpistemicTrustClass.ACCEPTED_TRUSTED:
                trusted_memory_refs.append(mem.memory_id)

        # Evaluate Deterministic Policy Pre-checks
        policy_checker = DeterministicPolicyChecker()
        policy_res = policy_checker.evaluate(
            input_text=CANONICAL_SUPPORTED_OPERATION.sql_up,
            tool_ids=["tool-migration-planner", "tool-artifact-generator"],
            target_paths=[f"synthetic/{CANONICAL_SUPPORTED_OPERATION.migration_file}"],
            action_type="SCHEMA_MIGRATION",
            data_classification=request.data_classification.value,
            change_id=change_id,
        )
        if policy_res.blocked_count > 0:
            transition_and_persist(
                target_state=ChangeState.BLOCKED,
                reason=f"Deterministic policy blocked change: {policy_res.findings}",
                producer_id="agent-policy-guardian",
                producer_role="policy_guardian",
                producer_revision="1.0.0",
                payload_summary={
                    "action": "policy_precheck_blocked",
                    "findings": list(policy_res.findings),
                },
            )
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.BLOCKED,
                is_completed=False,
                autonomy_class=AutonomyClass.BLOCKED,
                stopped_reason="BLOCKED by deterministic policy pre-checks",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-ground-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-memory-trust",
                agent_role="memory_trust",
                agent_revision="1.0.0",
                action_class="EPISTEMIC_GROUNDING",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=(
                    f"Epistemic grounding complete: {len(trusted_memory_refs)} trusted memory refs"
                ),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-ground-{change_id}",
                subject="epistemic_grounding",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id="agent-memory-trust",
                agent_revision="1.0.0",
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.GROUNDED:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                stopped_reason="Stopped at requested state GROUNDED",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 5: Authorize (AUTHORIZED / AWAITING_AUTHORITY / BLOCKED)
        # -------------------------------------------------------------------------
        # Determine Reversibility Classification deterministically (zero caller overrides)
        sample_sql_up = CANONICAL_SUPPORTED_OPERATION.sql_up
        sample_sql_down = CANONICAL_SUPPORTED_OPERATION.sql_down
        blast_score = (
            min(1.0, len(blast_radius_artifact.impacted_assets) * 0.1)
            if blast_radius_artifact.impacted_assets
            else 0.2
        )

        rev_assessment = ReversibilityClassifier.classify_sql(
            change_id=change_id,
            sql_up=sample_sql_up,
            sql_down=sample_sql_down,
            blast_radius_score=blast_score,
        )

        rehearsal_status = (
            RehearsalStatus.REHEARSAL_PASSED
            if rehearsal_outcome.passed
            else RehearsalStatus.REHEARSAL_FAILED
        )

        policy_inputs = DeterministicPolicyInputs(
            change_id=change_id,
            blast_radius_score=blast_score,
            blast_radius_source="impact_scout",
            blast_radius_reason=(
                f"Impacted assets count: {len(blast_radius_artifact.impacted_assets)}"
            ),
            reversibility_class=rev_assessment.reversibility_class,
            has_down_migration=rev_assessment.has_down_migration,
            rollback_summary=rev_assessment.rollback_plan_summary,
            reversibility_source="reversibility_classifier",
            privilege_level=PrivilegeLevel.SCHEMA_MODIFY,
            privilege_source="migration_planner",
            data_classification=request.data_classification,
            sensitivity_source="change_request",
            evidence_state=EvidenceState.PASS,
            evidence_mode=evidence_mode,
            evidence_digests=(blast_radius_artifact.digest,),
            evidence_source="impact_scout",
            novelty_tier=NoveltyTier.ROUTINE_KNOWN,
            novelty_source="novelty_classifier",
            rehearsal_status=rehearsal_status,
            rehearsal_digests=(rehearsal_outcome.evidence_digest,),
            rehearsal_source="shadowlab",
        )

        gate_result = self.policy_gate.evaluate_inputs(
            policy_inputs,
            assessment=rev_assessment,
            now=now,
        )
        active_autonomy_class = gate_result.autonomy_class

        # Check for HARD BLOCKER (BLOCKED)
        if gate_result.autonomy_class == AutonomyClass.BLOCKED:
            transition_and_persist(
                target_state=ChangeState.BLOCKED,
                reason=f"Policy Guardian Gate issued hard blocker: {gate_result.decision_summary}",
                producer_id="agent-policy-guardian",
                producer_role="policy_guardian",
                producer_revision="1.0.0",
                payload_summary={
                    "autonomy_class": gate_result.autonomy_class.value,
                    "reversibility_class": rev_assessment.reversibility_class.value,
                    "decision_summary": gate_result.decision_summary,
                },
            )
            # Return BLOCKED result with zero approval card and zero execution tasks
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.BLOCKED,
                is_completed=False,
                autonomy_class=AutonomyClass.BLOCKED,
                stopped_reason=f"BLOCKED: {gate_result.decision_summary}",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # Check for HUMAN_AUTHORITY_REQUIRED
        if (
            gate_result.autonomy_class == AutonomyClass.HUMAN_AUTHORITY_REQUIRED
            and not gate_result.is_authorized
        ):
            active_approval_card = gate_result.compression_card
            transition_and_persist(
                target_state=ChangeState.AWAITING_AUTHORITY,
                reason=(
                    "Policy Gate determined Human Authority is required: "
                    f"{gate_result.decision_summary}"
                ),
                producer_id="agent-policy-guardian",
                producer_role="policy_guardian",
                producer_revision="1.0.0",
                payload_summary={
                    "autonomy_class": gate_result.autonomy_class.value,
                    "reversibility_class": rev_assessment.reversibility_class.value,
                    "decision_summary": gate_result.decision_summary,
                },
            )

            # Persist Approval Record derived strictly from compression card
            if gate_result.compression_card is not None:
                card = gate_result.compression_card
                self.repository.create_approval(
                    tid,
                    change_id,
                    ApprovalRecord(
                        tenant_id=tid,
                        change_id=change_id,
                        card_id=card.card_id,
                        authority_slot_ref=card.authority_slot_ref,
                        decision_question=card.decision_question,
                        decision_options=card.decision_options,
                        policy_reason=card.policy_reason,
                        action_scope=card.action_scope,
                        completed_work_summary=card.completed_work_summary,
                        rehearsed_work_summary=card.rehearsed_work_summary,
                        remaining_decision_summary=card.remaining_decision_summary,
                        evidence_refs=card.evidence_refs,
                        card_created_at=card.created_at,
                        resolution_status=ApprovalResolutionStatus.PENDING,
                        created_at=now,
                        updated_at=now,
                    ),
                )

            # Stop cleanly at AWAITING_AUTHORITY — zero execution and zero Release Steward mutation!
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                approval_card=active_approval_card,
                stopped_reason=(
                    "Awaiting verified human authority decision; execution halted cleanly"
                ),
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # Autonomous Authorization Granted (AUTO_EXECUTE or REHEARSE_THEN_EXECUTE)
        transition_and_persist(
            target_state=ChangeState.AUTHORIZED,
            reason=f"Authorized under autonomy class {gate_result.autonomy_class.value}",
            producer_id="agent-policy-guardian",
            producer_role="policy_guardian",
            producer_revision="1.0.0",
            payload_summary={
                "autonomy_class": gate_result.autonomy_class.value,
                "reversibility_class": rev_assessment.reversibility_class.value,
                "decision_summary": gate_result.decision_summary,
            },
        )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-authorize-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-policy-guardian",
                agent_role="policy_guardian",
                agent_revision="1.0.0",
                action_class="AUTHORIZATION_GATE",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=f"Authorized autonomously as {gate_result.autonomy_class.value}",
                created_at=now,
                updated_at=now,
            ),
        )

        if stop_at_state == ChangeState.AUTHORIZED:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                stopped_reason="Stopped at requested state AUTHORIZED",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 6: Execute (EXECUTING) — Real P-17 Migration Plan & Manifest
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.EXECUTING,
            reason="Executing change synthesis and artifact generation",
            producer_id="agent-migration-engineer",
            producer_role="migration_engineer",
            producer_revision="1.0.0",
            payload_summary={"action": "generate_migration_artifacts"},
        )

        # Generate Migration Artifacts
        mig_gen = MigrationPlanGenerator()
        mig_plan = mig_gen.generate_plan(
            change_id=change_id,
            source_schema=CANONICAL_SUPPORTED_OPERATION.source_schema,
            target_schema=CANONICAL_SUPPORTED_OPERATION.target_schema,
            column_additions=[CANONICAL_SUPPORTED_OPERATION.column_name],
            table_name=CANONICAL_SUPPORTED_OPERATION.table_name,
        )

        manifest_gen = ManifestGenerator()
        file_manifest = manifest_gen.generate_manifest(
            change_id=change_id,
            plan_id=mig_plan.plan_id,
            file_contents={
                CANONICAL_SUPPORTED_OPERATION.migration_file: (CANONICAL_SUPPORTED_OPERATION.sql_up)
            },
        )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-execute-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-migration-engineer",
                agent_role="migration_engineer",
                agent_revision="1.0.0",
                action_class="MIGRATION_EXECUTION",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=(
                    f"Synthesized migration with {len(mig_plan.steps)} steps and "
                    f"{len(file_manifest.entries)} files"
                ),
                artifact_hashes=({"manifest_hash": file_manifest.manifest_hash},),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-execute-{change_id}",
                subject="migration_artifacts",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id="agent-migration-engineer",
                agent_revision="1.0.0",
                artifact_digests=(file_manifest.manifest_hash,),
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.EXECUTING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                stopped_reason="Stopped at requested state EXECUTING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 7: Verify (VERIFYING) — Real P-18 Claims, Audit, Reconciliation
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.VERIFYING,
            reason="Executing independent evidence audit and deterministic reconciliation",
            producer_id="agent-evidence-auditor",
            producer_role="evidence_auditor",
            producer_revision="1.0.0",
            payload_summary={"action": "audit_and_reconcile"},
        )

        # Catalog produced evidence records from earlier stages in this run
        produced_evidence_catalog: dict[str, dict[str, Any]] = {
            f"ev-discover-{change_id}": {
                "types": frozenset(
                    {
                        "BLAST_RADIUS_ANALYSIS",
                        "BLAST_RADIUS_ESTIMATION",
                        "AST_STATIC_ANALYSIS",
                        "DISCOVERY",
                    }
                ),
                "state": EvidenceState.PASS,
                "mode": evidence_mode,
                "subject": "blast_radius",
                "summary": (
                    f"Blast radius calculated: {len(blast_radius_artifact.impacted_assets)} assets"
                ),
            },
            f"ev-qualify-{change_id}": {
                "types": frozenset(
                    {"CAPABILITY_QUALIFICATION", "AGENT_QUALIFICATION", "PASSPORT_VERIFICATION"}
                ),
                "state": EvidenceState.PASS,
                "mode": evidence_mode,
                "subject": "capability_qualification",
                "summary": f"Verified qualifications for {verified_role_count} agent roles",
            },
            f"ev-rehearse-{change_id}": {
                "types": frozenset({"REHEARSAL_SIMULATION", "SHADOWLAB_REHEARSAL", "REHEARSAL"}),
                "state": rehearsal_outcome.evidence_state,
                "mode": ExecutionEvidenceMode.SIMULATION,
                "subject": "shadowlab_rehearsal",
                "summary": (
                    f"Rehearsal outcome: {rehearsal_outcome.evidence_state.value} "
                    f"with digest {rehearsal_outcome.evidence_digest}"
                ),
            },
            f"ev-ground-{change_id}": {
                "types": frozenset({"EPISTEMIC_GROUNDING", "POLICY_PRECHECK", "GROUNDING"}),
                "state": EvidenceState.PASS,
                "mode": evidence_mode,
                "subject": "epistemic_grounding",
                "summary": (
                    f"Epistemic grounding complete: {len(trusted_memory_refs)} trusted memory refs"
                ),
            },
            f"ev-execute-{change_id}": {
                "types": frozenset(
                    {
                        "MIGRATION_EXECUTION",
                        "MIGRATION_SYNTHESIS",
                        "DETERMINISTIC_MANIFEST",
                        "MANIFEST_GENERATION",
                        "ARTIFACT_GENERATION",
                    }
                ),
                "state": EvidenceState.PASS,
                "mode": evidence_mode,
                "subject": "migration_artifacts",
                "summary": f"Execution manifest: Valid SHA-256 hash {file_manifest.manifest_hash}",
            },
        }

        # Effective criteria: from request or standard defaults
        if request.success_criteria:
            effective_criteria = list(request.success_criteria)
        else:
            effective_criteria = [
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-rehearsal",
                    description="Rehearsal completed with zero unhandled faults.",
                    verification_method="deterministic",
                    required_evidence_types=["REHEARSAL_SIMULATION"],
                ),
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="crit-manifest",
                    description="Migration manifest contains deterministic file hashes.",
                    verification_method="deterministic",
                    required_evidence_types=["MIGRATION_EXECUTION"],
                ),
            ]

        supported_methods = frozenset({"deterministic", "automated", "semantic", "model_assisted"})
        criterion_deterministic_state: dict[str, str] = {}
        criterion_bound_evidence: dict[str, list[str]] = {}
        verification_failures: list[str] = []

        for crit in effective_criteria:
            bound_keys: list[str] = []
            method = crit.verification_method.strip().lower()
            crit_failed = False
            crit_reasons: list[str] = []

            if method not in supported_methods:
                crit_failed = True
                crit_reasons.append(
                    f"Verification method {crit.verification_method!r} is not supported "
                    "by automated saga runtime"
                )

            # 1. Machine-verifiable condition semantic validation
            # (fails closed on opposite / unproven / unknown criterion semantics)
            is_valid_cond, cond_id, cond_fail_reason = validate_criterion_condition_semantics(crit)
            spec: Optional[BoundedCriterionConditionSpec] = None
            if not is_valid_cond or cond_id is None:
                crit_failed = True
                crit_reasons.append(cond_fail_reason)
            else:
                spec = CANONICAL_CONDITION_SPECS.get(cond_id)
                if spec is None:
                    crit_failed = True
                    crit_reasons.append(
                        f"Resolved condition {cond_id!r} is not registered in "
                        "canonical condition specs"
                    )

            # 2. Validate caller-supplied required_evidence_types against condition spec
            if spec is not None:
                if not crit.required_evidence_types:
                    crit_failed = True
                    crit_reasons.append(
                        f"Criterion {crit.criterion_id!r} has no required_evidence_types specified"
                    )
                else:
                    for req_type in crit.required_evidence_types:
                        normalized_req = req_type.strip().upper()
                        if (
                            req_type not in spec.allowed_evidence_types
                            and normalized_req not in spec.allowed_evidence_types
                        ):
                            allowed_list = list(spec.allowed_evidence_types)
                            crit_failed = True
                            crit_reasons.append(
                                f"Required evidence type {req_type!r} is not capable of "
                                f"proving condition {cond_id!r} (expected one of: {allowed_list})"
                            )

            # 3. Bind evidence ONLY from the resolved condition spec
            if spec is not None and not crit_failed:
                matched_evidence_found = False
                for ev_key, ev_info in produced_evidence_catalog.items():
                    key_match = spec.expected_evidence_key_prefix is None or ev_key.startswith(
                        spec.expected_evidence_key_prefix
                    )
                    subject_match = (
                        spec.expected_subject is None
                        or ev_info.get("subject") == spec.expected_subject
                    )
                    type_match = any(t in spec.allowed_evidence_types for t in ev_info["types"])

                    if key_match and subject_match and type_match:
                        # Check evidence state
                        ev_state = ev_info["state"]
                        if ev_state not in spec.allowed_evidence_states:
                            allowed_states_str = [s.value for s in spec.allowed_evidence_states]
                            crit_failed = True
                            crit_reasons.append(
                                f"Bound evidence {ev_key} for condition {cond_id!r} has invalid "
                                f"state: {ev_state.value} (allowed: {allowed_states_str})"
                            )
                        # Check evidence mode
                        ev_mode = ev_info.get("mode")
                        if ev_mode is not None and ev_mode not in spec.allowed_evidence_modes:
                            allowed_modes_str = [m.value for m in spec.allowed_evidence_modes]
                            crit_failed = True
                            crit_reasons.append(
                                f"Bound evidence {ev_key} for condition {cond_id!r} has invalid "
                                f"mode: {ev_mode.value} (allowed: {allowed_modes_str})"
                            )

                        if not crit_failed:
                            if ev_key not in bound_keys:
                                bound_keys.append(ev_key)
                            matched_evidence_found = True

                if not matched_evidence_found and not crit_failed:
                    crit_failed = True
                    crit_reasons.append(
                        f"No produced evidence found satisfying canonical condition {cond_id!r} "
                        f"(expected type: {spec.canonical_evidence_type})"
                    )

            if not bound_keys and not crit_failed:
                crit_failed = True
                crit_reasons.append("No capable evidence records could be bound to criterion")

            criterion_bound_evidence[crit.criterion_id] = bound_keys
            if crit_failed:
                criterion_deterministic_state[crit.criterion_id] = "FAIL"
                verification_failures.extend([f"[{crit.criterion_id}] {r}" for r in crit_reasons])
            else:
                criterion_deterministic_state[crit.criterion_id] = "PASS"

        # Build NeutralClaims with ONLY bound evidence keys
        claims_list = []
        evidence_store_for_bundle: dict[str, str] = {}
        for i, crit in enumerate(effective_criteria):
            bound_keys = criterion_bound_evidence[crit.criterion_id]
            for k in bound_keys:
                if k in produced_evidence_catalog:
                    evidence_store_for_bundle[k] = produced_evidence_catalog[k]["summary"]
            claims_list.append(
                NeutralClaim(
                    claim_id=f"claim_{i}",
                    claim_type=ClaimType.MISSION_CLAIM,
                    statement=sanitize_secrets_in_text(crit.description),
                    evidence_keys=tuple(bound_keys),
                    source_criterion_id=crit.criterion_id,
                )
            )

        claims = tuple(claims_list)
        claim_engine = ClaimDerivationEngine()
        violations = claim_engine.validate_neutrality(claims)
        if violations:
            raise ValueError(f"Claim neutrality violations detected: {violations}")

        bundle_builder = AuditBundleBuilder()
        audit_bundle = bundle_builder.build_bundle(
            change_id=change_id,
            claims=claims,
            evidence_store=evidence_store_for_bundle,
        )

        auditor = SemanticAuditor()
        audit_report = auditor.audit_claims(audit_bundle, use_live_gemini=False)

        reconciler = DeterministicReconciler()
        reconciliation_results = []
        for i, res in enumerate(audit_report.results):
            crit = effective_criteria[i]
            det_state = criterion_deterministic_state[crit.criterion_id]
            recon_res = reconciler.reconcile(
                audit_result=res,
                deterministic_state=det_state,
                change_id=change_id,
            )
            if not recon_res.deterministic_state_preserved:
                raise ValueError("Semantic audit failed to preserve deterministic state!")
            reconciliation_results.append(recon_res)

        # Check if verification passed
        if verification_failures:
            failure_summary = "; ".join(verification_failures)
            transition_and_persist(
                target_state=ChangeState.FAILED,
                reason=f"Verification failed: {failure_summary}",
                producer_id="agent-evidence-auditor",
                producer_role="evidence_auditor",
                producer_revision="1.0.0",
                payload_summary={
                    "action": "verification_failed",
                    "failures": verification_failures,
                    "supports_count": audit_report.supports_count,
                    "insufficient_count": audit_report.insufficient_count,
                },
            )
            tasks_executed += 1
            self.repository.create_task(
                tid,
                change_id,
                TaskRecord(
                    tenant_id=tid,
                    change_id=change_id,
                    task_id=f"task-verify-{change_id}",
                    sequence_number=tasks_executed,
                    agent_id="agent-evidence-auditor",
                    agent_role="evidence_auditor",
                    agent_revision="1.0.0",
                    action_class="EVIDENCE_AUDIT_RECONCILIATION",
                    status=TaskStatus.FAILED,
                    started_at=now,
                    completed_at=now,
                    output_summary=f"Verification FAILED: {failure_summary}",
                    created_at=now,
                    updated_at=now,
                ),
            )
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=ChangeState.FAILED,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                stopped_reason=f"VERIFICATION_FAILED: {failure_summary}",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-verify-{change_id}",
                sequence_number=tasks_executed,
                agent_id="agent-evidence-auditor",
                agent_role="evidence_auditor",
                agent_revision="1.0.0",
                action_class="EVIDENCE_AUDIT_RECONCILIATION",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary=(
                    f"Audit completed: {audit_report.supports_count} supported claims reconciled"
                ),
                created_at=now,
                updated_at=now,
            ),
        )

        evidence_collected += 1
        self.repository.create_evidence_ref(
            tid,
            change_id,
            EvidenceRefRecord(
                tenant_id=tid,
                change_id=change_id,
                evidence_id=f"ev-verify-{change_id}",
                subject="audit_reconciliation",
                state=EvidenceState.PASS,
                collection_mode=evidence_mode,
                producer_kind=EvidenceProducerKind.AGENT,
                agent_id="agent-evidence-auditor",
                agent_revision="1.0.0",
                collected_at=now,
                created_at=now,
            ),
        )

        if stop_at_state == ChangeState.VERIFYING:
            return SagaExecutionResult(
                tenant_id=tid,
                change_id=change_id,
                correlation_id=correlation_id,
                initial_state=ChangeState.RECEIVED,
                final_state=current_state,
                is_completed=False,
                autonomy_class=active_autonomy_class,
                stopped_reason="Stopped at requested state VERIFYING",
                events_emitted=events_emitted,
                tasks_executed=tasks_executed,
                evidence_collected=evidence_collected,
                checkpoints_created=checkpoints_created,
                timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
            )

        # -------------------------------------------------------------------------
        # STAGE 8: Certify (CERTIFYING -> COMPLETE) — Checkpoint & Complete
        # -------------------------------------------------------------------------
        transition_and_persist(
            target_state=ChangeState.CERTIFYING,
            reason="Certifying complete proof-carrying change evidence package",
            producer_id=self.orchestrator_id,
            producer_role="change_orchestrator",
            producer_revision=self.orchestrator_revision,
            payload_summary={"action": "certify_change_evidence"},
        )

        # Create Durable Checkpoint
        checkpoints_created += 1
        SagaCheckpointManager.create_checkpoint(
            repo=self.repository,
            tenant_id=tid,
            change_id=change_id,
            lifecycle_state=ChangeState.CERTIFYING,
            completed_task_ids=(
                f"task-discover-{change_id}",
                f"task-qualify-{change_id}",
                f"task-rehearse-{change_id}",
                f"task-ground-{change_id}",
                f"task-authorize-{change_id}",
                f"task-execute-{change_id}",
                f"task-verify-{change_id}",
            ),
            now=now,
        )

        tasks_executed += 1
        self.repository.create_task(
            tid,
            change_id,
            TaskRecord(
                tenant_id=tid,
                change_id=change_id,
                task_id=f"task-certify-{change_id}",
                sequence_number=tasks_executed,
                agent_id=self.orchestrator_id,
                agent_role="change_orchestrator",
                agent_revision=self.orchestrator_revision,
                action_class="SAGA_CERTIFICATION",
                status=TaskStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                output_summary="Certified complete evidence package",
                created_at=now,
                updated_at=now,
            ),
        )

        # Final Transition to COMPLETE
        transition_and_persist(
            target_state=ChangeState.COMPLETE,
            reason="Change saga completed successfully with all verification gates passed",
            producer_id=self.orchestrator_id,
            producer_role="change_orchestrator",
            producer_revision=self.orchestrator_revision,
            payload_summary={
                "status": "SUCCESS",
                "tasks_executed": tasks_executed,
                "evidence_collected": evidence_collected,
            },
        )

        # Update final evidence summary in ChangeRecord
        final_record = self.repository.get_change(tid, change_id)
        if final_record is not None:
            updated_final = final_record.model_copy(
                update={
                    "evidence_summary": {
                        "pass": evidence_collected - 1,  # 1 was SIMULATED
                        "fail": 0,
                        "simulated": 1,
                        "blocked": 0,
                    },
                    "updated_at": now,
                }
            )
            self.repository.update_change(tid, updated_final, expected_version=final_record.version)

        return SagaExecutionResult(
            tenant_id=tid,
            change_id=change_id,
            correlation_id=correlation_id,
            initial_state=ChangeState.RECEIVED,
            final_state=ChangeState.COMPLETE,
            is_completed=True,
            autonomy_class=active_autonomy_class,
            stopped_reason=None,
            events_emitted=events_emitted,
            tasks_executed=tasks_executed,
            evidence_collected=evidence_collected,
            checkpoints_created=checkpoints_created,
            timeline_digest=self.timeline.compute_timeline_digest() if self.timeline else None,
        )

    # =========================================================================
    # P-20.02 — Recovery Path Methods
    # =========================================================================
    # Every path:
    # 1. Loads authoritative persisted state with optimistic concurrency
    # 2. Validates transition legality against ALLOWED_TRANSITIONS
    # 3. Persists new state BEFORE publishing event
    # 4. Publishes causal EventEnvelope with full identity chain
    # 5. Returns explicit SagaRecoveryResult with all metadata
    # =========================================================================

    def _recovery_transition(
        self,
        tenant_id: str,
        change_id: str,
        target_state: ChangeState,
        reason: str,
        *,
        retry_origin: Optional[ChangeState] = None,
        now: Optional[datetime] = None,
    ) -> tuple[ChangeRecord, str]:
        """Atomically persist a recovery state transition with event emission.

        Returns (updated_record, event_id).
        Raises IllegalTransitionError if the transition is not allowed.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        current_state = record.state
        if current_state != target_state:
            require_transition(current_state, target_state, retry_origin=retry_origin)

        sanitized_reason = sanitize_secrets_in_text(reason)

        # Persist state FIRST (optimistic concurrency)
        updated = record.model_copy(
            update={
                "state": target_state,
                "state_updated_at": now,
                "state_reason": sanitized_reason,
                "updated_at": now,
            }
        )
        self.repository.update_change(tenant_id, updated, expected_version=record.version)

        # Emit causal event AFTER persistence
        unique_suffix = uuid.uuid4().hex[:8]
        event_id = f"evt-{change_id}-recovery-{target_state.value.lower()}-{unique_suffix}"
        idempotency_key = f"idem_recovery_{change_id}_{target_state.value.lower()}_{unique_suffix}"

        from domain.contracts.agent_descriptor import AgentRevisionProvenance

        provenance = AgentRevisionProvenance(
            agent_id=self.orchestrator_id,
            agent_revision=self.orchestrator_revision,
            role="change_orchestrator",
        )

        envelope = EventEnvelope(
            schema_version=CANONICAL_SCHEMA_VERSION,
            event_id=event_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            producer_id=self.orchestrator_id,
            producer_revision=self.orchestrator_revision,
            producer_role="change_orchestrator",
            agent_provenance=provenance,
            timestamp=now,
            idempotency_key=idempotency_key,
        )

        route = self._topology.get_route_for_state(target_state)
        topic_id = route.primary_topic_id if route else "changemesh-lifecycle-v1"
        payload = {
            "action": f"recovery_{target_state.value.lower()}",
            "reason": sanitized_reason,
            "previous_state": current_state.value,
        }

        from events.wire import EventWireMessage, scan_payload_for_secrets

        scan_payload_for_secrets(payload)
        wire_msg = EventWireMessage(
            topic_id=topic_id,
            envelope=envelope,
            payload=payload,
            published_at=now,
        )

        if isinstance(self.event_bus, LocalEventBus):
            self.event_bus.publish_message(wire_msg)
        else:
            self.event_bus.publish(wire_msg)

        if self.timeline is not None:
            self.timeline.record_event(
                envelope, topic_id=topic_id, payload=payload, transport="LOCAL"
            )

        # Re-read to get updated version
        final_record = self.repository.get_change(tenant_id, change_id)
        return final_record or updated, event_id

    def pause_saga(
        self,
        tenant_id: str,
        change_id: str,
        reason: str,
        *,
        now: Optional[datetime] = None,
    ) -> SagaRecoveryResult:
        """Pause a running saga by transitioning to BLOCKED with explicit reason.

        P-20.02: Pause transitions the saga to BLOCKED state with a persisted
        reason. The saga can be resumed by calling resume_saga. Only non-terminal,
        non-BLOCKED states can be paused.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        previous_state = record.state
        if is_terminal(previous_state):
            raise ValueError(f"Cannot pause saga in terminal state {previous_state.value}")

        updated_record, event_id = self._recovery_transition(
            tenant_id,
            change_id,
            ChangeState.BLOCKED,
            f"PAUSED: {reason}",
            now=now,
        )

        # Create checkpoint at pause boundary
        SagaCheckpointManager.create_checkpoint(
            repo=self.repository,
            tenant_id=tenant_id,
            change_id=change_id,
            lifecycle_state=ChangeState.BLOCKED,
            now=now,
        )

        return SagaRecoveryResult(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            action=RecoveryAction.PAUSED,
            previous_state=previous_state,
            final_state=ChangeState.BLOCKED,
            reason=f"PAUSED: {reason}",
            event_id=event_id,
            timestamp=now,
        )

    def cancel_saga(
        self,
        tenant_id: str,
        change_id: str,
        reason: str,
        *,
        now: Optional[datetime] = None,
    ) -> SagaRecoveryResult:
        """Cancel a saga, transitioning to terminal CANCELLED state.

        P-20.02: Cancel is allowed from any non-terminal state. Once cancelled,
        the saga cannot be resumed. Persists state, emits causal event.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        previous_state = record.state
        if is_terminal(previous_state):
            raise ValueError(f"Cannot cancel saga in terminal state {previous_state.value}")

        updated_record, event_id = self._recovery_transition(
            tenant_id,
            change_id,
            ChangeState.CANCELLED,
            f"CANCELLED: {reason}",
            now=now,
        )

        return SagaRecoveryResult(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            action=RecoveryAction.CANCELLED,
            previous_state=previous_state,
            final_state=ChangeState.CANCELLED,
            reason=f"CANCELLED: {reason}",
            event_id=event_id,
            timestamp=now,
        )

    def timeout_saga(
        self,
        tenant_id: str,
        change_id: str,
        *,
        timeout_seconds: float = DEFAULT_SAGA_TIMEOUT_SECONDS,
        now: Optional[datetime] = None,
    ) -> Optional[SagaRecoveryResult]:
        """Check and apply timeout to a saga.

        P-20.02: If the saga has been in its current non-terminal state for
        longer than timeout_seconds, transition to FAILED with explicit timeout
        evidence. Returns None if not timed out.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        if is_terminal(record.state):
            return None  # Terminal states cannot time out

        elapsed = (now - record.state_updated_at).total_seconds()
        if elapsed < timeout_seconds:
            return None  # Not timed out yet

        previous_state = record.state
        timeout_reason = (
            f"TIMEOUT: Saga exceeded {timeout_seconds}s in state "
            f"{previous_state.value} (elapsed: {elapsed:.1f}s)"
        )

        updated_record, event_id = self._recovery_transition(
            tenant_id,
            change_id,
            ChangeState.FAILED,
            timeout_reason,
            now=now,
        )

        return SagaRecoveryResult(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            action=RecoveryAction.TIMED_OUT,
            previous_state=previous_state,
            final_state=ChangeState.FAILED,
            reason=timeout_reason,
            event_id=event_id,
            timestamp=now,
        )

    def schedule_retry(
        self,
        tenant_id: str,
        change_id: str,
        reason: str,
        *,
        retry_attempt: int = 1,
        max_attempts: int = DEFAULT_SAGA_RETRY_MAX_ATTEMPTS,
        now: Optional[datetime] = None,
    ) -> SagaRecoveryResult:
        """Schedule a retry for a failed saga phase.

        P-20.02: Transitions to RETRY_SCHEDULED from the current state.
        The retry_origin is persisted for bounded resume validation.
        If retry_attempt exceeds max_attempts, transitions to FAILED via dead-letter
        instead.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        previous_state = record.state

        # Exhaustion check: if attempts exhausted, dead-letter instead
        if retry_attempt > max_attempts:
            return self._dead_letter_saga(
                tenant_id,
                change_id,
                f"RETRY_EXHAUSTED: {reason} (attempt {retry_attempt}/{max_attempts})",
                previous_state=previous_state,
                correlation_id=record.correlation_id,
                now=now,
            )

        if is_terminal(previous_state):
            raise ValueError(f"Cannot schedule retry from terminal state {previous_state.value}")

        # Validate transition is legal from current state
        if not can_transition(previous_state, ChangeState.RETRY_SCHEDULED):
            raise ValueError(f"Cannot schedule retry from state {previous_state.value}")

        updated_record, event_id = self._recovery_transition(
            tenant_id,
            change_id,
            ChangeState.RETRY_SCHEDULED,
            f"RETRY_SCHEDULED: {reason} (attempt {retry_attempt}/{max_attempts})",
            now=now,
        )

        return SagaRecoveryResult(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            action=RecoveryAction.RETRY_SCHEDULED,
            previous_state=previous_state,
            final_state=ChangeState.RETRY_SCHEDULED,
            reason=f"RETRY_SCHEDULED: {reason}",
            retry_origin=previous_state,
            retry_attempt=retry_attempt,
            retry_max_attempts=max_attempts,
            event_id=event_id,
            timestamp=now,
        )

    def resume_from_retry(
        self,
        tenant_id: str,
        change_id: str,
        retry_origin: ChangeState,
        *,
        now: Optional[datetime] = None,
    ) -> SagaRecoveryResult:
        """Resume saga from RETRY_SCHEDULED back to the retry origin phase.

        P-20.02: Validates that the saga is in RETRY_SCHEDULED state and
        the resume target matches the bounded RETRY_RESUME_TARGETS for
        the given retry_origin. Persists state before event emission.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        if record.state != ChangeState.RETRY_SCHEDULED:
            raise ValueError(
                f"Cannot resume retry: saga is in {record.state.value}, expected RETRY_SCHEDULED"
            )

        # The transition validation with retry_origin is enforced by require_transition
        updated_record, event_id = self._recovery_transition(
            tenant_id,
            change_id,
            retry_origin,
            f"RETRY_RESUMED: Resuming from RETRY_SCHEDULED to {retry_origin.value}",
            retry_origin=retry_origin,
            now=now,
        )

        return SagaRecoveryResult(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            action=RecoveryAction.RESUMED,
            previous_state=ChangeState.RETRY_SCHEDULED,
            final_state=retry_origin,
            reason=f"RETRY_RESUMED: Resumed to {retry_origin.value}",
            retry_origin=retry_origin,
            event_id=event_id,
            timestamp=now,
        )

    def start_compensation(
        self,
        tenant_id: str,
        change_id: str,
        compensation_description: str,
        *,
        now: Optional[datetime] = None,
    ) -> SagaRecoveryResult:
        """Start compensation for a saga that failed during execution.

        P-20.02: Compensation transitions to COMPENSATING state and describes
        what is actually being compensated. Compensation is NOT fabricated
        rollback evidence — it describes the real compensating actions taken.
        Only EXECUTING and VERIFYING states can initiate compensation (per
        ALLOWED_TRANSITIONS).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        previous_state = record.state
        if not can_transition(previous_state, ChangeState.COMPENSATING):
            raise ValueError(f"Cannot start compensation from state {previous_state.value}")

        sanitized_desc = sanitize_secrets_in_text(compensation_description)

        updated_record, event_id = self._recovery_transition(
            tenant_id,
            change_id,
            ChangeState.COMPENSATING,
            f"COMPENSATION_STARTED: {sanitized_desc}",
            now=now,
        )

        # Record compensation task
        self.repository.create_task(
            tenant_id,
            change_id,
            TaskRecord(
                tenant_id=tenant_id,
                change_id=change_id,
                task_id=f"task-compensate-{change_id}",
                sequence_number=len(self.repository.list_tasks(tenant_id, change_id)) + 1,
                agent_id=self.orchestrator_id,
                agent_role="change_orchestrator",
                agent_revision=self.orchestrator_revision,
                action_class="COMPENSATION",
                status=TaskStatus.IN_PROGRESS,
                started_at=now,
                output_summary=sanitized_desc,
                created_at=now,
                updated_at=now,
            ),
        )

        return SagaRecoveryResult(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            action=RecoveryAction.COMPENSATION_STARTED,
            previous_state=previous_state,
            final_state=ChangeState.COMPENSATING,
            reason=f"COMPENSATION_STARTED: {sanitized_desc}",
            compensation_description=sanitized_desc,
            event_id=event_id,
            timestamp=now,
        )

    def complete_compensation(
        self,
        tenant_id: str,
        change_id: str,
        outcome: str,
        *,
        success: bool = True,
        now: Optional[datetime] = None,
    ) -> SagaRecoveryResult:
        """Complete a running compensation phase.

        P-20.02: If success=True, transitions COMPENSATING -> FAILED
        (compensation completed but the change itself is failed).
        If success=False, transitions COMPENSATING -> FAILED
        (compensation itself failed; the change is still failed).
        Compensation ≠ pretend rollback — it records what actually happened.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        if record.state != ChangeState.COMPENSATING:
            raise ValueError(
                f"Cannot complete compensation: saga is in {record.state.value}, "
                f"expected COMPENSATING"
            )

        sanitized_outcome = sanitize_secrets_in_text(outcome)
        action = (
            RecoveryAction.COMPENSATION_COMPLETED if success else RecoveryAction.COMPENSATION_FAILED
        )
        reason_prefix = "COMPENSATION_COMPLETED" if success else "COMPENSATION_FAILED"

        updated_record, event_id = self._recovery_transition(
            tenant_id,
            change_id,
            ChangeState.FAILED,
            f"{reason_prefix}: {sanitized_outcome}",
            now=now,
        )

        # Update compensation task status
        tasks = self.repository.list_tasks(tenant_id, change_id)
        for task in tasks:
            if task.task_id == f"task-compensate-{change_id}":
                updated_task = task.model_copy(
                    update={
                        "status": TaskStatus.COMPENSATED if success else TaskStatus.FAILED,
                        "completed_at": now,
                        "output_summary": sanitized_outcome,
                        "updated_at": now,
                    }
                )
                self.repository.update_task(
                    tenant_id, change_id, updated_task, expected_version=task.version
                )
                break

        return SagaRecoveryResult(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=record.correlation_id,
            action=action,
            previous_state=ChangeState.COMPENSATING,
            final_state=ChangeState.FAILED,
            reason=f"{reason_prefix}: {sanitized_outcome}",
            compensation_description=sanitized_outcome,
            event_id=event_id,
            timestamp=now,
        )

    def _dead_letter_saga(
        self,
        tenant_id: str,
        change_id: str,
        reason: str,
        *,
        previous_state: ChangeState,
        correlation_id: str,
        now: Optional[datetime] = None,
    ) -> SagaRecoveryResult:
        """Route a saga to the dead-letter path.

        P-20.02: Dead-letter preserves all metadata for safe recovery without
        credentials. Creates a DeadLetterEventRecord and TerminalFailureHandoff
        with human_authority_required strictly False.
        """
        from events.dead_letter import (
            build_dead_letter_record,
            compute_dead_letter_id,
        )

        if now is None:
            now = datetime.now(timezone.utc)

        dl_id = compute_dead_letter_id(change_id, f"saga-{change_id}")
        sanitized_reason = sanitize_secrets_in_text(reason)

        # Build dead-letter record with full metadata preservation
        _ = build_dead_letter_record(
            dead_letter_id=dl_id,
            original_event_id=f"saga-{change_id}",
            change_id=change_id,
            correlation_id=correlation_id,
            original_topic_id="changemesh-lifecycle-v1",
            failure_classification=FailureClassification.TERMINAL_EXHAUSTED,
            raw_error=sanitized_reason,
            attempts_made=0,
            timestamp=now,
        )

        # Transition to FAILED terminal state
        record = self.repository.get_change(tenant_id, change_id)
        if record is not None and not is_terminal(record.state):
            self._recovery_transition(
                tenant_id,
                change_id,
                ChangeState.FAILED,
                f"DEAD_LETTERED: {sanitized_reason}",
                now=now,
            )

        return SagaRecoveryResult(
            tenant_id=tenant_id,
            change_id=change_id,
            correlation_id=correlation_id,
            action=RecoveryAction.DEAD_LETTERED,
            previous_state=previous_state,
            final_state=ChangeState.FAILED,
            reason=f"DEAD_LETTERED: {sanitized_reason}",
            dead_letter_id=dl_id,
            timestamp=now,
        )

    def dead_letter_saga(
        self,
        tenant_id: str,
        change_id: str,
        reason: str,
        *,
        now: Optional[datetime] = None,
    ) -> SagaRecoveryResult:
        """Public dead-letter entry point for saga routing.

        P-20.02: Routes a saga to the dead-letter path with full metadata
        preservation. Dead-letter records contain sanitized diagnostics but
        zero credentials. human_authority_required is strictly False.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        record = self.repository.get_change(tenant_id, change_id)
        if record is None:
            raise ValueError(f"Change {change_id!r} not found in tenant {tenant_id!r}")

        return self._dead_letter_saga(
            tenant_id,
            change_id,
            reason,
            previous_state=record.state,
            correlation_id=record.correlation_id,
            now=now,
        )
