import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import AuditLog

def test_history_list(client: TestClient, db_session: Session, test_case_file):
    # Create dummy audit log
    audit = AuditLog(
        user_id=1,
        tenant_id="mega_tenant",
        action="TEST_ACTION",
        entity_type="CaseFile",
        entity_id=str(test_case_file.id),
        details="Test details",
        status="SUCCESS"
    )
    db_session.add(audit)
    db_session.commit()

    response = client.get(
        f"/api/v6/cases/{test_case_file.id}/history",
        headers={"Authorization": "Bearer test_token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["action"] == "TEST_ACTION"

def test_history_cross_tenant_rejected(other_client: TestClient, db_session: Session, test_case_file):
    cross_res = other_client.get(
        f"/api/v6/cases/{test_case_file.id}/history",
        headers={"Authorization": "Bearer other_tenant_token"}
    )
    assert cross_res.status_code in [403, 404]
