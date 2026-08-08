import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.domain import WorkerHeartbeat, ProcessingMetrics, ProcessingJob, AuditLog
from app.schemas.monitoring import (
    WorkerStatusResponse,
    WorkerListResponse,
    LatencyMetricsResponse,
    LatencyReportResponse,
    ErrorSummaryItem,
    ErrorAnalyticsResponse,
    StaleJobSummaryItem,
    RecoverySummaryResponse
)
from app.services.job_repository import JobRepository

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MonitoringService:
    """
    Servicio central de observabilidad y telemetría SRE V5.4.
    Provee métricas operacionales agregadas, salud de workers, latencias percentiles
    y analítica de fallos bajo estrictos principios de SSOT, Read-Only y Multi-tenancy.
    """

    DEFAULT_HEARTBEAT_THRESHOLD_SECONDS = 30
    DEFAULT_TIME_WINDOW_HOURS = 24
    MAX_TIME_WINDOW_HOURS = 168  # 7 días máximo
    MIN_TIME_WINDOW_HOURS = 1

    # =========================================================
    # 1. WORKER CLUSTER & LIVENESS STATUS
    # =========================================================

    @classmethod
    def get_workers_status(
        cls,
        db: Session,
        tenant_id: Optional[str] = None,
        heartbeat_threshold_sec: int = DEFAULT_HEARTBEAT_THRESHOLD_SECONDS
    ) -> WorkerListResponse:
        """
        Inspecciona el estado de los workers en base a WorkerHeartbeat.
        Determina dinámicamente si un worker está UNRESPONSIVE si ha transcurrido
        más del umbral sin latido, SIN mutar la base de datos (Read-Only).
        """
        now = _utc_now()
        query = db.query(WorkerHeartbeat)
        
        if tenant_id:
            query = query.filter(
                (WorkerHeartbeat.tenant_id == tenant_id) | (WorkerHeartbeat.tenant_id.is_(None))
            )
            
        heartbeats = query.order_by(WorkerHeartbeat.worker_name).all()

        worker_statuses: List[WorkerStatusResponse] = []
        total_active = 0
        total_busy = 0
        total_unresponsive = 0
        total_offline = 0

        for hb in heartbeats:
            last_seen_dt = hb.last_seen
            if last_seen_dt and last_seen_dt.tzinfo is None:
                last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)

            started_at_dt = hb.started_at
            if started_at_dt and started_at_dt.tzinfo is None:
                started_at_dt = started_at_dt.replace(tzinfo=timezone.utc)

            # Cálculo de uptime
            uptime_seconds = 0
            if started_at_dt:
                uptime_seconds = max(0, int((now - started_at_dt).total_seconds()))

            # Detección dinámica de liveness
            delta_seconds = 0
            if last_seen_dt:
                delta_seconds = max(0, int((now - last_seen_dt).total_seconds()))

            status_declared = hb.status.upper() if hb.status else "IDLE"
            effective_status = status_declared
            is_healthy = False

            if status_declared == "OFFLINE":
                effective_status = "OFFLINE"
                is_healthy = False
                total_offline += 1
            elif delta_seconds > heartbeat_threshold_sec:
                effective_status = "UNRESPONSIVE"
                is_healthy = False
                total_unresponsive += 1
            else:
                is_healthy = True
                total_active += 1
                if status_declared == "BUSY":
                    total_busy += 1

            worker_statuses.append(
                WorkerStatusResponse(
                    worker_name=hb.worker_name,
                    worker_type=hb.worker_type,
                    hostname=hb.hostname,
                    status=effective_status,
                    current_job_id=hb.current_job_id,
                    tenant_id=hb.tenant_id,
                    last_seen=last_seen_dt or now,
                    started_at=started_at_dt or now,
                    uptime_seconds=uptime_seconds,
                    is_healthy=is_healthy
                )
            )

        return WorkerListResponse(
            total_workers=len(worker_statuses),
            total_active=total_active,
            total_busy=total_busy,
            total_unresponsive=total_unresponsive,
            total_offline=total_offline,
            workers=worker_statuses
        )

    # =========================================================
    # 2. LATENCY METRICS & SLA PERCENTILES (p50, p95, p99)
    # =========================================================

    @classmethod
    def get_latency_metrics(
        cls,
        db: Session,
        tenant_id: str,
        job_type: Optional[str] = None,
        hours: int = DEFAULT_TIME_WINDOW_HOURS
    ) -> LatencyReportResponse:
        """
        Calcula percentiles de latencia (p50, p95, p99), promedios, mínimos y máximos
        utilizando SQL analítico nativo de PostgreSQL sobre ProcessingMetrics.
        Garantiza aislamiento multi-tenant y acotación temporal.
        """
        # Validación y acotación de ventana temporal
        clamped_hours = max(cls.MIN_TIME_WINDOW_HOURS, min(hours, cls.MAX_TIME_WINDOW_HOURS))
        cutoff = _utc_now() - timedelta(hours=clamped_hours)

        # Función auxiliar para calcular agregaciones sobre un subconjunto
        def _compute_metrics_for_query(base_q, job_type_label: str) -> LatencyMetricsResponse:
            try:
                row = base_q.with_entities(
                    func.count(ProcessingMetrics.id).label("sample_count"),
                    func.percentile_cont(0.50).within_group(ProcessingMetrics.total_time_ms.asc()).label("p50"),
                    func.percentile_cont(0.95).within_group(ProcessingMetrics.total_time_ms.asc()).label("p95"),
                    func.percentile_cont(0.99).within_group(ProcessingMetrics.total_time_ms.asc()).label("p99"),
                    func.avg(ProcessingMetrics.total_time_ms).label("avg_ms"),
                    func.min(ProcessingMetrics.total_time_ms).label("min_ms"),
                    func.max(ProcessingMetrics.total_time_ms).label("max_ms"),
                ).first()

                sample_count = int(row.sample_count or 0) if row else 0
                if sample_count == 0:
                    return LatencyMetricsResponse(
                        job_type=job_type_label,
                        sample_count=0,
                        p50_ms=0.0,
                        p95_ms=0.0,
                        p99_ms=0.0,
                        avg_ms=0.0,
                        min_ms=0,
                        max_ms=0,
                        time_window_hours=clamped_hours
                    )

                return LatencyMetricsResponse(
                    job_type=job_type_label,
                    sample_count=sample_count,
                    p50_ms=round(float(row.p50 or 0.0), 2),
                    p95_ms=round(float(row.p95 or 0.0), 2),
                    p99_ms=round(float(row.p99 or 0.0), 2),
                    avg_ms=round(float(row.avg_ms or 0.0), 2),
                    min_ms=int(row.min_ms or 0),
                    max_ms=int(row.max_ms or 0),
                    time_window_hours=clamped_hours
                )
            except Exception as e:
                logger.warning(f"[MonitoringService] Fallback en cálculo de percentiles para {job_type_label}: {e}")
                # Fallback manual en Python en caso de BD sin soporte nativo de within_group
                records = [r[0] for r in base_q.with_entities(ProcessingMetrics.total_time_ms).all() if r[0] is not None]
                if not records:
                    return LatencyMetricsResponse(
                        job_type=job_type_label,
                        sample_count=0,
                        p50_ms=0.0,
                        p95_ms=0.0,
                        p99_ms=0.0,
                        avg_ms=0.0,
                        min_ms=0,
                        max_ms=0,
                        time_window_hours=clamped_hours
                    )
                records.sort()
                n = len(records)
                def _pct(p):
                    k = (n - 1) * p
                    f = int(k)
                    c = f + 1 if f + 1 < n else f
                    d = k - f
                    return records[f] + d * (records[c] - records[f])

                return LatencyMetricsResponse(
                    job_type=job_type_label,
                    sample_count=n,
                    p50_ms=round(float(_pct(0.50)), 2),
                    p95_ms=round(float(_pct(0.95)), 2),
                    p99_ms=round(float(_pct(0.99)), 2),
                    avg_ms=round(float(sum(records) / n), 2),
                    min_ms=int(records[0]),
                    max_ms=int(records[-1]),
                    time_window_hours=clamped_hours
                )

        # 1. Query base acotada por tenant y ventana temporal
        base_query = db.query(ProcessingMetrics).filter(
            ProcessingMetrics.tenant_id == tenant_id,
            ProcessingMetrics.created_at >= cutoff
        )

        if job_type:
            base_query = base_query.filter(ProcessingMetrics.job_type == job_type)

        global_metrics = _compute_metrics_for_query(base_query, job_type or "GLOBAL")

        # 2. Desglose por cada tipo de job presente en el período
        distinct_types_query = db.query(ProcessingMetrics.job_type).filter(
            ProcessingMetrics.tenant_id == tenant_id,
            ProcessingMetrics.created_at >= cutoff
        ).distinct()
        
        if job_type:
            distinct_types_query = distinct_types_query.filter(ProcessingMetrics.job_type == job_type)

        distinct_types = [t[0] for t in distinct_types_query.all() if t[0]]
        metrics_by_type: List[LatencyMetricsResponse] = []

        for j_type in sorted(distinct_types):
            type_q = db.query(ProcessingMetrics).filter(
                ProcessingMetrics.tenant_id == tenant_id,
                ProcessingMetrics.created_at >= cutoff,
                ProcessingMetrics.job_type == j_type
            )
            metrics_by_type.append(_compute_metrics_for_query(type_q, j_type))

        return LatencyReportResponse(
            time_window_hours=clamped_hours,
            total_samples=global_metrics.sample_count,
            global_metrics=global_metrics,
            metrics_by_job_type=metrics_by_type
        )

    # =========================================================
    # 3. ERROR ANALYTICS & TAXONOMY BREAKDOWN
    # =========================================================

    @classmethod
    def get_error_analytics(
        cls,
        db: Session,
        tenant_id: str,
        hours: int = DEFAULT_TIME_WINDOW_HOURS
    ) -> ErrorAnalyticsResponse:
        """
        Agrupa y analiza métricas de error (success=False) según la taxonomía V5.4.
        Genera matriz de fallos por categoría, código y tipo de job.
        """
        clamped_hours = max(cls.MIN_TIME_WINDOW_HOURS, min(hours, cls.MAX_TIME_WINDOW_HOURS))
        cutoff = _utc_now() - timedelta(hours=clamped_hours)

        # 1. Conteo total y fallidos en la ventana
        total_jobs = db.query(func.count(ProcessingMetrics.id)).filter(
            ProcessingMetrics.tenant_id == tenant_id,
            ProcessingMetrics.created_at >= cutoff
        ).scalar() or 0

        failed_jobs = db.query(func.count(ProcessingMetrics.id)).filter(
            ProcessingMetrics.tenant_id == tenant_id,
            ProcessingMetrics.created_at >= cutoff,
            ProcessingMetrics.success.is_(False)
        ).scalar() or 0

        failure_rate = round((failed_jobs / total_jobs * 100.0), 2) if total_jobs > 0 else 0.0

        # 2. Agrupación por error_category
        cat_rows = db.query(
            ProcessingMetrics.error_category,
            func.count(ProcessingMetrics.id)
        ).filter(
            ProcessingMetrics.tenant_id == tenant_id,
            ProcessingMetrics.created_at >= cutoff,
            ProcessingMetrics.success.is_(False)
        ).group_by(ProcessingMetrics.error_category).all()

        errors_by_category = {
            (cat or "UNCATEGORIZED"): count for cat, count in cat_rows
        }

        # 3. Agrupación por error_code
        code_rows = db.query(
            ProcessingMetrics.error_code,
            func.count(ProcessingMetrics.id)
        ).filter(
            ProcessingMetrics.tenant_id == tenant_id,
            ProcessingMetrics.created_at >= cutoff,
            ProcessingMetrics.success.is_(False)
        ).group_by(ProcessingMetrics.error_code).all()

        errors_by_code = {
            (code or "UNKNOWN_CODE"): count for code, count in code_rows
        }

        # 4. Agrupación por job_type
        type_rows = db.query(
            ProcessingMetrics.job_type,
            func.count(ProcessingMetrics.id)
        ).filter(
            ProcessingMetrics.tenant_id == tenant_id,
            ProcessingMetrics.created_at >= cutoff,
            ProcessingMetrics.success.is_(False)
        ).group_by(ProcessingMetrics.job_type).all()

        errors_by_job_type = {
            (jt or "UNKNOWN_TYPE"): count for jt, count in type_rows
        }

        # 5. Detalle granular agrupado
        detail_rows = db.query(
            ProcessingMetrics.error_category,
            ProcessingMetrics.error_code,
            ProcessingMetrics.job_type,
            func.count(ProcessingMetrics.id)
        ).filter(
            ProcessingMetrics.tenant_id == tenant_id,
            ProcessingMetrics.created_at >= cutoff,
            ProcessingMetrics.success.is_(False)
        ).group_by(
            ProcessingMetrics.error_category,
            ProcessingMetrics.error_code,
            ProcessingMetrics.job_type
        ).order_by(func.count(ProcessingMetrics.id).desc()).all()

        error_details: List[ErrorSummaryItem] = []
        for cat, code, jt, count in detail_rows:
            pct = round((count / failed_jobs * 100.0), 2) if failed_jobs > 0 else 0.0
            error_details.append(
                ErrorSummaryItem(
                    error_category=cat or "UNCATEGORIZED",
                    error_code=code or "UNKNOWN_CODE",
                    job_type=jt or "UNKNOWN_TYPE",
                    count=count,
                    percentage=pct
                )
            )

        return ErrorAnalyticsResponse(
            time_window_hours=clamped_hours,
            total_jobs=total_jobs,
            failed_jobs=failed_jobs,
            failure_rate_percent=failure_rate,
            errors_by_category=errors_by_category,
            errors_by_code=errors_by_code,
            errors_by_job_type=errors_by_job_type,
            error_details=error_details
        )

    # =========================================================
    # 4. RECOVERY STATUS & OPERATIONAL HEALTH
    # =========================================================

    @classmethod
    def get_recovery_status(
        cls,
        db: Session,
        tenant_id: str,
        heartbeat_timeout_sec: int = DEFAULT_HEARTBEAT_THRESHOLD_SECONDS,
        queued_timeout_sec: int = 300
    ) -> RecoverySummaryResponse:
        """
        Monitorea el estado del subsistema de recuperación automática de jobs V5.4.
        Consulta JobRepository de forma estrictamente Read-Only.
        """
        now = _utc_now()

        # 1. Obtener jobs estancados mediante JobRepository
        stale_processing = JobRepository.get_stale_processing_jobs(
            db=db,
            heartbeat_timeout_seconds=heartbeat_timeout_sec,
            tenant_id=tenant_id
        )

        stale_queued = JobRepository.get_stale_queued_jobs(
            db=db,
            queued_timeout_seconds=queued_timeout_sec,
            tenant_id=tenant_id
        )

        # 2. Conteo de jobs recuperados (reintentados exitosamente o en proceso con attempt > 1)
        recovered_count = db.query(func.count(ProcessingJob.id)).filter(
            ProcessingJob.tenant_id == tenant_id,
            ProcessingJob.attempt_count > 1
        ).scalar() or 0

        # 3. Conteo de fallos finales
        failed_final_count = db.query(func.count(ProcessingJob.id)).filter(
            ProcessingJob.tenant_id == tenant_id,
            ProcessingJob.status == "FAILED",
            ProcessingJob.failure_classification == "FINAL"
        ).scalar() or 0

        # 4. Última ejecución registrada en AuditLog de recuperación
        last_audit = db.query(AuditLog.created_at).filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action.in_([
                "JOB_RECOVERY_RETRIED",
                "JOB_RECOVERY_FAILED_FINAL",
                "JOB_RECOVERY_MAX_RETRIES_EXCEEDED",
                "ADMIN_TRIGGER_RECOVERY"
            ])
        ).order_by(AuditLog.created_at.desc()).first()

        last_execution = last_audit[0] if last_audit else None
        if last_execution and last_execution.tzinfo is None:
            last_execution = last_execution.replace(tzinfo=timezone.utc)

        # Formateo de items
        stale_proc_items: List[StaleJobSummaryItem] = []
        for job in stale_processing:
            duration_sec = None
            if job.last_heartbeat_at:
                hb_dt = job.last_heartbeat_at
                if hb_dt.tzinfo is None:
                    hb_dt = hb_dt.replace(tzinfo=timezone.utc)
                duration_sec = max(0, int((now - hb_dt).total_seconds()))
            elif job.started_at:
                st_dt = job.started_at
                if st_dt.tzinfo is None:
                    st_dt = st_dt.replace(tzinfo=timezone.utc)
                duration_sec = max(0, int((now - st_dt).total_seconds()))

            stale_proc_items.append(
                StaleJobSummaryItem(
                    job_id=job.job_id or str(job.id),
                    job_type=job.job_type,
                    status=job.status,
                    attempt_count=job.attempt_count,
                    max_retries=job.max_retries,
                    worker_name=job.worker_name,
                    stale_duration_seconds=duration_sec
                )
            )

        stale_queue_items: List[StaleJobSummaryItem] = []
        for job in stale_queued:
            duration_sec = None
            if job.created_at:
                cr_dt = job.created_at
                if cr_dt.tzinfo is None:
                    cr_dt = cr_dt.replace(tzinfo=timezone.utc)
                duration_sec = max(0, int((now - cr_dt).total_seconds()))

            stale_queue_items.append(
                StaleJobSummaryItem(
                    job_id=job.job_id or str(job.id),
                    job_type=job.job_type,
                    status=job.status,
                    attempt_count=job.attempt_count,
                    max_retries=job.max_retries,
                    worker_name=job.worker_name,
                    stale_duration_seconds=duration_sec
                )
            )

        return RecoverySummaryResponse(
            stale_processing_count=len(stale_proc_items),
            stale_queued_count=len(stale_queue_items),
            recovered_jobs_count=recovered_count,
            failed_final_count=failed_final_count,
            last_execution=last_execution,
            stale_processing_jobs=stale_proc_items,
            stale_queued_jobs=stale_queue_items
        )
