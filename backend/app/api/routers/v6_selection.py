from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile
from app.services.v6.selection.selection_service import SelectionService
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal
from app.models.v6.supplier_offer import SupplierOffer
from app.services.v6.quotation_guard import ensure_requirement_review_valid
from app.services.v6.lifecycle_guard import ensure_case_mutable
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter()

class SelectionRequest(BaseModel):
    supplier_offer_id: int
    justification_comment: Optional[str] = None

class SelectionResponse(BaseModel):
    case_id: int
    status: str
    supplier_offer_id: Optional[int] = None
    justification_comment: Optional[str] = None
    selected_by: Optional[int] = None

class ResultResponse(BaseModel):
    case_id: int
    attempt_id: int
    created_at: datetime
    supplier_name: Optional[str] = None
    supplier_ruc: Optional[str] = None
    offer_total_amount: Optional[float] = None
    offer_currency: Optional[str] = None
    justification_comment: Optional[str] = None
    status: str = "APPROVED"

@router.post("/cases/{case_id}/selection", response_model=SelectionResponse)
def propose_selection(
    req: SelectionRequest,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_requirement_review_valid(case)
    try:
        SelectionService.propose_selection(
            db=db,
            case_id=case.id,
            supplier_offer_id=req.supplier_offer_id,
            justification=req.justification_comment,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            user_role=current_user.role
        )
        return {"case_id": case.id, "status": "UNDER_REVIEW"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cases/{case_id}/selection", response_model=Optional[SelectionResponse])
def get_selection(
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Get the latest selection attempt
    attempt = db.query(SupplierSelectionAttempt).filter_by(case_id=case.id).order_by(SupplierSelectionAttempt.id.desc()).first()
    if not attempt:
        return None
    
    return {
        "case_id": attempt.case_id,
        "status": attempt.status,
        "supplier_offer_id": attempt.supplier_offer_id,
        "justification_comment": attempt.justification_comment,
        "selected_by": attempt.selected_by
    }

@router.post("/cases/{case_id}/approve", response_model=SelectionResponse)
def approve_selection(
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_requirement_review_valid(case)
    if current_user.role not in ["ADMIN", "SUPERVISOR"]:
        raise HTTPException(status_code=403, detail="Supervisor role required to approve")

    try:
        SelectionService.approve_selection(
            db=db,
            case_id=case.id,
            supervisor_id=current_user.id,
            tenant_id=current_user.tenant_id
        )
        return {"case_id": case.id, "status": "APPROVED"}
    except ValueError as e:
        if "terminal" in str(e).lower() or "finalized" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/cases/{case_id}/result", response_model=Optional[ResultResponse])
def get_result(
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    final = db.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()
    if not final:
        return None
    
    # Eager load attempt and offer to avoid N+1 and detached session issues
    attempt = db.query(SupplierSelectionAttempt).filter_by(id=final.attempt_id).first()
    offer = None
    supplier = None
    if attempt:
        offer = db.query(SupplierOffer).filter_by(id=attempt.supplier_offer_id).first()
        if offer:
            from app.models.v6.supplier import Supplier
            supplier = db.query(Supplier).filter_by(id=offer.supplier_id).first()

    return {
        "case_id": final.case_id,
        "attempt_id": final.attempt_id,
        "created_at": final.created_at,
        "supplier_name": supplier.business_name if supplier else None,
        "supplier_ruc": supplier.ruc if supplier else None,
        "offer_total_amount": offer.total_amount if offer else None,
        "offer_currency": getattr(offer, "currency", "PEN") if offer else None,
        "justification_comment": attempt.justification_comment if attempt else None,
        "status": "APPROVED"
    }
