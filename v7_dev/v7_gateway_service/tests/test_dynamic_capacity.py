import pytest
from services.rollout_controller import rollout_controller, EngineState
from services.capacity_guard import capacity_guard
from services.tenant_capacity import tenant_capacity_service, MockTenantRegistry

def setup_module():
    capacity_guard.total_capacity_available = 2000.0
    capacity_guard.update_metrics(cpu_usage=20) # Healthy

def test_tenant_capacity_score():
    score_whale = tenant_capacity_service.get_tenant_score("whale_tenant")
    # Whale: QPS=300 (180), Size=5000 (125), Growth=500 (75) -> 380
    assert score_whale > 0
    
    score_small = tenant_capacity_service.get_tenant_score("small_tenant")
    # Small: QPS=5 (3), Size=100 (2.5), Growth=10 (1.5) -> 7.0
    assert score_small > 0 # Reconciled V1 weights

def test_simulate_wave_safe():
    # Wave 1 is 0% -> load 0
    res = rollout_controller.simulate_wave(1)
    assert res["status"] == "SAFE"
    assert res["forecasted_load"] == 0.0

def test_simulate_wave_unsafe():
    # If we drop capacity significantly
    capacity_guard.total_capacity_available = 100.0
    
    # Wave 5 is 100% -> all tenants. Projected load is well over 100.
    res = rollout_controller.simulate_wave(5)
    assert res["status"] == "UNSAFE"
    
    capacity_guard.total_capacity_available = 2000.0 # reset

def test_wave_approval_blocked_by_simulation():
    capacity_guard.total_capacity_available = 100.0
    # Should be blocked
    success = rollout_controller.set_wave(5)
    assert success == False
    assert rollout_controller.current_wave != 5
    capacity_guard.total_capacity_available = 2000.0 # reset

def test_emergency_rollback_audit():
    rollout_controller.set_wave(2)
    rollout_controller.rollback_emergency("Corrupted index", initiator="sre-admin", affected_count=15)
    assert rollout_controller.global_rollback == True
