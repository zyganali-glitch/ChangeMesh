import pytest

from domain.contracts.change_lifecycle import (
    ChangeState,
    IllegalTransitionError,
    ALLOWED_TRANSITIONS,
    can_transition,
    require_transition,
    is_terminal,
    CHANGE_LIFECYCLE_VERSION
)

class TestP0502Lifecycle:
    """State machine validation tests corresponding to LIFECYCLE-001 through LIFECYCLE-020."""

    def test_lifecycle_001_declared_states_are_valid(self):
        """LIFECYCLE-001: All declared states are valid enum members."""
        expected_states = {
            "RECEIVED", "DISCOVERING", "QUALIFYING", "REHEARSING", "GROUNDED",
            "AWAITING_AUTHORITY", "AUTHORIZED", "EXECUTING", "VERIFYING", "CERTIFYING",
            "RETRY_SCHEDULED", "COMPENSATING", "BLOCKED", "COMPLETE", "FAILED", "CANCELLED"
        }
        actual_states = {state.value for state in ChangeState}
        assert actual_states == expected_states

    def test_lifecycle_002_happy_path_transitions_accepted(self):
        """LIFECYCLE-002: Happy-path transitions are accepted."""
        happy_path = [
            ChangeState.RECEIVED,
            ChangeState.DISCOVERING,
            ChangeState.QUALIFYING,
            ChangeState.REHEARSING,
            ChangeState.GROUNDED,
            ChangeState.AUTHORIZED,
            ChangeState.EXECUTING,
            ChangeState.VERIFYING,
            ChangeState.CERTIFYING,
            ChangeState.COMPLETE
        ]
        
        for i in range(len(happy_path) - 1):
            assert can_transition(happy_path[i], happy_path[i+1])
            require_transition(happy_path[i], happy_path[i+1]) # Should not raise

    def test_lifecycle_003_illegal_forward_skips_rejected(self):
        """LIFECYCLE-003: Illegal forward skips are rejected."""
        assert not can_transition(ChangeState.RECEIVED, ChangeState.EXECUTING)
        assert not can_transition(ChangeState.DISCOVERING, ChangeState.GROUNDED)
        
        with pytest.raises(IllegalTransitionError):
            require_transition(ChangeState.RECEIVED, ChangeState.EXECUTING)

    def test_lifecycle_004_backward_transitions_rejected(self):
        """LIFECYCLE-004: Backward transitions not explicitly declared are rejected."""
        # E.g., Executing cannot simply go back to Discovering without RETRY_SCHEDULED or COMPENSATING
        assert not can_transition(ChangeState.EXECUTING, ChangeState.DISCOVERING)
        assert not can_transition(ChangeState.AUTHORIZED, ChangeState.QUALIFYING)
        assert not can_transition(ChangeState.VERIFYING, ChangeState.EXECUTING)

    def test_lifecycle_005_terminal_states_no_outgoing(self):
        """LIFECYCLE-005: All terminal states have zero outgoing transitions."""
        terminals = [ChangeState.BLOCKED, ChangeState.COMPLETE, ChangeState.FAILED, ChangeState.CANCELLED]
        for t in terminals:
            assert is_terminal(t)
            assert len(ALLOWED_TRANSITIONS[t]) == 0
            
            # Verify they cannot transition to themselves either
            assert not can_transition(t, t)

    def test_lifecycle_006_terminal_states_cannot_retry(self):
        """LIFECYCLE-006: No terminal state can retry."""
        terminals = [ChangeState.BLOCKED, ChangeState.COMPLETE, ChangeState.FAILED, ChangeState.CANCELLED]
        for t in terminals:
            assert not can_transition(t, ChangeState.RETRY_SCHEDULED)

    def test_lifecycle_007_retry_branch_explicit(self):
        """LIFECYCLE-007: Retry branch entry is explicit."""
        explicitly_retriable = {
            ChangeState.DISCOVERING, ChangeState.QUALIFYING, ChangeState.REHEARSING,
            ChangeState.EXECUTING, ChangeState.VERIFYING, ChangeState.CERTIFYING,
            ChangeState.COMPENSATING
        }
        
        for state in ChangeState:
            if state in explicitly_retriable:
                assert can_transition(state, ChangeState.RETRY_SCHEDULED)
            else:
                assert not can_transition(state, ChangeState.RETRY_SCHEDULED)

    def test_lifecycle_008_retry_targets_bounded(self):
        """LIFECYCLE-008: Retry resume targets are bounded."""
        retry_targets = ALLOWED_TRANSITIONS[ChangeState.RETRY_SCHEDULED]
        
        allowed_resumes = {
            ChangeState.DISCOVERING, ChangeState.QUALIFYING, ChangeState.REHEARSING,
            ChangeState.EXECUTING, ChangeState.VERIFYING, ChangeState.CERTIFYING,
            ChangeState.CANCELLED, ChangeState.FAILED
        }
        
        assert retry_targets == frozenset(allowed_resumes)

    def test_lifecycle_009_compensation_explicit(self):
        """LIFECYCLE-009: Compensation entry is explicit."""
        # Only EXECUTING and VERIFYING enter COMPENSATING
        assert can_transition(ChangeState.EXECUTING, ChangeState.COMPENSATING)
        assert can_transition(ChangeState.VERIFYING, ChangeState.COMPENSATING)
        
        # Grounded cannot compensate (it hasn't executed)
        assert not can_transition(ChangeState.GROUNDED, ChangeState.COMPENSATING)

    def test_lifecycle_010_compensation_exit_bounded(self):
        """LIFECYCLE-010: Compensation exit paths are bounded."""
        targets = ALLOWED_TRANSITIONS[ChangeState.COMPENSATING]
        assert targets == frozenset({
            ChangeState.RETRY_SCHEDULED, ChangeState.FAILED, ChangeState.CANCELLED, ChangeState.BLOCKED
        })
        # Cannot jump to COMPLETE
        assert ChangeState.COMPLETE not in targets

    def test_lifecycle_011_unknown_state_fails_closed(self):
        """LIFECYCLE-011: Unknown state/value fails closed."""
        assert not can_transition("RUNNING", ChangeState.COMPLETE) # type: ignore
        assert not can_transition(ChangeState.EXECUTING, "DONE") # type: ignore
        assert not can_transition(None, ChangeState.COMPLETE) # type: ignore
        
        with pytest.raises(IllegalTransitionError):
            require_transition("RUNNING", ChangeState.COMPLETE) # type: ignore

    def test_lifecycle_012_self_transitions_rejected(self):
        """LIFECYCLE-012: Self-transitions rejected unless explicitly frozen."""
        for state in ChangeState:
            assert not can_transition(state, state)
            with pytest.raises(IllegalTransitionError):
                require_transition(state, state)

    def test_lifecycle_013_authority_optional(self):
        """LIFECYCLE-013: Authority-required branch is optional rather than universal."""
        # Autonomous authorization path
        assert can_transition(ChangeState.GROUNDED, ChangeState.AUTHORIZED)
        # Human authority path
        assert can_transition(ChangeState.GROUNDED, ChangeState.AWAITING_AUTHORITY)
        assert can_transition(ChangeState.AWAITING_AUTHORITY, ChangeState.AUTHORIZED)

    def test_lifecycle_014_human_denial_behavior(self):
        """LIFECYCLE-014: Human-authority denial cannot progress into execution."""
        # From AWAITING_AUTHORITY, one cannot go to EXECUTING
        assert not can_transition(ChangeState.AWAITING_AUTHORITY, ChangeState.EXECUTING)
        # Denials go to BLOCKED or CANCELLED
        assert can_transition(ChangeState.AWAITING_AUTHORITY, ChangeState.BLOCKED)
        assert can_transition(ChangeState.AWAITING_AUTHORITY, ChangeState.CANCELLED)

    def test_lifecycle_015_live_write_does_not_imply_human_authority(self):
        """
        LIFECYCLE-015: LIVE_WRITE does not automatically imply AWAITING_AUTHORITY.
        This is structurally proven by the fact that the transition from GROUNDED
        directly to AUTHORIZED exists, allowing a system to bypass AWAITING_AUTHORITY
        entirely when policy permits, regardless of execution mode.
        """
        assert can_transition(ChangeState.GROUNDED, ChangeState.AUTHORIZED)

    def test_lifecycle_016_gemini_uncertainty_is_not_lifecycle_authority(self):
        """
        LIFECYCLE-016: Gemini uncertainty does not appear as a lifecycle transition authority.
        The state machine has no 'UNCERTAIN' or 'ESCALATED_FOR_REVIEW' states.
        """
        for state in ChangeState:
            assert "UNCERTAIN" not in state.value
            assert "REVIEW" not in state.value

    def test_lifecycle_017_transition_table_covers_all(self):
        """LIFECYCLE-017: Transition table covers every ChangeState source exactly once."""
        keys = set(ALLOWED_TRANSITIONS.keys())
        all_states = set(ChangeState)
        assert keys == all_states

    def test_lifecycle_018_every_target_is_valid(self):
        """LIFECYCLE-018: Every transition-table target is a valid ChangeState."""
        for source, targets in ALLOWED_TRANSITIONS.items():
            assert isinstance(source, ChangeState)
            for target in targets:
                assert isinstance(target, ChangeState)

    def test_lifecycle_019_public_exports_are_deliberate(self):
        """LIFECYCLE-019: Public lifecycle exports are deliberate."""
        import domain.contracts as contracts
        # ChangeState must be exported
        assert "ChangeState" in contracts.__all__
        # EvidenceState must NOT be exported
        assert "EvidenceState" not in contracts.__all__
        
    def test_lifecycle_020_no_provider_imports(self):
        """LIFECYCLE-020: Provider-specific imports absent from the new lifecycle domain module."""
        import sys
        
        # Reload to capture imports strictly happening in the module
        import importlib
        import domain.contracts.change_lifecycle as change_lifecycle
        importlib.reload(change_lifecycle)
        
        forbidden = ['google', 'vertexai', 'firebase', 'github', 'pydantic']
        
        import ast
        with open(change_lifecycle.__file__, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
            
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    for f_mod in forbidden:
                        assert not name.name.startswith(f_mod)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for f_mod in forbidden:
                        assert not node.module.startswith(f_mod)
