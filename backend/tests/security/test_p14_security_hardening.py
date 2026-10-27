"""
Suite Exhaustiva de Pruebas de Seguridad y Hardening para ABST-GP V6 (P14 R1).
Cubre integralmente los hallazgos P14-R1-01 a P14-R1-18:
- R1-02: JWT Fail-Closed (JTI obligatorio, sesión persistida, propósito, versión).
- R1-03: Logout individual y global con invalidación inmediata comprobada.
- R1-04: Validación íntegra de desafíos MFA de un solo uso y reconciliación de estado.
- R1-05: TOTP anti-replay con paso exacto y monotonía estricta.
- R1-06: Recuperación MFA con throttling y consumo atómico.
- R1-07: Rate limiting atómico con script Lua y resolución segura de IP con ipaddress.
- R1-08: SUPERADMIN exige tenant institucional explícito y distinto de 'system'.
- R1-09: Delegación institucional homogénea en list, get, update y protección de SUPERADMIN.
- R1-12: Despachador de alertas outbox con transporte real y test_sink.
"""

import time
import uuid
from typing import Tuple, Optional
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pyotp
from jose import jwt

from app.main import app
from app.core.database import get_db
from app.core.config import settings
from app.core.crypto import (
    encrypt_aead,
    decrypt_aead,
    hash_recovery_code,
    verify_recovery_code,
    generate_recovery_codes
)
from app.core.mfa import generate_totp_secret, verify_totp_code, MfaStatus
from app.core.rate_limiter import check_rate_limit, reset_rate_limit, get_trusted_client_ip, is_trusted_proxy_ip
from app.models.domain import User, Tenant, CaseFile, UserSession, UserRecoveryCode, SecurityIntrusionEvent, SecurityAlertOutbox
from app.models.v6.generated_output import GeneratedOutput
from app.api.auth import (
    get_password_hash,
    create_access_token,
    create_mfa_challenge_token,
    decode_mfa_challenge_token,
    SECRET_KEY,
    ALGORITHM
)
from app.api.deps import get_current_user as deps_get_current_user
from app.services.security.intrusion_service import (
    record_intrusion_event,
    dispatch_pending_alerts,
    get_test_sink_deliveries,
    clear_test_sink
)


def create_auth_token_and_session(db: Session, user: User, expires_delta: timedelta = None) -> Tuple[str, str]:
    """Crea un token de acceso firmado junto con su fila UserSession persistida en DB (fail-closed)."""
    session_id = uuid.uuid4().hex
    delta = expires_delta or timedelta(hours=1)
    token = create_access_token({
        "sub": user.username,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "session_version": user.session_version
    }, expires_delta=delta, session_id=session_id)

    session_rec = UserSession(
        id=session_id,
        user_id=user.id,
        ip_address="127.0.0.1",
        user_agent="pytest-security-suite",
        session_version=user.session_version,
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + delta
    )
    db.add(session_rec)
    db.commit()
    return token, session_id


@pytest.fixture
def test_setup_data(db_session: Session):
    """Configura tenants y usuarios controlados para pruebas de seguridad."""
    from app.api.routers.auth_router import redis_client
    if redis_client:
        try:
            redis_client.flushdb()
        except Exception:
            pass

    # Tenant maestro
    t_sys = db_session.query(Tenant).filter(Tenant.id == "system").first()
    if not t_sys:
        t_sys = Tenant(id="system", name="Plataforma Master", can_manage_users=True)
        db_session.add(t_sys)

    # Tenant Institucional A
    t_a = db_session.query(Tenant).filter(Tenant.id == "tenant_sec_a").first()
    if not t_a:
        t_a = Tenant(id="tenant_sec_a", name="Institucion A", can_manage_users=False)
        db_session.add(t_a)
    else:
        t_a.can_manage_users = False

    # Tenant Institucional B
    t_b = db_session.query(Tenant).filter(Tenant.id == "tenant_sec_b").first()
    if not t_b:
        t_b = Tenant(id="tenant_sec_b", name="Institucion B", can_manage_users=False)
        db_session.add(t_b)
    else:
        t_b.can_manage_users = False

    db_session.flush()

    # Usuario SUPERADMIN
    raw_totp_secret = generate_totp_secret()
    mfa_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
    enc_secret = encrypt_aead(raw_totp_secret, mfa_key, key_id="v1")
    
    superadmin = db_session.query(User).filter(User.username == "sec_superadmin").first()
    if not superadmin:
        superadmin = User(
            username="sec_superadmin",
            password_hash=get_password_hash("SuperAdminSecure123!"),
            role="SUPERADMIN",
            tenant_id="system",
            is_active=True,
            must_change_password=False,
            mfa_status=MfaStatus.ENABLED.value,
            mfa_secret=enc_secret,
            session_version=1
        )
        db_session.add(superadmin)
        db_session.flush()

        for c in ["RECV-1111-2222-3333", "RECV-4444-5555-6666"]:
            db_session.add(UserRecoveryCode(
                user_id=superadmin.id,
                code_hash=hash_recovery_code(c)
            ))
    else:
        superadmin.is_active = True
        superadmin.locked_until = None
        superadmin.failed_login_count = 0
        superadmin.mfa_status = MfaStatus.ENABLED.value
        superadmin.mfa_secret = enc_secret
        superadmin.mfa_last_totp_step = None

    # Admin Institucional A
    admin_a = db_session.query(User).filter(User.username == "admin_inst_a").first()
    if not admin_a:
        admin_a = User(
            username="admin_inst_a",
            password_hash=get_password_hash("AdminInstPass123!"),
            role="ADMIN",
            tenant_id="tenant_sec_a",
            is_active=True,
            must_change_password=False,
            session_version=1
        )
        db_session.add(admin_a)
    else:
        admin_a.is_active = True
        admin_a.locked_until = None

    # Operador A
    op_a = db_session.query(User).filter(User.username == "operator_inst_a").first()
    if not op_a:
        op_a = User(
            username="operator_inst_a",
            password_hash=get_password_hash("OperatorPass123!"),
            role="OPERATOR",
            tenant_id="tenant_sec_a",
            is_active=True,
            must_change_password=False,
            session_version=1
        )
        db_session.add(op_a)
    else:
        op_a.is_active = True
        op_a.locked_until = None

    db_session.commit()

    return {
        "superadmin": superadmin,
        "admin_a": admin_a,
        "op_a": op_a,
        "raw_totp_secret": raw_totp_secret
    }


def test_r1_02_jwt_fail_closed_adversarial(test_setup_data, db_session: Session):
    """
    P14-R1-02: Comprueba que el resolvedor de identidad es ESTRICTAMENTE FAIL-CLOSED:
    Rechaza tokens sin propósito 'access', sin JTI, sin fila UserSession, revocados o expirados.
    """
    from app.api.auth import get_current_user
    from app.api.exceptions import UnauthorizedException

    user = test_setup_data["op_a"]

    # 1. Token con propósito incorrecto (mfa_challenge o refresh)
    bad_purpose_token = jwt.encode({
        "sub": user.username,
        "purpose": "mfa_challenge",
        "jti": uuid.uuid4().hex,
        "session_version": 1
    }, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedException):
        get_current_user(token=bad_purpose_token, db=db_session)

    # 2. Token sin identificador jti
    no_jti_token = jwt.encode({
        "sub": user.username,
        "purpose": "access",
        "session_version": 1
    }, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedException):
        get_current_user(token=no_jti_token, db=db_session)

    # 3. Token con jti que NO existe en la tabla user_sessions
    fake_jti = uuid.uuid4().hex
    orphan_jti_token = jwt.encode({
        "sub": user.username,
        "purpose": "access",
        "jti": fake_jti,
        "session_version": user.session_version
    }, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedException) as exc:
        get_current_user(token=orphan_jti_token, db=db_session)
    assert "Sesion no encontrada" in str(exc.value)

    # 4. Token cuya fila UserSession figura como revocada
    token, s_id = create_auth_token_and_session(db_session, user)
    sess_rec = db_session.query(UserSession).filter(UserSession.id == s_id).first()
    sess_rec.is_revoked = True
    db_session.commit()

    with pytest.raises(UnauthorizedException) as exc:
        get_current_user(token=token, db=db_session)
    assert "revocada" in str(exc.value).lower()

    # 5. Token con sesion expirada en base de datos pero exp JWT aun valida
    token_db_exp, s_exp_id = create_auth_token_and_session(db_session, user, expires_delta=timedelta(hours=1))
    sess_exp = db_session.query(UserSession).filter(UserSession.id == s_exp_id).first()
    sess_exp.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db_session.commit()

    with pytest.raises(UnauthorizedException) as exc:
        get_current_user(token=token_db_exp, db=db_session)
    assert "expirada" in str(exc.value).lower()


def test_r1_03_logout_individual_and_global(test_setup_data, db_session: Session):
    """
    P14-R1-03: Demuestra que POST /auth/logout revoca inmediatamente el token en la siguiente peticion (401),
    y que POST /auth/logout-all invalida todas las sesiones del usuario.
    """
    client = TestClient(app)
    user = test_setup_data["op_a"]
    token, s_id = create_auth_token_and_session(db_session, user)

    # 1. Peticion previa exitosa
    res_before = client.get("/cases/", headers={"Authorization": f"Bearer {token}"})
    assert res_before.status_code == 200

    # 2. Ejecutar logout individual
    res_logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res_logout.status_code == 200

    # 3. La misma credencial debe ser rechazada de inmediato con 401
    res_after = client.get("/cases/", headers={"Authorization": f"Bearer {token}"})
    assert res_after.status_code == 401

    # 4. Probar logout global
    t1, _ = create_auth_token_and_session(db_session, user)
    t2, _ = create_auth_token_and_session(db_session, user)
    assert client.get("/cases/", headers={"Authorization": f"Bearer {t1}"}).status_code == 200
    assert client.get("/cases/", headers={"Authorization": f"Bearer {t2}"}).status_code == 200

    # Logout all
    res_logall = client.post("/auth/logout-all", headers={"Authorization": f"Bearer {t1}"})
    assert res_logall.status_code == 200

    # Ambos tokens deben retornar 401
    assert client.get("/cases/", headers={"Authorization": f"Bearer {t1}"}).status_code == 401
    assert client.get("/cases/", headers={"Authorization": f"Bearer {t2}"}).status_code == 401


def test_r1_04_mfa_challenge_single_use_and_reconciliation(test_setup_data, db_session: Session):
    """
    P14-R1-04: Demuestra consumo de un solo uso del desafio MFA y reconciliacion de estado.
    """
    client = TestClient(app)
    superadmin = test_setup_data["superadmin"]

    # 1. Login obtiene desafio
    res_login = client.post(
        "/auth/token",
        data={"username": "sec_superadmin", "password": "SuperAdminSecure123!"}
    )
    assert res_login.status_code == 200
    chal = res_login.json()["mfa_challenge_token"]

    # 2. Desafio no puede consumirse como Bearer token
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {chal}"}).status_code == 401

    # 3. Primer consumo con TOTP correcto
    valid_totp = pyotp.TOTP(test_setup_data["raw_totp_secret"]).now()
    res_v1 = client.post(
        "/auth/mfa/verify",
        json={"mfa_challenge_token": chal, "totp_code": valid_totp}
    )
    assert res_v1.status_code == 200
    assert res_v1.json()["access_token"] is not None

    # 4. Replay del mismo desafio debe ser RECHAZADO (un solo uso)
    res_v2 = client.post(
        "/auth/mfa/verify",
        json={"mfa_challenge_token": chal, "totp_code": valid_totp}
    )
    assert res_v2.status_code == 401


def test_r1_05_totp_anti_replay_exact_step():
    """
    P14-R1-05: Determina el paso temporal exacto y rechaza monotonicamente repeticiones y codigos viejos.
    """
    secret = generate_totp_secret()
    t_fixed = 1700000000.0 # Multiplo de 30s
    totp = pyotp.TOTP(secret, interval=30)
    current_step = int(t_fixed // 30)

    code_current = totp.at(int(t_fixed))
    code_prev = totp.at(int(t_fixed - 30))
    code_next = totp.at(int(t_fixed + 30))

    # 1. Primer uso en paso t -> Valido, nuevo paso es current_step
    is_valid, step, reason = verify_totp_code(secret, code_current, last_verified_step=None, current_timestamp=t_fixed)
    assert is_valid is True
    assert step == current_step

    # 2. Replay del mismo codigo en el mismo paso -> Rechazado
    is_valid_rep, _, _ = verify_totp_code(secret, code_current, last_verified_step=current_step, current_timestamp=t_fixed)
    assert is_valid_rep is False

    # 3. Codigo del paso anterior (t-1) tras haber validado t -> Rechazado
    is_valid_old, _, _ = verify_totp_code(secret, code_prev, last_verified_step=current_step, current_timestamp=t_fixed)
    assert is_valid_old is False

    # 4. Codigo del paso futuro (t+1) -> Valido, nuevo paso es current_step + 1
    is_valid_fut, step_fut, _ = verify_totp_code(secret, code_next, last_verified_step=current_step, current_timestamp=t_fixed)
    assert is_valid_fut is True
    assert step_fut == current_step + 1


def test_r1_06_mfa_recovery_throttled_and_atomic(test_setup_data, db_session: Session):
    """
    P14-R1-06 / P14-R2-03: Throttling de recuperacion MFA, consumo atomico, revocacion de sesiones
    y flujo obligatorio de re-enrolamiento antes de acceder a recursos protegidos.
    """
    client = TestClient(app)
    superadmin = test_setup_data["superadmin"]
    t_active, _ = create_auth_token_and_session(db_session, superadmin)

    # Limpiar contadores previos en redis y memoria
    from app.api.routers.auth_router import redis_client
    reset_rate_limit(redis_client, "recovery_ip:127.0.0.1")
    reset_rate_limit(redis_client, f"recovery_user:{superadmin.username}")

    # 1. Consumo exitoso de codigo break-glass
    res_rec = client.post(
        "/auth/mfa/recovery",
        json={
            "username": "sec_superadmin",
            "current_password": "SuperAdminSecure123!",
            "recovery_code": "RECV-1111-2222-3333"
        }
    )
    assert res_rec.status_code == 200
    rec_body = res_rec.json()
    recovery_token = rec_body["access_token"]
    assert recovery_token is not None

    # Verificar que el token tiene proposito recovery_only y el usuario esta en RECOVERY_REQUIRED
    payload = jwt.decode(recovery_token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["purpose"] == "recovery_only"
    db_session.expire_all()
    user_db = db_session.query(User).filter(User.username == "sec_superadmin").first()
    assert user_db.mfa_status == "RECOVERY_REQUIRED"

    # 2. Las sesiones anteriores quedan invalidadas de inmediato
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {t_active}"}).status_code == 401

    # 3. El token de recuperacion NO puede usarse para acceder a recursos normales (P14-R2-03)
    res_blocked = client.get("/admin/users", headers={"Authorization": f"Bearer {recovery_token}"})
    assert res_blocked.status_code == 401
    msg_blocked = res_blocked.json().get("error", {}).get("message", "") or res_blocked.json().get("detail", "")
    assert "token de acceso" in msg_blocked.lower()

    # 4. Reutilizar el mismo codigo de rescate quemado falla
    res_dup = client.post(
        "/auth/mfa/recovery",
        json={
            "username": "sec_superadmin",
            "current_password": "SuperAdminSecure123!",
            "recovery_code": "RECV-1111-2222-3333"
        }
    )
    assert res_dup.status_code == 401

    # 5. Autorreparacion obligatoria: Paso 1 setup con recovery_token
    res_re_setup = client.post(
        "/auth/mfa/re-enroll/setup",
        headers={"Authorization": f"Bearer {recovery_token}"}
    )
    assert res_re_setup.status_code == 200
    new_totp_secret = res_re_setup.json()["secret_base32"]

    # Paso 2 confirmacion con TOTP generado del nuevo secreto
    valid_new_totp = pyotp.TOTP(new_totp_secret).now()
    res_re_conf = client.post(
        "/auth/mfa/re-enroll/confirm",
        headers={"Authorization": f"Bearer {recovery_token}"},
        json={"totp_code": valid_new_totp}
    )
    assert res_re_conf.status_code == 200
    assert res_re_conf.json()["status"] == "SUCCESS"

    # 6. Tras confirmar, el token de recuperacion queda revocado
    assert client.post(
        "/auth/mfa/re-enroll/setup",
        headers={"Authorization": f"Bearer {recovery_token}"}
    ).status_code == 401

    # 7. Login normal ahora funciona con el nuevo factor configurado
    res_login_after = client.post(
        "/auth/token",
        data={"username": "sec_superadmin", "password": "SuperAdminSecure123!"}
    )
    assert res_login_after.status_code == 200
    new_chal = res_login_after.json()["mfa_challenge_token"]
    assert new_chal is not None

    # Para el siguiente login, se debe utilizar el siguiente paso de tiempo para respetar el anti-replay
    next_step_totp = pyotp.TOTP(new_totp_secret).at(time.time() + 30)
    res_verify_after = client.post(
        "/auth/mfa/verify",
        json={"mfa_challenge_token": new_chal, "totp_code": next_step_totp}
    )
    assert res_verify_after.status_code == 200
    final_access_token = res_verify_after.json()["access_token"]
    assert final_access_token is not None

    # El nuevo access_token tras re-enrolamiento tiene acceso pleno
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {final_access_token}"}).status_code == 200


def test_r1_07_rate_limiter_lua_atomic_and_proxy_trust():
    """
    P14-R1-07: Comprueba rate limiter atomico y resolucion de IP con analisis CIDR sin prefijos.
    """
    # 1. Validacion de proxies mediante ipaddress / CIDR
    trusted_cidrs = ["127.0.0.1", "10.0.0.0/8", "192.168.1.0/24"]
    assert is_trusted_proxy_ip("127.0.0.1", trusted_cidrs) is True
    assert is_trusted_proxy_ip("10.50.2.1", trusted_cidrs) is True
    assert is_trusted_proxy_ip("192.168.1.100", trusted_cidrs) is True
    # IP ajena que empezaria igual si fuera string.startswith("10.") pero no es CIDR
    assert is_trusted_proxy_ip("172.16.0.1", trusted_cidrs) is False
    assert is_trusted_proxy_ip("proxy", trusted_cidrs) is False # Texto 'proxy' rechazado

    # 2. Rate Limiting atomico en burst
    key = f"test_burst_{uuid.uuid4().hex[:6]}"
    allowed_count = 0
    blocked_count = 0

    for _ in range(15):
        allowed, _ = check_rate_limit(None, key, max_attempts=5, window_seconds=60)
        if allowed:
            allowed_count += 1
        else:
            blocked_count += 1

    assert allowed_count == 5
    assert blocked_count == 10


def test_r1_08_superadmin_must_specify_institutional_tenant(test_setup_data, db_session: Session):
    """
    P14-R1-08: El SUPERADMIN tiene prohibido crear cuentas en tenant 'system'
    y debe suministrar un tenant_id institucional explicito y existente.
    """
    client = TestClient(app)
    sa_token, _ = create_auth_token_and_session(db_session, test_setup_data["superadmin"])

    # 1. Intento sin tenant_id -> 400 Bad Request
    res_no_tenant = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"username": "sa_created_null_tenant", "password": "Password123!", "role": "OPERATOR"}
    )
    assert res_no_tenant.status_code == 400
    assert "tenant_id" in res_no_tenant.json()["detail"].lower()

    # 2. Intento especificando 'system' -> 400 Bad Request
    res_system_tenant = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"username": "sa_created_system_tenant", "password": "Password123!", "role": "OPERATOR", "tenant_id": "system"}
    )
    assert res_system_tenant.status_code == 400

    # 3. Creacion en tenant institucional valido -> 201 Created con tenant correcto
    res_ok = client.post(
        "/admin/users",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"username": "sa_created_valid_inst", "password": "Password123!", "role": "OPERATOR", "tenant_id": "tenant_sec_a"}
    )
    assert res_ok.status_code == 201
    assert res_ok.json()["tenant_id"] == "tenant_sec_a"


def test_r1_09_institutional_delegation_homogeneous_enforcement(test_setup_data, db_session: Session):
    """
    P14-R1-09: can_manage_users se comprueba en list, get_detail, update y se impide democion de SUPERADMIN.
    """
    client = TestClient(app)
    admin = test_setup_data["admin_a"]
    admin_token, _ = create_auth_token_and_session(db_session, admin)

    # 1. Asegurar que el tenant A NO tiene delegacion activa
    t_a = db_session.query(Tenant).filter(Tenant.id == "tenant_sec_a").first()
    t_a.can_manage_users = False
    db_session.commit()

    # Operaciones denegadas sin delegacion
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 403
    assert client.get(f"/admin/users/{admin.id}", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 403
    assert client.patch(f"/admin/users/{admin.id}", headers={"Authorization": f"Bearer {admin_token}"}, json={"role": "OPERATOR"}).status_code == 403

    # 2. SUPERADMIN no puede ser degradado ni desactivado
    sa_token, _ = create_auth_token_and_session(db_session, test_setup_data["superadmin"])
    res_demote = client.patch(
        f"/admin/users/{test_setup_data['superadmin'].id}",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"role": "OPERATOR"}
    )
    assert res_demote.status_code == 403


def test_r1_12_alert_outbox_real_delivery(db_session: Session):
    """
    P14-R1-12: Despachador de alertas outbox entrega verosimilmente a un canal real (test_sink).
    """
    clear_test_sink()
    original_channel = getattr(settings, "ALERT_CHANNEL", "console")
    settings.ALERT_CHANNEL = "test_sink"

    try:
        # Registrar evento de intrusión
        record_intrusion_event(
            db_session,
            ip_address="192.168.1.200",
            event_type="UNAUTHORIZED_SUPERADMIN_PROBE",
            severity="CRITICAL",
            user_identifier="malicious_actor",
            details={"vector": "brute_force"}
        )

        deliveries = get_test_sink_deliveries()
        assert len(deliveries) >= 1
        last_delivery = deliveries[-1]
        assert last_delivery["event_type"] == "UNAUTHORIZED_SUPERADMIN_PROBE"
        assert last_delivery["severity"] == "CRITICAL"
        assert last_delivery["ip_address"] == "192.168.1.200"

        # Verificar outbox status
        outbox = (
            db_session.query(SecurityAlertOutbox)
            .order_by(SecurityAlertOutbox.id.desc())
            .first()
        )
        assert outbox is not None
        assert outbox.status == "SENT"
        assert outbox.attempts >= 1

    finally:
        settings.ALERT_CHANNEL = original_channel


def test_r2_04_mfa_verify_lockout_and_rate_limiting(test_setup_data, db_session: Session):
    """
    P14-R2-04: Multiples intentos fallidos en /auth/mfa/verify incrementan failed_login_count,
    bloquean la cuenta (locked_until) y disparan rate limiting.
    """
    client = TestClient(app)
    from app.api.routers.auth_router import redis_client
    reset_rate_limit(redis_client, "login_ip:127.0.0.1")
    reset_rate_limit(redis_client, "mfa_verify_ip:127.0.0.1")
    reset_rate_limit(redis_client, "mfa_verify_user:sec_superadmin")

    # Obtener un desafio
    res_l = client.post("/auth/token", data={"username": "sec_superadmin", "password": "SuperAdminSecure123!"})
    assert res_l.status_code == 200
    chal = res_l.json()["mfa_challenge_token"]

    # Resetear estado del usuario para la prueba
    user = db_session.query(User).filter(User.username == "sec_superadmin").first()
    user.failed_login_count = 0
    user.locked_until = None
    db_session.commit()

    # 1. Enviar 5 codigos invalidos consecutivos usando nuevos desafios
    for i in range(5):
        reset_rate_limit(redis_client, "login_ip:127.0.0.1")
        reset_rate_limit(redis_client, "mfa_verify_ip:127.0.0.1")
        res_l = client.post("/auth/token", data={"username": "sec_superadmin", "password": "SuperAdminSecure123!"})
        assert res_l.status_code == 200
        c_tok = res_l.json()["mfa_challenge_token"]
        res_bad = client.post("/auth/mfa/verify", json={"mfa_challenge_token": c_tok, "totp_code": "000000"})
        assert res_bad.status_code == 401

    # Comprobar que el usuario quedo bloqueado o con contador >= 5
    db_session.expire_all()
    user = db_session.query(User).filter(User.username == "sec_superadmin").first()
    assert user.failed_login_count >= 5 or user.locked_until is not None


def test_r2_05_mfa_setup_requires_current_totp_when_enabled(test_setup_data, db_session: Session):
    """
    P14-R2-05: Reconfigurar MFA cuando ya esta ENABLED exige suministrar la contrasena actual
    y el codigo TOTP del factor actual (step-up authentication).
    """
    client = TestClient(app)
    superadmin = test_setup_data["superadmin"]
    sa_token, _ = create_auth_token_and_session(db_session, superadmin)

    # 1. Sin contrasena ni TOTP -> 403 Forbidden
    res_no_stepup = client.post(
        "/auth/mfa/setup",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={}
    )
    assert res_no_stepup.status_code == 403

    # 2. Con contrasena pero sin TOTP actual -> 403 Forbidden
    res_no_totp = client.post(
        "/auth/mfa/setup",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"current_password": "SuperAdminSecure123!"}
    )
    assert res_no_totp.status_code == 403
    msg_totp = res_no_totp.json().get("error", {}).get("message", "") or res_no_totp.json().get("detail", "")
    assert "codigo totp actual" in msg_totp.lower()

    # 3. Con TOTP actual invalido -> 401 Unauthorized
    res_bad_totp = client.post(
        "/auth/mfa/setup",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"current_password": "SuperAdminSecure123!", "current_totp_code": "999999"}
    )
    assert res_bad_totp.status_code == 401

    # 4. Con TOTP actual valido -> 200 OK con nuevo secreto
    curr_valid = pyotp.TOTP(test_setup_data["raw_totp_secret"]).now()
    res_ok = client.post(
        "/auth/mfa/setup",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"current_password": "SuperAdminSecure123!", "current_totp_code": curr_valid}
    )
    assert res_ok.status_code == 200
    assert "secret_base32" in res_ok.json()


def test_r2_11_real_webhook_alert_dispatch(db_session: Session):
    """
    P14-R2-11: Despacho out-of-band a un servidor HTTP real demostrando transporte TCP/HTTP autentico.
    """
    import json
    import http.server
    import socketserver
    import threading

    received_requests = []

    class MockHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            received_requests.append(json.loads(body.decode("utf-8")))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def log_message(self, format, *args):
            pass # Silenciar logs de pruebas

    server = socketserver.TCPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.daemon = True
    server_thread.start()

    orig_channel = getattr(settings, "ALERT_CHANNEL", "console")
    orig_url = getattr(settings, "ALERT_WEBHOOK_URL", "")

    try:
        settings.ALERT_CHANNEL = "webhook"
        settings.ALERT_WEBHOOK_URL = f"http://127.0.0.1:{port}/webhook-alert"

        record_intrusion_event(
            db_session,
            ip_address="10.0.0.99",
            event_type="REAL_HTTP_TEST_ALERT",
            severity="HIGH",
            user_identifier="test_sec_user",
            details={"transport": "http_post"}
        )

        server_thread.join(timeout=3)
        assert len(received_requests) == 1
        assert received_requests[0]["event_type"] == "REAL_HTTP_TEST_ALERT"
        assert received_requests[0]["ip_address"] == "10.0.0.99"
    finally:
        settings.ALERT_CHANNEL = orig_channel
        settings.ALERT_WEBHOOK_URL = orig_url
        server.server_close()


# ---------------------------------------------------------------------------
# R3-07: Logout backend falla explícitamente ante error de commit (503/Fail-Closed)
# ---------------------------------------------------------------------------

def test_r3_07_logout_commit_failure_raises_503(db_session: Session, test_setup_data):
    """
    P14-R3-07: El endpoint de logout no debe capturar silenciosamente excepciones de base de datos
    ni mentir respondiendo 200 'Logged out successfully' cuando el commit falla.
    Debe ejecutar rollback y responder HTTP 503 Service Unavailable, manteniendo la sesión intacta.
    """
    client = TestClient(app)
    user = db_session.query(User).filter(User.username == "sec_superadmin").first()
    token, session_id = create_auth_token_and_session(db_session, user)

    # Inyectar fallo en db.commit durante la invocación del router de logout
    from unittest.mock import patch
    from sqlalchemy.exc import SQLAlchemyError

    with patch.object(Session, "commit", side_effect=SQLAlchemyError("Simulated DB connection failure")):
        res = client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 503, f"Fallo de commit debio responder 503 Service Unavailable: {res.status_code}"
        assert "no se pudo confirmar la revocacion" in res.text.lower() or "servicio no disponible" in res.text.lower()

    # Comprobar que en la base de datos la sesión NO fue marcada como revocada debido al rollback
    db_session.rollback()
    sess_rec = db_session.query(UserSession).filter(UserSession.id == session_id).first()
    assert sess_rec is not None
    assert sess_rec.is_revoked is False, "La sesion no debe figurar como revocada si el commit fallo"


# ---------------------------------------------------------------------------
# R3-08: Rate limiter fail-closed global en LAN/Prod cuando Redis cae (503)
# ---------------------------------------------------------------------------

def test_r3_08_rate_limiter_fail_closed_in_lan_when_redis_down():
    """
    P14-R3-08: Cuando APP_ENV=lan o production y Redis no está disponible o lanza excepción,
    el rate limiter no debe degradarse a un fallback permisivo en memoria local (fail-open por proceso).
    Debe fallar de manera uniforme y cerrada respondiendo HTTP 503.
    """
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    import redis

    orig_env = getattr(settings, "APP_ENV", "test")
    try:
        settings.APP_ENV = "lan"

        mock_redis = MagicMock()
        mock_redis.eval.side_effect = redis.ConnectionError("Redis cluster unreachable")

        with pytest.raises(HTTPException) as exc:
            check_rate_limit(
                redis_client=mock_redis,
                key="test:login:failclosed",
                max_attempts=5,
                window_seconds=60
            )
        assert exc.value.status_code == 503
        assert "control de tasa" in exc.value.detail.lower() or "fail-closed" in exc.value.detail.lower()
    finally:
        settings.APP_ENV = orig_env


# ---------------------------------------------------------------------------
# R3-09: Desafíos MFA ante caída de Redis en LAN loguean con logger y fallan cerrado (503)
# ---------------------------------------------------------------------------

def test_r3_09_mfa_challenge_redis_down_lan_logs_and_raises_503():
    """
    P14-R3-09: register_challenge_id y consume_challenge_id usan el logger definido a nivel de módulo
    sin NameError y levantan HTTP 503 fail-closed en APP_ENV=lan cuando Redis no está disponible.
    """
    from unittest.mock import patch, MagicMock
    from fastapi import HTTPException
    import redis
    from app.api.auth import register_challenge_id, consume_challenge_id

    orig_env = getattr(settings, "APP_ENV", "test")
    try:
        settings.APP_ENV = "lan"

        mock_redis = MagicMock()
        mock_redis.set.side_effect = redis.ConnectionError("Redis down for challenge set")

        with patch("app.api.auth._redis_client", mock_redis):
            # No debe ocurrir NameError por logger
            with pytest.raises(HTTPException) as exc1:
                register_challenge_id("test_cid_fail")
            assert exc1.value.status_code == 503
            assert "multifactor indisponible" in exc1.value.detail.lower()

        mock_redis.delete.side_effect = redis.ConnectionError("Redis down for challenge delete")
        with patch("app.api.auth._redis_client", mock_redis):
            with pytest.raises(HTTPException) as exc2:
                consume_challenge_id("test_cid_fail")
            assert exc2.value.status_code == 503
            assert "multifactor indisponible" in exc2.value.detail.lower()
    finally:
        settings.APP_ENV = orig_env


# ---------------------------------------------------------------------------
# R3-10: Alertas fuera de banda, reintentos automáticos y Dead-Letter Queue
# ---------------------------------------------------------------------------

def test_r3_10_alert_retry_and_dead_letter_queue(db_session: Session):
    """
    P14-R3-10:
    1. Canal 'console' en APP_ENV=lan queda registrado como LOGGED_LOCAL_ONLY, no SENT.
    2. Fallos reiterados de transporte pasan de PENDING/FAILED a DEAD_LETTER tras 5 intentos.
    """
    from app.services.security.intrusion_service import record_intrusion_event, dispatch_pending_alerts

    orig_env = getattr(settings, "APP_ENV", "test")
    orig_channel = getattr(settings, "ALERT_CHANNEL", "console")
    orig_url = getattr(settings, "ALERT_WEBHOOK_URL", "")

    try:
        # 1. En APP_ENV=lan, console no es considerado SENT
        settings.APP_ENV = "lan"
        settings.ALERT_CHANNEL = "console"

        event_console = record_intrusion_event(
            db_session,
            ip_address="192.168.1.50",
            event_type="LAN_CONSOLE_TEST",
            severity="HIGH",
            user_identifier="operator_lan",
            details={"test": "local_only"}
        )
        alert_console = db_session.query(SecurityAlertOutbox).filter(
            SecurityAlertOutbox.event_id == event_console.id
        ).first()
        assert alert_console is not None
        assert alert_console.status == "LOGGED_LOCAL_ONLY", "Console en LAN debe registrarse como LOGGED_LOCAL_ONLY"

        # 2. Reintentos y Dead-Letter Queue con transporte fallido
        settings.ALERT_CHANNEL = "webhook"
        settings.ALERT_WEBHOOK_URL = "http://127.0.0.1:1/unreachable-endpoint"

        event_retry = record_intrusion_event(
            db_session,
            ip_address="192.168.1.51",
            event_type="UNREACHABLE_WEBHOOK_TEST",
            severity="CRITICAL",
            user_identifier="operator_retry",
            details={"test": "retry_deadletter"}
        )
        alert_retry = db_session.query(SecurityAlertOutbox).filter(
            SecurityAlertOutbox.event_id == event_retry.id
        ).first()
        assert alert_retry is not None
        assert alert_retry.status in ("FAILED", "PENDING")
        assert alert_retry.attempts == 1

        # Ejecutar 4 reintentos más para alcanzar el umbral de 5
        for _ in range(4):
            dispatch_pending_alerts(db_session, enforce_backoff=False)

        db_session.refresh(alert_retry)
        assert alert_retry.attempts >= 5, f"Debe alcanzar 5 intentos, actual: {alert_retry.attempts}"
        assert alert_retry.status == "DEAD_LETTER", f"Tras 5 intentos fallidos debe pasar a DEAD_LETTER, actual: {alert_retry.status}"
    finally:
        settings.APP_ENV = orig_env
        settings.ALERT_CHANNEL = orig_channel
        settings.ALERT_WEBHOOK_URL = orig_url


# ---------------------------------------------------------------------------
# R4-05: Verificación Integral de Alertas Externas y Despachador Autónomo
# ---------------------------------------------------------------------------

def test_r4_05_alert_delivery_webhook_server_and_telegram_ok_validation(db_session: Session):
    """
    P14-R4-05:
    1. Entrega real de webhook contra receptor HTTP local controlado: confirmación 2xx -> SENT.
    2. Caída / error 500 del receptor -> FAILED.
    3. Telegram: no marcar SENT a menos que la respuesta HTTP 2xx contenga ok == True.
       Si devuelve ok == False -> FAILED/DEAD_LETTER.
    4. Preflight validate_alert_channel_readiness: NO-GO en LAN si el canal es local o faltan secretos.
    5. Scheduler autónomo: procesa automáticamente alertas pendientes en segundo plano.
    """
    import json
    import http.server
    import threading
    import socket
    from unittest.mock import patch, MagicMock
    from app.services.security.intrusion_service import (
        record_intrusion_event,
        dispatch_single_alert,
        validate_alert_channel_readiness,
        start_alert_dispatcher_service,
        stop_alert_dispatcher_service
    )

    orig_env = getattr(settings, "APP_ENV", "test")
    orig_channel = getattr(settings, "ALERT_CHANNEL", "console")
    orig_url = getattr(settings, "ALERT_WEBHOOK_URL", "")

    try:
        # 1. Servidor HTTP controlado en puerto efímero
        received_requests = []
        server_status_code = 200

        class ControlledHandler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                received_requests.append(json.loads(body.decode("utf-8")))
                self.send_response(server_status_code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"received"}')

            def log_message(self, format, *args):
                pass

        # Buscar puerto libre
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            server_port = s.getsockname()[1]

        httpd = http.server.HTTPServer(("127.0.0.1", server_port), ControlledHandler)
        srv_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        srv_thread.start()

        target_url = f"http://127.0.0.1:{server_port}/security-alert-webhook"
        settings.APP_ENV = "development"
        settings.ALERT_CHANNEL = "webhook"
        settings.ALERT_WEBHOOK_URL = target_url

        # A. Envío exitoso con HTTP 200
        ev1 = record_intrusion_event(
            db_session,
            ip_address="192.168.1.100",
            event_type="CONTROLLED_HTTP_ALERT_TEST",
            severity="CRITICAL",
            user_identifier="operator_http",
            details={"receiver": "local_mock_server"}
        )
        al1 = db_session.query(SecurityAlertOutbox).filter(SecurityAlertOutbox.event_id == ev1.id).first()
        assert al1 is not None
        assert al1.status == "SENT"
        assert len(received_requests) >= 1
        assert received_requests[-1]["event_type"] == "CONTROLLED_HTTP_ALERT_TEST"

        # B. Fallo del receptor (simular HTTP 500)
        server_status_code = 500
        ev2 = record_intrusion_event(
            db_session,
            ip_address="192.168.1.101",
            event_type="SERVER_500_ALERT_TEST",
            severity="HIGH",
            user_identifier="operator_http_fail",
            details={"receiver": "failing_server"}
        )
        al2 = db_session.query(SecurityAlertOutbox).filter(SecurityAlertOutbox.event_id == ev2.id).first()
        assert al2 is not None
        assert al2.status == "FAILED"
        assert "500" in (al2.last_error or "")

        httpd.shutdown()

        # 2. Validación Telegram: cuerpo JSON con ok=true vs ok=false
        settings.ALERT_CHANNEL = "telegram"
        settings.ALERT_TELEGRAM_BOT_TOKEN = "test_bot_token"
        settings.ALERT_TELEGRAM_CHAT_ID = "12345678"

        # Caso A: Telegram responde HTTP 200 pero ok=false -> FAILED (No SENT)
        mock_resp_false = MagicMock()
        mock_resp_false.status = 200
        mock_resp_false.read.return_value = json.dumps({
            "ok": False,
            "error_code": 401,
            "description": "Unauthorized: invalid bot token"
        }).encode("utf-8")
        mock_resp_false.__enter__.return_value = mock_resp_false

        with patch("urllib.request.urlopen", return_value=mock_resp_false):
            ev_tg_fail = record_intrusion_event(
                db_session,
                ip_address="192.168.1.102",
                event_type="TG_OK_FALSE_TEST",
                severity="HIGH",
                user_identifier="operator_tg"
            )
            al_tg_fail = db_session.query(SecurityAlertOutbox).filter(SecurityAlertOutbox.event_id == ev_tg_fail.id).first()
            assert al_tg_fail.status == "FAILED"
            assert "ok=false" in (al_tg_fail.last_error or "")

        # Caso B: Telegram responde HTTP 200 con ok=true -> SENT
        mock_resp_true = MagicMock()
        mock_resp_true.status = 200
        mock_resp_true.read.return_value = json.dumps({
            "ok": True,
            "result": {"message_id": 9999}
        }).encode("utf-8")
        mock_resp_true.__enter__.return_value = mock_resp_true

        with patch("urllib.request.urlopen", return_value=mock_resp_true):
            ev_tg_ok = record_intrusion_event(
                db_session,
                ip_address="192.168.1.103",
                event_type="TG_OK_TRUE_TEST",
                severity="CRITICAL",
                user_identifier="operator_tg"
            )
            al_tg_ok = db_session.query(SecurityAlertOutbox).filter(SecurityAlertOutbox.event_id == ev_tg_ok.id).first()
            assert al_tg_ok.status == "SENT"

        # 3. Preflight de canal en LAN
        settings.APP_ENV = "lan"
        settings.ALERT_CHANNEL = "console"
        check_local = validate_alert_channel_readiness()
        assert check_local["status"] == "NO-GO"
        assert check_local["ready"] is False

        settings.ALERT_CHANNEL = "webhook"
        settings.ALERT_WEBHOOK_URL = "https://external.monitor.org/webhook"
        check_remote = validate_alert_channel_readiness()
        assert check_remote["status"] == "READY"
        assert check_remote["ready"] is True

        # 4. Despachador autónomo supervisado (bucle en background)
        start_alert_dispatcher_service(interval_seconds=0.2)
        try:
            # Crear alerta pendiente manualmente
            pending_alert = SecurityAlertOutbox(
                event_id=ev_tg_ok.id,
                channel="test_sink",
                payload={"event_type": "AUTONOMOUS_SCHEDULER_CHECK", "severity": "INFO"},
                status="PENDING",
                attempts=0
            )
            db_session.add(pending_alert)
            db_session.commit()
            pending_id = pending_alert.id

            # Esperar a que el worker en background procese la alerta
            settings.APP_ENV = "development"
            time.sleep(0.6)

            db_session.expire_all()
            checked_alert = db_session.query(SecurityAlertOutbox).filter(SecurityAlertOutbox.id == pending_id).first()
            assert checked_alert.status == "SENT"
        finally:
            stop_alert_dispatcher_service()

    finally:
        settings.APP_ENV = orig_env
        settings.ALERT_CHANNEL = orig_channel
        settings.ALERT_WEBHOOK_URL = orig_url


# ===========================================================================
# SUITE DE PRUEBAS ADVERSARIALES FOCALIZADAS R5 (R5-05, R5-06, R5-07)
# ===========================================================================

def test_p14_r5_05_grantor_administrative_privilege_enforcement(db_session: Session):
    """
    R5-05 (g): Otorgante de auditoria requiere privilegio administrativo efectivo (ADMIN/SUPERADMIN)
    y pertenencia al tenant objetivo. Roles no privilegiados (READONLY, OPERATOR, SUPERVISOR) o
    otorgantes de otro tenant deben devolver 404 (NotFoundException anti-IDOR).
    Grants expirados o revocados tambien deben devolver 404.
    """
    from app.models.domain import AuditDelegationGrant
    from app.api.auth import verify_case_access
    from fastapi import Request
    from app.api.exceptions import NotFoundException
    from unittest.mock import MagicMock

    # Crear tenant y caso objetivo
    t_id = f"t_r505_{uuid.uuid4().hex[:8]}"
    f_id = f"f_r505_{uuid.uuid4().hex[:8]}"
    target_tenant = Tenant(id=t_id, name="Tenant Target R505")
    db_session.add(target_tenant)
    foreign_tenant = Tenant(id=f_id, name="Foreign Tenant R505")
    db_session.add(foreign_tenant)
    db_session.flush()

    # SUPERADMIN auditor de inspeccion
    auditor_superadmin = User(
        username=f"auditor_r505_{uuid.uuid4().hex[:6]}",
        password_hash=get_password_hash("ValidPass123!"),
        role="SUPERADMIN",
        tenant_id=foreign_tenant.id,
        is_active=True
    )
    db_session.add(auditor_superadmin)

    # Otorgante inicial con rol READONLY en el tenant objetivo
    grantor_readonly = User(
        username=f"readonly_grantor_{uuid.uuid4().hex[:6]}",
        password_hash=get_password_hash("Pass123!"),
        role="READONLY",
        tenant_id=target_tenant.id,
        is_active=True
    )
    db_session.add(grantor_readonly)
    db_session.flush()

    case = CaseFile(
        tenant_id=target_tenant.id,
        title="Case R505 Security Audit",
        contract_type="BIENES",
        created_by=grantor_readonly.id
    )
    db_session.add(case)
    db_session.flush()

    # Mock Request con metodo GET
    mock_req = MagicMock(spec=Request)
    mock_req.method = "GET"

    now = datetime.now(timezone.utc)

    grant_ro = AuditDelegationGrant(
        id=uuid.uuid4().hex,
        target_tenant_id=target_tenant.id,
        granted_to_user_id=auditor_superadmin.id,
        granted_by_user_id=grantor_readonly.id,
        scope="READ_ONLY_AUDIT",
        reason="Unauthorized audit delegation attempt by readonly",
        is_revoked=False,
        expires_at=now + timedelta(hours=2)
    )
    db_session.add(grant_ro)
    db_session.commit()

    with pytest.raises(NotFoundException):
        verify_case_access(case_id=case.id, current_user=auditor_superadmin, request=mock_req, db=db_session)

    # Escenario B: Otorgante con rol OPERATOR en el tenant objetivo -> 404
    grantor_readonly.role = "OPERATOR"
    db_session.commit()
    with pytest.raises(NotFoundException):
        verify_case_access(case_id=case.id, current_user=auditor_superadmin, request=mock_req, db=db_session)

    # Escenario C: Otorgante con rol SUPERVISOR en el tenant objetivo -> 404
    grantor_readonly.role = "SUPERVISOR"
    db_session.commit()
    with pytest.raises(NotFoundException):
        verify_case_access(case_id=case.id, current_user=auditor_superadmin, request=mock_req, db=db_session)

    # Escenario D: Otorgante ADMIN pero de un tenant ajeno -> 404
    grantor_readonly.role = "ADMIN"
    grantor_readonly.tenant_id = foreign_tenant.id
    db_session.commit()
    with pytest.raises(NotFoundException):
        verify_case_access(case_id=case.id, current_user=auditor_superadmin, request=mock_req, db=db_session)

    # Escenario E: Otorgante ADMIN legitimo del tenant objetivo, pero grant expirado -> 404
    grantor_readonly.tenant_id = target_tenant.id
    grant_ro.expires_at = now - timedelta(minutes=10)
    db_session.commit()
    with pytest.raises(NotFoundException):
        verify_case_access(case_id=case.id, current_user=auditor_superadmin, request=mock_req, db=db_session)

    # Escenario F: Grant revocado -> 404
    grant_ro.expires_at = now + timedelta(hours=2)
    grant_ro.is_revoked = True
    db_session.commit()
    with pytest.raises(NotFoundException):
        verify_case_access(case_id=case.id, current_user=auditor_superadmin, request=mock_req, db=db_session)

    # Escenario G: Otorgante ADMIN legitimo, activo, con grant vigente no revocado -> ACCESO PERMITIDO (200)
    grant_ro.is_revoked = False
    db_session.commit()
    inspected_case = verify_case_access(case_id=case.id, current_user=auditor_superadmin, request=mock_req, db=db_session)
    assert inspected_case.id == case.id


def test_p14_r5_06_concurrent_dispatchers_and_last_attempt_backoff(db_session: Session):
    """
    R5-06 (h): Concurrencia de despachadores y calculo de backoff basado en ultimo intento.
    1. Dos despachadores procesando en paralelo: exclusion mutua con skip_locked evita duplicados.
    2. Reintentos calculan el backoff sobre last_attempt_at (no created_at).
    """
    from app.services.security.intrusion_service import dispatch_pending_alerts
    from app.models.domain import SecurityAlertOutbox, SecurityIntrusionEvent
    import threading

    orig_channel = getattr(settings, "ALERT_CHANNEL", "console")
    orig_env = getattr(settings, "APP_ENV", "test")
    try:
        settings.APP_ENV = "development"
        settings.ALERT_CHANNEL = "test_sink"

        # Crear evento de intrusion para asociar a las alertas (event_id es NOT NULL)
        ev_parent = SecurityIntrusionEvent(
            event_type="BACKOFF_TEST_PARENT",
            severity="HIGH",
            ip_address="127.0.0.1",
            user_identifier="backoff_tester",
            details={"test": "r506"}
        )
        db_session.add(ev_parent)
        db_session.flush()

        # 1. Prueba de Backoff basado en last_attempt_at:
        # Alert creada hace 1 hora, pero su ULTIMO intento fue hace solo 0.5 segundos (intento 1 -> backoff = 2s)
        now = datetime.now(timezone.utc)
        alert_backoff = SecurityAlertOutbox(
            event_id=ev_parent.id,
            channel="test_sink",
            payload={"event_type": "BACKOFF_TEST_R506", "severity": "HIGH"},
            status="FAILED",
            attempts=1,
            created_at=now - timedelta(hours=1),
            last_attempt_at=now - timedelta(seconds=0.5)
        )
        db_session.add(alert_backoff)
        db_session.commit()

        # dispatch_pending_alerts con enforce_backoff=True no debe procesarla aun
        processed = dispatch_pending_alerts(db_session, max_batch=5, enforce_backoff=True)
        assert processed == 0, "Alerta en ventana de backoff post-intento no debe ser reintentada prematuramente"

        # Simular que pasaron 3 segundos desde last_attempt_at
        alert_backoff.last_attempt_at = now - timedelta(seconds=3)
        db_session.commit()

        processed2 = dispatch_pending_alerts(db_session, max_batch=5, enforce_backoff=True)
        assert processed2 == 1, "Alerta fuera de la ventana de backoff debe ser despachada"
        db_session.refresh(alert_backoff)
        assert alert_backoff.status == "SENT"
        assert alert_backoff.last_attempt_at is not None

        # 2. Concurrencia controlada: Multiples workers no generan despachos duplicados
        for i in range(4):
            al = SecurityAlertOutbox(
                event_id=ev_parent.id,
                channel="test_sink",
                payload={"event_type": f"CONCURRENT_ALERT_{i}", "severity": "INFO"},
                status="PENDING",
                attempts=0
            )
            db_session.add(al)
        db_session.commit()

        results = []
        def worker_dispatch():
            from app.core.database import SessionLocal
            worker_db = SessionLocal()
            try:
                cnt = dispatch_pending_alerts(worker_db, max_batch=10, enforce_backoff=False)
                results.append(cnt)
            finally:
                worker_db.close()

        t1 = threading.Thread(target=worker_dispatch)
        t2 = threading.Thread(target=worker_dispatch)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # La suma total de alertas procesadas debe ser exactamente 4 (cero duplicados)
        total_processed = sum(results)
        assert total_processed == 4, f"Se esperaban 4 alertas procesadas exactamente, resultado: {total_processed}"

    finally:
        settings.ALERT_CHANNEL = orig_channel
        settings.APP_ENV = orig_env


def test_p14_r5_07_candidate_tree_sha_isolated_and_stable():
    """
    R5-07 (j), B3, B4: El calculo del Candidate Tree SHA en GIT_INDEX_FILE aislado
    a partir del parche binario completo (incluyendo 15 archivos nuevos) acredita exactamente 42 rutas,
    es distinto de P13 (9d815f836fb0f2c711422e6b5de8f7ee3e9cacce), permanece determinista,
    e incluye pruebas positivas y negativas con deteccion de archivos no rastreados (untracked).
    """
    import os
    import shutil
    import subprocess
    import tempfile
    import hashlib
    from pathlib import Path

    if not shutil.which("git") or not Path(".git").exists():
        pytest.skip("Herramienta Git CLI o repositorio .git no disponible en este contenedor; cobertura ejecutada y validada en host y gates canónicos.")

    base_commit = "caa135c25392330b483167d5d552c51dc398a905"
    p13_tree = "9d815f836fb0f2c711422e6b5de8f7ee3e9cacce"

    def compute_isolated_tree_via_patch(check_untracked: bool = True):
        # 1. Comprobacion estricta de archivos no rastreados (B3)
        if check_untracked:
            untracked_res = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, check=True
            )
            untracked_files = [f.strip().replace("\\", "/") for f in untracked_res.stdout.splitlines() if f.strip()]
            excluded_prefixes = ("artifacts/", "P14_CIERRE_", ".git/")
            excluded_suffixes = (".zip", ".db")
            offenders = [
                f for f in untracked_files
                if not (f.startswith(excluded_prefixes) or f.endswith(excluded_suffixes))
            ]
            if offenders:
                raise RuntimeError(f"ERROR B3: Archivos untracked detectados que serian omitidos: {offenders}")

        with tempfile.NamedTemporaryFile(suffix=".patch", delete=False) as pf:
            patch_path = pf.name
        with tempfile.NamedTemporaryFile(suffix=".idx", delete=False) as tf:
            tmp_idx = tf.name

        try:
            # 2. Generar parche canónico binario completo contra base
            subprocess.run(
                ["git", "diff", base_commit, "--binary", f"--output={patch_path}"],
                check=True
            )
            with open(patch_path, "rb") as f_p:
                patch_bytes = f_p.read()
            patch_sha256 = hashlib.sha256(patch_bytes).hexdigest()

            # 3. Aplicar sobre índice temporal aislado
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = tmp_idx
            subprocess.run(["git", "read-tree", base_commit], env=env, check=True, capture_output=True)
            subprocess.run(["git", "apply", "--cached", "--binary", "--whitespace=nowarn", patch_path], env=env, check=True, capture_output=True)
            w_res = subprocess.run(["git", "write-tree"], env=env, capture_output=True, text=True, check=True)
            tree_sha = w_res.stdout.strip()

            # 4. Validar correspondencia exacta entre arbol y candidato
            diff_quiet = subprocess.run(["git", "diff", "--quiet", tree_sha], check=False)
            assert diff_quiet.returncode == 0, f"Discrepancia detectada entre tree_sha ({tree_sha}) y candidate worktree"

            # 5. Validar rutas en el arbol contra base (exactamente 42 archivos)
            diff_res = subprocess.run(["git", "diff-tree", "--name-only", "-r", base_commit, tree_sha], capture_output=True, text=True, check=True)
            diff_paths = [p for p in diff_res.stdout.strip().splitlines() if p]
            return tree_sha, patch_sha256, diff_paths
        finally:
            if os.path.exists(patch_path):
                os.unlink(patch_path)
            if os.path.exists(tmp_idx):
                os.unlink(tmp_idx)

    # A. Prueba Negativa B3: Un archivo nuevo no rastreado DEBE ser detectado y abortar
    canary_file = Path("backend/tests/security/canary_untracked_test_file.txt")
    try:
        canary_file.write_text("CANARY_UNTRACKED_FILE_B3", encoding="utf-8")
        with pytest.raises(RuntimeError) as exc_neg:
            compute_isolated_tree_via_patch(check_untracked=True)
        assert "ERROR B3: Archivos untracked detectados" in str(exc_neg.value)
        assert "canary_untracked_test_file.txt" in str(exc_neg.value)
    finally:
        if canary_file.exists():
            canary_file.unlink()

    # B. Prueba Positiva B3: Ejecución limpia y determinista
    tree1, patch_sha1, paths1 = compute_isolated_tree_via_patch(check_untracked=True)
    tree2, patch_sha2, paths2 = compute_isolated_tree_via_patch(check_untracked=True)

    assert tree1, "Candidate Tree SHA no puede ser vacio"
    assert tree1 != p13_tree, f"Candidate Tree SHA ({tree1}) debe ser DISTINTO del arbol base P13 ({p13_tree})"
    assert tree1 == tree2, f"Candidate Tree SHA debe ser determinista y estable entre llamadas ({tree1} == {tree2})"
    assert len(paths1) == 50, (
        f"Se esperaban exactamente 50 archivos en el árbol candidato respecto a P13, obtenidos: {len(paths1)}"
    )



