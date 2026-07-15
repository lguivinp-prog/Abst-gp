import time
import uuid
import socket
import logging
from datetime import datetime, timedelta
from redis import Redis
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import SessionLocal
from app.models.domain import OCRProcessingRun
from app.core.config import settings

logger = logging.getLogger(__name__)

# Centralized route table
ROUTE_TABLE = {
    ("PRIMARY", "v1"): {
        "queue": "default",
        "function": "app.worker.tasks.process_run_v1",
    },
    ("PRIMARY", "v2"): {
        "queue": "ocr_tasks",
        "function": "app.worker.ocr_worker_tasks.process_run_v2",
    },
    ("SHADOW", "v2"): {
        "queue": "ocr_tasks",
        "function": "app.worker.ocr_worker_tasks.process_run_v2",
    },
    ("FALLBACK", "v1"): {
        "queue": "default",
        "function": "app.worker.tasks.process_run_v1",
    },
}

class FallbackDispatcher:
    def __init__(self, lease_duration_seconds=30):
        self.redis_conn = Redis.from_url(settings.REDIS_URL)
        self.lease_duration_seconds = lease_duration_seconds
        self.owner_id = f"dispatcher-{socket.gethostname()}-{uuid.uuid4()}"
        
        # Cache queues
        self.queues = {
            "default": Queue("default", connection=self.redis_conn),
            "ocr_tasks": Queue("ocr_tasks", connection=self.redis_conn)
        }
        
    def get_queue(self, queue_name: str) -> Queue:
        if queue_name not in self.queues:
            self.queues[queue_name] = Queue(queue_name, connection=self.redis_conn)
        return self.queues[queue_name]
        
    def process_one_batch(self, batch_size=10):
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            
            # 1. Select PENDING_DISPATCH or expired DISPATCHING with SKIP LOCKED
            runs_to_claim = db.query(OCRProcessingRun).filter(
                or_(
                    OCRProcessingRun.status == 'PENDING_DISPATCH',
                    (OCRProcessingRun.status == 'DISPATCHING') & (OCRProcessingRun.dispatch_lease_expires_at < now)
                )
            ).with_for_update(skip_locked=True).limit(batch_size).all()
            
            if not runs_to_claim:
                return 0
                
            claims = []
            for run in runs_to_claim:
                # 2. Change to DISPATCHING and set lease
                token = uuid.uuid4()
                run.status = 'DISPATCHING'
                run.dispatch_owner = self.owner_id
                run.dispatch_token = token
                run.dispatch_claimed_at = now
                run.dispatch_lease_expires_at = now + timedelta(seconds=self.lease_duration_seconds)
                run.dispatch_attempt_count += 1
                run.last_dispatch_attempt_at = now
                
                claims.append({
                    "run_id": str(run.run_id),
                    "token": token,
                    "role": run.execution_role,
                    "engine": run.engine,
                    "job_id": f"job_{run.run_dedup_key}"
                })
                
            # 3. Commit PostgreSQL claim
            db.commit()
            
            # Now we dispatch them out-of-transaction
            dispatched = 0
            for claim in claims:
                self._dispatch_run(claim)
                dispatched += 1
                
            return dispatched
                
        except Exception as e:
            logger.error(f"Dispatcher batch error: {str(e)}")
            db.rollback()
            return 0
        finally:
            db.close()
            
    def _dispatch_run(self, claim):
        db = SessionLocal()
        try:
            route = ROUTE_TABLE.get((claim["role"], claim["engine"]))
            if not route:
                raise ValueError(f"Invalid route combination: {claim['role']} - {claim['engine']}")
                
            queue_name = route["queue"]
            func_path = route["function"]
            job_id = claim["job_id"]
            
            # 4 & 5. Consult RQ and Enqueue if not exists
            queue = self.get_queue(queue_name)
            
            try:
                job = Job.fetch(job_id, connection=self.redis_conn)
                logger.info(f"Job {job_id} already exists in Redis.")
            except NoSuchJobError:
                logger.info(f"Enqueuing job {job_id} to {queue_name}")
                # We pass the run_id to the task
                job = queue.enqueue(
                    func_path,
                    args=(claim["run_id"],),
                    job_id=job_id
                )
                
            # 6. Change to QUEUED verifying dispatch_token
            # We don't want to update if another dispatcher stole it because of a long freeze
            run = db.query(OCRProcessingRun).filter(
                OCRProcessingRun.run_id == claim["run_id"],
                OCRProcessingRun.dispatch_token == claim["token"]
            ).first()
            
            if run:
                run.status = 'QUEUED'
                run.rq_job_id = job.id
                db.commit()
                logger.info(f"Run {claim['run_id']} marked as QUEUED")
            else:
                logger.warning(f"Run {claim['run_id']} lost lease before marking QUEUED")
                
        except Exception as e:
            logger.error(f"Failed to dispatch run {claim['run_id']}: {str(e)}")
            db.rollback()
            
            # We try to record the error, but still verify token
            try:
                run = db.query(OCRProcessingRun).filter(
                    OCRProcessingRun.run_id == claim["run_id"],
                    OCRProcessingRun.dispatch_token == claim["token"]
                ).first()
                if run:
                    run.last_dispatch_error = str(e)
                    # We leave it as DISPATCHING. It will expire and be picked up again.
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dispatcher = FallbackDispatcher()
    logger.info(f"Started dispatcher {dispatcher.owner_id}")
    while True:
        processed = dispatcher.process_one_batch()
        if processed == 0:
            time.sleep(5)
