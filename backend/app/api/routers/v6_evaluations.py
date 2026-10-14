from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile
from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
from app.models.v6.supplier_offer import SupplierOffer
from app.services.v6.quotation_guard import ensure_requirement_review_valid
from app.services.v6.lifecycle_guard import ensure_case_mutable
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
    requirement_description: Optional[str] = None
    requirement_type: Optional[str] = None

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
    # Populate extra fields from relationship
    for ev in evals:
        if ev.requirement:
            ev.requirement_description = ev.requirement.description
            ev.requirement_type = ev.requirement.requirement_type
    return evals

@router.post("/cases/{case_id}/offers/{offer_id}/evaluate", response_model=List[EvaluationResponse])
def evaluate_offer(
    case_id: int,
    offer_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_requirement_review_valid(case)
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
    for ev in evals:
        if ev.requirement:
            ev.requirement_description = ev.requirement.description
            ev.requirement_type = ev.requirement.requirement_type
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

    evals = db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id == offer_id).all()
    for ev in evals:
        if ev.requirement:
            ev.requirement_description = ev.requirement.description
            ev.requirement_type = ev.requirement.requirement_type
    return evals

@router.put("/cases/{case_id}/evaluations/{eval_id}", response_model=EvaluationResponse)
def update_evaluation(
    case_id: int,
    eval_id: int,
    update_data: EvaluationUpdate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    ensure_case_mutable(case)
    ensure_requirement_review_valid(case)
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
    if updated.requirement:
        updated.requirement_description = updated.requirement.description
        updated.requirement_type = updated.requirement.requirement_type
    return updated

class ContractualConditionResponse(BaseModel):
    id: int
    supplier_offer_id: int
    key: Optional[str] = None
    label: Optional[str] = None
    required_value: Optional[str] = None
    offered_value: Optional[str] = None
    final_value: Optional[str] = None
    unit: Optional[str] = None
    resolution_rule: str
    status: str

    class Config:
        from_attributes = True

@router.get("/cases/{case_id}/evaluations/contractual", response_model=List[ContractualConditionResponse])
def get_contractual_evaluations(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.supplier_offer import SupplierOffer
    from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
    from app.services.v6.evaluation.contractual_resolver import ContractualResolver
    from app.models.v6.contractual_condition import ContractualCondition

    offers = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id).all()
    requirements = db.query(CaseRequirementMatrix).filter(CaseRequirementMatrix.case_id == case_id).all()

    resolver = ContractualResolver(db)
    all_conditions = []

    for offer in offers:
        existing = db.query(ContractualCondition).filter_by(supplier_offer_id=offer.id).all()
        
        if case.status in ["APPROVED", "COMPLETED"]:
            all_conditions.extend(existing)
            continue
            
        if existing:
            db.query(ContractualCondition).filter_by(supplier_offer_id=offer.id).delete()
            db.flush()

        conditions = resolver.resolve_offer(offer.id, requirements)
        all_conditions.extend(conditions)

    return all_conditions

class VFMResponse(BaseModel):
    supplier_offer_id: int
    supplier_id: int
    is_eligible: bool
    is_evaluated: Optional[bool] = None
    reason: Optional[str] = None
    total_score: Optional[float] = None
    price: Optional[float] = None
    vfm_ratio: Optional[float] = None

@router.get("/cases/{case_id}/evaluations/vfm", response_model=List[VFMResponse])
def get_vfm_ranking(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.services.v6.evaluation.vfm_service import ValueForMoneyService

    vfm_service = ValueForMoneyService(db)
    results = vfm_service.calculate_vfm(case_id)
    return results
