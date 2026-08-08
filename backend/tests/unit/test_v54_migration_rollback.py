import os
from alembic.config import Config
from alembic import command
from sqlalchemy.orm import Session
from app.models.domain import ProcessingJob, Tenant


def test_alembic_migration_and_rollback_cycle():
    """Valida el ciclo completo de upgrade y downgrade de Alembic sin romper la base de datos."""
    alembic_cfg = Config("alembic.ini")
    test_db_url = os.environ.get("DATABASE_URL")
    if test_db_url:
        alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # 1. Downgrade a la versión anterior (f1a2b3c4d5e6)
    command.downgrade(alembic_cfg, "f1a2b3c4d5e6")

    # 2. Re-upgrade a head (b2c3d4e5f6a7)
    command.upgrade(alembic_cfg, "head")


def test_v53_legacy_data_compatibility(db_session: Session):
    """Valida que un ProcessingJob creado con el esquema V5.3 (valores por defecto) funciona sin problemas."""
    tenant = db_session.query(Tenant).filter(Tenant.id == "mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        db_session.commit()

    # Insertar un job simulando registro estilo V5.3 (sin pasar nuevos campos explícitos)
    legacy_job = ProcessingJob(
        job_id="job_v53_legacy_compat",
        tenant_id="mega_tenant",
        job_type="QUOTATION_EXTRACTION",
        status="QUEUED",
        progress=0
    )
    db_session.add(legacy_job)
    db_session.commit()
    db_session.refresh(legacy_job)

    # Verificar que los nuevos campos V5.4 adoptan sus defaults del servidor/modelo
    assert legacy_job.attempt_count == 1
    assert legacy_job.max_retries == 3
    assert legacy_job.failure_classification is None
    assert legacy_job.last_heartbeat_at is None
    assert legacy_job.worker_name is None
