import os
import pytest
from datetime import datetime, timezone, timedelta
from app.models.domain import (
    Tenant,
    User,
    CaseFile,
    ProcessingJob,
    ProcessingMetrics,
    WorkerHeartbeat,
    QuotationExtraction,
    FinalConditionComparison,
    AuditLog
)
from app.services.job_repository import JobRepository
from app.worker.quotation_tasks import process_quotation_task
from app.worker.comparison_tasks import process_comparison_task


@pytest.fixture
def v54_worker_fixture(db_session):
    """Fixture para pruebas de instrumentación V5.4 con tenant y usuario estándar."""
    tenant_id = "mega_tenant"
    user_id = 1

    case = CaseFile(
        id=7701,
        title="Expediente de Instrumentación V5.4",
        contract_type="BIENES",
        status="COMPARING",
        tenant_id=tenant_id,
        created_by=user_id
    )
    db_session.add(case)
    db_session.commit()

    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "case_id": case.id
    }


def test_worker_heartbeat_full_lifecycle(db_session, v54_worker_fixture):
    """Verifica el ciclo de estados STARTED -> BUSY -> IDLE -> OFFLINE en WorkerHeartbeat."""
    t_id = v54_worker_fixture["tenant_id"]
    u_id = v54_worker_fixture["user_id"]
    c_id = v54_worker_fixture["case_id"]

    job = JobRepository.create_job(
        db=db_session,
        case_id=c_id,
        tenant_id=t_id,
        user_id=u_id,
        job_type="QUOTATION_EXTRACT"
    )

    worker_name = "test_quotation_worker_node_1"

    # 1. STARTED
    hb_started = JobRepository.record_heartbeat(
        db=db_session,
        worker_name=worker_name,
        worker_type="QUOTATION_WORKER",
        status="STARTED",
        tenant_id=t_id
    )
    assert hb_started.status == "STARTED"
    assert hb_started.worker_name == worker_name
    assert hb_started.current_job_id is None

    # 2. BUSY (Asignando job_id)
    hb_busy = JobRepository.record_heartbeat(
        db=db_session,
        worker_name=worker_name,
        worker_type="QUOTATION_WORKER",
        status="BUSY",
        current_job_id=job.job_id,
        tenant_id=t_id
    )
    assert hb_busy.status == "BUSY"
    assert hb_busy.current_job_id == job.job_id

    # Comprobar que ProcessingJob se actualizó con worker_name y last_heartbeat_at
    db_session.refresh(job)
    assert job.worker_name == worker_name
    assert job.last_heartbeat_at is not None

    # 3. IDLE (Completando job)
    hb_idle = JobRepository.record_heartbeat(
        db=db_session,
        worker_name=worker_name,
        worker_type="QUOTATION_WORKER",
        status="IDLE",
        current_job_id=None,
        tenant_id=t_id
    )
    assert hb_idle.status == "IDLE"
    assert hb_idle.current_job_id is None

    # 4. OFFLINE
    hb_off = JobRepository.record_heartbeat(
        db=db_session,
        worker_name=worker_name,
        worker_type="QUOTATION_WORKER",
        status="OFFLINE",
        tenant_id=t_id
    )
    assert hb_off.status == "OFFLINE"


def test_success_metrics_generation_quotation_task(db_session, v54_worker_fixture, tmp_path, monkeypatch):
    """Verifica que la ejecución exitosa de quotation_task genera ProcessingMetrics con latencias correctas."""
    t_id = v54_worker_fixture["tenant_id"]
    u_id = v54_worker_fixture["user_id"]
    c_id = v54_worker_fixture["case_id"]

    dummy_pdf = tmp_path / "cotizacion_v54.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy content")

    fake_parsed = {
        "supplier": {"supplier_name": {"value": "Tech Corp"}, "supplier_ruc": {"value": "20123456789"}},
        "items": [{"item": "Laptop", "quantity": 5, "price": 1000}],
        "global_confidence": 0.95,
        "page_count": 3
    }
    monkeypatch.setattr(
        "app.worker.quotation_tasks.parse_quotation_pdf",
        lambda path: fake_parsed
    )

    job = JobRepository.create_job(
        db=db_session,
        case_id=c_id,
        tenant_id=t_id,
        user_id=u_id,
        job_type="QUOTATION_EXTRACT"
    )

    # Simular tiempo de espera en cola (500 ms antes)
    job.created_at = datetime.now(timezone.utc) - timedelta(milliseconds=500)
    db_session.commit()

    result = process_quotation_task(
        job_id=job.job_id,
        case_id=c_id,
        tenant_id=t_id,
        user_id=u_id,
        file_path=str(dummy_pdf),
        db=db_session
    )

    assert result["review_status"] == "validated"
    assert result["supplier_ruc"] == "20123456789"

    # Verificar ProcessingJob
    db_session.refresh(job)
    assert job.status == "READY"
    assert job.progress == 100
    assert "quotation_worker" in job.worker_name

    # Verificar ProcessingMetrics generado
    metric = db_session.query(ProcessingMetrics).filter(ProcessingMetrics.job_id == job.job_id).first()
    assert metric is not None
    assert metric.success is True
    assert metric.tenant_id == t_id
    assert metric.case_id == c_id
    assert metric.job_type == "QUOTATION_EXTRACT"
    assert metric.queue_time_ms >= 0
    assert metric.processing_time_ms >= 0
    assert metric.total_time_ms >= 0
    assert metric.pages_processed == 3
    assert metric.error_code is None
    assert metric.error_category is None


def test_failed_metrics_and_error_classification(db_session, v54_worker_fixture):
    """Verifica que un fallo clasifica el error y emite ProcessingMetrics con success=False."""
    t_id = v54_worker_fixture["tenant_id"]
    u_id = v54_worker_fixture["user_id"]
    c_id = v54_worker_fixture["case_id"]

    job = JobRepository.create_job(
        db=db_session,
        case_id=c_id,
        tenant_id=t_id,
        user_id=u_id,
        job_type="QUOTATION_EXTRACT"
    )

    # Intentar procesar un archivo inexistente -> FileNotFoundError
    with pytest.raises(FileNotFoundError):
        process_quotation_task(
            job_id=job.job_id,
            case_id=c_id,
            tenant_id=t_id,
            user_id=u_id,
            file_path="/path/to/non_existent_file_v54.pdf",
            db=db_session
        )

    # Comprobar que ProcessingJob falló y tiene clasificación
    db_session.refresh(job)
    assert job.status == "FAILED"
    assert job.failure_classification == "FINAL"

    # Comprobar ProcessingMetrics
    metric = db_session.query(ProcessingMetrics).filter(ProcessingMetrics.job_id == job.job_id).first()
    assert metric is not None
    assert metric.success is False
    assert metric.error_code == "FILE_NOT_FOUND"
    assert metric.error_category == "CORRUPT_INPUT"
    assert metric.total_time_ms >= 0


def test_error_taxonomy_classification():
    """Prueba unitaria para el clasificador taxonómico de excepciones."""
    # 1. Archivo no encontrado
    code, cat, classif = JobRepository.classify_error(FileNotFoundError("No such file or directory: demo.pdf"))
    assert code == "FILE_NOT_FOUND"
    assert cat == "CORRUPT_INPUT"
    assert classif == "FINAL"

    # 2. PDF Corrupto
    code, cat, classif = JobRepository.classify_error(ValueError("PDF corrupt or damaged header"))
    assert code == "CORRUPT_PDF"
    assert cat == "CORRUPT_INPUT"
    assert classif == "FINAL"

    # 3. Regla de negocio / Estado inválido
    code, cat, classif = JobRepository.classify_error(ValueError("El expediente no está listo para comparación."))
    assert code == "BUSINESS_RULE_VIOLATION"
    assert cat == "BUSINESS_RULE"
    assert classif == "FINAL"

    # 4. Timeout transitorio de infraestructura
    code, cat, classif = JobRepository.classify_error(TimeoutError("Connection to Redis timed out"))
    assert code == "INFRASTRUCTURE_TIMEOUT"
    assert cat == "TRANSIENT_INFRA"
    assert classif == "RETRYABLE"

    # 5. Error inesperado
    code, cat, classif = JobRepository.classify_error(RuntimeError("Unexpected memory error"))
    assert code == "INTERNAL_PROCESSING_ERROR"
    assert cat == "UNEXPECTED_ERROR"
    assert classif == "RETRYABLE"


def test_comparison_task_success_metrics(db_session, v54_worker_fixture, monkeypatch):
    """Verifica que process_comparison_task genera métricas de comparación exitosas."""
    t_id = v54_worker_fixture["tenant_id"]
    u_id = v54_worker_fixture["user_id"]
    c_id = v54_worker_fixture["case_id"]

    # Añadir cotización
    quot = QuotationExtraction(
        case_id=c_id,
        raw_json={"supplier": {"value": "Supplier Inc"}, "items": [{"item": "Product A"}]},
        review_status="validated"
    )
    db_session.add(quot)
    db_session.commit()

    monkeypatch.setattr(
        "app.worker.comparison_tasks.run_comparison",
        lambda req, quot: [
            {
                "field_name": "plazo_entrega",
                "requirement_value": "30 dias",
                "quotation_value": "30 dias",
                "final_value": "30 dias",
                "status": "Coincide"
            },
            {
                "field_name": "garantia",
                "requirement_value": "12 meses",
                "quotation_value": "12 meses",
                "final_value": "12 meses",
                "status": "Coincide"
            }
        ]
    )

    job = JobRepository.create_job(
        db=db_session,
        case_id=c_id,
        tenant_id=t_id,
        user_id=u_id,
        job_type="COMPARISON_RUN"
    )

    result = process_comparison_task(
        job_id=job.job_id,
        case_id=c_id,
        tenant_id=t_id,
        user_id=u_id,
        db=db_session
    )

    assert result["items_compared"] == 2
    assert result["case_status"] == "READY_GENERATE"

    # Comprobar ProcessingMetrics
    metric = db_session.query(ProcessingMetrics).filter(ProcessingMetrics.job_id == job.job_id).first()
    assert metric is not None
    assert metric.success is True
    assert metric.job_type == "COMPARISON_RUN"
    assert metric.pages_processed == 2
    assert metric.error_code is None
