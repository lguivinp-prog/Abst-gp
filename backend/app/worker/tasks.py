import os
import json
import logging
from datetime import datetime
import threading
import time
from rq import get_current_job
from app.core.database import SessionLocal
from app.models.domain import CaseFile, UploadedDocument, ParsedSection, OCRProcessingRun
from app.services.ocr.engine import process_pdf
from app.services.ocr.cleaner import clean_ocr_text
from app.services.extraction.section_detector import extract_sections

def process_run_v1(run_id: str):
    """
    Wrapper for V1 execution mapped from OCRProcessingRun.
    Updates the run status and triggers the legacy V1 pipeline.
    """
    job = get_current_job()
    db = SessionLocal()
    
    try:
        import logging
        logger = logging.getLogger(__name__)
        
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
            # Execute legacy pipeline
            job_id = job.id if job else run.rq_job_id
            fallback_used = (run.execution_role == 'FALLBACK')
            execute_v1_pipeline(doc.case_id, doc.stored_path, job_id, fallback_used)
        finally:
            stop_event.set()
            hb_thread.join(timeout=2)
        
        # Mark Completed
        run = db.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
        run.status = 'COMPLETED'
        run.finished_at = datetime.utcnow()
        run.quality_status = 'APPROVED'
        db.commit()
        
        # If this is PRIMARY v1 in a validation case, we must create SHADOW v2
        if run.execution_role == 'PRIMARY' and run.engine == 'v1' and run.validation_case_id:
            try:
                # Calculate baseline snapshot
                from app.services.ocr.checksum import calculate_baseline_hash
                from app.models.domain import GeneratedOutput
                
                sections = db.query(ParsedSection).filter(ParsedSection.case_id == doc.case_id).all()
                generated_out = db.query(GeneratedOutput).filter(GeneratedOutput.case_id == doc.case_id).order_by(GeneratedOutput.id.desc()).first()
                html = generated_out.html_output if generated_out else ""
                
                baseline_hash = calculate_baseline_hash(sections, html, "")
                
                # Update run metadata with baseline info
                meta = dict(run.metadata_ or {})
                meta["baseline"] = {
                    "status": "BASELINE_READY",
                    "hash": baseline_hash,
                    "created_at": datetime.utcnow().isoformat()
                }
                run.metadata_ = meta
                db.commit()
                
                # Now, strictly after BASELINE_READY, create SHADOW
                shadow_dedup = hashlib.sha256(f"{run.validation_case_id}:SHADOW:v2:1".encode()).hexdigest()
                shadow_run = OCRProcessingRun(
                    uploaded_document_id=run.uploaded_document_id,
                    validation_case_id=run.validation_case_id,
                    execution_role="SHADOW",
                    engine="v2",
                    status="PENDING_DISPATCH",
                    source_run_id=run.run_id,
                    run_dedup_key=shadow_dedup
                )
                from app.services.ocr.run_repository import OCRRunRepository
                repo = OCRRunRepository(db)
                repo.create_run(shadow_run)
                db.commit()
            except Exception as snap_e:
                logger.error(f"Failed to create baseline snapshot for run {run_id}: {str(snap_e)}")
                meta = dict(run.metadata_ or {})
                meta["baseline"] = {
                    "status": "BASELINE_SNAPSHOT_FAILED",
                    "error": str(snap_e)
                }
                run.metadata_ = meta
                db.commit()
                # Do NOT create SHADOW
            
    except Exception as e:
        db.rollback()
        run = db.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
        if run:
            run.status = 'FAILED'
            run.failure_code = 'TASK_EXCEPTION'
            run.failure_detail = str(e)
            run.finished_at = datetime.utcnow()
            db.commit()
        raise e
    finally:
        db.close()

def execute_v1_pipeline(case_id: int, file_path: str, job_id: str, fallback_used: bool = False):
    """
    Original V1 pipeline. Kept unmodified for compatibility and fallback.
    """
    job = get_current_job()
    db = SessionLocal()
    try:
        # 1. Update Document status to 'started'
        doc = db.query(UploadedDocument).filter(UploadedDocument.processing_job_id == job_id).first()
        if not doc:
            doc = db.query(UploadedDocument).filter(
                UploadedDocument.case_id == case_id,
                UploadedDocument.document_type == "requirement"
            ).order_by(UploadedDocument.id.desc()).first()
            
        if doc:
            doc.processing_status = "started"
            if fallback_used:
                doc.ocr_engine_used = "v1_fallback"
            else:
                doc.ocr_engine_used = "v1"
            if job:
                job.meta['progress'] = 10
                job.meta['status_message'] = "Iniciando OCR (V1)..."
                job.save_meta()
            db.commit()

        # 2. Run OCR
        ocr_result = process_pdf(file_path)
        
        if job:
            job.meta['progress'] = 50
            job.meta['status_message'] = "Limpiando texto extraído..."
            job.save_meta()

        # 3. Clean OCR text and Extract Sections via DocumentExtractionAgent
        from app.services.extraction.document_extraction_agent import DocumentExtractionAgent
        
        agent = DocumentExtractionAgent()
        db_case = db.query(CaseFile).filter(CaseFile.id == case_id).first()
        
        extracted_sections = agent.process(ocr_result.pages_text, db_case.contract_type)
        
        # 4. Save extracted data to document
        if doc:
            doc.text_extracted = ocr_result.text
            doc.ocr_used = ocr_result.ocr_used
            doc.ocr_metadata = {
                "page_count": ocr_result.page_count,
                "confidence_avg": ocr_result.confidence_avg,
                "ocr_pipeline_version": "1.0",
                "fallback_used": fallback_used
            }
            db.commit()

        if job:
            job.meta['progress'] = 70
            job.meta['status_message'] = "Detectando y limpiando secciones..."
            job.save_meta()

        # 6. Save Sections
        for sec_data in extracted_sections:
            sec = ParsedSection(
                case_id=case_id,
                original_roman=sec_data.metadata.get("original_roman"),
                original_order=sec_data.metadata.get("original_order"),
                title=sec_data.metadata.get("title"),
                original_text=sec_data.original_text,
                cleaned_text=sec_data.cleaned_text,
                normalized_text=sec_data.normalized_text,
                current_text=sec_data.cleaned_text,
                structure_json=sec_data.structure_json,
                corrections_json=sec_data.corrections_json,
                warnings_json=sec_data.warnings_json,
                extraction_metadata=sec_data.metadata,
                confidence_score=sec_data.metadata.get("confidence", 0.0),
                review_status="pending_review"
            )
            db.add(sec)
        
        # 7. Update Case Status and Doc Status
        db_case.status = "REVIEW_SECTIONS"
        if doc:
            doc.processing_status = "finished"
        
        if job:
            job.meta['progress'] = 100
            job.meta['status_message'] = "Completado"
            job.save_meta()
            
        db.commit()
        
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        error_trace = traceback.format_exc()
        
        doc = db.query(UploadedDocument).filter(UploadedDocument.processing_job_id == job_id).first()
        if not doc:
            doc = db.query(UploadedDocument).filter(
                UploadedDocument.case_id == case_id,
                UploadedDocument.document_type == "requirement"
            ).order_by(UploadedDocument.id.desc()).first()
            
        if doc:
            doc.processing_status = "failed"
            doc.processing_error = error_trace
            doc.ocr_status = "FAILED"
            
        db_case = db.query(CaseFile).filter(CaseFile.id == case_id).first()
        if db_case:
            db_case.status = "ERROR"
            
        if job:
            job.meta['progress'] = 100
            job.meta['status_message'] = f"Error: {error_msg}"
            job.save_meta()
            
        db.commit()
        raise e
        
    finally:
        db.close()


def process_requirement_task(case_id: int, file_path: str):
    """
    Main entry point for document processing.
    Delegates routing to the ExtractionOrchestrator.
    """
    from app.services.extraction_engine.orchestrator import ExtractionOrchestrator
    
    job = get_current_job()
    job_id = job.id if job else "unknown"
    
    ExtractionOrchestrator.coordinate_extraction(case_id, file_path, job_id)
