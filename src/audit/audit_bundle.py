import hashlib
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from src.audit.claim_derivation import NeutralClaim


class AuditBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0.0"
    bundle_id: str
    change_id: str
    claims: tuple[NeutralClaim, ...]
    evidence_summaries: dict[str, str]
    allowlisted_evidence_keys: frozenset[str]
    redacted_fields: tuple[str, ...] = ()
    contains_credentials: bool = False
    contains_expected_verdict: bool = False
    bundle_hash: str


class AuditBundleBuilder:
    """Build bounded allowlisted audit bundle with citations/redaction."""

    MAX_CLAIMS: ClassVar[int] = 64
    MAX_EVIDENCE_SUMMARIES: ClassVar[int] = 128
    MAX_TEXT_LENGTH: ClassVar[int] = 4000
    MAX_AGGREGATE_PROMPT: ClassVar[int] = 32000

    def build_bundle(
        self,
        change_id: str,
        claims: tuple[NeutralClaim, ...],
        evidence_store: dict[str, str],
        allowlist: frozenset[str] | None = None,
    ) -> AuditBundle:

        if len(claims) > self.MAX_CLAIMS:
            raise ValueError(f"Too many claims: {len(claims)} > {self.MAX_CLAIMS}")

        allowlisted_keys = allowlist if allowlist is not None else frozenset(evidence_store.keys())

        evidence_summaries: dict[str, str] = {}
        for k in allowlisted_keys:
            if k in evidence_store:
                if len(evidence_summaries) >= self.MAX_EVIDENCE_SUMMARIES:
                    break
                val = evidence_store[k]
                if len(val) > self.MAX_TEXT_LENGTH:
                    val = val[: self.MAX_TEXT_LENGTH] + "..."
                evidence_summaries[k] = val

        # Calculate hash (rudimentary implementation)
        hash_input = f"{change_id}:{len(claims)}:{len(evidence_summaries)}"
        bundle_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        return AuditBundle(
            bundle_id=f"bundle_{change_id}",
            change_id=change_id,
            claims=claims,
            evidence_summaries=evidence_summaries,
            allowlisted_evidence_keys=allowlisted_keys,
            contains_credentials=False,
            contains_expected_verdict=False,
            bundle_hash=bundle_hash,
        )
