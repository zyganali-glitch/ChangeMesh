"""ChangeMesh ShadowLab Rehearsal Twin package.

P-13: Synthetic twin execution sandbox, deterministic fault injection,
simulation-labeled evidence generation, and bounded re-rehearsal plan correction.
"""

from src.shadowlab.runner import ShadowLabRunner
from src.shadowlab.scenarios import (
    FaultType,
    InjectedFault,
    RehearsalOutcome,
    ShadowScenario,
    get_standard_shadow_scenarios,
)
from src.shadowlab.tool_doubles import (
    SimulatedApiClient,
    SimulatedDatabaseClient,
    SimulatedGitClient,
)

__all__ = [
    "FaultType",
    "InjectedFault",
    "ShadowScenario",
    "RehearsalOutcome",
    "get_standard_shadow_scenarios",
    "SimulatedDatabaseClient",
    "SimulatedApiClient",
    "SimulatedGitClient",
    "ShadowLabRunner",
]
