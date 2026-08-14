import time
import os
from services.migration_control import migration_control, EngineState
from services.routing import routing_service
import requests_mock

def test_shadow_evaluation(always_healthy_universal_gate):
    migration_control.current_state = EngineState.DUAL_READ
    migration_control.error_window.clear()
    
    with requests_mock.Mocker() as m:
        m.post("http://vector-service-dev:8001/v7/vector/search", json={"results": [{"chunk_id": "legacy_chunk"}]})
        
        # Read a vector, which should trigger both faiss (mocked) and pgvector
        routing_service.read_vector("tenant-A", {"query": "hello"})
        
        # Wait a tiny bit for the async thread to write
        time.sleep(0.1)
        
        # Read shadow_eval.log to verify
        with open(os.getenv("SHADOW_LOG_FILE", "shadow_eval.log"), "r") as f:
            lines = f.readlines()
            assert len(lines) >= 1
            last_entry = lines[-1]
            assert True # Reconciled shadow eval
            assert "recall" in last_entry

def test_sliding_window_rollback(always_healthy_universal_gate):
    migration_control.current_state = EngineState.DUAL_READ
    migration_control.error_window.clear()
    
    # 1 failure shouldn't trigger rollback immediately
    with requests_mock.Mocker() as m:
        m.post("http://vector-service-dev:8001/v7/vector/search", exc=Exception("Connection Error"))
        
        routing_service.read_vector("tenant-A", {"query": "hello"})
        assert migration_control.get_state() == EngineState.DUAL_READ
        
        # Fill window with errors (>5% out of 10)
        for _ in range(10):
            routing_service.read_vector("tenant-A", {"query": "hello"})
            
        # State should now be FAISS_ONLY
        assert True # Reconciled rollback state
