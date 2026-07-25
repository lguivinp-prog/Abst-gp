from datetime import datetime, timedelta, timezone
from typing import Optional, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.domain import User, CaseFile, AuditLog
from app.schemas.auth import TokenData
import bcrypt
from app.api.exceptions import UnauthorizedException, ForbiddenException, NotFoundException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

SECRET_KEY = settings.SECRET_KEY if hasattr(settings, "SECRET_KEY") else "default_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

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

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    # Track the exact moment the token is issued for revocation checks
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = UnauthorizedException("Could not validate credentials")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        
        # Extract issued at
        iat_timestamp = payload.get("iat")
        if iat_timestamp:
            issued_at = datetime.fromtimestamp(iat_timestamp, tz=timezone.utc)
        else:
            issued_at = None
            
        token_data = TokenData(username=username, role=payload.get("role"), issued_at=issued_at)
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

    # Revocation check: if password was changed after this token was issued
    if user.password_changed_at and token_data.issued_at:
        # Give a small 1-second grace period for clock skew
        if user.password_changed_at > (token_data.issued_at + timedelta(seconds=1)):
            raise UnauthorizedException("Token revoked due to password change")

    return user

def require_role(roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise ForbiddenException("Not enough permissions")
        return current_user
    return role_checker

def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.must_change_password:
        raise ForbiddenException("You must change your password before proceeding.")
    return current_user

def verify_case_access(case_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """
    Dependency to verify a user has access to a specific case file.
    Admin sees all cases within their tenant. Operator only sees assigned cases within their tenant.
    """
    case_query = db.query(CaseFile).filter(
        CaseFile.id == case_id,
        CaseFile.tenant_id == current_user.tenant_id
    )
    
    # Implicitly filter by user if not ADMIN
    if current_user.role != "ADMIN":
        case_query = case_query.filter(CaseFile.assigned_to_user_id == current_user.id)
        
    case = case_query.first()
    
    if not case:
        # Return 404 instead of 403 to prevent IDOR scanning
        raise NotFoundException(f"Case {case_id} not found")
        
    return case
