"""ChangeMesh domain contracts — provider-neutral core contract layer.

This package exposes the five public P-05.01 domain contracts.
Provider-specific layers (ADK, Firestore, Pub/Sub, GitHub, UI) depend
inward on these contracts.  These contracts never depend outward on
providers.
"""

from .change_request import ChangeRequest
from .success_criterion import SuccessCriterion
from .agent_descriptor import AgentDescriptor
from .tool_descriptor import ToolDescriptor
from .data_class import DataClass, DataClassLevel

from .change_lifecycle import (
    ChangeState,
    IllegalTransitionError,
    CHANGE_LIFECYCLE_VERSION,
    can_transition,
    require_transition,
    is_terminal,
)

__all__ = [
    "DataClassLevel",
    "DataClass",
    "SuccessCriterion",
    "ChangeRequest",
    "AgentDescriptor",
    "ToolDescriptor",
    "ChangeState",
    "IllegalTransitionError",
    "CHANGE_LIFECYCLE_VERSION",
    "can_transition",
    "require_transition",
    "is_terminal",
]
