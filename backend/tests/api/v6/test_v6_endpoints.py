from fastapi.testclient import TestClient
from app.models.domain import AuditLog, CaseFile
from sqlalchemy.orm import Session
from app.models.v6.supplier import Supplier

def test_create_matrix_item_generates_audit(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    # 1. Setup a basic CaseFile
    case = CaseFile(title="Test V6 Case", contract_type="Bienes", status="CREATED", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    # 2. Call the API
    payload = {
        "requirement_type": "TECHNICAL",
        "description": "Must have 16GB RAM",
        "mandatory": True
    }
    response = admin_client.post(f"/api/v6/cases/{case.id}/requirements", json=payload)
    assert response.status_code == 200, response.text
    
    # 3. Verify AuditLog
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "CREATE_REQUIREMENT",
        AuditLog.entity_id == str(response.json()["id"])
    ).first()
    assert audit is not None
    assert audit.tenant_id == "mega_tenant"

def test_create_supplier_generates_audit(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    payload = {
        "ruc": "20123456789",
        "business_name": "Tech Corp"
    }
    response = admin_client.post("/api/v6/suppliers", json=payload)
    assert response.status_code == 200, response.text
    
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "CREATE_SUPPLIER",
        AuditLog.entity_id == str(response.json()["id"])
    ).first()
    assert audit is not None

def test_create_supplier_offer_generates_audit(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    case = CaseFile(title="Test V6 Case", contract_type="Bienes", status="CREATED", tenant_id="mega_tenant")
    db_session.add(case)
    
    supplier = Supplier(ruc="20123456789", business_name="Tech Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    
    payload = {
        "supplier_id": supplier.id,
        "price": 5000.00
    }
    response = admin_client.post(f"/api/v6/cases/{case.id}/offers", json=payload)
    assert response.status_code == 200, response.text
    
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "CREATE_SUPPLIER_OFFER",
        AuditLog.entity_id == str(response.json()["id"])
    ).first()
    assert audit is not None
