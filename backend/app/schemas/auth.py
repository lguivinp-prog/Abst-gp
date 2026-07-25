from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    role: str = Field(default="readonly")

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    model_config = ConfigDict(extra='forbid')

class UserResponse(UserBase):
    id: int
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str
    
class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    issued_at: Optional[datetime] = None
