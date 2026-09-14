import pytest
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
def enable_v2_upload(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_UPLOAD_MODE", "v2")

@pytest.fixture
def auth_headers(db_session: Session):
    # Setup test user and tenant
    tenant = Tenant(id="tenant_v2_test", name="Tenant V2")
    db_session.merge(tenant)
    
    user = User(
        username="v2_user",
        password_hash="fake",
        tenant_id="tenant_v2_test",
        role="operator",
        tenant_resolution_status="RESOLVED"
    )
    db_session.merge(user)
    db_session.commit()
    
    # We will just patch get_current_user in the app to avoid real token logic
    return {"Authorization": "Bearer fake-token"}

@pytest.fixture
def case_file(db_session: Session):
    case = CaseFile(
        tenant_id="tenant_v2_test",
        title="Test V2 Upload",
        contract_type="BIENES",
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case

@pytest.fixture
def another_tenant_case(db_session: Session):
    tenant = Tenant(id="tenant_other", name="Other")
    db_session.merge(tenant)
    db_session.flush()
    case = CaseFile(
        tenant_id="tenant_other",
        title="Other Case",
        contract_type="BIENES",
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case

def test_initiate_v2_disabled(v2_client, auth_headers, case_file, db_session):
    from app.api.auth import get_current_user
    user = db_session.query(User).filter_by(username="v2_user").first()
    app.dependency_overrides[get_current_user] = lambda: user
    # without monkeypatch, it defaults to legacy (or whatever is in env)
    # Ensure it's not v2
    import os
    if os.getenv("DOCUMENT_UPLOAD_MODE") != "v2":
        resp = v2_client.post("/v2/documents/upload/initiate", json={
            "case_id": case_file.id,
            "document_type": "requirement",
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1000
        }, headers=auth_headers)
        assert resp.status_code == 501
        assert "not enabled" in resp.json()["detail"]
    app.dependency_overrides.clear()

def test_initiate_and_complete_upload(v2_client, enable_v2_upload, auth_headers, case_file, db_session, mocker):
    # Mock get_current_user dependency
    from app.api.auth import get_current_user
    user = db_session.query(User).filter_by(username="v2_user").first()
    app.dependency_overrides[get_current_user] = lambda: user
    
        # Mock Storage
    from io import BytesIO
    from app.storage.local import LocalStorageAdapter
    import fitz

    mocker.patch.object(LocalStorageAdapter, 'generate_presigned_url', return_value="http://fake-url")
    mocker.patch.object(LocalStorageAdapter, 'exists', return_value=True)
    mocker.patch.object(LocalStorageAdapter, 'checksum', return_value="fakehash")

    mock_doc = fitz.open()
    mock_doc.new_page()
    mock_pdf = mock_doc.tobytes()
    mock_doc.close()

    mocker.patch.object(
        LocalStorageAdapter,
        'get',
        side_effect=lambda uri: BytesIO(mock_pdf)
    )

    # 1. Initiate
    init_payload = {
        "case_id": case_file.id,
        "document_type": "requirement",
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1000
    }
    
    resp = v2_client.post("/v2/documents/upload/initiate", json=init_payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "upload_id" in data
    assert "presigned_url" in data
    assert data["presigned_url"] == "http://fake-url"
    
    doc_id = data["document_id"]
    upload_id = data["upload_id"]
    
    doc = db_session.query(UploadedDocument).get(doc_id)
    assert doc.processing_status == "UPLOADING"
    assert doc.ocr_metadata["v6_upload_id"] == upload_id
    
    # 2. Complete
    complete_payload = {
        "document_id": doc_id,
        "upload_id": upload_id,
        "sha256_checksum": "fakehash"
    }
    
    resp_complete = v2_client.post("/v2/documents/upload/complete", json=complete_payload, headers=auth_headers)
    assert resp_complete.status_code == 200, resp_complete.text
    assert resp_complete.json()["status"] == "QUEUED"
    
    db_session.refresh(doc)
    assert doc.processing_status == "queued"
    
    app.dependency_overrides.clear()

def test_tenant_isolation(v2_client, enable_v2_upload, auth_headers, another_tenant_case, db_session):
    from app.api.auth import get_current_user
    user = db_session.query(User).filter_by(username="v2_user").first()
    app.dependency_overrides[get_current_user] = lambda: user
    
    init_payload = {
        "case_id": another_tenant_case.id,
        "document_type": "requirement",
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1000
    }
    
    resp = v2_client.post("/v2/documents/upload/initiate", json=init_payload, headers=auth_headers)
    assert resp.status_code == 403
    assert "Tenant isolation breach" in resp.json()["detail"]
    app.dependency_overrides.clear()

def test_checksum_mismatch(v2_client, enable_v2_upload, auth_headers, case_file, db_session, mocker):
    from app.api.auth import get_current_user
    user = db_session.query(User).filter_by(username="v2_user").first()
    app.dependency_overrides[get_current_user] = lambda: user
    
    from app.storage.local import LocalStorageAdapter
    mocker.patch.object(LocalStorageAdapter, 'generate_presigned_url', return_value="http://fake-url")
    mocker.patch.object(LocalStorageAdapter, 'exists', return_value=True)
    mocker.patch.object(LocalStorageAdapter, 'checksum', return_value="realhash")
    
    resp = v2_client.post("/v2/documents/upload/initiate", json={
        "case_id": case_file.id,
        "document_type": "requirement",
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1000
    }, headers=auth_headers)
    data = resp.json()
    
    # Complete with wrong hash
    resp_complete = v2_client.post("/v2/documents/upload/complete", json={
        "document_id": data["document_id"],
        "upload_id": data["upload_id"],
        "sha256_checksum": "wronghash"
    }, headers=auth_headers)
    
    assert resp_complete.status_code == 400
    assert "Checksum mismatch" in resp_complete.json()["detail"]
    
    doc = db_session.query(UploadedDocument).get(data["document_id"])
    assert doc.processing_status == "FAILED"
    
    app.dependency_overrides.clear()
