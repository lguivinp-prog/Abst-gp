import pytest
import httpx
import hashlib
import uuid
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import Tenant, User, CaseFile, UploadedDocument, OCRProcessingRun, ProcessingJob
from app.main import app
from app.core.config import settings
from app.worker.ocr_worker_tasks import process_run_v2
from rq import SimpleWorker, Queue
from contextlib import contextmanager

@pytest.fixture(scope="module")
def v2_client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def enable_v2_upload_minio(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_UPLOAD_MODE", "v2")
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "object_storage")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "minioadmin")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "minioadmin123")
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "abst-documents")

@pytest.fixture
def auth_headers(db_session: Session):
    tenant = Tenant(id="tenant_integration_worker", name="Tenant Integration")
    db_session.merge(tenant)
    user = User(
        username="integration_user_worker",
        password_hash="fake",
        tenant_id="tenant_integration_worker",
        role="operator",
        tenant_resolution_status="RESOLVED"
    )
    db_session.merge(user)
    db_session.commit()
    return {"Authorization": "Bearer fake-token"}

@pytest.fixture
def case_file(db_session: Session):
    case = CaseFile(
        tenant_id="tenant_integration_worker",
        title="Test V2 Worker Integration",
        contract_type="BIENES",
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case

@contextmanager
def mock_rq_job():
    import rq
    class MockJob:
        id = "mock_job_id"
    # mock rq.get_current_job
    original = rq.get_current_job
    rq.get_current_job = lambda: MockJob()
    yield
    rq.get_current_job = original

def test_ocr_worker_v2_end_to_end(
    v2_client, enable_v2_upload_minio, auth_headers, case_file, db_session, monkeypatch
):
    from app.api.auth import get_current_user
    user = db_session.query(User).filter_by(username="integration_user_worker").first()
    app.dependency_overrides[get_current_user] = lambda: user
    
    # 1. Upload Document via V2 Upload Flow
    # We will use a dummy PDF content that the OCR pipeline (mocked or real) can process.
    # The OCR pipeline in Abst-GP uses a dummy process for testing or PyPDF.
    # We'll just provide a small valid PDF or text that can be digested.
    # We can use a minimal PDF:
    minimal_pdf = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Resources <<\n/Font <<\n/F1 <<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\n>>\n>>\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n72 712 Td\n(Hello MinIO!) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000289 00000 n \ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n384\n%%EOF\n"
    
    expected_hash = hashlib.sha256(minimal_pdf).hexdigest()
    
    init_payload = {
        "case_id": case_file.id,
        "document_type": "requirement",
        "filename": "test_doc.pdf",
        "content_type": "application/pdf",
        "size_bytes": len(minimal_pdf)
    }
    
    resp = v2_client.post("/v2/documents/upload/initiate", json=init_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    upload_id = data["upload_id"]
    doc_id = data["document_id"]
    presigned_url = data["presigned_url"]
    
    # 2. Upload to MinIO
    upload_resp = httpx.put(presigned_url, content=minimal_pdf)
    assert upload_resp.status_code == 200, upload_resp.text
    
    # 3. Complete Upload
    complete_resp = v2_client.post("/v2/documents/upload/complete", json={
        "document_id": doc_id,
        "upload_id": upload_id,
        "sha256_checksum": expected_hash
    }, headers=auth_headers)
    assert complete_resp.status_code == 200, complete_resp.text
    
    # 4. Create ProcessingJob and OCRProcessingRun to simulate the V2 Orchestrator
    run_id = uuid.uuid4()
    pjob = ProcessingJob(
        case_id=case_file.id,
        tenant_id=case_file.tenant_id,
        worker_type="OCR_WORKER",
        status="PROCESSING"
    )
    db_session.add(pjob)
    db_session.commit()
    db_session.refresh(pjob)
    
    run = OCRProcessingRun(
        run_id=run_id,
        uploaded_document_id=doc_id,
        processing_job_id=pjob.id,
        execution_role="PRIMARY",
        engine="v2",
        status="QUEUED",
        run_dedup_key=(uuid.uuid4().hex * 2)[:64]
    )
    db_session.add(run)
    db_session.commit()
    
    # 5. Execute the OCR Worker directly
    # Mock OCRV2Pipeline so we don't need paddleocr installed in the API container during testing
    class MockBlock:
        def __init__(self):
            self.type = "section"
            self.original_text = "I. INTRODUCTION"
            self.normalized_text = "INTRODUCTION"
            self.roman_numeral = "I"
            self.confidence = 0.99
            self.title = "INTRODUCTION"
            self.metadata = {}
            self.polygon = []
            self.bounding_box = [0,0,10,10]
            self.page = 1
            self.content = ["This is the intro"]
            self.style = {}

    class MockStructuredDoc:
        def __init__(self):
            self.confidence = 0.95
            self.sections = []
            self.blocks = [MockBlock()]
            self.tables = []
            self.entities = []
            self.metadata = {"evaluation": {"score": 0.95}}
        def model_dump(self):
            return {"content": "mock_ocr_result"}
            
    class MockOCRV2Pipeline:
        def process_document(self, path):
            return MockStructuredDoc()

    monkeypatch.setattr("app.worker.ocr_worker_tasks.OCRV2Pipeline", MockOCRV2Pipeline)

    with mock_rq_job():
        process_run_v2(str(run_id))
        
    # 6. Validate Output
    db_session.refresh(run)
    assert run.status == "COMPLETED"
    
    # Verify the artifact was uploaded to MinIO
    from app.storage.factory import get_storage
    storage = get_storage()
    assert run.structured_document_path is not None
    assert storage.exists(run.structured_document_path)
    
    # Check that artifact is valid JSON
    artifact_bytes = storage.get(run.structured_document_path)
    # Get all from stream
    artifact_content = artifact_bytes.read()
    data_json = json.loads(artifact_content)
    assert "checksum" in data_json
    
    # Cleanup Storage
    doc = db_session.query(UploadedDocument).get(doc_id)
    storage.delete(doc.stored_path)
    storage.delete(run.structured_document_path)
    
    app.dependency_overrides.clear()
