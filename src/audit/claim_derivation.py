from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ClaimType(str, Enum):
    MISSION_CLAIM = "MISSION_CLAIM"
    CHANGE_CLAIM = "CHANGE_CLAIM"
    TEST_CLAIM = "TEST_CLAIM"


class NeutralClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    claim_type: ClaimType
    statement: str
    evidence_keys: tuple[str, ...]
    source_criterion_id: str | None = None


class ClaimDerivationEngine:
    """Derive neutral claims from success criteria and evidence.

    Claims MUST be neutral - no expected verdict, label, or hidden answer key.
    """

    FORBIDDEN_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "expected_result",
            "expected_verdict",
            "expected_answer",
            "should_pass",
            "correct_answer",
            "expected_label",
        }
    )

    def derive_claims(
        self, success_criteria: list[dict], evidence_refs: list[str]
    ) -> tuple[NeutralClaim, ...]:
        claims = []
        for i, crit in enumerate(success_criteria):
            statement = crit.get("statement", f"Criterion {i} is met.")
            claims.append(
                NeutralClaim(
                    claim_id=f"claim_{i}",
                    claim_type=ClaimType.MISSION_CLAIM,
                    statement=statement,
                    evidence_keys=tuple(evidence_refs),
                    source_criterion_id=crit.get("id"),
                )
            )
        return tuple(claims)

    def validate_neutrality(self, claims: tuple[NeutralClaim, ...]) -> tuple[str, ...]:
        """Return tuple of violations if any claim contains forbidden fields."""
        violations = []
        for claim in claims:
            statement_lower = claim.statement.lower()
            for forbidden in self.FORBIDDEN_FIELDS:
                if forbidden in statement_lower:
                    violations.append(
                        f"Claim {claim.claim_id} contains forbidden term: {forbidden}"
                    )
        return tuple(violations)
