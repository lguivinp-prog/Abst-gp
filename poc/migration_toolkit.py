import time
import random
from datetime import datetime

# --- FASE 1: VECTOR ROUTER IMPLEMENTATION ---
class VectorEngineRouter:
    def __init__(self):
        self.mode = "FAISS_ONLY"
        self.audit_log = []
        
    def change_mode(self, new_mode, user):
        old_mode = self.mode
        self.mode = new_mode
        self.audit_log.append(f"[{datetime.now().time()}] {user} changed mode: {old_mode} -> {new_mode}")
        print(f"\n[ROUTER] Mode switched to: {self.mode}")
        
    def rollback(self, user):
        self.change_mode("FAISS_ONLY", user)
        print("[ROUTER] EMERGENCY ROLLBACK EXECUTED. Traffic diverted to FAISS.")

    def route_write(self, document_id, chunk_data):
        if self.mode == "FAISS_ONLY":
            return "Wrote to FAISS"
        elif self.mode in ("DUAL_WRITE", "DUAL_READ"):
            return "Wrote to FAISS & PGVECTOR"
        elif self.mode == "PGVECTOR_PRIMARY":
            return "Wrote to PGVECTOR"

    def route_read(self, query):
        if self.mode == "FAISS_ONLY":
            return {"source": "FAISS", "results": ["chunk_1"]}
        elif self.mode == "DUAL_WRITE":
            return {"source": "FAISS", "results": ["chunk_1"]}
        elif self.mode == "DUAL_READ":
            # Shadow testing
            faiss_res = ["chunk_1"]
            pg_res = ["chunk_1"]
            recall_match = (faiss_res == pg_res)
            return {"source": "FAISS", "results": faiss_res, "shadow_match": recall_match}
        elif self.mode == "PGVECTOR_PRIMARY":
            return {"source": "PGVECTOR", "results": ["chunk_1"]}

# --- FASE 2 & 3 & 4: BACKFILL CONTROLLER & RESOURCE & METRICS ---
class MigrationBackfillController:
    def __init__(self):
        self.state = "STOPPED"
        self.metrics = {
            "docs_processed": 0,
            "chunks_created": 0,
            "errors": 0,
            "time_elapsed_ms": 0
        }
        self.nocturnal_window = (22, 6) # 10 PM to 6 AM
        self.cpu_limit_percent = 20
        
    def _is_nocturnal_window(self):
        # Mock logic for time window
        current_hour = 23 # Simulating 11 PM
        return current_hour >= self.nocturnal_window[0] or current_hour < self.nocturnal_window[1]

    def start(self):
        if not self._is_nocturnal_window():
            print("[BACKFILL] Warning: Starting outside nocturnal window. CPU throttled heavily.")
            self.cpu_limit_percent = 5
        self.state = "RUNNING"
        print(f"[BACKFILL] Started. CPU Limit: {self.cpu_limit_percent}%")

    def pause(self):
        self.state = "PAUSED"
        print("[BACKFILL] Paused.")

    def resume(self):
        self.state = "RUNNING"
        print("[BACKFILL] Resumed.")

    def cancel(self):
        self.state = "CANCELLED"
        print("[BACKFILL] Cancelled.")

    def status(self):
        print(f"[BACKFILL STATUS] State: {self.state} | Metrics: {self.metrics}")

    def simulate_processing(self, num_docs):
        if self.state != "RUNNING":
            return
            
        start_t = time.time()
        for i in range(num_docs):
            if random.random() < 0.05: # 5% error rate
                self.metrics["errors"] += 1
            else:
                self.metrics["docs_processed"] += 1
                self.metrics["chunks_created"] += random.randint(5, 15)
                
            # Simulate CPU throttling by sleeping
            time.sleep(0.01 if self.cpu_limit_percent > 10 else 0.05)
            
        self.metrics["time_elapsed_ms"] += (time.time() - start_t) * 1000

# --- FASE 5: CUTOVER SIMULATION ---
def run_cutover_simulation():
    print("=== V7 MIGRATION CUTOVER SIMULATION ===")
    
    router = VectorEngineRouter()
    backfill = MigrationBackfillController()
    admin_user = "CISO_Admin"
    
    print("\n>>> STATE: FAISS_ONLY (Baseline) <<<")
    router.route_write("doc_001", "data")
    print(router.route_read("Query A"))
    
    print("\n>>> INITIATING MIGRATION BACKFILL <<<")
    backfill.start()
    backfill.simulate_processing(50)
    backfill.status()
    
    print("\n>>> STATE: DUAL_WRITE (Syncing new data) <<<")
    router.change_mode("DUAL_WRITE", admin_user)
    print(router.route_write("doc_002", "new_data"))
    
    print("\n>>> STATE: DUAL_READ (Validation) <<<")
    router.change_mode("DUAL_READ", admin_user)
    read_res = router.route_read("Query B")
    print(read_res)
    if read_res.get("shadow_match"):
        print("[VALIDATION] PGVECTOR Recall matches FAISS perfectly.")
        
    print("\n>>> STATE: PGVECTOR_PRIMARY (Go-Live) <<<")
    router.change_mode("PGVECTOR_PRIMARY", admin_user)
    print(router.route_read("Query C"))
    
    print("\n>>> INCIDENT: HIGH MEMORY USAGE DETECTED <<<")
    # Simulate an incident requiring rollback
    router.rollback(admin_user)
    print(router.route_read("Query D"))
    
    print("\n>>> AUDIT LOGS <<<")
    for log in router.audit_log:
        print(log)

if __name__ == "__main__":
    run_cutover_simulation()
