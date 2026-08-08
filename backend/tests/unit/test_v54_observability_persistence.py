import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.domain import (
    CaseFile,
    Tenant,
    User,
    ProcessingJob,
    ProcessingMetrics,
    WorkerHeartbeat
)


@pytest.fixture
def db_session_setup(db_session: Session):
    """Fixture que asegura datos base de Tenant, User y CaseFile."""
    tenant = db_session.query(Tenant).filter(Tenant.id == "mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant Test")
        db_session.add(tenant)
        db_session.commit()

    user = db_session.query(User).filter(User.username == "test_obs_user").first()
    if not user:
        user = User(
            username="test_obs_user",
            password_hash="fake_hash",
            role="ADMIN",
            tenant_id="mega_tenant",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    case = db_session.query(CaseFile).filter(CaseFile.id == 9991).first()
    if not case:
        case = CaseFile(
            id=9991,
            title="Expediente Test Observabilidad",
            contract_type="BIEN",
            tenant_id="mega_tenant",
            created_by=user.id,
            status="CREATED"
        )
        db_session.add(case)
        db_session.commit()
        db_session.refresh(case)

    return {"tenant": tenant, "user": user, "case": case}


def test_processing_job_v54_extended_fields(db_session: Session, db_session_setup):
    """Valida los nuevos campos de resiliencia en ProcessingJob."""
    case = db_session_setup["case"]
    user = db_session_setup["user"]

    job = ProcessingJob(
        job_id="job_obs_test_001",
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=user.id,
        job_type="QUOTATION_EXTRACTION",
        worker_type="quotation_worker",
        worker_name="worker_node_1@host_alpha",
        status="PROCESSING",
        progress=45,
        attempt_count=2,
        max_retries=5,
        failure_classification="RETRYABLE",
        last_heartbeat_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.id is not None
    assert job.job_id == "job_obs_test_001"
    assert job.attempt_count == 2
    assert job.max_retries == 5
    assert job.failure_classification == "RETRYABLE"
    assert job.worker_name == "worker_node_1@host_alpha"
    assert job.last_heartbeat_at is not None


def test_processing_metrics_creation_and_fk(db_session: Session, db_session_setup):
    """Valida la creación y relaciones FK de ProcessingMetrics."""
    case = db_session_setup["case"]
    user = db_session_setup["user"]

    # Crear job padre
    job = ProcessingJob(
        job_id="job_metric_test_002",
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=user.id,
        job_type="COMPARISON_RUN",
        status="READY",
        progress=100,
        worker_name="comparison_worker_pid_123"
    )
    db_session.add(job)
    db_session.commit()

    # Crear métrica asociada
    metric = ProcessingMetrics(
        job_id="job_metric_test_002",
        tenant_id="mega_tenant",
        case_id=case.id,
        job_type="COMPARISON_RUN",
        queue_time_ms=1250,
        processing_time_ms=4500,
        total_time_ms=5750,
        worker_name="comparison_worker_pid_123",
        pages_processed=12,
        success=True,
        error_code=None,
        error_category=None
    )
    db_session.add(metric)
    db_session.commit()
    db_session.refresh(metric)

    assert metric.id is not None
    assert metric.job_id == "job_metric_test_002"
    assert metric.queue_time_ms == 1250
    assert metric.processing_time_ms == 4500
    assert metric.total_time_ms == 5750
    assert metric.pages_processed == 12
    assert metric.success is True
    assert metric.created_at is not None


def test_processing_metrics_cascade_delete(db_session: Session, db_session_setup):
    """Valida que la eliminación de ProcessingJob cascadee hacia ProcessingMetrics."""
    case = db_session_setup["case"]
    user = db_session_setup["user"]

    job = ProcessingJob(
        job_id="job_cascade_test_003",
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=user.id,
        job_type="REQUIREMENT_OCR",
        status="FAILED"
    )
    db_session.add(job)
    db_session.commit()

    metric = ProcessingMetrics(
        job_id="job_cascade_test_003",
        tenant_id="mega_tenant",
        case_id=case.id,
        job_type="REQUIREMENT_OCR",
        queue_time_ms=500,
        processing_time_ms=1200,
        total_time_ms=1700,
        worker_name="ocr_worker_01",
        pages_processed=3,
        success=False,
        error_code="CORRUPT_PDF",
        error_category="CORRUPT_INPUT"
    )
    db_session.add(metric)
    db_session.commit()

    # Verificar que existe
    found_metric = db_session.query(ProcessingMetrics).filter(ProcessingMetrics.job_id == "job_cascade_test_003").first()
    assert found_metric is not None
    assert found_metric.error_code == "CORRUPT_PDF"

    # Eliminar job padre
    db_session.delete(job)
    db_session.commit()

    # Validar que la métrica fue eliminada por CASCADE FK
    found_metric_after = db_session.query(ProcessingMetrics).filter(ProcessingMetrics.job_id == "job_cascade_test_003").first()
    assert found_metric_after is None


def test_worker_heartbeat_lifecycle(db_session: Session, db_session_setup):
    """Valida el ciclo de vida y actualización de WorkerHeartbeat."""
    worker = WorkerHeartbeat(
        worker_name="worker_ocr_node_5@cluster",
        worker_type="OCR_WORKER",
        hostname="cluster-node-5.internal",
        status="IDLE",
        current_job_id=None,
        tenant_id="mega_tenant",
        last_seen=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc)
    )
    db_session.add(worker)
    db_session.commit()
    db_session.refresh(worker)

    assert worker.worker_name == "worker_ocr_node_5@cluster"
    assert worker.status == "IDLE"
    assert worker.current_job_id is None

    # Simular asignación de tarea (BUSY)
    worker.status = "BUSY"
    worker.current_job_id = "job_metric_test_002"
    worker.last_seen = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(worker)

    assert worker.status == "BUSY"
    assert worker.current_job_id == "job_metric_test_002"


def test_multi_tenant_metrics_isolation(db_session: Session, db_session_setup):
    """Valida el aislamiento de métricas por tenant."""
    case = db_session_setup["case"]
    user = db_session_setup["user"]

    # Crear otro tenant
    tenant_b = db_session.query(Tenant).filter(Tenant.id == "tenant_beta").first()
    if not tenant_b:
        tenant_b = Tenant(id="tenant_beta", name="Tenant Beta")
        db_session.add(tenant_b)
        db_session.commit()

    job_a = ProcessingJob(job_id="job_tenant_a", case_id=case.id, tenant_id="mega_tenant", user_id=user.id, job_type="QUOTATION_EXTRACTION")
    job_b = ProcessingJob(job_id="job_tenant_b", case_id=case.id, tenant_id="tenant_beta", user_id=user.id, job_type="QUOTATION_EXTRACTION")
    db_session.add_all([job_a, job_b])
    db_session.commit()

    metric_a = ProcessingMetrics(job_id="job_tenant_a", tenant_id="mega_tenant", case_id=case.id, job_type="QUOTATION_EXTRACTION", queue_time_ms=100, processing_time_ms=200, total_time_ms=300, worker_name="w1", success=True)
    metric_b = ProcessingMetrics(job_id="job_tenant_b", tenant_id="tenant_beta", case_id=case.id, job_type="QUOTATION_EXTRACTION", queue_time_ms=150, processing_time_ms=250, total_time_ms=400, worker_name="w2", success=True)
    db_session.add_all([metric_a, metric_b])
    db_session.commit()

    metrics_tenant_a = db_session.query(ProcessingMetrics).filter(ProcessingMetrics.tenant_id == "mega_tenant").all()
    metrics_tenant_b = db_session.query(ProcessingMetrics).filter(ProcessingMetrics.tenant_id == "tenant_beta").all()

    assert any(m.job_id == "job_tenant_a" for m in metrics_tenant_a)
    assert not any(m.job_id == "job_tenant_b" for m in metrics_tenant_a)
    assert any(m.job_id == "job_tenant_b" for m in metrics_tenant_b)
    assert not any(m.job_id == "job_tenant_a" for m in metrics_tenant_b)
