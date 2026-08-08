import time
import json
import uuid
import socket
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple, Union, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, text
from app.models.domain import ProcessingJob, ProcessingMetrics, WorkerHeartbeat, AuditLog
from app.core.telemetry import (
    record_job_lifecycle,
    record_worker_telemetry,
    record_capacity_claim,
    record_job_retained,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_job_filter(job_id_or_pk: Union[str, int]):
    """
    Construye un filtro seguro para ProcessingJob que maneja indistintamente:
    - job_id como UUID o string alfanumérico (ej. 'req_ocr_123_abc')
    - job_id numérico como string (ej. '1')
    - id primario como integer (ej. 1)
    Evita errores de coerción PostgreSQL (character varying = integer).
    """
    if isinstance(job_id_or_pk, int):
        return or_(ProcessingJob.id == job_id_or_pk, ProcessingJob.job_id == str(job_id_or_pk))
    elif isinstance(job_id_or_pk, str):
        if job_id_or_pk.isdigit():
            return or_(ProcessingJob.job_id == job_id_or_pk, ProcessingJob.id == int(job_id_or_pk))
        return ProcessingJob.job_id == job_id_or_pk
    else:
        return ProcessingJob.job_id == str(job_id_or_pk)


class JobRepository:
    """
    Repositorio de persistencia en PostgreSQL para ProcessingJob, ProcessingMetrics y WorkerHeartbeat.
    Garantiza que PostgreSQL sea la única fuente histórica (SSOT) de jobs,
    con soporte multi-tenant, telemetría de latencias y resiliencia operacional V5.4.
    """

    @staticmethod
    def classify_error(exc_or_reason: Union[Exception, str]) -> Tuple[str, str, str]:
        """
        Clasifica una excepción o mensaje de error en (error_code, error_category, failure_classification).
        Categorías:
          - CORRUPT_INPUT: Archivo inexistente, formato inválido, PDF corrupto, esquema inválido.
          - BUSINESS_RULE: Validaciones de estado, reglas de negocio, secciones no aprobadas.
          - TRANSIENT_INFRA: Timeouts de red/infraestructura, fallos de conexión a DB/Redis, worker heartbeat perdido.
          - UNEXPECTED_ERROR: Excepciones no tipificadas.
        Clasificaciones:
          - FINAL: No reintentable automáticamente.
          - RETRYABLE: Candidato a reintento automático o manual con backoff.
        """
        if isinstance(exc_or_reason, Exception):
            exc_str = str(exc_or_reason).lower()
            exc_type = type(exc_or_reason).__name__
        else:
            exc_str = str(exc_or_reason).lower()
            exc_type = "str"

        # FINAL: CORRUPT_INPUT
        if isinstance(exc_or_reason, FileNotFoundError) or "no encontrado" in exc_str or "not found" in exc_str or "file_not_found" in exc_str:
            return "FILE_NOT_FOUND", "CORRUPT_INPUT", "FINAL"
        if "pdf" in exc_str and ("corrupt" in exc_str or "inválid" in exc_str or "damaged" in exc_str or "error al abrir" in exc_str or "invalid" in exc_str):
            return "CORRUPT_PDF", "CORRUPT_INPUT", "FINAL"
        if "esquema inválido" in exc_str or "invalid_schema" in exc_str or "validationerror" in exc_type.lower() or "schema" in exc_str:
            return "INVALID_SCHEMA", "CORRUPT_INPUT", "FINAL"

        # FINAL: BUSINESS_RULE
        if isinstance(exc_or_reason, ValueError) or "estado inconsistente" in exc_str or "no está listo" in exc_str or "business_rule" in exc_str or "validación negocio" in exc_str or "unapproved" in exc_str:
            return "BUSINESS_RULE_VIOLATION", "BUSINESS_RULE", "FINAL"

        # RETRYABLE: TRANSIENT_INFRA
        if isinstance(exc_or_reason, TimeoutError) or "timeout" in exc_str or "timed out" in exc_str or "infrastructure_timeout" in exc_str:
            if "heartbeat" in exc_str or "worker" in exc_str:
                return "WORKER_HEARTBEAT_TIMEOUT", "TRANSIENT_INFRA", "RETRYABLE"
            if "queue" in exc_str or "cola" in exc_str:
                return "QUEUE_TIMEOUT", "TRANSIENT_INFRA", "RETRYABLE"
            return "INFRASTRUCTURE_TIMEOUT", "TRANSIENT_INFRA", "RETRYABLE"
        if "heartbeat" in exc_str or "stale" in exc_str or "worker muerto" in exc_str or "unresponsive" in exc_str or "worker_heartbeat_timeout" in exc_str:
            return "WORKER_HEARTBEAT_TIMEOUT", "TRANSIENT_INFRA", "RETRYABLE"
        if "queue_timeout" in exc_str or "tiempo máximo en cola" in exc_str or "cola excedid" in exc_str or "stuck in queue" in exc_str:
            return "QUEUE_TIMEOUT", "TRANSIENT_INFRA", "RETRYABLE"
        if "redis" in exc_str or "broker" in exc_str:
            return "REDIS_CONNECTION_ERROR", "TRANSIENT_INFRA", "RETRYABLE"
        if "connection" in exc_str or "operationalerror" in exc_type.lower() or "conexión bd" in exc_str or "database" in exc_str:
            return "DB_CONNECTION_ERROR", "TRANSIENT_INFRA", "RETRYABLE"

        return "INTERNAL_PROCESSING_ERROR", "UNEXPECTED_ERROR", "RETRYABLE"

    @staticmethod
    def _record_metric(
        db: Session,
        job: ProcessingJob,
        effective_worker: str,
        success: bool,
        error_code: Optional[str] = None,
        error_category: Optional[str] = None,
        pages_processed: int = 0,
        now: Optional[datetime] = None
    ) -> ProcessingMetrics:
        ts = now or _utc_now()
        created_at = job.created_at or ts
        started_at = job.started_at or created_at
        queue_time_ms = int(max(0, (started_at - created_at).total_seconds() * 1000))
        processing_time_ms = int(max(0, (ts - started_at).total_seconds() * 1000))
        total_time_ms = int(max(0, (ts - created_at).total_seconds() * 1000))

        metric = ProcessingMetrics(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            case_id=job.case_id,
            job_type=job.job_type,
            queue_time_ms=queue_time_ms,
            processing_time_ms=processing_time_ms,
            total_time_ms=total_time_ms,
            worker_name=effective_worker,
            pages_processed=pages_processed,
            success=success,
            error_code=error_code,
            error_category=error_category,
            created_at=ts
        )
        db.add(metric)

        # Emisión de métricas Prometheus (Fase 7.1)
        try:
            duration_sec = total_time_ms / 1000.0 if total_time_ms is not None else None
            record_job_lifecycle(
                job_type=job.job_type,
                status=job.status,
                duration_seconds=duration_sec
            )
        except Exception as te:
            logger.debug(f"Error emitiendo telemetría Prometheus para job {job.job_id}: {te}")

        return metric

    @staticmethod
    def record_heartbeat(
        db: Session,
        worker_name: str,
        worker_type: str,
        status: str = "BUSY",  # STARTED, IDLE, BUSY, OFFLINE
        hostname: Optional[str] = None,
        current_job_id: Optional[Union[str, int]] = None,
        tenant_id: Optional[str] = None
    ) -> WorkerHeartbeat:
        """
        Registra o actualiza el latido de un worker en la tabla worker_heartbeats.
        Si se especifica current_job_id, actualiza también last_heartbeat_at en ProcessingJob.
        """
        now = _utc_now()
        host = hostname or socket.gethostname()
        str_job_id = str(current_job_id) if current_job_id is not None else None

        heartbeat = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_name == worker_name).first()
        if not heartbeat:
            heartbeat = WorkerHeartbeat(
                worker_name=worker_name,
                worker_type=worker_type,
                hostname=host,
                status=status,
                current_job_id=str_job_id,
                tenant_id=tenant_id,
                last_seen=now,
                started_at=now
            )
            db.add(heartbeat)
        else:
            heartbeat.status = status
            heartbeat.hostname = host
            heartbeat.current_job_id = str_job_id
            if tenant_id:
                heartbeat.tenant_id = tenant_id
            heartbeat.last_seen = now

        # Si hay un job activo, refrescar su último latido y worker asignado
        if current_job_id is not None:
            job = db.query(ProcessingJob).filter(_build_job_filter(current_job_id)).first()
            if job:
                job.last_heartbeat_at = now
                job.worker_name = worker_name
                job.updated_at = now

        # Emisión de métricas Prometheus para estado de worker (Fase 7.1)
        try:
            record_worker_telemetry(
                worker_type=worker_type,
                status=status,
                count=1
            )
        except Exception as te:
            logger.debug(f"Error emitiendo telemetría Prometheus para worker {worker_name}: {te}")

        db.commit()
        db.refresh(heartbeat)
        return heartbeat

    @staticmethod
    def create_job(
        db: Session,
        case_id: int,
        tenant_id: str,
        user_id: Optional[int],
        job_type: str,
        job_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        document_id: Optional[int] = None,
        worker_type: str = "abst_worker"
    ) -> ProcessingJob:
        """
        Crea y persiste un nuevo ProcessingJob con estado inicial QUEUED.
        """
        if not job_id:
            job_id = f"{job_type.lower()}_{case_id}_{uuid.uuid4().hex[:8]}"

        job = ProcessingJob(
            job_id=job_id,
            case_id=case_id,
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=document_id,
            job_type=job_type,
            worker_type=worker_type,
            status="QUEUED",
            progress=0,
            status_message="En cola de procesamiento",
            idempotency_key=idempotency_key,
            attempt_count=1,
            max_retries=3,
            created_at=_utc_now()
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_by_job_id(
        db: Session,
        job_id: Union[str, int],
        tenant_id: Optional[str] = None
    ) -> Optional[ProcessingJob]:
        """
        Busca un job por su job_id o PK y opcionalmente valida el tenant.
        """
        query = db.query(ProcessingJob).filter(_build_job_filter(job_id))
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)
        return query.first()

    @staticmethod
    def get_by_idempotency_key(
        db: Session,
        idempotency_key: str,
        tenant_id: Optional[str] = None
    ) -> Optional[ProcessingJob]:
        """
        Busca el job más reciente asociado a una clave de idempotencia.
        """
        query = db.query(ProcessingJob).filter(ProcessingJob.idempotency_key == idempotency_key)
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)
        return query.order_by(ProcessingJob.id.desc()).first()

    @staticmethod
    def get_active_job_for_case(
        db: Session,
        case_id: int,
        job_type: str,
        tenant_id: Optional[str] = None
    ) -> Optional[ProcessingJob]:
        """
        Verifica si ya existe un job activo (QUEUED o PROCESSING) para un expediente y tipo de tarea.
        """
        query = db.query(ProcessingJob).filter(
            ProcessingJob.case_id == case_id,
            ProcessingJob.job_type == job_type,
            ProcessingJob.status.in_(["QUEUED", "PROCESSING", "started", "pending"])
        )
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)
        return query.order_by(ProcessingJob.id.desc()).first()

    @staticmethod
    def update_progress(
        db: Session,
        job_id: Union[str, int],
        progress: int,
        status_message: Optional[str] = None,
        status: str = "PROCESSING",
        tenant_id: Optional[str] = None,
        worker_name: Optional[str] = None
    ) -> Optional[ProcessingJob]:
        """
        Actualiza el progreso porcentual (0-100), estado, mensaje descriptivo y latido.
        """
        now = _utc_now()
        query = db.query(ProcessingJob).filter(_build_job_filter(job_id))
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)
        job = query.first()
        if not job:
            logger.warning(f"ProcessingJob {job_id} no encontrado para update_progress.")
            return None

        job.progress = max(0, min(100, progress))
        job.status = status
        if status_message:
            job.status_message = status_message
        if not job.started_at and status in ("PROCESSING", "started"):
            job.started_at = now
        if worker_name:
            job.worker_name = worker_name
        job.last_heartbeat_at = now
        job.updated_at = now

        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def mark_completed(
        db: Session,
        job_id: Union[str, int],
        result_summary: Optional[Dict[str, Any]] = None,
        status_message: str = "Procesamiento completado exitosamente",
        tenant_id: Optional[str] = None,
        worker_name: Optional[str] = None,
        pages_processed: int = 0
    ) -> Optional[ProcessingJob]:
        """
        Marca el job como READY/COMPLETED, guarda el resumen de resultados,
        registra finished_at y genera la métrica analítica en ProcessingMetrics.
        """
        now = _utc_now()
        query = db.query(ProcessingJob).filter(_build_job_filter(job_id))
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)
        job = query.first()
        if not job:
            logger.warning(f"ProcessingJob {job_id} no encontrado para mark_completed.")
            return None

        effective_worker = worker_name or job.worker_name or "unassigned"

        job.status = "READY"
        job.progress = 100
        job.status_message = status_message
        job.worker_name = effective_worker
        if result_summary:
            job.result_summary = json.dumps(result_summary, default=str)
        job.finished_at = now
        job.last_heartbeat_at = now
        job.updated_at = now

        # Asegurar que job_id esté poblado para satisfacer la FK en processing_metrics
        if not job.job_id:
            job.job_id = str(job.id)
            db.flush()

        # Registro de métrica analítica
        JobRepository._record_metric(
            db=db,
            job=job,
            effective_worker=effective_worker,
            success=True,
            pages_processed=pages_processed,
            now=now
        )

        # Actualizar heartbeat a IDLE si el worker está registrado
        if worker_name:
            hb = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_name == worker_name).first()
            if hb:
                hb.status = "IDLE"
                hb.current_job_id = None
                hb.last_seen = now

        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def mark_failed(
        db: Session,
        job_id: Union[str, int],
        error_message: str,
        status_message: Optional[str] = None,
        tenant_id: Optional[str] = None,
        worker_name: Optional[str] = None,
        error_code: Optional[str] = None,
        error_category: Optional[str] = None,
        failure_classification: Optional[str] = None,
        pages_processed: int = 0
    ) -> Optional[ProcessingJob]:
        """
        Marca el job como FAILED, clasifica el error y persiste ProcessingMetrics de fallo.
        """
        now = _utc_now()
        query = db.query(ProcessingJob).filter(_build_job_filter(job_id))
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)
        job = query.first()
        if not job:
            logger.warning(f"ProcessingJob {job_id} no encontrado para mark_failed.")
            return None

        effective_worker = worker_name or job.worker_name or "unassigned"

        job.status = "FAILED"
        job.progress = 100
        job.error_message = error_message
        job.status_message = status_message or f"Error: {error_message[:200]}"
        job.worker_name = effective_worker
        job.failure_classification = failure_classification or ("FINAL" if error_category in ("CORRUPT_INPUT", "BUSINESS_RULE") else "RETRYABLE")
        job.finished_at = now
        job.last_heartbeat_at = now
        job.updated_at = now

        # Asegurar que job_id esté poblado para satisfacer la FK en processing_metrics
        if not job.job_id:
            job.job_id = str(job.id)
            db.flush()

        # Registro de métrica analítica de fallo
        JobRepository._record_metric(
            db=db,
            job=job,
            effective_worker=effective_worker,
            success=False,
            error_code=error_code or "ERROR",
            error_category=error_category or "UNEXPECTED_ERROR",
            pages_processed=pages_processed,
            now=now
        )

        # Actualizar heartbeat a IDLE si el worker está registrado
        if worker_name:
            hb = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_name == worker_name).first()
            if hb:
                hb.status = "IDLE"
                hb.current_job_id = None
                hb.last_seen = now

        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_stale_processing_jobs(
        db: Session,
        heartbeat_timeout_seconds: int = 30,
        tenant_id: Optional[str] = None
    ) -> List[ProcessingJob]:
        """
        Retorna los ProcessingJobs en estado PROCESSING (o started) cuyo último heartbeat
        ha expirado según el umbral heartbeat_timeout_seconds.
        """
        cutoff = _utc_now() - timedelta(seconds=heartbeat_timeout_seconds)

        stale_condition = or_(
            ProcessingJob.last_heartbeat_at < cutoff,
            and_(ProcessingJob.last_heartbeat_at.is_(None), ProcessingJob.started_at < cutoff),
            and_(ProcessingJob.last_heartbeat_at.is_(None), ProcessingJob.started_at.is_(None), ProcessingJob.created_at < cutoff)
        )

        query = db.query(ProcessingJob).filter(
            ProcessingJob.status.in_(["PROCESSING", "started"]),
            stale_condition
        )
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)

        return query.order_by(ProcessingJob.id.asc()).all()

    @staticmethod
    def get_stale_queued_jobs(
        db: Session,
        queued_timeout_seconds: int = 300,
        tenant_id: Optional[str] = None
    ) -> List[ProcessingJob]:
        """
        Retorna los ProcessingJobs en estado QUEUED (o pending) que han permanecido
        en cola más tiempo del permitido por queued_timeout_seconds.
        """
        cutoff = _utc_now() - timedelta(seconds=queued_timeout_seconds)

        query = db.query(ProcessingJob).filter(
            ProcessingJob.status.in_(["QUEUED", "pending"]),
            ProcessingJob.created_at < cutoff
        )
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)

        return query.order_by(ProcessingJob.id.asc()).all()

    @staticmethod
    def recover_and_retry_job(
        db: Session,
        job_id: Union[str, int],
        reason: str,
        failure_classification: Optional[str] = None,
        base_backoff_sec: int = 5,
        tenant_id: Optional[str] = None
    ) -> Tuple[bool, Optional[ProcessingJob], str]:
        """
        Ejecuta la recuperación transaccional de un job con SELECT FOR UPDATE.
        Evalúa si es reintentable o final:
          - Si es FINAL o attempt_count >= max_retries: Marca FAILED, emite AuditLog y ProcessingMetrics.
          - Si es RETRYABLE y attempt_count < max_retries: Incrementa attempt_count, aplica backoff exponencial,
            resetea a QUEUED y registra AuditLog.
        Retorna (is_retried: bool, job: Optional[ProcessingJob], outcome: str).
        """
        now = _utc_now()
        query = db.query(ProcessingJob).filter(_build_job_filter(job_id)).with_for_update()
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)
        job = query.first()

        if not job:
            logger.warning(f"ProcessingJob {job_id} no encontrado para recuperación.")
            return False, None, "NOT_FOUND"

        # Si ya terminó en un estado terminal, ignorar para evitar duplicaciones
        if job.status in ("READY", "COMPLETED"):
            return False, job, "ALREADY_COMPLETED"
        if job.status == "FAILED" and job.failure_classification == "FINAL":
            return False, job, "ALREADY_FAILED_FINAL"

        err_code, err_cat, auto_classif = JobRepository.classify_error(reason)
        effective_classif = failure_classification or job.failure_classification or auto_classif

        # Asegurar FK para processing_metrics
        if not job.job_id:
            job.job_id = str(job.id)
            db.flush()

        effective_worker = job.worker_name or "recovery_engine"

        # 1. Caso FINAL: Fallo no reintentable
        if effective_classif == "FINAL":
            job.status = "FAILED"
            job.progress = 100
            job.error_message = f"Fallo no reintentable: {reason}"
            job.status_message = f"Error definitivo ({err_code}): {reason[:200]}"
            job.failure_classification = "FINAL"
            job.finished_at = now
            job.updated_at = now

            audit = AuditLog(
                tenant_id=job.tenant_id,
                user_id=job.user_id,
                action="JOB_RECOVERY_FAILED_FINAL",
                entity_type="ProcessingJob",
                entity_id=job.job_id,
                status="FAILED",
                details=f"Job marcado como FAILED definitivo sin retry. Código: {err_code}. Causa: {reason}"
            )
            db.add(audit)

            JobRepository._record_metric(
                db=db,
                job=job,
                effective_worker=effective_worker,
                success=False,
                error_code=err_code,
                error_category=err_cat,
                now=now
            )

            db.commit()
            db.refresh(job)
            return False, job, "FAILED_FINAL"

        # 2. Caso Límite de reintentos excedido
        if job.attempt_count >= job.max_retries:
            job.status = "FAILED"
            job.progress = 100
            job.error_message = f"Límite de reintentos alcanzado ({job.attempt_count}/{job.max_retries}). Causa: {reason}"
            job.status_message = f"Error definitivo: Excedidos {job.max_retries} reintentos ({err_code})"
            job.failure_classification = "FINAL"
            job.finished_at = now
            job.updated_at = now

            audit = AuditLog(
                tenant_id=job.tenant_id,
                user_id=job.user_id,
                action="JOB_RECOVERY_MAX_RETRIES_EXCEEDED",
                entity_type="ProcessingJob",
                entity_id=job.job_id,
                status="FAILED",
                details=f"Job cancelado tras agotar {job.max_retries} intentos ({job.attempt_count}/{job.max_retries}). Código: {err_code}. Causa: {reason}"
            )
            db.add(audit)

            JobRepository._record_metric(
                db=db,
                job=job,
                effective_worker=effective_worker,
                success=False,
                error_code="MAX_RETRIES_EXCEEDED",
                error_category=err_cat or "TRANSIENT_INFRA",
                now=now
            )

            db.commit()
            db.refresh(job)
            return False, job, "MAX_RETRIES_EXCEEDED"

        # 3. Caso RETRYABLE: Reintento con backoff exponencial
        backoff_sec = int(base_backoff_sec * (2 ** (job.attempt_count - 1)))
        job.attempt_count += 1
        job.status = "QUEUED"
        job.progress = 0
        job.worker_name = None
        job.last_heartbeat_at = None
        job.started_at = None
        job.finished_at = None
        job.failure_classification = "RETRYABLE"
        job.status_message = f"Job recuperado y re-encolado (Intento {job.attempt_count}/{job.max_retries}, backoff {backoff_sec}s). Motivo: {reason}"
        job.updated_at = now

        audit = AuditLog(
            tenant_id=job.tenant_id,
            user_id=job.user_id,
            action="JOB_RECOVERY_RETRY",
            entity_type="ProcessingJob",
            entity_id=job.job_id,
            status="QUEUED",
            details=f"Job recuperado para reintento {job.attempt_count}/{job.max_retries} (backoff {backoff_sec}s). Motivo: {reason}"
        )
        db.add(audit)

        db.commit()
        db.refresh(job)
        return True, job, "RETRY_QUEUED"

    @staticmethod
    def can_dispatch_job(
        db: Session,
        tenant_id: str,
        max_tenant_concurrency: Optional[int] = None,
        max_system_concurrency: Optional[int] = None
    ) -> bool:
        """
        Consulta al TenantCapacityGovernor si el tenant tiene cuota disponible para despachar un job.
        """
        from app.services.capacity_governor import TenantCapacityGovernor
        return TenantCapacityGovernor.can_dispatch(
            db=db,
            tenant_id=tenant_id,
            max_tenant_concurrency=max_tenant_concurrency,
            max_system_concurrency=max_system_concurrency
        )

    @staticmethod
    def claim_and_start_job(
        db: Session,
        job_id: Union[str, int],
        worker_name: str,
        tenant_id: Optional[str] = None,
        max_tenant_concurrency: Optional[int] = None,
        max_system_concurrency: Optional[int] = None
    ) -> Tuple[bool, Optional[ProcessingJob], str]:
        """
        Reclama e inicia atómicamente la ejecución de un job respetando la jerarquía estricta de locks:
        1. Advisory Lock Global: pg_advisory_xact_lock(1001, 1)
        2. Advisory Lock Tenant: pg_advisory_xact_lock(1002, hashtext(tenant_id))
        3. Evaluación de Capacidad (COUNTs indexados en PostgreSQL SSOT)
        4. Bloqueo de fila: SELECT FOR UPDATE
        5. Mutación de estado QUEUED -> PROCESSING (o retención con supresión de WAL churn)
        6. Commit transaccional
        """
        from app.services.capacity_governor import TenantCapacityGovernor
        t0 = time.perf_counter()
        now = _utc_now()

        # Determinar tenant objetivo para locking jerárquico
        target_tenant = str(tenant_id or "default")
        is_postgres = "postgresql" in str(db.bind.url if db.bind else "").lower()

        # 1. Adquirir Advisory Lock Global
        # 2. Adquirir Advisory Lock Tenant
        if is_postgres:
            try:
                db.execute(text("SELECT pg_advisory_xact_lock(1001, 1)"))
                db.execute(
                    text("SELECT pg_advisory_xact_lock(1002, hashtext(:tid))"),
                    {"tid": target_tenant}
                )
            except Exception as lock_err:
                logger.warning(f"Advisory lock notice: {lock_err}")

        # 3. Evaluación de Capacidad Multi-Tenant
        can_run, reason, metrics = TenantCapacityGovernor.evaluate_capacity(
            db=db,
            tenant_id=tenant_id,
            max_tenant_concurrency=max_tenant_concurrency,
            max_system_concurrency=max_system_concurrency
        )

        # 4. Seleccionar y bloquear la fila del job
        query = db.query(ProcessingJob).filter(_build_job_filter(job_id)).with_for_update()
        if tenant_id:
            query = query.filter(ProcessingJob.tenant_id == tenant_id)
        job = query.first()

        claim_duration = max(0.0001, time.perf_counter() - t0)

        if not job:
            db.rollback()
            record_capacity_claim(result="failed", reason="no_candidate", duration_seconds=claim_duration)
            return False, None, "NOT_FOUND"

        if job.status in ("PROCESSING", "READY", "COMPLETED", "FAILED"):
            db.rollback()
            record_capacity_claim(result="failed", reason="already_processed", duration_seconds=claim_duration)
            return False, job, f"ALREADY_{job.status}"

        # Si no se pasó tenant_id explícito pero el job tiene uno distinto de "default",
        # asegurar el lock específico del tenant del job
        if not tenant_id and job.tenant_id and job.tenant_id != target_tenant and is_postgres:
            try:
                db.execute(
                    text("SELECT pg_advisory_xact_lock(1002, hashtext(:tid))"),
                    {"tid": str(job.tenant_id)}
                )
            except Exception:
                pass
            can_run, reason, metrics = TenantCapacityGovernor.evaluate_capacity(
                db=db,
                tenant_id=job.tenant_id,
                max_tenant_concurrency=max_tenant_concurrency,
                max_system_concurrency=max_system_concurrency
            )

        if not can_run:
            new_msg = f"En espera de capacidad ({reason}: {metrics.get('tenant_active', 0)}/{metrics.get('tenant_limit', 0)} activos)"
            # Supresión de WAL Churn: solo mutar si el mensaje es diferente
            if job.status_message != new_msg:
                job.status_message = new_msg
                db.commit()
                db.refresh(job)
            else:
                db.rollback()
            record_job_retained(reason=reason)
            record_capacity_claim(result="retained", reason=reason, duration_seconds=claim_duration)
            return False, job, reason

        # 5. Capacidad Concedida: Transicionar atómicamente a PROCESSING
        job.status = "PROCESSING"
        job.progress = max(5, job.progress)
        job.worker_name = worker_name
        job.status_message = "Procesamiento en ejecución"
        job.started_at = job.started_at or now
        job.last_heartbeat_at = now
        job.updated_at = now

        db.commit()
        db.refresh(job)
        record_capacity_claim(result="claimed", reason="success", duration_seconds=claim_duration)
        return True, job, "STARTED"

    @staticmethod
    def claim_next_fair_job(
        db: Session,
        worker_name: str,
        max_tenant_concurrency: Optional[int] = None,
        max_system_concurrency: Optional[int] = None
    ) -> Tuple[bool, Optional[ProcessingJob], str]:
        """
        Reclama atómicamente el siguiente job disponible respetando la política de Fair Sharing.
        Aplica el orden jerárquico GLOBAL -> TENANT -> ROW LOCK para prevenir condiciones de carrera.
        """
        from app.services.capacity_governor import TenantCapacityGovernor
        t0 = time.perf_counter()
        now = _utc_now()
        is_postgres = "postgresql" in str(db.bind.url if db.bind else "").lower()

        # 1. Advisory Lock Global
        if is_postgres:
            try:
                db.execute(text("SELECT pg_advisory_xact_lock(1001, 1)"))
            except Exception as le:
                logger.warning(f"Advisory lock warning: {le}")

        # 2. Buscar candidato elegible (excluyendo tenants saturados con SKIP LOCKED)
        candidate = TenantCapacityGovernor.find_next_fair_claimable_job(
            db=db,
            max_tenant_concurrency=max_tenant_concurrency,
            max_system_concurrency=max_system_concurrency
        )

        claim_duration = max(0.0001, time.perf_counter() - t0)

        if not candidate:
            db.rollback()
            record_capacity_claim(result="retained", reason="no_candidate", duration_seconds=claim_duration)
            return False, None, "NO_CANDIDATE"

        # 3. Advisory Lock del Tenant del candidato
        if is_postgres and candidate.tenant_id:
            try:
                db.execute(
                    text("SELECT pg_advisory_xact_lock(1002, hashtext(:tid))"),
                    {"tid": str(candidate.tenant_id)}
                )
            except Exception as le:
                logger.warning(f"Tenant advisory lock warning: {le}")

        # 4. Evaluación de capacidad final
        can_run, reason, metrics = TenantCapacityGovernor.evaluate_capacity(
            db=db,
            tenant_id=candidate.tenant_id,
            max_tenant_concurrency=max_tenant_concurrency,
            max_system_concurrency=max_system_concurrency
        )

        if not can_run:
            new_msg = f"En espera de capacidad ({reason}: {metrics.get('tenant_active', 0)}/{metrics.get('tenant_limit', 0)} activos)"
            if candidate.status_message != new_msg:
                candidate.status_message = new_msg
                db.commit()
                db.refresh(candidate)
            else:
                db.rollback()
            record_job_retained(reason=reason)
            record_capacity_claim(result="retained", reason=reason, duration_seconds=claim_duration)
            return False, candidate, reason

        # 5. Transicionar a PROCESSING
        candidate.status = "PROCESSING"
        candidate.progress = max(5, candidate.progress)
        candidate.worker_name = worker_name
        candidate.status_message = "Procesamiento en ejecución"
        candidate.started_at = candidate.started_at or now
        candidate.last_heartbeat_at = now
        candidate.updated_at = now

        db.commit()
        db.refresh(candidate)
        record_capacity_claim(result="claimed", reason="success", duration_seconds=claim_duration)
        return True, candidate, "STARTED"

    @staticmethod
    def get_capacity_report(db: Session, tenant_ids: Optional[list] = None) -> Dict[str, Any]:
        """
        Retorna el informe de capacidad multi-tenant y global.
        """
        from app.services.capacity_governor import TenantCapacityGovernor
        return TenantCapacityGovernor.get_capacity_report(db, tenant_ids=tenant_ids)
