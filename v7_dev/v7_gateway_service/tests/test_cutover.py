import pytest
import time
from services.migration_control import migration_control, EngineState
from services.routing import routing_service
import requests_mock

def test_pgvector_primary_sync(always_healthy_universal_gate):
    migration_control.current_state = EngineState.PGVECTOR_PRIMARY_SYNC
    migration_control.error_window.clear()
    
    with requests_mock.Mocker() as m:
        m.post("http://vector-service-dev:8001/v7/vector/index", json={"success": True})
        m.post("http://vector-service-dev:8001/v7/vector/search", json={"results": [{"chunk_id": "pg_chunk", "distance": 0.1}]})
        
        # Test read
        res = routing_service.read_vector("tenant-A", {"query": "test"})
        # Should return pg_result
        assert res[0]["chunk_id"] == "pg_chunk"
        
        # Test write
        routing_service.write_vector("tenant-A", {"chunk_id": "new_chunk"})
        # Check FAISS received the write (paridad)
        assert len(routing_service.faiss_db) >= 1
        # Check PGVECTOR received the write
        assert m.call_count == 2 # 1 search, 1 index

def test_faiss_standby(always_healthy_universal_gate):
    migration_control.current_state = EngineState.FAISS_STANDBY
    migration_control.error_window.clear()
    routing_service.faiss_db.clear()
    
    with requests_mock.Mocker() as m:
        m.post("http://vector-service-dev:8001/v7/vector/index", json={"success": True})
        m.post("http://vector-service-dev:8001/v7/vector/search", json={"results": [{"chunk_id": "pg_chunk", "distance": 0.1}]})
        
        # Test read
        res = routing_service.read_vector("tenant-A", {"query": "test"})
        assert res[0]["chunk_id"] == "pg_chunk"
        
        # Test write
        routing_service.write_vector("tenant-A", {"chunk_id": "new_chunk"})
        
        # Check FAISS did NOT receive the write
        assert len(routing_service.faiss_db) == 0

def test_rollback_from_primary_sync(always_healthy_universal_gate):
    migration_control.current_state = EngineState.PGVECTOR_PRIMARY_SYNC
    migration_control.error_window.clear()
    
    with requests_mock.Mocker() as m:
        m.post("http://vector-service-dev:8001/v7/vector/search", exc=Exception("DB Down"))
        
        # Test read fail
        res = routing_service.read_vector("tenant-A", {"query": "test"})
        # Should fallback to FAISS result
        assert res[0]["chunk_id"] == "legacy_chunk"
        
        # Bombard to trigger rollback
        for _ in range(15):
            routing_service.read_vector("tenant-A", {"query": "test"})
            
        assert migration_control.get_state() == EngineState.FAISS_ONLY
