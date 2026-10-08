import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.contractual_condition import ContractualCondition

@pytest.fixture
def terminal_cases(db_session, setup_mega_tenant):
    case_approved = CaseFile(title="Test V6 Case Approved", contract_type="Bienes", status="APPROVED", tenant_id="mega_tenant")
    case_completed = CaseFile(title="Test V6 Case Completed", contract_type="Bienes", status="COMPLETED", tenant_id="mega_tenant")
    db_session.add_all([case_approved, case_completed])
    db_session.commit()
    
    from app.models.v6.supplier import Supplier
    
    # Create or get a supplier first to satisfy foreign key constraints
    supplier = db_session.query(Supplier).filter_by(id=1).first()
    if not supplier:
        supplier = Supplier(id=1, tenant_id="mega_tenant", ruc="12345678901", business_name="Test Supplier")
        db_session.add(supplier)
        db_session.commit()
    
    # Add dummy offer for routes needing offer_id
    offer1 = SupplierOffer(case_id=case_approved.id, supplier_id=1, total_amount=100.0, status="PENDING")
    offer2 = SupplierOffer(case_id=case_completed.id, supplier_id=1, total_amount=100.0, status="PENDING")
    db_session.add_all([offer1, offer2])
    db_session.commit()
    
    return {"APPROVED": case_approved, "COMPLETED": case_completed}

@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_terminal_guard_blocks_mutations(admin_client: TestClient, db_session: Session, terminal_cases, status_key):
    case = terminal_cases[status_key]
    case_id = case.id
    
    offer = db_session.query(SupplierOffer).filter_by(case_id=case_id).first()
    offer_id = offer.id

    endpoints = [
        # Requirements
        ("POST", f"/api/v6/cases/{case_id}/requirements", {"requirement_type": "TECHNICAL", "description": "Desc", "mandatory": True}),
        # Procurement items
        ("POST", f"/api/v6/cases/{case_id}/procurement-items", {"item_number": "1", "description": "D", "quantity": 1, "unit": "U"}),
        # Suppliers
        ("POST", f"/api/v6/cases/{case_id}/suppliers", {"ruc": "12345678901", "business_name": "Test"}),
        # Offers
        ("POST", f"/api/v6/cases/{case_id}/offers", {"supplier_id": 1}),
        # Evaluations
        ("PUT", f"/api/v6/cases/{case_id}/evaluations/999", {"status": "MET", "explanation": "Ok"}),
        # Selection
        ("POST", f"/api/v6/cases/{case_id}/selection", {"supplier_offer_id": offer_id, "justification_comment": "Ok"}),
    ]
    
    for method, path, payload in endpoints:
        if method == "POST":
            response = admin_client.post(path, json=payload)
        elif method == "PUT":
            response = admin_client.put(path, json=payload)
        elif method == "DELETE":
            response = admin_client.delete(path)
            
        assert response.status_code == 409, f"Endpoint {method} {path} failed to block terminal state"
        assert "terminal status" in response.text or "not mutable" in response.text

@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_contractual_get_side_effect_free(admin_client: TestClient, db_session: Session, terminal_cases, status_key):
    case = terminal_cases[status_key]
    case_id = case.id
    
    offer = db_session.query(SupplierOffer).filter_by(case_id=case_id).first()
    offer_id = offer.id
    
    # Pre-seed a ContractualCondition to prove it's NOT deleted
    cond = ContractualCondition(
        supplier_offer_id=offer_id,
        key="TEST",
        label="Test",
        required_value="A",
        offered_value="B",
        resolution_rule="EXACT",
        status="PENDING"
    )
    db_session.add(cond)
    db_session.commit()
    
    # Get initial count
    initial_count = db_session.query(ContractualCondition).filter_by(supplier_offer_id=offer_id).count()
    
    response = admin_client.get(f"/api/v6/cases/{case_id}/evaluations/contractual")
    assert response.status_code == 200
    
    # Verify count unchanged
    final_count = db_session.query(ContractualCondition).filter_by(supplier_offer_id=offer_id).count()
    assert initial_count == final_count, "Contractual GET should not mutate existing rows for terminal cases"
    
    # Case status unchanged
    db_session.refresh(case)
    assert case.status == status_key

def test_terminal_guard_allows_mutation_on_active(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    case = CaseFile(title="Test V6 Case Active", contract_type="Bienes", status="CREATED", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    payload = {
        "requirement_type": "TECHNICAL",
        "description": "Must have 16GB RAM",
        "mandatory": True
    }
    response = admin_client.post(f"/api/v6/cases/{case.id}/requirements", json=payload)
    
    assert response.status_code == 200
