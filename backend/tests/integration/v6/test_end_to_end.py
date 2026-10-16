from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.supplier_selection import SupplierSelectionFinal
from app.models.v6.case_workflow import CaseWorkflow

def test_full_v6_end_to_end_flow(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Validates the end-to-end V6 flow without automated mocks interfering with the happy path.
    Steps: Case -> Reqs -> Supplier -> Validations -> Offer -> Evaluate -> Select -> Approve -> Output
    """
    # 1. Create CaseFile (Simulated as existing legacy domain)
    case = CaseFile(title="E2E Servers", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    # 2. Extract Requirements (Simulate existing req)
    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="RAM", value="16GB")
    db_session.add(req)
    db_session.commit()
    
    # 3. Create Supplier & Profile
    supplier = Supplier(ruc="20111111111", business_name="E2E Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    
    # 4. Load Offer & Evidence
    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, status="SUBMITTED", price=1000.0)
    db_session.add(offer)
    db_session.commit()
    ev = OfferEvidence(supplier_offer_id=offer.id, document_type="Ficha Tecnica", fragment="32GB RAM")
    db_session.add(ev)
    db_session.commit()

    # Link and verify requirement evidence (P12 traceability)
    link_res = admin_client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req.id}/evidence",
        json={"offer_evidence_id": ev.id}
    )
    assert link_res.status_code == 200
    link_id = link_res.json()["id"]
    rev_res = admin_client.put(
        f"/api/v6/cases/{case.id}/evidence/{link_id}/review",
        json={"verification_status": "VERIFIED", "review_notes": "Acreditado tecnicamente"}
    )
    assert rev_res.status_code == 200

    # 5. Trigger Validation
    val_res = admin_client.post(f"/api/v6/cases/{case.id}/suppliers/{supplier.id}/validations", json={"source": "SUNAT"})
    assert val_res.status_code == 200
    
    # 6. Evaluate Offer
    eval_res = admin_client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 200
    
    # 7. Evaluate Experience (Mocked passed via rules)
    # 8. Supplier Selection
    sel_res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Cumple tecnico"})
    assert sel_res.status_code == 200
    assert sel_res.json()["status"] == "UNDER_REVIEW"
    
    # 9. Supervisor Approval
    app_res = admin_client.post(f"/api/v6/cases/{case.id}/approve")
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"
    
    # 10. Generate Output
    out_res = admin_client.post(f"/api/v6/cases/{case.id}/prepare-output")
    assert out_res.status_code == 200
    assert out_res.json()["status"] == "GENERATED"
    out_id = out_res.json()["id"]
    
    # 11. Approve & Export Output
    admin_client.post(f"/api/v6/outputs/{out_id}/approve")
    export_res = admin_client.post(f"/api/v6/outputs/{out_id}/export")
    assert export_res.status_code == 200
    assert export_res.json()["status"] == "EXPORTED"
