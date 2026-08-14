import pytest
from services.rollout_controller import rollout_controller
from services.capacity_guard import capacity_guard

original_validate = rollout_controller.validate_universal_gate

@pytest.fixture(autouse=False)
def always_healthy_universal_gate():
    """
    Fixture for component/unit tests that do not validate the Universal Gate itself.
    Bypasses the 15-point checks so legacy isolated tests can pass without full setup.
    """
    rollout_controller.validate_universal_gate = lambda w: (True, "SAFE")
    yield
    rollout_controller.validate_universal_gate = original_validate

@pytest.fixture(autouse=True)
def reset_state():
    capacity_guard.total_capacity_available = 15000.0
    rollout_controller.active_isolation_violations = 0
    rollout_controller.current_wave = 0
    rollout_controller.celery_backlog = False
    rollout_controller.redis_pressure = False
    rollout_controller.error_rate_ok = True
    rollout_controller.cost_within_budget = True
    rollout_controller.slo_p99_ok = True
    rollout_controller.slo_p95_ok = True
    rollout_controller.db_connections_ok = True
    rollout_controller.faiss_stale = False
    rollout_controller.pgvector_up = True
    rollout_controller.gateway_fail_closed_active = True
    rollout_controller.validate_universal_gate = original_validate
    
    # We also mock simulate_wave so it is safe by default unless tested
    original_simulate = rollout_controller.simulate_wave
    rollout_controller.simulate_wave = lambda w: {"status": "SAFE", "forecasted_load": 100}
    yield
    rollout_controller.simulate_wave = original_simulate

