import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from app.api.auth import get_current_user
from app.api.exceptions import UnauthorizedException
from app.models.domain import User, UserTenantQuarantine, Tenant, AuditLog
from app.schemas.auth import TokenData
from jose import jwt
from app.api.auth import SECRET_KEY, ALGORITHM
from click.testing import CliRunner
from app.cli.quarantine_cli import resolve
import uuid

@pytest.fixture
def mock_db_session():
    mock_db = MagicMock()
    return mock_db

def test_auth_rejects_null_tenant(mock_db_session):
    user = User(username="test", is_active=True, tenant_id=None, tenant_resolution_status="RESOLVED", session_version=1)
    mock_db_session.query().filter().first.return_value = user
    token = jwt.encode({"sub": "test", "purpose": "access", "jti": "jti_test", "session_version": 1}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedException) as exc:
        get_current_user(token=token, db=mock_db_session)
    assert "User tenant assignment missing" in str(exc.value)

def test_auth_rejects_unresolved_quarantine(mock_db_session):
    user = User(username="test", is_active=True, tenant_id=1, tenant_resolution_status="QUARANTINED", session_version=1)
    mock_db_session.query().filter().first.return_value = user
    token = jwt.encode({"sub": "test", "purpose": "access", "jti": "jti_test", "session_version": 1}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedException) as exc:
        get_current_user(token=token, db=mock_db_session)
    assert "User is quarantined or unresolved" in str(exc.value)

def test_auth_rejects_inactive(mock_db_session):
    user = User(username="test", is_active=False, tenant_id=1, tenant_resolution_status="RESOLVED", session_version=1)
    mock_db_session.query().filter().first.return_value = user
    token = jwt.encode({"sub": "test", "purpose": "access", "jti": "jti_test", "session_version": 1}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedException) as exc:
        get_current_user(token=token, db=mock_db_session)
    assert "Inactive user" in str(exc.value)

def test_cli_resolve_quarantine_real_db(db_session, setup_mega_tenant):
    runner = CliRunner()
    
        # 1. Prepare data
    admin_u = db_session.query(User).filter_by(role="ADMIN").first()
    if not admin_u:
        admin_u = User(
            username=f"admin_{uuid.uuid4().hex[:8]}",
            password_hash="h",
            is_active=True,
            role="ADMIN",
            tenant_id=setup_mega_tenant.id,
        )
        db_session.add(admin_u)

    quarantine_origin = Tenant(
        id=f"quarantine_origin_{uuid.uuid4().hex[:8]}",
        name="Quarantine Origin",
    )
    db_session.add(quarantine_origin)
    db_session.flush()

    target_u = User(
        username=f"ambiguous_{uuid.uuid4().hex[:8]}",
        password_hash="h",
        is_active=False,
        role="USER",
        tenant_id=quarantine_origin.id,
        tenant_resolution_status="QUARANTINED",
        quarantined_at=datetime.now(timezone.utc),
    )
    db_session.add(target_u)
    db_session.commit()

    quarantine = UserTenantQuarantine(
        user_id=target_u.id,
        reason_code="AMBIGUOUS",
        status="QUARANTINED",
    )
    db_session.add(quarantine)
    db_session.commit()
    
    # 2. Execute command patching SessionLocal to use db_session
    with patch("app.cli.quarantine_cli.SessionLocal", return_value=db_session), patch.object(db_session, "close"):
        result = runner.invoke(resolve, [target_u.username, setup_mega_tenant.id, "ticket-123", "--actor", admin_u.username])
        
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "successfully resolved" in result.output
    
    # 3. Verify target user
    db_session.refresh(target_u)
    assert target_u.tenant_id == setup_mega_tenant.id
    assert target_u.tenant_resolution_status == "RESOLVED"
    
    db_session.refresh(quarantine)
    assert quarantine.status == "RESOLVED"
    assert quarantine.resolution_reference == "ticket-123"
    
    # 4. Verify AuditLog
    log = db_session.query(AuditLog).filter_by(action="QUARANTINE_RESOLVED", entity_id=str(target_u.id)).first()
    assert log is not None, "AuditLog for QUARANTINE_RESOLVED was not created!"
    # The requirement: "actor_id NO SEA NULO"
    assert log.user_id is not None, "AuditLog user_id cannot be NULL!"
    assert log.user_id == admin_u.id, "AuditLog user_id must match the admin who ran the CLI!"

def test_cli_resolve_already_resolved(db_session, setup_mega_tenant):
    runner = CliRunner()
    
    admin_u = db_session.query(User).filter_by(role="ADMIN").first()
    if not admin_u:
        admin_u = User(username=f"admin2_{uuid.uuid4().hex[:8]}", password_hash="h", is_active=True, role='ADMIN', tenant_id=setup_mega_tenant.id)
        db_session.add(admin_u)
        
    target_u = User(username=f"resolved_{uuid.uuid4().hex[:8]}", password_hash="h", is_active=True, role='USER', tenant_id=setup_mega_tenant.id, tenant_resolution_status="RESOLVED")
    db_session.add(target_u)
    db_session.commit()
    
    quarantine = UserTenantQuarantine(user_id=target_u.id, reason_code="AMBIGUOUS", status="RESOLVED", resolved_at=datetime.now(timezone.utc))
    db_session.add(quarantine)
    db_session.commit()
    
    with patch("app.cli.quarantine_cli.SessionLocal", return_value=db_session), patch.object(db_session, "close"):
        result = runner.invoke(resolve, [target_u.username, setup_mega_tenant.id, "ticket-999", "--actor", admin_u.username])
        
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "already resolved" in result.output

def test_cli_resolve_invalid_actor(db_session, setup_mega_tenant):
    runner = CliRunner()
    
    target_u = User(username=f"target_{uuid.uuid4().hex[:8]}", password_hash="h", is_active=False, role='USER', tenant_id=setup_mega_tenant.id, tenant_resolution_status="QUARANTINED", quarantined_at=datetime.now(timezone.utc))
    db_session.add(target_u)
    db_session.commit()
    
    # Intencional fallo: actor inexistente
    with patch("app.cli.quarantine_cli.SessionLocal", return_value=db_session), patch.object(db_session, "close"):
        result = runner.invoke(resolve, [target_u.username, setup_mega_tenant.id, "ticket-999", "--actor", "nonexistent_actor"])
        
    assert result.exit_code != 0
    assert "Actor 'nonexistent_actor' not found" in result.output
