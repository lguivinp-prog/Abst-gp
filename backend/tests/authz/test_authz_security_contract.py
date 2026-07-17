import pytest

# Since endpoints and security guards are not implemented yet, 
# these tests serve as TDD contracts. We mark them as expected failures.

@pytest.mark.xfail(reason="Authz security guards not implemented yet")
def test_operator_cannot_administer_users(client):
    """
    TDD Contract: A user with role OPERATOR must receive 403 Forbidden 
    when trying to access /admin/users endpoints.
    """
    # Assuming 'client' is an authenticated test client with OPERATOR role
    response = client.post("/admin/users", json={"username": "new_op"})
    assert response.status_code == 403

@pytest.mark.xfail(reason="CaseFile assignment guards not implemented yet")
def test_operator_cannot_access_unassigned_case(client):
    """
    TDD Contract: A user with role OPERATOR must receive 404 Not Found
    (to prevent enumeration) when accessing a case not assigned to them.
    """
    # Assuming 'client' is OPERATOR and case '123' is NOT assigned to them
    response = client.get("/cases/123")
    assert response.status_code == 404

@pytest.mark.xfail(reason="Admin global access not fully enforced yet")
def test_admin_can_see_all_cases(admin_client):
    """
    TDD Contract: A user with role ADMIN can access any case, assigned or not.
    """
    # Assuming 'admin_client' is ADMIN and case '123' is assigned to another operator
    response = admin_client.get("/cases/123")
    assert response.status_code == 200

@pytest.mark.xfail(reason="Unassigned case rules not implemented yet")
def test_unassigned_case_exclusive_to_admin(client, admin_client):
    """
    TDD Contract: A case without an assigned operator can only be accessed by ADMIN.
    """
    # Assuming case '999' is unassigned
    response_op = client.get("/cases/999")
    assert response_op.status_code == 404
    
    response_admin = admin_client.get("/cases/999")
    assert response_admin.status_code == 200
