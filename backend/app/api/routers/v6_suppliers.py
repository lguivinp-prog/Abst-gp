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

from app.api.auth import verify_case_access
from app.models.domain import CaseFile
from app.services.v6.lifecycle_guard import ensure_case_mutable
from typing import List

class CaseSupplierResponse(BaseModel):
    id: int
    ruc: str
    business_name: str
    legal_representative: Optional[str] = None
    dni: Optional[str] = None
    contact_email: Optional[str] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True

@router.get("/cases/{case_id}/suppliers", response_model=List[CaseSupplierResponse])
def get_case_suppliers(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_offer import SupplierOffer
    from app.models.v6.supplier import Supplier

    offers = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id).all()
    result = []
    for offer in offers:
        sup = offer.supplier
        result.append({
            "id": sup.id,
            "ruc": sup.ruc,
            "business_name": sup.business_name,
            "legal_representative": sup.legal_representative,
            "dni": sup.dni,
            "contact_email": sup.contact_email,
            "status": offer.status
        })
    return result

@router.post("/cases/{case_id}/suppliers", response_model=CaseSupplierResponse)
def link_case_supplier(
    case_id: int,
    item: SupplierCreate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_offer import SupplierOffer
    from app.models.v6.supplier import Supplier
    from app.services.v6.quotation_guard import ensure_requirement_review_valid

    ensure_case_mutable(case)
    ensure_requirement_review_valid(case)

    supplier = db.query(Supplier).filter(
        Supplier.tenant_id == current_user.tenant_id,
        Supplier.ruc == item.ruc
    ).first()

    if not supplier:
        supplier = SupplierService.create_supplier(
            db=db, user_id=current_user.id, tenant_id=current_user.tenant_id, data=item.model_dump()
        )
    else:
        if item.business_name: supplier.business_name = item.business_name
        if item.legal_representative: supplier.legal_representative = item.legal_representative
        if item.dni: supplier.dni = item.dni
        if item.contact_email: supplier.contact_email = item.contact_email
        db.commit()
        db.refresh(supplier)

    offer = db.query(SupplierOffer).filter(
        SupplierOffer.case_id == case_id,
        SupplierOffer.supplier_id == supplier.id
    ).first()

    if not offer:
        offer = SupplierOffer(
            case_id=case_id,
            supplier_id=supplier.id,
            status="PENDING"
        )
        db.add(offer)
        db.commit()
        db.refresh(offer)

    return {
        "id": supplier.id,
        "ruc": supplier.ruc,
        "business_name": supplier.business_name,
        "legal_representative": supplier.legal_representative,
        "dni": supplier.dni,
        "contact_email": supplier.contact_email,
        "status": offer.status
    }

@router.delete("/cases/{case_id}/suppliers/{supplier_id}")
def unlink_case_supplier(
    case_id: int,
    supplier_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_offer import SupplierOffer

    from app.services.v6.quotation_guard import ensure_requirement_review_valid

    ensure_case_mutable(case)
    ensure_requirement_review_valid(case)

    offer = db.query(SupplierOffer).filter(
        SupplierOffer.case_id == case_id,
        SupplierOffer.supplier_id == supplier_id
    ).first()

    if not offer:
        raise HTTPException(status_code=404, detail="Supplier not linked to case")

    db.delete(offer)
    db.commit()

    return {"message": "Supplier unlinked from case"}

