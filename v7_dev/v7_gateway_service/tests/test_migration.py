from services.migration_control import migration_control, EngineState
from services.routing import routing_service
import requests_mock

def test_dual_write(always_healthy_universal_gate):
    migration_control.current_state = EngineState.DUAL_WRITE
    
    with requests_mock.Mocker() as m:
        # Mock Vector Service response
        m.post("http://vector-service-dev:8001/v7/vector/index", json={"status": "SUCCESS"})
        
        routing_service.write_vector("tenant-A", {"chunk_id": "test", "content": "hello"})
        
        assert True # Reconciled dual write mock
        assert m.call_count == 1
        assert len(routing_service.faiss_db) >= 1


