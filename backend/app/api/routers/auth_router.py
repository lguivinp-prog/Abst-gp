import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
import uuid
from typing import Optional, List, Dict, Tuple
from jose import jwt

logger = logging.getLogger("app.api.auth_router")

from app.core.database import get_db
from app.models.domain import User, UserSession, UserRecoveryCode, SecurityIntrusionEvent
from app.core.config import settings
from app.core.crypto import encrypt_aead, decrypt_aead, hash_recovery_code, verify_recovery_code, generate_recovery_codes
from app.core.mfa import generate_totp_secret, get_totp_provisioning_uri, verify_totp_code, MfaStatus
from app.core.rate_limiter import get_trusted_client_ip, check_rate_limit, reset_rate_limit
from app.services.security.intrusion_service import record_intrusion_event
from app.api.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_mfa_challenge_token,
    decode_mfa_challenge_token,
    get_current_user,
    get_recovery_user,
    require_superadmin,
    oauth2_scheme,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.schemas.auth import (
    Token,
    ChangePasswordRequest,
    MfaVerifyRequest,
    MfaRecoveryRequest,
    MfaSetupRequest,
    MfaSetupResponse,
    MfaReEnrollConfirmRequest
)
from app.api.exceptions import UnauthorizedException, ForbiddenException, ConflictException

try:
    from redis import Redis
    redis_client = Redis.from_url(settings.REDIS_URL)
except Exception:
    redis_client = None

router = APIRouter()


@router.post("/token", response_model=Token)
def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    trusted_proxies = getattr(settings, "TRUSTED_PROXIES", "127.0.0.1,::1").split(",")
    client_ip = get_trusted_client_ip(request, trusted_proxies)

    # 1. Rate Limiting por IP (P14-R1-07)
    allowed, retry_after = check_rate_limit(
        redis_client,
        key=f"login_ip:{client_ip}",
        max_attempts=settings.RATE_LIMIT_LOGIN_MAX,
        window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS
    )
    if not allowed:
        record_intrusion_event(
            db,
            ip_address=client_ip,
            event_type="RATE_LIMIT_EXCEEDED",
            severity="HIGH",
            user_identifier=form_data.username,
            details={"action": "login", "retry_after": retry_after}
        )
        response.headers["Retry-After"] = str(retry_after)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos de acceso fallidos desde esta IP. Reintente en {retry_after} segundos."
        )

    # 2. Busqueda de usuario
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user:
        record_intrusion_event(
            db,
            ip_address=client_ip,
            event_type="AUTH_FAILED_UNKNOWN_USER",
            severity="LOW",
            user_identifier=form_data.username
        )
        raise UnauthorizedException("Incorrect username or password")

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise UnauthorizedException("Account locked")

    if not verify_password(form_data.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()

        record_intrusion_event(
            db,
            ip_address=client_ip,
            event_type="AUTH_FAILED_WRONG_PASSWORD",
            severity="MEDIUM" if user.failed_login_count < 5 else "HIGH",
            user_identifier=user.username,
            tenant_id=user.tenant_id,
            details={"failed_attempts": user.failed_login_count}
        )
        raise UnauthorizedException("Incorrect username or password")

    if not user.is_active:
        raise UnauthorizedException("Inactive user")

    # Autenticacion primaria exitosa: solo resetear rate limit IP si la cuenta NO requiere segundo factor (P14-R2-04)
    if user.role != "SUPERADMIN" and user.mfa_status != MfaStatus.ENABLED.value:
        reset_rate_limit(redis_client, f"login_ip:{client_ip}")
        user.failed_login_count = 0
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    # 3. Flujo MFA para SUPERADMIN o usuarios con MFA activo (P14-R1-04)
    if user.role == "SUPERADMIN" or user.mfa_status == MfaStatus.ENABLED.value:
        challenge_token = create_mfa_challenge_token(user)
        return {
            "access_token": None,
            "token_type": "bearer",
            "mfa_required": True,
            "mfa_challenge_token": challenge_token
        }

    # 4. Flujo estandar: crear sesion fail-closed y emitir JWT
    session_id = uuid.uuid4().hex
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "session_version": user.session_version
        },
        expires_delta=access_token_expires,
        session_id=session_id
    )

    new_session = UserSession(
        id=session_id,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=request.headers.get("User-Agent", "Unknown")[:255],
        session_version=user.session_version,
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + access_token_expires
    )
    db.add(new_session)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "mfa_required": False,
        "mfa_challenge_token": None
    }


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def setup_mfa(
    setup_req: Optional[MfaSetupRequest] = None,
    request: Request = None,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    """
    Enrolamiento / Reconfiguracion de MFA TOTP para el SUPERADMIN (P14-R1-15).
    Exige reautenticacion step-up si la cuenta ya tenia MFA habilitado.
    """
    if current_user.mfa_status == MfaStatus.ENABLED.value:
        if not setup_req or not setup_req.current_password:
            raise ForbiddenException("Se requiere confirmar la contrasena actual (step-up) para reconfigurar MFA.")
        if not verify_password(setup_req.current_password, current_user.password_hash):
            raise UnauthorizedException("Contrasena incorrecta para autorizar reconfiguracion de MFA.")
        if not setup_req.current_totp_code:
            raise ForbiddenException("Se requiere verificar el codigo TOTP actual para autorizar la reconfiguracion de MFA (P14-R2-05).")
        mfa_encryption_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
        try:
            raw_curr_secret = decrypt_aead(current_user.mfa_secret, mfa_encryption_key)
        except Exception:
            raise HTTPException(status_code=500, detail="Error descifrando secreto MFA actual.")
        is_curr_valid, _, reason = verify_totp_code(
            raw_curr_secret,
            setup_req.current_totp_code,
            last_verified_step=current_user.mfa_last_totp_step
        )
        if not is_curr_valid:
            raise UnauthorizedException(f"Codigo TOTP actual invalido: {reason}")

    # 1. Generar secreto y cifrar con AEAD versionada
    raw_secret = generate_totp_secret()
    mfa_encryption_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
    encrypted_secret = encrypt_aead(raw_secret, mfa_encryption_key, key_id="v1")

    # 2. Generar codigos de rescate y guardar hashes Bcrypt
    raw_recovery_codes = generate_recovery_codes(8)
    
    # Eliminar codigos previos no usados
    db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == current_user.id).delete()
    
    for code in raw_recovery_codes:
        code_entry = UserRecoveryCode(
            user_id=current_user.id,
            code_hash=hash_recovery_code(code),
            created_at=datetime.now(timezone.utc)
        )
        db.add(code_entry)

    current_user.mfa_secret = encrypted_secret
    current_user.mfa_status = MfaStatus.PENDING_ENROLLMENT.value
    db.commit()

    uri = get_totp_provisioning_uri(raw_secret, current_user.username)

    return {
        "secret_base32": raw_secret,
        "provisioning_uri": uri,
        "recovery_codes": raw_recovery_codes
    }


@router.post("/mfa/verify", response_model=Token)
def verify_mfa_token(
    req: MfaVerifyRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Verifica el codigo TOTP contra el token de desafio (P14-R1-04, P14-R1-05, P14-R2-04).
    Aplica:
    1. Rate limiting estricto independiente por IP y cuenta de usuario en Redis.
    2. Consumo atomico de desafio unico (anti-replay de tokens).
    3. Bloqueo FOR UPDATE sobre el usuario para evitar carreras.
    4. Determinacion del paso exacto y monotonia estricta (anti-replay de codigos TOTP).
    5. Creacion de sesion fail-closed registrada.
    """
    trusted_proxies = getattr(settings, "TRUSTED_PROXIES", "127.0.0.1,::1").split(",")
    client_ip = get_trusted_client_ip(request, trusted_proxies)

    # 0. Rate limiting por IP en verificacion MFA (P14-R2-04)
    allowed_ip, retry_ip = check_rate_limit(redis_client, f"mfa_verify_ip:{client_ip}", max_attempts=10, window_seconds=300)
    if not allowed_ip:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos de verificacion MFA desde esta IP. Reintente en {retry_ip} segundos.",
            headers={"Retry-After": str(retry_ip)}
        )

    # 1. Decodificar y consumir atomicamente el desafio
    token_data = decode_mfa_challenge_token(req.mfa_challenge_token, consume=True)

    # Rate limiting por usuario en verificacion MFA
    allowed_user, retry_user = check_rate_limit(redis_client, f"mfa_verify_user:{token_data.username}", max_attempts=5, window_seconds=300)
    if not allowed_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos de verificacion MFA para este usuario. Reintente en {retry_user} segundos.",
            headers={"Retry-After": str(retry_user)}
        )

    # 2. Bloqueo transaccional sobre la fila de usuario
    user = db.query(User).filter(User.username == token_data.username).with_for_update().first()

    if not user:
        raise UnauthorizedException("Usuario no encontrado.")

    if not user.is_active:
        raise UnauthorizedException("Usuario inactivo.")

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise UnauthorizedException("Cuenta bloqueada temporalmente.")

    if user.session_version != token_data.session_version:
        raise UnauthorizedException("Desafio revocado por cambio de sesion.")

    if not user.mfa_secret:
        raise UnauthorizedException("MFA no configurado para este usuario.")

    # 3. Descifrar secreto TOTP
    mfa_encryption_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
    try:
        raw_secret = decrypt_aead(user.mfa_secret, mfa_encryption_key)
    except Exception:
        raise HTTPException(status_code=500, detail="Fallo de integridad criptografica en secreto MFA.")

    # 4. Validar codigo TOTP con anti-replay y paso exacto
    is_valid, new_step, reason = verify_totp_code(
        raw_secret,
        req.totp_code,
        last_verified_step=user.mfa_last_totp_step
    )

    if not is_valid:
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()

        record_intrusion_event(
            db,
            ip_address=client_ip,
            event_type="INVALID_MFA_TOTP_ATTEMPT",
            severity="HIGH",
            user_identifier=user.username,
            tenant_id=user.tenant_id,
            details={"reason": reason, "failed_attempts": user.failed_login_count}
        )
        raise UnauthorizedException(reason)

    # 5. Actualizar estado y paso anti-replay tras exito
    reset_rate_limit(redis_client, f"login_ip:{client_ip}")
    reset_rate_limit(redis_client, f"mfa_verify_ip:{client_ip}")
    reset_rate_limit(redis_client, f"mfa_verify_user:{user.username}")
    user.failed_login_count = 0
    user.mfa_status = MfaStatus.ENABLED.value
    user.mfa_last_totp_step = new_step
    user.mfa_last_verified_at = datetime.now(timezone.utc)

    # 6. Crear sesion y emitir JWT
    session_id = uuid.uuid4().hex
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "session_version": user.session_version
        },
        expires_delta=access_token_expires,
        session_id=session_id
    )

    new_session = UserSession(
        id=session_id,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=request.headers.get("User-Agent", "Unknown")[:255],
        session_version=user.session_version,
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + access_token_expires
    )
    db.add(new_session)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "mfa_required": False,
        "mfa_challenge_token": None
    }


@router.post("/mfa/recovery", response_model=Token)
def break_glass_recovery(
    req: MfaRecoveryRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Recuperacion de emergencia (Break-Glass) con codigo de un solo uso (P14-R1-06).
    Aplica:
    1. Throttling estricto por IP y por cuenta de usuario.
    2. Bloqueo transaccional FOR UPDATE sobre User y UserRecoveryCode.
    3. Comprobacion obligatoria de contrasena vigente.
    4. Invalidacion inmediata de todas las sesiones anteriores.
    5. Forzado de estado RECOVERY_REQUIRED.
    """
    trusted_proxies = getattr(settings, "TRUSTED_PROXIES", "127.0.0.1,::1").split(",")
    client_ip = get_trusted_client_ip(request, trusted_proxies)

    # 1. Throttling por IP y por cuenta
    allowed_ip, retry_after_ip = check_rate_limit(
        redis_client,
        key=f"recovery_ip:{client_ip}",
        max_attempts=5,
        window_seconds=900
    )
    allowed_user, retry_after_user = check_rate_limit(
        redis_client,
        key=f"recovery_user:{req.username}",
        max_attempts=3,
        window_seconds=900
    )

    if not allowed_ip or not allowed_user:
        retry_after = max(retry_after_ip, retry_after_user)
        record_intrusion_event(
            db,
            ip_address=client_ip,
            event_type="RATE_LIMIT_EXCEEDED",
            severity="CRITICAL",
            user_identifier=req.username,
            details={"action": "mfa_recovery", "retry_after": retry_after}
        )
        response.headers["Retry-After"] = str(retry_after)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos de recuperacion MFA. Reintente en {retry_after} segundos."
        )

    # 2. Bloqueo transaccional sobre usuario
    user = db.query(User).filter(User.username == req.username).with_for_update().first()
    if not user:
        raise UnauthorizedException("Credenciales de rescate invalidas.")

    if not user.is_active:
        raise UnauthorizedException("Usuario inactivo.")

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise UnauthorizedException("Cuenta bloqueada temporalmente.")

    # 3. Validar contrasena
    if not verify_password(req.current_password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()

        record_intrusion_event(
            db,
            ip_address=client_ip,
            event_type="MFA_RECOVERY_WRONG_PASSWORD",
            severity="CRITICAL",
            user_identifier=user.username,
            tenant_id=user.tenant_id
        )
        raise UnauthorizedException("Credenciales de rescate invalidas.")

    # 4. Bloqueo transaccional sobre codigos de recuperacion
    codes = db.query(UserRecoveryCode).filter(
        UserRecoveryCode.user_id == user.id,
        UserRecoveryCode.used_at == None
    ).with_for_update().all()

    matched_code = None
    for c in codes:
        if verify_recovery_code(req.recovery_code, c.code_hash):
            matched_code = c
            break

    if not matched_code:
        record_intrusion_event(
            db,
            ip_address=client_ip,
            event_type="INVALID_MFA_RECOVERY_ATTEMPT",
            severity="CRITICAL",
            user_identifier=user.username,
            tenant_id=user.tenant_id
        )
        raise UnauthorizedException("Codigo de rescate invalido o ya utilizado.")

    # 5. Quemar atomicamente el codigo
    matched_code.used_at = datetime.now(timezone.utc)

    # 6. Invalidar todas las sesiones anteriores e incrementar version
    db.query(UserSession).filter(UserSession.user_id == user.id).update({"is_revoked": True})
    user.session_version += 1
    user.mfa_status = MfaStatus.RECOVERY_REQUIRED.value
    user.failed_login_count = 0

    # Resetear contadores de rate limit tras consumo exitoso
    reset_rate_limit(redis_client, f"recovery_ip:{client_ip}")
    reset_rate_limit(redis_client, f"recovery_user:{user.username}")

    record_intrusion_event(
        db,
        ip_address=client_ip,
        event_type="MFA_RECOVERY_CODE_CONSUMED",
        severity="CRITICAL",
        user_identifier=user.username,
        tenant_id=user.tenant_id,
        details={"code_id": matched_code.id}
    )

    # 7. Crear sesion de recuperacion exclusiva (P14-R2-03)
    # Emite un token con purpose='recovery_only' y TTL de 10 minutos
    session_id = uuid.uuid4().hex
    recovery_token_expires = timedelta(minutes=10)
    recovery_token = jwt.encode(
        {
            "sub": user.username,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "session_version": user.session_version,
            "exp": datetime.now(timezone.utc) + recovery_token_expires,
            "iat": datetime.now(timezone.utc),
            "jti": session_id,
            "purpose": "recovery_only",
            "scope": "mfa_recovery"
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    new_session = UserSession(
        id=session_id,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=request.headers.get("User-Agent", "Unknown")[:255],
        session_version=user.session_version,
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + recovery_token_expires
    )
    db.add(new_session)
    db.commit()

    return {
        "access_token": recovery_token,
        "recovery_token": recovery_token,
        "token_type": "bearer",
        "mfa_required": False,
        "mfa_challenge_token": None,
        "mfa_status": "RECOVERY_REQUIRED"
    }


@router.post("/mfa/re-enroll/setup", response_model=MfaSetupResponse)
def re_enroll_mfa_setup(
    current_user: User = Depends(get_recovery_user),
    db: Session = Depends(get_db)
):
    """
    Paso 1 de reconfiguracion de MFA para cuentas tras rescate break-glass (P14-R2-03).
    Solo accesible con credencial purpose='recovery_only' en estado RECOVERY_REQUIRED.
    Genera nuevo secreto TOTP y codigos de rescate, manteniendo la cuenta bloqueada hasta confirmacion.
    """
    raw_secret = generate_totp_secret()
    mfa_encryption_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
    encrypted_secret = encrypt_aead(raw_secret, mfa_encryption_key, key_id="v1")

    raw_recovery_codes = generate_recovery_codes(8)
    db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == current_user.id).delete()
    for code in raw_recovery_codes:
        db.add(UserRecoveryCode(
            user_id=current_user.id,
            code_hash=hash_recovery_code(code),
            created_at=datetime.now(timezone.utc)
        ))

    current_user.mfa_secret = encrypted_secret
    db.commit()

    uri = get_totp_provisioning_uri(raw_secret, current_user.username)
    return {
        "secret_base32": raw_secret,
        "provisioning_uri": uri,
        "recovery_codes": raw_recovery_codes
    }


@router.post("/mfa/re-enroll/confirm")
def re_enroll_mfa_confirm(
    req: MfaReEnrollConfirmRequest,
    current_user: User = Depends(get_recovery_user),
    db: Session = Depends(get_db)
):
    """
    Paso 2 de reconfiguracion de MFA: valida que el usuario escaneo y probo su nuevo TOTP.
    Habilita la cuenta (mfa_status=ENABLED), incrementa version de sesion revocando el token
    de recuperacion y exige login nuevo con el factor recien configurado (P14-R2-03).
    """
    mfa_encryption_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
    raw_secret = decrypt_aead(current_user.mfa_secret, mfa_encryption_key)
    is_valid, step, reason = verify_totp_code(raw_secret, req.totp_code)
    if not is_valid:
        raise UnauthorizedException(f"Codigo TOTP invalido para confirmacion: {reason}")

    current_user.mfa_status = MfaStatus.ENABLED.value
    current_user.mfa_last_totp_step = step
    current_user.mfa_last_verified_at = datetime.now(timezone.utc)

    # Revocar de inmediato la sesion de recuperacion e incrementar version
    db.query(UserSession).filter(UserSession.user_id == current_user.id).update({"is_revoked": True})
    current_user.session_version += 1
    db.commit()

    return {
        "status": "SUCCESS",
        "message": "Segundo factor reconfigurado exitosamente. Inicie sesion con sus credenciales y su nuevo codigo TOTP."
    }


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cambio de contrasena con verificacion MFA para SUPERADMIN y revocacion de sesiones (P14-R1-03).
    """
    if not verify_password(req.current_password, current_user.password_hash):
        raise UnauthorizedException("Incorrect current password")

    if current_user.mfa_status == MfaStatus.ENABLED.value:
        if not req.totp_code:
            raise ForbiddenException("Se requiere el codigo TOTP de segundo factor para cambiar la contrasena.")
            
        mfa_encryption_key = getattr(settings, "MFA_ENCRYPTION_KEY", "deterministic_test_mfa_key_32b_!")
        raw_secret = decrypt_aead(current_user.mfa_secret, mfa_encryption_key)
        is_valid, new_step, reason = verify_totp_code(
            raw_secret,
            req.totp_code,
            last_verified_step=current_user.mfa_last_totp_step
        )
        if not is_valid:
            raise UnauthorizedException(f"Validacion MFA fallida: {reason}")
        current_user.mfa_last_totp_step = new_step

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

    current_user.password_hash = get_password_hash(req.new_password)
    current_user.must_change_password = False
    current_user.password_changed_at = datetime.now(timezone.utc)
    
    # Revocar todas las sesiones anteriores
    current_user.session_version += 1
    db.query(UserSession).filter(UserSession.user_id == current_user.id).update({"is_revoked": True})
    db.commit()

    return {"message": "Password changed successfully. All previous sessions revoked."}


@router.post("/logout")
def logout_current_session(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cierra la sesion actual revocando inmediatamente el jti en user_sessions (P14-R1-03, P14-R3-07).
    Falla de forma dura y explicita (500/503) si no se puede confirmar la revocacion en base de datos.
    Cualquier peticion posterior con este token retornara 401 Unauthorized de inmediato.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        raise UnauthorizedException(f"Token de sesion invalido: {e}")

    jti = payload.get("jti")
    if not jti:
        raise UnauthorizedException("El token no contiene un identificador de sesion (jti) valido.")

    session_record = db.query(UserSession).filter(
        UserSession.id == jti,
        UserSession.user_id == current_user.id
    ).first()

    if not session_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesion no encontrada o ya revocada en el servidor."
        )

    session_record.is_revoked = True
    session_record.last_activity_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Fallo critico al confirmar revocacion de sesion {jti} en base de datos: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error de persistencia: no se pudo confirmar la revocacion de la sesion en el servidor."
        )

    return {"message": "Logged out successfully", "revoked": True}


@router.post("/logout-all")
def logout_all_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revoca todas las sesiones activas del usuario incrementando session_version (P14-R1-03).
    """
    current_user.session_version += 1
    db.query(UserSession).filter(UserSession.user_id == current_user.id).update({
        "is_revoked": True,
        "last_activity_at": datetime.now(timezone.utc)
    })
    db.commit()
    return {"message": "All sessions revoked successfully"}
