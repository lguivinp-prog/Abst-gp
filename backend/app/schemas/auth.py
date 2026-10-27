from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    OPERATOR = "OPERATOR"
    READONLY = "READONLY"


class AssignableRole(str, Enum):
    SUPERVISOR = "SUPERVISOR"
    OPERATOR = "OPERATOR"
    READONLY = "READONLY"


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    role: str = Field(default="readonly")


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    password: str = Field(..., min_length=8)
    role: AssignableRole = Field(default=AssignableRole.OPERATOR)
    tenant_id: Optional[str] = None

    model_config = ConfigDict(extra='forbid')

    @field_validator("role", mode="before")
    @classmethod
    def validate_role_whitelist(cls, v):
        if str(v).upper() == "SUPERADMIN":
            raise ValueError("No esta permitido crear o asignar el rol SUPERADMIN a traves de la API (P14-G02).")
        if str(v).upper() == "ADMIN":
            raise ValueError("No esta permitido crear usuarios con rol ADMIN mediante este esquema. Use delegacion institucional.")
        return v


class SuperadminCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    password: str = Field(..., min_length=12)
    role: str = "SUPERADMIN"

    model_config = ConfigDict(extra='forbid')


class AdminUserUpdate(BaseModel):
    role: Optional[AssignableRole] = None
    is_active: Optional[bool] = None
    must_change_password: Optional[bool] = None
    unlock_account: Optional[bool] = None

    model_config = ConfigDict(extra='forbid')


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    tenant_id: Optional[str] = None
    is_active: bool
    must_change_password: bool
    mfa_status: str = "DISABLED"
    created_at: datetime
    last_login_at: Optional[datetime] = None
    locked_until: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_challenge_token: Optional[str] = None


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    tenant_id: Optional[str] = None
    jti: Optional[str] = None
    session_version: Optional[int] = None
    issued_at: Optional[datetime] = None
    purpose: Optional[str] = None


class MfaSetupRequest(BaseModel):
    current_password: Optional[str] = None
    current_totp_code: Optional[str] = None

    model_config = ConfigDict(extra='forbid')


class MfaSetupResponse(BaseModel):
    secret_base32: str
    provisioning_uri: str
    recovery_codes: List[str]


class MfaVerifyRequest(BaseModel):
    mfa_challenge_token: str
    totp_code: str = Field(..., min_length=6, max_length=6)

    model_config = ConfigDict(extra='forbid')


class MfaReEnrollConfirmRequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=6)

    model_config = ConfigDict(extra='forbid')


class MfaRecoveryRequest(BaseModel):
    username: str
    current_password: str
    recovery_code: str

    model_config = ConfigDict(extra='forbid')


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    totp_code: Optional[str] = None

    model_config = ConfigDict(extra='forbid')
