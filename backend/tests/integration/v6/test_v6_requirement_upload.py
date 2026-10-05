import pytest
from unittest.mock import patch, MagicMock
from app.models.domain import CaseFile, UploadedDocument, OCRProcessingRun
import io
import uuid

def test_v6_requirement_upload_success(admin_client, db_session):
    # Setup case
    case = CaseFile(tenant_id="mega_tenant", title="V6 Native Upload Case", contract_type="BIENES", status="DRAFT", created_by=1)
    db_session.add(case)
    db_session.commit()

    file_content = b"%PDF-1.4 dummy pdf"

    with patch("app.services.v6.requirement_ingestion_service.get_storage") as mock_storage, \
         patch("app.services.v6.requirement_ingestion_service.ocr_queue.enqueue") as mock_enqueue:

        mock_storage.return_value.put.return_value = "storage/path/to/test.pdf"

        mock_job = MagicMock()
        mock_job.id = "fake-job-id"
        mock_enqueue.return_value = mock_job

        response = admin_client.post(
            f"/api/v6/cases/{case.id}/requirements/upload",
            files={"file": ("test_req.pdf", io.BytesIO(file_content), "application/pdf")}
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert "document_id" in data
        assert "run_id" in data
        assert data["processing_status"] == "QUEUED"

        # Check DB State
        doc = db_session.query(UploadedDocument).filter(UploadedDocument.id == data["document_id"]).first()
        assert doc is not None
        assert doc.document_type == "requirement"
        assert doc.processing_status == "queued"

        run = db_session.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == data["run_id"]).first()
        assert run is not None
        assert run.uploaded_document_id == doc.id
        assert run.engine == "v2"
        assert run.status == "QUEUED"

        # Case state updated
        db_session.refresh(case)
        assert case.status == "PROCESSING_REQUIREMENT"

        # Exactly one dispatch
        assert mock_enqueue.call_count == 1
        args, kwargs = mock_enqueue.call_args
        assert args[0] == "app.worker.ocr_worker_tasks.process_run_v2"
        assert kwargs["args"][0] == str(run.run_id)

def test_v6_requirement_upload_non_pdf(admin_client, db_session):
    case = CaseFile(tenant_id="mega_tenant", title="V6 Reject Non PDF", contract_type="BIENES", status="DRAFT", created_by=1)
    db_session.add(case)
    db_session.commit()

    file_content = b"Not a PDF"
    response = admin_client.post(
        f"/api/v6/cases/{case.id}/requirements/upload",
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    )

    assert response.status_code == 400
    assert "Only PDF" in response.text

def test_v6_requirement_upload_unauthorized(db_session):
    from fastapi.testclient import TestClient
    from app.main import app
    unauth_client = TestClient(app)

    # Missing auth token
    case = CaseFile(tenant_id="mega_tenant", title="V6 Unauthorized Case", contract_type="BIENES", status="DRAFT", created_by=1)
    db_session.add(case)
    db_session.commit()

    response = unauth_client.post(
        f"/api/v6/cases/{case.id}/requirements/upload",
        files={"file": ("test.pdf", io.BytesIO(b"%PDF"), "application/pdf")}
    )
    assert response.status_code == 401

def test_v6_requirement_upload_dispatch_failure(admin_client, db_session):
    case = CaseFile(tenant_id="mega_tenant", title="V6 Dispatch Failure", contract_type="BIENES", status="DRAFT", created_by=1)
    db_session.add(case)
    db_session.commit()

    with patch("app.services.v6.requirement_ingestion_service.get_storage") as mock_storage, \
         patch("app.services.v6.requirement_ingestion_service.ocr_queue.enqueue", side_effect=Exception("Redis failure")):

        mock_storage.return_value.put.return_value = "storage/path/to/fail.pdf"

        from fastapi.testclient import TestClient
        from app.main import app

        # Disable server exceptions raising so we can get the 500 response
        faulty_client = TestClient(app, raise_server_exceptions=False)
        # We need to manually set the auth token headers to simulate admin
        # Or better, override dependency for this specific client
        from app.api.auth import get_current_active_user, get_current_user
        from app.models.domain import User

        def override_admin():
            return User(id=2, username="admin", role="ADMIN", is_active=True, must_change_password=False, tenant_id="mega_tenant")

        app.dependency_overrides[get_current_active_user] = override_admin
        app.dependency_overrides[get_current_user] = override_admin

        response = faulty_client.post(
            f"/api/v6/cases/{case.id}/requirements/upload",
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 dummy"), "application/pdf")}
        )

        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 500

        # We check the response is 500, indicating dispatch failure semantic.
        # DB records should exist but be marked as error/FAILED.
        doc = db_session.query(UploadedDocument).filter(UploadedDocument.case_id == case.id).first()
        assert doc is not None
        assert doc.processing_status == "error"
        assert doc.processing_error == "Dispatch failure"

        run = db_session.query(OCRProcessingRun).filter(OCRProcessingRun.uploaded_document_id == doc.id).first()
        assert run is not None
        assert run.status == "FAILED"

def test_v6_offer_document_regression(admin_client, db_session):
    from app.models.domain import OCRProcessingRun
    case = CaseFile(tenant_id="mega_tenant", title="V6 Offer Regression", contract_type="BIENES", status="DRAFT", created_by=1)
    db_session.add(case)
    db_session.commit()

    initial_runs = db_session.query(OCRProcessingRun).count()

    with patch("app.core.redis.ocr_queue.enqueue") as mock_enqueue:
        response = admin_client.post(
            f"/api/v6/cases/{case.id}/documents",
            data={"document_type": "offer", "description": "offer doc"},
            files={"file": ("offer.pdf", io.BytesIO(b"%PDF-1.4 mock"), "application/pdf")}
        )
        assert response.status_code == 200

        final_runs = db_session.query(OCRProcessingRun).count()
        assert final_runs == initial_runs
        mock_enqueue.assert_not_called()
