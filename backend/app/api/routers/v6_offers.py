from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile
from app.services.v6.supplier_offer_service import SupplierOfferService
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from typing import List, Optional
from decimal import Decimal, ROUND_HALF_UP

class SupplierOfferItemCreate(BaseModel):
    procurement_item_id: int
    unit_price: Decimal

class SupplierOfferItemResponse(BaseModel):
    id: int
    procurement_item_id: int
    description: Optional[str] = None
    quantity: float
    unit: str
    unit_price: Decimal
    subtotal: Decimal

    class Config:
        from_attributes = True

class SupplierOfferCreate(BaseModel):
    supplier_id: int
    price: Optional[float] = None
    currency: Optional[str] = "PEN"
    source_document: Optional[str] = None
    document_ids: Optional[List[int]] = None
    items: Optional[List[SupplierOfferItemCreate]] = None

class SupplierBasic(BaseModel):
    id: int
    ruc: str
    business_name: str

    class Config:
        from_attributes = True

class SupplierOfferResponse(BaseModel):
    id: int
    case_id: int
    supplier_id: int
    status: str
    evaluation_status: str
    price: Optional[float] = None
    currency: Optional[str] = "PEN"
    source_document: Optional[str] = None
    documents: List[dict] = []
    supplier: Optional[SupplierBasic] = None
    items: List[SupplierOfferItemResponse] = []
    total_amount: Optional[Decimal] = None

    class Config:
        from_attributes = True

class SupplierOfferUpdate(BaseModel):
    price: Optional[float] = None
    currency: Optional[str] = None
    source_document: Optional[str] = None
    document_ids: Optional[List[int]] = None
    status: Optional[str] = None
    items: Optional[List[SupplierOfferItemCreate]] = None

@router.post("/cases/{case_id}/offers", response_model=SupplierOfferResponse)
def attach_offer(
    case_id: int,
    item: SupplierOfferCreate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier import Supplier

    # Validar supplier existe y pertenece al tenant
    supplier = db.query(Supplier).filter(
        Supplier.id == item.supplier_id,
        Supplier.tenant_id == current_user.tenant_id
    ).first()

    if not supplier:
        raise HTTPException(status_code=400, detail="Supplier not found or not accessible")

    return SupplierOfferService.attach_offer(
        db=db,
        case_id=case_id,
        supplier_id=item.supplier_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        data=item.model_dump()
    )

@router.get("/cases/{case_id}/offers", response_model=List[SupplierOfferResponse])
def get_offers(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_offer import SupplierOffer
    offers = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id).all()
    return offers

@router.get("/cases/{case_id}/offers/{offer_id}", response_model=SupplierOfferResponse)
def get_offer(
    case_id: int,
    offer_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_offer import SupplierOffer
    offer = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id, SupplierOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    return offer

@router.put("/cases/{case_id}/offers/{offer_id}", response_model=SupplierOfferResponse)
def update_offer(
    case_id: int,
    offer_id: int,
    item: SupplierOfferUpdate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_offer import SupplierOffer
    offer = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id, SupplierOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    if item.price is not None:
        offer.price = item.price
    if item.currency is not None:
        offer.currency = item.currency
    if item.source_document is not None:
        offer.source_document = item.source_document
    if item.status is not None:
        offer.status = item.status
    if item.document_ids is not None:
        from app.models.v6.supplier_offer import SupplierOfferDocument
        # Remove old docs
        db.query(SupplierOfferDocument).filter(SupplierOfferDocument.offer_id == offer_id).delete()
        # Add new docs
        for doc_id in item.document_ids:
            offer_doc = SupplierOfferDocument(offer_id=offer.id, document_id=doc_id)
            db.add(offer_doc)

    if item.items is not None:
        from app.models.v6.supplier_offer_item import SupplierOfferItem
        from app.models.v6.case_procurement_item import CaseProcurementItem

        # Remove old items to replace them
        db.query(SupplierOfferItem).filter(SupplierOfferItem.supplier_offer_id == offer_id).delete()

        total_amount = Decimal('0.00')

        for item_data in item.items:
            if item_data.unit_price is None or item_data.unit_price < 0:
                raise HTTPException(status_code=400, detail="Invalid unit price")

            procurement_item = db.query(CaseProcurementItem).filter_by(id=item_data.procurement_item_id).first()
            if not procurement_item or procurement_item.case_id != case_id:
                raise HTTPException(status_code=403, detail=f"Procurement item {item_data.procurement_item_id} is invalid or does not belong to the case")

            qty = Decimal(str(procurement_item.quantity)) if procurement_item.quantity is not None else Decimal('0')
            u_price = item_data.unit_price

            # Subtotal calculation
            subtotal = (qty * u_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            total_amount += subtotal

            offer_item = SupplierOfferItem(
                supplier_offer_id=offer.id,
                procurement_item_id=procurement_item.id,
                description=procurement_item.description,
                quantity=procurement_item.quantity,
                unit=procurement_item.unit,
                unit_price=u_price
            )
            db.add(offer_item)

        offer.total_amount = total_amount

    db.commit()
    db.refresh(offer)
    return offer

@router.delete("/cases/{case_id}/offers/{offer_id}")
def delete_offer(
    case_id: int,
    offer_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_offer import SupplierOffer
    offer = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id, SupplierOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    db.delete(offer)
    db.commit()
    return {"message": "Offer deleted"}
