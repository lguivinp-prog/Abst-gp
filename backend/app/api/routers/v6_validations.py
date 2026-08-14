from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user
from app.models.domain import User
from app.services.v6.integrations.validation_service import ValidationService
from app.models.v6.validation_request import ValidationRequest
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

router = APIRouter()

class ValidationRequestCreate(BaseModel):
    source: str # SUNAT, RNP, FUP, CIIU

class ValidationRequestResponse(BaseModel):
    id: int
    supplier_id: int
    source: str
    status: str
    requested_at: datetime
    completed_at: Optional[datetime] = None
    response_payload: Optional[Any] = None

    class Config:
        from_attributes = True

@router.post("/suppliers/{supplier_id}/validation-requests", response_model=ValidationRequestResponse)
def create_validation_request(
    supplier_id: int,
    req: ValidationRequestCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Enqueue to background worker (simulated)
    return ValidationService.request_validation(
        db=db,
        supplier_id=supplier_id,
        source=req.source,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )

@router.get("/validation-requests/{req_id}", response_model=ValidationRequestResponse)
def get_validation_request(
    req_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    val_req = db.query(ValidationRequest).filter(ValidationRequest.id == req_id).first()
    if not val_req:
        raise HTTPException(status_code=404, detail="Validation request not found")
    # RBAC check omitted for brevity in Sprint 3 mock
    return val_req
