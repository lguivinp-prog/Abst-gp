from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import sqlalchemy

from app.core.database import get_db
from app.models.domain import User, Tenant, SecurityIntrusionEvent, SecurityAlertOutbox
from app.schemas.auth import UserCreate, UserResponse, AdminUserUpdate, AssignableRole
from app.api.auth import get_current_user, require_role, require_superadmin, get_password_hash
from app.api.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.services.security.intrusion_service import record_intrusion_event, dispatch_pending_alerts
from app.api.admin import monitoring

router = APIRouter()
router.include_router(monitoring.router, prefix="/monitoring", tags=["admin-monitoring"])


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPERADMIN"]))
):
    """
    Creacion de usuarios institucionales (P14-R1-08, P14-R1-09).
    - Para SUPERADMIN: tenant_id es OBLIGATORIO, existente y distinto de 'system'.
    - Para ADMIN: estrictamente limitado al tenant propio si y solo si can_manage_users esta habilitado.
    - Aplica lista blanca estricta (AssignableRole: SUPERVISOR, OPERATOR, READONLY).
    """
    # 1. Validacion de tenant de destino y delegacion
    if current_user.role == "SUPERADMIN":
        if not user_in.tenant_id or user_in.tenant_id.strip() == "system":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El SUPERADMIN debe especificar un tenant_id institucional valido y distinto de 'system' para crear una cuenta (P14-R1-08)."
            )
        target_tenant = db.query(Tenant).filter(Tenant.id == user_in.tenant_id.strip()).first()
        if not target_tenant:
            raise NotFoundException(f"El tenant institucional '{user_in.tenant_id}' no existe.")
        target_tenant_id = target_tenant.id
    else:
        # Administrador institucional
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        if not tenant or not tenant.can_manage_users:
            raise ForbiddenException(
                "La administracion delegada de usuarios no esta habilitada para esta institucion. "
                "Contacte al SUPERADMIN para solicitar autorizacion (P14-R1-09)."
            )
        if user_in.tenant_id and user_in.tenant_id != current_user.tenant_id:
            raise ForbiddenException("Un administrador institucional no puede crear usuarios fuera de su tenant asignado.")
        target_tenant_id = current_user.tenant_id

    # 2. Impedir escalamiento a SUPERADMIN o ADMIN
    role_str = str(user_in.role).upper()
    if role_str in ("SUPERADMIN", "ADMIN"):
        record_intrusion_event(
            db,
            ip_address="internal_api",
            event_type="PRIVILEGE_ESCALATION_ATTEMPT",
            severity="CRITICAL",
            user_identifier=current_user.username,
            tenant_id=current_user.tenant_id,
            details={"attempted_role": role_str, "target_username": user_in.username}
        )
        raise ForbiddenException("No esta permitido asignar el rol SUPERADMIN ni ADMIN por la API.")

    # 3. Comprobar existencia previa de username
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise ConflictException("Username already registered")

    new_user = User(
        username=user_in.username,
        password_hash=get_password_hash(user_in.password),
        role=user_in.role.value if hasattr(user_in.role, "value") else str(user_in.role),
        is_active=True,
        must_change_password=True,
        created_by_user_id=current_user.id,
        tenant_id=target_tenant_id,
        mfa_status="DISABLED",
        session_version=1
    )
    db.add(new_user)
    try:
        db.commit()
    except sqlalchemy.exc.IntegrityError as e:
        db.rollback()
        diag = getattr(e.orig, "diag", None)
        constraint_name = getattr(diag, "constraint_name", None) if diag else None
        if constraint_name in ("ix_users_admin_singleton", "ix_users_admin_tenant"):
            raise ConflictException("An ADMIN user already exists.")
        if constraint_name == "ix_users_superadmin_singleton":
            raise ConflictException("A SUPERADMIN user already exists on the platform.")
        raise e

    db.refresh(new_user)
    return new_user


@router.get("/users", response_model=List[UserResponse])
def list_users(
    tenant_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPERADMIN"]))
):
    """
    Lista los usuarios del tenant correspondiente (P14-R1-09).
    Exige can_manage_users habilitado para administradores institucionales.
    """
    query = db.query(User)
    if current_user.role != "SUPERADMIN":
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        if not tenant or not tenant.can_manage_users:
            raise ForbiddenException(
                "La administracion delegada de usuarios no esta habilitada para esta institucion. "
                "Contacte al SUPERADMIN para solicitar autorizacion (P14-R1-09)."
            )
        query = query.filter(User.tenant_id == current_user.tenant_id)
    elif tenant_id:
        query = query.filter(User.tenant_id == tenant_id)

    return query.order_by(User.id.asc()).all()


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPERADMIN"]))
):
    """
    Obtiene el detalle de un usuario respetando el aislamiento multitenant y delegacion (P14-R1-09).
    """
    if current_user.role != "SUPERADMIN":
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        if not tenant or not tenant.can_manage_users:
            raise ForbiddenException(
                "La administracion delegada de usuarios no esta habilitada para esta institucion (P14-R1-09)."
            )

    query = db.query(User).filter(User.id == user_id)
    if current_user.role != "SUPERADMIN":
        query = query.filter(User.tenant_id == current_user.tenant_id)

    user = query.first()
    if not user:
        raise NotFoundException(f"Usuario {user_id} no encontrado")
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPERADMIN"]))
):
    """
    Actualiza rol, estado o desbloqueo de cuenta (P14-R1-09).
    Exige can_manage_users para administradores institucionales e impide
    auto-democion o desactivacion accidental del SUPERADMIN.
    """
    if current_user.role != "SUPERADMIN":
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        if not tenant or not tenant.can_manage_users:
            raise ForbiddenException(
                "La administracion delegada de usuarios no esta habilitada para esta institucion (P14-R1-09)."
            )

    query = db.query(User).filter(User.id == user_id)
    if current_user.role != "SUPERADMIN":
        query = query.filter(User.tenant_id == current_user.tenant_id)

    target_user = query.first()
    if not target_user:
        raise NotFoundException(f"Usuario {user_id} no encontrado")

    # Impedir alterar al SUPERADMIN por administradores no autorizados
    if target_user.role == "SUPERADMIN" and current_user.role != "SUPERADMIN":
        raise ForbiddenException("No esta permitido alterar la cuenta del SUPERADMIN por la API.")

    # Salvaguarda de singleton SUPERADMIN: no auto-democion ni desactivacion
    if target_user.role == "SUPERADMIN":
        if user_update.role is not None and str(user_update.role).upper() != "SUPERADMIN":
            raise ForbiddenException("No esta permitido degradar la cuenta SUPERADMIN de la plataforma.")
        if user_update.is_active is False:
            raise ForbiddenException("No esta permitido desactivar la cuenta SUPERADMIN de la plataforma.")

    if user_update.role is not None:
        role_str = str(user_update.role).upper()
        if role_str in ("SUPERADMIN", "ADMIN"):
            raise ForbiddenException("No esta permitido elevar privilegios a SUPERADMIN ni ADMIN.")
        target_user.role = user_update.role.value if hasattr(user_update.role, "value") else str(user_update.role)

    if user_update.is_active is not None:
        target_user.is_active = user_update.is_active
        if not user_update.is_active:
            target_user.session_version += 1 # Invalida sesiones activas al desactivar

    if user_update.must_change_password is not None:
        target_user.must_change_password = user_update.must_change_password

    if user_update.unlock_account:
        target_user.locked_until = None
        target_user.failed_login_count = 0

    db.commit()
    db.refresh(target_user)
    return target_user


@router.post("/tenants/{target_tenant_id}/delegation")
def configure_tenant_delegation(
    target_tenant_id: str,
    enabled: bool = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    """Permite al SUPERADMIN activar o revocar la gestion delegada de usuarios en un tenant (P14-R1-09)."""
    tenant = db.query(Tenant).filter(Tenant.id == target_tenant_id).first()
    if not tenant:
        raise NotFoundException(f"Tenant '{target_tenant_id}' no encontrado.")

    tenant.can_manage_users = enabled
    db.commit()
    return {
        "tenant_id": target_tenant_id,
        "can_manage_users": enabled,
        "message": f"Delegacion de usuarios {'habilitada' if enabled else 'revocada'} para tenant '{target_tenant_id}'."
    }


@router.get("/security/events")
def list_security_intrusion_events(
    limit: int = 50,
    severity: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    """Consulta de eventos de intrusion exclusiva del SUPERADMIN (P14-R1-12)."""
    query = db.query(SecurityIntrusionEvent)
    if severity:
        query = query.filter(SecurityIntrusionEvent.severity == severity.upper())

    events = query.order_by(SecurityIntrusionEvent.id.desc()).limit(limit).all()
    
    return [
        {
            "id": e.id,
            "ip_address": e.ip_address,
            "user_identifier": e.user_identifier,
            "tenant_id": e.tenant_id,
            "event_type": e.event_type,
            "severity": e.severity,
            "details": e.details,
            "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None
        }
        for e in events
    ]


@router.get("/security/alerts")
def list_security_outbox_alerts(
    status_filter: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    """Consulta de alertas en la cola de outbox (P14-R1-12)."""
    query = db.query(SecurityAlertOutbox)
    if status_filter:
        query = query.filter(SecurityAlertOutbox.status == status_filter.upper())

    alerts = query.order_by(SecurityAlertOutbox.id.desc()).limit(limit).all()
    return [
        {
            "id": a.id,
            "event_id": a.event_id,
            "channel": a.channel,
            "destination": a.destination,
            "payload": a.payload,
            "status": a.status,
            "attempts": a.attempts,
            "last_error": a.last_error,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "processed_at": a.processed_at.isoformat() if a.processed_at else None
        }
        for a in alerts
    ]


@router.post("/security/alerts/dispatch")
def trigger_alert_dispatch(
    max_batch: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    """Ejecuta el despacho de alertas pendientes en outbox (P14-R1-12)."""
    count = dispatch_pending_alerts(db, max_batch=max_batch)
    return {"dispatched_count": count, "message": f"Se procesaron {count} alertas del outbox."}
