"""ChangeMesh P-07.01 — Change Orchestrator ADK Skeleton Tests.

Tests proving all P-07.01 acceptance criteria and invariants:
1. Orchestrator uses a genuine Google ADK BaseAgent abstraction.
2. Construction and import without credentials or network.
3. Typed ChangeRequest domain contract is accepted.
4. Returns ChangeRuntimeState with a distinct, non-blank change_id.
5. Initial lifecycle state is strictly ChangeState.RECEIVED.
6. request_id remains intact and distinguishable from change_id.
7. Passed ChangeRequest is not mutated.
8. Invalid/untyped input fails closed (raises TypeError).
9. Deterministic ID generator injection allows exact control without randomness.
10. Blank or invalid generated change_id fails closed.
11. Generated change_id identical to request_id fails closed.
12. ChangeRuntimeState is frozen and immutable.
13. Multiple initializations do not share mutable state.
14. Alias method receive_change_request behaves identically to initialize_change.
15. Zero external writes (no Firestore, Pub/Sub, Cloud Run, GitHub, network).
16. Zero Gemini / Vertex AI model invocations.
17. Local ADK integration/smoke boundary with Runner and InMemorySessionService.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from google.adk.agents.base_agent import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from pydantic import BaseModel, ValidationError

from domain.contracts.change_lifecycle import ChangeState
from domain.contracts.change_request import ChangeRequest
from domain.contracts.data_class import DataClassLevel
from domain.contracts.success_criterion import SuccessCriterion
from src.agents.change_orchestrator import ChangeOrchestrator, ChangeRuntimeState


def _make_valid_change_request(
    request_id: str = "req-audit-001",
    title: str = "Add column to users table",
    description: str = "Add non-sensitive column with deterministic verification",
    target_systems: list[str] | None = None,
    data_classification: DataClassLevel = DataClassLevel.INTERNAL,
) -> ChangeRequest:
    """Helper to construct a valid typed ChangeRequest domain contract."""
    return ChangeRequest(
        schema_version="1.0.0",
        request_id=request_id,
        title=title,
        description=description,
        target_systems=target_systems or ["repo-enterprise-db"],
        data_classification=data_classification,
        success_criteria=[
            SuccessCriterion(
                schema_version="1.0.0",
                criterion_id="sc-001",
                description="Schema change applied without errors",
                verification_method="deterministic",
                required_evidence_types=["unit_test", "schema_validation"],
            )
        ],
        requested_by="operator@changemesh.internal",
        requested_at=datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


# ===========================================================================
# 1. Genuine Google ADK Integration & Construction
# ===========================================================================


def test_adk_agent_inheritance_and_properties() -> None:
    """Verify ChangeOrchestrator is a genuine Google ADK BaseAgent subclass."""
    assert issubclass(ChangeOrchestrator, BaseAgent)

    orch = ChangeOrchestrator()
    assert isinstance(orch, BaseAgent)
    assert orch.name == "change_orchestrator"
    assert "Change Orchestrator" in orch.description


def test_construction_without_credentials_or_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify construction succeeds in an environment stripped of credentials/network."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    orch = ChangeOrchestrator()
    assert orch.name == "change_orchestrator"
    assert isinstance(orch, BaseAgent)


# ===========================================================================
# 2. Typed Intake Boundary & State Initialization
# ===========================================================================


def test_typed_change_request_accepted() -> None:
    """Verify typed ChangeRequest is accepted and produces ChangeRuntimeState."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request(request_id="req-20260815-01")

    state = orch.initialize_change(cr)

    assert isinstance(state, ChangeRuntimeState)
    assert state.request_id == "req-20260815-01"
    assert state.state == ChangeState.RECEIVED
    assert state.created_at.tzinfo == timezone.utc


def test_change_id_distinct_and_non_blank() -> None:
    """Verify change_id is non-blank, string, and distinct from request_id."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request(request_id="req-distinct-id")

    state = orch.initialize_change(cr)

    assert isinstance(state.change_id, str)
    assert len(state.change_id.strip()) > 0
    assert state.change_id != cr.request_id


def test_initial_state_strictly_received() -> None:
    """Verify initial lifecycle state is strictly RECEIVED and not advanced."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request()

    state = orch.initialize_change(cr)

    assert state.state == ChangeState.RECEIVED
    assert state.state != ChangeState.DISCOVERING
    assert state.state != ChangeState.QUALIFYING
    assert state.state != ChangeState.REHEARSING
    assert state.state != ChangeState.AUTHORIZED
    assert state.state != ChangeState.EXECUTING


def test_request_id_preserved_and_distinguishable() -> None:
    """Verify request_id remains intact and distinguishable from change_id."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request(request_id="req-unique-9988")

    state = orch.initialize_change(cr)

    assert state.request_id == "req-unique-9988"
    assert state.request_id == cr.request_id
    assert state.change_id != state.request_id


def test_change_request_not_mutated() -> None:
    """Verify passed ChangeRequest is not mutated by the intake boundary."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request(request_id="req-immutable-01")
    original_dump = cr.model_dump()

    orch.initialize_change(cr)

    assert cr.model_dump() == original_dump
    assert cr.request_id == "req-immutable-01"


# ===========================================================================
# 3. Fail-Closed Validation & Edge Cases
# ===========================================================================


class _DummyModel(BaseModel):
    pass


@pytest.mark.parametrize(
    "invalid_input",
    [
        {"request_id": "dict_input", "title": "Not a ChangeRequest"},
        "plain string request",
        12345,
        None,
        [1, 2, 3],
        _DummyModel(),
    ],
)
def test_invalid_untyped_input_fails_closed(invalid_input: Any) -> None:
    """Verify untyped or invalid inputs fail closed with TypeError."""
    orch = ChangeOrchestrator()

    with pytest.raises(TypeError, match="Expected ChangeRequest domain contract instance"):
        orch.initialize_change(invalid_input)


def test_deterministic_id_generator_injection() -> None:
    """Verify ID generation is injectable and deterministically controllable."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request(request_id="req-fixed-01")

    state = orch.initialize_change(
        cr,
        id_generator=lambda: "change-det-fixed-12345",
    )

    assert state.change_id == "change-det-fixed-12345"
    assert state.request_id == "req-fixed-01"


@pytest.mark.parametrize("blank_id", ["", "   ", "\t\n"])
def test_blank_generated_id_fails_closed(blank_id: str) -> None:
    """Verify blank generated change_id raises ValueError."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request()

    with pytest.raises(ValueError, match="Generated change_id must not be blank"):
        orch.initialize_change(cr, id_generator=lambda: blank_id)


def test_change_id_equal_to_request_id_fails_closed() -> None:
    """Verify generated change_id identical to request_id raises ValueError."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request(request_id="req-conflict-same")

    with pytest.raises(ValueError, match="must be distinct from request_id"):
        orch.initialize_change(cr, id_generator=lambda: "req-conflict-same")


def test_state_immutability() -> None:
    """Verify ChangeRuntimeState is frozen and rejects field mutation."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request()
    state = orch.initialize_change(cr)

    with pytest.raises(ValidationError):
        state.change_id = "new-id"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        state.state = ChangeState.DISCOVERING  # type: ignore[misc]


def test_separate_initializations_isolated() -> None:
    """Verify two distinct initializations create independent state without shared references."""
    orch = ChangeOrchestrator()
    cr1 = _make_valid_change_request(request_id="req-001")
    cr2 = _make_valid_change_request(request_id="req-002")

    state1 = orch.initialize_change(cr1)
    state2 = orch.initialize_change(cr2)

    assert state1.change_id != state2.change_id
    assert state1.request_id == "req-001"
    assert state2.request_id == "req-002"
    assert state1 is not state2


def test_receive_change_request_alias() -> None:
    """Verify receive_change_request alias matches initialize_change behavior."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request(request_id="req-alias-test")

    state = orch.receive_change_request(
        cr,
        id_generator=lambda: "change-alias-456",
    )

    assert state.change_id == "change-alias-456"
    assert state.request_id == "req-alias-test"
    assert state.state == ChangeState.RECEIVED


# ===========================================================================
# 4. Zero External Writes & Zero Model Invocations
# ===========================================================================


def test_zero_external_writes_during_intake() -> None:
    """Verify initialization performs zero external writes or network calls."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request()

    with patch("urllib.request.urlopen") as mock_url, patch("socket.socket") as mock_socket:
        state = orch.initialize_change(cr)
        assert state.state == ChangeState.RECEIVED
        assert mock_url.call_count == 0
        assert mock_socket.call_count == 0


def test_no_gemini_or_vertex_invocation() -> None:
    """Verify no Gemini / Vertex AI model client or inference is invoked."""
    orch = ChangeOrchestrator()
    cr = _make_valid_change_request()

    with patch("google.genai.Client") as mock_genai_client:
        state = orch.initialize_change(cr)
        assert state.state == ChangeState.RECEIVED
        assert mock_genai_client.call_count == 0


# ===========================================================================
# 5. Local ADK Runner / Smoke Integration Boundary
# ===========================================================================


def test_local_adk_runner_smoke_integration() -> None:
    """Verify ChangeOrchestrator integrates with real Google ADK Runner locally."""
    orch = ChangeOrchestrator()
    session_service = InMemorySessionService()

    runner = Runner(
        agent=orch,
        app_name="changemesh_local_test",
        session_service=session_service,
        auto_create_session=True,
    )

    message = Content(role="user", parts=[Part.from_text(text="run")])
    events = list(
        runner.run(user_id="local_tester", session_id="test_sess_001", new_message=message)
    )

    assert len(events) >= 1
    assert any(isinstance(ev, Event) for ev in events)
    assert any(getattr(ev, "author", None) == "change_orchestrator" for ev in events)
    assert any(getattr(ev, "turn_complete", False) is True for ev in events)
