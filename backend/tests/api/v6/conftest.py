import pytest
from sqlalchemy.orm import Session
from app.models.domain import CaseFile

@pytest.fixture
def test_case_file(db_session: Session, setup_mega_tenant):
    case = CaseFile(
        title="Test Case V6",
        contract_type="services",
        tenant_id="mega_tenant",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case

@pytest.fixture(scope="function")
def other_client(db_session):
    from app.main import app
    from fastapi.testclient import TestClient
    from app.api.auth import get_current_active_user, get_current_user
    from app.models.domain import User

    def override_get_current_active_user_other():
        return User(id=99, username="other", role="OPERATOR", is_active=True, must_change_password=False, tenant_id="other_tenant")
    
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user_other
    app.dependency_overrides[get_current_user] = override_get_current_active_user_other
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)
