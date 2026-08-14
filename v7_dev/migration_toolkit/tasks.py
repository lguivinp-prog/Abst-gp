from celery import Celery
import os
import requests
import time

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000/v7/gateway")

app = Celery('migration_tasks', broker=BROKER_URL, backend=RESULT_BACKEND)

@app.task(bind=True, max_retries=3)
def process_chunk(self, job_id, chunk_data):
    # Check if job is paused or cancelled via Redis (simulated here)
    # In a real app we would check a redis key `job:{job_id}:status`
    try:
        res = requests.post(
            f"{GATEWAY_URL}/sanitize", 
            json=chunk_data,
            headers={"Authorization": "Bearer MOCK_JWT"}
        )
        res.raise_for_status()
        return {"status": "SUCCESS", "chunk_id": chunk_data.get("request_id")}
    except Exception as exc:
        # Exponential backoff: 2^request * 10
        raise self.retry(exc=exc, countdown=10 ** self.request.retries)
