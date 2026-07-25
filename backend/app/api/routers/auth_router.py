from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone

from app.core.database import get_db
from app.models.domain import User
from app.api.auth import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.schemas.auth import Token
from app.api.exceptions import UnauthorizedException

router = APIRouter()

@router.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).with_for_update().first()
    
    if not user:
        raise UnauthorizedException("Incorrect username or password")
        
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise UnauthorizedException("Account locked")
        
    if not verify_password(form_data.password, user.password_hash):
        # Increment failed login count
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()
        raise UnauthorizedException("Incorrect username or password")
        
    if not user.is_active:
        raise UnauthorizedException("Inactive user")

    # Reset failed login count
    user.failed_login_count = 0
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
