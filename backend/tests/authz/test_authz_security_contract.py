import pytest

# Since endpoints and security guards are not implemented yet, 
# these tests serve as TDD contracts. We mark them as expected failures.

def test_operator_cannot_administer_users(client):
    """
    TDD Contract: A user with role OPERATOR must receive 403 Forbidden 
    when trying to access /admin/users endpoints.
    """
    # Assuming 'client' is an authenticated test client with OPERATOR role
    response = client.post("/admin/users", json={"username": "new_op"})
    assert response.status_code == 403

def test_operator_cannot_access_unassigned_case(client):
    """
    TDD Contract: A user with role OPERATOR must receive 404 Not Found
    (to prevent enumeration) when accessing a case not assigned to them.
    """
    print("STARTING TEST")
    response = client.get("/cases/123")
    print(f"RESPONSE RECEIVED {response.status_code}")
    assert response.status_code == 404

def test_admin_can_see_all_cases(admin_client, db_session):
    """
    TDD Contract: A user with role ADMIN can access any case, assigned or not.
    """
    from app.models.domain import CaseFile
    c = CaseFile(title="T", contract_type="C", status="CREATED")
    db_session.add(c)
    db_session.commit()
    
    response = admin_client.get(f"/cases/{c.id}")
    assert response.status_code == 200

def test_unassigned_case_exclusive_to_admin(db_session):
    from app.main import app
    from fastapi.testclient import TestClient
    from app.api.auth import get_current_active_user, get_current_user
    from app.models.domain import User, CaseFile

    c = CaseFile(title="T", contract_type="C", status="CREATED")
    db_session.add(c)
    db_session.commit()

    def override_get_current_active_user():
        return User(id=1, username="operator", role="OPERATOR", is_active=True, must_change_password=False, tenant_id="mega_tenant")
    
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    app.dependency_overrides[get_current_user] = override_get_current_active_user
    
    with TestClient(app) as client:
        response_op = client.get(f"/cases/{c.id}")
        assert response_op.status_code == 404
        
    def override_get_current_active_user_admin():
        return User(id=2, username="admin", role="ADMIN", is_active=True, must_change_password=False, tenant_id="mega_tenant")
    
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user_admin
    app.dependency_overrides[get_current_user] = override_get_current_active_user_admin
    
    with TestClient(app) as client:
        response_admin = client.get(f"/cases/{c.id}")
        assert response_admin.status_code == 200

    app.dependency_overrides.clear()
