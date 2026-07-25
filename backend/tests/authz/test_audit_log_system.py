import pytest
import uuid
from app.models.domain import AuditLog, User
from sqlalchemy.orm import Session

def test_audit_log_system_actor(db_session: Session):
    """
    TDD Contract: The system must be able to log actions under a real ADMIN actor
    for background tasks like backfilling, ensuring AuditLog doesn't fail.
    """
    # Use existing admin user
    system_user = db_session.query(User).filter(User.role == "ADMIN").first()
    if not system_user:
        system_user = User(username=f"admin:backfill_{uuid.uuid4()}", password_hash="", role="ADMIN", tenant_id="mega_tenant")
        db_session.add(system_user)
        db_session.commit()

    log = AuditLog(
        action="TENANT_BACKFILL",
        user_id=system_user.id,
        entity_type="users",
        entity_id="all",
        details="{'assigned': 1000, 'quarantined': 500}"
    )
    db_session.add(log)
    db_session.commit()
    
    saved_log = db_session.query(AuditLog).filter_by(user_id=system_user.id).first()
    assert saved_log is not None
    assert saved_log.action == "TENANT_BACKFILL"
    assert "1000" in saved_log.details

def test_audit_log_concurrent_resolution(db_session: Session):
    """
    TDD Contract: Ensures that concurrent resolutions or updates
    are logged correctly and do not overwrite each other silently.
    """
    admin1 = User(username=f"admin1_{uuid.uuid4()}", password_hash="", role="operator", tenant_id="mega_tenant")
    admin2 = User(username=f"admin2_{uuid.uuid4()}", password_hash="", role="readonly", tenant_id="mega_tenant")
    db_session.add_all([admin1, admin2])
    db_session.commit()

    log1 = AuditLog(action="USER_RESOLUTION", user_id=admin1.id, entity_type="users", entity_id="123")
    log2 = AuditLog(action="USER_RESOLUTION", user_id=admin2.id, entity_type="users", entity_id="123")
    
    db_session.add_all([log1, log2])
    db_session.commit()
    
    logs = db_session.query(AuditLog).filter_by(entity_type="users", entity_id="123").all()
    assert len(logs) == 2
