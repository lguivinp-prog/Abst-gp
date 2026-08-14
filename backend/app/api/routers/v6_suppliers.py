from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user
from app.models.domain import User
from app.services.v6.supplier_service import SupplierService
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class SupplierCreate(BaseModel):
    ruc: str
    business_name: str
    legal_representative: Optional[str] = None
    dni: Optional[str] = None
    contact_email: Optional[str] = None

class SupplierResponse(BaseModel):
    id: int
    tenant_id: str
    ruc: str
    business_name: str
    
    class Config:
        from_attributes = True

@router.post("/suppliers", response_model=SupplierResponse)
def create_supplier(
    item: SupplierCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return SupplierService.create_supplier(
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        data=item.model_dump()
    )

@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
def get_supplier(
    supplier_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    supplier = SupplierService.get_supplier(db, supplier_id, current_user.tenant_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier

@router.get("/suppliers/{supplier_id}/profile")
def get_supplier_profile(
    supplier_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_profile import SupplierProfile
    
    supplier = SupplierService.get_supplier(db, supplier_id, current_user.tenant_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
        
    profile = db.query(SupplierProfile).filter(SupplierProfile.supplier_id == supplier_id).first()
    
    return {
        "id": supplier.id,
        "ruc": supplier.ruc,
        "business_name": supplier.business_name,
        "profile": {
            "address": profile.address if profile else None,
            "aggregated_score": profile.aggregated_score if profile else None,
            "status_summary": profile.status_summary if profile else "PENDING_VERIFICATION"
        }
    }
