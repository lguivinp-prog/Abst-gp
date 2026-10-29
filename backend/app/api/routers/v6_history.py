from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile, AuditLog
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier import Supplier
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.case_procurement_item import CaseProcurementItem
from app.models.v6.validation_request import ValidationRequest
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal
from app.models.v6.generated_output import GeneratedOutput
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter()

class AuditLogResponse(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: str
    details: Optional[str] = None
    status: Optional[str] = None
    created_at: datetime
    user_id: Optional[int] = None

    class Config:
        from_attributes = True

@router.get("/cases/{case_id}/history", response_model=List[AuditLogResponse])
def get_case_history(
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    case_id = case.id
    tenant_id = current_user.tenant_id

    # 1. Gather all strictly verified database entity IDs associated with this case
    req_ids = [str(r[0]) for r in db.query(CaseRequirementMatrix.id).filter(CaseRequirementMatrix.case_id == case_id).all()]

    offer_rows = db.query(SupplierOffer.id, SupplierOffer.supplier_id).filter(SupplierOffer.case_id == case_id).all()
    offer_ids = [str(r[0]) for r in offer_rows]
    supplier_ids = [str(r[1]) for r in offer_rows if r[1] is not None]

    eval_ids = []
    if offer_ids:
        eval_ids = [str(e[0]) for e in db.query(OfferEvaluation.id).filter(OfferEvaluation.supplier_offer_id.in_([int(oid) for oid in offer_ids])).all()]

    item_ids = [str(i[0]) for i in db.query(CaseProcurementItem.id).filter(CaseProcurementItem.case_id == case_id).all()]
    val_ids = [str(v[0]) for v in db.query(ValidationRequest.id).filter(ValidationRequest.case_id == case_id).all()]
    attempt_ids = [str(a[0]) for a in db.query(SupplierSelectionAttempt.id).filter(SupplierSelectionAttempt.case_id == case_id).all()]
    final_ids = [str(f[0]) for f in db.query(SupplierSelectionFinal.id).filter(SupplierSelectionFinal.case_id == case_id).all()]
    output_ids = [str(o[0]) for o in db.query(GeneratedOutput.id).filter(GeneratedOutput.case_id == case_id).all()]

    # 2. Build verified criteria: match tenant AND related entity types with their exact IDs
    or_clauses = [
        and_(AuditLog.entity_type == "CaseFile", AuditLog.entity_id == str(case_id)),
        and_(AuditLog.entity_type == "GeneratedOutput", AuditLog.entity_id == str(case_id))
    ]
    if req_ids:
        or_clauses.append(and_(AuditLog.entity_type == "CaseRequirementMatrix", AuditLog.entity_id.in_(req_ids)))
    if offer_ids:
        or_clauses.append(and_(AuditLog.entity_type == "SupplierOffer", AuditLog.entity_id.in_(offer_ids)))
    if supplier_ids:
        or_clauses.append(
            and_(
                AuditLog.entity_type == "Supplier",
                AuditLog.entity_id.in_(supplier_ids),
                AuditLog.details.like(f"Expediente {case_id}:%")
            )
        )
    if eval_ids:
        or_clauses.append(and_(AuditLog.entity_type == "OfferEvaluation", AuditLog.entity_id.in_(eval_ids)))
    item_conditions = [AuditLog.details.like(f"Expediente {case_id}:%")]
    if item_ids:
        item_conditions.append(AuditLog.entity_id.in_(item_ids))
    or_clauses.append(
        and_(
            AuditLog.entity_type == "CaseProcurementItem",
            or_(*item_conditions)
        )
    )
    if val_ids:
        or_clauses.append(and_(AuditLog.entity_type == "ValidationRequest", AuditLog.entity_id.in_(val_ids)))
    if attempt_ids:
        or_clauses.append(and_(AuditLog.entity_type == "SupplierSelectionAttempt", AuditLog.entity_id.in_(attempt_ids)))
    if final_ids:
        or_clauses.append(and_(AuditLog.entity_type == "SupplierSelectionFinal", AuditLog.entity_id.in_(final_ids)))
    if output_ids:
        or_clauses.append(and_(AuditLog.entity_type == "GeneratedOutput", AuditLog.entity_id.in_(output_ids)))

    logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.tenant_id == tenant_id,
            or_(*or_clauses)
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .all()
    )

    return logs
