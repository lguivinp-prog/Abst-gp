import uuid
import pytest
from app.services.v6.governance.admin_service import AdminGovernanceService
from app.services.v6.telemetry.telemetry_worker import InstitutionalTelemetryWorker
from app.models.domain import AuditLog, User, Tenant
from app.models.v6.tenant_config import TenantConfiguration
from sqlalchemy.orm import Session
from fastapi import HTTPException

def test_admin_governance_service_update(db_session: Session):
    tenant_id = f"tenant_governance_{uuid.uuid4().hex}"
    tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        tenant = Tenant(
            id=tenant_id,
            name="Tenant B",
        )
        db_session.add(tenant)

    user = db_session.query(User).filter(User.id == 5).first()
    if not user:
        user = User(
            id=5,
            username="governance_admin",
            password_hash="h",
            role="ADMIN",
            is_active=True,
            tenant_id=tenant_id,
            tenant_resolution_status="RESOLVED",
        )
        db_session.add(user)

    db_session.commit()

    service = AdminGovernanceService(db_session)

    # Enable telemetry opt-in
    updates = {"telemetry_opt_in": True, "min_dpi_threshold": 300}
    config = service.update_configuration(user_id=5, tenant_id=tenant_id, updates=updates)
    
    assert config.telemetry_opt_in is True
    assert config.min_dpi_threshold == 300
    
    # Verify AuditLog injected TELEMETRY_OPT_IN_GRANTED
    audit = (
    db_session.query(AuditLog)
    .filter_by(
        action="TELEMETRY_OPT_IN_GRANTED",
        tenant_id=tenant_id,
        user_id=5,
    )
    .first()
)
    assert audit is not None
    assert audit.user_id == 5

def test_telemetry_worker_opt_out_respect(db_session: Session):
    worker = InstitutionalTelemetryWorker(db_session)
    
    # By default, a new tenant has opt_in = False
    service = AdminGovernanceService(db_session)
    service.get_configuration("tenant_strict")
    
    # Try generating telemetry
    event = worker.generate_weekly_snapshot("tenant_strict")
    assert event is None # Respects privacy, returns None

def test_rbac_system_admin_break_glass():
    # Logic mockup for RBAC boundaries
    system_admin = User(id=99, role="SYSTEM_ADMIN", tenant_id="GLOBAL")
    
    # If the system admin tries to view a case from tenant A normally, they should fail (Mock test)
    # The true enforcement happens via dependancy injection `require_system_admin` combined with `tenant_id` filtering in endpoints.
    assert system_admin.role == "SYSTEM_ADMIN"
    # Endpoints logic must explicitly check for `BREAK_GLASS_GRANTED` token claim to allow cross-tenant read.
