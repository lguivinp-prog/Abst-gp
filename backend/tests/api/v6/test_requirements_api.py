from fastapi.testclient import TestClient
from app.models.domain import AuditLog, CaseFile, UploadedDocument
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.requirement_evidence import RequirementEvidence
from sqlalchemy.orm import Session
import json

def test_extract_requirements_generates_pending_proposals(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    case = CaseFile(title="Test V6 Case", contract_type="Bienes", status="CREATED", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="tdr.pdf",
        stored_path="/tmp/tdr.pdf",
        mime_type="application/pdf",
        text_extracted="El proveedor debe tener 5 años de experiencia.\nEl equipo debe ser nuevo."
    )
    db_session.add(doc)
    db_session.commit()
    
    payload = {"document_id": doc.id}
    response = admin_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json=payload)
    
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) > 0
    
    for req in data:
        assert req["status"] in ["PENDING_REVIEW", "REVIEW_REQUIRED"] # No auto-approval
        assert len(req["evidences"]) > 0
        
        db_evidence = db_session.query(RequirementEvidence).filter(RequirementEvidence.requirement_id == req["id"]).first()
        assert db_evidence is not None
        assert db_evidence.source_fragment is not None

def test_update_requirement_generates_audit_and_enforces_status(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    case = CaseFile(title="Test V6 Case 2", contract_type="Bienes", status="CREATED", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Must be new",
        status="PENDING_REVIEW"
    )
    db_session.add(req)
    db_session.commit()
    
    payload = {
        "status": "VALIDATED",
        "reason": "Verified manually"
    }
    
    response = admin_client.put(f"/api/v6/cases/{case.id}/requirements/{req.id}", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "VALIDATED"
    
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "UPDATE_REQUIREMENT",
        AuditLog.entity_id == str(req.id)
    ).first()
    
    assert audit is not None
    details = json.loads(audit.details)
    assert details["old_value"] == "PENDING_REVIEW"
    assert details["new_value"] == "VALIDATED"
    assert details["reason"] == "Verified manually"
