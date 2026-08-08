import pytest
from datetime import datetime, timezone, timedelta
from app.models.domain import (
    Tenant,
    User,
    CaseFile,
    ProcessingJob,
    ProcessingMetrics,
    WorkerHeartbeat,
    AuditLog
)
from app.services.job_repository import JobRepository
from app.services.job_recovery_engine import JobRecoveryEngine, RecoveryReport


def _utc_now():
    return datetime.now(timezone.utc)


@pytest.fixture
def recovery_fixture(db_session):
    """Fixture con configuración multi-tenant para pruebas de JobRecoveryEngine V5.4."""
    tenant_a = db_session.query(Tenant).filter(Tenant.id == "tenant_a").first()
    if not tenant_a:
        tenant_a = Tenant(id="tenant_a", name="Tenant Alfa")
        db_session.add(tenant_a)

    tenant_b = db_session.query(Tenant).filter(Tenant.id == "tenant_b").first()
    if not tenant_b:
        tenant_b = Tenant(id="tenant_b", name="Tenant Beta")
        db_session.add(tenant_b)

    user = db_session.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, email="admin@abst.com", hashed_password="pw", full_name="Admin")
        db_session.add(user)

    case_a = CaseFile(
        id=8801,
        title="Expediente Alfa",
        contract_type="BIENES",
        status="COMPARING",
        tenant_id="tenant_a",
        created_by=1
    )
    case_b = CaseFile(
        id=8802,
        title="Expediente Beta",
        contract_type="SERVICIOS",
        status="COMPARING",
        tenant_id="tenant_b",
        created_by=1
    )
    db_session.add(case_a)
    db_session.add(case_b)
    db_session.commit()

    return {
        "tenant_a": "tenant_a",
        "tenant_b": "tenant_b",
        "case_a_id": case_a.id,
        "case_b_id": case_b.id,
        "user_id": 1
    }


def test_recovery_worker_dead_during_processing(db_session, recovery_fixture):
    """
    Escenario 1: Worker muerto durante PROCESSING (latido expirado).
    El JobRecoveryEngine debe detectar el job, aplicar SELECT FOR UPDATE,
    reintentar con backoff exponencial, incrementar attempt_count y registrar AuditLog.
    """
    t_a = recovery_fixture["tenant_a"]
    c_a = recovery_fixture["case_a_id"]
    u_id = recovery_fixture["user_id"]

    # Crear job en PROCESSING con latido expirado (hace 120s)
    job = JobRepository.create_job(
        db=db_session,
        case_id=c_a,
        tenant_id=t_a,
        user_id=u_id,
        job_type="REQUIREMENT_OCR"
    )
    stale_time = _utc_now() - timedelta(seconds=120)
    job.status = "PROCESSING"
    job.worker_name = "dead_worker_pid_999@node_lost"
    job.started_at = stale_time
    job.last_heartbeat_at = stale_time
    job.attempt_count = 1
    job.max_retries = 3
    db_session.commit()

    # Ejecutar escaneo y recuperación con timeout de 30s
    engine = JobRecoveryEngine(
        heartbeat_timeout_seconds=30,
        queued_timeout_seconds=300,
        base_backoff_sec=5
    )
    report = engine.scan_and_recover(tenant_id=t_a, db=db_session)

    assert report.total_scanned == 1
    assert report.stale_processing_count == 1
    assert report.recovered_retried == 1
    assert report.marked_failed_final == 0
    assert report.marked_failed_max_retries == 0

    # Validar estado del job tras recuperación
    db_session.refresh(job)
    assert job.status == "QUEUED"
    assert job.attempt_count == 2
    assert job.worker_name is None
    assert job.last_heartbeat_at is None
    assert job.progress == 0
    assert "Intento 2/3" in job.status_message
    assert "backoff 5s" in job.status_message

    # Validar AuditLog generado
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == job.job_id,
        AuditLog.action == "JOB_RECOVERY_RETRY"
    ).first()
    assert audit is not None
    assert audit.status == "QUEUED"
    assert audit.tenant_id == t_a
    assert "backoff 5s" in audit.details


def test_recovery_stale_queued_job(db_session, recovery_fixture):
    """
    Escenario 2: Job estancado en QUEUED superando tiempo máximo de espera.
    """
    t_a = recovery_fixture["tenant_a"]
    c_a = recovery_fixture["case_a_id"]
    u_id = recovery_fixture["user_id"]

    job = JobRepository.create_job(
        db=db_session,
        case_id=c_a,
        tenant_id=t_a,
        user_id=u_id,
        job_type="QUOTATION_EXTRACTION"
    )
    job.status = "QUEUED"
    job.created_at = _utc_now() - timedelta(seconds=600)  # Creado hace 10 minutos
    db_session.commit()

    engine = JobRecoveryEngine(
        heartbeat_timeout_seconds=30,
        queued_timeout_seconds=300,
        base_backoff_sec=5
    )
    report = engine.scan_and_recover(tenant_id=t_a, db=db_session)

    assert report.stale_queued_count == 1
    assert report.recovered_retried == 1

    db_session.refresh(job)
    assert job.status == "QUEUED"
    assert job.attempt_count == 2
    assert "Intento 2/3" in job.status_message


def test_recovery_max_retries_exceeded(db_session, recovery_fixture):
    """
    Escenario 3: Job que alcanza y supera el límite max_retries.
    Debe transicionar a FAILED definitivo, registrar AuditLog y emitir ProcessingMetrics de fallo.
    """
    t_a = recovery_fixture["tenant_a"]
    c_a = recovery_fixture["case_a_id"]
    u_id = recovery_fixture["user_id"]

    job = JobRepository.create_job(
        db=db_session,
        case_id=c_a,
        tenant_id=t_a,
        user_id=u_id,
        job_type="COMPARISON_RUN"
    )
    stale_time = _utc_now() - timedelta(seconds=100)
    job.status = "PROCESSING"
    job.started_at = stale_time
    job.last_heartbeat_at = stale_time
    job.attempt_count = 3
    job.max_retries = 3
    db_session.commit()

    engine = JobRecoveryEngine(
        heartbeat_timeout_seconds=30,
        queued_timeout_seconds=300,
        base_backoff_sec=5
    )
    report = engine.scan_and_recover(tenant_id=t_a, db=db_session)

    assert report.marked_failed_max_retries == 1
    assert report.recovered_retried == 0

    db_session.refresh(job)
    assert job.status == "FAILED"
    assert job.progress == 100
    assert job.failure_classification == "FINAL"
    assert "Límite de reintentos alcanzado" in job.error_message

    # Validar AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == job.job_id,
        AuditLog.action == "JOB_RECOVERY_MAX_RETRIES_EXCEEDED"
    ).first()
    assert audit is not None
    assert audit.status == "FAILED"

    # Validar ProcessingMetrics
    metric = db_session.query(ProcessingMetrics).filter(
        ProcessingMetrics.job_id == job.job_id
    ).first()
    assert metric is not None
    assert metric.success is False
    assert metric.error_code == "MAX_RETRIES_EXCEEDED"


def test_recovery_final_error_no_retry(db_session, recovery_fixture):
    """
    Escenario 4: Error clasificado como FINAL (ej. PDF corrupto o validación de negocio).
    No debe reintentarse; debe pasar directamente a FAILED con métrica y auditoría.
    """
    t_a = recovery_fixture["tenant_a"]
    c_a = recovery_fixture["case_a_id"]
    u_id = recovery_fixture["user_id"]

    job = JobRepository.create_job(
        db=db_session,
        case_id=c_a,
        tenant_id=t_a,
        user_id=u_id,
        job_type="QUOTATION_EXTRACTION"
    )
    job.status = "PROCESSING"
    job.attempt_count = 1
    job.max_retries = 3
    db_session.commit()

    engine = JobRecoveryEngine()
    result = engine.recover_job(
        job_id=job.job_id,
        reason="CORRUPT_PDF: El archivo PDF proporcionado está dañado y no se puede leer",
        failure_classification="FINAL",
        tenant_id=t_a,
        db=db_session
    )

    assert result["is_retried"] is False
    assert result["outcome"] == "FAILED_FINAL"
    assert result["status"] == "FAILED"

    db_session.refresh(job)
    assert job.status == "FAILED"
    assert job.attempt_count == 1  # No se incrementó
    assert job.failure_classification == "FINAL"

    # Validar AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == job.job_id,
        AuditLog.action == "JOB_RECOVERY_FAILED_FINAL"
    ).first()
    assert audit is not None
    assert audit.status == "FAILED"
    assert "CORRUPT_PDF" in audit.details


def test_recovery_multi_tenant_isolation(db_session, recovery_fixture):
    """
    Escenario 5: Aislamiento multi-tenant.
    Un escaneo filtrado por tenant_a NO debe alterar ni tocar jobs de tenant_b.
    """
    t_a = recovery_fixture["tenant_a"]
    t_b = recovery_fixture["tenant_b"]
    c_a = recovery_fixture["case_a_id"]
    c_b = recovery_fixture["case_b_id"]
    u_id = recovery_fixture["user_id"]

    stale_time = _utc_now() - timedelta(seconds=150)

    # Job estancado en Tenant A
    job_a = JobRepository.create_job(
        db=db_session,
        case_id=c_a,
        tenant_id=t_a,
        user_id=u_id,
        job_type="REQUIREMENT_OCR"
    )
    job_a.status = "PROCESSING"
    job_a.last_heartbeat_at = stale_time
    job_a.started_at = stale_time

    # Job estancado en Tenant B
    job_b = JobRepository.create_job(
        db=db_session,
        case_id=c_b,
        tenant_id=t_b,
        user_id=u_id,
        job_type="REQUIREMENT_OCR"
    )
    job_b.status = "PROCESSING"
    job_b.last_heartbeat_at = stale_time
    job_b.started_at = stale_time
    db_session.commit()

    engine = JobRecoveryEngine(heartbeat_timeout_seconds=30)

    # Recuperar ÚNICAMENTE Tenant A
    report_a = engine.scan_and_recover(tenant_id=t_a, db=db_session)
    assert report_a.total_scanned == 1
    assert report_a.recovered_retried == 1

    # Validar que Job A se recuperó a QUEUED
    db_session.refresh(job_a)
    assert job_a.status == "QUEUED"
    assert job_a.attempt_count == 2

    # Validar que Job B permanece inalterado en PROCESSING
    db_session.refresh(job_b)
    assert job_b.status == "PROCESSING"
    assert job_b.attempt_count == 1
    assert job_b.last_heartbeat_at == stale_time


def test_recovery_exponential_backoff_intervals(db_session, recovery_fixture):
    """
    Escenario 6: Validación de backoff exponencial en sucesivos reintentos.
    attempt 1 -> backoff 5s
    attempt 2 -> backoff 10s
    """
    t_a = recovery_fixture["tenant_a"]
    c_a = recovery_fixture["case_a_id"]
    u_id = recovery_fixture["user_id"]

    job = JobRepository.create_job(
        db=db_session,
        case_id=c_a,
        tenant_id=t_a,
        user_id=u_id,
        job_type="QUOTATION_EXTRACTION"
    )
    job.attempt_count = 1
    job.max_retries = 4
    db_session.commit()

    # Reintento 1 -> pasa a attempt 2 con backoff 5 * (2**0) = 5s
    is_retried, _, outcome = JobRepository.recover_and_retry_job(
        db=db_session,
        job_id=job.job_id,
        reason="INFRASTRUCTURE_TIMEOUT: Redis socket timeout",
        base_backoff_sec=5
    )
    assert is_retried is True
    assert job.attempt_count == 2
    assert "backoff 5s" in job.status_message

    # Reintento 2 -> pasa a attempt 3 con backoff 5 * (2**1) = 10s
    is_retried, _, outcome = JobRepository.recover_and_retry_job(
        db=db_session,
        job_id=job.job_id,
        reason="INFRASTRUCTURE_TIMEOUT: DB connection drop",
        base_backoff_sec=5
    )
    assert is_retried is True
    assert job.attempt_count == 3
    assert "backoff 10s" in job.status_message
