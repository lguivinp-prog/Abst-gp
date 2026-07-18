import pytest
from sqlalchemy import inspect
from app.models.domain import User, CaseFile, AuditLog

@pytest.mark.xfail(reason="Phase 5 not started", strict=True)
def test_user_model_has_required_fields():
    """
    TDD Contract: The User model must include new authz fields.
    """
    mapper = inspect(User)
    columns = [c.key for c in mapper.columns]
    
    expected_fields = [
        "id",
        "username",
        "password_hash",
        "role",
        "is_active",
        "must_change_password",
        "created_by_user_id",
        "last_login_at",
        "failed_login_count",
        "locked_until",
        "password_changed_at"
    ]
    
    for field in expected_fields:
        assert field in columns, f"User model is missing expected field: {field}"

@pytest.mark.xfail(reason="Phase 5 not started", strict=True)
def test_case_file_model_has_assignment_fields():
    """
    TDD Contract: The CaseFile model must support assignment to operators.
    """
    mapper = inspect(CaseFile)
    columns = [c.key for c in mapper.columns]
    
    expected_fields = [
        "assigned_to_user_id",
        "assigned_by_user_id",
        "assigned_at"
    ]
    
    for field in expected_fields:
        assert field in columns, f"CaseFile model is missing assignment field: {field}"

@pytest.mark.xfail(reason="Phase 5 not started", strict=True)
def test_audit_log_model_contract():
    """
    TDD Contract: The AuditLog model must support robust auditing.
    """
    mapper = inspect(AuditLog)
    columns = [c.key for c in mapper.columns]
    
    # We expect 'status' to be added and 'entity_id' to support String (UUIDs)
    assert "status" in columns, "AuditLog model is missing 'status' field"
    
    # Check that entity_id type allows strings/UUIDs (this will fail if it's still Integer)
    entity_id_col = mapper.columns.get("entity_id")
    assert entity_id_col is not None
    assert str(entity_id_col.type).upper() == "VARCHAR" or str(entity_id_col.type).upper() == "STRING", "AuditLog.entity_id must be String to support UUIDs"
