from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.validation_request import ValidationRequest
from app.models.domain import AuditLog
import json

def test_get_supplier_profile(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    supplier = Supplier(ruc="20123456789", business_name="Tech Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.flush()
    
    profile = SupplierProfile(supplier_id=supplier.id, address="Av 123", aggregated_score=8.5, status_summary="VERIFIED")
    db_session.add(profile)
    db_session.commit()
    
    response = admin_client.get(f"/api/v6/suppliers/{supplier.id}/profile")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ruc"] == "20123456789"
    assert data["profile"]["address"] == "Av 123"
    assert data["profile"]["status_summary"] == "VERIFIED"

def test_create_validation_request_is_async_and_audited(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    supplier = Supplier(ruc="20123456789", business_name="Tech Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    
    payload = {"source": "SUNAT"}
    response = admin_client.post(f"/api/v6/suppliers/{supplier.id}/validation-requests", json=payload)
    
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "PENDING" # Async behavior enforced
    
    req_id = data["id"]
    db_req = db_session.query(ValidationRequest).filter_by(id=req_id).first()
    assert db_req is not None
    assert db_req.attempt_number == 1
    
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "REQUEST_VALIDATION",
        AuditLog.entity_id == str(req_id)
    ).first()
    assert audit is not None
