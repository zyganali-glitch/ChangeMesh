from enum import Enum
from types import MappingProxyType
from typing import FrozenSet, Mapping, Optional


class ChangeState(str, Enum):
    """
    Canonical ChangeMesh lifecycle states.
    Provider-neutral domain contract defining the exact progression of a change.
    """

    RECEIVED = "RECEIVED"
    DISCOVERING = "DISCOVERING"
    QUALIFYING = "QUALIFYING"
    REHEARSING = "REHEARSING"
    GROUNDED = "GROUNDED"

    # Authority Branch
    AWAITING_AUTHORITY = "AWAITING_AUTHORITY"
    AUTHORIZED = "AUTHORIZED"

    # Execution & Verification
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    CERTIFYING = "CERTIFYING"

    # Recovery Branches
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    COMPENSATING = "COMPENSATING"

    # Terminal States
    BLOCKED = "BLOCKED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


CHANGE_LIFECYCLE_VERSION = "1.0.0"


class IllegalTransitionError(ValueError):
    """Raised when a state transition violates the ALLOWED_TRANSITIONS graph."""

    pass


# The definitive executable transition graph.
# Every ChangeState appears exactly once as a key.
ALLOWED_TRANSITIONS: Mapping[ChangeState, FrozenSet[ChangeState]] = MappingProxyType(
    {
        ChangeState.RECEIVED: frozenset(
            {
                ChangeState.DISCOVERING,
                ChangeState.BLOCKED,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.DISCOVERING: frozenset(
            {
                ChangeState.QUALIFYING,
                ChangeState.RETRY_SCHEDULED,
                ChangeState.BLOCKED,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.QUALIFYING: frozenset(
            {
                ChangeState.REHEARSING,
                ChangeState.RETRY_SCHEDULED,
                ChangeState.BLOCKED,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.REHEARSING: frozenset(
            {
                ChangeState.GROUNDED,
                ChangeState.RETRY_SCHEDULED,
                ChangeState.BLOCKED,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.GROUNDED: frozenset(
            {
                ChangeState.AUTHORIZED,
                ChangeState.AWAITING_AUTHORITY,
                ChangeState.BLOCKED,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.AWAITING_AUTHORITY: frozenset(
            {ChangeState.AUTHORIZED, ChangeState.BLOCKED, ChangeState.CANCELLED}
        ),
        ChangeState.AUTHORIZED: frozenset(
            {ChangeState.EXECUTING, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED}
        ),
        ChangeState.EXECUTING: frozenset(
            {
                ChangeState.VERIFYING,
                ChangeState.RETRY_SCHEDULED,
                ChangeState.COMPENSATING,
                ChangeState.BLOCKED,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.VERIFYING: frozenset(
            {
                ChangeState.CERTIFYING,
                ChangeState.RETRY_SCHEDULED,
                ChangeState.COMPENSATING,
                ChangeState.BLOCKED,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.CERTIFYING: frozenset(
            {
                ChangeState.COMPLETE,
                ChangeState.RETRY_SCHEDULED,
                ChangeState.BLOCKED,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.RETRY_SCHEDULED: frozenset(
            {
                ChangeState.DISCOVERING,
                ChangeState.QUALIFYING,
                ChangeState.REHEARSING,
                ChangeState.EXECUTING,
                ChangeState.VERIFYING,
                ChangeState.CERTIFYING,
                ChangeState.COMPENSATING,
                ChangeState.CANCELLED,
                ChangeState.FAILED,
            }
        ),
        ChangeState.COMPENSATING: frozenset(
            {
                ChangeState.RETRY_SCHEDULED,
                ChangeState.FAILED,
                ChangeState.CANCELLED,
                ChangeState.BLOCKED,
            }
        ),
        # Terminal states have no outgoing transitions
        ChangeState.BLOCKED: frozenset(),
        ChangeState.COMPLETE: frozenset(),
        ChangeState.FAILED: frozenset(),
        ChangeState.CANCELLED: frozenset(),
    }
)

# Defines which states are allowed to resume from a given retry origin.
# Terminal exits from RETRY_SCHEDULED are handled independently of origin.
RETRY_RESUME_TARGETS: Mapping[ChangeState, FrozenSet[ChangeState]] = MappingProxyType(
    {
        ChangeState.DISCOVERING: frozenset({ChangeState.DISCOVERING}),
        ChangeState.QUALIFYING: frozenset({ChangeState.QUALIFYING}),
        ChangeState.REHEARSING: frozenset({ChangeState.REHEARSING}),
        ChangeState.EXECUTING: frozenset({ChangeState.EXECUTING}),
        ChangeState.VERIFYING: frozenset({ChangeState.VERIFYING}),
        ChangeState.CERTIFYING: frozenset({ChangeState.CERTIFYING}),
        ChangeState.COMPENSATING: frozenset({ChangeState.COMPENSATING}),
    }
)

# Terminal exits allowed explicitly from RETRY_SCHEDULED
RETRY_TERMINAL_EXITS: FrozenSet[ChangeState] = frozenset(
    {ChangeState.CANCELLED, ChangeState.FAILED}
)


def is_terminal(state: ChangeState) -> bool:
    """Returns True if the state has no outgoing transitions."""
    if not isinstance(state, ChangeState):
        raise ValueError(f"Unknown state: {state}")
    return len(ALLOWED_TRANSITIONS[state]) == 0


def can_transition(
    current: ChangeState, target: ChangeState, *, retry_origin: Optional[ChangeState] = None
) -> bool:
    """Returns True if the transition from current to target is allowed."""
    if not isinstance(current, ChangeState):
        return False
    if not isinstance(target, ChangeState):
        return False

    # Check general transition legality
    if target not in ALLOWED_TRANSITIONS[current]:
        return False

    # Retry resume logic
    if current == ChangeState.RETRY_SCHEDULED:
        # 1. retry_origin must be a ChangeState
        if not isinstance(retry_origin, ChangeState):
            return False

        # 2. retry_origin must be a valid retriable origin
        if retry_origin not in RETRY_RESUME_TARGETS:
            return False

        # 3. If target is a terminal exit, allow it after origin validation
        if target in RETRY_TERMINAL_EXITS:
            return True

        # 4. Otherwise target must be the exact bounded resume target for that origin
        return target in RETRY_RESUME_TARGETS[retry_origin]

    return True


def require_transition(
    current: ChangeState, target: ChangeState, *, retry_origin: Optional[ChangeState] = None
) -> None:
    """
    Asserts that the transition from current to target is allowed.
    Raises IllegalTransitionError if it is not.
    """
    if not isinstance(current, ChangeState):
        raise IllegalTransitionError(f"Invalid current state type: {type(current)}")
    if not isinstance(target, ChangeState):
        raise IllegalTransitionError(f"Invalid target state type: {type(target)}")

    if not can_transition(current, target, retry_origin=retry_origin):
        if current == ChangeState.RETRY_SCHEDULED and isinstance(retry_origin, ChangeState):
            raise IllegalTransitionError(
                f"Illegal transition from {current.value} to {target.value} with retry_origin={retry_origin.value}"
            )
        raise IllegalTransitionError(f"Illegal transition from {current.value} to {target.value}")
