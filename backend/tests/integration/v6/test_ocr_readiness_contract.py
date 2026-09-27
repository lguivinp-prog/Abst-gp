import pytest
from unittest.mock import patch, MagicMock
from app.models.domain import CaseFile, UploadedDocument, Tenant
from app.worker.ocr_worker_tasks import process_run_v2
from app.services.extraction_engine.models.document import StructuredDocument, DocumentPage, OcrElement
import uuid
from datetime import datetime, timezone

@pytest.fixture
def mock_structured_document():
    page = DocumentPage(
        page_number=1,
        width=800,
        height=1000,
        elements=[
            OcrElement(text="TEST REQUIREMENT", confidence=0.99, x=10, y=10, width=100, height=20, page_number=1)
        ]
    )
    from app.services.extraction_engine.models.document import DocumentBlock

    block = DocumentBlock(
        type="section",
        original_text="I. GENERAL",
        normalized_text="GENERAL",
        confidence=0.99,
        page=1,
        content="TEST REQUIREMENT"
    )

    doc = StructuredDocument(
        pages=[page],
        blocks=[block],
        tables=[],
        entities=[],
        confidence=0.95,
        metadata={"evaluation": {"score": 0.95}}
    )
    return doc

def test_worker_persists_text_for_v6_extraction_readiness(db_session, mock_structured_document):
    # Setup test case
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        db_session.commit()

    from app.models.domain import User
    user = db_session.query(User).filter_by(id=1).first()
    if not user:
        user = User(id=1, username="test_user", tenant_id="mega_tenant", password_hash="dummy")
        db_session.add(user)
        db_session.commit()

    case = CaseFile(
        tenant_id="mega_tenant",
        title="Test Case OCR Readiness",
        contract_type="Bienes",
        status="PROCESSING_REQUIREMENT",
        created_by=user.id
    )
    db_session.add(case)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="test_req.pdf",
        stored_path="test_req.pdf",
        mime_type="application/pdf",
        processing_status="pending"
    )
    db_session.add(doc)
    db_session.commit()

    from app.models.domain import OCRProcessingRun, ProcessingJob
    job = ProcessingJob(
        tenant_id="mega_tenant",
        job_type="REQUIREMENT_OCR",
        worker_type="abst_worker_ocr",
        status="QUEUED"
    )
    db_session.add(job)
    db_session.commit()

    run = OCRProcessingRun(
        run_id=uuid.uuid4(),
        uploaded_document_id=doc.id,
        processing_job_id=job.id,
        engine="v2",
        execution_role="PRIMARY",
        status="QUEUED",
        run_dedup_key="a"*64
    )
    db_session.add(run)
    db_session.commit()

    # Mock the pipeline components so we only test persistence
    with patch("app.storage.factory.get_storage") as mock_get_storage, \
         patch("app.worker.ocr_worker_tasks.OCRV2Pipeline") as mock_pipeline, \
         patch("app.storage.workspace.materialize_document") as mock_materialize:

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.process_document.return_value = mock_structured_document
        mock_pipeline.return_value = mock_pipeline_instance

        mock_storage = MagicMock()
        mock_storage.put.return_value = "storage/test_req_structured.json"
        mock_get_storage.return_value = mock_storage

        # mock context manager
        mock_materialize.return_value.__enter__.return_value = "local/temp/path.pdf"

        # Run worker task
        process_run_v2(str(run.run_id))

    # Verify DB persistence
    db_session.refresh(doc)
    assert doc.processing_status == "finished"
    assert doc.structured_document_path == "storage/test_req_structured.json"
    assert doc.text_extracted == "TEST REQUIREMENT", "INCOMPLETE_WORKER_PERSISTENCE: Text was not stored"

    # Test API contract directly (simulating v6_documents response derivation)
    extraction_ready = bool(doc.text_extracted and doc.text_extracted.strip())
    assert extraction_ready is True, "API Readiness contract failed because text_extracted is empty"

def test_extraction_ready_whitespace_semantics():
    from app.models.domain import UploadedDocument
    # Validate various states based on the real API condition
    def is_ready(t):
        return bool(t and t.strip())

    assert is_ready(None) is False
    assert is_ready("") is False
    assert is_ready("   ") is False
    assert is_ready("\n\n") is False
    assert is_ready("texto válido") is True
