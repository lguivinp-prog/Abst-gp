from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, AuditLog
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.case_workflow import CaseWorkflow

def test_propose_and_approve_selection(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    case = CaseFile(title="Laptop Purchase", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    db_session.add(case)
    supplier = Supplier(ruc="20123456789", business_name="Tech Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()

    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, status="SUBMITTED")
    db_session.add(offer)
    db_session.commit()

    # 1. Propose Selection
    payload = {"supplier_offer_id": offer.id, "justification_comment": "Mejor precio y plazo"}
    response = admin_client.post(f"/api/v6/cases/{case.id}/selection", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "UNDER_REVIEW"

    # Verify Selection and Workflow State
    attempt = db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first()
    assert attempt is not None
    assert attempt.selected_by is not None

    workflow = db_session.query(CaseWorkflow).filter_by(case_id=case.id).first()
    assert workflow.status == "UNDER_REVIEW"

    # 2. Approve Selection
    approve_res = admin_client.post(f"/api/v6/cases/{case.id}/approve")
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    db_session.refresh(workflow)
    assert workflow.status == "APPROVED"
    assert workflow.supervisor_id is not None

    final_sel = db_session.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()
    assert final_sel is not None
