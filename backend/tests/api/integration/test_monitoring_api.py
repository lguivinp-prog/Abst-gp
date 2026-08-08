import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.domain import (
    WorkerHeartbeat,
    ProcessingMetrics,
    ProcessingJob,
    AuditLog,
    Tenant,
    User
)


def _utc_now():
    return datetime.now(timezone.utc)


def test_monitoring_rbac_enforcement(client: TestClient):
    """
    Verifica que usuarios sin rol ADMIN (ej. OPERATOR) sean rechazados con 403 Forbidden
    en todos los endpoints administrativos de monitoreo.
    """
    res_workers = client.get("/admin/monitoring/workers")
    assert res_workers.status_code == 403

    res_lat = client.get("/admin/monitoring/latencies")
    assert res_lat.status_code == 403

    res_err = client.get("/admin/monitoring/errors")
    assert res_err.status_code == 403

    res_rec = client.get("/admin/monitoring/recovery")
    assert res_rec.status_code == 403

    res_trig = client.post("/admin/monitoring/recovery/trigger")
    assert res_trig.status_code == 403


def test_get_workers_status_endpoint(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Verifica que GET /admin/monitoring/workers retorne el estado del cluster
    con detección dinámica de liveness (IDLE, BUSY, UNRESPONSIVE, OFFLINE).
    """
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    w1 = WorkerHeartbeat(
        worker_name=f"worker_api_idle_{uid}",
        worker_type="abst_worker",
        hostname="api-node-1",
        status="IDLE",
        tenant_id="mega_tenant",
        last_seen=now - timedelta(seconds=5),
        started_at=now - timedelta(hours=1)
    )
    w2 = WorkerHeartbeat(
        worker_name=f"worker_api_unresp_{uid}",
        worker_type="abst_worker_ocr",
        hostname="api-node-2",
        status="BUSY",
        current_job_id=f"job-api-{uid}",
        tenant_id="mega_tenant",
        last_seen=now - timedelta(seconds=60),
        started_at=now - timedelta(hours=2)
    )

    db_session.add_all([w1, w2])
    db_session.commit()

    res = admin_client.get("/admin/monitoring/workers?heartbeat_threshold_sec=30")
    assert res.status_code == 200
    data = res.json()

    assert data["total_workers"] >= 2
    worker_map = {w["worker_name"]: w for w in data["workers"]}

    assert worker_map[f"worker_api_idle_{uid}"]["status"] == "IDLE"
    assert worker_map[f"worker_api_idle_{uid}"]["is_healthy"] is True

    assert worker_map[f"worker_api_unresp_{uid}"]["status"] == "UNRESPONSIVE"
    assert worker_map[f"worker_api_unresp_{uid}"]["is_healthy"] is False


def test_get_latency_metrics_endpoint(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Verifica que GET /admin/monitoring/latencies retorne percentiles p50, p95, p99 y promedios
    filtrados por ventana temporal y tipo de job.
    """
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    # Insertar métricas en mega_tenant
    for i, lat in enumerate([100, 200, 300, 400, 500]):
        j_id = f"job-api-lat-{uid}-{i}"
        pj = ProcessingJob(job_id=j_id, tenant_id="mega_tenant", job_type="QUOTATION_EXTRACTION", status="READY")
        db_session.add(pj)
        m = ProcessingMetrics(
            job_id=j_id,
            tenant_id="mega_tenant",
            job_type="QUOTATION_EXTRACTION",
            total_time_ms=lat,
            processing_time_ms=lat,
            queue_time_ms=0,
            success=True,
            created_at=now - timedelta(minutes=5)
        )
        db_session.add(m)

    db_session.commit()

    res = admin_client.get("/admin/monitoring/latencies?hours=24")
    assert res.status_code == 200
    data = res.json()

    assert data["total_samples"] >= 5
    assert data["global_metrics"]["sample_count"] >= 5
    assert data["global_metrics"]["min_ms"] <= 100
    assert data["global_metrics"]["max_ms"] >= 500

    # Filtro específico por job_type
    res_type = admin_client.get("/admin/monitoring/latencies?job_type=QUOTATION_EXTRACTION&hours=24")
    assert res_type.status_code == 200
    data_type = res_type.json()
    assert data_type["global_metrics"]["job_type"] == "QUOTATION_EXTRACTION"


def test_get_error_analytics_endpoint(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Verifica que GET /admin/monitoring/errors retorne la matriz taxonómica de errores V5.4.
    """
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    # Métrica de error de infraestructura
    pj1 = ProcessingJob(job_id=f"job-api-err-1-{uid}", tenant_id="mega_tenant", job_type="REQUIREMENT_OCR", status="FAILED")
    db_session.add(pj1)
    m1 = ProcessingMetrics(
        job_id=f"job-api-err-1-{uid}",
        tenant_id="mega_tenant",
        job_type="REQUIREMENT_OCR",
        total_time_ms=1200,
        success=False,
        error_code="REDIS_TIMEOUT",
        error_category="TRANSIENT_INFRA",
        created_at=now - timedelta(minutes=2)
    )
    db_session.add(m1)

    # Métrica de error de entrada corrupta
    pj2 = ProcessingJob(job_id=f"job-api-err-2-{uid}", tenant_id="mega_tenant", job_type="QUOTATION_EXTRACTION", status="FAILED")
    db_session.add(pj2)
    m2 = ProcessingMetrics(
        job_id=f"job-api-err-2-{uid}",
        tenant_id="mega_tenant",
        job_type="QUOTATION_EXTRACTION",
        total_time_ms=850,
        success=False,
        error_code="PDF_PARSE_ERROR",
        error_category="CORRUPT_INPUT",
        created_at=now - timedelta(minutes=2)
    )
    db_session.add(m2)

    db_session.commit()

    res = admin_client.get("/admin/monitoring/errors?hours=24")
    assert res.status_code == 200
    data = res.json()

    assert data["failed_jobs"] >= 2
    assert "TRANSIENT_INFRA" in data["errors_by_category"]
    assert "CORRUPT_INPUT" in data["errors_by_category"]
    assert "REDIS_TIMEOUT" in data["errors_by_code"]
    assert "PDF_PARSE_ERROR" in data["errors_by_code"]


def test_get_recovery_status_endpoint(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Verifica que GET /admin/monitoring/recovery retorne jobs estancados sin mutar la BD.
    """
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    job_stuck = ProcessingJob(
        job_id=f"job-api-stuck-{uid}",
        tenant_id="mega_tenant",
        job_type="COMPARISON_RUN",
        status="PROCESSING",
        last_heartbeat_at=now - timedelta(seconds=90),
        started_at=now - timedelta(seconds=120),
        attempt_count=1,
        max_retries=3
    )
    db_session.add(job_stuck)
    db_session.commit()

    res = admin_client.get("/admin/monitoring/recovery?heartbeat_timeout_sec=30")
    assert res.status_code == 200
    data = res.json()

    assert data["stale_processing_count"] >= 1
    found_ids = [j["job_id"] for j in data["stale_processing_jobs"]]
    assert f"job-api-stuck-{uid}" in found_ids


def test_post_recovery_trigger_endpoint(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Verifica que POST /admin/monitoring/recovery/trigger ejecute la reconciliación
    y genere el registro de auditoría inmutable en AuditLog.
    """
    now = _utc_now()
    uid = uuid.uuid4().hex[:6]

    job_dead = ProcessingJob(
        job_id=f"job-api-dead-{uid}",
        tenant_id="mega_tenant",
        job_type="REQUIREMENT_OCR",
        status="PROCESSING",
        last_heartbeat_at=now - timedelta(seconds=120),
        started_at=now - timedelta(seconds=150),
        attempt_count=1,
        max_retries=3
    )
    db_session.add(job_dead)
    db_session.commit()

    res = admin_client.post("/admin/monitoring/recovery/trigger")
    assert res.status_code == 200
    data = res.json()

    assert data["total_scanned"] >= 1
    assert data["recovered_retried"] >= 1

    # Verificar que el job se reinició a QUEUED con attempt_count=2
    db_session.refresh(job_dead)
    assert job_dead.status == "QUEUED"
    assert job_dead.attempt_count == 2

    # Verificar que se registró la entrada inmutable en AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.tenant_id == "mega_tenant",
        AuditLog.action == "ADMIN_TRIGGER_RECOVERY"
    ).first()
    assert audit is not None
    assert audit.user_id == 2  # Admin user id

