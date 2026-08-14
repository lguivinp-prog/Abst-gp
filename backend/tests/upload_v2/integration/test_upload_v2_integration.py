import pytest
import httpx
import hashlib
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import Tenant, User, CaseFile, UploadedDocument
from app.main import app
from app.core.config import settings

@pytest.fixture(scope="module")
def v2_client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def enable_v2_upload_minio(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_UPLOAD_MODE", "v2")
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "object_storage")
    # Point to MinIO
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "minioadmin")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "minioadmin123")
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "abst-documents")

@pytest.fixture
def auth_headers(db_session: Session):
    tenant = Tenant(id="tenant_integration", name="Tenant Integration")
    db_session.merge(tenant)
    user = User(
        username="integration_user",
        password_hash="fake",
        tenant_id="tenant_integration",
        role="operator",
        tenant_resolution_status="RESOLVED"
    )
    db_session.merge(user)
    db_session.commit()
    return {"Authorization": "Bearer fake-token"}

@pytest.fixture
def case_file(db_session: Session):
    case = CaseFile(
        tenant_id="tenant_integration",
        title="Test V2 Integration",
        contract_type="BIENES",
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case

def test_upload_v2_end_to_end_integration(
    v2_client, enable_v2_upload_minio, auth_headers, case_file, db_session
):
    from app.api.auth import get_current_user
    user = db_session.query(User).filter_by(username="integration_user").first()
    app.dependency_overrides[get_current_user] = lambda: user
    
    # 1. Initiate Upload
    file_content = b"Integration test content for MinIO upload v2"
    file_size = len(file_content)
    expected_hash = hashlib.sha256(file_content).hexdigest()
    
    init_payload = {
        "case_id": case_file.id,
        "document_type": "requirement",
        "filename": "integration.pdf",
        "content_type": "application/pdf",
        "size_bytes": file_size
    }
    
    resp = v2_client.post("/v2/documents/upload/initiate", json=init_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    
    upload_id = data["upload_id"]
    doc_id = data["document_id"]
    presigned_url = data["presigned_url"]
    
    # Verify state in DB
    doc = db_session.query(UploadedDocument).get(doc_id)
    assert doc.processing_status == "UPLOADING"
    assert doc.stored_path.startswith("tenant_integration/")
    
    # 2. Upload directly to MinIO using the presigned URL
    # Boto3 generated URLs for PUT require a PUT request
    upload_resp = httpx.put(presigned_url, content=file_content)
    assert upload_resp.status_code == 200, upload_resp.text
    
    # 3. Complete Upload
    complete_payload = {
        "document_id": doc_id,
        "upload_id": upload_id,
        "sha256_checksum": expected_hash
    }
    
    complete_resp = v2_client.post("/v2/documents/upload/complete", json=complete_payload, headers=auth_headers)
    assert complete_resp.status_code == 200, complete_resp.text
    
    # 4. Verify Final State
    db_session.refresh(doc)
    assert doc.processing_status == "AVAILABLE"
    
    # Verify the object exists in MinIO with correct checksum
    from app.storage.factory import get_storage
    storage = get_storage()
    assert storage.exists(doc.stored_path)
    assert storage.checksum(doc.stored_path) == expected_hash
    
    # Cleanup
    storage.delete(doc.stored_path)
    app.dependency_overrides.clear()
