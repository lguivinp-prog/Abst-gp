"""
Pruebas Unitarias de Telemetría Externa y OpenTelemetry (Fase 7.1)
Valida:
1. Endpoint /metrics responde con formato OpenMetrics / Prometheus.
2. Contadores, Histogramas y Gauges incrementan y registran muestras con precisión.
3. Aislamiento Multi-tenant: Ningún label contiene 'tenant_id' o datos sensibles.
4. Overhead despreciable (<0.05ms por emisión).
5. Propagación de trazabilidad distribuida W3C (traceparent, x-trace-id).
6. Integración transparente con JobRepository.
"""

import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.telemetry import (
    metrics_registry,
    record_job_lifecycle,
    record_worker_telemetry,
    record_queue_telemetry,
    parse_traceparent,
    format_traceparent,
    normalize_endpoint_path,
    current_trace_id,
    current_span_id
)
from app.models.domain import ProcessingJob
from app.services.job_repository import JobRepository


@pytest.fixture
def client():
    return TestClient(app)


def test_metrics_endpoint_response(client):
    """Valida que /metrics responda 200 con formato estándar Prometheus."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text

    assert "# HELP abst_jobs_total" in body
    assert "# TYPE abst_jobs_total counter"
    assert "# HELP abst_job_duration_seconds" in body
    assert "# TYPE abst_job_duration_seconds histogram"
    assert "# HELP abst_worker_status" in body
    assert "# TYPE abst_worker_status gauge"
    assert "# HELP abst_queue_depth" in body
    assert "# TYPE abst_queue_depth gauge"
    assert "# HELP abst_http_request_duration_seconds" in body
    assert "# TYPE abst_http_request_duration_seconds histogram"


def test_metrics_increment_and_histogram():
    """Valida la acumulación correcta de contadores e histogramas."""
    initial_sample = metrics_registry.jobs_total.get_sample(
        job_type="QUOTATION_EXTRACTION",
        status="READY"
    )

    record_job_lifecycle(
        job_type="QUOTATION_EXTRACTION",
        status="READY",
        duration_seconds=2.45
    )

    updated_sample = metrics_registry.jobs_total.get_sample(
        job_type="QUOTATION_EXTRACTION",
        status="READY"
    )
    assert updated_sample == initial_sample + 1.0

    # Histograma
    count = metrics_registry.job_duration_seconds.get_count(
        job_type="QUOTATION_EXTRACTION",
        status="READY"
    )
    assert count >= 1


def test_gauges_worker_and_queue():
    """Valida actualización de gauges para workers y colas."""
    record_worker_telemetry("ocr_worker", "BUSY", count=4)
    sample_worker = metrics_registry.worker_status.get_sample(worker_type="ocr_worker", status="BUSY")
    assert sample_worker == 4.0

    record_queue_telemetry("ocr_tasks", depth=12)
    sample_queue = metrics_registry.queue_depth.get_sample(queue_name="ocr_tasks")
    assert sample_queue == 12.0


def test_no_tenant_id_leakage_in_metrics():
    """
    CRÍTICO SRE: Valida que ninguna métrica de Prometheus exponga 'tenant_id'
    para prevenir explosión de cardinalidad y garantizar aislamiento de privacidad.
    """
    output = metrics_registry.generate_latest()
    lines = output.splitlines()

    for line in lines:
        if line.startswith("#"):
            continue
        assert "tenant_id" not in line.lower(), f"Fuga de tenant_id detectada en métrica: {line}"
        assert "tenant-demo" not in line.lower(), f"Fuga de tenant específico detectada en métrica: {line}"


def test_path_normalization_for_low_cardinality():
    """Valida que los IDs dinámicos en rutas HTTP se normalicen a {id}."""
    assert normalize_endpoint_path("/cases/123") == "/cases/{id}"
    assert normalize_endpoint_path("/cases/550e8400-e29b-41d4-a716-446655440000/quotations") == "/cases/{id}/quotations"
    assert normalize_endpoint_path("/health") == "/health"
    assert normalize_endpoint_path("/admin/monitoring/workers") == "/admin/monitoring/workers"


def test_w3c_traceparent_propagation(client):
    """Valida propagación e inyección de encabezados W3C TraceContext."""
    # 1. Petición con traceparent existente
    trace_id_in = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id_in = "00f067aa0ba902b7"
    incoming_traceparent = f"00-{trace_id_in}-{span_id_in}-01"

    response = client.get("/health", headers={"traceparent": incoming_traceparent})
    assert response.status_code == 200
    assert response.headers.get("x-trace-id") == trace_id_in
    assert "x-span-id" in response.headers
    assert response.headers.get("traceparent").startswith(f"00-{trace_id_in}-")

    # 2. Petición sin traceparent genera uno nuevo válido
    response_new = client.get("/health")
    assert response_new.status_code == 200
    new_trace_id = response_new.headers.get("x-trace-id")
    assert len(new_trace_id) == 32
    assert response_new.headers.get("traceparent").startswith(f"00-{new_trace_id}-")


def test_telemetry_performance_overhead():
    """Valida que 1,000 registros de métricas se ejecuten en < 50ms (< 0.05ms/op)."""
    start = time.perf_counter()
    for _ in range(1000):
        record_job_lifecycle("OCR_PROCESSING", "READY", duration_seconds=1.2)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert elapsed_ms < 50.0, f"Overhead de telemetría excesivo: {elapsed_ms:.2f}ms para 1,000 ops"


def test_job_repository_telemetry_integration(db_session):
    """Valida que JobRepository._record_metric emita métricas a Prometheus."""
    from app.models.domain import Tenant, CaseFile

    tenant = db_session.query(Tenant).filter(Tenant.id == "tenant-telemetry-test").first()
    if not tenant:
        tenant = Tenant(id="tenant-telemetry-test", name="Tenant Telemetry Test")
        db_session.add(tenant)
        db_session.flush()

    case = db_session.query(CaseFile).filter(CaseFile.id == 9991).first()
    if not case:
        case = CaseFile(
            id=9991,
            title="Expediente Telemetria",
            contract_type="BIENES",
            status="DRAFT",
            tenant_id="tenant-telemetry-test"
        )
        db_session.add(case)
        db_session.flush()

    job = ProcessingJob(
        case_id=9991,
        tenant_id="tenant-telemetry-test",
        job_type="COMPARISON_GENERATION",
        status="READY",
        job_id="job-telemetry-1"
    )
    db_session.add(job)
    db_session.commit()

    initial = metrics_registry.jobs_total.get_sample(
        job_type="COMPARISON_GENERATION",
        status="READY"
    )

    JobRepository._record_metric(
        db=db_session,
        job=job,
        effective_worker="test-worker-node",
        success=True
    )

    updated = metrics_registry.jobs_total.get_sample(
        job_type="COMPARISON_GENERATION",
        status="READY"
    )
    assert updated == initial + 1.0

