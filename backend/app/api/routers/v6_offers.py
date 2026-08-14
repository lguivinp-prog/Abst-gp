from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile
from app.services.v6.supplier_offer_service import SupplierOfferService
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class SupplierOfferCreate(BaseModel):
    supplier_id: int
    price: Optional[float] = None
    source_document: Optional[str] = None

class SupplierOfferResponse(BaseModel):
    id: int
    case_id: int
    supplier_id: int
    status: str
    price: Optional[float] = None
    
    class Config:
        from_attributes = True

@router.post("/cases/{case_id}/offers", response_model=SupplierOfferResponse)
def attach_offer(
    case_id: int,
    item: SupplierOfferCreate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return SupplierOfferService.attach_offer(
        db=db,
        case_id=case_id,
        supplier_id=item.supplier_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        data=item.model_dump()
    )
