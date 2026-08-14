import pytest
import hashlib
from services.rollout_controller import rollout_controller, EngineState
from services.capacity_guard import capacity_guard
from services.tenant_capacity import tenant_capacity_service
from services.capacity_analyzer import capacity_analyzer, AdjustmentState

def setup_function():
    capacity_guard.total_capacity_available = 15000.0
    capacity_guard.update_metrics(cpu_usage=20)
    rollout_controller.current_wave = 0
    rollout_controller.global_rollback = False
    rollout_controller.is_paused = False
    rollout_controller.active_isolation_violations = 0
    rollout_controller.faiss_stale = False
    rollout_controller.slo_p95_ok = True
    rollout_controller.celery_backlog = False
    rollout_controller.cost_within_budget = True
    capacity_analyzer.pending_adjustments.clear()
    tenant_capacity_service.version = "v1"

def test_deterministic_hashing():
    t1 = "tenant_xyz_123"
    hash1 = rollout_controller._hash_tenant(t1)
    
    # Simulate another process by recreating hash directly with sha256
    hash2 = int(hashlib.sha256(t1.encode('utf-8')).hexdigest(), 16) % 100
    
    assert hash1 == hash2
    assert type(hash1) == int

def test_universal_gate_blocking():
    # Trigger a violation
    rollout_controller.celery_backlog = True
    
    passed, reason = rollout_controller.validate_universal_gate(3)
    assert passed == False
    rollout_controller.celery_backlog = False
    assert "Celery/Redis backlog" in reason
    
    # Attempt to set wave
    rollout_controller.celery_backlog = False
    assert rollout_controller.set_wave(3) == True

def test_security_violation_zero_tolerance():
    rollout_controller.active_isolation_violations = 1
    passed, reason = rollout_controller.validate_universal_gate(4)
    assert passed == False
    rollout_controller.celery_backlog = False
    assert "isolation violations" in reason

def test_end_to_end_sprint56():
    # 1. Wave 3 approval and execution
    sim3 = rollout_controller.simulate_wave(3)
    capacity_analyzer.record_prediction(3, sim3["forecasted_load"])
    assert rollout_controller.set_wave(3) == True
    
    # 2. Soak Test (SIMULATED_SOAK) - Generate high actual load
    actual_load = sim3["forecasted_load"] * 1.30 # 30% higher
    res = capacity_analyzer.run_simulated_soak_test(3, actual_load)
    
    # 3. Model Calibration Governance
    assert len(capacity_analyzer.pending_adjustments) > 0
    req_id, adj = list(capacity_analyzer.pending_adjustments.items())[0]
    
    # SRE approves the adjustment for Wave 4
    adj.approve()
    tenant_capacity_service.apply_adjustment(adj)
    
    assert tenant_capacity_service.version == "v2"
    
    # 4. Wave 4 Execution
    sim4 = rollout_controller.simulate_wave(4)
    capacity_analyzer.record_prediction(4, sim4["forecasted_load"])
    assert rollout_controller.set_wave(4) == True
    capacity_analyzer.run_simulated_soak_test(4, sim4["forecasted_load"] * 1.05) # Stable soak
    
    # 5. Wave 5 Execution
    sim5 = rollout_controller.simulate_wave(5)
    capacity_analyzer.record_prediction(5, sim5["forecasted_load"])
    assert rollout_controller.set_wave(5) == True
    
    assert rollout_controller.current_wave == 5

def test_golden_hash_vector():
    # INTENTIONAL BEHAVIOR CHANGE: Hash algorithm changed from MD5 to SHA-256
    # rollout_hash_version = "sha256-v1"
    import hashlib
    tenant_id = "tenant_A"
    expected_bucket = int(hashlib.sha256(tenant_id.encode('utf-8')).hexdigest(), 16) % 100
    assert rollout_controller._hash_tenant(tenant_id) == expected_bucket
