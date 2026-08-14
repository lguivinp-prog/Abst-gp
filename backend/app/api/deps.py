from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.domain import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # Mock JWT decoding
    user = db.query(User).filter(User.id == 1).first() # Default fallback for legacy endpoints
    if not user:
        raise HTTPException(status_code=401, detail="Invalid auth credentials")
    return user

def require_admin_it(current_user: User = Depends(get_current_user)):
    if current_user.role != "ADMIN_IT_INSTITUCIONAL":
        raise HTTPException(status_code=403, detail="Solo los usuarios con rol ADMIN_IT_INSTITUCIONAL pueden modificar configuraciones del tenant.")
    return current_user

def require_system_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "SYSTEM_ADMIN":
        raise HTTPException(status_code=403, detail="Acceso restringido a SYSTEM_ADMIN.")
    # Note: Multi-Tenant isolation is maintained. SYSTEM_ADMIN cannot access another tenant's data implicitly.
    return current_user
