"""
Prueba Exhaustiva de la Matriz de Rutas, Permisos RBAC Multitenant y SoD (P14-R1-14, P14-R2-16, P14-R2-17).

Cubre exhaustivamente:
1. Rechazo anónimo fail-closed (401 Unauthorized) en todos los métodos protegidos.
2. Jerarquía y escalamiento: ADMIN no puede crear, modificar ni elevar identidades a SUPERADMIN ni ADMIN.
3. Delegación institucional: ADMIN requiere can_manage_users=True para listar, consultar o crear usuarios.
4. Aislamiento estricto multi-tenant (2 instituciones independientes: inst_alpha e inst_beta):
   - Expedientes, documentos, evaluaciones, selección e informes P13.
   - Las referencias directas (IDOR) a recursos de otro tenant devuelven 404 Not Found (sin enumeración).
5. SUPERADMIN sin bypass transversal automático:
   - Requiere contexto institucional explícito y auditado (X-Audit-Tenant-ID); de lo contrario, 404.
6. Separación de funciones (SoD) en Informes P13:
   - El autor del informe no puede aprobar su propio informe.
   - SUPERADMIN no puede eludir la regla de SoD de P13.
7. Restricción mutadora de READONLY:
   - Métodos mutadores administrativos y de reporte prohibidos (403 Forbidden).
   - Acciones de solo lectura permitidas dentro de su propio tenant (200 OK).
8. Revocación de sesión persistida:
   - Un token no expirado cuya sesión fue revocada en PostgreSQL devuelve 401 Unauthorized inmediatamente.
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.domain import User, Tenant, CaseFile, UploadedDocument, UserSession, SystemSettings, AuditDelegationGrant, AuditLog
from app.models.v6.generated_output import GeneratedOutput
from app.models.v6.output_template import OutputTemplate
from app.api.auth import get_password_hash, create_access_token


def make_test_user_and_session(db: Session, username: str, role: str, tenant_id: str) -> str:
    """Crea un usuario de prueba en base de datos junto con su fila de sesión UserSession fail-closed."""
    # Asegurar tenant
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        t = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", can_manage_users=True)
        db.add(t)
        db.flush()

    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(
            username=username,
            password_hash=get_password_hash("SecurePassword123!"),
            role=role,
            tenant_id=tenant_id,
            is_active=True,
            must_change_password=False,
            session_version=1
        )
        db.add(user)
        db.flush()
    else:
        user.role = role
        user.tenant_id = tenant_id
        user.is_active = True
        user.must_change_password = False
        user.session_version = 1
        db.flush()

    session_id = uuid.uuid4().hex
    session_rec = UserSession(
        id=session_id,
        user_id=user.id,
        ip_address="127.0.0.1",
        user_agent="pytest-route-security",
        session_version=user.session_version,
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
    )
    db.add(session_rec)
    db.commit()

    return create_access_token({
        "sub": user.username,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "session_version": user.session_version
    }, session_id=session_id)


# ---------------------------------------------------------------------------
# R1-14: Rechazo Anónimo en Todas las Rutas Protegidas
# ---------------------------------------------------------------------------

def test_r1_14_all_routes_mounted_anonymous_rejection():
    """
    P14-R1-14: Inspecciona todos los métodos HTTP montados en la aplicación
    y comprueba que el acceso anónimo es rechazado con 401 Unauthorized.
    """
    client = TestClient(app)

    PUBLIC_PATHS = {
        "/auth/token",
        "/auth/mfa/verify",
        "/auth/mfa/recovery",
        "/health",
        "/api/v6/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json"
    }

    openapi_paths = app.openapi().get("paths", {})
    endpoints_checked = 0

    for path, methods_dict in openapi_paths.items():
        is_public = any(path == pub or path.startswith(pub + "/") for pub in PUBLIC_PATHS)
        if is_public:
            continue

        test_path = (
            path.replace("{case_id}", "99999")
            .replace("{document_id}", "99999")
            .replace("{id}", "99999")
            .replace("{job_id}", "99999")
            .replace("{section_id}", "99999")
            .replace("{user_id}", "99999")
            .replace("{tenant_id}", "inst_alpha")
            .replace("{target_tenant_id}", "inst_alpha")
            .replace("{report_id}", "99999")
            .replace("{run_id}", "99999")
            .replace("{output_id}", "99999")
            .replace("{supplier_id}", "99999")
            .replace("{req_id}", "99999")
            .replace("{item_id}", "99999")
            .replace("{offer_id}", "99999")
            .replace("{eval_id}", "99999")
            .replace("{file_name}", "sample.pdf")
            .replace("{filename}", "sample.pdf")
        )

        if "{" in test_path:
            continue

        for method in methods_dict.keys():
            method_lower = method.lower()
            req_fn = getattr(client, method_lower, None)
            if not req_fn:
                continue

            if method_lower in ("post", "put", "patch"):
                res = req_fn(test_path, json={})
                if res.status_code == 422:
                    res = req_fn(test_path, data={"case_id": "99999"}, files={"file": ("sample.pdf", b"%PDF-1.5 test")})
            else:
                res = req_fn(test_path)

            assert res.status_code == 401, (
                f"Ruta protegida [{method.upper()}] {test_path} permitio acceso anonimo con status {res.status_code}!"
            )
            endpoints_checked += 1

    assert endpoints_checked >= 40, f"Se esperaba verificar al menos 40 endpoints montados, se comprobaron {endpoints_checked}."


# ---------------------------------------------------------------------------
# R2-16 & R2-17: Matriz de Control de Acceso, Escalación y Delegación
# ---------------------------------------------------------------------------

def test_r2_16_r2_17_admin_privilege_escalation_and_delegation(db_session: Session):
    """
    P14-R2-16 / P14-R2-17:
    - ADMIN no puede crear ni elevar identidades a SUPERADMIN ni ADMIN.
    - ADMIN no puede administrar usuarios si carece de can_manage_users=True.
    - SUPERADMIN gestiona delegación y controla el tenant institucional de destino.
    """
    client = TestClient(app)

    # Tenant Alpha con can_manage_users=False
    tenant_nodeleg = db_session.query(Tenant).filter(Tenant.id == "tenant_no_deleg").first()
    if not tenant_nodeleg:
        tenant_nodeleg = Tenant(id="tenant_no_deleg", name="Tenant Sin Delegacion", can_manage_users=False)
        db_session.add(tenant_nodeleg)
    else:
        tenant_nodeleg.can_manage_users = False
    db_session.commit()

    # Tenant Alpha con can_manage_users=True
    tenant_deleg = db_session.query(Tenant).filter(Tenant.id == "tenant_with_deleg").first()
    if not tenant_deleg:
        tenant_deleg = Tenant(id="tenant_with_deleg", name="Tenant Con Delegacion", can_manage_users=True)
        db_session.add(tenant_deleg)
    else:
        tenant_deleg.can_manage_users = True
    db_session.commit()

    token_admin_nodeleg = make_test_user_and_session(db_session, "admin_nodeleg_usr", "ADMIN", "tenant_no_deleg")
    token_admin_deleg = make_test_user_and_session(db_session, "admin_deleg_usr", "ADMIN", "tenant_with_deleg")
    token_sa = make_test_user_and_session(db_session, "sa_rbac_user", "SUPERADMIN", "system")

    # 1. ADMIN sin delegación no puede crear usuarios -> 403 Forbidden
    res = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {token_admin_nodeleg}"},
        json={"username": "new_op_nodeleg", "password": "Password123!", "role": "OPERATOR"}
    )
    assert res.status_code == 403
    assert "delegada" in res.text.lower()

    # 2. ADMIN sin delegación no puede listar usuarios -> 403 Forbidden
    res = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {token_admin_nodeleg}"}
    )
    assert res.status_code == 403

    # 3. ADMIN con delegación intentando crear SUPERADMIN -> 403 Forbidden (Escalamiento bloqueado)
    res = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {token_admin_deleg}"},
        json={"username": "malicious_sa", "password": "Password123!", "role": "SUPERADMIN"}
    )
    assert res.status_code in (403, 422)

    # 4. ADMIN con delegación intentando crear otro ADMIN -> 403 Forbidden
    res = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {token_admin_deleg}"},
        json={"username": "malicious_admin", "password": "Password123!", "role": "ADMIN"}
    )
    assert res.status_code in (403, 422)

    # 5. ADMIN con delegación intentando crear usuario en OTRO tenant -> 403 Forbidden
    res = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {token_admin_deleg}"},
        json={"username": "cross_tenant_usr", "password": "Password123!", "role": "OPERATOR", "tenant_id": "other_tenant"}
    )
    assert res.status_code == 403

    # 6. ADMIN con delegación crea OPERATOR legítimo en su propio tenant -> 201 Created
    unique_user = f"legit_op_{uuid.uuid4().hex[:6]}"
    res = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {token_admin_deleg}"},
        json={"username": unique_user, "password": "Password123!", "role": "OPERATOR"}
    )
    assert res.status_code == 201
    assert res.json()["username"] == unique_user
    assert res.json()["tenant_id"] == "tenant_with_deleg"

    # 7. SUPERADMIN activa delegación en tenant_no_deleg -> 200 OK
    res = client.post(
        "/admin/tenants/tenant_no_deleg/delegation?enabled=true",
        headers={"Authorization": f"Bearer {token_sa}"}
    )
    assert res.status_code == 200
    assert res.json()["can_manage_users"] is True

    # 8. Ahora el ADMIN de tenant_no_deleg sí puede listar usuarios -> 200 OK
    res = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {token_admin_nodeleg}"}
    )
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# R2-16 & R2-17: Aislamiento Multitenant Estricto entre 2 Instituciones
# ---------------------------------------------------------------------------

def test_r2_16_r2_17_cross_tenant_isolation_and_idor_protection(db_session: Session):
    """
    P14-R2-16 / P14-R2-17: Aislamiento riguroso entre 2 tenants (inst_alpha e inst_beta).
    - Ningún usuario institucional accede a expedientes o documentos de otro tenant.
    - Las peticiones a recursos ajenos devuelven 404 Not Found para prevenir enumeración IDOR.
    """
    client = TestClient(app)

    # Crear 2 tenants independientes
    t_a = db_session.query(Tenant).filter(Tenant.id == "inst_alpha").first()
    if not t_a:
        t_a = Tenant(id="inst_alpha", name="Hospital Regional Alpha", can_manage_users=True)
        db_session.add(t_a)
    t_b = db_session.query(Tenant).filter(Tenant.id == "inst_beta").first()
    if not t_b:
        t_b = Tenant(id="inst_beta", name="Universidad Nacional Beta", can_manage_users=True)
        db_session.add(t_b)
    db_session.commit()

    # Usuarios para cada rol en Tenant Alpha
    token_admin_a = make_test_user_and_session(db_session, "admin_inst_alpha", "ADMIN", "inst_alpha")
    token_sup_a = make_test_user_and_session(db_session, "sup_inst_alpha", "SUPERVISOR", "inst_alpha")
    token_op_a = make_test_user_and_session(db_session, "op_inst_alpha", "OPERATOR", "inst_alpha")
    token_ro_a = make_test_user_and_session(db_session, "ro_inst_alpha", "READONLY", "inst_alpha")

    # Usuarios para cada rol en Tenant Beta
    token_admin_b = make_test_user_and_session(db_session, "admin_inst_beta", "ADMIN", "inst_beta")
    token_sup_b = make_test_user_and_session(db_session, "sup_inst_beta", "SUPERVISOR", "inst_beta")
    token_op_b = make_test_user_and_session(db_session, "op_inst_beta", "OPERATOR", "inst_beta")

    # Crear expediente en Tenant Alpha
    user_op_a_rec = db_session.query(User).filter(User.username == "op_inst_alpha").first()
    case_a = CaseFile(
        title="Expediente Medico Alpha",
        contract_type="BIENES",
        status="CREATED",
        tenant_id="inst_alpha",
        created_by=user_op_a_rec.id,
        assigned_to_user_id=user_op_a_rec.id
    )
    db_session.add(case_a)
    db_session.flush()

    # Documento en Tenant Alpha
    doc_a = UploadedDocument(
        case_id=case_a.id,
        document_type="requirement",
        original_filename="especificaciones_alpha.pdf",
        stored_path="uploads/alpha/especificaciones.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc_a)

    # Crear expediente en Tenant Beta
    user_op_b_rec = db_session.query(User).filter(User.username == "op_inst_beta").first()
    case_b = CaseFile(
        title="Expediente Cientifico Beta",
        contract_type="SERVICIOS",
        status="CREATED",
        tenant_id="inst_beta",
        created_by=user_op_b_rec.id,
        assigned_to_user_id=user_op_b_rec.id
    )
    db_session.add(case_b)
    db_session.flush()

    doc_b = UploadedDocument(
        case_id=case_b.id,
        document_type="requirement",
        original_filename="terminos_referencia_beta.pdf",
        stored_path="uploads/beta/tdr.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc_b)
    db_session.commit()

    # 1. Acceso legítimo de Tenant Alpha a su propio expediente -> 200 OK
    res = client.get(
        f"/api/v6/cases/{case_a.id}/requirements",
        headers={"Authorization": f"Bearer {token_op_a}"}
    )
    assert res.status_code == 200

    # 2. Intento de acceso de ADMIN de Tenant Alpha al expediente de Tenant Beta -> 404 Not Found (IDOR protegido)
    res = client.get(
        f"/api/v6/cases/{case_b.id}/requirements",
        headers={"Authorization": f"Bearer {token_admin_a}"}
    )
    assert res.status_code == 404, f"Se esperaba 404 para impedir IDOR, pero retorno {res.status_code}"

    # 3. Intento de SUPERVISOR de Tenant Alpha a expediente de Tenant Beta -> 404 Not Found
    res = client.get(
        f"/api/v6/cases/{case_b.id}/requirements",
        headers={"Authorization": f"Bearer {token_sup_a}"}
    )
    assert res.status_code == 404

    # 4. Intento de OPERATOR de Tenant Alpha a expediente de Tenant Beta -> 404 Not Found
    res = client.get(
        f"/api/v6/cases/{case_b.id}/requirements",
        headers={"Authorization": f"Bearer {token_op_a}"}
    )
    assert res.status_code == 404

    # 5. Intento de READONLY de Tenant Alpha a expediente de Tenant Beta -> 404 Not Found
    res = client.get(
        f"/api/v6/cases/{case_b.id}/requirements",
        headers={"Authorization": f"Bearer {token_ro_a}"}
    )
    assert res.status_code == 404

    # 6. Intento de OPERATOR de Tenant Beta al expediente de Tenant Alpha -> 404 Not Found
    res = client.get(
        f"/api/v6/cases/{case_a.id}/requirements",
        headers={"Authorization": f"Bearer {token_op_b}"}
    )
    assert res.status_code == 404

    # 7. Intento de acceso cruzado a informes P13 de otro tenant -> 404 Not Found
    res = client.get(
        f"/api/v6/cases/{case_b.id}/reports/p13",
        headers={"Authorization": f"Bearer {token_op_a}"}
    )
    assert res.status_code == 404

    # 8. Intento de acceso cruzado a selección de otro tenant -> 404 Not Found
    res = client.get(
        f"/api/v6/cases/{case_b.id}/selection",
        headers={"Authorization": f"Bearer {token_op_a}"}
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# R2-16: SUPERADMIN sin bypass transversal automático
# ---------------------------------------------------------------------------

def test_r2_16_superadmin_no_transversal_operative_access(db_session: Session):
    """
    P14-R2-16 & R3-01: SUPERADMIN no obtiene acceso operativo transversal automático ni por simple
    cabecera X-Audit-Tenant-ID arbitraria. Requiere estrictamente una concesión formal auditada
    (AuditDelegationGrant) en base de datos, limita el acceso a métodos de solo lectura (GET) y
    registra cada acceso en AuditLog (Anti-IDOR).
    """
    client = TestClient(app)

    token_sa = make_test_user_and_session(db_session, "sa_audit_usr", "SUPERADMIN", "system")
    token_admin_a = make_test_user_and_session(db_session, "admin_audit_usr", "ADMIN", "inst_alpha")

    user_sa = db_session.query(User).filter(User.username == "sa_audit_usr").first()
    user_alpha = db_session.query(User).filter(User.username == "admin_audit_usr").first()

    # Expediente institucional
    case_audit = CaseFile(
        title="Expediente Confidencial Auditoria",
        contract_type="BIENES",
        status="CREATED",
        tenant_id="inst_alpha",
        created_by=user_alpha.id
    )
    db_session.add(case_audit)
    db_session.commit()

    # 1. SUPERADMIN sin header de contexto institucional auditado -> 404 Not Found (Anti-IDOR)
    res = client.get(
        f"/api/v6/cases/{case_audit.id}/requirements",
        headers={"Authorization": f"Bearer {token_sa}"}
    )
    assert res.status_code == 404

    # 2. SUPERADMIN con header inventado sin concesion persistida -> 404 Not Found (R3-01)
    res_fake = client.get(
        f"/api/v6/cases/{case_audit.id}/requirements",
        headers={
            "Authorization": f"Bearer {token_sa}",
            "X-Audit-Tenant-ID": "inst_alpha"
        }
    )
    assert res_fake.status_code == 404, "Cabecera sin concesion no debe otorgar acceso (R3-01)"

    # 3. SUPERADMIN con concesion expirada -> 404 Not Found (R3-01)
    expired_grant = AuditDelegationGrant(
        id=uuid.uuid4().hex,
        target_tenant_id="inst_alpha",
        granted_to_user_id=user_sa.id,
        granted_by_user_id=user_alpha.id,
        scope="READ_ONLY_AUDIT",
        reason="Auditoria historica expirada",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        is_revoked=False
    )
    db_session.add(expired_grant)
    db_session.commit()

    res_exp = client.get(
        f"/api/v6/cases/{case_audit.id}/requirements",
        headers={
            "Authorization": f"Bearer {token_sa}",
            "X-Audit-Tenant-ID": "inst_alpha"
        }
    )
    assert res_exp.status_code == 404, "Concesion expirada debe retornar 404"

    # 4. SUPERADMIN con concesion revocada -> 404 Not Found (R3-01)
    revoked_grant = AuditDelegationGrant(
        id=uuid.uuid4().hex,
        target_tenant_id="inst_alpha",
        granted_to_user_id=user_sa.id,
        granted_by_user_id=user_alpha.id,
        scope="READ_ONLY_AUDIT",
        reason="Auditoria revocada",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        is_revoked=True
    )
    db_session.add(revoked_grant)
    db_session.commit()

    res_rev = client.get(
        f"/api/v6/cases/{case_audit.id}/requirements",
        headers={
            "Authorization": f"Bearer {token_sa}",
            "X-Audit-Tenant-ID": "inst_alpha"
        }
    )
    assert res_rev.status_code == 404, "Concesion revocada debe retornar 404"

    # 5. SUPERADMIN con concesion activa valida -> GET 200 OK y registro en AuditLog (R3-01)
    valid_grant = AuditDelegationGrant(
        id=uuid.uuid4().hex,
        target_tenant_id="inst_alpha",
        granted_to_user_id=user_sa.id,
        granted_by_user_id=user_alpha.id,
        scope="READ_ONLY_AUDIT",
        reason="Auditoria formal autorizada CGR",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        is_revoked=False
    )
    db_session.add(valid_grant)
    db_session.commit()

    res_valid = client.get(
        f"/api/v6/cases/{case_audit.id}/requirements",
        headers={
            "Authorization": f"Bearer {token_sa}",
            "X-Audit-Tenant-ID": "inst_alpha"
        }
    )
    assert res_valid.status_code == 200

    # Verificar que el acceso quedo registrado en AuditLog
    audit_entry = db_session.query(AuditLog).filter(
        AuditLog.action == "CROSS_TENANT_AUDIT_INSPECTION",
        AuditLog.user_id == user_sa.id
    ).first()
    assert audit_entry is not None
    assert audit_entry.tenant_id == "inst_alpha"

    # 6. SUPERADMIN con concesion activa intentando operacion mutadora (POST) -> 403 Forbidden
    res_mutate = client.post(
        f"/api/v6/cases/{case_audit.id}/requirements",
        headers={
            "Authorization": f"Bearer {token_sa}",
            "X-Audit-Tenant-ID": "inst_alpha"
        },
        json={"title": "Requisito mutado ilegal"}
    )
    assert res_mutate.status_code in (403, 405), "Acceso delegado no debe permitir mutaciones operativas"


# ---------------------------------------------------------------------------
# R4-03 & R4-04: Concesiones de Auditoría con Scope Estricto y Fail-Closed
# ---------------------------------------------------------------------------

def test_r4_03_cross_tenant_audit_invalid_scope_and_self_grant_rejected_404(db_session: Session):
    """
    P14-R4-03: Consulta de concesión exige scope == 'READ_ONLY_AUDIT' y valida procedencia.
    - Concesión con scope distinto (ej. 'ADMIN_BILLING') -> 404 Not Found.
    - Concesión auto-otorgada (granted_by == granted_to) -> 404 Not Found.
    - Concesión otorgada por usuario ajeno al tenant objetivo -> 404 Not Found.
    """
    client = TestClient(app)

    token_sa = make_test_user_and_session(db_session, "sa_r4_audit_usr", "SUPERADMIN", "system")
    user_sa = db_session.query(User).filter(User.username == "sa_r4_audit_usr").first()

    token_alpha = make_test_user_and_session(db_session, "admin_r4_alpha", "ADMIN", "inst_alpha")
    user_alpha = db_session.query(User).filter(User.username == "admin_r4_alpha").first()

    # Usuario de un tercer tenant (inst_gamma)
    make_test_user_and_session(db_session, "admin_r4_gamma", "ADMIN", "inst_gamma")
    user_gamma = db_session.query(User).filter(User.username == "admin_r4_gamma").first()

    case_r4 = CaseFile(
        title="Expediente Auditoria Scope Test",
        contract_type="BIENES",
        status="CREATED",
        tenant_id="inst_alpha",
        created_by=user_alpha.id
    )
    db_session.add(case_r4)
    db_session.commit()

    # 1. Concesión con scope no autorizado ('ADMIN_BILLING') -> 404
    bad_scope_grant = AuditDelegationGrant(
        id=uuid.uuid4().hex,
        target_tenant_id="inst_alpha",
        granted_to_user_id=user_sa.id,
        granted_by_user_id=user_alpha.id,
        scope="ADMIN_BILLING",
        reason="Intento de scope no de solo lectura",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        is_revoked=False
    )
    db_session.add(bad_scope_grant)
    db_session.commit()

    res1 = client.get(
        f"/api/v6/cases/{case_r4.id}/requirements",
        headers={"Authorization": f"Bearer {token_sa}", "X-Audit-Tenant-ID": "inst_alpha"}
    )
    assert res1.status_code == 404, "Grant con scope distinto de READ_ONLY_AUDIT debe ser rechazado con 404"

    # Limpiar grant
    db_session.delete(bad_scope_grant)
    db_session.commit()

    # 2. Concesión auto-otorgada (granted_by == current_user) -> 404
    self_grant = AuditDelegationGrant(
        id=uuid.uuid4().hex,
        target_tenant_id="inst_alpha",
        granted_to_user_id=user_sa.id,
        granted_by_user_id=user_sa.id,
        scope="READ_ONLY_AUDIT",
        reason="Auto-concesion ilegal",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        is_revoked=False
    )
    db_session.add(self_grant)
    db_session.commit()

    res2 = client.get(
        f"/api/v6/cases/{case_r4.id}/requirements",
        headers={"Authorization": f"Bearer {token_sa}", "X-Audit-Tenant-ID": "inst_alpha"}
    )
    assert res2.status_code == 404, "Grant auto-otorgado debe ser rechazado con 404"

    # Limpiar grant
    db_session.delete(self_grant)
    db_session.commit()

    # 3. Concesión otorgada por usuario ilegítimo (de otro tenant) -> 404
    illegitimate_grant = AuditDelegationGrant(
        id=uuid.uuid4().hex,
        target_tenant_id="inst_alpha",
        granted_to_user_id=user_sa.id,
        granted_by_user_id=user_gamma.id,
        scope="READ_ONLY_AUDIT",
        reason="Grantor de tenant ajeno",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        is_revoked=False
    )
    db_session.add(illegitimate_grant)
    db_session.commit()

    res3 = client.get(
        f"/api/v6/cases/{case_r4.id}/requirements",
        headers={"Authorization": f"Bearer {token_sa}", "X-Audit-Tenant-ID": "inst_alpha"}
    )
    assert res3.status_code == 404, "Grant otorgado por usuario sin legitimidad sobre el tenant debe ser rechazado con 404"


def test_r4_04_cross_tenant_audit_persistence_failure_fail_closed_503(db_session: Session):
    """
    P14-R4-04: Exigir registro durable antes de devolver datos.
    Ante fallo de la transacción de auditoría (AuditLog), responder 503 sin exponer
    expediente ni datos sensibles (fail-closed absoluto).
    """
    from unittest import mock
    client = TestClient(app)

    token_sa = make_test_user_and_session(db_session, "sa_r4_04_usr", "SUPERADMIN", "system")
    user_sa = db_session.query(User).filter(User.username == "sa_r4_04_usr").first()

    token_alpha = make_test_user_and_session(db_session, "admin_r4_04_alpha", "ADMIN", "inst_alpha")
    user_alpha = db_session.query(User).filter(User.username == "admin_r4_04_alpha").first()

    case_r4_04 = CaseFile(
        title="Expediente Confidencial Fail-Closed Test",
        contract_type="BIENES",
        status="CREATED",
        tenant_id="inst_alpha",
        created_by=user_alpha.id
    )
    db_session.add(case_r4_04)
    db_session.commit()

    # Crear concesión válida
    valid_grant = AuditDelegationGrant(
        id=uuid.uuid4().hex,
        target_tenant_id="inst_alpha",
        granted_to_user_id=user_sa.id,
        granted_by_user_id=user_alpha.id,
        scope="READ_ONLY_AUDIT",
        reason="Auditoria autorizada para test de fail-closed",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        is_revoked=False
    )
    db_session.add(valid_grant)
    db_session.commit()

    # Simular fallo en la sesión aislada de auditoría (SessionLocal)
    with mock.patch("app.api.auth.SessionLocal") as mock_session_factory:
        mock_audit_session = mock.MagicMock()
        mock_audit_session.commit.side_effect = RuntimeError("Simulated Audit Storage Failure (Disk Full / Network Partition)")
        mock_session_factory.return_value = mock_audit_session

        res = client.get(
            f"/api/v6/cases/{case_r4_04.id}/requirements",
            headers={"Authorization": f"Bearer {token_sa}", "X-Audit-Tenant-ID": "inst_alpha"}
        )

        # Debe responder 503 Service Unavailable y NUNCA devolver el expediente
        assert res.status_code == 503, "Fallo en persistencia de auditoria debe responder 503 Service Unavailable"
        assert "fail-closed" in res.text.lower() or "subsistema de auditoria" in res.text.lower()
        # Verificar que el contenido del expediente no fue filtrado
        assert "Expediente Confidencial" not in res.text


# ---------------------------------------------------------------------------
# R3-12: Separación de Funciones (SoD) Causal vs Rechazo RBAC en Informes P13
# ---------------------------------------------------------------------------

def test_r3_12_p13_sod_causality_author_cannot_self_approve(db_session: Session):
    """
    P14-R3-12: Acredita la causalidad estricta de SoD:
    - Se prueba con usuarios con rol plenamente habilitado para aprobacion (SUPERVISOR).
    - Cuando el supervisor ES el autor del informe, el intento de aprobacion es denegado
      especificamente por SoD con HTTP 403, el informe permanece UNDER_REVIEW,
      no se transiciona de estado ni se designa aprobador, y se registra SOD_VIOLATION_ATTEMPT.
    - Contraejemplo: Un segundo supervisor INDEPENDIENTE (no autor) aprueba exitosamente
      el mismo informe con HTTP 200, transicionando el estado a APPROVED.
    """
    import hashlib
    from app.services.v6.reporting.canonical_serializer import CanonicalSerializer

    client = TestClient(app)

    token_author = make_test_user_and_session(db_session, "sup_author_sod", "SUPERVISOR", "inst_alpha")
    token_independent = make_test_user_and_session(db_session, "sup_indep_sod", "SUPERVISOR", "inst_alpha")

    user_author = db_session.query(User).filter(User.username == "sup_author_sod").first()
    user_indep = db_session.query(User).filter(User.username == "sup_indep_sod").first()

    case_p13 = CaseFile(
        title="Expediente Causal SoD P13 Test",
        contract_type="BIENES",
        status="IN_EVALUATION",
        tenant_id="inst_alpha",
        created_by=user_author.id,
        assigned_to_user_id=user_author.id
    )
    db_session.add(case_p13)
    db_session.flush()

    output_template = db_session.query(OutputTemplate).first()
    if not output_template:
        output_template = OutputTemplate(
            type="INFORME_TECNICO_EVALUACION",
            version="1.0",
            entity_name="P13_TEMPLATE",
            content="<html><body>{{content}}</body></html>",
            checksum="0" * 64,
            status="ACTIVE"
        )
        db_session.add(output_template)
        db_session.flush()

    template_checksum = hashlib.sha256(output_template.content.encode('utf-8')).hexdigest()
    output_template.checksum = template_checksum
    db_session.flush()

    snapshot = {"case_id": case_p13.id}
    snap_bytes = CanonicalSerializer.serialize_to_bytes(snapshot)
    snap_hash = CanonicalSerializer.calculate_hash(snap_bytes)

    # Informe generado por sup_author_sod
    report_output = GeneratedOutput(
        case_id=case_p13.id,
        template_id=output_template.id,
        content_rendered="<html><body>Informe Tecnico Evaluacion SoD</body></html>",
        generation_hash="b" * 64,
        generated_by=user_author.id,
        template_version="1.0",
        accuracy_gate_result="PASS",
        source_snapshot=snapshot,
        snapshot_hash=snap_hash,
        status="UNDER_REVIEW",
        report_kind="INFORME_TECNICO_EVALUACION"
    )
    db_session.add(report_output)
    db_session.commit()

    # 1. El propio autor (con rol SUPERVISOR valido) intenta auto-aprobar -> 403 SoD Causal (R3-12)
    res_author = client.post(
        f"/api/v6/cases/{case_p13.id}/reports/p13/{report_output.id}/approve",
        headers={"Authorization": f"Bearer {token_author}"},
        json={"approval_notes": "Intento de auto-aprobacion por autor"}
    )
    assert res_author.status_code == 403, f"Auto-aprobacion debio ser rechazada por SoD: {res_author.status_code} {res_author.text}"
    detail = res_author.text.lower()
    assert "separación de funciones" in detail or "separacion de funciones" in detail or "sod" in detail or "autor" in detail

    # Comprobar que en la base de datos el informe NO transiciono y permanece UNDER_REVIEW
    db_session.refresh(report_output)
    assert report_output.status == "UNDER_REVIEW", "El informe no debio transicionar de estado"
    assert report_output.approved_by is None, "No debe registrarse aprobador tras intento fallido SoD"
    assert report_output.approved_at is None

    # Comprobar evento de auditoria de violacion SoD en AuditLog
    sod_audit = db_session.query(AuditLog).filter(
        AuditLog.action == "SOD_VIOLATION_ATTEMPT",
        AuditLog.user_id == user_author.id
    ).first()
    assert sod_audit is not None, "Debe registrarse evento SOD_VIOLATION_ATTEMPT en AuditLog"

    # 2. Contraejemplo: Supervisor independiente (no autor) aprueba exitosamente -> 200 OK (R3-12)
    res_indep = client.post(
        f"/api/v6/cases/{case_p13.id}/reports/p13/{report_output.id}/approve",
        headers={"Authorization": f"Bearer {token_independent}"},
        json={"approval_notes": "Aprobacion valida por supervisor independiente"}
    )
    assert res_indep.status_code == 200, f"Supervisor independiente debio aprobar exitosamente: {res_indep.status_code} {res_indep.text}"

    # Comprobar que transiciono efectivamente a APPROVED con el aprobador correcto
    db_session.refresh(report_output)
    assert report_output.status == "APPROVED"
    assert report_output.approved_by == user_indep.id
    assert report_output.approved_at is not None


def test_r3_12_p13_rbac_unauthorized_roles_cannot_approve(db_session: Session):
    """
    P14-R3-12: Prueba de rechazo por rol (RBAC) separada de la prueba de SoD:
    - OPERATOR y READONLY son denegados por rol insuficiente, no por regla de autor==aprobador.
    - SUPERADMIN sin tenant/delegacion no tiene acceso transversal operativo.
    """
    client = TestClient(app)

    token_admin = make_test_user_and_session(db_session, "admin_case_owner", "ADMIN", "inst_alpha")
    token_op = make_test_user_and_session(db_session, "op_role_usr", "OPERATOR", "inst_alpha")
    token_ro = make_test_user_and_session(db_session, "ro_role_usr", "READONLY", "inst_alpha")
    token_sa = make_test_user_and_session(db_session, "sa_role_usr", "SUPERADMIN", "system")

    user_admin = db_session.query(User).filter(User.username == "admin_case_owner").first()
    user_op = db_session.query(User).filter(User.username == "op_role_usr").first()
    user_ro = db_session.query(User).filter(User.username == "ro_role_usr").first()

    case_p13 = CaseFile(
        title="Expediente RBAC P13 Test",
        contract_type="BIENES",
        status="IN_EVALUATION",
        tenant_id="inst_alpha",
        created_by=user_admin.id,
        assigned_to_user_id=user_op.id
    )
    db_session.add(case_p13)
    db_session.flush()

    output_template = db_session.query(OutputTemplate).first()
    report_output = GeneratedOutput(
        case_id=case_p13.id,
        template_id=output_template.id,
        content_rendered="<html><body>Informe RBAC</body></html>",
        generation_hash="c" * 64,
        generated_by=user_admin.id,
        template_version="1.0",
        accuracy_gate_result="PASS",
        source_snapshot={"case_id": case_p13.id},
        status="UNDER_REVIEW",
        report_kind="INFORME_TECNICO_EVALUACION"
    )
    db_session.add(report_output)
    db_session.commit()

    # 1. OPERATOR intenta aprobar -> 403 Forbidden por RBAC (Rol insuficiente: requiere ADMIN o SUPERVISOR)
    res_op = client.post(
        f"/api/v6/cases/{case_p13.id}/reports/p13/{report_output.id}/approve",
        headers={"Authorization": f"Bearer {token_op}"},
        json={"approval_notes": "OPERATOR attempting approval"}
    )
    assert res_op.status_code == 403
    assert "not enough permissions" in res_op.text.lower() or "rol insuficiente" in res_op.text.lower() or "insuficiente" in res_op.text.lower()

    # 2. READONLY intenta aprobar -> 403 Forbidden por RBAC
    case_p13.assigned_to_user_id = user_ro.id
    db_session.commit()
    res_ro = client.post(
        f"/api/v6/cases/{case_p13.id}/reports/p13/{report_output.id}/approve",
        headers={"Authorization": f"Bearer {token_ro}"},
        json={"approval_notes": "READONLY attempting approval"}
    )
    assert res_ro.status_code == 403
    assert "not enough permissions" in res_ro.text.lower() or "rol insuficiente" in res_ro.text.lower() or "insuficiente" in res_ro.text.lower()

    # 3. SUPERADMIN intenta aprobar expediente institucional sin contexto formal -> 404 Not Found
    res_sa = client.post(
        f"/api/v6/cases/{case_p13.id}/reports/p13/{report_output.id}/approve",
        headers={"Authorization": f"Bearer {token_sa}"},
        json={"approval_notes": "SUPERADMIN attempting approval"}
    )
    assert res_sa.status_code == 404


# ---------------------------------------------------------------------------
# R2-17: READONLY Denegación de Mutaciones y Aprobación de Lectura
# ---------------------------------------------------------------------------

def test_r2_17_readonly_mutations_denied(db_session: Session):
    """
    P14-R2-17: El rol READONLY tiene prohibido cualquier método mutador (POST, PUT, PATCH, DELETE),
    pero puede consultar información de su tenant.
    """
    client = TestClient(app)

    token_ro = make_test_user_and_session(db_session, "ro_strict_usr", "READONLY", "inst_alpha")
    user_ro = db_session.query(User).filter(User.username == "ro_strict_usr").first()

    case_ro = CaseFile(
        title="Expediente de Solo Lectura",
        contract_type="BIENES",
        status="CREATED",
        tenant_id="inst_alpha",
        created_by=user_ro.id,
        assigned_to_user_id=user_ro.id
    )
    db_session.add(case_ro)
    db_session.commit()

    # 1. Consulta permitida (GET) -> 200 OK
    res = client.get(
        f"/api/v6/cases/{case_ro.id}/requirements",
        headers={"Authorization": f"Bearer {token_ro}"}
    )
    assert res.status_code == 200

    # 2. Intento de crear usuario administrativo (POST) -> 403 Forbidden
    res = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {token_ro}"},
        json={"username": "ro_forbidden_create", "password": "Password123!", "role": "OPERATOR"}
    )
    assert res.status_code == 403

    # 3. Intento de modificar usuario administrativo (PATCH) -> 403 Forbidden
    res = client.patch(
        f"/admin/users/{user_ro.id}",
        headers={"Authorization": f"Bearer {token_ro}"},
        json={"is_active": False}
    )
    assert res.status_code == 403

    # 4. Intento de generar reporte P13 (POST) -> 403 Forbidden
    res = client.post(
        f"/api/v6/cases/{case_ro.id}/reports/p13/generate",
        headers={"Authorization": f"Bearer {token_ro}"},
        json={}
    )
    assert res.status_code == 403

    # 5. Intento de aprobar reporte P13 (POST) -> 403 Forbidden
    res = client.post(
        f"/api/v6/cases/{case_ro.id}/reports/p13/1/approve",
        headers={"Authorization": f"Bearer {token_ro}"},
        json={"approval_notes": "READONLY attempting approval"}
    )
    assert res.status_code == 403

    # 6. Intento de rechazar reporte P13 (POST) -> 403 Forbidden
    res = client.post(
        f"/api/v6/cases/{case_ro.id}/reports/p13/1/reject",
        headers={"Authorization": f"Bearer {token_ro}"},
        json={"rejection_reason": "READONLY attempting rejection"}
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# R2-17: Rechazo Inmediato de Sesiones Revocadas (401 Fail-Closed)
# ---------------------------------------------------------------------------

def test_r2_17_revoked_session_rejected_even_if_jwt_valid(db_session: Session):
    """
    P14-R2-17: Una sesión marcada is_revoked=True o con session_version invalidada
    es rechazada inmediatamente con 401 Unauthorized ante cualquier petición protegida.
    """
    client = TestClient(app)

    token = make_test_user_and_session(db_session, "revocation_target_usr", "OPERATOR", "inst_alpha")

    # Verificar que el token funciona inicialmente -> 200 OK
    res = client.get(
        "/api/v6/health",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200

    # Revocar la sesión en PostgreSQL
    user_rec = db_session.query(User).filter(User.username == "revocation_target_usr").first()
    db_session.query(UserSession).filter(UserSession.user_id == user_rec.id).update({"is_revoked": True})
    db_session.commit()

    # Reutilizar el JWT no expirado contra endpoint protegido -> 401 Unauthorized
    res = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 401
    assert "revocada" in res.text.lower() or "revoked" in res.text.lower() or "expired" in res.text.lower()
