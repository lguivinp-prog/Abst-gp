from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.domain import CaseFile, AuditLog

def test_evaluate_offer_creates_evaluations_and_audit(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    case = CaseFile(title="Laptop Purchase", contract_type="BIENES", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    supplier = Supplier(ruc="20123456789", business_name="Tech Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    
    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, status="PENDING", evaluation_status="PENDING")
    db_session.add(offer)
    db_session.commit()
    
    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="Plazo", value="10 dias")
    db_session.add(req)
    db_session.commit()
    
    response = admin_client.post(f"/api/v6/offers/{offer.id}/evaluate")
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "MISSING_DATA" # Because we didn't add OfferEvidence
    
    # Check AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "EVALUATE_OFFER",
        AuditLog.entity_id == str(offer.id)
    ).first()
    assert audit is not None

def test_update_evaluation_resolves_status(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    from app.models.v6.offer_evaluation import OfferEvaluation
    case = CaseFile(title="Services", contract_type="SERVICIOS", tenant_id="mega_tenant")
    db_session.add(case)
    supplier = Supplier(ruc="20123456790", business_name="Serv Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    
    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, evaluation_status="HAS_CONFLICTS")
    db_session.add(offer)
    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="X", value="Y")
    db_session.add(req)
    db_session.commit()
    
    eval_entry = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req.id, status="CONFLICT")
    db_session.add(eval_entry)
    db_session.commit()
    
    payload = {"status": "PASSED", "explanation": "Humano resolvio conflicto a favor del anexo."}
    response = admin_client.put(f"/api/v6/evaluations/{eval_entry.id}", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "PASSED"
    
    # Check if parent offer unblocked
    db_session.refresh(offer)
    assert offer.evaluation_status == "UNDER_REVIEW" # Unblocked
