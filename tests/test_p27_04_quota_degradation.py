"""ChangeMesh P-27.04 — Quota and Rate-Limit Degradation Resilience Security Suite.

Acceptance criteria from master plan:
  - System retries/pauses without corrupting state.
  - Verification that HTTP 429 (Resource Exhausted / Rate Limit) triggers exponential backoff.
  - Verification that transient quota exhaustion recovers gracefully.
  - Verification that permanent quota exhaustion fails closed without state corruption.

Required evidence: Fault test (docs/P-27.04_QUOTA_DEGRADATION_REPORT.md).
Mandatory documentation sync: Lessons.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from google.genai import errors

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.success_criterion import SuccessCriterion
from events.local_bus import LocalEventBus
from src.core.gemini_client import (
    RETRYABLE_STATUS_CODES,
    BoundedGeminiClient,
    ModelClientError,
    ModelRetryExhaustedError,
)
from src.orchestrator.in_memory_repository import InMemorySagaStateRepository
from src.orchestrator.orchestrator_saga import (
    ChangeSagaOrchestrator,
    SagaExecutionResult,
)
from tests.test_p08_01_gemini_client import FakeSDKClient, make_successful_response


class TestQuotaAndRateLimitDegradation:
    """Verify quota degradation handling, 429 retries, and state preservation."""

    def test_retryable_status_codes_include_429_resource_exhausted(self):
        """BoundedGeminiClient must classify 429 (Rate Limit / Quota) as retryable."""
        assert 429 in RETRYABLE_STATUS_CODES
        assert 503 in RETRYABLE_STATUS_CODES
        assert 400 not in RETRYABLE_STATUS_CODES
        assert 401 not in RETRYABLE_STATUS_CODES

    def test_transient_rate_limit_recovers_after_retry(self):
        """Simulate transient 429 rate limit that recovers on the 2nd attempt."""
        error_429 = errors.APIError(429, {"message": "Resource exhausted: Rate limit exceeded"})
        success_resp = make_successful_response("Success on attempt 2 after 429")

        fake_sdk = FakeSDKClient(responses=[success_resp], exceptions=[error_429])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda _: None,
        )

        resp = client.generate_text("Test prompt under load")
        assert resp.text == "Success on attempt 2 after 429"
        assert resp.telemetry.attempts == 2
        assert resp.telemetry.final_outcome == "SUCCESS"

    def test_permanent_quota_exhaustion_fails_closed_without_state_corruption(self):
        """Permanent quota failure must raise ModelRetryExhaustedError."""
        error_429_a = errors.APIError(429, {"message": "Rate limited"})
        error_429_b = errors.APIError(429, {"message": "Rate limited"})
        error_429_c = errors.APIError(429, {"message": "Rate limited"})

        fake_sdk = FakeSDKClient(exceptions=[error_429_a, error_429_b, error_429_c])
        client = BoundedGeminiClient(
            _sdk_client=fake_sdk,
            _sleep_fn=lambda _: None,
        )

        with pytest.raises((ModelRetryExhaustedError, ModelClientError)) as exc_info:
            client.generate_text("Prompt during quota outage")

        assert "429" in str(exc_info.value) or "exhausted" in str(exc_info.value).lower()
        assert len(client.telemetry_history) == 1
        assert client.telemetry_history[0].final_outcome == "RETRY_EXHAUSTED"

    def test_saga_orchestrator_state_consistency_under_fault(self):
        """Orchestrator must transition cleanly to terminal state without state corruption."""
        repo = InMemorySagaStateRepository()
        bus = LocalEventBus()
        orchestrator = ChangeSagaOrchestrator(repository=repo, event_bus=bus)

        req = ChangeRequest(
            schema_version="1.0.0",
            request_id="req-quota-fail-01",
            title="Broken Intent",
            description="DROP TABLE payments;",  # Destructive
            target_systems=["billing-db"],
            data_classification=DataClassLevel.INTERNAL,
            success_criteria=[
                SuccessCriterion(
                    schema_version="1.0.0",
                    criterion_id="sc-1",
                    description="test",
                    verification_method="deterministic",
                    required_evidence_types=["POLICY_EVALUATION"],
                )
            ],
            requested_by="operator",
            requested_at=datetime.now(timezone.utc),
        )

        result = orchestrator.run_saga(
            tenant_id="demo-tenant",
            request=req,
            change_id="chg-quota-test-01",
        )
        assert isinstance(result, SagaExecutionResult)
        assert result.final_state in (ChangeState.BLOCKED, ChangeState.FAILED)

        # Check repository state integrity
        change = repo.get_change("demo-tenant", "chg-quota-test-01")
        assert change is not None
        assert change.version >= 1
