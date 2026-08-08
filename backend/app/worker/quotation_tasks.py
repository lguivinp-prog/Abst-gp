import os
import json
import socket
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from rq import get_current_job

from app.core.database import SessionLocal
from app.models.domain import CaseFile, QuotationExtraction, AuditLog
from app.services.job_repository import JobRepository
from app.services.extraction.quotation_parser import parse_quotation_pdf

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def process_quotation_task(
    job_id: str,
    case_id: int,
    tenant_id: str,
    user_id: int,
    file_path: str,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Worker asíncrono para extracción y procesamiento de Cotizaciones PDF en V5.4.
    Garantiza persistencia en PostgreSQL como SSOT vía JobRepository,
    supervisión por WorkerHeartbeat, telemetría ProcessingMetrics y auditoría inmutable.
    """
    rq_job = get_current_job()
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    worker_name = f"quotation_worker_{os.getpid()}@{socket.gethostname()}"
    pages_processed = 0

    try:
        # 1. Registrar latido inicial y transición de estado a PROCESSING
        JobRepository.record_heartbeat(
            db=db,
            worker_name=worker_name,
            worker_type="QUOTATION_WORKER",
            status="BUSY",
            current_job_id=job_id,
            tenant_id=tenant_id
        )

        JobRepository.update_progress(
            db=db,
            job_id=job_id,
            progress=10,
            status_message="Iniciando procesamiento asíncrono de cotización PDF...",
            status="PROCESSING",
            tenant_id=tenant_id,
            worker_name=worker_name
        )
        if rq_job:
            rq_job.meta["progress"] = 10
            rq_job.meta["worker_name"] = worker_name
            rq_job.save_meta()

        # 2. Validación de ruta de archivo y aislamiento seguro
        resolved_path = Path(file_path).resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(f"Archivo físico de cotización no encontrado: {file_path}")

        # 3. Actualizar progreso hacia extracción
        JobRepository.update_progress(
            db=db,
            job_id=job_id,
            progress=30,
            status_message="Extrayendo texto y metadatos de cotización PDF...",
            status="PROCESSING",
            tenant_id=tenant_id,
            worker_name=worker_name
        )
        if rq_job:
            rq_job.meta["progress"] = 30
            rq_job.save_meta()

        # 4. Ejecutar parse_quotation_pdf
        quotation_data = parse_quotation_pdf(str(resolved_path))
        if "error" in quotation_data and not quotation_data.get("supplier"):
            raise ValueError(f"Fallo en motor de extracción de PDF: {quotation_data['error']}")

        pages_processed = quotation_data.get("pages_processed") or quotation_data.get("page_count") or 1

        # 5. Persistir QuotationExtraction y actualizar CaseFile
        JobRepository.update_progress(
            db=db,
            job_id=job_id,
            progress=70,
            status_message="Estructurando datos y persistiendo entidad de cotización...",
            status="PROCESSING",
            tenant_id=tenant_id,
            worker_name=worker_name
        )
        if rq_job:
            rq_job.meta["progress"] = 70
            rq_job.save_meta()

        confidence = quotation_data.get("global_confidence", 0.0)
        review_status = "validated" if confidence > 0.8 else "pending_review"

        quotation = QuotationExtraction(
            case_id=case_id,
            raw_json=quotation_data,
            review_status=review_status
        )
        db.add(quotation)

        # Actualizar caso a COMPARING
        case = db.query(CaseFile).filter(CaseFile.id == case_id, CaseFile.tenant_id == tenant_id).first()
        if case:
            case.status = "COMPARING"

        db.flush()

        # 6. Registrar AuditLog SUCCESS
        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="QUOTATION_EXTRACTED_ASYNC",
            entity_type="QuotationExtraction",
            entity_id=str(quotation.id),
            details=f"Extracción asíncrona de cotización completada ({os.path.basename(file_path)})",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()

        # 7. Marcar ProcessingJob completado y generar ProcessingMetrics
        result_summary = {
            "extraction_id": quotation.id,
            "review_status": review_status,
            "global_confidence": confidence,
            "supplier_ruc": quotation_data.get("supplier", {}).get("supplier_ruc", {}).get("value")
        }

        completed_job = JobRepository.mark_completed(
            db=db,
            job_id=job_id,
            result_summary=result_summary,
            status_message="Cotización procesada y extraída exitosamente.",
            tenant_id=tenant_id,
            worker_name=worker_name,
            pages_processed=pages_processed
        )

        if rq_job:
            rq_job.meta["progress"] = 100
            rq_job.meta["status_message"] = "Cotización procesada exitosamente"
            rq_job.save_meta()

        return result_summary

    except Exception as e:
        db.rollback()
        logger.error(
            f"[QuotationWorker] Error procesando cotización job_id={job_id}, case_id={case_id}: {str(e)}",
            exc_info=True
        )

        # Registrar auditoría de fallo
        try:
            audit_fail = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                action="QUOTATION_EXTRACTED_ASYNC",
                entity_type="CaseFile",
                entity_id=str(case_id),
                details=f"Fallo en procesamiento asíncrono de cotización: {str(e)}",
                status="FAILED"
            )
            db.add(audit_fail)
            db.commit()
        except Exception as audit_err:
            logger.error(f"Error al registrar AuditLog de fallo: {audit_err}")
            db.rollback()

        # Clasificación taxonómica de error V5.4
        error_code, error_category, failure_classif = JobRepository.classify_error(e)

        # Marcar ProcessingJob como FAILED vía JobRepository y generar ProcessingMetrics de fallo
        JobRepository.mark_failed(
            db=db,
            job_id=job_id,
            error_message=str(e),
            tenant_id=tenant_id,
            worker_name=worker_name,
            error_code=error_code,
            error_category=error_category,
            failure_classification=failure_classif,
            pages_processed=pages_processed
        )

        if rq_job:
            rq_job.meta["progress"] = 100
            rq_job.meta["error"] = str(e)
            rq_job.save_meta()

        raise e
    finally:
        if own_session:
            db.close()

