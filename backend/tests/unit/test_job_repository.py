import json
import pytest
from app.models.domain import ProcessingJob, CaseFile, User, Tenant
from app.services.job_repository import JobRepository


def test_job_repository_crud_lifecycle(db_session):
    """
    Prueba el ciclo de vida completo de un ProcessingJob en PostgreSQL:
    Creación -> Progreso -> Completado -> Consulta por ID/Idempotencia.
    """
    # 1. Setup inicial de caso y usuario
    case = CaseFile(
        id=901,
        title="Expediente Test Async V5.3",
        contract_type="SERVICE",
        status="WAITING_QUOTATION",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    # 2. Crear ProcessingJob
    idempotency_key = "idemp_test_hash_12345"
    job = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=1,
        job_type="QUOTATION_EXTRACTION",
        idempotency_key=idempotency_key
    )

    assert job.id is not None
    assert job.job_id.startswith("quotation_extraction_901_")
    assert job.status == "QUEUED"
    assert job.progress == 0
    assert job.tenant_id == "mega_tenant"
    assert job.idempotency_key == idempotency_key

    # 3. Consulta por job_id y por idempotency_key
    fetched_job = JobRepository.get_by_job_id(db_session, job.job_id, tenant_id="mega_tenant")
    assert fetched_job is not None
    assert fetched_job.id == job.id

    fetched_by_idemp = JobRepository.get_by_idempotency_key(db_session, idempotency_key, tenant_id="mega_tenant")
    assert fetched_by_idemp is not None
    assert fetched_by_idemp.job_id == job.job_id

    # 4. Verificar detección de job activo
    active_job = JobRepository.get_active_job_for_case(db_session, case.id, "QUOTATION_EXTRACTION", tenant_id="mega_tenant")
    assert active_job is not None
    assert active_job.job_id == job.job_id

    # 5. Actualizar progreso
    updated = JobRepository.update_progress(
        db=db_session,
        job_id=job.job_id,
        progress=50,
        status_message="Extrayendo tablas de cotización...",
        status="PROCESSING"
    )
    assert updated.progress == 50
    assert updated.status == "PROCESSING"
    assert updated.status_message == "Extrayendo tablas de cotización..."
    assert updated.started_at is not None

    # 6. Marcar como completado
    summary_data = {"ruc": "20123456789", "total_items": 5, "currency": "PEN"}
    completed = JobRepository.mark_completed(
        db=db_session,
        job_id=job.job_id,
        result_summary=summary_data,
        status_message="Cotización extraída con éxito"
    )
    assert completed.status == "READY"
    assert completed.progress == 100
    assert completed.finished_at is not None
    assert json.loads(completed.result_summary) == summary_data

    # 7. Verificar que ya no hay job activo pendiente
    active_job_after = JobRepository.get_active_job_for_case(db_session, case.id, "QUOTATION_EXTRACTION", tenant_id="mega_tenant")
    assert active_job_after is None


def test_job_repository_failure_handling(db_session):
    """
    Prueba el manejo de fallos y marcado seguro de errores en ProcessingJob.
    """
    case = CaseFile(
        id=902,
        title="Expediente Test Failure V5.3",
        contract_type="SERVICE",
        status="COMPARING",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    job = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=1,
        job_type="COMPARISON_RUN"
    )

    failed_job = JobRepository.mark_failed(
        db=db_session,
        job_id=job.job_id,
        error_message="División por cero en matriz de penalidades"
    )

    assert failed_job.status == "FAILED"
    assert failed_job.progress == 100
    assert "División por cero" in failed_job.error_message
    assert failed_job.finished_at is not None


def test_job_repository_multi_tenant_isolation(db_session):
    """
    Prueba el estricto aislamiento multi-tenant en consultas de ProcessingJob.
    """
    # Crear o recuperar segundo tenant
    t2 = db_session.query(Tenant).filter(Tenant.id == "tenant_foreign_test").first()
    if not t2:
        t2 = Tenant(id="tenant_foreign_test", name="Foreign Entity")
        db_session.add(t2)
        db_session.commit()

    case1 = CaseFile(id=903, title="Caso Tenant 1", contract_type="SERVICE", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    case2 = CaseFile(id=904, title="Caso Tenant 2", contract_type="SERVICE", status="WAITING_QUOTATION", tenant_id="tenant_foreign_test")
    db_session.add_all([case1, case2])
    db_session.commit()

    job1 = JobRepository.create_job(
        db=db_session,
        case_id=case1.id,
        tenant_id="mega_tenant",
        user_id=1,
        job_type="QUOTATION_EXTRACTION"
    )

    # Consulta con tenant_id cruzado debe retornar None
    cross_lookup = JobRepository.get_by_job_id(db_session, job1.job_id, tenant_id="tenant_foreign_test")
    assert cross_lookup is None

    # Consulta con el tenant correcto debe retornar el registro
    valid_lookup = JobRepository.get_by_job_id(db_session, job1.job_id, tenant_id="mega_tenant")
    assert valid_lookup is not None
    assert valid_lookup.id == job1.id
