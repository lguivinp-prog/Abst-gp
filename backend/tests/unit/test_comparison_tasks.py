import pytest
from app.models.domain import (
    CaseFile,
    UploadedDocument,
    ParsedSection,
    QuotationExtraction,
    FinalConditionComparison,
    AuditLog
)
from app.services.job_repository import JobRepository
from app.worker.comparison_tasks import process_comparison_task


def test_process_comparison_task_success(db_session):
    """
    Verifica la ejecución exitosa del worker de comparación asíncrono:
    - Adquisición de bloqueo y lectura de requerimientos y cotización.
    - Ejecución del motor de comparación algorítmico.
    - Persistencia de FinalConditionComparison.
    - Transición de CaseFile a READY_GENERATE.
    - Actualización de ProcessingJob en PostgreSQL (100% READY).
    - Registro de AuditLog SUCCESS.
    """
    case = CaseFile(
        id=920,
        title="Expediente Comparación Async V5.3",
        contract_type="SERVICE",
        status="COMPARING",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    # Documento de requerimiento
    doc = UploadedDocument(
        id=9201,
        case_id=case.id,
        document_type="requirement",
        original_filename="requerimiento_test.pdf",
        stored_path="/data/uploads/req_test.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    # Sección de requerimiento seleccionada
    section = ParsedSection(
        case_id=case.id,
        document_id=doc.id,
        title="PLAZO DE ENTREGA",
        current_text="El plazo de entrega será de 15 días calendario.",
        is_selected=True
    )
    db_session.add(section)

    # Cotización extraída
    quotation = QuotationExtraction(
        case_id=case.id,
        raw_json={
            "supplier": {"supplier_ruc": {"value": "20123456789", "confidence": 0.95}},
            "conditions": {"delivery_time": {"value": "15 días calendario", "confidence": 0.90}}
        },
        review_status="validated"
    )
    db_session.add(quotation)
    db_session.commit()

    # Crear ProcessingJob
    job = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=1,
        job_type="COMPARISON_RUN"
    )

    result = process_comparison_task(
        job_id=job.job_id,
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=1,
        db=db_session
    )

    assert result["case_status"] == "READY_GENERATE"
    assert result["items_compared"] > 0
    assert result["already_completed"] is False

    # Verificar ProcessingJob
    updated_job = JobRepository.get_by_job_id(db_session, job.job_id, tenant_id="mega_tenant")
    assert updated_job.status == "READY"
    assert updated_job.progress == 100
    assert "Comparación finalizada" in updated_job.status_message

    # Verificar CaseFile status
    db_session.refresh(case)
    assert case.status == "READY_GENERATE"

    # Verificar FinalConditionComparison
    comparisons = db_session.query(FinalConditionComparison).filter(FinalConditionComparison.case_id == case.id).all()
    assert len(comparisons) > 0

    # Verificar AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.tenant_id == "mega_tenant",
        AuditLog.action == "COMPARISON_RUN_ASYNC",
        AuditLog.status == "SUCCESS"
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert audit.user_id == 1


def test_process_comparison_task_idempotency(db_session):
    """
    Verifica que llamadas posteriores sobre un caso ya comparado sean idempotentes:
    - Retornan inmediatamente sin duplicar registros en FinalConditionComparison.
    - Marcan el nuevo ProcessingJob como READY.
    """
    case = CaseFile(
        id=921,
        title="Expediente Idempotencia V5.3",
        contract_type="SERVICE",
        status="READY_GENERATE",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    # Insertar una comparación existente
    comp = FinalConditionComparison(
        case_id=case.id,
        field_name="plazo_entrega",
        requirement_value="10 dias",
        quotation_value="10 dias",
        final_value="10 dias",
        status="Coincide"
    )
    db_session.add(comp)
    db_session.commit()

    job2 = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=1,
        job_type="COMPARISON_RUN"
    )

    result = process_comparison_task(
        job_id=job2.job_id,
        case_id=case.id,
        tenant_id="mega_tenant",
        user_id=1,
        db=db_session
    )

    assert result["already_completed"] is True
    assert result["items_compared"] == 1

    # Verificar que el conteo no cambió
    count = db_session.query(FinalConditionComparison).filter(FinalConditionComparison.case_id == case.id).count()
    assert count == 1

    # Verificar ProcessingJob completado
    updated_job = JobRepository.get_by_job_id(db_session, job2.job_id, tenant_id="mega_tenant")
    assert updated_job.status == "READY"
    assert updated_job.progress == 100
    assert "Idempotente" in updated_job.status_message


def test_process_comparison_task_invalid_status_failure(db_session):
    """
    Verifica que si el caso está en un estado inválido (ej. WAITING_QUOTATION),
    el worker falle de forma controlada y marque el ProcessingJob como FAILED.
    """
    case = CaseFile(
        id=922,
        title="Expediente Estado Inválido",
        contract_type="SERVICE",
        status="WAITING_QUOTATION",
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

    with pytest.raises(ValueError) as exc:
        process_comparison_task(
            job_id=job.job_id,
            case_id=case.id,
            tenant_id="mega_tenant",
            user_id=1,
            db=db_session
        )

    assert "no está listo para comparación" in str(exc.value)

    # Verificar ProcessingJob FAILED
    updated_job = JobRepository.get_by_job_id(db_session, job.job_id, tenant_id="mega_tenant")
    assert updated_job.status == "FAILED"
    assert updated_job.progress == 100
    assert "no está listo" in updated_job.error_message

    # Verificar AuditLog FAILED
    audit = db_session.query(AuditLog).filter(
        AuditLog.tenant_id == "mega_tenant",
        AuditLog.action == "COMPARISON_RUN_ASYNC",
        AuditLog.status == "FAILED"
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
