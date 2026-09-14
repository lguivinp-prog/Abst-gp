import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.models.domain import CaseFile, UploadedDocument, Tenant, User
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix

@pytest.fixture
def req_client(client, db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def readonly_client(client, db_session):
    # client is OPERATOR. Let's create a READONLY user
    user = User(
        username="test_readonly",
        password_hash="fake",
        role="readonly",
        tenant_id="mega_tenant"
    )
    db_session.add(user)
    db_session.commit()

    # We need a proper token or just override get_current_active_user
    from app.api.auth import get_current_active_user, get_current_user
    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    app.dependency_overrides[get_current_user] = override_user

    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

def test_extract_success_and_idempotent(req_client, db_session, setup_mega_tenant):
    case = CaseFile(title="Idempotent Case", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=1)
    db_session.add(case)
    db_session.commit()

    # Manual requirement
    manual_req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Manual Req",
        status="VALIDATED",
        source_document_id=None
    )
    db_session.add(manual_req)
    db_session.commit()

    doc1 = UploadedDocument(
        case_id=case.id, document_type="requirement", original_filename="doc1.pdf",
        mime_type="application/pdf", stored_path="/f1", processing_status="COMPLETED",
        text_extracted="Req 1 from doc 1"
    )
    db_session.add(doc1)
    db_session.commit()

    payload = {"document_id": doc1.id}
    # First extraction
    resp1 = req_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert len(data1) > 0
    assert all(r["source_document_id"] == doc1.id for r in data1)

    # Second extraction
    resp2 = req_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2) == len(data1)

    # Verify manual req untouched
    manual = db_session.query(CaseRequirementMatrix).filter_by(id=manual_req.id).first()
    assert manual.description == "Manual Req"
    assert manual.source_document_id is None

def test_extract_empty_text_422(req_client, db_session, setup_mega_tenant):
    case = CaseFile(title="Empty Case", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=1)
    db_session.add(case)
    db_session.commit()

    for text in [None, "", "   "]:
        doc = UploadedDocument(
            case_id=case.id, document_type="requirement", original_filename="doc.pdf",
            mime_type="application/pdf", stored_path="/f", processing_status="COMPLETED",
            text_extracted=text
        )
        db_session.add(doc)
        db_session.commit()

        resp = req_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json={"document_id": doc.id})
        assert resp.status_code == 422

def test_extract_cross_tenant_denied(req_client, db_session):
    other_tenant = db_session.query(Tenant).filter_by(id="other_tenant_ext").first()
    if not other_tenant:
        other_tenant = Tenant(id="other_tenant_ext", name="Other Tenant")
        db_session.add(other_tenant)
        db_session.commit()

    case = CaseFile(title="Other Case", contract_type="goods", tenant_id="other_tenant_ext", assigned_to_user_id=1)
    db_session.add(case)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id, document_type="requirement", original_filename="doc.pdf",
        mime_type="application/pdf", stored_path="/f", processing_status="COMPLETED",
        text_extracted="text"
    )
    db_session.add(doc)
    db_session.commit()

    resp = req_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json={"document_id": doc.id})
    assert resp.status_code == 404

def test_extract_unauthorized_user(readonly_client, db_session, setup_mega_tenant):
    user = db_session.query(User).filter_by(username="test_readonly").first()
    case = CaseFile(title="Case", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=user.id)
    db_session.add(case)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id, document_type="requirement", original_filename="doc.pdf",
        mime_type="application/pdf", stored_path="/f", processing_status="COMPLETED",
        text_extracted="text"
    )
    db_session.add(doc)
    db_session.commit()

    resp = readonly_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json={"document_id": doc.id})
    assert resp.status_code == 403

def test_extract_edited_requirement_preserved(req_client, db_session, setup_mega_tenant):
    case = CaseFile(title="Edited Req Case", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=1)
    db_session.add(case)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id, document_type="requirement", original_filename="doc.pdf",
        mime_type="application/pdf", stored_path="/f", processing_status="COMPLETED",
        text_extracted="Some req text"
    )
    db_session.add(doc)
    db_session.commit()

    # Pre-existing extracted req that was modified
    edited_req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Original text",
        value="Edited value",
        status="MODIFIED_BY_USER",
        source_document_id=doc.id
    )
    db_session.add(edited_req)
    db_session.commit()

    resp = req_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json={"document_id": doc.id})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "MODIFIED_BY_USER"
    assert data[0]["value"] == "Edited value"

def test_extract_multiple_docs_same_case(req_client, db_session, setup_mega_tenant):
    case = CaseFile(title="Multi Doc Case", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=1)
    db_session.add(case)
    db_session.commit()

    doc1 = UploadedDocument(
        case_id=case.id, document_type="requirement", original_filename="doc1.pdf",
        mime_type="application/pdf", stored_path="/f1", processing_status="COMPLETED",
        text_extracted="This is requirement 1"
    )
    doc2 = UploadedDocument(
        case_id=case.id, document_type="requirement", original_filename="doc2.pdf",
        mime_type="application/pdf", stored_path="/f2", processing_status="COMPLETED",
        text_extracted="This is requirement 2"
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()

    resp1 = req_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json={"document_id": doc1.id})
    assert resp1.status_code == 200
    assert len(resp1.json()) > 0
    assert all(r["source_document_id"] == doc1.id for r in resp1.json())

    resp2 = req_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json={"document_id": doc2.id})
    assert resp2.status_code == 200
    assert len(resp2.json()) > 0
    assert all(r["source_document_id"] == doc2.id for r in resp2.json())

def test_extract_doc_from_another_case_rejected(req_client, db_session, setup_mega_tenant):
    case1 = CaseFile(title="Case 1", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=1)
    case2 = CaseFile(title="Case 2", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=1)
    db_session.add_all([case1, case2])
    db_session.commit()

    doc_case2 = UploadedDocument(
        case_id=case2.id, document_type="requirement", original_filename="doc.pdf",
        mime_type="application/pdf", stored_path="/f", processing_status="COMPLETED",
        text_extracted="text"
    )
    db_session.add(doc_case2)
    db_session.commit()

    # Try to extract doc_case2 on case1
    resp = req_client.post(f"/api/v6/cases/{case1.id}/requirements/extract", json={"document_id": doc_case2.id})
    assert resp.status_code == 404
