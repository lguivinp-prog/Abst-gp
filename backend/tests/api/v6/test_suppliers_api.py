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


