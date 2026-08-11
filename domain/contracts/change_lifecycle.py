from enum import Enum
from typing import Mapping, FrozenSet

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
ALLOWED_TRANSITIONS: Mapping[ChangeState, FrozenSet[ChangeState]] = {
    ChangeState.RECEIVED: frozenset({
        ChangeState.DISCOVERING, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.DISCOVERING: frozenset({
        ChangeState.QUALIFYING, ChangeState.RETRY_SCHEDULED, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.QUALIFYING: frozenset({
        ChangeState.REHEARSING, ChangeState.RETRY_SCHEDULED, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.REHEARSING: frozenset({
        ChangeState.GROUNDED, ChangeState.RETRY_SCHEDULED, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.GROUNDED: frozenset({
        ChangeState.AUTHORIZED, ChangeState.AWAITING_AUTHORITY, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.AWAITING_AUTHORITY: frozenset({
        ChangeState.AUTHORIZED, ChangeState.BLOCKED, ChangeState.CANCELLED
    }),
    ChangeState.AUTHORIZED: frozenset({
        ChangeState.EXECUTING, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.EXECUTING: frozenset({
        ChangeState.VERIFYING, ChangeState.RETRY_SCHEDULED, ChangeState.COMPENSATING, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.VERIFYING: frozenset({
        ChangeState.CERTIFYING, ChangeState.RETRY_SCHEDULED, ChangeState.COMPENSATING, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.CERTIFYING: frozenset({
        ChangeState.COMPLETE, ChangeState.RETRY_SCHEDULED, ChangeState.BLOCKED, ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.RETRY_SCHEDULED: frozenset({
        ChangeState.DISCOVERING, ChangeState.QUALIFYING, ChangeState.REHEARSING, 
        ChangeState.EXECUTING, ChangeState.VERIFYING, ChangeState.CERTIFYING, 
        ChangeState.CANCELLED, ChangeState.FAILED
    }),
    ChangeState.COMPENSATING: frozenset({
        ChangeState.RETRY_SCHEDULED, ChangeState.FAILED, ChangeState.CANCELLED, ChangeState.BLOCKED
    }),
    # Terminal states have no outgoing transitions
    ChangeState.BLOCKED: frozenset(),
    ChangeState.COMPLETE: frozenset(),
    ChangeState.FAILED: frozenset(),
    ChangeState.CANCELLED: frozenset()
}

def is_terminal(state: ChangeState) -> bool:
    """Returns True if the state has no outgoing transitions."""
    if not isinstance(state, ChangeState):
        raise ValueError(f"Unknown state: {state}")
    return len(ALLOWED_TRANSITIONS[state]) == 0

def can_transition(current: ChangeState, target: ChangeState) -> bool:
    """Returns True if the transition from current to target is allowed."""
    if not isinstance(current, ChangeState):
        return False
    if not isinstance(target, ChangeState):
        return False
    return target in ALLOWED_TRANSITIONS[current]

def require_transition(current: ChangeState, target: ChangeState) -> None:
    """
    Asserts that the transition from current to target is allowed.
    Raises IllegalTransitionError if it is not.
    """
    if not isinstance(current, ChangeState):
        raise IllegalTransitionError(f"Invalid current state type: {type(current)}")
    if not isinstance(target, ChangeState):
        raise IllegalTransitionError(f"Invalid target state type: {type(target)}")
        
    if not can_transition(current, target):
        raise IllegalTransitionError(
            f"Illegal transition from {current.value} to {target.value}"
        )
