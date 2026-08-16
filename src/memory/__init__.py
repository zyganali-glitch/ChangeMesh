"""ChangeMesh Memory Trust Layer.

P-11: Epistemic trust evaluation, contradiction and supersession tracking,
prompt-injection quarantine, and local memory bank integration.
"""

from domain.contracts.memory import MemoryRecord, MemoryTrustStatus
from src.memory.memory_bank import InMemoryMemoryBank, MemoryBank
from src.memory.quarantine import MemoryQuarantineEngine, PromptInjectionDetectedError
from src.memory.supersession import ContradictionDetectionResult, MemorySupersessionManager
from src.memory.trust_layer import EpistemicTrustEvaluation, MemoryTrustEvaluator

__all__ = [
    "MemoryRecord",
    "MemoryTrustStatus",
    "EpistemicTrustEvaluation",
    "MemoryTrustEvaluator",
    "ContradictionDetectionResult",
    "MemorySupersessionManager",
    "PromptInjectionDetectedError",
    "MemoryQuarantineEngine",
    "MemoryBank",
    "InMemoryMemoryBank",
]
