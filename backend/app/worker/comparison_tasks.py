import os
import socket
import logging
from typing import Dict, Any, Optional
from rq import get_current_job

from app.core.database import SessionLocal
from app.models.domain import (
    CaseFile,
    QuotationExtraction,
    ParsedSection,
    FinalConditionComparison,
    AuditLog
)
from app.services.job_repository import JobRepository
from app.services.extraction.requirement_condition_extractor import extract_requirement_conditions
from sqlalchemy.orm import Session
from app.services.comparison.comparison_engine import run_comparison

logger = logging.getLogger(__name__)


def process_comparison_task(
    job_id: str,
    case_id: int,
    tenant_id: str,
    user_id: int,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Worker asíncrono para ejecución del motor de comparación en V5.4.
    Garantiza:
    - Bloqueo exclusivo a nivel de fila (SELECT FOR UPDATE) sobre CaseFile.
    - Idempotencia estricta ante reintentos.
    - Registro y monitoreo de WorkerHeartbeat.
    - Generación de telemetría y latencias en ProcessingMetrics.
    - Registro inmutable de AuditLog (SUCCESS / FAILED).
    """
    rq_job = get_current_job()
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    worker_name = f"comparison_worker_{os.getpid()}@{socket.gethostname()}"
    items_count = 0

    try:
        # 1. Registrar latido inicial y transición de estado a PROCESSING
        JobRepository.record_heartbeat(
            db=db,
            worker_name=worker_name,
            worker_type="COMPARISON_WORKER",
            status="BUSY",
            current_job_id=job_id,
            tenant_id=tenant_id
        )

        JobRepository.update_progress(
            db=db,
            job_id=job_id,
            progress=10,
            status_message="Adquiriendo bloqueo de caso y verificando idempotencia...",
            status="PROCESSING",
            tenant_id=tenant_id,
            worker_name=worker_name
        )
        if rq_job:
            rq_job.meta["progress"] = 10
            rq_job.meta["worker_name"] = worker_name
            rq_job.save_meta()

        # 2. Bloqueo exclusivo a nivel de fila con populate_existing
        locked_case = (
            db.query(CaseFile)
            .filter(CaseFile.id == case_id, CaseFile.tenant_id == tenant_id)
            .populate_existing()
            .with_for_update()
            .first()
        )

        if not locked_case:
            raise ValueError(f"Expediente {case_id} no encontrado para tenant {tenant_id}")

        # 3. Conteo de comparaciones existentes para validación de idempotencia
        existing_comparisons_count = (
            db.query(FinalConditionComparison)
            .filter(FinalConditionComparison.case_id == case_id)
            .count()
        )

        # Idempotencia: Si ya está en READY_GENERATE y existen comparaciones, retornar éxito inmediatamente
        if locked_case.status == "READY_GENERATE":
            if existing_comparisons_count > 0:
                summary = {
                    "already_completed": True,
                    "items_compared": existing_comparisons_count,
                    "case_status": "READY_GENERATE"
                }
                JobRepository.mark_completed(
                    db=db,
                    job_id=job_id,
                    result_summary=summary,
                    status_message="Comparación completada previamente (Idempotente).",
                    tenant_id=tenant_id,
                    worker_name=worker_name,
                    pages_processed=existing_comparisons_count
                )
                if rq_job:
                    rq_job.meta["progress"] = 100
                    rq_job.meta["status_message"] = "Comparación idempotente"
                    rq_job.save_meta()
                return summary
            else:
                raise ValueError("Estado inconsistente: el caso está en READY_GENERATE pero no contiene resultados.")

        # Validar que el caso esté en estado COMPARING
        if locked_case.status != "COMPARING":
            raise ValueError(f"El expediente no está listo para comparación. Estado actual: {locked_case.status}")

        if existing_comparisons_count > 0:
            raise ValueError("Estado inconsistente: el expediente está en COMPARING pero ya contiene comparaciones.")

        # 4. Cargar cotización y secciones seleccionadas
        JobRepository.update_progress(
            db=db,
            job_id=job_id,
            progress=30,
            status_message="Cargando términos de requerimiento y cotización validada...",
            status="PROCESSING",
            tenant_id=tenant_id,
            worker_name=worker_name
        )
        if rq_job:
            rq_job.meta["progress"] = 30
            rq_job.save_meta()

        quotation = (
            db.query(QuotationExtraction)
            .filter(QuotationExtraction.case_id == case_id)
            .order_by(QuotationExtraction.id.desc())
            .first()
        )

        if not quotation:
            raise ValueError(f"No se encontró cotización extraída para el caso {case_id}")

        sections = (
            db.query(ParsedSection)
            .filter(
                ParsedSection.case_id == case_id,
                ParsedSection.is_selected == True
            )
            .all()
        )

        requirement_data = extract_requirement_conditions(sections)
        quotation_data = quotation.raw_json or {}

        # 5. Ejecutar motor algorítmico de comparación
        JobRepository.update_progress(
            db=db,
            job_id=job_id,
            progress=60,
            status_message="Ejecutando motor de comparación algorítmico...",
            status="PROCESSING",
            tenant_id=tenant_id,
            worker_name=worker_name
        )
        if rq_job:
            rq_job.meta["progress"] = 60
            rq_job.save_meta()

        results = run_comparison(
            requirement_data,
            quotation_data
        )
        items_count = len(results)

        for result in results:
            db.add(
                FinalConditionComparison(
                    case_id=case_id,
                    **result
                )
            )

        db.flush()

        # 6. Actualizar estado del caso a READY_GENERATE
        locked_case.status = "READY_GENERATE"

        # 7. Registrar AuditLog SUCCESS
        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="COMPARISON_RUN_ASYNC",
            entity_type="FinalConditionComparison",
            entity_id=str(case_id),
            details=f"Comparación asíncrona ejecutada exitosamente ({items_count} condiciones analizadas)",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()

        # 8. Marcar ProcessingJob completado en PostgreSQL y generar ProcessingMetrics
        result_summary = {
            "items_compared": items_count,
            "case_status": "READY_GENERATE",
            "already_completed": False
        }

        JobRepository.mark_completed(
            db=db,
            job_id=job_id,
            result_summary=result_summary,
            status_message="Comparación finalizada y persistida con éxito.",
            tenant_id=tenant_id,
            worker_name=worker_name,
            pages_processed=items_count
        )

        if rq_job:
            rq_job.meta["progress"] = 100
            rq_job.meta["status_message"] = "Comparación completada exitosamente"
            rq_job.save_meta()

        return result_summary

    except Exception as e:
        db.rollback()
        logger.error(
            f"[ComparisonWorker] Error en comparación job_id={job_id}, case_id={case_id}: {str(e)}",
            exc_info=True
        )

        # Registrar auditoría de fallo
        try:
            audit_fail = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                action="COMPARISON_RUN_ASYNC",
                entity_type="CaseFile",
                entity_id=str(case_id),
                details=f"Fallo en comparación asíncrona: {str(e)}",
                status="FAILED"
            )
            db.add(audit_fail)
            db.commit()
        except Exception as audit_err:
            logger.error(f"Error al registrar AuditLog de fallo en comparación: {audit_err}")
            db.rollback()

        # Clasificación taxonómica de error V5.4
        error_code, error_category, failure_classif = JobRepository.classify_error(e)

        # Marcar ProcessingJob como FAILED y generar ProcessingMetrics de fallo
        JobRepository.mark_failed(
            db=db,
            job_id=job_id,
            error_message=str(e),
            tenant_id=tenant_id,
            worker_name=worker_name,
            error_code=error_code,
            error_category=error_category,
            failure_classification=failure_classif,
            pages_processed=items_count
        )

        if rq_job:
            rq_job.meta["progress"] = 100
            rq_job.meta["error"] = str(e)
            rq_job.save_meta()

        raise e
    finally:
        if own_session:
            db.close()

