import time
import logging
from datetime import datetime, timedelta
from redis import Redis
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError
from rq.registry import StartedJobRegistry, FailedJobRegistry

from app.core.database import SessionLocal
from app.models.domain import OCRProcessingRun
from app.services.ocr.run_repository import OCRRunRepository
from app.core.config import settings

logger = logging.getLogger(__name__)

class FallbackMonitor:
    def __init__(self, queue_names=["default", "ocr_tasks"]):
        self.redis_conn = Redis.from_url(settings.REDIS_URL)
        self.heartbeat_grace_seconds = int(os.environ.get("OCR_RUN_HEARTBEAT_GRACE_SECONDS", 90))
        self.queue_names = queue_names
        
    def check_and_recover_dead_runs(self):
        db = SessionLocal()
        try:
            repo = OCRRunRepository(db)
            now = datetime.utcnow()
            timeout_threshold = now - timedelta(seconds=self.heartbeat_grace_seconds)
            
            # 1. RUNNING with expired heartbeat
            dead_runs = db.query(OCRProcessingRun).filter(
                OCRProcessingRun.status == 'RUNNING',
                (OCRProcessingRun.heartbeat_at < timeout_threshold) | 
                ((OCRProcessingRun.heartbeat_at == None) & (OCRProcessingRun.started_at < timeout_threshold))
            ).with_for_update(skip_locked=True).all()
            
            for run in dead_runs:
                self._handle_dead_run(run, repo, db)
                
            # 2. DISPATCHING with expired lease
            dispatch_grace = now - timedelta(seconds=30)
            stuck_dispatch = db.query(OCRProcessingRun).filter(
                OCRProcessingRun.status == 'DISPATCHING',
                OCRProcessingRun.dispatch_lease_expires_at < now
            ).with_for_update(skip_locked=True).all()
            for run in stuck_dispatch:
                logger.warning(f"Run {run.run_id} stuck in DISPATCHING. Reverting to PENDING_DISPATCH.")
                run.status = 'PENDING_DISPATCH'
                run.dispatch_owner = None
                run.dispatch_token = None
            
            # 3. QUEUED without job in RQ (lost enqueue)
            queued_threshold = now - timedelta(minutes=10)
            queued_runs = db.query(OCRProcessingRun).filter(
                OCRProcessingRun.status == 'QUEUED',
                OCRProcessingRun.dispatch_claimed_at < queued_threshold
            ).with_for_update(skip_locked=True).all()
            
            for run in queued_runs:
                # Check if job exists in RQ
                job_exists = False
                if run.rq_job_id:
                    try:
                        Job.fetch(run.rq_job_id, connection=self.redis_conn)
                        job_exists = True
                    except NoSuchJobError:
                        pass
                
                if not job_exists:
                    logger.warning(f"Run {run.run_id} is QUEUED but job {run.rq_job_id} missing in RQ.")
                    run.status = 'FAILED'
                    run.failure_code = 'RQ_FAILED'
                    run.failure_detail = 'Job disappeared from RQ while QUEUED'
                    run.finished_at = now
                    self._create_fallback_if_needed(run, repo, db)
                    
            db.commit()
        except Exception as e:
            logger.error(f"Monitor error: {str(e)}")
            db.rollback()
        finally:
            db.close()
            
    def _handle_dead_run(self, run: OCRProcessingRun, repo: OCRRunRepository, db: Session):
        logger.warning(f"Run {run.run_id} evaluating for DEAD status.")
        job_id = run.rq_job_id
        
        # Analyze RQ to determine real cause
        cause = 'HEARTBEAT_TIMEOUT'
        
        if job_id:
            job_found = False
            for qname in self.queue_names:
                q = Queue(qname, connection=self.redis_conn)
                
                try:
                    job = Job.fetch(job_id, connection=self.redis_conn)
                    job_found = True
                    # Job exists. Where is it?
                    if job.is_failed:
                        cause = 'TASK_EXCEPTION'
                        break
                    if job.is_finished:
                        # Job finished but DB is RUNNING. Something failed during DB commit.
                        cause = 'DB_COMMIT_FAILED'
                        break
                    
                    started_registry = StartedJobRegistry(queue=q)
                    if job_id in started_registry.get_job_ids():
                        # Job is in StartedJobRegistry. Has the worker crashed (OOM)?
                        # We don't have worker monitoring here easily, so we assume HEARTBEAT_TIMEOUT or WORKER_LOST
                        cause = 'WORKER_LOST'
                        
                except NoSuchJobError:
                    pass
            
            if not job_found:
                # Job doesn't exist anymore
                cause = 'JOB_EXPIRED'
        
        logger.info(f"Marking run {run.run_id} as FAILED. Cause: {cause}")
        run.status = 'FAILED'
        run.failure_code = cause
        run.finished_at = datetime.utcnow()
        
        self._create_fallback_if_needed(run, repo, db)
        
    def _create_fallback_if_needed(self, run: OCRProcessingRun, repo: OCRRunRepository, db: Session):
        # Only PRIMARY v2 gets a fallback
        # SHADOW NEVER gets a fallback
        # FALLBACK NEVER gets a fallback
        if run.execution_role == 'PRIMARY' and run.engine == 'v2':
            logger.info(f"Creating FALLBACK run for {run.run_id}")
            
            fallback = OCRProcessingRun(
                uploaded_document_id=run.uploaded_document_id,
                validation_case_id=run.validation_case_id,
                processing_job_id=run.processing_job_id,
                execution_role='FALLBACK',
                engine='v1',
                status='PENDING_DISPATCH',
                source_run_id=run.run_id,
                # Deterministic deduplication key for the fallback run
                run_dedup_key=f"{run.run_dedup_key[:32]}{'f'*32}"[:64] 
            )
            
            try:
                repo.create_run(fallback)
            except Exception as e:
                logger.error(f"Failed to create FALLBACK run for {run.run_id}: {str(e)}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    monitor = FallbackMonitor()
    logger.info("Started Fallback Monitor")
    while True:
        monitor.check_and_recover_dead_runs()
        time.sleep(60)
