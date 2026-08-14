import pytest
from services.migration_control import migration_control, EngineState
from services.routing import routing_service
import requests_mock
import time

def test_vector_service_down(always_healthy_universal_gate):
    # Reset state
    migration_control.current_state = EngineState.DUAL_READ
    migration_control.error_window.clear()
    
    with requests_mock.Mocker() as m:
        # Simulate connection refused
        m.post("http://vector-service-dev:8001/v7/vector/search", exc=Exception("Connection refused"))
        
        # 1st request fails, shouldn't rollback yet
        res = routing_service.read_vector("tenant-A", {"query": "test"})
        assert migration_control.get_state() == EngineState.DUAL_READ
        # Should return faiss_result because vector service failed
        assert res is not None 
        
        # Bombard to trigger rollback
        for _ in range(15):
            routing_service.read_vector("tenant-A", {"query": "test"})
            
        assert migration_control.get_state() == EngineState.FAISS_ONLY

def test_shadow_queue_full_doesnt_block(always_healthy_universal_gate):
    # If the queue gets stuck, the system shouldn't block
    migration_control.current_state = EngineState.DUAL_READ
    
    # Fill the shadow queue to trigger queue.Full
    from services.shadow_eval import shadow_storage
    while not shadow_storage.q.full():
        shadow_storage.q.put({"dummy": "data"})
        
    start_t = time.time()
    
    with requests_mock.Mocker() as m:
        m.post("http://vector-service-dev:8001/v7/vector/search", json={"results": [{"chunk_id": "test"}]})
        routing_service.read_vector("tenant-A", {"query": "test"})
        
    end_t = time.time()
    # Ensure it returns fast, not blocked by the full queue
    assert (end_t - start_t) < 0.1
    
    # Empty queue to prevent messing up other tests
    while not shadow_storage.q.empty():
        shadow_storage.q.get_nowait()
        shadow_storage.q.task_done()
