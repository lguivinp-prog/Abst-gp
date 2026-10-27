from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
import uuid
import threading
import logging
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import bcrypt

from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.models.domain import User, CaseFile, AuditLog, UserSession, AuditDelegationGrant
from app.core.mfa import MfaStatus
from app.schemas.auth import TokenData
from app.api.exceptions import UnauthorizedException, ForbiddenException, NotFoundException

logger = logging.getLogger("app.api.auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

SECRET_KEY = settings.SECRET_KEY if hasattr(settings, "SECRET_KEY") else "default_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)

# Almacenamiento en memoria para desafíos MFA con cerrojo de concurrencia
_CHALLENGE_LOCK = threading.Lock()
_LOCAL_CHALLENGE_STORE: Dict[str, float] = {}

try:
    from redis import Redis
    _redis_client = Redis.from_url(settings.REDIS_URL)
except Exception:
    _redis_client = None


def register_challenge_id(challenge_id: str, ttl_seconds: int = 180) -> None:
    """Registra un ID de desafio MFA para consumo de un solo uso (fail-closed en LAN/prod, P14-R2-06)."""
    now = datetime.now(timezone.utc).timestamp()
    app_env = getattr(settings, "APP_ENV", "development").lower()
    if _redis_client:
        try:
            _redis_client.set(f"mfa_chal:{challenge_id}", "ACTIVE", ex=ttl_seconds)
            return
        except Exception as e:
            if app_env in ("lan", "production"):
                logger.critical(f"Redis indisponible para registro de desafios MFA en entorno {app_env}: {e}")
                raise HTTPException(status_code=503, detail="Servicio de autenticacion multifactor indisponible (fail-closed).")
    elif app_env in ("lan", "production"):
        raise HTTPException(status_code=503, detail="Servicio de autenticacion multifactor no configurado (fail-closed).")

    with _CHALLENGE_LOCK:
        # Limpiar expirados
        expired = [cid for cid, exp in _LOCAL_CHALLENGE_STORE.items() if exp < now]
        for cid in expired:
            _LOCAL_CHALLENGE_STORE.pop(cid, None)
        _LOCAL_CHALLENGE_STORE[challenge_id] = now + ttl_seconds


def consume_challenge_id(challenge_id: str) -> bool:
    """
    Consume atomicamente un ID de desafio MFA. Retorna True si existia y fue consumido,
    False si ya habia sido consumido o expiro (fail-closed en LAN/prod, P14-R2-06).
    """
    now = datetime.now(timezone.utc).timestamp()
    app_env = getattr(settings, "APP_ENV", "development").lower()
    if _redis_client:
        try:
            deleted = _redis_client.delete(f"mfa_chal:{challenge_id}")
            if deleted > 0:
                return True
        except Exception as e:
            if app_env in ("lan", "production"):
                logger.critical(f"Redis indisponible para consumo de desafios MFA en entorno {app_env}: {e}")
                raise HTTPException(status_code=503, detail="Servicio de autenticacion multifactor indisponible (fail-closed).")
    elif app_env in ("lan", "production"):
        raise HTTPException(status_code=503, detail="Servicio de autenticacion multifactor no configurado (fail-closed).")

    with _CHALLENGE_LOCK:
        exp = _LOCAL_CHALLENGE_STORE.pop(challenge_id, None)
        if exp and exp > now:
            return True
        return False


def verify_password(plain_password, hashed_password):
    password_bytes = plain_password.encode('utf-8')
    try:
        hashed_bytes = hashed_password.encode('utf-8')
        if len(password_bytes) > 72:
            truncated = password_bytes[:72].decode('utf-8', errors='ignore')
            try:
                if bcrypt.checkpw(password_bytes, hashed_bytes):
                    return True
            except ValueError:
                pass
            return bcrypt.checkpw(truncated.encode('utf-8'), hashed_bytes)
        else:
            return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def get_password_hash(password):
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 71:
        raise ValueError("Password exceeds 71 bytes limit")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, session_id: Optional[str] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    jti = session_id if session_id else uuid.uuid4().hex
    session_version = to_encode.get("session_version", 1)
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": jti,
        "session_version": session_version,
        "purpose": "access"
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_mfa_challenge_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    """
    Genera un token de desafio temporal de proposito unico (purpose='mfa_challenge')
    vinculado al estado, tenant y version de sesion del usuario (P14-R1-04).
    """
    challenge_minutes = getattr(settings, "MFA_CHALLENGE_EXPIRE_MINUTES", 3)
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
        ttl_seconds = int(expires_delta.total_seconds())
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=challenge_minutes)
        ttl_seconds = challenge_minutes * 60

    challenge_id = uuid.uuid4().hex
    register_challenge_id(challenge_id, ttl_seconds=ttl_seconds)

    to_encode = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "session_version": user.session_version,
        "challenge_id": challenge_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": challenge_id,
        "purpose": "mfa_challenge"
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_mfa_challenge_token(token: str, consume: bool = True) -> TokenData:
    """
    Valida y decodifica un token de desafio MFA exigiendo purpose='mfa_challenge'
    y consumiendo atomicamente su challenge_id de un solo uso (P14-R1-04).
    """
    credentials_exception = UnauthorizedException("Token de desafio MFA invalido o expirado")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "mfa_challenge":
            raise credentials_exception
        username: str = payload.get("sub")
        challenge_id = payload.get("challenge_id") or payload.get("jti")
        if not username or not challenge_id:
            raise credentials_exception

        if consume:
            is_fresh = consume_challenge_id(challenge_id)
            if not is_fresh:
                raise UnauthorizedException("El desafio MFA ya ha sido utilizado o ha expirado.")

        return TokenData(
            username=username,
            role=payload.get("role"),
            tenant_id=payload.get("tenant_id"),
            jti=challenge_id,
            session_version=payload.get("session_version"),
            purpose="mfa_challenge"
        )
    except JWTError:
        raise credentials_exception


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    Resuelve el usuario autenticado de forma ESTRICTAMENTE FAIL-CLOSED (P14-R1-02).
    Exige obligatoriamente:
    1. purpose == 'access'.
    2. jti presente y existente en user_sessions.
    3. Fila de sesion no revocada, vigente y perteneciente al usuario.
    4. Version de sesion del token identica a user.session_version.
    5. Usuario activo, no bloqueado y con resolucion institucional valida.
    """
    credentials_exception = UnauthorizedException("Could not validate credentials")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # 1. Proposito estrictamente 'access'
        purpose = payload.get("purpose")
        if purpose != "access":
            if purpose == "mfa_challenge":
                raise UnauthorizedException("El token de desafio MFA no puede ser utilizado como token de acceso.")
            raise UnauthorizedException("Token de proposito invalido: se requiere token de acceso.")

        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception

        jti = payload.get("jti")
        if not jti:
            raise UnauthorizedException("Token invalido: identificador de sesion (jti) ausente.")

        token_session_version = payload.get("session_version")
        if token_session_version is None:
            raise UnauthorizedException("Token invalido: version de sesion ausente.")
        
        # Extract issued at
        iat_timestamp = payload.get("iat")
        if iat_timestamp:
            issued_at = datetime.fromtimestamp(iat_timestamp, tz=timezone.utc)
        else:
            issued_at = None
            
        token_data = TokenData(
            username=username,
            role=payload.get("role"),
            tenant_id=payload.get("tenant_id"),
            jti=jti,
            session_version=token_session_version,
            issued_at=issued_at,
            purpose=purpose
        )
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.username == token_data.username).first()
    if user is None:
        raise credentials_exception
        
    if not user.is_active:
        raise UnauthorizedException("Inactive user")
        
    if user.tenant_id is None:
        raise UnauthorizedException("User tenant assignment missing")
        
    if user.tenant_resolution_status != 'RESOLVED':
        raise UnauthorizedException("User is quarantined or unresolved")
        
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise UnauthorizedException("Account locked")

    # 2. Version de sesion global (revocacion global)
    if user.session_version != token_data.session_version:
        raise UnauthorizedException("Token revocado por invalidacion de sesion.")

    # 3. Fila de sesion individual en user_sessions (revocacion individual fail-closed)
    session_record = db.query(UserSession).filter(UserSession.id == token_data.jti).first()
    if not session_record:
        raise UnauthorizedException("Sesion no encontrada o inexistente.")

    if session_record.user_id != user.id:
        raise UnauthorizedException("Sesion no corresponde al usuario autenticado.")

    if session_record.is_revoked:
        raise UnauthorizedException("Sesion revocada por cierre de sesion.")

    if session_record.expires_at <= datetime.now(timezone.utc):
        raise UnauthorizedException("Sesion expirada.")

    if session_record.session_version != user.session_version:
        raise UnauthorizedException("Sesion revocada por invalidacion global.")

    # 4. Revocation check por cambio de contrasena
    if user.password_changed_at and token_data.issued_at:
        if user.password_changed_at > (token_data.issued_at + timedelta(seconds=1)):
            raise UnauthorizedException("Token revoked due to password change")

    # 5. Estado de recuperacion MFA (P14-R2-03)
    # Ninguna cuenta en estado RECOVERY_REQUIRED puede acceder a recursos normales
    if user.mfa_status == MfaStatus.RECOVERY_REQUIRED.value:
        raise ForbiddenException("La cuenta requiere reconfiguracion obligatoria de MFA tras rescate de emergencia antes de acceder a recursos del sistema.")

    # Actualizar actividad
    session_record.last_activity_at = datetime.now(timezone.utc)

    return user


def get_recovery_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    Resuelve el usuario para operaciones exclusivas de autorreparacion/re-enrolamiento MFA (P14-R2-03).
    Solo admite tokens con purpose='recovery_only' y usuarios con mfa_status='RECOVERY_REQUIRED'.
    """
    credentials_exception = UnauthorizedException("Credencial de recuperacion invalida")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        purpose = payload.get("purpose")
        if purpose != "recovery_only":
            raise UnauthorizedException("Se requiere un token exclusivo de recuperacion break-glass.")
        username: str = payload.get("sub")
        jti = payload.get("jti")
        token_session_version = payload.get("session_version")
        if not username or not jti or token_session_version is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or (user.locked_until and user.locked_until > datetime.now(timezone.utc)):
        raise credentials_exception

    if user.session_version != token_session_version:
        raise UnauthorizedException("Sesion de recuperacion revocada.")

    session_record = db.query(UserSession).filter(UserSession.id == jti).first()
    if not session_record or session_record.is_revoked or session_record.expires_at <= datetime.now(timezone.utc):
        raise UnauthorizedException("Sesion de recuperacion expirada o revocada.")

    if user.mfa_status != MfaStatus.RECOVERY_REQUIRED.value:
        raise ForbiddenException("El usuario no se encuentra en estado de recuperacion pendiente.")

    return user


def require_role(roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise ForbiddenException("Not enough permissions")
        return current_user
    return role_checker


def require_superadmin(current_user: User = Depends(get_current_user)) -> User:
    """Verifica que el usuario posea exclusivamente el rol SUPERADMIN."""
    if current_user.role != "SUPERADMIN":
        raise ForbiddenException("Acceso restringido exclusivamente al SUPERADMIN de la plataforma.")
    return current_user


def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.must_change_password:
        raise ForbiddenException("You must change your password before proceeding.")
    return current_user


def verify_case_access(
    case_id: int,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Dependency to verify a user has access to a specific case file.
    P14-R3-01: Aislamiento estricto multitenant con concesiones de auditoria formalmente autorizadas.
    - Ningun usuario institucional accede a expedientes de otro tenant.
    - SUPERADMIN no obtiene acceso operativo transversal automatico.
    - Una cabecera unilateral X-Audit-Tenant-ID o inventada NO concede acceso sin una concesion activa en base de datos.
    - Las concesiones de auditoria son estrictamente de solo lectura (verbos mutadores prohibidos) y mantienen SoD.
    """
    case = db.query(CaseFile).filter(CaseFile.id == case_id).first()
    if not case:
        raise NotFoundException(f"Case file with ID {case_id} not found")

    # Si el usuario pertenece al tenant del caso
    if current_user.tenant_id == case.tenant_id:
        if current_user.role not in ["ADMIN", "SUPERVISOR", "SUPERADMIN"]:
            if case.assigned_to_user_id != current_user.id:
                raise NotFoundException(f"Case file with ID {case_id} not found")
        return case

    # Caso de acceso cruzado entre tenants (R3-01, R4-03, R4-04):
    # Solo SUPERADMIN con una concesion de auditoria formal activa, vigente, de scope READ_ONLY_AUDIT
    if current_user.role == "SUPERADMIN":
        now = datetime.now(timezone.utc)
        active_grant = db.query(AuditDelegationGrant).filter(
            AuditDelegationGrant.target_tenant_id == case.tenant_id,
            AuditDelegationGrant.granted_to_user_id == current_user.id,
            AuditDelegationGrant.scope == "READ_ONLY_AUDIT",
            AuditDelegationGrant.is_revoked == False,
            AuditDelegationGrant.expires_at > now,
            AuditDelegationGrant.granted_by_user_id != current_user.id
        ).first()

        if not active_grant:
            # Cabecera arbitraria, scope invalido, grant revocado/expirado o auto-concesion -> 404 (Anti-IDOR)
            raise NotFoundException(f"Case file with ID {case_id} not found")

        # R4-03, R5-05: Validar procedencia y legitimidad del otorgante con capacidad institucional
        grantor = db.query(User).filter(User.id == active_grant.granted_by_user_id).first()
        if not grantor or not grantor.is_active or grantor.tenant_id != case.tenant_id:
            raise NotFoundException(f"Case file with ID {case_id} not found")

        # R5-05: Exigir rol administrativo explicito en el tenant objetivo (ADMIN o SUPERADMIN)
        # Otorgantes con rol READONLY, OPERATOR, SUPERVISOR, etc., NO tienen permiso de delegacion de auditoria
        if grantor.role not in ("ADMIN", "SUPERADMIN"):
            raise NotFoundException(f"Case file with ID {case_id} not found")

        # Concesion formal verificada: exigir operacion estrictamente de solo lectura (R3-01, R4-03)
        if request.method.upper() not in ("GET", "HEAD", "OPTIONS"):
            raise ForbiddenException(
                "Las concesiones de auditoria institucional son estrictamente de solo lectura. "
                "Cualquier operacion mutadora sobre el expediente esta prohibida."
            )

        # R4-04: Registrar evento auditable inmutable de forma duradera en sesion aislada (fail-closed)
        # NUNCA hacer commit sobre la sesion principal 'db' dentro de una operacion GET
        audit_session = SessionLocal()
        try:
            audit_entry = AuditLog(
                tenant_id=case.tenant_id,
                user_id=current_user.id,
                action="CROSS_TENANT_AUDIT_INSPECTION",
                entity_type="case_file",
                entity_id=str(case.id),
                status="SUCCESS",
                details=f"Inspeccion autorizada bajo concesion {active_grant.id} (scope={active_grant.scope}): {active_grant.reason}"
            )
            audit_session.add(audit_entry)
            audit_session.commit()
        except Exception as e:
            audit_session.rollback()
            logger.critical(f"Fallo critico registrando auditoria durable de acceso interinstitucional (R4-04): {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Fallo en subsistema de auditoria de seguridad: acceso denegado (fail-closed)."
            )
        finally:
            audit_session.close()

        return case

    # Cualquier otro intento cruzado -> 404 Not Found (Anti-IDOR)
    raise NotFoundException(f"Case file with ID {case_id} not found")
