import time
import threading
import os
import json
import traceback
import logging
from datetime import datetime
from rq import get_current_job
from app.core.database import SessionLocal
from app.models.domain import CaseFile, UploadedDocument, ParsedSection, OCRProcessingRun
from app.services.extraction_engine.v2_pipeline import OCRV2Pipeline
from app.services.extraction_engine.adapters.structured_document_adapter import StructuredDocumentAdapter
from app.services.extraction_engine.utils.persistence import AtomicPersistence

logger = logging.getLogger(__name__)

def process_run_v2(run_id: str):
    """
    Wrapper for V2 execution mapped from OCRProcessingRun.
    Executes V2 Pipeline either as PRIMARY or SHADOW.
    """
    job = get_current_job()
    db = SessionLocal()
    
    try:
        updated = db.query(OCRProcessingRun).filter(
            OCRProcessingRun.run_id == run_id,
            OCRProcessingRun.status.in_(['QUEUED', 'DISPATCHING'])
        ).update({
            "status": "RUNNING",
            "started_at": datetime.utcnow(),
            "heartbeat_at": datetime.utcnow()
        })
        db.commit()
        
        if updated == 0:
            run = db.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
            if run and run.status in ('RUNNING', 'COMPLETED', 'FAILED'):
                logger.info(f"Run {run_id} is already {run.status}. Skipping duplicate execution.")
                return
            raise ValueError(f"Run {run_id} is not QUEUED or DISPATCHING (status: {run.status if run else 'None'})")
            
        run = db.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
        doc = db.query(UploadedDocument).filter(UploadedDocument.id == run.uploaded_document_id).first()
        
        file_path = doc.stored_path
        case_id = doc.case_id
        
        logger.info(f"Starting OCR V2 for run {run_id}. Role: {run.execution_role}")
        
        stop_event = threading.Event()
        def heartbeat_worker():
            interval = int(os.environ.get("OCR_RUN_HEARTBEAT_INTERVAL_SECONDS", 15))
            while not stop_event.is_set():
                try:
                    db_hb = SessionLocal()
                    r = db_hb.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
                    if r and r.status == 'RUNNING':
                        r.heartbeat_at = datetime.utcnow()
                        db_hb.commit()
                    db_hb.close()
                except Exception:
                    pass
                time.sleep(interval)
                
        hb_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        hb_thread.start()
        
        try:
            if run.execution_role == "PRIMARY":
                doc.processing_status = "started"
                db.commit()
                
            # 1. Run V2 Pipeline
            pipeline = OCRV2Pipeline()
            structured_doc = pipeline.process_document(file_path)
            
            from app.core.config import settings
            
            if run.execution_role == "SHADOW":
                # Shadow Mode: Save artifacts to isolated path
                val_case = run.validation_case_id
                isolated_dir = os.path.join(
                    settings.UPLOADS_DIR,
                    "validation_artifacts",
                    str(val_case) if val_case else "unknown",
                    str(doc.id),
                    str(run.run_id)
                )
                os.makedirs(isolated_dir, exist_ok=True)
                doc_path = os.path.join(isolated_dir, f"structured_doc_{run.run_id}.json")
                
                with open(doc_path, "w", encoding="utf-8") as f:
                    json.dump(structured_doc.model_dump(), f, ensure_ascii=False, indent=2)
                    
                # DO NOT overwrite UploadedDocument or ParsedSection product records
                run.status = 'COMPLETED'
                run.finished_at = datetime.utcnow()
                run.score = structured_doc.confidence
                run.review_threshold = settings.OCR_REVIEW_THRESHOLD
                run.structured_document_path = doc_path
                # Quality status for SHADOW doesn't strictly matter as it doesn't face user, but CheckConstraint requires it if COMPLETED
                run.quality_status = 'APPROVED' if structured_doc.confidence >= settings.OCR_REVIEW_THRESHOLD else 'REVIEW_REQUIRED'
                
                # Save metrics explicitly in run metadata
                run.metadata_ = {
                    "shadow_ocr": {
                        "engine": "v2",
                        "score": structured_doc.confidence,
                        "pipeline_version": "2.0.0",
                        "review_threshold": settings.OCR_REVIEW_THRESHOLD
                    }
                }
                db.commit()
                
            else: # PRIMARY
                # Use AtomicPersistence for product record
                persister = AtomicPersistence()
                doc_path, doc_checksum = persister.save_structured_document(
                    settings.UPLOADS_DIR,
                    run.run_id,
                    structured_doc.model_dump()
                )
                
                score = structured_doc.confidence
                ocr_status = "APPROVED" if score >= settings.OCR_REVIEW_THRESHOLD else "REVIEW_REQUIRED"
                
                # Update product columns
                doc.ocr_engine_used = "v2"
                doc.ocr_score = score
                doc.ocr_status = ocr_status
                doc.ocr_processed_at = datetime.utcnow()
                doc.structured_document_path = doc_path
                
                trace_meta = {
                    "primary_ocr": {
                        "engine": "v2",
                        "status": ocr_status
                    },
                    "ocr_pipeline_version": "2.0.0",
                    "adapter_version": "1.0",
                    "review_threshold": settings.OCR_REVIEW_THRESHOLD
                }
                doc.ocr_metadata = trace_meta
                
                # Update Run
                run.status = 'COMPLETED'
                run.finished_at = datetime.utcnow()
                run.score = score
                run.review_threshold = settings.OCR_REVIEW_THRESHOLD
                run.structured_document_path = doc_path
                run.structured_document_checksum = doc_checksum
                run.quality_status = ocr_status
                
                # Parse Sections
                parsed_sections = StructuredDocumentAdapter.to_parsed_sections(case_id, structured_doc)
                if not parsed_sections:
                    from app.services.extraction.exceptions import NoSectionsExtractedError
                    raise NoSectionsExtractedError("No se detectaron secciones estructurales válidas en el documento (V2).")

                for sec in parsed_sections:
                    db.add(sec)
                    
                db_case = db.query(CaseFile).filter(CaseFile.id == case_id).first()
                if db_case:
                    db_case.status = "REVIEW_SECTIONS"
                    
                doc.processing_status = "finished"
                db.commit()
        finally:
            stop_event.set()
            hb_thread.join(timeout=2)
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        logger.error(f"Error in OCR V2 Pipeline for run {run_id}: {error_msg}")
        logger.error(traceback.format_exc())
        
        run = db.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
        if run:
            run.status = 'FAILED'
            run.failure_code = 'TASK_EXCEPTION'
            run.failure_detail = error_msg
            run.finished_at = datetime.utcnow()
            run.quality_status = None
            
            if run.execution_role == 'PRIMARY':
                doc = db.query(UploadedDocument).filter(UploadedDocument.id == run.uploaded_document_id).first()
                if doc:
                    doc.processing_status = "failed"
                    doc.processing_error = error_msg
                    doc.ocr_status = "FAILED"
                    
                    db_case = db.query(CaseFile).filter(CaseFile.id == doc.case_id).first()
                    if db_case:
                        db_case.status = "ERROR"

                # Attempt to create FALLBACK immediately on clean exception
                # If we die (SIGKILL), Monitor handles it.
                from app.services.ocr.run_repository import OCRRunRepository
                repo = OCRRunRepository(db)
                fallback = OCRProcessingRun(
                    uploaded_document_id=run.uploaded_document_id,
                    validation_case_id=run.validation_case_id,
                    processing_job_id=run.processing_job_id,
                    execution_role='FALLBACK',
                    engine='v1',
                    status='PENDING_DISPATCH',
                    source_run_id=run.run_id,
                    run_dedup_key=f"{run.run_dedup_key[:32]}{'f'*32}"[:64]
                )
                try:
                    repo.create_run(fallback)
                    logger.info("FALLBACK run created immediately due to task exception")
                except Exception as fallback_e:
                    logger.error(f"Failed to create fallback: {str(fallback_e)}")
            
            db.commit()
        raise
    finally:
        db.close()
