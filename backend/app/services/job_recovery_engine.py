import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.domain import ProcessingJob
from app.services.job_repository import JobRepository

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RecoveryReport:
    """
    Reporte estructurado del ciclo de recuperación y reconciliación de jobs V5.4.
    """
    total_scanned: int = 0
    stale_processing_count: int = 0
    stale_queued_count: int = 0
    recovered_retried: int = 0
    marked_failed_final: int = 0
    marked_failed_max_retries: int = 0
    skipped_terminal: int = 0
    job_details: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=_utc_now)
    tenant_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scanned": self.total_scanned,
            "stale_processing_count": self.stale_processing_count,
            "stale_queued_count": self.stale_queued_count,
            "recovered_retried": self.recovered_retried,
            "marked_failed_final": self.marked_failed_final,
            "marked_failed_max_retries": self.marked_failed_max_retries,
            "skipped_terminal": self.skipped_terminal,
            "job_details": self.job_details,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "tenant_id": self.tenant_id
        }


class JobRecoveryEngine:
    """
    Motor de recuperación y reconciliación de jobs huérfanos / abandonados V5.4.
    Detecta anomalías en workers muertos, latidos vencidos y colas estancadas,
    aplicando políticas de retry con backoff exponencial y clasificación taxonómica de fallos.
    """

    def __init__(
        self,
        db_factory=SessionLocal,
        heartbeat_timeout_seconds: int = 30,
        queued_timeout_seconds: int = 300,
        base_backoff_sec: int = 5,
        max_retries_default: int = 3
    ):
        self.db_factory = db_factory
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.queued_timeout_seconds = queued_timeout_seconds
        self.base_backoff_sec = base_backoff_sec
        self.max_retries_default = max_retries_default

    def scan_and_recover(
        self,
        tenant_id: Optional[str] = None,
        db: Optional[Session] = None
    ) -> RecoveryReport:
        """
        Ejecuta un ciclo completo de escaneo y recuperación:
        1. Identifica jobs en PROCESSING con latido expirado (stale heartbeat).
        2. Identifica jobs en QUEUED que han superado el umbral de tiempo máximo en cola.
        3. Para cada job, aplica SELECT FOR UPDATE y clasifica según RETRYABLE vs FINAL.
        4. Reintenta con backoff exponencial o cancela definitivamente si excede max_retries o es fallo FINAL.
        """
        own_session = False
        if db is None:
            db = self.db_factory()
            own_session = True

        report = RecoveryReport(
            timestamp=_utc_now(),
            tenant_id=tenant_id
        )

        try:
            # 1. Obtener jobs abandonados en PROCESSING
            stale_processing = JobRepository.get_stale_processing_jobs(
                db=db,
                heartbeat_timeout_seconds=self.heartbeat_timeout_seconds,
                tenant_id=tenant_id
            )
            report.stale_processing_count = len(stale_processing)

            # 2. Obtener jobs estancados en QUEUED
            stale_queued = JobRepository.get_stale_queued_jobs(
                db=db,
                queued_timeout_seconds=self.queued_timeout_seconds,
                tenant_id=tenant_id
            )
            report.stale_queued_count = len(stale_queued)

            # Consolidar lista de jobs a recuperar (evitando duplicados por id)
            seen_job_ids = set()
            candidates = []

            for job in stale_processing:
                if job.id not in seen_job_ids:
                    seen_job_ids.add(job.id)
                    candidates.append((job.job_id or str(job.id), "WORKER_HEARTBEAT_TIMEOUT: Worker sin respuesta durante PROCESSING"))

            for job in stale_queued:
                if job.id not in seen_job_ids:
                    seen_job_ids.add(job.id)
                    candidates.append((job.job_id or str(job.id), "QUEUE_TIMEOUT: Job excedió tiempo máximo en cola QUEUED"))

            report.total_scanned = len(candidates)

            # 3. Procesar recuperación transaccional de cada candidato
            for job_id_str, reason in candidates:
                try:
                    is_retried, recovered_job, outcome = JobRepository.recover_and_retry_job(
                        db=db,
                        job_id=job_id_str,
                        reason=reason,
                        base_backoff_sec=self.base_backoff_sec,
                        tenant_id=tenant_id
                    )

                    detail = {
                        "job_id": job_id_str,
                        "outcome": outcome,
                        "reason": reason,
                        "is_retried": is_retried,
                        "status": recovered_job.status if recovered_job else "UNKNOWN",
                        "attempt_count": recovered_job.attempt_count if recovered_job else None,
                        "max_retries": recovered_job.max_retries if recovered_job else None,
                        "failure_classification": recovered_job.failure_classification if recovered_job else None
                    }
                    report.job_details.append(detail)

                    if outcome == "RETRY_QUEUED":
                        report.recovered_retried += 1
                        logger.info(f"[JobRecoveryEngine] Job {job_id_str} reintentado exitosamente (Intento {recovered_job.attempt_count}/{recovered_job.max_retries}).")
                    elif outcome == "FAILED_FINAL":
                        report.marked_failed_final += 1
                        logger.warning(f"[JobRecoveryEngine] Job {job_id_str} marcado como FAILED definitivo sin retry.")
                    elif outcome == "MAX_RETRIES_EXCEEDED":
                        report.marked_failed_max_retries += 1
                        logger.warning(f"[JobRecoveryEngine] Job {job_id_str} cancelado: Límite de reintentos excedido.")
                    elif outcome in ("ALREADY_COMPLETED", "ALREADY_FAILED_FINAL"):
                        report.skipped_terminal += 1

                except Exception as job_err:
                    db.rollback()
                    logger.error(f"[JobRecoveryEngine] Error recuperando job {job_id_str}: {job_err}", exc_info=True)
                    report.job_details.append({
                        "job_id": job_id_str,
                        "outcome": "ERROR",
                        "error": str(job_err)
                    })

            return report

        finally:
            if own_session:
                db.close()

    def recover_job(
        self,
        job_id: Union[str, int],
        reason: str,
        failure_classification: Optional[str] = None,
        tenant_id: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Recupera manualmente o bajo demanda un job específico.
        """
        own_session = False
        if db is None:
            db = self.db_factory()
            own_session = True

        try:
            is_retried, recovered_job, outcome = JobRepository.recover_and_retry_job(
                db=db,
                job_id=job_id,
                reason=reason,
                failure_classification=failure_classification,
                base_backoff_sec=self.base_backoff_sec,
                tenant_id=tenant_id
            )

            return {
                "job_id": str(job_id),
                "is_retried": is_retried,
                "outcome": outcome,
                "reason": reason,
                "status": recovered_job.status if recovered_job else None,
                "attempt_count": recovered_job.attempt_count if recovered_job else None,
                "max_retries": recovered_job.max_retries if recovered_job else None,
                "failure_classification": recovered_job.failure_classification if recovered_job else None
            }
        finally:
            if own_session:
                db.close()
