import io
import json
import pytest
from unittest.mock import patch, Mock
from app.models.domain import (
    CaseFile,
    UploadedDocument,
    ParsedSection,
    QuotationExtraction,
    FinalConditionComparison,
    ProcessingJob
)
from app.services.job_repository import JobRepository
from app.core.config import settings


def test_quotation_upload_sync_fallback(admin_client, db_session, monkeypatch):
    """
    Verifica que con Feature Flags apagadas (OFF), el endpoint /quotation/upload
    mantenga 100% de compatibilidad con el flujo síncrono V5.2.1.
    """
    monkeypatch.setattr(settings, "FEATURE_ASYNC_PROCESSING", False)
    monkeypatch.setattr(settings, "FEATURE_ASYNC_QUOTATION", False)

    # Crear caso en DB
    case = CaseFile(
        id=701,
        title="Expediente Cotizacion Sync Fallback",
        contract_type="SERVICE",
        status="WAITING_QUOTATION",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    mock_quotation_payload = {
        "text_raw": "Cotizacion Proveedor RUC 20999888777",
        "supplier": {"supplier_ruc": {"value": "20999888777", "confidence": 0.95}},
        "global_confidence": 0.90
    }

    dummy_pdf = io.BytesIO(b"%PDF-1.4 mock quotation content")

    with patch("app.api.routers.cases.parse_quotation_pdf", return_value=mock_quotation_payload):
        res = admin_client.post(
            f"/cases/{case.id}/quotation/upload",
            files={"file": ("cotizacion.pdf", dummy_pdf, "application/pdf")}
        )

    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Quotation processed"

    # Verificar que el caso cambió a COMPARING y se persistió QuotationExtraction
    db_session.refresh(case)
    assert case.status == "COMPARING"

    extraction = db_session.query(QuotationExtraction).filter(QuotationExtraction.case_id == case.id).first()
    assert extraction is not None
    assert extraction.review_status == "validated"


def test_quotation_upload_async(admin_client, db_session, monkeypatch):
    """
    Verifica que con Feature Flag activa (ON), el endpoint /quotation/upload:
    1. Persista el archivo PDF en UPLOADS_DIR.
    2. Cree un ProcessingJob en PostgreSQL (estado QUEUED) con tenant_id y user_id.
    3. Encole la tarea en Redis RQ sin ejecutar OCR/extracción síncrona.
    4. Retorne inmediatamente {job_id, status: 'QUEUED'}.
    """
    monkeypatch.setattr(settings, "FEATURE_ASYNC_PROCESSING", True)
    monkeypatch.setattr(settings, "FEATURE_ASYNC_QUOTATION", True)

    case = CaseFile(
        id=702,
        title="Expediente Cotizacion Async V5.3",
        contract_type="SERVICE",
        status="WAITING_QUOTATION",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    dummy_pdf = io.BytesIO(b"%PDF-1.4 async quotation content")

    with patch("app.api.routers.cases.task_queue.enqueue") as mock_enqueue, \
         patch("app.api.routers.cases.parse_quotation_pdf") as mock_sync_parser:

        res = admin_client.post(
            f"/cases/{case.id}/quotation/upload",
            files={"file": ("cotizacion_async.pdf", dummy_pdf, "application/pdf")}
        )

        assert res.status_code == 200
        data = res.json()
        assert "job_id" in data
        assert data["status"] == "QUEUED"
        assert "queued" in data["message"].lower()

        # Asegurar que el parser síncrono NUNCA fue llamado en el request
        mock_sync_parser.assert_not_called()

        # Asegurar que task_queue.enqueue fue invocado
        mock_enqueue.assert_called_once()

        # Verificar que el ProcessingJob fue creado en PostgreSQL con SSOT
        job = JobRepository.get_by_job_id(db_session, data["job_id"], tenant_id="mega_tenant")
        assert job is not None
        assert job.status == "QUEUED"
        assert job.job_type == "QUOTATION_EXTRACTION"
        assert job.case_id == case.id
        assert job.tenant_id == "mega_tenant"


def test_comparison_run_sync_fallback(admin_client, db_session, monkeypatch):
    """
    Verifica que con Feature Flags apagadas (OFF), el endpoint /comparison/run
    ejecute el motor de comparación síncrono de V5.2.1.
    """
    monkeypatch.setattr(settings, "FEATURE_ASYNC_PROCESSING", False)
    monkeypatch.setattr(settings, "FEATURE_ASYNC_COMPARISON", False)

    case = CaseFile(
        id=703,
        title="Expediente Comparación Sync Fallback",
        contract_type="SERVICE",
        status="COMPARING",
        tenant_id="mega_tenant"
    )
    db_session.add(case)

    # Documento y sección
    doc = UploadedDocument(id=7031, case_id=case.id, document_type="requirement", stored_path="/data/req.pdf", original_filename="req.pdf", mime_type="application/pdf")
    db_session.add(doc)
    db_session.commit()

    sec = ParsedSection(case_id=case.id, document_id=doc.id, title="PLAZO", current_text="Plazo: 10 días", is_selected=True)
    db_session.add(sec)

    quot = QuotationExtraction(case_id=case.id, raw_json={"conditions": {"delivery_time": {"value": "10 días"}}}, review_status="validated")
    db_session.add(quot)
    db_session.commit()

    res = admin_client.post(f"/cases/{case.id}/comparison/run")
    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "Comparison completed"
    assert data["already_completed"] is False

    # Verificar que el caso cambió a READY_GENERATE
    db_session.refresh(case)
    assert case.status == "READY_GENERATE"

    comparisons = db_session.query(FinalConditionComparison).filter(FinalConditionComparison.case_id == case.id).all()
    assert len(comparisons) > 0


def test_comparison_run_async(admin_client, db_session, monkeypatch):
    """
    Verifica que con Feature Flag activa (ON), el endpoint /comparison/run:
    1. Cree un ProcessingJob en PostgreSQL (estado QUEUED).
    2. Encole la tarea en Redis RQ sin ejecutar el motor algorítmico en el request.
    3. Retorne inmediatamente {job_id, status: 'QUEUED'}.
    """
    monkeypatch.setattr(settings, "FEATURE_ASYNC_PROCESSING", True)
    monkeypatch.setattr(settings, "FEATURE_ASYNC_COMPARISON", True)

    case = CaseFile(
        id=704,
        title="Expediente Comparación Async V5.3",
        contract_type="SERVICE",
        status="COMPARING",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    quot = QuotationExtraction(case_id=case.id, raw_json={"conditions": {"delivery_time": {"value": "5 días"}}}, review_status="validated")
    db_session.add(quot)
    db_session.commit()

    with patch("app.api.routers.cases.task_queue.enqueue") as mock_enqueue, \
         patch("app.api.routers.cases.run_comparison") as mock_sync_comparison:

        res = admin_client.post(f"/cases/{case.id}/comparison/run")
        assert res.status_code == 200
        data = res.json()
        assert "job_id" in data
        assert data["status"] == "QUEUED"
        assert data["already_completed"] is False

        # Asegurar que el motor síncrono NUNCA fue llamado en el request
        mock_sync_comparison.assert_not_called()

        # Asegurar encolamiento en RQ
        mock_enqueue.assert_called_once()

        # Verificar ProcessingJob en PostgreSQL
        job = JobRepository.get_by_job_id(db_session, data["job_id"], tenant_id="mega_tenant")
        assert job is not None
        assert job.status == "QUEUED"
        assert job.job_type == "COMPARISON_RUN"
        assert job.case_id == case.id


def test_get_job_status_postgres_ssot(admin_client, db_session):
    """
    Verifica que GET /cases/jobs/{job_id} consulte primero PostgreSQL (SSOT)
    y retorne progreso, estado y mensaje descriptivo.
    """
    case = CaseFile(
        id=705,
        title="Expediente Job Status",
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
        user_id=2,
        job_type="QUOTATION_EXTRACTION"
    )

    JobRepository.update_progress(
        db=db_session,
        job_id=job.job_id,
        progress=65,
        status_message="Extrayendo campos estructurados...",
        status="PROCESSING",
        tenant_id="mega_tenant"
    )

    res = admin_client.get(f"/cases/jobs/{job.job_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["job_id"] == job.job_id
    assert data["status"] == "PROCESSING"
    assert data["progress"] == 65
    assert data["message"] == "Extrayendo campos estructurados..."
    assert data["case_status"] == "COMPARING"


def test_get_job_status_multi_tenant_isolation(admin_client, db_session):
    """
    Verifica que un usuario de 'mega_tenant' no pueda consultar un job
    perteneciente a 'other_tenant' (aislamiento multi-tenant estricto).
    """
    # Insertar otro tenant y usuario si no existen
    from app.models.domain import Tenant, User
    if not db_session.query(Tenant).filter_by(id="other_tenant").first():
        db_session.add(Tenant(id="other_tenant", name="Other Tenant"))
        db_session.commit()

    other_user = db_session.query(User).filter_by(id=99).first()
    if not other_user:
        other_user = User(
            id=99,
            username="other_admin",
            password_hash="mock",
            role="ADMIN",
            is_active=True,
            must_change_password=False,
            tenant_id="other_tenant"
        )
        db_session.add(other_user)
        db_session.commit()

    other_case = CaseFile(
        id=999,
        title="Expediente Other Tenant",
        contract_type="SERVICE",
        status="COMPARING",
        tenant_id="other_tenant"
    )
    db_session.add(other_case)
    db_session.commit()

    other_job = JobRepository.create_job(
        db=db_session,
        case_id=other_case.id,
        tenant_id="other_tenant",
        user_id=other_user.id,
        job_type="QUOTATION_EXTRACTION"
    )

    # El admin_client pertenece a 'mega_tenant'
    res = admin_client.get(f"/cases/jobs/{other_job.job_id}")
    assert res.status_code == 404
    assert res.json()["detail"] == "Job not found"


def test_get_job_status_redis_fallback(admin_client, db_session):
    """
    Verifica que si un job no está en PostgreSQL, consulte el fallback a RQ/Redis.
    La seguridad V6 exige asociar el job con UploadedDocument.processing_job_id
    y comprobar el tenant del expediente.
    Cubre:
    1. Caso autorizado: job asociado a UploadedDocument de un expediente perteneciente al tenant del admin ('mega_tenant') -> 200 OK.
    2. Caso no autorizado: job asociado a UploadedDocument de otro tenant ('other_tenant') -> 404 (sin fugas).
    3. Caso no autorizado: job existente en RQ/Redis pero sin UploadedDocument asociado en BD -> 404.
    """
    from app.models.domain import Tenant

    # Asegurar existencia de 'other_tenant'
    if not db_session.query(Tenant).filter_by(id="other_tenant").first():
        db_session.add(Tenant(id="other_tenant", name="Other Tenant"))
        db_session.commit()

    # 1. Expediente y documento autorizado (mega_tenant)
    auth_case = CaseFile(
        id=710,
        title="Expediente Fallback Autorizado",
        contract_type="SERVICE",
        status="COMPARING",
        tenant_id="mega_tenant"
    )
    auth_doc = UploadedDocument(
        id=710,
        case_id=710,
        document_type="requirement",
        original_filename="doc_auth.pdf",
        stored_path="/tmp/auth.pdf",
        mime_type="application/pdf",
        processing_job_id="mock-legacy-ocr-job-auth"
    )

    # 2. Expediente y documento no autorizado (other_tenant)
    unauth_case = CaseFile(
        id=711,
        title="Expediente Fallback No Autorizado",
        contract_type="SERVICE",
        status="COMPARING",
        tenant_id="other_tenant"
    )
    unauth_doc = UploadedDocument(
        id=711,
        case_id=711,
        document_type="requirement",
        original_filename="doc_unauth.pdf",
        stored_path="/tmp/unauth.pdf",
        mime_type="application/pdf",
        processing_job_id="mock-legacy-ocr-job-unauth"
    )

    db_session.add_all([auth_case, auth_doc, unauth_case, unauth_doc])
    db_session.commit()

    # Mocks de RQ Jobs
    mock_rq_job_auth = Mock()
    mock_rq_job_auth.id = "mock-legacy-ocr-job-auth"
    mock_rq_job_auth.get_status.return_value = "started"
    mock_rq_job_auth.meta = {"progress": 40, "status_message": "Ejecutando Tesseract OCR"}

    mock_rq_job_unauth = Mock()
    mock_rq_job_unauth.id = "mock-legacy-ocr-job-unauth"
    mock_rq_job_unauth.get_status.return_value = "started"
    mock_rq_job_unauth.meta = {"progress": 20, "status_message": "Procesando"}

    mock_rq_job_unlinked = Mock()
    mock_rq_job_unlinked.id = "mock-legacy-ocr-job-unlinked"
    mock_rq_job_unlinked.get_status.return_value = "queued"
    mock_rq_job_unlinked.meta = {"progress": 0}

    def mock_fetch(job_id, connection=None):
        if job_id == "mock-legacy-ocr-job-auth":
            return mock_rq_job_auth
        elif job_id == "mock-legacy-ocr-job-unauth":
            return mock_rq_job_unauth
        elif job_id == "mock-legacy-ocr-job-unlinked":
            return mock_rq_job_unlinked
        from rq.exceptions import NoSuchJobError
        raise NoSuchJobError(f"No such job: {job_id}")

    with patch("app.api.routers.cases.rq.job.Job.fetch", side_effect=mock_fetch):
        # A. Job autorizado -> 200 OK con metadatos
        res_auth = admin_client.get(f"/cases/jobs/{mock_rq_job_auth.id}")
        assert res_auth.status_code == 200
        data_auth = res_auth.json()
        assert data_auth["job_id"] == mock_rq_job_auth.id
        assert data_auth["status"] == "started"
        assert data_auth["progress"] == 40
        assert data_auth["message"] == "Ejecutando Tesseract OCR"

        # B. Job no autorizado (pertenece a other_tenant) -> 404 (sin fugas)
        res_unauth = admin_client.get(f"/cases/jobs/{mock_rq_job_unauth.id}")
        assert res_unauth.status_code == 404
        assert res_unauth.json()["detail"] == "Job not found"

        # C. Job sin UploadedDocument asociado en BD -> 404
        res_unlinked = admin_client.get(f"/cases/jobs/{mock_rq_job_unlinked.id}")
        assert res_unlinked.status_code == 404
        assert res_unlinked.json()["detail"] == "Job not found"
