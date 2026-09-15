from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile
from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
from app.models.v6.supplier_offer import SupplierOffer
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

@router.get("/cases/{case_id}/evaluations", response_model=List[EvaluationResponse])
def get_case_evaluations(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.offer_evaluation import OfferEvaluation
    # Get all offers for the case
    offers = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id).all()
    offer_ids = [offer.id for offer in offers]

    if not offer_ids:
        return []

    evals = db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id.in_(offer_ids)).all()
    return evals

@router.post("/cases/{case_id}/offers/{offer_id}/evaluate", response_model=List[EvaluationResponse])
def evaluate_offer(
    case_id: int,
    offer_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Verify offer belongs to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.id == offer_id,
        SupplierOffer.case_id == case_id
    ).first()

    if not offer:
        raise HTTPException(status_code=403, detail="Offer does not belong to this case")

    # Check if offer is actually an offer (has a price or document)
    if offer.status == "PENDING" and offer.price is None and offer.source_document is None:
        raise HTTPException(status_code=400, detail="Cannot evaluate incomplete offer")

    # Delete existing evaluations for this offer to allow re-evaluation
    from app.models.v6.offer_evaluation import OfferEvaluation
    db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id == offer_id).delete()
    db.commit()

    evals = evaluation_service.evaluate_offer(
        db=db,
        supplier_offer_id=offer_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )
    return evals

@router.get("/cases/{case_id}/offers/{offer_id}/evaluations", response_model=List[EvaluationResponse])
def get_offer_evaluations(
    case_id: int,
    offer_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.offer_evaluation import OfferEvaluation
    # Verify offer belongs to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.id == offer_id,
        SupplierOffer.case_id == case_id
    ).first()

    if not offer:
        raise HTTPException(status_code=403, detail="Offer does not belong to this case")

    return db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id == offer_id).all()

@router.put("/cases/{case_id}/evaluations/{eval_id}", response_model=EvaluationResponse)
def update_evaluation(
    case_id: int,
    eval_id: int,
    update_data: EvaluationUpdate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.offer_evaluation import OfferEvaluation
    eval_entry = db.query(OfferEvaluation).filter(OfferEvaluation.id == eval_id).first()
    if not eval_entry:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Verify it belongs to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.id == eval_entry.supplier_offer_id,
        SupplierOffer.case_id == case_id
    ).first()

    if not offer:
        raise HTTPException(status_code=403, detail="Evaluation does not belong to this case")

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
