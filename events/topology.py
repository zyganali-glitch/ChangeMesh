"""ChangeMesh event topology configuration and lifecycle mapping.

P-09.01: Defines the canonical topic and subscription topology for:
- change lifecycle events
- agent work dispatch & coordination
- authority / approval transport
- evidence & validation transport
- retry scheduling flow
- dead-letter & poison event flow

Provider-neutral: Standard library + Pydantic + domain contracts only.
Zero imports of google.cloud.pubsub or provider SDKs.
Credentials and secrets are strictly forbidden.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from domain.contracts.change_lifecycle import ChangeState

CANONICAL_TOPOLOGY_VERSION = "1.0.0"

# Topic & subscription name validation: lowercase alphanumeric, hyphens, and version suffixes
_RESOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class LogicalTopicKind(str, Enum):
    """Canonical classification of logical message flows."""

    CHANGE_LIFECYCLE = "CHANGE_LIFECYCLE"
    AGENT_WORK = "AGENT_WORK"
    APPROVAL_AUTHORITY = "APPROVAL_AUTHORITY"
    EVIDENCE = "EVIDENCE"
    RETRY = "RETRY"
    DEAD_LETTER = "DEAD_LETTER"


class DeadLetterPolicyConfig(BaseModel):
    """Configuration for subscription dead-lettering."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dead_letter_topic: str
    max_delivery_attempts: int

    @field_validator("dead_letter_topic")
    @classmethod
    def _validate_topic_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("dead_letter_topic must not be blank")
        clean = v.strip()
        if not _RESOURCE_NAME_PATTERN.match(clean):
            raise ValueError(f"Invalid dead_letter_topic name format: {v!r}")
        return clean

    @field_validator("max_delivery_attempts")
    @classmethod
    def _validate_max_attempts(cls, v: int) -> int:
        if v < 5 or v > 100:
            raise ValueError(f"max_delivery_attempts must be between 5 and 100, got {v}")
        return v


class RetryPolicyConfig(BaseModel):
    """Configuration for subscription delivery retry backoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_backoff_seconds: float
    maximum_backoff_seconds: float

    @field_validator("minimum_backoff_seconds", "maximum_backoff_seconds")
    @classmethod
    def _validate_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Backoff seconds must be strictly positive")
        return v

    @model_validator(mode="after")
    def _validate_order(self) -> RetryPolicyConfig:
        if self.minimum_backoff_seconds > self.maximum_backoff_seconds:
            raise ValueError("minimum_backoff_seconds cannot exceed maximum_backoff_seconds")
        return self


class TopicConfig(BaseModel):
    """Configuration for a single Pub/Sub topic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: str
    logical_kind: LogicalTopicKind
    description: str
    labels: Mapping[str, str] = {}

    @field_validator("topic_id", "description")
    @classmethod
    def _must_not_be_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        if info.field_name == "topic_id":
            clean = v.strip()
            if not _RESOURCE_NAME_PATTERN.match(clean):
                raise ValueError(f"Invalid topic_id format: {v!r}")
            return clean
        return v.strip()


class SubscriptionConfig(BaseModel):
    """Configuration for a Pub/Sub subscription attached to a topic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subscription_id: str
    topic_id: str
    logical_kind: LogicalTopicKind
    description: str
    ack_deadline_seconds: int = 30
    dead_letter_policy: Optional[DeadLetterPolicyConfig] = None
    retry_policy: Optional[RetryPolicyConfig] = None
    labels: Mapping[str, str] = {}

    @field_validator("subscription_id", "topic_id", "description")
    @classmethod
    def _must_not_be_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        if info.field_name in ("subscription_id", "topic_id"):
            clean = v.strip()
            if not _RESOURCE_NAME_PATTERN.match(clean):
                raise ValueError(f"Invalid {info.field_name} format: {v!r}")
            return clean
        return v.strip()

    @field_validator("ack_deadline_seconds")
    @classmethod
    def _validate_ack_deadline(cls, v: int) -> int:
        if v < 10 or v > 600:
            raise ValueError(f"ack_deadline_seconds must be between 10 and 600, got {v}")
        return v


class LifecycleStateRoute(BaseModel):
    """Mapping of a canonical ChangeState to its logical message destination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: ChangeState
    primary_topic_id: str
    logical_kind: LogicalTopicKind
    secondary_topic_id: Optional[str] = None
    description: str

    @field_validator("primary_topic_id", "description")
    @classmethod
    def _must_not_be_blank(cls, v: str, info: Any) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        if info.field_name == "primary_topic_id":
            clean = v.strip()
            if not _RESOURCE_NAME_PATTERN.match(clean):
                raise ValueError(f"Invalid primary_topic_id format: {v!r}")
            return clean
        return v.strip()

    @field_validator("secondary_topic_id")
    @classmethod
    def _validate_secondary_topic(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or not v.strip():
                raise ValueError("secondary_topic_id must not be blank when provided")
            clean = v.strip()
            if not _RESOURCE_NAME_PATTERN.match(clean):
                raise ValueError(f"Invalid secondary_topic_id format: {v!r}")
            return clean
        return None


class TopologyConfig(BaseModel):
    """Immutable, versioned Pub/Sub topic and subscription topology."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    topics: Sequence[TopicConfig]
    subscriptions: Sequence[SubscriptionConfig]
    lifecycle_routes: Sequence[LifecycleStateRoute]

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("schema_version must not be blank")
        return v.strip()

    @model_validator(mode="after")
    def _validate_topology_integrity(self) -> TopologyConfig:
        # 1. Unique topic IDs
        topic_ids = set()
        topic_kind_map = {}
        for t in self.topics:
            if t.topic_id in topic_ids:
                raise ValueError(f"Duplicate topic_id declared in topology: {t.topic_id!r}")
            topic_ids.add(t.topic_id)
            topic_kind_map[t.topic_id] = t.logical_kind

        # 2. All LogicalTopicKind values must be covered
        declared_kinds = {t.logical_kind for t in self.topics}
        missing_kinds = set(LogicalTopicKind) - declared_kinds
        if missing_kinds:
            missing_names = [k.value for k in missing_kinds]
            raise ValueError(f"Topology missing mandatory logical topic kinds: {missing_names}")

        # 3. Subscriptions must point to declared topics and have unique IDs
        sub_ids = set()
        for s in self.subscriptions:
            if s.subscription_id in sub_ids:
                raise ValueError(
                    f"Duplicate subscription_id declared in topology: {s.subscription_id!r}"
                )
            sub_ids.add(s.subscription_id)

            if s.topic_id not in topic_ids:
                raise ValueError(
                    f"Subscription {s.subscription_id!r} points to undeclared topic {s.topic_id!r}"
                )

            # Dead letter validation
            if s.dead_letter_policy is not None:
                dl_topic = s.dead_letter_policy.dead_letter_topic
                if dl_topic not in topic_ids:
                    raise ValueError(
                        f"Subscription {s.subscription_id!r} references undeclared "
                        f"dead_letter_topic {dl_topic!r}"
                    )
                # Dead letter subscription cannot dead-letter to itself or create cycle
                if s.topic_id == dl_topic:
                    raise ValueError(
                        f"Dead-letter cycle detected: Subscription {s.subscription_id!r} "
                        f"on dead-letter topic {dl_topic!r} cannot have a dead_letter_policy"
                    )

        # 4. Lifecycle routes must cover EVERY ChangeState exactly once and point to declared topics
        routed_states = set()
        for r in self.lifecycle_routes:
            if r.state in routed_states:
                raise ValueError(f"Duplicate lifecycle route for ChangeState: {r.state.value}")
            routed_states.add(r.state)

            if r.primary_topic_id not in topic_ids:
                raise ValueError(
                    f"Lifecycle route for {r.state.value} points to undeclared "
                    f"primary_topic_id {r.primary_topic_id!r}"
                )
            if r.secondary_topic_id is not None and r.secondary_topic_id not in topic_ids:
                raise ValueError(
                    f"Lifecycle route for {r.state.value} points to undeclared "
                    f"secondary_topic_id {r.secondary_topic_id!r}"
                )

        all_states = set(ChangeState)
        missing_states = all_states - routed_states
        if missing_states:
            missing_names = sorted([s.value for s in missing_states])
            raise ValueError(f"Topology lifecycle routes missing ChangeStates: {missing_names}")

        return self

    def get_topic(self, topic_id: str) -> Optional[TopicConfig]:
        """Lookup topic by ID."""
        for t in self.topics:
            if t.topic_id == topic_id:
                return t
        return None

    def get_topic_by_kind(self, kind: LogicalTopicKind) -> Optional[TopicConfig]:
        """Lookup primary topic for a logical kind."""
        for t in self.topics:
            if t.logical_kind == kind:
                return t
        return None

    def get_subscription(self, sub_id: str) -> Optional[SubscriptionConfig]:
        """Lookup subscription by ID."""
        for s in self.subscriptions:
            if s.subscription_id == sub_id:
                return s
        return None

    def get_route_for_state(self, state: ChangeState) -> Optional[LifecycleStateRoute]:
        """Lookup lifecycle route for a ChangeState."""
        for r in self.lifecycle_routes:
            if r.state == state:
                return r
        return None


def get_canonical_topology() -> TopologyConfig:
    """Return the canonical, frozen ChangeMesh topic/subscription topology."""
    lifecycle_topic_id = "changemesh-lifecycle-v1"
    agent_work_topic_id = "changemesh-agent-work-v1"
    approval_topic_id = "changemesh-approval-v1"
    evidence_topic_id = "changemesh-evidence-v1"
    retry_topic_id = "changemesh-retry-v1"
    dead_letter_topic_id = "changemesh-dead-letter-v1"

    topics = [
        TopicConfig(
            topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            description="ChangeMesh change state progression and saga lifecycle transitions",
            labels={"system": "changemesh", "tier": "backbone", "kind": "lifecycle"},
        ),
        TopicConfig(
            topic_id=agent_work_topic_id,
            logical_kind=LogicalTopicKind.AGENT_WORK,
            description=(
                "Specialist agent task dispatch, routing requests, and multi-agent coordination"
            ),
            labels={"system": "changemesh", "tier": "backbone", "kind": "agent-work"},
        ),
        TopicConfig(
            topic_id=approval_topic_id,
            logical_kind=LogicalTopicKind.APPROVAL_AUTHORITY,
            description="Human authority request notification and explicit authority receipts",
            labels={"system": "changemesh", "tier": "backbone", "kind": "approval"},
        ),
        TopicConfig(
            topic_id=evidence_topic_id,
            logical_kind=LogicalTopicKind.EVIDENCE,
            description="Generated evidence records, rehearsal outcomes, proofs, and audits",
            labels={"system": "changemesh", "tier": "backbone", "kind": "evidence"},
        ),
        TopicConfig(
            topic_id=retry_topic_id,
            logical_kind=LogicalTopicKind.RETRY,
            description="Scheduled retry triggers and delayed re-execution dispatch",
            labels={"system": "changemesh", "tier": "backbone", "kind": "retry"},
        ),
        TopicConfig(
            topic_id=dead_letter_topic_id,
            logical_kind=LogicalTopicKind.DEAD_LETTER,
            description="Terminal dead-letter sink for unparseable, malformed, or exhausted events",
            labels={"system": "changemesh", "tier": "backbone", "kind": "dead-letter"},
        ),
    ]

    default_retry = RetryPolicyConfig(
        minimum_backoff_seconds=1.0,
        maximum_backoff_seconds=60.0,
    )

    default_dead_letter = DeadLetterPolicyConfig(
        dead_letter_topic=dead_letter_topic_id,
        max_delivery_attempts=5,
    )

    subscriptions = [
        SubscriptionConfig(
            subscription_id="changemesh-lifecycle-sub-v1",
            topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            description="Change Orchestrator / Saga listener for change lifecycle transitions",
            ack_deadline_seconds=30,
            dead_letter_policy=default_dead_letter,
            retry_policy=default_retry,
            labels={"consumer": "change-orchestrator"},
        ),
        SubscriptionConfig(
            subscription_id="changemesh-agent-work-sub-v1",
            topic_id=agent_work_topic_id,
            logical_kind=LogicalTopicKind.AGENT_WORK,
            description="Specialist agent fleet worker dispatch listener",
            ack_deadline_seconds=60,
            dead_letter_policy=default_dead_letter,
            retry_policy=default_retry,
            labels={"consumer": "agent-fleet"},
        ),
        SubscriptionConfig(
            subscription_id="changemesh-approval-sub-v1",
            topic_id=approval_topic_id,
            logical_kind=LogicalTopicKind.APPROVAL_AUTHORITY,
            description="Authority manager listener for human approval notifications and receipts",
            ack_deadline_seconds=30,
            dead_letter_policy=default_dead_letter,
            retry_policy=default_retry,
            labels={"consumer": "authority-manager"},
        ),
        SubscriptionConfig(
            subscription_id="changemesh-evidence-sub-v1",
            topic_id=evidence_topic_id,
            logical_kind=LogicalTopicKind.EVIDENCE,
            description="Evidence Recorder and PubSub timeline projection listener",
            ack_deadline_seconds=30,
            dead_letter_policy=default_dead_letter,
            retry_policy=default_retry,
            labels={"consumer": "evidence-ledger"},
        ),
        SubscriptionConfig(
            subscription_id="changemesh-retry-sub-v1",
            topic_id=retry_topic_id,
            logical_kind=LogicalTopicKind.RETRY,
            description="Retry manager listener for delayed re-execution dispatch",
            ack_deadline_seconds=30,
            dead_letter_policy=default_dead_letter,
            retry_policy=default_retry,
            labels={"consumer": "retry-manager"},
        ),
        SubscriptionConfig(
            subscription_id="changemesh-dead-letter-sub-v1",
            topic_id=dead_letter_topic_id,
            logical_kind=LogicalTopicKind.DEAD_LETTER,
            description="Dead-letter diagnostic processor and failure handoff generator",
            ack_deadline_seconds=60,
            dead_letter_policy=None,  # Crucial: No cycle!
            retry_policy=default_retry,
            labels={"consumer": "dead-letter-diagnostics"},
        ),
    ]

    routes = [
        LifecycleStateRoute(
            state=ChangeState.RECEIVED,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            description="Initial change intake event",
        ),
        LifecycleStateRoute(
            state=ChangeState.DISCOVERING,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=agent_work_topic_id,
            description="Impact scout repository discovery dispatch",
        ),
        LifecycleStateRoute(
            state=ChangeState.QUALIFYING,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=agent_work_topic_id,
            description="Policy qualification and boundary checks",
        ),
        LifecycleStateRoute(
            state=ChangeState.REHEARSING,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=evidence_topic_id,
            description="ShadowLab rehearsal twin execution and evidence generation",
        ),
        LifecycleStateRoute(
            state=ChangeState.GROUNDED,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            description="Evidence grounded; policy evaluation for autonomy vs human authority",
        ),
        LifecycleStateRoute(
            state=ChangeState.AWAITING_AUTHORITY,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=approval_topic_id,
            description="Human authority escalation notification and card dispatch",
        ),
        LifecycleStateRoute(
            state=ChangeState.AUTHORIZED,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=approval_topic_id,
            description="Authority confirmed; proceeding to execution",
        ),
        LifecycleStateRoute(
            state=ChangeState.EXECUTING,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=agent_work_topic_id,
            description="Release steward / migration engineer execution dispatch",
        ),
        LifecycleStateRoute(
            state=ChangeState.VERIFYING,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=evidence_topic_id,
            description="Post-execution verification and test suite checks",
        ),
        LifecycleStateRoute(
            state=ChangeState.CERTIFYING,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=evidence_topic_id,
            description="Evidence auditor blind semantic certification",
        ),
        LifecycleStateRoute(
            state=ChangeState.RETRY_SCHEDULED,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=retry_topic_id,
            description="Transient failure backoff schedule and retry dispatch",
        ),
        LifecycleStateRoute(
            state=ChangeState.COMPENSATING,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=agent_work_topic_id,
            description="Saga rollback and compensating action dispatch",
        ),
        LifecycleStateRoute(
            state=ChangeState.BLOCKED,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=evidence_topic_id,
            description="Policy or boundary block terminal transition",
        ),
        LifecycleStateRoute(
            state=ChangeState.COMPLETE,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=evidence_topic_id,
            description="Successful change lifecycle completion and passport sealing",
        ),
        LifecycleStateRoute(
            state=ChangeState.FAILED,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            secondary_topic_id=dead_letter_topic_id,
            description="Terminal failure transition and dead-letter diagnostic handoff",
        ),
        LifecycleStateRoute(
            state=ChangeState.CANCELLED,
            primary_topic_id=lifecycle_topic_id,
            logical_kind=LogicalTopicKind.CHANGE_LIFECYCLE,
            description="Explicit cancellation terminal transition",
        ),
    ]

    return TopologyConfig(
        schema_version=CANONICAL_TOPOLOGY_VERSION,
        topics=topics,
        subscriptions=subscriptions,
        lifecycle_routes=routes,
    )


def load_topology_from_json(json_str: str) -> TopologyConfig:
    """Load and validate topology from JSON string."""
    data = json.loads(json_str)
    return TopologyConfig.model_validate(data)
