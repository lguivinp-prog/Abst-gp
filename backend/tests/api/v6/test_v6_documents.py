import pytest
from app.main import app
from app.core.database import get_db
from app.models.domain import CaseFile, UploadedDocument, Tenant

@pytest.fixture
def v6_documents_client(client, db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)

def test_get_case_documents_success(v6_documents_client, db_session, setup_mega_tenant):
    case = CaseFile(title="Doc Case", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=1)
    db_session.add(case)
    db_session.commit()

    doc_a = UploadedDocument(
        case_id=case.id, document_type="requirement", original_filename="docA.pdf",
        mime_type="application/pdf", stored_path="/fake/pathA", processing_status="COMPLETED",
        text_extracted="Some text"
    )
    doc_b = UploadedDocument(
        case_id=case.id, document_type="quotation", original_filename="docB.pdf",
        mime_type="application/pdf", stored_path="/fake/pathB", processing_status="QUEUED",
        text_extracted=None
    )
    doc_c = UploadedDocument(
        case_id=case.id, document_type="quotation", original_filename="docC.pdf",
        mime_type="application/pdf", stored_path="/fake/pathC", processing_status="QUEUED",
        text_extracted=""
    )
    db_session.add_all([doc_a, doc_b, doc_c])
    db_session.commit()

    response = v6_documents_client.get(f"/api/v6/cases/{case.id}/documents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

    doc_a_resp = next(d for d in data if d["id"] == doc_a.id)
    assert doc_a_resp["original_filename"] == "docA.pdf"
    assert doc_a_resp["extraction_ready"] is True

    doc_b_resp = next(d for d in data if d["id"] == doc_b.id)
    assert doc_b_resp["extraction_ready"] is False

    doc_c_resp = next(d for d in data if d["id"] == doc_c.id)
    assert doc_c_resp["extraction_ready"] is False

    for d in data:
        assert "stored_path" not in d
        assert "text_extracted" not in d

def test_get_case_documents_empty(v6_documents_client, db_session, setup_mega_tenant):
    case = CaseFile(title="Empty Case", contract_type="goods", tenant_id="mega_tenant", assigned_to_user_id=1)
    db_session.add(case)
    db_session.commit()

    response = v6_documents_client.get(f"/api/v6/cases/{case.id}/documents")
    assert response.status_code == 200
    assert response.json() == []

def test_get_case_documents_cross_tenant_denied(v6_documents_client, db_session):
    other_tenant = (
        db_session.query(Tenant)
        .filter(Tenant.id == "other_tenant_v6_docs")
        .first()
    )

    if not other_tenant:
        other_tenant = Tenant(
            id="other_tenant_v6_docs",
            name="Other Tenant V6 Documents",
        )
        db_session.add(other_tenant)
        db_session.commit()

    case = CaseFile(title="Other Case", contract_type="goods", tenant_id="other_tenant_v6_docs", assigned_to_user_id=1)
    db_session.add(case)
    db_session.commit()

    response = v6_documents_client.get(f"/api/v6/cases/{case.id}/documents")
    assert response.status_code == 404
