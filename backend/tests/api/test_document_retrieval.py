import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import get_current_active_user, verify_case_access
from app.core.database import get_db
from app.models.domain import User, CaseFile, UploadedDocument, AuditLog
import os
import uuid
from pathlib import Path
import tempfile
from unittest.mock import MagicMock

client = TestClient(app)

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_user():
    user = User(id=1, username="admin_user", tenant_id="tenant1", role="ADMIN", tenant_resolution_status="RESOLVED")
    return user

@pytest.fixture
def mock_case():
    case = CaseFile(id=1, tenant_id="tenant1", title="Test Case")
    return case

@pytest.fixture
def test_uploads_dir():
    test_dir = tempfile.mkdtemp(prefix="uploads_")
    os.environ["UPLOADS_DIR"] = test_dir
    return test_dir

def test_get_document_success_admin(mock_db, mock_user, mock_case, test_uploads_dir):
    # Setup mock file
    file_path = os.path.join(test_uploads_dir, "test.pdf")
    with open(file_path, "wb") as f:
        f.write(b"%PDF-1.4 test document content")
        
    doc = UploadedDocument(id=10, case_id=1, document_type="requirement", stored_path=file_path, mime_type="application/pdf")
    
    # Mock DB query behavior
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_order = mock_filter.order_by.return_value
    mock_order.first.return_value = doc
    
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[verify_case_access] = lambda: mock_case
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.get("/cases/1/documents/requirement/content")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "requirement" in response.headers["content-disposition"]
    assert "nosniff" in response.headers["x-content-type-options"]
    assert response.content == b"%PDF-1.4 test document content"
    
    # Verify AuditLog was created
    mock_db.add.assert_called()
    added_obj = mock_db.add.call_args[0][0]
    assert isinstance(added_obj, AuditLog)
    assert added_obj.action == "READ_DOCUMENT_CONTENT"
    assert added_obj.status == "SUCCESS"
    
    app.dependency_overrides.clear()

def test_get_document_range_requests(mock_db, mock_user, mock_case, test_uploads_dir):
    file_path = os.path.join(test_uploads_dir, "test.pdf")
    with open(file_path, "wb") as f:
        f.write(b"%PDF-1.4 test document content")
    
    doc = UploadedDocument(id=10, case_id=1, document_type="requirement", stored_path=file_path)
    mock_db.query().filter().order_by().first.return_value = doc
    
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[verify_case_access] = lambda: mock_case
    app.dependency_overrides[get_db] = lambda: mock_db
    
    headers = {"Range": "bytes=0-3"}
    response = client.get("/cases/1/documents/requirement/content", headers=headers)
    assert response.status_code == 206
    assert response.content == b"%PDF"
    
    headers["Range"] = "bytes=1000-2000"
    response = client.get("/cases/1/documents/requirement/content", headers=headers)
    assert response.status_code == 416 # Range Not Satisfiable
    
    app.dependency_overrides.clear()

def test_path_traversal_prevention(mock_db, mock_user, mock_case, test_uploads_dir):
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[verify_case_access] = lambda: mock_case
    app.dependency_overrides[get_db] = lambda: mock_db
    
    import sys
    malicious_path = "C:\\Windows\\System32\\drivers\\etc\\hosts" if sys.platform == "win32" else "/etc/passwd"
    doc = UploadedDocument(id=10, case_id=1, document_type="requirement", stored_path=malicious_path)
    mock_db.query().filter().order_by().first.return_value = doc
    
    response = client.get("/cases/1/documents/requirement/content")
    assert response.status_code == 404
    assert malicious_path not in response.text
    
    # Prefix collision test
    malicious_dir = test_uploads_dir + "-malicious"
    os.makedirs(malicious_dir, exist_ok=True)
    fake_file = os.path.join(malicious_dir, "fake.pdf")
    with open(fake_file, "wb") as f:
        f.write(b"fake")
    doc.stored_path = fake_file
    
    response = client.get("/cases/1/documents/requirement/content")
    assert response.status_code == 404
    assert "fake.pdf" not in response.text
    assert malicious_dir not in response.text
    
    # Symlink escape test
    link_dir = os.path.join(test_uploads_dir, "symlinks")
    os.makedirs(link_dir, exist_ok=True)
    link_path = os.path.join(link_dir, "escape.pdf")
    try:
        # Create symlink pointing outside (e.g. to fake_file)
        os.symlink(fake_file, link_path)
        doc.stored_path = link_path
        
        response = client.get("/cases/1/documents/requirement/content")
        assert response.status_code == 404
    except OSError:
        pass # Symlinks might require admin privileges on Windows
    
    app.dependency_overrides.clear()

def test_multiple_requirement_documents_deterministic(mock_db, mock_user, mock_case, test_uploads_dir):
    new_file = os.path.join(test_uploads_dir, "new.pdf")
    with open(new_file, "wb") as f:
        f.write(b"NEWER")
    
    doc = UploadedDocument(id=11, case_id=1, document_type="requirement", stored_path=new_file)
    # The endpoint uses order_by(UploadedDocument.id.desc()).first() which gets the highest ID
    # We mock it to return doc id 11
    mock_db.query().filter().order_by().first.return_value = doc
    
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[verify_case_access] = lambda: mock_case
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.get("/cases/1/documents/requirement/content")
    assert response.status_code == 200
    assert response.content == b"NEWER"
    app.dependency_overrides.clear()

def test_not_found_on_missing_file(mock_db, mock_user, mock_case, test_uploads_dir):
    missing_file = os.path.join(test_uploads_dir, "missing.pdf")
    
    doc = UploadedDocument(id=10, case_id=1, document_type="requirement", stored_path=missing_file)
    mock_db.query().filter().order_by().first.return_value = doc
    
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[verify_case_access] = lambda: mock_case
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.get("/cases/1/documents/requirement/content")
    assert response.status_code == 404
    assert "physical file is not available" in response.text
    assert missing_file not in response.text
    
    # Check AuditLog for failure
    mock_db.add.assert_called()
    added_obj = mock_db.add.call_args[0][0]
    assert isinstance(added_obj, AuditLog)
    assert added_obj.action == "READ_DOCUMENT_CONTENT_FAILED"
    assert added_obj.status == "FAILED"
    
    app.dependency_overrides.clear()
