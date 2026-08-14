from services.migration_control import migration_control, EngineState
from services.rollout_controller import rollout_controller
from services.shadow_eval import shadow_storage
import time
import requests
import os

VECTOR_SERVICE_URL = os.getenv("VECTOR_SERVICE_URL", "http://vector-service-dev:8001/v7/vector")
# We track metrics via globals in main or through direct logging
# For this Alpha, we'll log the metrics to be scraped by the middleware or Prometheus

class VectorEngineRouter:
    def __init__(self):
        # Mock FAISS
        self.faiss_db = []
        
    def _faiss_write(self, data):
        time.sleep(0.01)
        self.faiss_db.append(data)
        return True

    def _faiss_read(self, query):
        time.sleep(0.01)
        return [{"chunk_id": "legacy_chunk", "distance": 0.5}]

    def write_vector(self, tenant_id: str, data: dict):
        state = rollout_controller.get_tenant_state(tenant_id)
        
        # Write to pgvector first if we are migrating
        if state in [EngineState.DUAL_WRITE, EngineState.DUAL_READ, EngineState.PGVECTOR_PRIMARY_SYNC, EngineState.FAISS_STANDBY]:
            try:
                # Call Vector Service
                res = requests.post(f"{VECTOR_SERVICE_URL}/index", headers={"x-tenant-id": tenant_id}, json=data, timeout=2)
                res.raise_for_status()
            except Exception as e:
                print(f"[PGVECTOR ERROR] {e}")
                # We do not rollback on write failure
                pass
                
        # Write to faiss
        if state in [EngineState.FAISS_ONLY, EngineState.DUAL_WRITE, EngineState.DUAL_READ, EngineState.PGVECTOR_PRIMARY_SYNC]:
            self._faiss_write(data)
                
    def read_vector(self, tenant_id: str, query: dict):
        state = rollout_controller.get_tenant_state(tenant_id)
        
        faiss_result = None
        pg_result = None
        
        # Read from FAISS
        if state in [EngineState.FAISS_ONLY, EngineState.DUAL_WRITE, EngineState.DUAL_READ, EngineState.PGVECTOR_PRIMARY_SYNC]:
            start_f = time.time()
            faiss_result = self._faiss_read(query)
            faiss_latency = (time.time() - start_f) * 1000
            
        # Read from PGVECTOR
        if state in [EngineState.DUAL_READ, EngineState.PGVECTOR_PRIMARY_SYNC, EngineState.FAISS_STANDBY]:
            start_t = time.time()
            try:
                res = requests.post(f"{VECTOR_SERVICE_URL}/search", headers={"x-tenant-id": tenant_id}, json=query, timeout=2)
                res.raise_for_status()
                pg_result = res.json().get("results", [])
                latency = (time.time() - start_t) * 1000
                
                # If DUAL_READ, compare
                if state == EngineState.DUAL_READ and faiss_result is not None:
                    migration_control.record_request(True)
                    shadow_storage.store_evaluation(tenant_id, query, faiss_result, pg_result, faiss_latency, latency)
                    print(f"[METRIC] v7_dual_read_difference_total {len(faiss_result)} vs {len(pg_result)}")
            except Exception as e:
                print(f"[PGVECTOR READ ERROR] {e}")
                if state in [EngineState.DUAL_READ, EngineState.PGVECTOR_PRIMARY_SYNC, EngineState.FAISS_STANDBY]:
                    migration_control.record_request(False)
                
        # Return primary source
        if state in [EngineState.PGVECTOR_PRIMARY_SYNC, EngineState.FAISS_STANDBY]:
            if pg_result is not None:
                return pg_result
            # If pgvector failed and we rolled back mid-request or just want to fallback
            if state == EngineState.PGVECTOR_PRIMARY_SYNC and faiss_result is not None:
                 return faiss_result
            if faiss_result is not None:
                return faiss_result
            return [{"error": "Vector service unavailable"}]
            
        return faiss_result if faiss_result is not None else pg_result

routing_service = VectorEngineRouter()
