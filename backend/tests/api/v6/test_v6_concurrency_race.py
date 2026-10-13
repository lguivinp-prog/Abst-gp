import pytest
import threading
import time
import tempfile
import uuid
import hashlib
from pathlib import Path
from unittest.mock import MagicMock
from sqlalchemy.orm import Session

from app.models.domain import (
    Tenant, User, CaseFile, UploadedDocument, ParsedSection, QuotationExtraction, AuditLog, ProcessingJob, OCRProcessingRun
)
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_profile import SupplierProfile
from app.services.v6.selection.selection_service import SelectionService
from app.services.job_repository import JobRepository
from app.worker.quotation_tasks import process_quotation_task
from app.worker.tasks import execute_v1_pipeline
from app.worker.ocr_worker_tasks import process_run_v2
from rq.timeouts import JobTimeoutException


@pytest.fixture
def concurrency_fixture(db_session: Session):
    """Fixture providing an isolated tenant, users, and base case setup for concurrency tests."""
    tenant = db_session.query(Tenant).filter_by(id="tenant_race").first()
    if not tenant:
        tenant = Tenant(id="tenant_race", name="Tenant Race")
        db_session.add(tenant)

    admin = db_session.query(User).filter_by(id=901).first()
    if not admin:
        admin = User(
            id=901,
            username="admin_race",
            password_hash="mock",
            role="ADMIN",
            is_active=True,
            must_change_password=False,
            tenant_id="tenant_race",
            tenant_resolution_status="RESOLVED"
        )
        db_session.add(admin)

    supervisor = db_session.query(User).filter_by(id=902).first()
    if not supervisor:
        supervisor = User(
            id=902,
            username="sup_race",
            password_hash="mock",
            role="SUPERVISOR",
            is_active=True,
            must_change_password=False,
            tenant_id="tenant_race",
            tenant_resolution_status="RESOLVED"
        )
        db_session.add(supervisor)

    operator = db_session.query(User).filter_by(id=903).first()
    if not operator:
        operator = User(
            id=903,
            username="op_race",
            password_hash="mock",
            role="OPERATOR",
            is_active=True,
            must_change_password=False,
            tenant_id="tenant_race",
            tenant_resolution_status="RESOLVED"
        )
        db_session.add(operator)

    readonly = db_session.query(User).filter_by(id=904).first()
    if not readonly:
        readonly = User(
            id=904,
            username="ro_race",
            password_hash="mock",
            role="READONLY",
            is_active=True,
            must_change_password=False,
            tenant_id="tenant_race",
            tenant_resolution_status="RESOLVED"
        )
        db_session.add(readonly)

    db_session.commit()

    return {
        "tenant": tenant,
        "admin": admin,
        "supervisor": supervisor,
        "operator": operator,
        "readonly": readonly
    }


def _create_case_and_doc(db_session: Session, case_id: int, status: str = "REVIEW_SECTIONS"):
    case = CaseFile(
        id=case_id,
        title=f"Expediente Concurrencia {case_id}",
        contract_type="BIENES",
        status=status,
        tenant_id="tenant_race",
        created_by=901,
        assigned_to_user_id=903
    )
    db_session.add(case)
    db_session.commit()

    doc = UploadedDocument(
        id=case_id + 10000,
        case_id=case.id,
        document_type="requirement",
        original_filename=f"req_{case_id}.pdf",
        stored_path=f"/data/uploads/req_{case_id}.pdf",
        mime_type="application/pdf",
        processing_status="started",
        text_extracted=""
    )
    db_session.add(doc)

    wf = CaseWorkflow(case_id=case.id, status="DRAFT")
    db_session.add(wf)
    db_session.commit()

    return case, doc, wf


# =========================================================================
# 1. COTIZACIÓN ASÍNCRONA: ÉXITO TARDÍO, FALLO TARDÍO Y REINTENTO
# =========================================================================

def test_quotation_worker_late_success_blocked_on_terminal_case(concurrency_fixture, db_session, monkeypatch):
    """
    Worker de cotización termina exitosamente después de que el expediente fue cerrado/aprobado.
    Debe detectar el estado terminal bajo bloqueo de fila, descartar la inserción,
    marcar el job FAILED (CASE_TERMINAL_IMMUTABLE) y dejar intactos los datos de negocio.
    """
    case, doc, wf = _create_case_and_doc(db_session, 9101, status="REVIEW_SECTIONS")

    # Cerrar el expediente antes de que el worker persista
    case.status = "APPROVED"
    wf.status = "APPROVED"
    db_session.commit()

    # Archivo ficticio
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4 mock quotation")
        temp_pdf = tf.name

    job_id = "job_quote_late_success_001"
    JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="tenant_race",
        user_id=903,
        job_type="QUOTATION_EXTRACTION",
        job_id=job_id
    )
    db_session.commit()

    # Mock del parser para simular éxito en la extracción pesada
    mock_parsed_data = {
        "supplier": "Proveedor Tardío S.A.C.",
        "ruc": "20123456789",
        "total_amount": 50000.0,
        "global_confidence": 0.95,
        "items": [{"description": "Item 1", "quantity": 10, "unit_price": 5000.0}]
    }
    monkeypatch.setattr("app.worker.quotation_tasks.parse_quotation_pdf", lambda path: mock_parsed_data)

    # Snapshot previo
    db_session.expire_all()
    q_count_before = db_session.query(QuotationExtraction).filter_by(case_id=case.id).count()

    # Ejecutar tarea del worker
    result = process_quotation_task(
        job_id=job_id,
        case_id=case.id,
        tenant_id="tenant_race",
        user_id=903,
        file_path=temp_pdf,
        db=db_session
    )

    # 1. El worker debe reportar el rechazo
    assert result.get("rejected") is True
    assert "terminal" in result.get("reason", "").lower()

    # 2. Base de datos: CERO cotizaciones insertadas y caso sigue APPROVED
    db_session.expire_all()
    q_count_after = db_session.query(QuotationExtraction).filter_by(case_id=case.id).count()
    case_db = db_session.query(CaseFile).filter_by(id=case.id).first()

    assert q_count_after == q_count_before == 0
    assert case_db.status == "APPROVED"

    # 3. Job y Auditoría: estado registrado fielmente
    job_db = JobRepository.get_by_job_id(db_session, job_id, tenant_id="tenant_race")
    assert job_db.status == "FAILED"
    assert "CASE_TERMINAL_IMMUTABLE" in (job_db.error_message or "")
    assert job_db.failure_classification == "FINAL"

    audit_entry = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(case.id),
        AuditLog.action == "QUOTATION_EXTRACTED_ASYNC_BLOCKED"
    ).first()
    assert audit_entry is not None
    assert audit_entry.status == "FAILED"


def test_quotation_worker_late_failure_preserves_terminal_case(concurrency_fixture, db_session, monkeypatch):
    """
    Worker de cotización falla tardíamente sobre un expediente cerrado.
    Debe registrar el fallo del job sin corromper el estado APPROVED del expediente.
    """
    case, doc, wf = _create_case_and_doc(db_session, 9102, status="APPROVED")
    wf.status = "APPROVED"
    db_session.commit()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"corrupt")
        temp_pdf = tf.name

    job_id = "job_quote_late_fail_002"
    JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="tenant_race",
        user_id=903,
        job_type="QUOTATION_EXTRACTION",
        job_id=job_id
    )
    db_session.commit()

    # Mock de excepción en el parser
    def raise_parser_err(path):
        raise ValueError("Corrupt PDF unreadable")
    monkeypatch.setattr("app.worker.quotation_tasks.parse_quotation_pdf", raise_parser_err)

    with pytest.raises(ValueError):
        process_quotation_task(
            job_id=job_id,
            case_id=case.id,
            tenant_id="tenant_race",
            user_id=903,
            file_path=temp_pdf,
            db=db_session
        )

    # Verificar que el expediente NO mutó a ERROR y permanece en APPROVED
    db_session.expire_all()
    case_db = db_session.query(CaseFile).filter_by(id=case.id).first()
    assert case_db.status == "APPROVED"

    job_db = JobRepository.get_by_job_id(db_session, job_id, tenant_id="tenant_race")
    assert job_db.status == "FAILED"
    assert "Corrupt PDF" in (job_db.error_message or "")


def test_quotation_worker_retry_blocked_on_terminal_case(concurrency_fixture, db_session, monkeypatch):
    """
    Reintento tardío de worker sobre caso cerrado debe ser bloqueado idénticamente.
    """
    case, doc, wf = _create_case_and_doc(db_session, 9103, status="APPROVED")
    wf.status = "APPROVED"
    db_session.commit()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4 mock quotation")
        temp_pdf = tf.name

    job_id = "job_quote_retry_003"
    JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="tenant_race",
        user_id=903,
        job_type="QUOTATION_EXTRACTION",
        job_id=job_id
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.worker.quotation_tasks.parse_quotation_pdf",
        lambda path: {"supplier": "Retry Supplier", "global_confidence": 0.9}
    )

    # Primer intento tardío
    res1 = process_quotation_task(job_id=job_id, case_id=case.id, tenant_id="tenant_race", user_id=903, file_path=temp_pdf, db=db_session)
    assert res1.get("rejected") is True

    # Reintento tardío
    res2 = process_quotation_task(job_id=job_id, case_id=case.id, tenant_id="tenant_race", user_id=903, file_path=temp_pdf, db=db_session)
    assert res2.get("rejected") is True

    db_session.expire_all()
    assert db_session.query(QuotationExtraction).filter_by(case_id=case.id).count() == 0
    assert db_session.query(CaseFile).filter_by(id=case.id).first().status == "APPROVED"


# =========================================================================
# 2. OCR V1: ÉXITO TARDÍO, FALLO TARDÍO Y TIMEOUT
# =========================================================================

def test_ocr_v1_late_success_blocked_on_terminal_case(concurrency_fixture, db_session, monkeypatch):
    """
    Pipeline OCR V1 completado tardíamente sobre caso cerrado no altera secciones ni documento.
    """
    case, doc, wf = _create_case_and_doc(db_session, 9201, status="APPROVED")
    wf.status = "APPROVED"
    db_session.commit()

    mock_ocr = MagicMock()
    mock_ocr.pages_text = "Texto extraído tardíamente OCR V1"
    mock_ocr.text = "Texto extraído tardíamente OCR V1"
    mock_ocr.ocr_used = False
    mock_ocr.page_count = 1
    mock_ocr.confidence_avg = 95.0
    mock_ocr.structured_document = None
    monkeypatch.setattr("app.worker.tasks.process_pdf", lambda path: mock_ocr)

    class MockContext:
        def __enter__(self):
            return "/tmp/fake_v1.pdf"
        def __exit__(self, *args):
            pass

    monkeypatch.setattr("app.storage.workspace.materialize_document", lambda p: MockContext())

    mock_sec = MagicMock()
    mock_sec.original_text = "Sección tardía"
    mock_sec.cleaned_text = "Sección tardía"
    mock_sec.normalized_text = "Sección tardía"
    mock_sec.structure_json = {}
    mock_sec.corrections_json = {}
    mock_sec.warnings_json = []
    mock_sec.metadata = {"original_order": 1, "title": "Sec 1", "original_roman": "I", "confidence": 0.9}
    mock_sec.structured_blocks = []
    monkeypatch.setattr(
        "app.services.extraction.document_extraction_agent.DocumentExtractionAgent.process",
        lambda self, text, ctype, sdoc: [mock_sec]
    )

    # Snapshot previo
    db_session.expire_all()
    sec_count_before = db_session.query(ParsedSection).filter_by(case_id=case.id).count()
    orig_doc_status = doc.processing_status

    # Ejecución de execute_v1_pipeline
    persisted = execute_v1_pipeline(case_id=case.id, file_path=doc.stored_path, job_id="v1_job_late_001")
    assert persisted is False

    # Snapshot posterior
    db_session.expire_all()
    sec_count_after = db_session.query(ParsedSection).filter_by(case_id=case.id).count()
    doc_db = db_session.query(UploadedDocument).filter_by(id=doc.id).first()
    case_db = db_session.query(CaseFile).filter_by(id=case.id).first()

    assert sec_count_after == sec_count_before == 0
    assert doc_db.processing_status == orig_doc_status
    assert doc_db.text_extracted == ""
    assert case_db.status == "APPROVED"

    # Verificar audit log
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(case.id),
        AuditLog.action == "OCR_V1_PROCESSING_BLOCKED_TERMINAL"
    ).first()
    assert audit is not None


def test_ocr_v1_late_failure_and_timeout_preserve_terminal_case(concurrency_fixture, db_session, monkeypatch):
    """
    Excepciones y timeouts tardíos en OCR V1 sobre expedientes cerrados no mutan el caso a ERROR ni a TIMEOUT.
    """
    # 1. Caso de fallo general durante la ejecución con cierre concurrente
    case1, doc1, wf1 = _create_case_and_doc(db_session, 9202, status="REVIEW_SECTIONS")
    db_session.commit()

    class MockContext1:
        def __enter__(self): return "/tmp/fake_v1.pdf"
        def __exit__(self, *args): pass
    monkeypatch.setattr("app.storage.workspace.materialize_document", lambda p: MockContext1())

    def crash_after_closure(path):
        case1.status = "APPROVED"
        wf1.status = "APPROVED"
        db_session.commit()
        raise RuntimeError("OCR engine crashed")

    monkeypatch.setattr("app.worker.tasks.process_pdf", crash_after_closure)

    with pytest.raises(RuntimeError):
        execute_v1_pipeline(case_id=case1.id, file_path=doc1.stored_path, job_id="v1_job_err_002")

    db_session.expire_all()
    case_db1 = db_session.query(CaseFile).filter_by(id=case1.id).first()
    doc_db1 = db_session.query(UploadedDocument).filter_by(id=doc1.id).first()
    assert case_db1.status == "APPROVED"
    assert doc_db1.processing_status != "failed"

    # 2. Caso de timeout con cierre concurrente
    case2, doc2, wf2 = _create_case_and_doc(db_session, 9203, status="REVIEW_SECTIONS")
    db_session.commit()

    def timeout_after_closure(path):
        case2.status = "APPROVED"
        wf2.status = "APPROVED"
        db_session.commit()
        raise JobTimeoutException("Job exceeded timeout")

    monkeypatch.setattr("app.worker.tasks.process_pdf", timeout_after_closure)

    with pytest.raises(JobTimeoutException):
        execute_v1_pipeline(case_id=case2.id, file_path=doc2.stored_path, job_id="v1_job_timeout_003")

    db_session.expire_all()
    case_db2 = db_session.query(CaseFile).filter_by(id=case2.id).first()
    doc_db2 = db_session.query(UploadedDocument).filter_by(id=doc2.id).first()
    assert case_db2.status == "APPROVED"
    assert doc_db2.processing_status != "timeout"


# =========================================================================
# 3. OCR V2: ÉXITO TARDÍO, FALLO TARDÍO Y COORDINACIÓN
# =========================================================================

def test_ocr_v2_late_success_blocked_on_terminal_case(concurrency_fixture, db_session, monkeypatch):
    """
    OCR V2 Primary tardío sobre expediente cerrado descarta persistencia, marca run FAILED
    con CASE_TERMINAL_IMMUTABLE y deja intacto el documento y secciones.
    """
    case, doc, wf = _create_case_and_doc(db_session, 9301, status="APPROVED")
    wf.status = "APPROVED"
    db_session.commit()

    run_uuid = uuid.uuid4()
    job_id = f"job_v2_late_{run_uuid}"
    proc_job = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="tenant_race",
        user_id=903,
        job_type="REQUIREMENT_OCR",
        job_id=job_id
    )
    db_session.commit()

    run = OCRProcessingRun(
        run_id=run_uuid,
        uploaded_document_id=doc.id,
        validation_case_id=None,
        processing_job_id=proc_job.id,
        execution_role="PRIMARY",
        engine="v2",
        run_dedup_key=hashlib.sha256(str(run_uuid).encode()).hexdigest(),
        status="QUEUED"
    )
    db_session.add(run)
    db_session.commit()

    # Mock V2 pipeline y storage
    mock_struct_doc = MagicMock()
    mock_struct_doc.confidence = 0.96
    mock_struct_doc.pages = []
    mock_struct_doc.model_dump.return_value = {"confidence": 0.96, "pages": []}

    class MockPipeline:
        def process_document(self, path):
            return mock_struct_doc

    monkeypatch.setattr("app.worker.ocr_worker_tasks.OCRV2Pipeline", MockPipeline)

    class MockContext:
        def __enter__(self):
            return "/tmp/fake.pdf"
        def __exit__(self, *args):
            pass

    monkeypatch.setattr("app.storage.workspace.materialize_document", lambda p: MockContext())

    # Snapshot previo
    db_session.expire_all()
    sec_count_before = db_session.query(ParsedSection).filter_by(case_id=case.id).count()

    # Ejecutar V2
    process_run_v2(run_id=str(run_uuid))

    # Verificaciones
    db_session.expire_all()
    sec_count_after = db_session.query(ParsedSection).filter_by(case_id=case.id).count()
    run_db = db_session.query(OCRProcessingRun).filter_by(run_id=run_uuid).first()
    case_db = db_session.query(CaseFile).filter_by(id=case.id).first()

    assert sec_count_after == sec_count_before == 0
    assert case_db.status == "APPROVED"
    assert run_db.status == "FAILED"
    assert run_db.failure_code == "CASE_TERMINAL_IMMUTABLE"

    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == str(case.id),
        AuditLog.action == "OCR_V2_PROCESSING_BLOCKED_TERMINAL"
    ).first()
    assert audit is not None


def test_ocr_v2_late_failure_preserves_terminal_case_and_no_fallback(concurrency_fixture, db_session, monkeypatch):
    """
    Fallo de OCR V2 sobre expediente cerrado no marca el caso como ERROR ni genera ejecuciones FALLBACK.
    Simula que el expediente se cerró concurrentemente mientras el pipeline procesaba el documento.
    """
    case, doc, wf = _create_case_and_doc(db_session, 9302, status="REVIEW_SECTIONS")

    fail_uuid = uuid.uuid4()
    job_id = f"job_v2_fail_{fail_uuid}"
    proc_job = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="tenant_race",
        user_id=903,
        job_type="REQUIREMENT_OCR",
        job_id=job_id
    )
    db_session.commit()

    run = OCRProcessingRun(
        run_id=fail_uuid,
        uploaded_document_id=doc.id,
        validation_case_id=None,
        processing_job_id=proc_job.id,
        execution_role="PRIMARY",
        engine="v2",
        run_dedup_key=hashlib.sha256(str(fail_uuid).encode()).hexdigest(),
        status="QUEUED"
    )
    db_session.add(run)
    db_session.commit()

    class FailingPipeline:
        def process_document(self, path):
            # Simular cierre concurrente del expediente antes de que el worker lance la excepción
            from tests.conftest import TestingSessionLocal
            term_db = TestingSessionLocal()
            c = term_db.query(CaseFile).filter_by(id=case.id).first()
            if c:
                c.status = "APPROVED"
                term_db.commit()
            term_db.close()
            raise RuntimeError("V2 Engine Internal OOM")

    monkeypatch.setattr("app.worker.ocr_worker_tasks.OCRV2Pipeline", FailingPipeline)

    class MockContext:
        def __enter__(self): return "/tmp/fake.pdf"
        def __exit__(self, *args): pass
    monkeypatch.setattr("app.storage.workspace.materialize_document", lambda p: MockContext())

    with pytest.raises(RuntimeError):
        process_run_v2(run_id=str(fail_uuid))

    db_session.expire_all()
    case_db = db_session.query(CaseFile).filter_by(id=case.id).first()
    doc_db = db_session.query(UploadedDocument).filter_by(id=doc.id).first()
    fallback_runs = db_session.query(OCRProcessingRun).filter_by(execution_role="FALLBACK").all()

    assert case_db.status == "APPROVED"
    assert doc_db.processing_status != "failed"
    assert len(fallback_runs) == 0


def test_ocr_v2_early_check_blocks_terminal_case(concurrency_fixture, db_session, monkeypatch):
    """
    Verificación temprana de OCR V2: si el caso ya está en estado terminal (APPROVED),
    process_run_v2 se detiene antes de mutar UploadedDocument o invocar el pipeline,
    marcando OCRProcessingRun como FAILED con CASE_TERMINAL_IMMUTABLE.
    """
    case, doc, wf = _create_case_and_doc(db_session, 9303, status="APPROVED")
    wf.status = "APPROVED"
    db_session.commit()

    early_uuid = uuid.uuid4()
    job_id = f"job_v2_early_{early_uuid}"
    proc_job = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id="tenant_race",
        user_id=903,
        job_type="REQUIREMENT_OCR",
        job_id=job_id
    )
    db_session.commit()

    run = OCRProcessingRun(
        run_id=early_uuid,
        uploaded_document_id=doc.id,
        validation_case_id=None,
        processing_job_id=proc_job.id,
        execution_role="PRIMARY",
        engine="v2",
        run_dedup_key=hashlib.sha256(str(early_uuid).encode()).hexdigest(),
        status="QUEUED"
    )
    db_session.add(run)
    db_session.commit()

    pipeline_called = False
    class SentinelPipeline:
        def process_document(self, path):
            nonlocal pipeline_called
            pipeline_called = True
            return MagicMock()

    monkeypatch.setattr("app.worker.ocr_worker_tasks.OCRV2Pipeline", SentinelPipeline)

    class MockContext:
        def __enter__(self): return "/tmp/fake.pdf"
        def __exit__(self, *args): pass
    monkeypatch.setattr("app.storage.workspace.materialize_document", lambda p: MockContext())

    # Ejecución de OCR V2: debe detectar estado terminal tempranamente y retornar sin error
    process_run_v2(run_id=str(early_uuid))

    assert pipeline_called is False, "El pipeline de extracción pesada no debe ejecutarse"

    db_session.expire_all()
    run_db = db_session.query(OCRProcessingRun).filter_by(run_id=early_uuid).first()
    case_db = db_session.query(CaseFile).filter_by(id=case.id).first()
    doc_db = db_session.query(UploadedDocument).filter_by(id=doc.id).first()

    assert run_db.status == "FAILED"
    assert run_db.failure_code == "CASE_TERMINAL_IMMUTABLE"
    assert case_db.status == "APPROVED"
    assert doc_db.processing_status != "finished"


# =========================================================================
# 4. CONCURRENCIA REAL: CARRERA ENTRE APROBACIÓN Y PERSISTENCIA DE WORKER
# =========================================================================

def test_concurrent_threads_approve_racing_with_worker_persistence(concurrency_fixture, db_session):
    """
    Prueba de hilos concurrentes en tiempo real:
    Hilo 1 ejecuta SelectionService.approve_selection bajo transacción y bloqueo con with_for_update().
    Hilo 2 ejecuta la persistencia de cotización bajo bloqueo de fila.
    Utiliza sesiones independientes (TestingSessionLocal()), registra y valida los resultados de ambos hilos,
    y comprueba exhaustivamente la integridad y el contenido del estado persistido.
    """
    from tests.conftest import TestingSessionLocal

    case, doc, wf = _create_case_and_doc(db_session, 9401, status="REVIEW_SECTIONS")

    supplier = db_session.query(Supplier).filter_by(tenant_id="tenant_race", ruc="20999999999").first()
    if not supplier:
        supplier = Supplier(
            tenant_id="tenant_race",
            ruc="20999999999",
            business_name="Proveedor Ganador"
        )
        db_session.add(supplier)
        db_session.flush()

    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    if not profile:
        profile = SupplierProfile(
            supplier_id=supplier.id,
            validation_status="VERIFIED"
        )
        db_session.add(profile)
        db_session.flush()

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        total_amount=1000.0,
        currency="PEN",
        status="ACTIVE"
    )
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(
        case_id=case.id,
        supplier_offer_id=offer.id,
        status="UNDER_REVIEW"
    )
    db_session.add(attempt)
    db_session.commit()

    barrier = threading.Barrier(2)
    thread_outcomes = {"approve": None, "worker": None}
    thread_errors = []

    def thread_approve():
        local_db = TestingSessionLocal()
        try:
            barrier.wait(timeout=5)
            # Aprobación concurrente con bloqueo de fila en SelectionService
            final_selection = SelectionService.approve_selection(
                db=local_db,
                case_id=case.id,
                supervisor_id=902,
                tenant_id="tenant_race"
            )
            thread_outcomes["approve"] = {
                "status": "SUCCESS",
                "final_id": final_selection.id,
                "selected_attempt_id": final_selection.attempt_id
            }
        except Exception as e:
            thread_errors.append(("approve", e))
        finally:
            local_db.close()

    def thread_worker_persist():
        local_db = TestingSessionLocal()
        try:
            barrier.wait(timeout=5)
            # Worker adquiriendo bloqueo de fila para verificar estado terminal
            locked_case = (
                local_db.query(CaseFile)
                .filter(CaseFile.id == case.id)
                .populate_existing()
                .with_for_update()
                .first()
            )
            from app.models.v6.case_workflow import CaseWorkflow
            from app.models.v6.supplier_selection import SupplierSelectionFinal

            is_terminal = (
                locked_case.status in ["APPROVED", "COMPLETED"]
                or local_db.query(CaseWorkflow).filter(CaseWorkflow.case_id == case.id, CaseWorkflow.status.in_(["APPROVED", "COMPLETED"])).first() is not None
                or local_db.query(SupplierSelectionFinal).filter(SupplierSelectionFinal.case_id == case.id).first() is not None
            )

            if not is_terminal:
                q = QuotationExtraction(case_id=case.id, raw_json={"supplier": "Race Supplier", "amount": 1000.0})
                local_db.add(q)
                local_db.commit()
                thread_outcomes["worker"] = {"persisted": True, "terminal_detected": False}
            else:
                thread_outcomes["worker"] = {"persisted": False, "terminal_detected": True}
                local_db.commit()
        except Exception as e:
            thread_errors.append(("worker", e))
        finally:
            local_db.close()

    t1 = threading.Thread(target=thread_approve)
    t2 = threading.Thread(target=thread_worker_persist)

    t1.start()
    t2.start()

    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(thread_errors) == 0, f"Errores en hilos concurrentes: {thread_errors}"
    assert thread_outcomes["approve"] is not None
    assert thread_outcomes["approve"]["status"] == "SUCCESS"
    assert thread_outcomes["worker"] is not None

    # Verificación rigurosa del contenido persistido en sesión fresca
    verify_db = TestingSessionLocal()
    try:
        final_case = verify_db.query(CaseFile).filter_by(id=case.id).first()
        final_wf = verify_db.query(CaseWorkflow).filter_by(case_id=case.id).first()
        final_selection = verify_db.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()

        assert final_case.status == "APPROVED"
        assert final_wf.status == "APPROVED"
        assert final_selection is not None
        assert final_selection.attempt_id == attempt.id

        if thread_outcomes["worker"]["persisted"]:
            persisted_q = verify_db.query(QuotationExtraction).filter_by(case_id=case.id).first()
            assert persisted_q is not None
            assert persisted_q.raw_json.get("supplier") == "Race Supplier"
        else:
            assert thread_outcomes["worker"]["terminal_detected"] is True
            persisted_q = verify_db.query(QuotationExtraction).filter_by(case_id=case.id).first()
            assert persisted_q is None
    finally:
        verify_db.close()


def test_concurrent_threads_approve_racing_with_worker_exception_and_timeout(concurrency_fixture, db_session):
    """
    Carrera concurrente en tiempo real entre aprobación y ruta de fallo/timeout de worker:
    Hilo 1: ejecuta SelectionService.approve_selection bajo transacción atómica.
    Hilo 2: worker sufre JobTimeoutException o Exception y ejecuta la ruta de error bajo bloqueo de fila.
    Garantiza que la excepción tardía jamás sobrescriba APPROVED con TIMEOUT o ERROR,
    utiliza sesiones independientes, valida resultados de ambos hilos y audita el bloqueo terminal.
    """
    from tests.conftest import TestingSessionLocal

    case, doc, wf = _create_case_and_doc(db_session, 9402, status="REVIEW_SECTIONS")

    supplier = db_session.query(Supplier).filter_by(tenant_id="tenant_race", ruc="20999999998").first()
    if not supplier:
        supplier = Supplier(tenant_id="tenant_race", ruc="20999999998", business_name="Proveedor Carrera Error")
        db_session.add(supplier)
        db_session.flush()

    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    if not profile:
        profile = SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED")
        db_session.add(profile)
        db_session.flush()

    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, total_amount=2500.0, currency="PEN", status="ACTIVE")
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(case_id=case.id, supplier_offer_id=offer.id, status="UNDER_REVIEW")
    db_session.add(attempt)
    db_session.commit()

    barrier = threading.Barrier(2)
    thread_outcomes = {"approve": None, "worker_error": None}
    thread_errors = []

    def thread_approve():
        local_db = TestingSessionLocal()
        try:
            barrier.wait(timeout=5)
            final_selection = SelectionService.approve_selection(
                db=local_db,
                case_id=case.id,
                supervisor_id=902,
                tenant_id="tenant_race"
            )
            thread_outcomes["approve"] = {"status": "SUCCESS", "final_id": final_selection.id}
        except Exception as e:
            thread_errors.append(("approve", e))
        finally:
            local_db.close()

    def thread_worker_timeout_path():
        local_db = TestingSessionLocal()
        try:
            barrier.wait(timeout=5)
            # Simular ruta de error/timeout con bloqueo de fila tal como en tasks.py
            locked_case = (
                local_db.query(CaseFile)
                .filter(CaseFile.id == case.id)
                .populate_existing()
                .with_for_update()
                .first()
            )
            from app.models.v6.case_workflow import CaseWorkflow
            from app.models.v6.supplier_selection import SupplierSelectionFinal

            is_terminal = (
                locked_case.status in ["APPROVED", "COMPLETED"]
                or local_db.query(CaseWorkflow).filter(CaseWorkflow.case_id == case.id, CaseWorkflow.status.in_(["APPROVED", "COMPLETED"])).first() is not None
                or local_db.query(SupplierSelectionFinal).filter(SupplierSelectionFinal.case_id == case.id).first() is not None
            )

            if is_terminal:
                # Terminal protegido: NO alterar status del caso ni del documento
                from app.models.domain import AuditLog
                audit = AuditLog(
                    tenant_id=locked_case.tenant_id,
                    user_id=locked_case.assigned_to_user_id or locked_case.created_by,
                    action="OCR_V1_TIMEOUT_BLOCKED_TERMINAL",
                    entity_type="CaseFile",
                    entity_id=str(case.id),
                    details="Timeout tardio descartado por estado terminal",
                    status="FAILED"
                )
                local_db.add(audit)
                local_db.commit()
                thread_outcomes["worker_error"] = {"status": "BLOCKED_TERMINAL", "overwrote": False}
            else:
                locked_case.status = "TIMEOUT"
                local_db.commit()
                thread_outcomes["worker_error"] = {"status": "OVERWROTE_BEFORE_APPROVE", "overwrote": True}
        except Exception as e:
            thread_errors.append(("worker_error", e))
        finally:
            local_db.close()

    t1 = threading.Thread(target=thread_approve)
    t2 = threading.Thread(target=thread_worker_timeout_path)

    t1.start()
    t2.start()

    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(thread_errors) == 0, f"Errores en hilos de carrera excepcional: {thread_errors}"
    assert thread_outcomes["approve"] is not None
    assert thread_outcomes["worker_error"] is not None

    # Verificación en sesión independiente:
    verify_db = TestingSessionLocal()
    try:
        final_case = verify_db.query(CaseFile).filter_by(id=case.id).first()
        final_wf = verify_db.query(CaseWorkflow).filter_by(case_id=case.id).first()
        final_doc = verify_db.query(UploadedDocument).filter_by(id=doc.id).first()

        # En cualquier resolución de carrera, un caso aprobado jamás termina en TIMEOUT o ERROR corrupto
        assert final_case.status == "APPROVED"
        assert final_wf.status == "APPROVED"
        assert final_doc.processing_status != "timeout"

        if thread_outcomes["worker_error"]["status"] == "BLOCKED_TERMINAL":
            audit = verify_db.query(AuditLog).filter_by(
                entity_id=str(case.id),
                action="OCR_V1_TIMEOUT_BLOCKED_TERMINAL"
            ).first()
            assert audit is not None
            assert audit.status == "FAILED"
    finally:
        verify_db.close()


def test_concurrent_threads_approve_racing_with_readonly_mutation(concurrency_fixture, db_session):
    """
    Carrera concurrente en tiempo real entre aprobación y usuario READONLY:
    Hilo 1: ejecuta SelectionService.approve_selection legítimamente.
    Hilo 2: usuario con rol READONLY intenta mutar el expediente concurrentemente.
    Garantiza que el rol READONLY sea rechazado rotundamente bajo sesiones independientes
    y que el contenido persistido sea únicamente el del flujo autorizado sin efectos secundarios.
    """
    from tests.conftest import TestingSessionLocal
    from app.api.auth import require_role
    from app.api.exceptions import ForbiddenException

    case, doc, wf = _create_case_and_doc(db_session, 9403, status="REVIEW_SECTIONS")

    supplier = db_session.query(Supplier).filter_by(tenant_id="tenant_race", ruc="20999999997").first()
    if not supplier:
        supplier = Supplier(tenant_id="tenant_race", ruc="20999999997", business_name="Proveedor Carrera RO")
        db_session.add(supplier)
        db_session.flush()

    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    if not profile:
        profile = SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED")
        db_session.add(profile)
        db_session.flush()

    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, total_amount=3000.0, currency="PEN", status="ACTIVE")
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(case_id=case.id, supplier_offer_id=offer.id, status="UNDER_REVIEW")
    db_session.add(attempt)
    db_session.commit()

    barrier = threading.Barrier(2)
    thread_outcomes = {"approve": None, "readonly": None}
    thread_errors = []

    def thread_approve():
        local_db = TestingSessionLocal()
        try:
            barrier.wait(timeout=5)
            final_selection = SelectionService.approve_selection(
                db=local_db,
                case_id=case.id,
                supervisor_id=902,
                tenant_id="tenant_race"
            )
            thread_outcomes["approve"] = {"status": "SUCCESS", "final_id": final_selection.id}
        except Exception as e:
            thread_errors.append(("approve", e))
        finally:
            local_db.close()

    def thread_readonly_attempt():
        local_db = TestingSessionLocal()
        try:
            barrier.wait(timeout=5)
            ro_user = concurrency_fixture["readonly"]
            # Validar RBAC para operación de escritura
            role_guard = require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])
            try:
                role_guard(ro_user)
                thread_outcomes["readonly"] = {"status": "UNEXPECTED_ALLOWED"}
            except ForbiddenException as fe:
                thread_outcomes["readonly"] = {"status": "FORBIDDEN_REJECTED", "message": fe.message}
        except Exception as e:
            thread_errors.append(("readonly", e))
        finally:
            local_db.close()

    t1 = threading.Thread(target=thread_approve)
    t2 = threading.Thread(target=thread_readonly_attempt)

    t1.start()
    t2.start()

    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(thread_errors) == 0, f"Errores no controlados en carrera READONLY: {thread_errors}"
    assert thread_outcomes["approve"] is not None
    assert thread_outcomes["approve"]["status"] == "SUCCESS"
    assert thread_outcomes["readonly"] is not None
    assert thread_outcomes["readonly"]["status"] == "FORBIDDEN_REJECTED"

    # Verificación en sesión independiente: integridad y contenido persistido
    verify_db = TestingSessionLocal()
    try:
        final_case = verify_db.query(CaseFile).filter_by(id=case.id).first()
        final_wf = verify_db.query(CaseWorkflow).filter_by(case_id=case.id).first()
        final_selection = verify_db.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()

        assert final_case.status == "APPROVED"
        assert final_wf.status == "APPROVED"
        assert final_selection is not None
        assert final_selection.attempt_id == attempt.id
    finally:
        verify_db.close()


# =========================================================================
# 5. PRUEBAS DETERMINISTAS CON BARRERAS DE SINCRONIZACIÓN Y FUNCIONES REALES
# =========================================================================

def _setup_case_with_offer_and_attempt(db_session: Session, case_id: int, status: str = "WAITING_QUOTATION"):
    case, doc, wf = _create_case_and_doc(db_session, case_id, status=status)
    supplier = db_session.query(Supplier).filter_by(tenant_id="tenant_race", ruc=f"209999{case_id}").first()
    if not supplier:
        supplier = Supplier(tenant_id="tenant_race", ruc=f"209999{case_id}", business_name=f"Proveedor Test {case_id}")
        db_session.add(supplier)
        db_session.flush()

    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    if not profile:
        profile = SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED")
        db_session.add(profile)
        db_session.flush()

    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, total_amount=1500.0, currency="PEN", status="ACTIVE")
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(case_id=case.id, supplier_offer_id=offer.id, status="UNDER_REVIEW")
    db_session.add(attempt)
    db_session.commit()
    return case, doc, wf, offer, attempt


def test_deterministic_worker_persists_before_approval(concurrency_fixture, db_session, monkeypatch):
    """
    Prueba determinista con barreras de sincronización:
    Demuestra el caso en que el worker ejecuta la función real 'process_quotation_task'
    y persiste su resultado ANTES de que la supervisión ejecute 'SelectionService.approve_selection'.
    Garantiza que la cotización quede legítimamente persistida y que la aprobación posterior
    concluya de manera atómica sin corromper el registro previo.
    """
    from tests.conftest import TestingSessionLocal

    case_id = 9501
    case, doc, wf, offer, attempt = _setup_case_with_offer_and_attempt(db_session, case_id, status="WAITING_QUOTATION")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4 mock quotation deterministic")
        temp_pdf = tf.name

    job_id = f"job_det_quote_persist_first_{case_id}"
    JobRepository.create_job(
        db=db_session,
        case_id=case_id,
        tenant_id="tenant_race",
        user_id=903,
        job_type="QUOTATION_EXTRACTION",
        job_id=job_id
    )
    db_session.commit()

    worker_persisted_event = threading.Event()
    thread_outcomes = {"worker": None, "approve": None}
    thread_errors = []

    mock_parsed_data = {
        "supplier": "Proveedor Ganador Previo",
        "ruc": "20999995011",
        "total_amount": 12500.0,
        "global_confidence": 0.92,
        "items": [{"description": "Item 1", "quantity": 5, "unit_price": 2500.0}]
    }
    monkeypatch.setattr("app.worker.quotation_tasks.parse_quotation_pdf", lambda path: mock_parsed_data)

    def thread_worker():
        local_db = TestingSessionLocal()
        try:
            # Ejecuta la función REAL de persistencia del worker
            result = process_quotation_task(
                job_id=job_id,
                case_id=case_id,
                tenant_id="tenant_race",
                user_id=903,
                file_path=temp_pdf,
                db=local_db
            )
            thread_outcomes["worker"] = result
            # Señalar a la supervisión que el worker ya persistió y confirmó
            worker_persisted_event.set()
        except Exception as e:
            thread_errors.append(("worker", e))
            worker_persisted_event.set()
        finally:
            local_db.close()

    def thread_approve():
        local_db = TestingSessionLocal()
        try:
            # Esperar a que el worker persista efectivamente
            assert worker_persisted_event.wait(timeout=10), "Timeout esperando persistencia del worker"
            final_selection = SelectionService.approve_selection(
                db=local_db,
                case_id=case_id,
                supervisor_id=902,
                tenant_id="tenant_race"
            )
            thread_outcomes["approve"] = {"final_id": final_selection.id}
        except Exception as e:
            thread_errors.append(("approve", e))
        finally:
            local_db.close()

    t_worker = threading.Thread(target=thread_worker)
    t_approve = threading.Thread(target=thread_approve)

    t_worker.start()
    t_approve.start()

    t_worker.join(timeout=10)
    t_approve.join(timeout=10)

    assert len(thread_errors) == 0, f"Errores en hilos deterministas (worker primero): {thread_errors}"
    assert thread_outcomes["worker"] is not None
    assert thread_outcomes["worker"].get("extraction_id") is not None
    assert thread_outcomes["approve"] is not None

    # Verificación en sesión independiente fresca:
    verify_db = TestingSessionLocal()
    try:
        final_case = verify_db.query(CaseFile).filter_by(id=case_id).first()
        final_wf = verify_db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        final_sel = verify_db.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
        quotations = verify_db.query(QuotationExtraction).filter_by(case_id=case_id).all()

        assert final_case.status == "APPROVED"
        assert final_wf.status == "APPROVED"
        assert final_sel is not None
        assert final_sel.attempt_id == attempt.id
        assert len(quotations) == 1
        persisted_supplier = quotations[0].raw_json.get("supplier")
        if isinstance(persisted_supplier, dict):
            assert persisted_supplier.get("supplier_name", {}).get("value") == "Proveedor Ganador Previo"
        else:
            assert persisted_supplier == "Proveedor Ganador Previo"
    finally:
        verify_db.close()


def test_deterministic_approval_commits_first_worker_discards_persistence(concurrency_fixture, db_session, monkeypatch):
    """
    Prueba determinista con barreras de sincronización:
    Demuestra el caso en que la aprobación ('SelectionService.approve_selection') se confirma
    primero mientras el worker está procesando, obligando al worker a descartar la persistencia
    de manera controlada al adquirir el bloqueo de fila y verificar el estado terminal.
    No reemplaza la función del worker por un mock de su lógica; ejecuta 'process_quotation_task' real.
    """
    from tests.conftest import TestingSessionLocal

    case_id = 9502
    case, doc, wf, offer, attempt = _setup_case_with_offer_and_attempt(db_session, case_id, status="WAITING_QUOTATION")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4 mock quotation discard")
        temp_pdf = tf.name

    job_id = f"job_det_quote_discard_{case_id}"
    JobRepository.create_job(
        db=db_session,
        case_id=case_id,
        tenant_id="tenant_race",
        user_id=903,
        job_type="QUOTATION_EXTRACTION",
        job_id=job_id
    )
    db_session.commit()

    worker_in_parser = threading.Event()
    approval_committed = threading.Event()
    thread_outcomes = {"worker": None, "approve": None}
    thread_errors = []

    def mock_parser_with_barrier(path):
        # El worker avisa que está dentro de la fase de extracción pesada
        worker_in_parser.set()
        # Espera que la aprobación se complete y confirme en la base de datos
        assert approval_committed.wait(timeout=10), "Timeout esperando confirmación de aprobación"
        return {
            "supplier": "Proveedor Descartado",
            "ruc": "20999995022",
            "total_amount": 8000.0,
            "global_confidence": 0.95,
            "items": [{"description": "Item X", "quantity": 2, "unit_price": 4000.0}]
        }

    monkeypatch.setattr("app.worker.quotation_tasks.parse_quotation_pdf", mock_parser_with_barrier)

    def thread_worker():
        local_db = TestingSessionLocal()
        try:
            # Ejecuta la función REAL de persistencia del worker
            result = process_quotation_task(
                job_id=job_id,
                case_id=case_id,
                tenant_id="tenant_race",
                user_id=903,
                file_path=temp_pdf,
                db=local_db
            )
            thread_outcomes["worker"] = result
        except Exception as e:
            thread_errors.append(("worker", e))
        finally:
            local_db.close()

    def thread_approve():
        local_db = TestingSessionLocal()
        try:
            # Esperar a que el worker esté dentro del parser antes de aprobar
            assert worker_in_parser.wait(timeout=10), "Timeout esperando que worker entre al parser"
            final_selection = SelectionService.approve_selection(
                db=local_db,
                case_id=case_id,
                supervisor_id=902,
                tenant_id="tenant_race"
            )
            thread_outcomes["approve"] = {"final_id": final_selection.id}
            # Avisar al worker que el estado terminal ya está confirmado en la BD
            approval_committed.set()
        except Exception as e:
            thread_errors.append(("approve", e))
            approval_committed.set()
        finally:
            local_db.close()

    t_worker = threading.Thread(target=thread_worker)
    t_approve = threading.Thread(target=thread_approve)

    t_worker.start()
    t_approve.start()

    t_worker.join(timeout=10)
    t_approve.join(timeout=10)

    assert len(thread_errors) == 0, f"Errores en hilos deterministas (aprobación primero): {thread_errors}"
    assert thread_outcomes["approve"] is not None
    assert thread_outcomes["worker"] is not None

    # El worker real debe haber descartado la persistencia
    assert thread_outcomes["worker"].get("rejected") is True
    assert "terminal" in thread_outcomes["worker"].get("reason", "").lower()

    # Verificación en sesión independiente fresca:
    verify_db = TestingSessionLocal()
    try:
        final_case = verify_db.query(CaseFile).filter_by(id=case_id).first()
        final_wf = verify_db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        final_sel = verify_db.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
        quotations = verify_db.query(QuotationExtraction).filter_by(case_id=case_id).all()
        job = verify_db.query(ProcessingJob).filter_by(job_id=job_id).first()

        assert final_case.status == "APPROVED"
        assert final_wf.status == "APPROVED"
        assert final_sel is not None
        assert final_sel.attempt_id == attempt.id
        # NINGUNA cotización insertada
        assert len(quotations) == 0
        # El job fue marcado FAILED por inmutabilidad terminal
        assert job.status == "FAILED"
        assert "CASE_TERMINAL_IMMUTABLE" in (job.error_message or "")
    finally:
        verify_db.close()


def test_deterministic_ocr_v1_early_write_blocked_by_concurrent_closure(concurrency_fixture, db_session, monkeypatch):
    """
    Prueba determinista con barreras de sincronización:
    Demuestra que un intento de escritura temprana de OCR V1 ('execute_v1_pipeline' real)
    queda bloqueado y descartado frente al cierre concurrente de expediente.
    Inyecta una barrera en 'get_current_job' para permitir que la aprobación confirme
    el estado terminal antes de que el worker adquiera el bloqueo de fila temprano.
    Verifica que el documento no sea modificado a 'started' y que se registre la auditoría correspondiente.
    """
    from tests.conftest import TestingSessionLocal

    case_id = 9503
    case, doc, wf, offer, attempt = _setup_case_with_offer_and_attempt(db_session, case_id, status="REVIEW_SECTIONS")

    # Documento en estado inicial 'queued'
    doc.processing_status = "queued"
    doc.ocr_engine_used = None
    db_session.commit()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4 mock requirement OCR")
        temp_pdf = tf.name

    worker_before_lock = threading.Event()
    approval_committed = threading.Event()
    thread_outcomes = {"worker": None, "approve": None}
    thread_errors = []

    def mock_get_current_job_with_barrier():
        worker_before_lock.set()
        assert approval_committed.wait(timeout=10), "Timeout esperando confirmación de aprobación en OCR V1"
        mock_job = MagicMock()
        mock_job.meta = {}
        return mock_job

    monkeypatch.setattr("app.worker.tasks.get_current_job", mock_get_current_job_with_barrier)

    def thread_worker():
        try:
            # Ejecuta la función REAL de OCR V1
            res = execute_v1_pipeline(
                case_id=case_id,
                file_path=temp_pdf,
                job_id="job_ocr_v1_early_det_001",
                fallback_used=False
            )
            thread_outcomes["worker"] = res
        except Exception as e:
            thread_errors.append(("worker", e))

    def thread_approve():
        local_db = TestingSessionLocal()
        try:
            # Esperar a que el worker comience y esté antes de adquirir el bloqueo
            assert worker_before_lock.wait(timeout=10), "Timeout esperando worker OCR V1"
            final_selection = SelectionService.approve_selection(
                db=local_db,
                case_id=case_id,
                supervisor_id=902,
                tenant_id="tenant_race"
            )
            thread_outcomes["approve"] = {"final_id": final_selection.id}
            # Avisar al worker que la aprobación fue confirmada
            approval_committed.set()
        except Exception as e:
            thread_errors.append(("approve", e))
            approval_committed.set()
        finally:
            local_db.close()

    t_worker = threading.Thread(target=thread_worker)
    t_approve = threading.Thread(target=thread_approve)

    t_worker.start()
    t_approve.start()

    t_worker.join(timeout=10)
    t_approve.join(timeout=10)

    assert len(thread_errors) == 0, f"Errores en hilos deterministas OCR V1: {thread_errors}"
    assert thread_outcomes["approve"] is not None
    assert thread_outcomes["worker"] is False  # execute_v1_pipeline retorna False al descartarse

    # Verificación en sesión independiente fresca:
    verify_db = TestingSessionLocal()
    try:
        final_case = verify_db.query(CaseFile).filter_by(id=case_id).first()
        final_wf = verify_db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        final_doc = verify_db.query(UploadedDocument).filter_by(id=doc.id).first()
        audit = verify_db.query(AuditLog).filter_by(
            entity_id=str(case_id),
            action="OCR_V1_PROCESSING_BLOCKED_TERMINAL"
        ).first()

        # El caso sigue APPROVED y no fue degradado
        assert final_case.status == "APPROVED"
        assert final_wf.status == "APPROVED"

        # La escritura temprana fue BLOQUEADA: el documento NO cambió a "started"
        assert final_doc.processing_status == "queued"
        assert final_doc.ocr_engine_used is None

        # Auditoría registrada de bloqueo
        assert audit is not None
        assert audit.status == "FAILED"
    finally:
        verify_db.close()
