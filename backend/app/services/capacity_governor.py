import logging
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.domain import ProcessingJob
from app.core.config import settings

logger = logging.getLogger(__name__)


class TenantCapacityGovernor:
    """
    Gobernador de Capacidad y Concurrencia Multi-Tenant (Fase 7.3).
    
    Principios de Diseño:
    1. PostgreSQL es la única fuente de verdad (SSOT): NO almacena estado en memoria ni en Redis.
    2. Utiliza índices compuestos (tenant_id, status) y (status) para COUNT(*) en tiempo sub-milisegundo.
    3. Fair Sharing & Aislamiento Noisy Neighbor:
       - Impide que un solo tenant monopolice los workers del sistema.
       - Aplica cuotas máximas de concurrencia por tenant (TENANT_MAX_CONCURRENT_PROCESSING_JOBS).
       - Aplica límites globales del sistema (SYSTEM_MAX_CONCURRENT_PROCESSING_JOBS).
    4. Política de Encolamiento No Destructiva:
       - Cuando se supera la cuota, los jobs se mantienen en estado 'QUEUED'.
       - NUNCA se rechaza ni descarta una solicitud de procesamiento.
    """

    @staticmethod
    def get_tenant_active_jobs_count(db: Session, tenant_id: str) -> int:
        """
        Calcula el número de jobs en estado activo ('PROCESSING', 'started') para un tenant específico.
        Aprovecha el índice compuesto idx_processing_jobs_tenant_status.
        """
        count = (
            db.query(func.count(ProcessingJob.id))
            .filter(
                ProcessingJob.tenant_id == tenant_id,
                ProcessingJob.status.in_(["PROCESSING", "started"])
            )
            .scalar()
        )
        return int(count or 0)

    @staticmethod
    def get_system_active_jobs_count(db: Session) -> int:
        """
        Calcula el número total de jobs en estado activo ('PROCESSING', 'started') en todo el cluster.
        Aprovecha el índice idx_processing_jobs_status_created.
        """
        count = (
            db.query(func.count(ProcessingJob.id))
            .filter(ProcessingJob.status.in_(["PROCESSING", "started"]))
            .scalar()
        )
        return int(count or 0)

    @staticmethod
    def get_tenant_queued_jobs_count(db: Session, tenant_id: str) -> int:
        """
        Calcula el número de jobs en cola ('QUEUED', 'pending') para un tenant específico.
        """
        count = (
            db.query(func.count(ProcessingJob.id))
            .filter(
                ProcessingJob.tenant_id == tenant_id,
                ProcessingJob.status.in_(["QUEUED", "pending"])
            )
            .scalar()
        )
        return int(count or 0)

    @classmethod
    def evaluate_capacity(
        cls,
        db: Session,
        tenant_id: str,
        max_tenant_concurrency: Optional[int] = None,
        max_system_concurrency: Optional[int] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evalúa si un tenant tiene capacidad para despachar un nuevo job a estado 'PROCESSING'.
        
        Retorna:
          (can_dispatch: bool, reason: str, metrics: Dict[str, Any])
        """
        if not settings.CAPACITY_GOVERNOR_ENABLED:
            return True, "CAPACITY_GOVERNOR_DISABLED", {
                "tenant_active": 0,
                "tenant_limit": -1,
                "system_active": 0,
                "system_limit": -1
            }

        tenant_limit = (
            max_tenant_concurrency
            if max_tenant_concurrency is not None
            else settings.TENANT_MAX_CONCURRENT_PROCESSING_JOBS
        )
        system_limit = (
            max_system_concurrency
            if max_system_concurrency is not None
            else settings.SYSTEM_MAX_CONCURRENT_PROCESSING_JOBS
        )

        tenant_active = cls.get_tenant_active_jobs_count(db, tenant_id)
        system_active = cls.get_system_active_jobs_count(db)

        metrics = {
            "tenant_id": tenant_id,
            "tenant_active": tenant_active,
            "tenant_limit": tenant_limit,
            "system_active": system_active,
            "system_limit": system_limit
        }

        # 1. Comprobación de cuota por Tenant (Noisy Neighbor Isolation)
        if tenant_active >= tenant_limit:
            logger.info(
                f"[CAPACITY_GOVERNOR] Tenant '{tenant_id}' ha alcanzado su cuota concurrente: "
                f"{tenant_active}/{tenant_limit}. Manteniendo job en QUEUED."
            )
            return False, "TENANT_QUOTA_EXCEEDED", metrics

        # 2. Comprobación de capacidad global del sistema
        if system_active >= system_limit:
            logger.warning(
                f"[CAPACITY_GOVERNOR] Capacidad global del sistema alcanzada: "
                f"{system_active}/{system_limit}. Manteniendo job en QUEUED."
            )
            return False, "SYSTEM_CAPACITY_EXCEEDED", metrics

        return True, "CAPACITY_AVAILABLE", metrics

    @classmethod
    def can_dispatch(
        cls,
        db: Session,
        tenant_id: str,
        max_tenant_concurrency: Optional[int] = None,
        max_system_concurrency: Optional[int] = None
    ) -> bool:
        """
        Método booleano simplificado para validación rápida en workers o JobRepository.
        """
        can_run, _, _ = cls.evaluate_capacity(
            db=db,
            tenant_id=tenant_id,
            max_tenant_concurrency=max_tenant_concurrency,
            max_system_concurrency=max_system_concurrency
        )
        return can_run

    LOCK_NAMESPACE_GLOBAL: int = 1001
    LOCK_NAMESPACE_TENANT: int = 1002

    @classmethod
    def find_next_fair_claimable_job(
        cls,
        db: Session,
        max_tenant_concurrency: Optional[int] = None,
        max_system_concurrency: Optional[int] = None
    ) -> Optional[ProcessingJob]:
        """
        Selecciona de forma justa (Fair Sharing) el siguiente job encolado elegible para ser procesado.
        
        Política:
        1. Comprueba la capacidad global del cluster.
        2. Identifica tenants con capacidad disponible (excluye tenants con active_jobs >= quota).
        3. Ordena los jobs elegibles por antigüedad (created_at ASC) priorizando el mayor tiempo de espera.
        4. Adquiere el lock de fila con FOR UPDATE SKIP LOCKED evitando contención entre workers.
        """
        if not settings.CAPACITY_GOVERNOR_ENABLED:
            return (
                db.query(ProcessingJob)
                .filter(ProcessingJob.status.in_(["QUEUED", "pending"]))
                .order_by(ProcessingJob.created_at.asc())
                .with_for_update(skip_locked=True)
                .first()
            )

        system_limit = (
            max_system_concurrency
            if max_system_concurrency is not None
            else settings.SYSTEM_MAX_CONCURRENT_PROCESSING_JOBS
        )
        tenant_limit = (
            max_tenant_concurrency
            if max_tenant_concurrency is not None
            else settings.TENANT_MAX_CONCURRENT_PROCESSING_JOBS
        )

        # 1. Verificar si el sistema global ha alcanzado su capacidad máxima
        system_active = cls.get_system_active_jobs_count(db)
        if system_active >= system_limit:
            return None

        # 2. Identificar tenants saturados que han copado su cuota individual
        active_counts = (
            db.query(
                ProcessingJob.tenant_id,
                func.count(ProcessingJob.id).label("active_count")
            )
            .filter(ProcessingJob.status.in_(["PROCESSING", "started"]))
            .group_by(ProcessingJob.tenant_id)
            .all()
        )
        saturated_tenants = {row[0] for row in active_counts if row[1] >= tenant_limit and row[0] is not None}

        # 3. Consultar el job QUEUED más antiguo perteneciente a un tenant elegible (con SKIP LOCKED)
        query = db.query(ProcessingJob).filter(ProcessingJob.status.in_(["QUEUED", "pending"]))
        if saturated_tenants:
            query = query.filter(~ProcessingJob.tenant_id.in_(saturated_tenants))

        candidate = (
            query.order_by(ProcessingJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        return candidate

    @classmethod
    def get_capacity_report(cls, db: Session, tenant_ids: Optional[list] = None) -> Dict[str, Any]:
        """
        Genera un reporte consolidado de uso de capacidad para la API de observabilidad y SRE Dashboard.
        """
        system_active = cls.get_system_active_jobs_count(db)
        
        tenants_data = {}
        if tenant_ids:
            for tid in tenant_ids:
                tenants_data[tid] = {
                    "active_jobs": cls.get_tenant_active_jobs_count(db, tid),
                    "queued_jobs": cls.get_tenant_queued_jobs_count(db, tid),
                    "max_concurrent_limit": settings.TENANT_MAX_CONCURRENT_PROCESSING_JOBS
                }

        return {
            "system": {
                "active_jobs": system_active,
                "max_system_limit": settings.SYSTEM_MAX_CONCURRENT_PROCESSING_JOBS,
                "utilization_pct": round((system_active / max(1, settings.SYSTEM_MAX_CONCURRENT_PROCESSING_JOBS)) * 100, 2),
                "governor_enabled": settings.CAPACITY_GOVERNOR_ENABLED
            },
            "tenants": tenants_data
        }
