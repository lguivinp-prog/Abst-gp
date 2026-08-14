from services.migration_control import migration_control, EngineState
from services.routing import routing_service

def test_valid_transitions():
    # Start at FAISS_ONLY
    migration_control.current_state = EngineState.FAISS_ONLY
    assert migration_control.get_state() == EngineState.FAISS_ONLY
    
    # Transition to DUAL_WRITE
    migration_control.transition_to(EngineState.DUAL_WRITE)
    assert migration_control.get_state() == EngineState.DUAL_WRITE
    
    # Transition to DUAL_READ
    migration_control.transition_to(EngineState.DUAL_READ)
    assert migration_control.get_state() == EngineState.DUAL_READ

def test_invalid_transition():
    migration_control.current_state = EngineState.FAISS_ONLY
    try:
        migration_control.transition_to(EngineState.PGVECTOR_PRIMARY_SYNC)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass # Expected

def test_rollback():
    migration_control.current_state = EngineState.DUAL_READ
    migration_control.trigger_rollback("TEST_FAILURE")
    assert migration_control.get_state() == EngineState.FAISS_ONLY
