from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user
from app.models.domain import User
from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()
evaluation_service = OfferEvaluationService()

class EvaluationResponse(BaseModel):
    id: int
    supplier_offer_id: int
    requirement_id: int
    status: str
    explanation: Optional[str] = None
    evaluation_confidence: Optional[float] = None

    class Config:
        from_attributes = True

class EvaluationUpdate(BaseModel):
    status: str
    explanation: str

@router.post("/offers/{offer_id}/evaluate", response_model=List[EvaluationResponse])
def evaluate_offer(
    offer_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    evals = evaluation_service.evaluate_offer(
        db=db,
        supplier_offer_id=offer_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )
    return evals

@router.get("/offers/{offer_id}/evaluation", response_model=List[EvaluationResponse])
def get_evaluation(
    offer_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.offer_evaluation import OfferEvaluation
    return db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id == offer_id).all()

@router.put("/evaluations/{eval_id}", response_model=EvaluationResponse)
def update_evaluation(
    eval_id: int,
    update_data: EvaluationUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    updated = evaluation_service.update_evaluation(
        db=db,
        eval_id=eval_id,
        new_status=update_data.status,
        explanation=update_data.explanation,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return updated
