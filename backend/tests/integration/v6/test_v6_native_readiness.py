import pytest
from unittest.mock import patch, MagicMock
from app.models.domain import CaseFile, UploadedDocument, OCRProcessingRun, Tenant, User
from app.worker.ocr_worker_tasks import process_run_v2
from app.services.extraction_engine.models.document import StructuredDocument, DocumentPage, OcrElement
import uuid
import io

@pytest.fixture
def mock_structured_document():
    page = DocumentPage(
        page_number=1,
        width=800,
        height=1000,
        elements=[
            OcrElement(text="NATIVE V6 REQUIREMENT TEXT", confidence=0.99, x=10, y=10, width=100, height=20, page_number=1)
        ]
    )
    from app.services.extraction_engine.models.document import DocumentBlock
    block = DocumentBlock(
        type="section",
        original_text="I. GENERAL",
        normalized_text="GENERAL",
        confidence=0.99,
        page=1,
        content="NATIVE V6 REQUIREMENT TEXT"
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

def test_native_v6_upload_and_readiness_flow(admin_client, db_session, mock_structured_document):
    # Setup case
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        db_session.commit()

    case = CaseFile(tenant_id="mega_tenant", title="Native Readiness Case", contract_type="BIENES", status="DRAFT", created_by=1)
    db_session.add(case)
    db_session.commit()

    file_content = b"%PDF-1.4 dummy pdf"

    with patch("app.services.v6.requirement_ingestion_service.get_storage") as mock_storage, \
         patch("app.services.v6.requirement_ingestion_service.ocr_queue.enqueue") as mock_enqueue, \
         patch("app.worker.ocr_worker_tasks.OCRV2Pipeline") as mock_pipeline, \
         patch("app.storage.factory.get_storage") as mock_get_storage_worker, \
         patch("app.storage.workspace.materialize_document") as mock_materialize:

        # Mock Upload Storage
        storage_instance = MagicMock()
        storage_instance.put.return_value = "storage/path/to/test.pdf"
        mock_storage.return_value = storage_instance

        # 1. Native V6 Upload
        response = admin_client.post(
            f"/api/v6/cases/{case.id}/requirements/upload",
            files={"file": ("test_req.pdf", io.BytesIO(file_content), "application/pdf")}
        )
        assert response.status_code == 200
        data = response.json()
        doc_id = data["document_id"]
        run_id = data["run_id"]

        # 2. Worker processes deterministic PDF
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.process_document.return_value = mock_structured_document
        mock_pipeline.return_value = mock_pipeline_instance

        mock_storage_worker = MagicMock()
        mock_storage_worker.put.return_value = "storage/structured_run.json"
        mock_get_storage_worker.return_value = mock_storage_worker
        mock_materialize.return_value.__enter__.return_value = "local/temp/path.pdf"

        process_run_v2(run_id)

        # 3. Text extracted populated
        doc = db_session.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
        assert doc.text_extracted == "NATIVE V6 REQUIREMENT TEXT"
        assert doc.processing_status == "finished"

        # 4. GET documents verifies extraction_ready=true
        get_response = admin_client.get(f"/api/v6/cases/{case.id}/documents")
        assert get_response.status_code == 200
        docs = get_response.json()
        assert len(docs) > 0
        target_doc = next(d for d in docs if d["id"] == doc_id)
        assert target_doc["extraction_ready"] is True
