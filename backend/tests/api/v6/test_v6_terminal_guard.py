from fastapi.testclient import TestClient
from app.models.domain import CaseFile
from sqlalchemy.orm import Session

def test_terminal_guard_blocks_mutation(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    # 1. Setup a CaseFile in a TERMINAL state
    case = CaseFile(title="Test V6 Case Terminal", contract_type="Bienes", status="APPROVED", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    # 2. Try to mutate it (e.g. create requirement)
    payload = {
        "requirement_type": "TECHNICAL",
        "description": "Must have 16GB RAM",
        "mandatory": True
    }
    response = admin_client.post(f"/api/v6/cases/{case.id}/requirements", json=payload)
    
    # 3. Verify it's blocked with 409
    assert response.status_code == 409
    assert "terminal status" in response.text
    
    # 4. Also verify COMPLETED state
    case.status = "COMPLETED"
    db_session.commit()
    
    response2 = admin_client.post(f"/api/v6/cases/{case.id}/requirements", json=payload)
    assert response2.status_code == 409
    assert "terminal status" in response2.text

def test_terminal_guard_allows_mutation_on_active(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    # 1. Setup a CaseFile in an active state
    case = CaseFile(title="Test V6 Case Active", contract_type="Bienes", status="CREATED", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    # 2. Try to mutate it
    payload = {
        "requirement_type": "TECHNICAL",
        "description": "Must have 16GB RAM",
        "mandatory": True
    }
    response = admin_client.post(f"/api/v6/cases/{case.id}/requirements", json=payload)
    
    # 3. Verify it works
    assert response.status_code == 200
