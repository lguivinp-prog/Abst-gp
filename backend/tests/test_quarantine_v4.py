import pytest
import threading
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
import os
import time

from app.models.domain import User, UserTenantQuarantine, AuditLog, Tenant
from app.core.database import get_db, SessionLocal
from app.cli.quarantine_cli import resolve
import click.testing

def get_test_db_url():
    return os.environ.get("DATABASE_URL")

def test_global_unique_username(db_session):
    # Setup test tenant
    tenant = Tenant(id="test_tenant", name="Test Tenant")
    db_session.merge(tenant)
    db_session.commit()

    # 1. dos usuarios activos no pueden compartir username
    user1 = User(username="unique_user", password_hash="hash", role="readonly", tenant_id="test_tenant")
    db_session.add(user1)
    db_session.commit()

    user2 = User(username="unique_user", password_hash="hash", role="readonly", tenant_id="test_tenant")
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 2. un usuario en cuarentena conserva y bloquea su username
    # 4. no puede registrarse otro usuario con el username del usuario en cuarentena
    user3 = User(username="quarantined_user", password_hash="hash", role="readonly", is_active=False, tenant_resolution_status="QUARANTINED", tenant_id=None)
    db_session.add(user3)
    db_session.commit()

    user4 = User(username="quarantined_user", password_hash="hash", role="readonly", tenant_id="test_tenant")
    db_session.add(user4)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 3. un usuario inactivo conserva y bloquea su username
    user5 = User(username="inactive_user", password_hash="hash", role="readonly", is_active=False, tenant_id="test_tenant")
    db_session.add(user5)
    db_session.commit()

    user6 = User(username="inactive_user", password_hash="hash", role="readonly", tenant_id="test_tenant")
    db_session.add(user6)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 5. la reactivacion del mismo usuario no crea una colision
    user5.is_active = True
    db_session.commit()
    assert user5.is_active == True

    # 6. usernames distintos siguen permitidos
    user7 = User(username="distinct_user", password_hash="hash", role="readonly", tenant_id="test_tenant")
    db_session.add(user7)
    db_session.commit()

    # 7. el DDL de PostgreSQL contiene la restriccion global y no el indice parcial
    engine = db_session.get_bind()
    with engine.connect() as conn:
        indexes = conn.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'users'")).fetchall()
        has_partial = any("WHERE" in idx[1] and "username" in idx[1] for idx in indexes)
        assert not has_partial, "Found partial index on username"
        
        # unique_constraint or unique_index on username
        has_global_unique = any("UNIQUE" in idx[1] and "username" in idx[1] and "WHERE" not in idx[1] for idx in indexes)
        assert has_global_unique, "Missing global unique constraint/index on username"


import json

def test_cli_sequential_resolution(db_session):
    # Test CLI parsing, actor validation, exit codes, and sanitized messages
    tenant = Tenant(id="seq_tenant", name="Sequential Tenant")
    db_session.merge(tenant)
    db_session.commit()

    # Admin is a singleton, grab existing or create
    admin = db_session.query(User).filter_by(role="ADMIN").first()
    if not admin:
        admin = User(username="admin_actor", password_hash="hash", role="ADMIN", is_active=True, tenant_id="seq_tenant")
        db_session.add(admin)

    user = User(username="seq_q_user", password_hash="hash", role="readonly", is_active=False, tenant_resolution_status="QUARANTINED", tenant_id=None)
    db_session.add(user)
    db_session.commit()

    quarantine = UserTenantQuarantine(user_id=user.id, reason_code="AMBIGUOUS", status="QUARANTINED")
    db_session.add(quarantine)
    db_session.commit()

    runner = click.testing.CliRunner()
    
    # 1. Parsing correctness and success
    result1 = runner.invoke(resolve, ["seq_q_user", "seq_tenant", "REF-SEQ-1", "--actor", admin.username])
    assert result1.exit_code == 0
    assert "successfully resolved" in result1.output

    # 2. Conflict exit code (AlreadyResolved)
    result2 = runner.invoke(resolve, ["seq_q_user", "seq_tenant", "REF-SEQ-1", "--actor", admin.username])
    assert result2.exit_code == 0 # Caught and echoed
    assert "Error:" in result2.output
    assert "already resolved" in result2.output

    # 3. Actor validation (Missing actor / invalid)
    result3 = runner.invoke(resolve, ["seq_q_user", "seq_tenant", "REF-SEQ-1", "--actor", "fake_actor"])
    assert result3.exit_code != 0
    assert "Actor 'fake_actor' not found" in result3.output

def test_concurrent_quarantine_resolution(db_session):
    from app.services.quarantine_service import resolve_user, QuarantineAlreadyResolvedError
    
    engine = create_engine(get_test_db_url(), pool_size=10, max_overflow=20)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Setup
    setup_session = TestingSessionLocal()
    tenant1 = Tenant(id="concurrent_tenant_1", name="Concurrent Tenant 1")
    tenant2 = Tenant(id="concurrent_tenant_2", name="Concurrent Tenant 2")
    setup_session.merge(tenant1)
    setup_session.merge(tenant2)
    setup_session.commit()
    
    admin = setup_session.query(User).filter_by(role="ADMIN").first()
    if not admin:
        admin = User(username="admin_actor", password_hash="hash", role="ADMIN", is_active=True, tenant_id="concurrent_tenant_1")
        setup_session.add(admin)

    user = User(username="concurrent_q_user", password_hash="hash", role="readonly", is_active=False, tenant_resolution_status="QUARANTINED", tenant_id=None)
    setup_session.add(user)
    setup_session.commit()

    quarantine = UserTenantQuarantine(user_id=user.id, reason_code="AMBIGUOUS", status="QUARANTINED")
    setup_session.add(quarantine)
    setup_session.commit()
    
    admin_username = admin.username
    admin_id = admin.id
    setup_session.close()

    # Barriers for synchronization
    barrier = threading.Barrier(2)
    results = []

    def resolve_worker(idx, target_tenant):
        session = TestingSessionLocal()
        try:
            barrier.wait()
            try:
                resolve_user(session, "concurrent_q_user", target_tenant, f"REF{idx}", admin_username)
                session.commit()
                results.append((idx, "SUCCESS"))
            except QuarantineAlreadyResolvedError:
                session.rollback()
                results.append((idx, "CONFLICT"))
            except Exception as e:
                session.rollback()
                results.append((idx, f"ERROR: {str(e)}"))
        finally:
            session.close()

    t1 = threading.Thread(target=resolve_worker, args=(1, "concurrent_tenant_1"))
    t2 = threading.Thread(target=resolve_worker, args=(2, "concurrent_tenant_2"))

    t1.start()
    t2.start()

    t1.join(timeout=10)
    t2.join(timeout=10)

    # Check exactly one success and one conflict
    successes = [r for r in results if r[1] == "SUCCESS"]
    conflicts = [r for r in results if r[1] == "CONFLICT"]

    assert len(successes) == 1, f"Exactly one transaction should succeed, got: {results}"
    assert len(conflicts) == 1, f"Exactly one transaction should raise conflict, got: {results}"

    winning_idx = successes[0][0]
    expected_tenant = f"concurrent_tenant_{winning_idx}"
    expected_ref = f"REF{winning_idx}"

    # Verify database state
    verify_session = TestingSessionLocal()
    try:
        final_user = verify_session.query(User).filter_by(username="concurrent_q_user").first()
        final_quarantine = verify_session.query(UserTenantQuarantine).filter_by(user_id=final_user.id).first()
        audit_logs = verify_session.query(AuditLog).filter_by(action="QUARANTINE_RESOLVED", entity_id=str(final_user.id)).all()

        assert final_user.tenant_id == expected_tenant, "User tenant must match the winning transaction"
        assert final_user.tenant_resolution_status == "RESOLVED"
        assert final_quarantine.status == "RESOLVED"
        assert final_quarantine.resolution_reference == expected_ref

        assert len(audit_logs) == 1, "There should be exactly one audit log for quarantine resolution"
        
        # Verify AuditLog constraints and details structure
        log = audit_logs[0]
        assert log.user_id == admin_id, "Audit log must explicitly trace back to the administrative actor"
        
        details_dict = json.loads(log.details)
        assert details_dict["new_status"] == "RESOLVED"
        assert details_dict["resolution_reference"] == expected_ref
        
    finally:
        verify_session.close()
