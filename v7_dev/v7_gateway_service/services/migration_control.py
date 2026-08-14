from enum import Enum
import time

class EngineState(Enum):
    FAISS_ONLY = "FAISS_ONLY"
    DUAL_WRITE = "DUAL_WRITE"
    DUAL_READ = "DUAL_READ"
    PGVECTOR_PRIMARY_SYNC = "PGVECTOR_PRIMARY_SYNC"
    FAISS_STANDBY = "FAISS_STANDBY"
    FAISS_RESYNCING = "FAISS_RESYNCING"

class MigrationControlService:
    def __init__(self):
        self.current_state = EngineState.FAISS_ONLY
        self.valid_transitions = {
            EngineState.FAISS_ONLY: [EngineState.DUAL_WRITE],
            EngineState.DUAL_WRITE: [EngineState.FAISS_ONLY, EngineState.DUAL_READ],
            EngineState.DUAL_READ: [EngineState.DUAL_WRITE, EngineState.FAISS_ONLY, EngineState.PGVECTOR_PRIMARY_SYNC],
            EngineState.PGVECTOR_PRIMARY_SYNC: [EngineState.FAISS_ONLY, EngineState.FAISS_STANDBY],
            EngineState.FAISS_STANDBY: [EngineState.PGVECTOR_PRIMARY_SYNC, EngineState.FAISS_RESYNCING],
            EngineState.FAISS_RESYNCING: [EngineState.FAISS_ONLY]
        }
        
        # Sliding Window for Rollback Intelligence
        self.error_window = []
        self.ERROR_RATE_THRESHOLD = 0.05 # 5%
        self.WINDOW_SIZE = 100 # Track last 100 requests
        
    def get_state(self) -> EngineState:
        return self.current_state
        
    def record_request(self, success: bool):
        self.error_window.append(0 if success else 1)
        if len(self.error_window) > self.WINDOW_SIZE:
            self.error_window.pop(0)
            
        if len(self.error_window) >= 10: # Minimum sample size
            error_rate = sum(self.error_window) / len(self.error_window)
            if error_rate > self.ERROR_RATE_THRESHOLD and self.current_state in [EngineState.DUAL_READ, EngineState.PGVECTOR_PRIMARY_SYNC]:
                self.trigger_rollback("ERROR_RATE_EXCEEDED")
        
    def transition_to(self, new_state: EngineState):
        if new_state not in self.valid_transitions[self.current_state]:
            raise ValueError(f"Invalid transition from {self.current_state} to {new_state}")
        
        # Log to Audit: VECTOR_ENGINE_CHANGED
        print(f"[AUDIT] VECTOR_ENGINE_CHANGED: {self.current_state.value} -> {new_state.value}")
        self.current_state = new_state
        
    def trigger_rollback(self, reason: str):
        print(f"[AUDIT] ROLLBACK_TRIGGERED: {reason}. Reverting to FAISS_ONLY")
        self.current_state = EngineState.FAISS_ONLY

migration_control = MigrationControlService()
