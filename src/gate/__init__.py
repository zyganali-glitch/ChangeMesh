"""ChangeMesh Reversibility Gate and Approval Compression package.

P-14: Implements deterministic reversibility classification, 1-screen compressed
decision packets, cryptographic HMAC approval tokens, and Policy Guardian gate evaluation.
"""

from src.gate.compression import ApprovalCompressionEngine
from src.gate.policy_guardian_gate import PolicyGateEvaluationResult, PolicyGuardianGate
from src.gate.reversibility import (
    ReversibilityAssessment,
    ReversibilityClass,
    ReversibilityClassifier,
)
from src.gate.token import (
    ApprovalTokenManager,
    ApprovalValidationResult,
    SignedApprovalToken,
)

__all__ = [
    "ReversibilityClass",
    "ReversibilityAssessment",
    "ReversibilityClassifier",
    "ApprovalCompressionEngine",
    "SignedApprovalToken",
    "ApprovalValidationResult",
    "ApprovalTokenManager",
    "PolicyGateEvaluationResult",
    "PolicyGuardianGate",
]
