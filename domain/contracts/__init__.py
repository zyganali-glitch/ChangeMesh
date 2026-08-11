"""ChangeMesh domain contracts — provider-neutral core contract layer.

This package exposes the five public P-05.01 domain contracts.
Provider-specific layers (ADK, Firestore, Pub/Sub, GitHub, UI) depend
inward on these contracts.  These contracts never depend outward on
providers.
"""

from domain.contracts.data_class import DataClassification, DataClassLevel
from domain.contracts.success_criterion import SuccessCriterion
from domain.contracts.change_request import ChangeRequest
from domain.contracts.agent_descriptor import AgentDescriptor
from domain.contracts.tool_descriptor import ToolDescriptor

__all__ = [
    "DataClassLevel",
    "DataClassification",
    "SuccessCriterion",
    "ChangeRequest",
    "AgentDescriptor",
    "ToolDescriptor",
]
