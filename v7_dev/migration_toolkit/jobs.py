from enum import Enum
import hashlib

class JobState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class MigrationJob:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.state = JobState.PENDING
        self.processed_chunks = set()
        
    def _generate_chunk_hash(self, chunk_id: str, content: str) -> str:
        return hashlib.sha256(f"{chunk_id}:{content}".encode()).hexdigest()
        
    def add_chunk(self, chunk_id: str, content: str):
        chunk_hash = self._generate_chunk_hash(chunk_id, content)
        
        # Idempotency check
        if chunk_hash in self.processed_chunks:
            print(f"[JOB {self.job_id}] Chunk {chunk_id} already processed. Skipping.")
            return False
            
        self.processed_chunks.add(chunk_hash)
        return True

    def transition(self, new_state: JobState):
        self.state = new_state
        print(f"[JOB {self.job_id}] Transición a {self.state.value}")
