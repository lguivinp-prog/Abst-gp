import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.auth import verify_case_access, get_current_active_user, get_current_user
from app.core.database import get_db
from app.models.domain import CaseFile, User

# Fake user & case data for tests
mock_user = User(id=1, username="admin", role="ADMIN", tenant_id="mega_tenant")
mock_case = CaseFile(id=1, tenant_id="mega_tenant", status="COMPARING")

def override_verify_case_access():
    return mock_case

def override_get_current_user():
    return mock_user

@pytest.fixture(autouse=True)
def override_auth_dependencies():
    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[verify_case_access] = override_verify_case_access
    app.dependency_overrides[get_current_active_user] = override_get_current_user
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)

client = TestClient(app)

@pytest.fixture
def mock_db_session():
    original_overrides = dict(app.dependency_overrides)
    session_mock = MagicMock()
    app.dependency_overrides[get_db] = lambda: session_mock
    try:
        yield session_mock
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)

def test_comparison_run_idempotent_ready_generate(mock_db_session):
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

    mock_db_session.query.side_effect = query_side_effect

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Comparison already completed",
        "already_completed": True
    }

    # Ensure run_comparison was not called
    mock_db_session.add.assert_not_called()

@patch("app.api.routers.cases.run_comparison")
def test_comparison_run_success(mock_run_comparison, mock_db_session):
    # Mocking the case query
    query_mock = MagicMock()
    mock_db_session.query.return_value = query_mock
    filter_mock = MagicMock()
    query_mock.filter.return_value = filter_mock
    with_for_update_mock = MagicMock()
    filter_mock.populate_existing.return_value.with_for_update.return_value = with_for_update_mock
    
    case_mock = MagicMock(status="COMPARING", id=1, tenant_id="mega_tenant")
    with_for_update_mock.first.return_value = case_mock

    # Mocking the existing_comparisons query count
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

    mock_db_session.query.side_effect = query_side_effect
    
    mock_run_comparison.return_value = [{"field_name": "Test", "status": "Coincide"}]

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Comparison completed",
        "already_completed": False
    }
    assert case_mock.status == "READY_GENERATE"
    mock_db_session.commit.assert_called_once()
    mock_db_session.add.assert_called()

def test_comparison_run_inconsistent_state(mock_db_session):
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

    mock_db_session.query.side_effect = query_side_effect

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 409
    assert "Inconsistent state" in response.json()["detail"]
    mock_db_session.commit.assert_not_called()

def test_comparison_run_wrong_status(mock_db_session):
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

    mock_db_session.query.side_effect = query_side_effect

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 409
    assert "not ready for comparison" in response.json()["detail"]
    mock_db_session.commit.assert_not_called()

@patch("app.api.routers.cases.run_comparison")
def test_comparison_run_rollback_on_failure(mock_run_comparison, mock_db_session):
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

    mock_db_session.query.side_effect = query_side_effect
    
    # Force exception during run_comparison
    mock_run_comparison.side_effect = ValueError("OCR Engine crashed")

    response = client.post("/cases/1/comparison/run")

    assert response.status_code == 500
    assert response.json()["detail"] == "An error occurred during comparison generation"
    
    # Assert rollback was called
    mock_db_session.rollback.assert_called_once()
    mock_db_session.commit.assert_not_called()
