import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.main import app
from app.api.auth import verify_case_access, get_current_active_user
from app.models.domain import CaseFile, User

# Fake user & case data for tests
mock_user = User(id=1, username="admin", role="ADMIN", tenant_id="mega_tenant")
mock_case = CaseFile(id=1, tenant_id="mega_tenant", status="COMPARING")

def override_verify_case_access():
    return mock_case

def override_get_current_active_user():
    return mock_user

@pytest.fixture(autouse=True)
def override_auth_dependencies():
    app.dependency_overrides[verify_case_access] = override_verify_case_access
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    yield
    app.dependency_overrides.pop(verify_case_access, None)
    app.dependency_overrides.pop(get_current_active_user, None)

client = TestClient(app)

@pytest.fixture
def mock_db_session():
    with patch("app.api.routers.cases.get_db") as mock_get_db:
        session_mock = MagicMock()
        mock_get_db.return_value = session_mock
        yield session_mock

@pytest.fixture
def db_session_mock():
    # Provide a mock db session that can be injected via dependency_overrides
    session_mock = MagicMock()
    app.dependency_overrides["app.core.database.get_db"] = lambda: session_mock
    yield session_mock
    app.dependency_overrides.pop("app.core.database.get_db", None)

@patch("app.api.routers.cases.get_db")
def test_comparison_run_idempotent_ready_generate(mock_get_db):
    session_mock = MagicMock()
    mock_get_db.return_value = session_mock
    
    # Override get_db in dependency_overrides for this test
    app.dependency_overrides[mock_get_db] = lambda: session_mock

    # First query is for CaseFile
    case_mock = MagicMock(status="READY_GENERATE", id=1, tenant_id="mega_tenant")
    
    def query_side_effect(model):
        from app.models.domain import CaseFile, FinalConditionComparison, RolloutTenantAssignment
        m = MagicMock()
        if model == CaseFile:
            m.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value = case_mock
        elif model == FinalConditionComparison:
            m.filter.return_value.count.return_value = 1
        elif model == RolloutTenantAssignment:
            m.filter.return_value.first.return_value = MagicMock(routing_mode="FORCE_LEGACY", override_until=None)
        return m

    session_mock.query.side_effect = query_side_effect

    # Need to patch the dependency inject for get_db directly since FastAPI resolves it
    with patch("app.api.routers.cases.get_db", return_value=session_mock):
        from app.core.database import get_db
        app.dependency_overrides[get_db] = lambda: session_mock

        response = client.post("/cases/1/comparison/run")

        assert response.status_code == 200
        assert response.json() == {
            "message": "Comparison already completed",
            "already_completed": True
        }
        
        # Ensure run_comparison was not called
        session_mock.add.assert_not_called()

@patch("app.api.routers.cases.run_comparison")
def test_comparison_run_success(mock_run_comparison):
    session_mock = MagicMock()
    
    # Mocking the case query
    query_mock = MagicMock()
    session_mock.query.return_value = query_mock
    filter_mock = MagicMock()
    query_mock.filter.return_value = filter_mock
    with_for_update_mock = MagicMock()
    filter_mock.populate_existing.return_value.with_for_update.return_value = with_for_update_mock
    
    case_mock = MagicMock(status="COMPARING", id=1, tenant_id="mega_tenant")
    with_for_update_mock.first.return_value = case_mock

    # Mocking the existing_comparisons query count
    # The second query in the endpoint is existing_comparisons
    def query_side_effect(model):
        from app.models.domain import CaseFile, FinalConditionComparison, QuotationExtraction, ParsedSection, RolloutTenantAssignment
        m = MagicMock()
        if model == CaseFile:
            m.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value = case_mock
        elif model == FinalConditionComparison:
            m.filter.return_value.count.return_value = 0
        elif model == QuotationExtraction:
            m.filter.return_value.first.return_value = MagicMock(raw_json={"q": 1})
        elif model == ParsedSection:
            m.filter.return_value.all.return_value = [MagicMock(is_selected=True, current_text="Forma de pago 30 dias")]
        elif model == RolloutTenantAssignment:
            m.filter.return_value.first.return_value = MagicMock(routing_mode="FORCE_LEGACY", override_until=None)
        return m

    session_mock.query.side_effect = query_side_effect
    
    mock_run_comparison.return_value = [{"field_name": "Test", "status": "Coincide"}]

    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: session_mock

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Comparison completed",
        "already_completed": False
    }
    assert case_mock.status == "READY_GENERATE"
    session_mock.commit.assert_called_once()
    session_mock.add.assert_called()

def test_comparison_run_inconsistent_state():
    session_mock = MagicMock()
    
    case_mock = MagicMock(status="COMPARING", id=1, tenant_id="mega_tenant")
    
    def query_side_effect(model):
        from app.models.domain import CaseFile, FinalConditionComparison, RolloutTenantAssignment
        m = MagicMock()
        if model == CaseFile:
            m.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value = case_mock
        elif model == FinalConditionComparison:
            m.filter.return_value.count.return_value = 1 # Inconsistent!
        elif model == RolloutTenantAssignment:
            m.filter.return_value.first.return_value = MagicMock(routing_mode="FORCE_LEGACY", override_until=None)
        return m

    session_mock.query.side_effect = query_side_effect

    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: session_mock

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 409
    assert "Inconsistent state" in response.json()["detail"]
    session_mock.commit.assert_not_called()

def test_comparison_run_wrong_status():
    session_mock = MagicMock()
    
    case_mock = MagicMock(status="CREATED", id=1, tenant_id="mega_tenant")
    
    def query_side_effect(model):
        from app.models.domain import CaseFile, FinalConditionComparison, RolloutTenantAssignment
        m = MagicMock()
        if model == CaseFile:
            m.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value = case_mock
        elif model == FinalConditionComparison:
            m.filter.return_value.count.return_value = 0
        elif model == RolloutTenantAssignment:
            m.filter.return_value.first.return_value = MagicMock(routing_mode="FORCE_LEGACY", override_until=None)
        return m

    session_mock.query.side_effect = query_side_effect

    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: session_mock

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 409
    assert "not ready for comparison" in response.json()["detail"]
    session_mock.commit.assert_not_called()

@patch("app.api.routers.cases.run_comparison")
def test_comparison_run_rollback_on_failure(mock_run_comparison):
    session_mock = MagicMock()
    case_mock = MagicMock(status="COMPARING", id=1, tenant_id="mega_tenant")
    
    def query_side_effect(model):
        from app.models.domain import CaseFile, FinalConditionComparison, QuotationExtraction, ParsedSection, RolloutTenantAssignment
        m = MagicMock()
        if model == CaseFile:
            m.filter.return_value.populate_existing.return_value.with_for_update.return_value.first.return_value = case_mock
        elif model == FinalConditionComparison:
            m.filter.return_value.count.return_value = 0
        elif model == QuotationExtraction:
            m.filter.return_value.first.return_value = MagicMock(raw_json={"q": 1})
        elif model == ParsedSection:
            m.filter.return_value.all.return_value = []
        elif model == RolloutTenantAssignment:
            m.filter.return_value.first.return_value = MagicMock(routing_mode="FORCE_LEGACY", override_until=None)
        return m

    session_mock.query.side_effect = query_side_effect
    
    # Force exception during run_comparison
    mock_run_comparison.side_effect = ValueError("OCR Engine crashed")

    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: session_mock

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 500
    assert response.json()["detail"] == "An error occurred during comparison generation"
    
    # Assert rollback was called
    session_mock.rollback.assert_called_once()
    session_mock.commit.assert_not_called()
