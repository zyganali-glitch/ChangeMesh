from enum import Enum

from pydantic import BaseModel, ConfigDict

from src.audit.audit_bundle import AuditBundle
from src.audit.claim_derivation import NeutralClaim


class SemanticVerdict(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INSUFFICIENT = "INSUFFICIENT"


class ClaimAuditResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    verdict: SemanticVerdict
    citations: tuple[str, ...] = ()
    reasoning: str
    authority: str = "GEMINI_SEMANTIC_JUDGMENT"


class SemanticAuditReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    change_id: str
    bundle_id: str
    results: tuple[ClaimAuditResult, ...]
    total_claims: int
    supports_count: int
    contradicts_count: int
    insufficient_count: int
    authority: str = "GEMINI_SEMANTIC_JUDGMENT"
    evidence_mode: str


class SemanticAuditor:
    """Independent Gemini audit (or deterministic fixture for demo)."""

    def audit_claims(
        self, bundle: AuditBundle, use_live_gemini: bool = False
    ) -> SemanticAuditReport:
        results = []
        for claim in bundle.claims:
            if not use_live_gemini:
                res = self._fixture_evaluate_claim(claim, bundle.evidence_summaries)
            else:
                # Not implemented in MVP
                res = ClaimAuditResult(
                    claim_id=claim.claim_id,
                    verdict=SemanticVerdict.INSUFFICIENT,
                    reasoning="Live Gemini not implemented in MVP",
                    citations=(),
                )
            results.append(res)

        supports = sum(1 for r in results if r.verdict == SemanticVerdict.SUPPORTS)
        contradicts = sum(1 for r in results if r.verdict == SemanticVerdict.CONTRADICTS)
        insufficient = sum(1 for r in results if r.verdict == SemanticVerdict.INSUFFICIENT)

        return SemanticAuditReport(
            change_id=bundle.change_id,
            bundle_id=bundle.bundle_id,
            results=tuple(results),
            total_claims=len(results),
            supports_count=supports,
            contradicts_count=contradicts,
            insufficient_count=insufficient,
            evidence_mode="LIVE_WRITE" if use_live_gemini else "FIXTURE",
        )

    def _fixture_evaluate_claim(
        self, claim: NeutralClaim, evidence: dict[str, str]
    ) -> ClaimAuditResult:
        if not claim.evidence_keys:
            return ClaimAuditResult(
                claim_id=claim.claim_id,
                verdict=SemanticVerdict.INSUFFICIENT,
                reasoning="Missing evidence keys",
                citations=(),
            )

        citations = []
        for key in claim.evidence_keys:
            val = evidence.get(key)
            if not val:
                return ClaimAuditResult(
                    claim_id=claim.claim_id,
                    verdict=SemanticVerdict.INSUFFICIENT,
                    reasoning=f"Evidence {key} missing or empty",
                    citations=(),
                )
            citations.append(key)

        return ClaimAuditResult(
            claim_id=claim.claim_id,
            verdict=SemanticVerdict.SUPPORTS,
            reasoning="Fixture deterministically supports non-empty evidence",
            citations=tuple(citations),
        )
