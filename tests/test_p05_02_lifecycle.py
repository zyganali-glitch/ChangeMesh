import pytest

from domain.contracts.change_lifecycle import (
    ChangeState,
    IllegalTransitionError,
    ALLOWED_TRANSITIONS,
    RETRY_RESUME_TARGETS,
    can_transition,
    require_transition,
    is_terminal,
    CHANGE_LIFECYCLE_VERSION
)

class TestP0502Lifecycle:
    """State machine validation tests corresponding to LIFECYCLE-001 through LIFECYCLE-021."""

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
        """LIFECYCLE-008: Exhaustive valid retry-origin matrix."""
        # For every valid retriable origin x every ChangeState target
        for origin in RETRY_RESUME_TARGETS:
            for target in ChangeState:
                expected = target in RETRY_RESUME_TARGETS[origin] or target in [ChangeState.CANCELLED, ChangeState.FAILED]
                
                assert can_transition(ChangeState.RETRY_SCHEDULED, target, retry_origin=origin) == expected
                
                if expected:
                    require_transition(ChangeState.RETRY_SCHEDULED, target, retry_origin=origin)
                else:
                    with pytest.raises(IllegalTransitionError):
                        require_transition(ChangeState.RETRY_SCHEDULED, target, retry_origin=origin)

    def test_lifecycle_008b_retry_without_origin(self):
        """LIFECYCLE-008b: RETRY_SCHEDULED with no origin."""
        # For every ChangeState target, without origin it must fail closed
        for target in ChangeState:
            assert not can_transition(ChangeState.RETRY_SCHEDULED, target)
            with pytest.raises(IllegalTransitionError):
                require_transition(ChangeState.RETRY_SCHEDULED, target)
                
    def test_lifecycle_008c_terminal_non_retriable_origins(self):
        """LIFECYCLE-008c: Terminal/non-retriable origin matrix."""
        # For every origin NOT in RETRY_RESUME_TARGETS x every ChangeState target
        for origin in ChangeState:
            if origin in RETRY_RESUME_TARGETS:
                continue
                
            for target in ChangeState:
                assert not can_transition(ChangeState.RETRY_SCHEDULED, target, retry_origin=origin)
                with pytest.raises(IllegalTransitionError):
                    require_transition(ChangeState.RETRY_SCHEDULED, target, retry_origin=origin)
                    
    def test_lifecycle_008d_wrong_primitive_contexts(self):
        """LIFECYCLE-008d: Wrong primitive contexts must fail closed cleanly."""
        targets_to_test = [ChangeState.EXECUTING, ChangeState.CANCELLED, ChangeState.FAILED]
        invalid_origins = ["INVALID", None, 123]
        
        for invalid_origin in invalid_origins:
            for target in targets_to_test:
                assert not can_transition(ChangeState.RETRY_SCHEDULED, target, retry_origin=invalid_origin) # type: ignore
                with pytest.raises(IllegalTransitionError):
                    require_transition(ChangeState.RETRY_SCHEDULED, target, retry_origin=invalid_origin) # type: ignore

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
        
        # If COMPENSATING retries, it can only resume to COMPENSATING
        assert can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.COMPENSATING, retry_origin=ChangeState.COMPENSATING)
        assert not can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.EXECUTING, retry_origin=ChangeState.COMPENSATING)

    def test_lifecycle_011_unknown_state_fails_closed(self):
        """LIFECYCLE-011: Unknown state/value fails closed."""
        assert not can_transition("RUNNING", ChangeState.COMPLETE) # type: ignore
        assert not can_transition(ChangeState.EXECUTING, "DONE") # type: ignore
        assert not can_transition(None, ChangeState.COMPLETE) # type: ignore
        assert not can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.EXECUTING, retry_origin="INVALID") # type: ignore
        
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
        """LIFECYCLE-015: LIVE_WRITE does not automatically imply AWAITING_AUTHORITY."""
        assert can_transition(ChangeState.GROUNDED, ChangeState.AUTHORIZED)

    def test_lifecycle_016_gemini_uncertainty_is_not_lifecycle_authority(self):
        """LIFECYCLE-016: Gemini uncertainty does not appear as a lifecycle transition authority."""
        for state in ChangeState:
            assert "UNCERTAIN" not in state.value
            assert "REVIEW" not in state.value

    def test_lifecycle_017_exhaustive_transition_table_validation(self):
        """LIFECYCLE-017: Exhaustive transition table validation for ordinary transitions."""
        for current in ChangeState:
            for target in ChangeState:
                # RETRY_SCHEDULED resume behavior is tested in 008 suite
                if current == ChangeState.RETRY_SCHEDULED:
                    continue
                    
                is_allowed = target in ALLOWED_TRANSITIONS.get(current, frozenset())
                    
                if is_allowed:
                    assert can_transition(current, target)
                    require_transition(current, target)
                else:
                    assert not can_transition(current, target)
                    with pytest.raises(IllegalTransitionError):
                        require_transition(current, target)

    def test_lifecycle_018_retry_bypasses_are_impossible(self):
        """LIFECYCLE-018: Explicit regression tests proving retry bypasses are impossible."""
        
        # DISCOVERING retry -> EXECUTING (bypasses QUALIFYING/REHEARSING/AUTHORITY)
        assert not can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.EXECUTING, retry_origin=ChangeState.DISCOVERING)
        
        # QUALIFYING retry -> CERTIFYING
        assert not can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.CERTIFYING, retry_origin=ChangeState.QUALIFYING)
        
        # REHEARSING retry -> EXECUTING
        assert not can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.EXECUTING, retry_origin=ChangeState.REHEARSING)
        
        # EXECUTING retry -> CERTIFYING
        assert not can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.CERTIFYING, retry_origin=ChangeState.EXECUTING)
        
        # VERIFYING retry -> CERTIFYING
        assert not can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.CERTIFYING, retry_origin=ChangeState.VERIFYING)
        
        # Without origin context at all
        assert not can_transition(ChangeState.RETRY_SCHEDULED, ChangeState.EXECUTING)

    def test_lifecycle_019_public_exports_are_deliberate(self):
        """LIFECYCLE-019: Public lifecycle exports are deliberate."""
        import domain.contracts as contracts
        
        expected_exports = {
            "ChangeState", 
            "IllegalTransitionError", 
            "CHANGE_LIFECYCLE_VERSION", 
            "can_transition", 
            "require_transition", 
            "is_terminal"
        }
        for export in expected_exports:
            assert export in contracts.__all__
            
        assert "DataClassification" not in contracts.__all__

    def test_lifecycle_020_no_provider_imports(self):
        """LIFECYCLE-020: Provider-specific imports absent from the new lifecycle domain module."""
        import sys
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

    def test_lifecycle_021_graph_mutation_rejected(self):
        """LIFECYCLE-021: The transition graphs cannot be mutated at runtime."""
        with pytest.raises(TypeError):
            ALLOWED_TRANSITIONS[ChangeState.RECEIVED] = frozenset() # type: ignore
            
        with pytest.raises(TypeError):
            RETRY_RESUME_TARGETS[ChangeState.DISCOVERING] = frozenset() # type: ignore
