import pytest
from services.rollout_controller import rollout_controller, EngineState

def test_hash_assignment(always_healthy_universal_gate):
    rollout_controller.global_rollback = False
    rollout_controller.tenant_registry.clear()
    
    # 0% wave
    rollout_controller.set_wave(0)
    assert rollout_controller.get_tenant_state("tenant_A") == EngineState.FAISS_ONLY
    
    # 100% wave
    rollout_controller.set_wave(5)
    assert rollout_controller.get_tenant_state("tenant_A") == EngineState.PGVECTOR_PRIMARY_SYNC
    assert rollout_controller.get_tenant_state("tenant_B") == EngineState.PGVECTOR_PRIMARY_SYNC

def test_manual_override(always_healthy_universal_gate):
    rollout_controller.global_rollback = False
    rollout_controller.tenant_registry.clear()
    rollout_controller.set_wave(0) # 0% wave
    
    # Assign tenant manually to active V7
    rollout_controller.assign_tenant("pilot_tenant", 1, EngineState.PGVECTOR_PRIMARY_SYNC, "ACTIVE_V7")
    
    assert rollout_controller.get_tenant_state("pilot_tenant") == EngineState.PGVECTOR_PRIMARY_SYNC
    assert rollout_controller.get_tenant_state("other_tenant") == EngineState.FAISS_ONLY

def test_tenant_rollback(always_healthy_universal_gate):
    rollout_controller.global_rollback = False
    rollout_controller.tenant_registry.clear()
    rollout_controller.set_wave(5) # 100% wave
    
    # Default is PGVECTOR based on hash
    assert rollout_controller.get_tenant_state("tenant_fail") == EngineState.PGVECTOR_PRIMARY_SYNC
    
    # Rollback just this tenant
    rollout_controller.rollback_tenant("tenant_fail", "Too many errors")
    
    assert rollout_controller.get_tenant_state("tenant_fail") == EngineState.FAISS_ONLY
    # Others are still V7
    assert rollout_controller.get_tenant_state("tenant_ok") == EngineState.PGVECTOR_PRIMARY_SYNC

def test_wave_rollback(always_healthy_universal_gate):
    rollout_controller.global_rollback = False
    rollout_controller.tenant_registry.clear()
    
    rollout_controller.set_wave(2) # 10%
    rollout_controller.assign_tenant("t1", 2, EngineState.PGVECTOR_PRIMARY_SYNC)
    rollout_controller.assign_tenant("t2", 2, EngineState.PGVECTOR_PRIMARY_SYNC)
    
    rollout_controller.rollback_wave(2, "Wave degradation")
    
    assert rollout_controller.get_tenant_state("t1") == EngineState.FAISS_ONLY
    assert rollout_controller.get_tenant_state("t2") == EngineState.FAISS_ONLY
    assert rollout_controller.current_wave == 1

def test_global_rollback(always_healthy_universal_gate):
    rollout_controller.global_rollback = False
    rollout_controller.tenant_registry.clear()
    rollout_controller.set_wave(5)
    
    assert rollout_controller.get_tenant_state("any_tenant") == EngineState.PGVECTOR_PRIMARY_SYNC
    
    rollout_controller.rollback_global("Catastrophic DB Failure")
    
    assert rollout_controller.get_tenant_state("any_tenant") == EngineState.FAISS_ONLY
    assert rollout_controller.current_wave == 0

def test_golden_vectors():
    import hashlib
    # INTENTIONAL_BEHAVIOR_CHANGE: HASH CONTRACT decoupling
    tenant_id = "tenant_A"
    digest = hashlib.sha256(tenant_id.encode('utf-8')).hexdigest()
    expected = int(digest, 16) % 100
    from services.rollout_controller import rollout_controller
    assert rollout_controller._hash_tenant(tenant_id) == expected
