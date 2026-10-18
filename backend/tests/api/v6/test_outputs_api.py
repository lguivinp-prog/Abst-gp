from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, AuditLog
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier import Supplier
from app.models.v6.generated_output import GeneratedOutput

def test_prepare_output_api(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    # Setup mock data for passing the gate
    case = CaseFile(title="Output Test", contract_type="BIENES", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    workflow = CaseWorkflow(case_id=case.id, status="APPROVED")
    db_session.add(workflow)
    
    # Each test creates its own supplier; never depend on persistent CI/seed rows.
    supplier = Supplier(tenant_id="mega_tenant", ruc="20100070970", business_name="Proveedor CI para prueba")
    db_session.add(supplier)
    db_session.flush()

    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, price=5000.0, total_amount=5000.0, status="PENDING", evaluation_status="APPROVED")
    db_session.add(offer)
    db_session.commit()
    
    # Needs a final selection to generate profile mock
    attempt = SupplierSelectionAttempt(case_id=case.id, supplier_offer_id=offer.id, status="PROPOSED")
    db_session.add(attempt)
    db_session.flush()
    sel = SupplierSelectionFinal(case_id=case.id, attempt_id=attempt.id) # Use real attempt.id
    db_session.add(sel)
    db_session.commit()
    
    # 1. Prepare Output
    response = admin_client.post(f"/api/v6/cases/{case.id}/prepare-output")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "GENERATED"
    output_id = data["id"]
    
    # 2. List Outputs
    list_res = admin_client.get(f"/api/v6/cases/{case.id}/outputs")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    
    # 3. Approve Output
    app_res = admin_client.post(f"/api/v6/outputs/{output_id}/approve")
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"
    
    # 4. Export Output
    exp_res = admin_client.post(f"/api/v6/outputs/{output_id}/export")
    assert exp_res.status_code == 200
    assert exp_res.json()["status"] == "EXPORTED"
