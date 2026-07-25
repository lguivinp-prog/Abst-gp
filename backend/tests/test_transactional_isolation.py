import pytest
from sqlalchemy import event
import sqlalchemy
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.domain import CaseFile, AuditLog, User
from app.core.database import get_db, SessionLocal

def test_assign_case_transactional_isolation(db_session, setup_mega_tenant):
    """
    Demuestra la atomicidad de assign_case usando el endpoint real.
    Añade un listener after_flush en la misma Session, verifica
    los DMLs antes del flush, comprueba identidades tras el flush
    y fuerza SQLAlchemyError. Comprueba que todo se revierte en la DB.
    """
    import uuid
    suffix = uuid.uuid4().hex[:6]
    target_user = User(tenant_id="mega_tenant", username=f"target_{suffix}", password_hash="hash", role="OPERATOR", is_active=True, must_change_password=False)
    admin_user = db_session.query(User).filter_by(role="ADMIN", tenant_id="mega_tenant").first()
    db_session.add(target_user)
    db_session.commit()

    case = CaseFile(title="Test Case", contract_type="IT", status="CREATED", created_by=admin_user.id, tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    case_id = case.id
    target_user_id = target_user.id
    admin_id = admin_user.id
    
    exception_triggered = False

    def after_flush_listener(session, flush_context):
        nonlocal exception_triggered
        case_modified = False
        audit_created = False
        
        for obj in session:
            if isinstance(obj, CaseFile) and obj.id == case_id:
                case_modified = True
            elif isinstance(obj, AuditLog) and obj.entity_type == "CaseFile" and obj.entity_id == str(case_id):
                audit_created = True
                assert obj.id is not None # Identity asignada tras el flush
                
        if case_modified and audit_created:
            exception_triggered = True
            raise sqlalchemy.exc.SQLAlchemyError("Simulated DB Failure after flush")

    # 2. Dependency Overrides
    def override_get_db():
        # Usamos la MISMA db_session que ya tenemos, pero le pegamos el listener.
        # En FastAPI, get_db suele hacer un yield db. Aquí damos la nuestra.
        event.listen(db_session, "after_flush", after_flush_listener)
        try:
            yield db_session
        finally:
            event.remove(db_session, "after_flush", after_flush_listener)

    def override_get_current_user():
        return admin_user

    from app.api.auth import get_current_active_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_active_user] = override_get_current_user

    client = TestClient(app)

    try:
        print(f"DEBUG: admin_user={admin_user.id}, tenant={admin_user.tenant_id}, role={admin_user.role}")
        print(f"DEBUG: case_id={case_id}")
        for c in db_session.query(CaseFile).all():
            print(f"DEBUG DB CASE: {c.id}, {c.tenant_id}")
        
        # 3. Llamada al endpoint real
        response = client.post(
            f"/cases/{case_id}/assign",
            json={"assigned_to_user_id": target_user_id}
        )
        
        assert response.status_code == 500, f"Expected 500 but got {response.status_code}. Response: {response.json()}"
        assert exception_triggered is True
        
        # La respuesta HTTP 500 debe estar sanitizada
        assert "Internal Server Error" in response.text or "Transaction failed" in response.text
        assert "Simulated DB Failure after flush" not in response.text # No detalles SQL
        
    finally:
        app.dependency_overrides.clear()
        
    # 5. Verificación en una nueva sesión PostgreSQL
    new_session = SessionLocal()
    try:
        reloaded_case = new_session.query(CaseFile).filter_by(id=case_id).first()
        assert reloaded_case.assigned_to_user_id is None, "El CaseFile no debe haberse modificado (rollback)"
        
        audit_logs = new_session.query(AuditLog).filter_by(entity_type="CaseFile", entity_id=str(case_id)).all()
        assert len(audit_logs) == 0, "No debe existir ningún AuditLog (rollback)"
    finally:
        new_session.close()

