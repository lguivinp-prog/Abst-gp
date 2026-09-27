from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence

def test_pilot_case_execution(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Simulates a real-world operator flow during the pilot.
    No direct DB manipulation except for setup dependencies (simulating V5.5 existing state).
    """
    # 1. Setup V5.5 Legacy Case
    case = CaseFile(title="Pilot Case: Laptops", contract_type="BIENES", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    # 2. Extract Requirements (Simulate)
    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="RAM", value="32GB")
    db_session.add(req)
    db_session.commit()
    
    # 3. Add Supplier
    supplier = Supplier(ruc="20555555555", business_name="Pilot Supplier SAC", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    
    # 4. Add Offer
    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        status="SUBMITTED",
        price=1000.0
    )
    db_session.add(offer)
    db_session.commit()

    # 4.1 Add documentary evidence required by V6 evaluation
    evidence = OfferEvidence(
        supplier_offer_id=offer.id,
        document_type="FICHA_TECNICA",
        fragment="32GB",
        confidence=0.99,
    )
    db_session.add(evidence)
    db_session.commit()

    # 5. Evaluate Offer
    eval_res = admin_client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 200
    
    # 6. Make Selection
    sel_res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Cumple tecnico para piloto"})
    assert sel_res.status_code == 200
    
    # 7. Supervisor Approves
    app_res = admin_client.post(f"/api/v6/cases/{case.id}/approve")
    assert app_res.status_code == 200
    
    # 8. Output Prep & Export
    out_res = admin_client.post(f"/api/v6/cases/{case.id}/prepare-output")
    assert out_res.status_code == 200
    out_id = out_res.json()["id"]
    
    admin_client.post(f"/api/v6/outputs/{out_id}/approve")
    exp_res = admin_client.post(f"/api/v6/outputs/{out_id}/export")
    assert exp_res.status_code == 200
    assert exp_res.json()["status"] == "EXPORTED"
