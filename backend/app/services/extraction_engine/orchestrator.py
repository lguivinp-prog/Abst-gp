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
            # Dispatch to V2 pipeline on ocr_tasks queue
            ocr_queue.enqueue(
                "app.worker.tasks.ocr_processing_task",
                args=(case_id, file_path, job_id, False),
                job_timeout=3600
            )
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
