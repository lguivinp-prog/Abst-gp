import time
import threading
import os
import json
import socket
import hashlib
import traceback
import logging
from datetime import datetime, timezone
from rq import get_current_job
from rq.timeouts import JobTimeoutException
from app.core.database import SessionLocal
from app.models.domain import CaseFile, UploadedDocument, ParsedSection, OCRProcessingRun
from app.services.extraction_engine.v2_pipeline import OCRV2Pipeline
from app.services.extraction_engine.adapters.structured_document_adapter import StructuredDocumentAdapter
from app.services.extraction_engine.utils.persistence import AtomicPersistence
from app.services.job_repository import JobRepository

logger = logging.getLogger(__name__)


def process_run_v2(run_id: str):
    """
    Wrapper for V2 execution mapped from OCRProcessingRun in V5.4.
    Executes V2 Pipeline either as PRIMARY or SHADOW.
    Monitors liveness via WorkerHeartbeat and emits ProcessingMetrics.
    """
    job = get_current_job()
    db = SessionLocal()
    worker_name = f"ocr_worker_{os.getpid()}@{socket.gethostname()}"

    try:
        now = datetime.now(timezone.utc)
        updated = db.query(OCRProcessingRun).filter(
            OCRProcessingRun.run_id == run_id,
            OCRProcessingRun.status.in_(['QUEUED', 'DISPATCHING'])
        ).update({
            "status": "RUNNING",
            "started_at": now,
            "heartbeat_at": now
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

        # Obtener tenant_id del caso
        case = db.query(CaseFile).filter(CaseFile.id == case_id).first()
        tenant_id = case.tenant_id if case else None

        logger.info(f"Starting OCR V2 for run {run_id}. Role: {run.execution_role}, Worker: {worker_name}")

        # 1. Registrar latido de inicio V5.4
        JobRepository.record_heartbeat(
            db=db,
            worker_name=worker_name,
            worker_type="OCR_WORKER",
            status="BUSY",
            current_job_id=run.processing_job_id,
            tenant_id=tenant_id
        )

        if run.processing_job_id:
            JobRepository.update_progress(
                db=db,
                job_id=run.processing_job_id,
                progress=15,
                status_message="Iniciando extracción OCR V2...",
                status="PROCESSING",
                tenant_id=tenant_id,
                worker_name=worker_name
            )

        stop_event = threading.Event()
        def heartbeat_worker():
            interval = int(os.environ.get("OCR_RUN_HEARTBEAT_INTERVAL_SECONDS", 15))
            while not stop_event.is_set():
                try:
                    db_hb = SessionLocal()
                    hb_now = datetime.now(timezone.utc)
                    r = db_hb.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
                    if r and r.status == 'RUNNING':
                        r.heartbeat_at = hb_now
                        db_hb.commit()
                    # Latido V5.4
                    JobRepository.record_heartbeat(
                        db=db_hb,
                        worker_name=worker_name,
                        worker_type="OCR_WORKER",
                        status="BUSY",
                        current_job_id=run.processing_job_id,
                        tenant_id=tenant_id
                    )
                    db_hb.close()
                except Exception:
                    pass
                stop_event.wait(interval)

        hb_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        hb_thread.start()

        try:
            if run.execution_role == "PRIMARY":
                # Verificación temprana de estado terminal con bloqueo de fila
                locked_case = (
                    db.query(CaseFile)
                    .filter(CaseFile.id == case_id)
                    .populate_existing()
                    .with_for_update()
                    .first()
                )
                from app.models.v6.case_workflow import CaseWorkflow
                from app.models.v6.supplier_selection import SupplierSelectionFinal

                is_terminal = False
                if locked_case:
                    is_terminal = (
                        locked_case.status in ["APPROVED", "COMPLETED"]
                        or db.query(CaseWorkflow).filter(CaseWorkflow.case_id == case_id, CaseWorkflow.status.in_(["APPROVED", "COMPLETED"])).first() is not None
                        or db.query(SupplierSelectionFinal).filter(SupplierSelectionFinal.case_id == case_id).first() is not None
                    )

                if is_terminal:
                    logger.warning(
                        f"[OCR V2 Early] Descartando inicio: expediente {case_id} en estado terminal {locked_case.status if locked_case else 'N/A'}"
                    )
                    now_term = datetime.now(timezone.utc)
                    run.status = 'FAILED'
                    run.failure_code = 'CASE_TERMINAL_IMMUTABLE'
                    run.failure_detail = f"Procesamiento OCR V2 cancelado tempranamente: expediente cerrado ({locked_case.status if locked_case else 'N/A'})"
                    run.finished_at = now_term
                    run.quality_status = None

                    from app.models.domain import AuditLog
                    audit = AuditLog(
                        tenant_id=locked_case.tenant_id if locked_case else (tenant_id or "unknown"),
                        user_id=(locked_case.assigned_to_user_id or locked_case.created_by) if locked_case else None,
                        action="OCR_V2_PROCESSING_BLOCKED_TERMINAL",
                        entity_type="CaseFile",
                        entity_id=str(case_id),
                        details=f"Procesamiento OCR V2 cancelado tempranamente: expediente cerrado ({locked_case.status if locked_case else 'N/A'})",
                        status="FAILED"
                    )
                    db.add(audit)

                    if run.processing_job_id:
                        JobRepository.mark_failed(
                            db=db,
                            job_id=run.processing_job_id,
                            error_message=f"CASE_TERMINAL_IMMUTABLE: Operación descartada: el expediente {case_id} está en estado terminal {locked_case.status if locked_case else 'N/A'}.",
                            tenant_id=tenant_id,
                            worker_name=worker_name,
                            error_code="CASE_TERMINAL_IMMUTABLE",
                            error_category="TERMINAL_STATE",
                            failure_classification="FINAL"
                        )
                    db.commit()
                    return

                doc.processing_status = "started"
                db.commit()

            # 1. Run V2 Pipeline
            pipeline = OCRV2Pipeline()
            from app.storage.workspace import materialize_document
            with materialize_document(file_path) as local_temp_path:
                structured_doc = pipeline.process_document(local_temp_path)

            from app.core.config import settings
            from app.storage.factory import get_storage
            import io
            storage = get_storage()

            finish_now = datetime.now(timezone.utc)
            if run.execution_role == "SHADOW":
                # Shadow Mode: Save artifacts to isolated path using DocumentStorage
                val_case = run.validation_case_id

                json_bytes = json.dumps(structured_doc.model_dump(), ensure_ascii=False, indent=2).encode('utf-8')
                doc_path = storage.put(
                    tenant_id=f"validation_artifacts/{val_case if val_case else 'unknown'}",
                    document_id=f"{doc.id}/{run.run_id}/structured_doc_{run.run_id}.json",
                    file_stream=io.BytesIO(json_bytes)
                )

                # DO NOT overwrite UploadedDocument or ParsedSection product records
                run.status = 'COMPLETED'
                run.finished_at = finish_now
                run.score = structured_doc.confidence
                run.review_threshold = settings.OCR_REVIEW_THRESHOLD
                run.structured_document_path = doc_path
                run.quality_status = 'APPROVED' if structured_doc.confidence >= settings.OCR_REVIEW_THRESHOLD else 'REVIEW_REQUIRED'

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
                # 1. Bloqueo de fila y verificación atómica de estado terminal
                locked_case = (
                    db.query(CaseFile)
                    .filter(CaseFile.id == case_id)
                    .populate_existing()
                    .with_for_update()
                    .first()
                )

                if not locked_case:
                    raise ValueError(f"Expediente {case_id} no encontrado")

                from app.models.v6.case_workflow import CaseWorkflow
                from app.models.v6.supplier_selection import SupplierSelectionFinal

                is_terminal = (
                    locked_case.status in ["APPROVED", "COMPLETED"]
                    or db.query(CaseWorkflow).filter(CaseWorkflow.case_id == case_id, CaseWorkflow.status.in_(["APPROVED", "COMPLETED"])).first() is not None
                    or db.query(SupplierSelectionFinal).filter(SupplierSelectionFinal.case_id == case_id).first() is not None
                )

                if is_terminal:
                    logger.warning(
                        f"[OCR V2] Descartando persistencia: expediente {case_id} en estado terminal {locked_case.status}"
                    )
                    run.status = 'FAILED'
                    run.failure_code = 'CASE_TERMINAL_IMMUTABLE'
                    run.failure_detail = f"Extracción OCR V2 tardía descartada: expediente cerrado ({locked_case.status})"
                    run.finished_at = finish_now
                    run.quality_status = None

                    from app.models.domain import AuditLog
                    audit = AuditLog(
                        tenant_id=locked_case.tenant_id,
                        user_id=locked_case.assigned_to_user_id or locked_case.created_by,
                        action="OCR_V2_PROCESSING_BLOCKED_TERMINAL",
                        entity_type="CaseFile",
                        entity_id=str(case_id),
                        details=f"Extracción OCR V2 tardía descartada: expediente cerrado ({locked_case.status})",
                        status="FAILED"
                    )
                    db.add(audit)

                    if run.processing_job_id:
                        JobRepository.mark_failed(
                            db=db,
                            job_id=run.processing_job_id,
                            error_message=f"CASE_TERMINAL_IMMUTABLE: Operación descartada: el expediente {case_id} está en estado terminal {locked_case.status}.",
                            tenant_id=tenant_id,
                            worker_name=worker_name,
                            error_code="CASE_TERMINAL_IMMUTABLE",
                            error_category="TERMINAL_STATE",
                            failure_classification="FINAL"
                        )
                    db.commit()
                    return

                # Save structured document via DocumentStorage
                from app.services.ocr.checksum import calculate_structured_document_checksum
                content_dump = structured_doc.model_dump()
                doc_checksum = calculate_structured_document_checksum(content_dump)
                content_dump["checksum"] = doc_checksum

                canonical_bytes = json.dumps(content_dump, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8')

                doc_path = storage.put(
                    tenant_id=tenant_id,
                    document_id=f"structured_{run.run_id}.json",
                    file_stream=io.BytesIO(canonical_bytes)
                )

                score = structured_doc.confidence
                ocr_status = "APPROVED" if score >= settings.OCR_REVIEW_THRESHOLD else "REVIEW_REQUIRED"

                # Reconstruct full text for downstream V6 extractors that require text_extracted
                full_text_lines = []
                if structured_doc.pages:
                    for page in structured_doc.pages:
                        if hasattr(page, "elements") and page.elements:
                            for el in page.elements:
                                if hasattr(el, "text"):
                                    full_text_lines.append(el.text)

                doc.text_extracted = "\n".join(full_text_lines) if full_text_lines else ""

                # Update product columns
                doc.ocr_engine_used = "v2"
                doc.ocr_score = score
                doc.ocr_status = ocr_status
                doc.ocr_processed_at = finish_now
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
                run.finished_at = finish_now
                run.score = score
                run.review_threshold = settings.OCR_REVIEW_THRESHOLD
                run.structured_document_path = doc_path
                run.structured_document_checksum = doc_checksum
                run.quality_status = ocr_status

                # Parse Sections
                parsed_sections = StructuredDocumentAdapter.to_parsed_sections(case_id, structured_doc, run.uploaded_document_id)
                if not parsed_sections:
                    from app.services.extraction.exceptions import NoSectionsExtractedError
                    raise NoSectionsExtractedError("No se detectaron secciones estructurales válidas en el documento (V2).")

                for sec in parsed_sections:
                    db.add(sec)

                locked_case.status = "REVIEW_SECTIONS"

                doc.processing_status = "finished"
                db.commit()

            # Si está vinculado a un ProcessingJob, marcar completado y emitir métricas
            if run.processing_job_id:
                JobRepository.mark_completed(
                    db=db,
                    job_id=run.processing_job_id,
                    result_summary={
                        "run_id": str(run.run_id),
                        "score": structured_doc.confidence,
                        "quality_status": run.quality_status
                    },
                    status_message="OCR V2 procesado exitosamente.",
                    tenant_id=tenant_id,
                    worker_name=worker_name,
                    pages_processed=len(getattr(structured_doc, 'pages', [])) or 1
                )
        finally:
            stop_event.set()
            hb_thread.join(timeout=2)
    except (Exception, JobTimeoutException) as e:
        db.rollback()
        error_msg = str(e)
        logger.error(f"Error in OCR V2 Pipeline for run {run_id}: {error_msg}")
        logger.error(traceback.format_exc())

        now_err = datetime.now(timezone.utc)
        run = db.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
        if run:
            is_timeout = isinstance(e, JobTimeoutException)
            run.status = 'FAILED'
            run.failure_code = 'TIMEOUT' if is_timeout else 'TASK_EXCEPTION'
            run.failure_detail = 'El proceso de OCR excedió el tiempo máximo permitido.' if is_timeout else error_msg
            run.finished_at = now_err
            run.quality_status = None

            if run.execution_role == 'PRIMARY':
                doc = db.query(UploadedDocument).filter(UploadedDocument.id == run.uploaded_document_id).first()
                if doc:
                    db_case = (
                        db.query(CaseFile)
                        .filter(CaseFile.id == doc.case_id)
                        .populate_existing()
                        .with_for_update()
                        .first()
                    )
                    from app.models.v6.case_workflow import CaseWorkflow
                    from app.models.v6.supplier_selection import SupplierSelectionFinal

                    is_terminal = False
                    if db_case:
                        is_terminal = (
                            db_case.status in ["APPROVED", "COMPLETED"]
                            or db.query(CaseWorkflow).filter(CaseWorkflow.case_id == db_case.id, CaseWorkflow.status.in_(["APPROVED", "COMPLETED"])).first() is not None
                            or db.query(SupplierSelectionFinal).filter(SupplierSelectionFinal.case_id == db_case.id).first() is not None
                        )

                    if not is_terminal:
                        doc.processing_status = "timeout" if is_timeout else "failed"
                        doc.processing_error = "Timeout OCR excedido" if is_timeout else error_msg
                        doc.ocr_status = "FAILED"

                        if db_case:
                            db_case.status = "TIMEOUT" if is_timeout else "ERROR"

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
                            run_dedup_key=hashlib.sha256(f"{run.run_id}_fallback_{now_err.isoformat()}".encode()).hexdigest()
                        )
                        try:
                            repo.create_run(fallback)
                            logger.info("FALLBACK run created immediately due to task exception")
                        except Exception as fallback_e:
                            logger.error(f"Failed to create fallback: {str(fallback_e)}")
                    else:
                        logger.info(
                            f"[OCR V2 Exception] Expediente {doc.case_id} cerrado ({db_case.status if db_case else 'N/A'}); no se alteran documentos ni caso, ni se crea fallback."
                        )
                        from app.models.domain import AuditLog
                        audit = AuditLog(
                            tenant_id=db_case.tenant_id if db_case else (tenant_id or "unknown"),
                            user_id=(db_case.assigned_to_user_id or db_case.created_by) if db_case else None,
                            action="OCR_V2_TIMEOUT_BLOCKED_TERMINAL" if is_timeout else "OCR_V2_ERROR_BLOCKED_TERMINAL",
                            entity_type="CaseFile",
                            entity_id=str(doc.case_id),
                            details=f"Mutación de error/timeout OCR V2 descartada: expediente cerrado ({db_case.status if db_case else 'N/A'})",
                            status="FAILED"
                        )
                        db.add(audit)

            # Clasificación taxonómica y marcado de fallo en ProcessingJob
            if run.processing_job_id:
                err_code, err_cat, fail_class = JobRepository.classify_error(e)
                case = db.query(CaseFile).filter(CaseFile.id == run.validation_case_id).first() if run.validation_case_id else None
                t_id = case.tenant_id if case else None
                JobRepository.mark_failed(
                    db=db,
                    job_id=run.processing_job_id,
                    error_message=error_msg,
                    tenant_id=t_id,
                    worker_name=worker_name,
                    error_code=err_code,
                    error_category=err_cat,
                    failure_classification=fail_class
                )

            db.commit()
        raise
    finally:
        db.close()
