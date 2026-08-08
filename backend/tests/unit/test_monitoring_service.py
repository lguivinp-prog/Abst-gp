import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.models.domain import WorkerHeartbeat, ProcessingMetrics, ProcessingJob, Tenant
from app.services.monitoring_service import MonitoringService
from app.services.job_repository import JobRepository


def _utc_now():
    return datetime.now(timezone.utc)


@pytest.fixture
def setup_tenants(db_session: Session):
    """Crea tenants únicos de prueba para verificar aislamiento multi-tenant."""
    uid = uuid.uuid4().hex[:8]
    tenant_a_id = f"t_mon_a_{uid}"
    tenant_b_id = f"t_mon_b_{uid}"

    tenant_a = Tenant(id=tenant_a_id, name=f"Tenant Mon Alpha {uid}")
    tenant_b = Tenant(id=tenant_b_id, name=f"Tenant Mon Beta {uid}")
    db_session.add_all([tenant_a, tenant_b])
    db_session.commit()
    return tenant_a, tenant_b


def test_monitoring_worker_status_active_unresponsive_offline(db_session: Session, setup_tenants):
    """
    Valida la clasificación dinámica de workers:
    - Activo (IDLE/BUSY con latido reciente) -> is_healthy=True
    - Sin latido (>30s) -> clasificado dinámicamente como UNRESPONSIVE, is_healthy=False
    - OFFLINE -> clasificado como OFFLINE, is_healthy=False
    - Verifica que NO se mute la BD (Read-Only).
    """
    tenant_a, _ = setup_tenants
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    w_idle_name = f"w_idle_{uid}"
    w_busy_name = f"w_busy_{uid}"
    w_unresp_name = f"w_unresp_{uid}"
    w_off_name = f"w_off_{uid}"

    # 1. Worker Activo IDLE (latido hace 5s)
    w_idle = WorkerHeartbeat(
        worker_name=w_idle_name,
        worker_type="abst_worker",
        hostname="node-1",
        status="IDLE",
        tenant_id=tenant_a.id,
        last_seen=now - timedelta(seconds=5),
        started_at=now - timedelta(hours=2)
    )

    # 2. Worker Activo BUSY (latido hace 2s)
    w_busy = WorkerHeartbeat(
        worker_name=w_busy_name,
        worker_type="abst_worker_ocr",
        hostname="node-2",
        status="BUSY",
        current_job_id=f"job-active-{uid}",
        tenant_id=tenant_a.id,
        last_seen=now - timedelta(seconds=2),
        started_at=now - timedelta(hours=1)
    )

    # 3. Worker UNRESPONSIVE (status BUSY pero sin latido desde hace 45s)
    w_unresp = WorkerHeartbeat(
        worker_name=w_unresp_name,
        worker_type="abst_worker",
        hostname="node-3",
        status="BUSY",
        current_job_id=f"job-stuck-{uid}",
        tenant_id=tenant_a.id,
        last_seen=now - timedelta(seconds=45),
        started_at=now - timedelta(hours=3)
    )

    # 4. Worker OFFLINE
    w_offline = WorkerHeartbeat(
        worker_name=w_off_name,
        worker_type="abst_worker",
        hostname="node-4",
        status="OFFLINE",
        tenant_id=tenant_a.id,
        last_seen=now - timedelta(hours=5),
        started_at=now - timedelta(hours=10)
    )

    db_session.add_all([w_idle, w_busy, w_unresp, w_offline])
    db_session.commit()

    # Ejecutar consulta de estado acotada al tenant de prueba
    report = MonitoringService.get_workers_status(
        db=db_session,
        tenant_id=tenant_a.id,
        heartbeat_threshold_sec=30
    )

    assert report.total_workers == 4
    assert report.total_active == 2  # idle + busy
    assert report.total_busy == 1
    assert report.total_unresponsive == 1
    assert report.total_offline == 1

    # Verificar detalles individuales
    worker_map = {w.worker_name: w for w in report.workers}

    assert worker_map[w_idle_name].status == "IDLE"
    assert worker_map[w_idle_name].is_healthy is True

    assert worker_map[w_busy_name].status == "BUSY"
    assert worker_map[w_busy_name].is_healthy is True
    assert worker_map[w_busy_name].current_job_id == f"job-active-{uid}"

    assert worker_map[w_unresp_name].status == "UNRESPONSIVE"
    assert worker_map[w_unresp_name].is_healthy is False

    assert worker_map[w_off_name].status == "OFFLINE"
    assert worker_map[w_off_name].is_healthy is False

    # Verificar que el registro en BD NO fue mutado (Read-Only)
    db_w_unresp = db_session.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_name == w_unresp_name).first()
    assert db_w_unresp.status == "BUSY"


def test_monitoring_latency_percentiles_calculation(db_session: Session, setup_tenants):
    """
    Valida el cálculo estadístico de p50, p95, p99, promedio, min y max
    con muestras controladas en ProcessingMetrics.
    """
    tenant_a, _ = setup_tenants
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    # Insertar 100 métricas controladas para QUOTATION_EXTRACTION con latencias de 100ms a 10000ms (paso 100ms)
    latencies = [i * 100 for i in range(1, 101)]  # 100, 200, ..., 10000 ms
    for idx, lat in enumerate(latencies):
        j_id = f"job-lat-{uid}-{idx}"
        job = ProcessingJob(
            job_id=j_id,
            tenant_id=tenant_a.id,
            job_type="QUOTATION_EXTRACTION",
            status="READY"
        )
        db_session.add(job)
        metric = ProcessingMetrics(
            job_id=j_id,
            tenant_id=tenant_a.id,
            job_type="QUOTATION_EXTRACTION",
            total_time_ms=lat,
            processing_time_ms=lat,
            queue_time_ms=0,
            success=True,
            created_at=now - timedelta(minutes=10)
        )
        db_session.add(metric)

    db_session.commit()

    report = MonitoringService.get_latency_metrics(
        db=db_session,
        tenant_id=tenant_a.id,
        job_type="QUOTATION_EXTRACTION",
        hours=24
    )

    assert report.total_samples == 100
    assert report.global_metrics.sample_count == 100
    assert report.global_metrics.min_ms == 100
    assert report.global_metrics.max_ms == 10000
    assert report.global_metrics.avg_ms == 5050.0

    # p50 esperado alrededor de 5050ms
    assert 5000 <= report.global_metrics.p50_ms <= 5100
    # p95 esperado alrededor de 9505ms
    assert 9400 <= report.global_metrics.p95_ms <= 9600
    # p99 esperado alrededor de 9901ms
    assert 9800 <= report.global_metrics.p99_ms <= 10000


def test_monitoring_error_analytics_taxonomy_grouping(db_session: Session, setup_tenants):
    """
    Valida la matriz de errores agrupada por categoría, código y tipo de job.
    """
    tenant_a, _ = setup_tenants
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    # 1. 10 jobs exitosos
    for i in range(10):
        j_id = f"job-succ-{uid}-{i}"
        pj = ProcessingJob(job_id=j_id, tenant_id=tenant_a.id, job_type="REQUIREMENT_OCR", status="READY")
        db_session.add(pj)
        m = ProcessingMetrics(job_id=j_id, tenant_id=tenant_a.id, job_type="REQUIREMENT_OCR", total_time_ms=500, success=True, created_at=now - timedelta(minutes=5))
        db_session.add(m)

    # 2. 3 jobs fallidos por TRANSIENT_INFRA (REDIS_TIMEOUT)
    for i in range(3):
        j_id = f"job-err-infra-{uid}-{i}"
        pj = ProcessingJob(job_id=j_id, tenant_id=tenant_a.id, job_type="REQUIREMENT_OCR", status="FAILED")
        db_session.add(pj)
        m = ProcessingMetrics(
            job_id=j_id,
            tenant_id=tenant_a.id,
            job_type="REQUIREMENT_OCR",
            total_time_ms=1000,
            success=False,
            error_code="REDIS_TIMEOUT",
            error_category="TRANSIENT_INFRA",
            created_at=now - timedelta(minutes=5)
        )
        db_session.add(m)

    # 3. 2 jobs fallidos por CORRUPT_INPUT (PDF_PARSE_ERROR)
    for i in range(2):
        j_id = f"job-err-pdf-{uid}-{i}"
        pj = ProcessingJob(job_id=j_id, tenant_id=tenant_a.id, job_type="QUOTATION_EXTRACTION", status="FAILED")
        db_session.add(pj)
        m = ProcessingMetrics(
            job_id=j_id,
            tenant_id=tenant_a.id,
            job_type="QUOTATION_EXTRACTION",
            total_time_ms=800,
            success=False,
            error_code="PDF_PARSE_ERROR",
            error_category="CORRUPT_INPUT",
            created_at=now - timedelta(minutes=5)
        )
        db_session.add(m)

    db_session.commit()

    analytics = MonitoringService.get_error_analytics(
        db=db_session,
        tenant_id=tenant_a.id,
        hours=24
    )

    assert analytics.total_jobs == 15
    assert analytics.failed_jobs == 5
    assert analytics.failure_rate_percent == 33.33

    assert analytics.errors_by_category["TRANSIENT_INFRA"] == 3
    assert analytics.errors_by_category["CORRUPT_INPUT"] == 2

    assert analytics.errors_by_code["REDIS_TIMEOUT"] == 3
    assert analytics.errors_by_code["PDF_PARSE_ERROR"] == 2

    assert analytics.errors_by_job_type["REQUIREMENT_OCR"] == 3
    assert analytics.errors_by_job_type["QUOTATION_EXTRACTION"] == 2

    assert len(analytics.error_details) == 2
    assert analytics.error_details[0].count == 3
    assert analytics.error_details[0].percentage == 60.0
    assert analytics.error_details[1].count == 2
    assert analytics.error_details[1].percentage == 40.0


def test_monitoring_multi_tenant_strict_isolation(db_session: Session, setup_tenants):
    """
    Garantiza que las métricas de un tenant nunca se filtren al consultar otro tenant.
    """
    tenant_a, tenant_b = setup_tenants
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    # Métrica en Tenant Alpha
    j_a = f"job-tenant-alpha-{uid}"
    pj_a = ProcessingJob(job_id=j_a, tenant_id=tenant_a.id, job_type="COMPARISON_RUN", status="READY")
    db_session.add(pj_a)
    m_a = ProcessingMetrics(
        job_id=j_a,
        tenant_id=tenant_a.id,
        job_type="COMPARISON_RUN",
        total_time_ms=5000,
        success=True,
        created_at=now - timedelta(minutes=2)
    )
    db_session.add(m_a)

    # Métrica fallida en Tenant Beta
    j_b = f"job-tenant-beta-{uid}"
    pj_b = ProcessingJob(job_id=j_b, tenant_id=tenant_b.id, job_type="COMPARISON_RUN", status="FAILED")
    db_session.add(pj_b)
    m_b = ProcessingMetrics(
        job_id=j_b,
        tenant_id=tenant_b.id,
        job_type="COMPARISON_RUN",
        total_time_ms=1000,
        success=False,
        error_code="BUSINESS_RULE_VIOLATION",
        error_category="BUSINESS_RULE",
        created_at=now - timedelta(minutes=2)
    )
    db_session.add(m_b)

    db_session.commit()

    # Consulta para Tenant Alpha
    lat_a = MonitoringService.get_latency_metrics(db=db_session, tenant_id=tenant_a.id, hours=24)
    err_a = MonitoringService.get_error_analytics(db=db_session, tenant_id=tenant_a.id, hours=24)

    assert lat_a.total_samples == 1
    assert err_a.total_jobs == 1
    assert err_a.failed_jobs == 0
    assert err_a.failure_rate_percent == 0.0

    # Consulta para Tenant Beta
    lat_b = MonitoringService.get_latency_metrics(db=db_session, tenant_id=tenant_b.id, hours=24)
    err_b = MonitoringService.get_error_analytics(db=db_session, tenant_id=tenant_b.id, hours=24)

    assert lat_b.total_samples == 1
    assert err_b.total_jobs == 1
    assert err_b.failed_jobs == 1
    assert err_b.failure_rate_percent == 100.0
    assert "BUSINESS_RULE" in err_b.errors_by_category


def test_monitoring_recovery_status_summary(db_session: Session, setup_tenants):
    """
    Valida la inspección de jobs en cola estancados y jobs en procesamiento sin latido
    sin alterar el estado de la base de datos.
    """
    tenant_a, _ = setup_tenants
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    job_proc_id = f"job-stuck-proc-{uid}"
    job_queue_id = f"job-stuck-queue-{uid}"

    # 1. Job estancado en PROCESSING (sin latido hace 120s)
    job_proc = ProcessingJob(
        job_id=job_proc_id,
        tenant_id=tenant_a.id,
        job_type="REQUIREMENT_OCR",
        status="PROCESSING",
        last_heartbeat_at=now - timedelta(seconds=120),
        started_at=now - timedelta(seconds=180),
        attempt_count=1,
        max_retries=3
    )

    # 2. Job estancado en QUEUED (creado hace 600s)
    job_queued = ProcessingJob(
        job_id=job_queue_id,
        tenant_id=tenant_a.id,
        job_type="QUOTATION_EXTRACTION",
        status="QUEUED",
        created_at=now - timedelta(seconds=600),
        attempt_count=1,
        max_retries=3
    )

    db_session.add_all([job_proc, job_queued])
    db_session.commit()

    recovery_summary = MonitoringService.get_recovery_status(
        db=db_session,
        tenant_id=tenant_a.id,
        heartbeat_timeout_sec=30,
        queued_timeout_sec=300
    )

    assert recovery_summary.stale_processing_count == 1
    assert recovery_summary.stale_queued_count == 1
    assert recovery_summary.stale_processing_jobs[0].job_id == job_proc_id
    assert recovery_summary.stale_queued_jobs[0].job_id == job_queue_id

    # Verificar que el job sigue en estado PROCESSING (no mutado)
    refreshed_job = db_session.query(ProcessingJob).filter(ProcessingJob.job_id == job_proc_id).first()
    assert refreshed_job.status == "PROCESSING"


def test_monitoring_time_window_clamping(db_session: Session, setup_tenants):
    """
    Verifica que las horas se acoten entre 1h y 168h para prevenir sobrecarga de BD.
    """
    tenant_a, _ = setup_tenants

    # Test con 0 horas (debe acotarse a 1)
    rep_min = MonitoringService.get_latency_metrics(db=db_session, tenant_id=tenant_a.id, hours=0)
    assert rep_min.time_window_hours == 1

    # Test con 500 horas (debe acotarse a 168)
    rep_max = MonitoringService.get_latency_metrics(db=db_session, tenant_id=tenant_a.id, hours=500)
    assert rep_max.time_window_hours == 168
