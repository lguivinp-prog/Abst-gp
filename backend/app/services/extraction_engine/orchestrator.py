import json
import logging
from app.core.config import settings
from app.core.redis import ocr_queue, task_queue
from app.models.domain import UploadedDocument
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

class ExtractionOrchestrator:
    """
    Coordinates the execution of V1 and V2 OCR pipelines, routing tasks
    to their appropriate queues, and managing shadow mode.
    Does not contain any PaddleOCR or OpenCV logic.
    """
    
    @staticmethod
    def coordinate_extraction(case_id: int, file_path: str, job_id: str):
        """
        Called by the primary `process_document_task` running on the default worker.
        """
        engine = settings.OCR_ENGINE.lower()
        shadow_mode = settings.OCR_SHADOW_MODE
        
        logger.info(f"Orchestrator invoked. Engine: {engine}, Shadow Mode: {shadow_mode}")
        
        if engine == "v2":
            # Create OCRProcessingRun for robust dispatch
            import uuid
            import hashlib
            from app.models.domain import OCRProcessingRun, ProcessingJob
            db = SessionLocal()
            try:
                doc = db.query(UploadedDocument).filter(UploadedDocument.processing_job_id == job_id).first()
                if not doc:
                    doc = db.query(UploadedDocument).filter(UploadedDocument.case_id == case_id).order_by(UploadedDocument.id.desc()).first()
                
                # Create a ProcessingJob to satisfy check_exclusive_scope
                pj = ProcessingJob(
                    document_id=doc.id,
                    worker_type="ocr_v2",
                    status="pending"
                )
                db.add(pj)
                db.flush()
                
                run_id = uuid.uuid4()
                # Run dedup key must be exactly 64 hex characters
                dedup_key = hashlib.sha256(str(run_id).encode()).hexdigest()
                run = OCRProcessingRun(
                    run_id=run_id,
                    uploaded_document_id=doc.id,
                    processing_job_id=pj.id,
                    execution_role="PRIMARY",
                    engine="v2",
                    status="QUEUED",
                    run_dedup_key=dedup_key
                )
                db.add(run)
                db.commit()
                
                # Dispatch to V2 pipeline on ocr_tasks queue
                job_v2 = ocr_queue.enqueue(
                    "app.worker.ocr_worker_tasks.process_run_v2",
                    args=(str(run_id),),
                    job_timeout=3600
                )
                
                # To maintain compatibility with tests that poll the original job_id, wait for V2 completion
                import time
                from rq import get_current_job
                current_job = get_current_job()
                
                while True:
                    db.refresh(run)
                    if run.status == 'COMPLETED':
                        if current_job:
                            current_job.meta['progress'] = 100
                            current_job.meta['status_message'] = "Completado"
                            current_job.save_meta()
                        break
                    elif run.status == 'FAILED':
                        if current_job:
                            current_job.meta['progress'] = 100
                            current_job.meta['status_message'] = f"Error: {run.failure_detail}"
                            current_job.save_meta()
                        break
                    
                    if current_job:
                        current_job.meta['progress'] = 50
                        current_job.save_meta()
                        
                    time.sleep(2)
            finally:
                db.close()
        else:
            # Engine is V1
            if shadow_mode:
                # Dispatch V2 in background for shadow testing (does not modify visible results)
                ocr_queue.enqueue(
                    "app.worker.tasks.ocr_shadow_task",
                    args=(case_id, file_path),
                    job_timeout=3600
                )
            
            # Execute V1 inline since we're already in the default worker
            from app.worker.tasks import execute_v1_pipeline
            execute_v1_pipeline(case_id, file_path, job_id)
