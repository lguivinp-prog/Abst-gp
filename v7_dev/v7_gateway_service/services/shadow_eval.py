import json
import os
import hashlib
import threading
import queue
import time
import logging
from logging.handlers import RotatingFileHandler

SHADOW_LOG_FILE = os.getenv("SHADOW_LOG_FILE", "shadow_eval.log")

# Configure Rotating File Handler
logger = logging.getLogger("ShadowEval")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(SHADOW_LOG_FILE, maxBytes=50*1024*1024, backupCount=10) # 50MB, 10 backups
handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(handler)

class ShadowEvaluationStorage:
    def __init__(self):
        # Async Queue for Shadow Writer
        self.q = queue.Queue(maxsize=1000)
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def _worker(self):
        while True:
            try:
                log_entry = self.q.get()
                if log_entry is None:
                    break # Stop signal
                
                logger.info(json.dumps(log_entry))
                self.q.task_done()
            except Exception as e:
                print(f"[SHADOW ERROR] Failed to write shadow log: {e}")
                # Generate alert here, but do not block

    def store_evaluation(self, tenant_id: str, query: dict, faiss_result: list, pg_result: list, latency_faiss: float, latency_pg: float):
        try:
            query_hash = hashlib.sha256(json.dumps(query).encode()).hexdigest()
            tenant_hash = hashlib.sha256(tenant_id.encode()).hexdigest()
            
            faiss_ids = {r.get("chunk_id") for r in faiss_result} if faiss_result else set()
            pg_ids = {r.get("chunk_id") for r in pg_result} if pg_result else set()
            
            recall = len(faiss_ids.intersection(pg_ids)) / len(faiss_ids) if faiss_ids else 1.0
            
            log_entry = {
                "tenant_hash": tenant_hash,
                "query_hash": query_hash,
                "latency_faiss_ms": latency_faiss,
                "latency_pg_ms": latency_pg,
                "faiss_count": len(faiss_ids),
                "pg_count": len(pg_ids),
                "recall": recall,
                "timestamp": time.time()
            }
            
            # Non-blocking put
            self.q.put_nowait(log_entry)
        except queue.Full:
            print("[SHADOW WARNING] Shadow queue is full. Dropping log entry.")
            # In a real app we'd increment the prometheus metric here.
            # We'll increment it globally if we have access, or just let Prometheus scrape it.
            # For simplicity in this demo, we'll import and increment
            from main import SHADOW_DROPPED
            SHADOW_DROPPED.inc()
        except Exception as e:
            print(f"[SHADOW ERROR] Failed to queue shadow eval: {e}")

shadow_storage = ShadowEvaluationStorage()
