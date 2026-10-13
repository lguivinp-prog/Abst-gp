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
from rq.timeouts import JobTimeoutException

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
                stop_event.wait(interval)

        hb_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        hb_thread.start()

        try:
            # Execute legacy pipeline
            job_id = job.id if job else run.rq_job_id
            fallback_used = (run.execution_role == 'FALLBACK')
            persisted = execute_v1_pipeline(doc.case_id, doc.stored_path, job_id, fallback_used)
        finally:
            stop_event.set()
            hb_thread.join(timeout=2)

        run = db.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
        if not persisted:
            run.status = 'FAILED'
            run.failure_code = 'CASE_TERMINAL_IMMUTABLE'
            run.failure_detail = 'Extracción OCR V1 tardía descartada: expediente cerrado'
            run.finished_at = datetime.utcnow()
            run.quality_status = None
            db.commit()
            return

        # Mark Completed
        run.status = 'COMPLETED'
        run.finished_at = datetime.utcnow()
        run.quality_status = 'APPROVED'
        db.commit()

        # If this is PRIMARY v1 in a validation case, we must create SHADOW v2
        if run.execution_role == 'PRIMARY' and run.engine == 'v1' and run.validation_case_id:
            try:
                # Calculate baseline snapshot
                from app.services.ocr.checksum import calculate_baseline_hash
                from app.models.v6.generated_output import GeneratedOutput

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
    except JobTimeoutException as e:
        db.rollback()
        run = db.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
        if run:
            run.status = 'FAILED'
            run.failure_code = 'TIMEOUT'
            run.failure_detail = 'El proceso de OCR excedió el tiempo máximo permitido.'
            run.finished_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()

logger = logging.getLogger(__name__)


def execute_v1_pipeline(case_id: int, file_path: str, job_id: str, fallback_used: bool = False):
    """
    Original V1 pipeline. Kept unmodified for compatibility and fallback.
    """
    job = get_current_job()
    db = SessionLocal()
    try:
        # 0. Verificación atómica bajo bloqueo de fila antes de modificar el documento
        locked_case = (
            db.query(CaseFile)
            .filter(CaseFile.id == case_id)
            .populate_existing()
            .with_for_update()
            .first()
        )
        from app.models.v6.case_workflow import CaseWorkflow
        from app.models.v6.supplier_selection import SupplierSelectionFinal

        is_initial_terminal = False
        if locked_case:
            is_initial_terminal = (
                locked_case.status in ["APPROVED", "COMPLETED"]
                or db.query(CaseWorkflow).filter(CaseWorkflow.case_id == case_id, CaseWorkflow.status.in_(["APPROVED", "COMPLETED"])).first() is not None
                or db.query(SupplierSelectionFinal).filter(SupplierSelectionFinal.case_id == case_id).first() is not None
            )

        if is_initial_terminal:
            logger.warning(f"[OCR V1] Caso {case_id} ya se encuentra en estado terminal ({locked_case.status if locked_case else 'N/A'}). Omitiendo ejecución V1.")
            if job:
                job.meta['progress'] = 100
                job.meta['status_message'] = f"OCR descartado: expediente cerrado ({locked_case.status if locked_case else 'N/A'})"
                job.meta['error'] = f"Case in terminal status {locked_case.status if locked_case else 'N/A'}"
                job.save_meta()

            from app.models.domain import AuditLog
            audit = AuditLog(
                tenant_id=locked_case.tenant_id if locked_case else "unknown",
                user_id=(locked_case.assigned_to_user_id or locked_case.created_by) if locked_case else 1,
                action="OCR_V1_PROCESSING_BLOCKED_TERMINAL",
                entity_type="CaseFile",
                entity_id=str(case_id),
                details=f"Extracción OCR V1 tardía descartada: expediente cerrado ({locked_case.status if locked_case else 'N/A'})",
                status="FAILED"
            )
            db.add(audit)
            db.commit()
            return False

        # 1. Update Document status to 'started' bajo la misma transacción atómica
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

        # Volver a comprobar el estado terminal inmediatamente antes de guardar
        is_terminal_recheck = False
        if locked_case:
            is_terminal_recheck = (
                locked_case.status in ["APPROVED", "COMPLETED"]
                or db.query(CaseWorkflow).filter(CaseWorkflow.case_id == case_id, CaseWorkflow.status.in_(["APPROVED", "COMPLETED"])).first() is not None
                or db.query(SupplierSelectionFinal).filter(SupplierSelectionFinal.case_id == case_id).first() is not None
            )

        if is_terminal_recheck:
            db.rollback()
            logger.warning(f"[OCR V1] Recomprobación antes de guardar detectó estado terminal en caso {case_id}. Omitiendo guardado temprano.")
            return False

        # Liberar el bloqueo transaccional ANTES de iniciar el procesamiento pesado de OCR
        db.commit()

        # 2. Run OCR
        from app.storage.workspace import materialize_document
        with materialize_document(file_path) as local_temp_path:
            ocr_result = process_pdf(local_temp_path)

        if job:
            job.meta['progress'] = 50
            job.meta['status_message'] = "Limpiando texto extraído..."
            job.save_meta()

        # 3. Clean OCR text and Extract Sections via DocumentExtractionAgent
        from app.services.extraction.document_extraction_agent import DocumentExtractionAgent
        from app.services.extraction.exceptions import NoSectionsExtractedError

        agent = DocumentExtractionAgent()
        db_case = db.query(CaseFile).filter(CaseFile.id == case_id).first()

        extracted_sections = agent.process(ocr_result.pages_text, db_case.contract_type, ocr_result.structured_document)
        if not extracted_sections:
            raise NoSectionsExtractedError("No se detectaron secciones estructurales válidas en el documento (V1).")

        # 4. Control de concurrencia y persistencia atómica con bloqueo de fila
        locked_case = (
            db.query(CaseFile)
            .filter(CaseFile.id == case_id)
            .populate_existing()
            .with_for_update()
            .first()
        )

        if not locked_case:
            raise ValueError(f"Expediente {case_id} no encontrado.")

        from app.models.v6.case_workflow import CaseWorkflow
        from app.models.v6.supplier_selection import SupplierSelectionFinal

        is_terminal = (
            locked_case.status in ["APPROVED", "COMPLETED"]
            or db.query(CaseWorkflow).filter(CaseWorkflow.case_id == case_id, CaseWorkflow.status.in_(["APPROVED", "COMPLETED"])).first() is not None
            or db.query(SupplierSelectionFinal).filter(SupplierSelectionFinal.case_id == case_id).first() is not None
        )

        if is_terminal:
            # Expediente cerrado: NO modificar secciones, documento ni status de caso
            logger.warning(f"[OCR V1] Descartando persistencia: expediente {case_id} en estado terminal {locked_case.status}")
            if job:
                job.meta['progress'] = 100
                job.meta['status_message'] = f"OCR descartado: expediente cerrado ({locked_case.status})"
                job.meta['error'] = f"Case in terminal status {locked_case.status}"
                job.save_meta()

            from app.models.domain import AuditLog
            audit = AuditLog(
                tenant_id=locked_case.tenant_id,
                user_id=locked_case.assigned_to_user_id or locked_case.created_by,
                action="OCR_V1_PROCESSING_BLOCKED_TERMINAL",
                entity_type="CaseFile",
                entity_id=str(case_id),
                details=f"Extracción OCR V1 tardía descartada: expediente cerrado ({locked_case.status})",
                status="FAILED"
            )
            db.add(audit)
            db.commit()
            return False

        # 5. Guardar metadatos en documento y limpiar secciones previas
        if doc:
            doc.text_extracted = ocr_result.text
            doc.ocr_used = ocr_result.ocr_used
            doc.ocr_metadata = {
                "page_count": ocr_result.page_count,
                "confidence_avg": ocr_result.confidence_avg,
                "ocr_pipeline_version": "1.0",
                "fallback_used": fallback_used
            }

        if job:
            job.meta['progress'] = 70
            job.meta['status_message'] = "Detectando y limpiando secciones..."
            job.save_meta()

        # Clean up existing sections for THIS DOCUMENT to prevent accumulation on re-processing
        if doc:
            db.query(ParsedSection).filter(ParsedSection.document_id == doc.id).delete()
            db.flush()

        has_warnings = False
        for sec_data in extracted_sections:
            sec_has_warnings = any(w.get("code") in ("MANUAL_REQUIRED", "LOW_CONFIDENCE_TABLE", "LOW_CONFIDENCE_TITLE") for w in sec_data.warnings_json)
            if sec_has_warnings:
                has_warnings = True

            # Ensure schema_version is explicitly preserved in the persistence layer
            meta = sec_data.metadata or {}
            meta["schema_version"] = 1

            sec = ParsedSection(
                case_id=case_id,
                document_id=doc.id,
                original_roman=meta.get("original_roman"),
                original_order=meta.get("original_order"),
                title=meta.get("title"),
                original_text=sec_data.original_text,
                cleaned_text=sec_data.cleaned_text,
                normalized_text=sec_data.normalized_text,
                current_text=sec_data.cleaned_text,
                structure_json=sec_data.structure_json,
                corrections_json=sec_data.corrections_json,
                warnings_json=sec_data.warnings_json,
                extraction_metadata=meta,
                confidence_score=meta.get("confidence", 0.0),
                review_status="pending_review" if sec_has_warnings else "validated"
            )
            db.add(sec)
            db.flush() # Need the section ID to link tables

            # Map tables from Pydantic objects to DB models
            from app.models.v6.structured_tables import StructuredTable, StructuredRow, StructuredCell
            for block_index, b in enumerate(getattr(sec_data, 'structured_blocks', [])):
                if b.type == "TABLE" and b.table_data:
                    # Parse bounding box if present
                    bbox_str = None
                    if b.bbox:
                        bbox_str = f"{b.bbox.x0},{b.bbox.y0},{b.bbox.x1},{b.bbox.y1}"

                    st = StructuredTable(
                        section_id=sec.id,
                        page_num=b.page_num,
                        order_index=block_index,
                        row_count=b.table_data.row_count,
                        col_count=b.table_data.col_count,
                        bbox=bbox_str
                    )
                    db.add(st)
                    db.flush()

                    for r_idx, row in enumerate(b.table_data.rows):
                        sr = StructuredRow(
                            table_id=st.id,
                            row_index=r_idx,
                            is_header=(r_idx == 0) # Basic heuristic: first row is header
                        )
                        db.add(sr)
                        db.flush()

                        for c_idx, cell in enumerate(row.cells):
                            sc = StructuredCell(
                                row_id=sr.id,
                                col_index=c_idx,
                                content=cell.text,
                                original_content=cell.text,
                                col_span=getattr(cell, 'col_span', 1),
                                row_span=getattr(cell, 'row_span', 1)
                            )
                            db.add(sc)

        # 6. Update Case Status and Doc Status
        locked_case.status = "REVIEW_SECTIONS"
        if doc:
            doc.processing_status = "review_required" if has_warnings else "finished"

        if job:
            job.meta['progress'] = 100
            job.meta['status_message'] = "Procesado - Pendiente Revisión" if has_warnings else "Completado"
            job.save_meta()

        db.commit()
        return True

    except JobTimeoutException as e:
        db.rollback()
        error_msg = "El proceso de OCR excedió el tiempo máximo permitido."

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

        if not is_terminal:
            doc = db.query(UploadedDocument).filter(UploadedDocument.processing_job_id == job_id).first()
            if not doc:
                doc = db.query(UploadedDocument).filter(
                    UploadedDocument.case_id == case_id,
                    UploadedDocument.document_type == "requirement"
                ).order_by(UploadedDocument.id.desc()).first()

            if doc:
                doc.processing_status = "timeout"
                doc.processing_error = error_msg
                doc.ocr_status = "FAILED"

            if locked_case:
                locked_case.status = "TIMEOUT"
        else:
            logger.warning(
                f"[OCR V1 Timeout] Expediente {case_id} cerrado ({locked_case.status if locked_case else 'N/A'}); no se alteran documentos ni estado de negocio."
            )
            from app.models.domain import AuditLog
            audit = AuditLog(
                tenant_id=locked_case.tenant_id if locked_case else "unknown",
                user_id=(locked_case.assigned_to_user_id or locked_case.created_by) if locked_case else 1,
                action="OCR_V1_TIMEOUT_BLOCKED_TERMINAL",
                entity_type="CaseFile",
                entity_id=str(case_id),
                details=f"Timeout OCR V1 tardío descartado: expediente cerrado ({locked_case.status if locked_case else 'N/A'})",
                status="FAILED"
            )
            db.add(audit)

        if job:
            job.meta['progress'] = 100
            job.meta['status_message'] = f"Error: {error_msg}"
            job.save_meta()

        db.commit()
        raise
    except Exception as e:
        db.rollback()
        error_msg = str(e)

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

        if not is_terminal:
            doc = db.query(UploadedDocument).filter(UploadedDocument.processing_job_id == job_id).first()
            if not doc:
                doc = db.query(UploadedDocument).filter(
                    UploadedDocument.case_id == case_id,
                    UploadedDocument.document_type == "requirement"
                ).order_by(UploadedDocument.id.desc()).first()

            if doc:
                doc.processing_status = "failed"
                doc.processing_error = error_msg
                doc.ocr_status = "FAILED"

            if locked_case:
                locked_case.status = "ERROR"
        else:
            logger.warning(
                f"[OCR V1 Exception] Expediente {case_id} cerrado ({locked_case.status if locked_case else 'N/A'}); no se alteran documentos ni estado de negocio."
            )
            from app.models.domain import AuditLog
            audit = AuditLog(
                tenant_id=locked_case.tenant_id if locked_case else "unknown",
                user_id=(locked_case.assigned_to_user_id or locked_case.created_by) if locked_case else 1,
                action="OCR_V1_ERROR_BLOCKED_TERMINAL",
                entity_type="CaseFile",
                entity_id=str(case_id),
                details=f"Fallo OCR V1 tardío descartado: expediente cerrado ({locked_case.status if locked_case else 'N/A'})",
                status="FAILED"
            )
            db.add(audit)

        if job:
            job.meta['progress'] = 100
            job.meta['status_message'] = f"Error: {error_msg}"
            job.save_meta()

        db.commit()
        raise
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

def ocr_shadow_task(case_id: int, file_path: str):
    """
    Dummy shadow task for V1 to prevent ImportError in ExtractionOrchestrator.
    """
    pass

def cleanup_abandoned_uploads_task():
    """
    Cleans up abandoned uploads (UPLOADING state > 24 hours).
    Marks them as EXPIRED and attempts to delete the physical object via DocumentStorage.
    """
    from app.storage.factory import get_storage
    from datetime import timedelta

    db = SessionLocal()
    storage = get_storage()
    try:
        threshold = datetime.utcnow() - timedelta(hours=24)
        abandoned_docs = db.query(UploadedDocument).filter(
            UploadedDocument.processing_status == "UPLOADING",
            UploadedDocument.created_at < threshold
        ).all()

        for doc in abandoned_docs:
            doc.processing_status = "EXPIRED"
            try:
                storage.delete(doc.stored_path)
            except Exception as e:
                logging.warning(f"Failed to delete abandoned object {doc.stored_path}: {str(e)}")

        db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Error in cleanup_abandoned_uploads_task: {str(e)}")
    finally:
        db.close()
