import os
import json
import pytest
from unittest.mock import patch
from app.models.domain import CaseFile, QuotationExtraction, ProcessingJob, AuditLog
from app.services.job_repository import JobRepository
from app.worker.quotation_tasks import process_quotation_task


def test_process_quotation_task_success(db_session, tmp_path):
    """
    Verifica la ejecución exitosa del worker de cotización:
    - Transiciones en PostgreSQL (JobRepository).
    - Creación de QuotationExtraction.
    - Transición de CaseFile a COMPARING.
    - Registro de AuditLog SUCCESS con tenant_id y user_id.
    """
    case = CaseFile(
        id=910,
        title="Expediente Cotización Async V5.3",
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
        job_type="QUOTATION_EXTRACTION"
    )

    # Crear PDF temporal
    pdf_file = tmp_path / "cotizacion_test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy quotation content")

    mock_quotation_payload = {
        "text_raw": "Cotización Proveedor RUC 20555666777 Total 1500 PEN",
        "supplier": {
            "supplier_ruc": {"value": "20555666777", "confidence": 0.95}
        },
        "product": {
            "total_price": {"value": "1500.00", "confidence": 0.90}
        },
        "conditions": {
            "payment_condition": {"value": "Contado", "confidence": 0.85}
        },
        "tables": [],
        "global_confidence": 0.90
    }

    with patch("app.worker.quotation_tasks.parse_quotation_pdf", return_value=mock_quotation_payload):
        result = process_quotation_task(
            job_id=job.job_id,
            case_id=case.id,
            tenant_id="mega_tenant",
            user_id=1,
            file_path=str(pdf_file),
            db=db_session
        )

    assert result["global_confidence"] == 0.90
    assert result["supplier_ruc"] == "20555666777"
    assert result["review_status"] == "validated"

    # Verificar ProcessingJob en PostgreSQL
    updated_job = JobRepository.get_by_job_id(db_session, job.job_id, tenant_id="mega_tenant")
    assert updated_job.status == "READY"
    assert updated_job.progress == 100
    assert "Cotización procesada" in updated_job.status_message

    # Verificar QuotationExtraction
    extraction = db_session.query(QuotationExtraction).filter(QuotationExtraction.case_id == case.id).first()
    assert extraction is not None
    assert extraction.review_status == "validated"
    assert extraction.raw_json["supplier"]["supplier_ruc"]["value"] == "20555666777"

    # Verificar CaseFile status
    db_session.refresh(case)
    assert case.status == "COMPARING"

    # Verificar AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.tenant_id == "mega_tenant",
        AuditLog.action == "QUOTATION_EXTRACTED_ASYNC"
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert audit.status == "SUCCESS"
    assert audit.user_id == 1


def test_process_quotation_task_missing_file_failure(db_session):
    """
    Verifica el manejo de errores ante archivo inexistente:
    - ProcessingJob pasa a FAILED vía JobRepository.
    - AuditLog FAILED es registrado.
    - La excepción es propagada limpiamente.
    """
    case = CaseFile(
        id=911,
        title="Expediente Cotización Inexistente",
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
        job_type="QUOTATION_EXTRACTION"
    )

    with pytest.raises(FileNotFoundError):
        process_quotation_task(
            job_id=job.job_id,
            case_id=case.id,
            tenant_id="mega_tenant",
            user_id=1,
            file_path="/tmp/non_existent_path_9999.pdf",
            db=db_session
        )

    # Verificar ProcessingJob en PostgreSQL
    updated_job = JobRepository.get_by_job_id(db_session, job.job_id, tenant_id="mega_tenant")
    assert updated_job.status == "FAILED"
    assert updated_job.progress == 100
    assert "no encontrado" in updated_job.error_message

    # Verificar AuditLog FAILED
    audit = db_session.query(AuditLog).filter(
        AuditLog.tenant_id == "mega_tenant",
        AuditLog.action == "QUOTATION_EXTRACTED_ASYNC",
        AuditLog.status == "FAILED"
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert audit.user_id == 1
