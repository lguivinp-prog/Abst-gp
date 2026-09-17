from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile
from app.services.v6.integrations.validation_service import ValidationService
from app.models.v6.validation_request import ValidationRequest
from app.models.v6.supplier_offer import SupplierOffer
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

router = APIRouter()

from enum import Enum

class ValidationRequestCreate(BaseModel):
    source: str # SUNAT, RNP, FUP, CIIU

class ManualValidationResult(str, Enum):
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"

class ValidationManualCreate(BaseModel):
    source: str
    result: ManualValidationResult
    observation: str
    evidence_reference: Optional[str] = None

class SupplierBasic(BaseModel):
    id: int
    ruc: str
    business_name: str

    class Config:
        from_attributes = True

class UserBasic(BaseModel):
    id: int
    username: Optional[str] = None
    full_name: Optional[str] = None

    class Config:
        from_attributes = True

class ValidationRequestResponse(BaseModel):
    id: int
    supplier_id: int
    source: str
    status: str
    requested_at: datetime
    completed_at: Optional[datetime] = None
    response_payload: Optional[Any] = None
    supplier: Optional[SupplierBasic] = None
    validation_mode: str
    manual_result: Optional[str] = None
    manual_observation: Optional[str] = None
    manual_evidence_reference: Optional[str] = None
    verified_by_user_id: Optional[int] = None
    verified_at: Optional[datetime] = None
    verified_by_user: Optional[UserBasic] = None

    class Config:
        from_attributes = True

@router.get("/cases/{case_id}/validations", response_model=List[ValidationRequestResponse])
def get_case_validations(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Get all suppliers linked to the case
    offers = db.query(SupplierOffer).filter(SupplierOffer.case_id == case_id).all()
    supplier_ids = [offer.supplier_id for offer in offers]

    if not supplier_ids:
        return []

    validations = db.query(ValidationRequest).filter(
        ValidationRequest.supplier_id.in_(supplier_ids),
        ValidationRequest.case_id == case_id
    ).all()

    return validations

@router.post("/cases/{case_id}/suppliers/{supplier_id}/validations")
def create_case_validation_request(
    case_id: int,
    supplier_id: int,
    req: ValidationRequestCreate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Verify supplier is linked to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.case_id == case_id,
        SupplierOffer.supplier_id == supplier_id
    ).first()

    if not offer:
        raise HTTPException(status_code=400, detail="Supplier is not linked to this case")

    if req.source == "ALL":
        from app.services.v6.integrations.validation_orchestrator import SupplierValidationOrchestrator
        orchestrator = SupplierValidationOrchestrator()
        orchestrator.run_async_validation(db, case_id, supplier_id, current_user.id)
        # Return the latest created for this supplier to satisfy any client expecting an object
        val = db.query(ValidationRequest).filter_by(supplier_id=supplier_id).order_by(ValidationRequest.id.desc()).first()
        return val

    return ValidationService.request_validation(
        db=db,
        case_id=case_id,
        supplier_id=supplier_id,
        source=req.source,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id
    )

@router.post("/cases/{case_id}/suppliers/{supplier_id}/validations/manual", response_model=ValidationRequestResponse)
def create_manual_validation(
    case_id: int,
    supplier_id: int,
    req: ValidationManualCreate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Verify supplier is linked to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.case_id == case_id,
        SupplierOffer.supplier_id == supplier_id
    ).first()

    if not offer:
        raise HTTPException(status_code=400, detail="Supplier is not linked to this case")

    if req.source not in ["SUNAT", "RNP", "FUP", "CIIU"]:
        raise HTTPException(status_code=422, detail="Invalid source")

    if not req.observation or not req.observation.strip():
        raise HTTPException(status_code=422, detail="Observation is required")

    status_map = {
        "VALIDATED": "PASSED",
        "REJECTED": "ERROR",
        "REVIEW_REQUIRED": "WARNING"
    }

    from sqlalchemy.sql import func

    val_req = ValidationRequest(
        supplier_id=supplier_id,
        case_id=case_id,
        source=req.source,
        status=status_map.get(req.result.value, "PENDING"),
        requested_by=current_user.id,
        requested_at=func.now(),
        completed_at=func.now(),
        validation_mode="MANUAL",
        manual_result=req.result.value,
        manual_observation=req.observation,
        manual_evidence_reference=req.evidence_reference,
        verified_by_user_id=current_user.id,
        verified_at=func.now(),
        response_payload={"manual_verification": True, "observation": req.observation}
    )

    db.add(val_req)
    db.commit()
    db.refresh(val_req)
    return val_req

@router.get("/cases/{case_id}/validations/{req_id}", response_model=ValidationRequestResponse)
def get_case_validation_request(
    case_id: int,
    req_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    val_req = db.query(ValidationRequest).filter(ValidationRequest.id == req_id).first()
    if not val_req:
        raise HTTPException(status_code=404, detail="Validation request not found")

    # Verify supplier is linked to case
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.case_id == case_id,
        SupplierOffer.supplier_id == val_req.supplier_id
    ).first()

    if not offer:
        raise HTTPException(status_code=403, detail="Validation does not belong to this case")

    return val_req
