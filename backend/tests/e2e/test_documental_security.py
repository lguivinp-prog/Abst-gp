import pytest
import os
import shutil
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import get_current_user, get_current_active_user
from app.models.domain import User, CaseFile, UploadedDocument, Tenant, AuditLog
from tests.conftest import TestingSessionLocal
from app.api.exceptions import UnauthorizedException, ForbiddenException
import uuid

# Crearemos datos en la base de datos de test
@pytest.fixture(scope="module")
def setup_security_data():
    with TestingSessionLocal() as db:
        # Tenants
        tenant1 = Tenant(id="tenant1", name="Tenant 1")
        tenant2 = Tenant(id="tenant2", name="Tenant 2")
        db.merge(tenant1)
        db.merge(tenant2)
        db.commit()

        # Usuarios
        user1 = User(id=1, username="admin1", password_hash="x", role="ADMIN", is_active=True, tenant_id="tenant1", tenant_resolution_status="RESOLVED")
        user2 = User(id=2, username="op1", password_hash="x", role="OPERATOR", is_active=True, tenant_id="tenant1", tenant_resolution_status="RESOLVED")
        user3 = User(id=3, username="ro1", password_hash="x", role="READONLY", is_active=True, tenant_id="tenant1", tenant_resolution_status="RESOLVED")
        user4 = User(id=4, username="op2", password_hash="x", role="OPERATOR", is_active=True, tenant_id="tenant2", tenant_resolution_status="RESOLVED")
        user5 = User(id=5, username="quar", password_hash="x", role="OPERATOR", is_active=False, tenant_id=None, tenant_resolution_status="QUARANTINED")
        db.merge(user1)
        db.merge(user2)
        db.merge(user3)
        db.merge(user4)
        db.merge(user5)
        db.commit()

        # Casos
        case1 = CaseFile(id=1001, tenant_id="tenant1", title="Sec Case 1", contract_type="Standard", status="CREATED")
        case2 = CaseFile(id=1002, tenant_id="tenant1", title="Sec Case 2", contract_type="Standard", status="CREATED")
        case3 = CaseFile(id=1003, tenant_id="tenant1", title="Sec Case 3", contract_type="Standard", status="CREATED")
        db.merge(case1)
        db.merge(case2)
        db.merge(case3)
        
        # Archivo real en UPLOADS_DIR
        uploads_root = os.environ.get("UPLOADS_DIR", "/data/uploads")
        os.makedirs(uploads_root, exist_ok=True)
        temp_dir = tempfile.mkdtemp(dir=uploads_root)
        safe_path = os.path.join(temp_dir, "test_doc.pdf")
        with open(safe_path, "wb") as f:
            f.write(b"%PDF-1.4 dummy content")
            
        doc1 = UploadedDocument(
            id=1001,
            case_id=1001,
            document_type="requirement",
            original_filename="test.pdf",
            stored_path=safe_path,
            mime_type="application/pdf"
        )
        db.merge(doc1)
        
        # Doc sin archivo físico (en case 1002)
        doc_missing = UploadedDocument(
            id=1002,
            case_id=1002,
            document_type="requirement",
            original_filename="missing.pdf",
            stored_path=os.path.join(temp_dir, "does_not_exist.pdf"),
            mime_type="application/pdf"
        )
        db.merge(doc_missing)
        
        # Doc no PDF (en case 1003)
        safe_txt = os.path.join(temp_dir, "test_doc.txt")
        with open(safe_txt, "w") as f:
            f.write("text content")
            
        doc_txt = UploadedDocument(
            id=1003,
            case_id=1003,
            document_type="requirement",
            original_filename="test.txt",
            stored_path=safe_txt,
            mime_type="text/plain"
        )
        db.merge(doc_txt)
        
        db.commit()

    yield temp_dir

    # Cleanup
    with TestingSessionLocal() as db:
        db.query(AuditLog).filter(AuditLog.user_id.in_([1, 2, 3, 4, 5])).delete(synchronize_session=False)
        db.query(UploadedDocument).filter(UploadedDocument.id.in_([1001, 1002, 1003])).delete(synchronize_session=False)
        db.query(CaseFile).filter(CaseFile.id.in_([1001, 1002, 1003])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([1, 2, 3, 4, 5])).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id.in_(["tenant1", "tenant2"])).delete(synchronize_session=False)
        db.commit()
    shutil.rmtree(temp_dir, ignore_errors=True)

def mock_auth(user_info):
    def override_dependency():
        user = User(**user_info)
        if not user.is_active:
            raise UnauthorizedException("Inactive user")
        if user.tenant_id is None:
            raise UnauthorizedException("User tenant assignment missing")
        if user.tenant_resolution_status != 'RESOLVED':
            raise UnauthorizedException("User is quarantined or unresolved")
        if user.must_change_password:
            raise ForbiddenException("Must change password")
        return user
    app.dependency_overrides[get_current_active_user] = override_dependency
    app.dependency_overrides[get_current_user] = override_dependency

def test_admin_authorized(setup_security_data):
    mock_auth({"id": 1, "username": "admin1", "role": "ADMIN", "is_active": True, "tenant_id": "tenant1", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1001/documents/requirement/content")
        assert response.status_code == 200
        assert "application/pdf" in response.headers.get("Content-Type", "")

def test_operator_assigned(setup_security_data):
    with TestingSessionLocal() as db:
        case = db.query(CaseFile).filter(CaseFile.id == 1001).first()
        case.assigned_to_user_id = 2
        db.commit()
        
    mock_auth({"id": 2, "username": "op1", "role": "OPERATOR", "is_active": True, "tenant_id": "tenant1", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1001/documents/requirement/content")
        assert response.status_code == 200

def test_operator_unassigned(setup_security_data):
    with TestingSessionLocal() as db:
        case = db.query(CaseFile).filter(CaseFile.id == 1001).first()
        case.assigned_to_user_id = 4
        db.commit()

    mock_auth({"id": 2, "username": "op1", "role": "OPERATOR", "is_active": True, "tenant_id": "tenant1", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1001/documents/requirement/content")
        assert response.status_code == 404

def test_readonly_authorized(setup_security_data):
    with TestingSessionLocal() as db:
        case = db.query(CaseFile).filter(CaseFile.id == 1001).first()
        case.assigned_to_user_id = 3
        db.commit()

    mock_auth({"id": 3, "username": "ro1", "role": "READONLY", "is_active": True, "tenant_id": "tenant1", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1001/documents/requirement/content")
        assert response.status_code == 200

def test_other_tenant(setup_security_data):
    mock_auth({"id": 4, "username": "op2", "role": "OPERATOR", "is_active": True, "tenant_id": "tenant2", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1001/documents/requirement/content")
        assert response.status_code == 404

def test_quarantine(setup_security_data):
    mock_auth({"id": 5, "username": "quar", "role": "OPERATOR", "is_active": False, "tenant_id": None, "tenant_resolution_status": "QUARANTINED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1001/documents/requirement/content")
        assert response.status_code == 401

def test_case_missing(setup_security_data):
    mock_auth({"id": 1, "username": "admin1", "role": "ADMIN", "is_active": True, "tenant_id": "tenant1", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/9999/documents/requirement/content")
        assert response.status_code == 404

def test_file_physically_missing(setup_security_data):
    mock_auth({"id": 1, "username": "admin1", "role": "ADMIN", "is_active": True, "tenant_id": "tenant1", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1002/documents/requirement/content")
        assert response.status_code == 404

def test_path_traversal(setup_security_data):
    mock_auth({"id": 1, "username": "admin1", "role": "ADMIN", "is_active": True, "tenant_id": "tenant1", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1001/documents/..%2F..%2Fetc%2Fpasswd/content")
        assert response.status_code in (404, 400, 422)

def test_cache_control_and_content_type(setup_security_data):
    mock_auth({"id": 1, "username": "admin1", "role": "ADMIN", "is_active": True, "tenant_id": "tenant1", "tenant_resolution_status": "RESOLVED", "must_change_password": False, "password_hash": "x"})
    with TestClient(app) as client:
        response = client.get("/cases/1001/documents/requirement/content")
        assert response.status_code == 200
        assert "application/pdf" in response.headers.get("Content-Type", "")
        assert "private, no-store" in response.headers.get("Cache-Control", "")
        assert "nosniff" in response.headers.get("X-Content-Type-Options", "")
