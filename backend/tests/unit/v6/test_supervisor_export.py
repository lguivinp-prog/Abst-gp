import pytest
from app.services.v6.export.supervisor_export_service import SupervisorExportService, SupervisorExportSchema
from app.models.v6.case_operational_snapshot import CaseOperationalSnapshot
from app.models.domain import AuditLog, User
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi import HTTPException

def test_export_schema_formatting():
    snapshot = CaseOperationalSnapshot(
        case_id=1,
        current_status="EVALUATION",
        risk_level="HIGH",
        risk_reason=[{"type": "BLOCKED_VALIDATION", "source": "SupplierProfile"}],
        pending_actions=["Require Manual Review"],
        updated_at=datetime(2026, 8, 9, 12, 0)
    )
    
    mock_supplier = {
        "ruc": "20555444333",
        "sunat": "PASSED",
        "rnp": "PASSED",
        "fup": "PASSED",
        "ciiu": "WARNING",
        "experience_amount": 150000.0
    }
    
    row = SupervisorExportSchema.format_row(snapshot, mock_supplier)
    assert row[0] == "1"
    assert row[1] == "EVALUATION"
    assert row[2] == "HIGH"
    assert row[3] == "20555444333"
    assert "BLOCKED_VALIDATION" in row[9]
    assert "Require Manual Review" in row[10]

def test_export_service_time_limit(db_session: Session):
    service = SupervisorExportService(db_session)
    
    # 7 months ago
    old_date = (datetime.utcnow() - timedelta(days=210)).isoformat()
    filters = {"start_date": old_date}
    
    with pytest.raises(HTTPException) as excinfo:
        # Evaluate the generator to trigger the DB query & exception
        list(service.generate_csv_stream(1, "t1", filters))
        
    assert excinfo.value.status_code == 400
    assert "6 meses" in excinfo.value.detail

def test_export_service_audit_logging(db_session: Session):
    from app.models.domain import Tenant, User

    tenant = db_session.get(Tenant, "tenantA")
    if tenant is None:
        tenant = Tenant(id="tenantA", name="Tenant A")
        db_session.add(tenant)
        db_session.flush()

    user = db_session.get(User, 10)
    if user is None:
        user = User(
            id=10,
            username="supervisor_export_user",
            password_hash="h",
            role="ADMIN",
            is_active=True,
            tenant_id="tenantA",
            tenant_resolution_status="RESOLVED",
        )
        db_session.add(user)
        db_session.flush()

    service = SupervisorExportService(db_session)
    filters = {"risk_level": "HIGH"}

    list(service.generate_csv_stream(10, "tenantA", filters))
    
    # Check audit log
    audit = db_session.query(AuditLog).filter_by(action="EXPORT_GENERATED").first()
    assert audit is not None
    assert audit.user_id == 10
    assert audit.tenant_id == "tenantA"
    assert SupervisorExportSchema.VERSION in audit.details
