from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
import sqlalchemy

from app.core.database import get_db
from app.models.domain import User
from app.schemas.auth import UserCreate, UserResponse
from app.api.auth import get_current_user, require_role, get_password_hash
from app.api.exceptions import ConflictException
from app.api.admin import monitoring

router = APIRouter()
router.include_router(monitoring.router, prefix="/monitoring", tags=["admin-monitoring"])


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN"]))
):
    # Check if username exists
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise ConflictException("Username already registered")
        
    # Prevent creating multiple ADMINs (Basic check, will also catch concurrently via IntegrityError)
    if user_in.role == "ADMIN":
        admin_exists = db.query(User).filter(User.role == "ADMIN", User.tenant_id == current_user.tenant_id).first()
        if admin_exists:
            raise ConflictException("An ADMIN user already exists for this tenant.")

    new_user = User(
        username=user_in.username,
        password_hash=get_password_hash(user_in.password),
        role=user_in.role,
        is_active=True,
        must_change_password=True,
        created_by_user_id=current_user.id,
        tenant_id=current_user.tenant_id
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
            
        raise e
        
    db.refresh(new_user)
    
    return new_user
