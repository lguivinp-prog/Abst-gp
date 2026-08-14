import pytest
from services.rollout_controller import rollout_controller
from services.capacity_guard import capacity_guard
from services.tenant_capacity import tenant_capacity_service
from services.capacity_analyzer import capacity_analyzer, AdjustmentState

def setup_function():
    # Reset states
    capacity_guard.total_capacity_available = 2000.0
    rollout_controller.current_wave = 0
    rollout_controller.global_rollback = False
    rollout_controller.is_paused = False
    capacity_analyzer.pending_adjustments.clear()
    tenant_capacity_service.version = "v1"

def test_wave3_dry_run_and_execution():
    # Dry Run
    sim = rollout_controller.simulate_wave(3)
    assert sim["status"] == "SAFE"
    
    # Record prediction
    capacity_analyzer.record_prediction(3, sim["forecasted_load"])
    
    # Execute
    success = rollout_controller.set_wave(3)
    assert success == True
    assert rollout_controller.current_wave == 3

def test_delta_analyzer_and_calibration():
    # Setup wave 3 prediction
    sim = rollout_controller.simulate_wave(3)
    predicted = sim["forecasted_load"]
    capacity_analyzer.record_prediction(3, predicted)
    
    # Run soak test with 20% higher actual load
    actual_load = predicted * 1.20
    res = capacity_analyzer.run_simulated_soak_test(3, actual_load)
    
    assert res["prediction_error"] > 0
    assert res["error_percentage"] > 10.0
    
    # Verify adjustment was proposed
    assert len(capacity_analyzer.pending_adjustments) == 1
    req_id, adj = list(capacity_analyzer.pending_adjustments.items())[0]
    
    assert adj.state == AdjustmentState.PROPOSED
    assert adj.proposed_weights["qps_weight"] == 0.70
    
    # SRE Approves and Applies
    adj.approve()
    tenant_capacity_service.apply_adjustment(adj)
    
    assert adj.state == AdjustmentState.APPLIED
    assert tenant_capacity_service.version == "v2"
    assert tenant_capacity_service.weights["qps_weight"] == 0.70

def test_wave4_and_wave5_execution():
    # Increase capacity significantly to allow Wave 4 and 5 to pass simulation
    capacity_guard.total_capacity_available = 10000.0
    
    # Assuming V2 model is active, simulate wave 4 and 5
    sim4 = rollout_controller.simulate_wave(4)
    capacity_analyzer.record_prediction(4, sim4["forecasted_load"])
    assert rollout_controller.set_wave(4) == True
    
    sim5 = rollout_controller.simulate_wave(5)
    capacity_analyzer.record_prediction(5, sim5["forecasted_load"])
    assert rollout_controller.set_wave(5) == True
    assert rollout_controller.current_wave == 5
