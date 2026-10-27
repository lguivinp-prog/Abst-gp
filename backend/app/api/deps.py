from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.models.domain import User
from app.api.auth import get_current_user, require_role

# Re-exportamos get_current_user desde app.api.auth para erradicar el mock bypass (P14-G01)

def require_admin_it(current_user: User = Depends(get_current_user)):
    if current_user.role not in ("ADMIN_IT_INSTITUCIONAL", "ADMIN", "SUPERADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los usuarios con rol ADMIN_IT_INSTITUCIONAL pueden modificar configuraciones del tenant."
        )
    return current_user

def require_system_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in ("SYSTEM_ADMIN", "SUPERADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a SYSTEM_ADMIN o SUPERADMIN."
        )
    return current_user
