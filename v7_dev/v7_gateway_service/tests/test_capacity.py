import pytest
from services.rollout_controller import rollout_controller, EngineState
from services.capacity_guard import capacity_guard, CapacityState

def test_large_tenant_blocked(always_healthy_universal_gate):
    rollout_controller.global_rollback = False
    rollout_controller.tenant_registry.clear()
    rollout_controller.is_paused = False
    capacity_guard.update_metrics(cpu_usage=40)
    
    rollout_controller.set_wave(1)
    
    # "whale_tenant" weight is 300. Max safe capacity is 250 (1000 * 0.25).
    # It should be blocked.
    res = rollout_controller.assign_tenant("whale_tenant", 1, EngineState.PGVECTOR_PRIMARY_SYNC)
    
    assert res == False
    assert "whale_tenant" not in rollout_controller.tenant_registry

def test_auto_pause(always_healthy_universal_gate):
    rollout_controller.global_rollback = False
    rollout_controller.tenant_registry.clear()
    rollout_controller.is_paused = False
    
    # Trigger critical
    capacity_guard.update_metrics(cpu_usage=95)
    assert capacity_guard.get_state() == CapacityState.CRITICAL
    
    # Evaluate state (which is done on every read/write)
    rollout_controller.evaluate_system_state()
    assert rollout_controller.is_paused == True
    
    # Try assign while paused
    res = rollout_controller.assign_tenant("small_tenant", 1, EngineState.PGVECTOR_PRIMARY_SYNC)
    assert res == False

def test_safe_resume(always_healthy_universal_gate):
    rollout_controller.global_rollback = False
    rollout_controller.is_paused = True
    
    # Return to healthy
    capacity_guard.update_metrics(cpu_usage=40, celery_queue_depth=0, pgvector_latency=10)
    assert capacity_guard.get_state() == CapacityState.HEALTHY
    
    # Evaluate state should resume
    rollout_controller.evaluate_system_state()
    assert rollout_controller.is_paused == False
    
    # Try assign now
    res = rollout_controller.assign_tenant("small_tenant", 1, EngineState.PGVECTOR_PRIMARY_SYNC)
    assert res == True

def test_emergency_rollback(always_healthy_universal_gate):
    rollout_controller.set_wave(2)
    rollout_controller.rollback_emergency("Total outage")
    
    assert rollout_controller.global_rollback == True
    assert rollout_controller.current_wave == 0
    assert rollout_controller.is_paused == True
