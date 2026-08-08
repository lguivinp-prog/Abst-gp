import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import User, AuditLog
from app.api.auth import require_role
from app.schemas.monitoring import (
    WorkerListResponse,
    LatencyReportResponse,
    ErrorAnalyticsResponse,
    RecoverySummaryResponse,
    RecoveryTriggerResponse
)
from app.services.monitoring_service import MonitoringService
from app.services.job_recovery_engine import JobRecoveryEngine

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_tenant_id(current_user: User, requested_tenant_id: Optional[str] = None) -> Optional[str]:
    """
    Resuelve el tenant_id respetando la seguridad multi-tenant:
    - Si el usuario administrador está asignado a un tenant específico,
      SOLO puede consultar y operar sobre su propio tenant.
    - Si es Superadmin global (sin tenant_id), puede filtrar por el tenant solicitado
      o consultar globalmente según el endpoint.
    """
    if current_user.tenant_id:
        return current_user.tenant_id
    return requested_tenant_id


# =========================================================
# 1. WORKERS LIVENESS & STATUS ENDPOINT
# =========================================================

@router.get("/workers", response_model=WorkerListResponse, status_code=status.HTTP_200_OK)
def get_workers_status(
    tenant_id: Optional[str] = Query(None, description="Filtrar workers por tenant (solo superadmin)"),
    heartbeat_threshold_sec: int = Query(30, ge=5, le=300, description="Umbral en segundos para clasificar worker como UNRESPONSIVE"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """
    Inspecciona en tiempo real la salud y estado de liveness del cluster de workers RQ/OCR.
    Clasifica dinámicamente workers como IDLE, BUSY, UNRESPONSIVE u OFFLINE sin mutar la BD.
    """
    effective_tenant = _resolve_tenant_id(current_user, tenant_id)
    return MonitoringService.get_workers_status(
        db=db,
        tenant_id=effective_tenant,
        heartbeat_threshold_sec=heartbeat_threshold_sec
    )


# =========================================================
# 2. LATENCY METRICS & SLA PERCENTILES ENDPOINT
# =========================================================

@router.get("/latencies", response_model=LatencyReportResponse, status_code=status.HTTP_200_OK)
def get_latency_metrics(
    job_type: Optional[str] = Query(None, description="Tipo de job específico (ej. QUOTATION_EXTRACTION, COMPARISON_RUN)"),
    hours: int = Query(24, ge=1, le=168, description="Ventana de tiempo en horas (máximo 168h / 7 días)"),
    tenant_id: Optional[str] = Query(None, description="Filtrar por tenant (solo superadmin)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """
    Obtiene las métricas agregadas de SLA y percentiles (p50, p95, p99, avg, min, max)
    calculadas directamente sobre ProcessingMetrics vía PostgreSQL nativo.
    """
    effective_tenant = _resolve_tenant_id(current_user, tenant_id) or "default"
    return MonitoringService.get_latency_metrics(
        db=db,
        tenant_id=effective_tenant,
        job_type=job_type,
        hours=hours
    )


# =========================================================
# 3. ERROR ANALYTICS & TAXONOMY BREAKDOWN ENDPOINT
# =========================================================

@router.get("/errors", response_model=ErrorAnalyticsResponse, status_code=status.HTTP_200_OK)
def get_error_analytics(
    hours: int = Query(24, ge=1, le=168, description="Ventana de tiempo en horas (máximo 168h / 7 días)"),
    tenant_id: Optional[str] = Query(None, description="Filtrar por tenant (solo superadmin)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """
    Analiza y categoriza los fallos operacionales (success=False) según la taxonomía V5.4
    (TRANSIENT_INFRA, CORRUPT_INPUT, BUSINESS_RULE, STATE_INCONSISTENCY).
    """
    effective_tenant = _resolve_tenant_id(current_user, tenant_id) or "default"
    return MonitoringService.get_error_analytics(
        db=db,
        tenant_id=effective_tenant,
        hours=hours
    )


# =========================================================
# 4. RECOVERY STATUS SUMMARY ENDPOINT
# =========================================================

@router.get("/recovery", response_model=RecoverySummaryResponse, status_code=status.HTTP_200_OK)
def get_recovery_status(
    heartbeat_timeout_sec: int = Query(30, ge=5, le=300, description="Umbral de latido para jobs PROCESSING estancados"),
    queued_timeout_sec: int = Query(300, ge=30, le=3600, description="Umbral de tiempo máximo en cola QUEUED"),
    tenant_id: Optional[str] = Query(None, description="Filtrar por tenant (solo superadmin)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """
    Retorna el estado de salud de las colas y jobs estancados en PROCESSING o QUEUED
    mediante JobRepository de manera estrictamente Read-Only.
    """
    effective_tenant = _resolve_tenant_id(current_user, tenant_id) or "default"
    return MonitoringService.get_recovery_status(
        db=db,
        tenant_id=effective_tenant,
        heartbeat_timeout_sec=heartbeat_timeout_sec,
        queued_timeout_sec=queued_timeout_sec
    )


# =========================================================
# 5. TRIGGER ON-DEMAND RECOVERY RECONCILIATION
# =========================================================

@router.post("/recovery/trigger", response_model=RecoveryTriggerResponse, status_code=status.HTTP_200_OK)
def trigger_recovery_reconciliation(
    tenant_id: Optional[str] = Query(None, description="Tenant específico a reconciliar (solo superadmin)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """
    Dispara manualmente una pasada del ciclo de reconciliación y recuperación
    de jobs abandonados o estancados para el tenant objetivo.
    Registra evento inmutable en AuditLog.
    """
    effective_tenant = _resolve_tenant_id(current_user, tenant_id) or "default"
    engine = JobRecoveryEngine(db_factory=lambda: db)
    report = engine.scan_and_recover(tenant_id=effective_tenant, db=db)

    # Registrar evento de auditoría administrativa inmutable
    import json
    audit = AuditLog(
        tenant_id=effective_tenant,
        user_id=current_user.id,
        action="ADMIN_TRIGGER_RECOVERY",
        entity_type="SYSTEM_RECOVERY",
        entity_id=effective_tenant,
        status="COMPLETED",
        details=json.dumps(report.to_dict())
    )
    db.add(audit)
    db.commit()


    return RecoveryTriggerResponse(
        message="Ciclo de reconciliación y recuperación SRE completado con éxito.",
        total_scanned=report.total_scanned,
        stale_processing_count=report.stale_processing_count,
        stale_queued_count=report.stale_queued_count,
        recovered_retried=report.recovered_retried,
        marked_failed_final=report.marked_failed_final,
        marked_failed_max_retries=report.marked_failed_max_retries,
        skipped_terminal=report.skipped_terminal,
        job_details=report.job_details,
        timestamp=report.timestamp or datetime.now(timezone.utc),
        tenant_id=effective_tenant
    )
