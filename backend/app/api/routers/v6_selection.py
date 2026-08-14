from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user
from app.models.domain import User
from app.services.v6.selection.selection_service import SelectionService
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class SelectionRequest(BaseModel):
    supplier_offer_id: int
    justification_comment: Optional[str] = None

class SelectionResponse(BaseModel):
    case_id: int
    status: str

@router.post("/cases/{case_id}/selection", response_model=SelectionResponse)
def propose_selection(
    case_id: int,
    req: SelectionRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        SelectionService.propose_selection(
            db=db,
            case_id=case_id,
            supplier_offer_id=req.supplier_offer_id,
            justification=req.justification_comment,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id
        )
        return {"case_id": case_id, "status": "UNDER_REVIEW"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/cases/{case_id}/approve", response_model=SelectionResponse)
def approve_selection(
    case_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # In a real app, verify current_user has Supervisor role
    try:
        SelectionService.approve_selection(
            db=db,
            case_id=case_id,
            supervisor_id=current_user.id,
            tenant_id=current_user.tenant_id
        )
        return {"case_id": case_id, "status": "APPROVED"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
