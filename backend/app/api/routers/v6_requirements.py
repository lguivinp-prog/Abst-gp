from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile, AuditLog, UploadedDocument
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.services.v6.extraction.service import RequirementExtractionService
from pydantic import BaseModel
from typing import List, Optional
import json
from datetime import datetime, timezone
from sqlalchemy.orm import selectinload
from app.services.v6.extraction.requirement_classifier import classify_requirement

router = APIRouter()
extraction_service = RequirementExtractionService()

class ExtractionRequest(BaseModel):
    document_id: int # El PDF fuente

class EvidenceResponse(BaseModel):
    id: int
    source_document: str
    source_page: Optional[int] = None
    source_fragment: str
    confidence: float

    class Config:
        from_attributes = True

class RequirementResponse(BaseModel):
    id: int
    case_id: int
    requirement_type: str
    key: Optional[str] = None
    description: str
    value: Optional[str] = None
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    comparator: Optional[str] = None
    mandatory: bool
    status: str
    source_document_id: Optional[int] = None
    evidences: List[EvidenceResponse] = []
    is_manual_edit: Optional[bool] = False

    category: Optional[str] = None
    phase: Optional[str] = None
    procurement_item_id: Optional[int] = None
    flows_to_contract: bool = False
    source_section: Optional[str] = None

    class Config:
        from_attributes = True

class RequirementUpdate(BaseModel):
    status: str # VALIDATED, MODIFIED_BY_USER, OBSERVED, REJECTED
    description: Optional[str] = None
    value: Optional[str] = None
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    comparator: Optional[str] = None
    reason: str

    category: Optional[str] = None
    phase: Optional[str] = None
    procurement_item_id: Optional[int] = None
    flows_to_contract: Optional[bool] = None
    source_section: Optional[str] = None

class RequirementCreate(BaseModel):
    requirement_type: str
    description: str
    mandatory: bool = True
    value: Optional[str] = None
    category: Optional[str] = None
    phase: Optional[str] = None

from app.api.auth import get_current_active_user, verify_case_access, require_role

@router.post("/cases/{case_id}/requirements/extract", response_model=List[RequirementResponse])
def extract_requirements(
    case_id: int,
    req: ExtractionRequest,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: Session = Depends(get_db)
):
    doc = db.query(UploadedDocument).filter(UploadedDocument.id == req.document_id, UploadedDocument.case_id == case_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.text_extracted or not doc.text_extracted.strip():
        raise HTTPException(status_code=422, detail="Document text not yet extracted or empty")

    # Idempotency check
    existing_reqs = db.query(CaseRequirementMatrix).filter(
        CaseRequirementMatrix.case_id == case_id,
        CaseRequirementMatrix.source_document_id == req.document_id
    ).all()

    from app.models.v6.case_procurement_item import CaseProcurementItem
    existing_items = db.query(CaseProcurementItem).filter(
        CaseProcurementItem.case_id == case_id,
        CaseProcurementItem.source_document_id == req.document_id
    ).all()

    if existing_reqs and existing_items:
        return existing_reqs

    if existing_reqs and not existing_items:
        # We only need to process items
        extraction_service.process_text_and_propose(
            db=db,
            case_id=case_id,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            text=doc.text_extracted,
            document_name=doc.original_filename,
            document_id=doc.id,
            skip_requirements=True
        )
        return existing_reqs

    return extraction_service.process_text_and_propose(
        db=db,
        case_id=case_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        text=doc.text_extracted,
        document_name=doc.original_filename,
        document_id=doc.id
    )

@router.get("/cases/{case_id}/requirements", response_model=List[RequirementResponse])
def get_requirements(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    return db.query(CaseRequirementMatrix).filter(CaseRequirementMatrix.case_id == case_id).all()

@router.post("/cases/{case_id}/requirements", response_model=RequirementResponse)
def create_requirement(
    case_id: int,
    req_data: RequirementCreate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.v6.case_procurement_item import CaseProcurementItem, CaseProcurementItemSpecification
    procurement_items = db.query(CaseProcurementItem).filter(CaseProcurementItem.case_id == case_id).all()
    specifications = db.query(CaseProcurementItemSpecification).join(CaseProcurementItem).filter(CaseProcurementItem.case_id == case_id).all()

    candidate_text = req_data.value if req_data.value else req_data.description

    # Always classify using the deterministic logic
    classification = classify_requirement(candidate_text, procurement_items, specifications)

    req = CaseRequirementMatrix(
        case_id=case_id,
        requirement_type=req_data.requirement_type,
        description=req_data.description,
        mandatory=req_data.mandatory,
        value=req_data.value,
        status="PENDING_REVIEW" if classification.get("status") != "REVIEW_REQUIRED" else "REVIEW_REQUIRED",
        category=classification.get("category"),
        phase=classification.get("phase"),
        procurement_item_id=classification.get("procurement_item_id"),
        flows_to_contract=classification.get("flows_to_contract", True)
    )
    db.add(req)

    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="CREATE_REQUIREMENT",
        entity_type="CaseRequirementMatrix",
        entity_id="", # will update after flush
        details=json.dumps({"description": req_data.description}),
        status="SUCCESS"
    )
    db.add(audit)
    db.flush()
    audit.entity_id = str(req.id)
    db.commit()
    db.refresh(req)

    return req

@router.put("/cases/{case_id}/requirements/{req_id}", response_model=RequirementResponse)
def update_requirement(
    case_id: int,
    req_id: int,
    update_data: RequirementUpdate,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    req = db.query(CaseRequirementMatrix).filter(
        CaseRequirementMatrix.id == req_id,
        CaseRequirementMatrix.case_id == case_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    old_status = req.status

    if update_data.status not in ["VALIDATED", "MODIFIED_BY_USER", "OBSERVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    req.status = update_data.status
    req.is_manual_edit = True
    if update_data.description:
        req.description = update_data.description
    if update_data.value is not None:
        req.value = update_data.value
    if update_data.numeric_value is not None:
        req.numeric_value = update_data.numeric_value
    if update_data.unit is not None:
        req.unit = update_data.unit
    if update_data.comparator is not None:
        req.comparator = update_data.comparator

    if update_data.category is not None:
        req.category = update_data.category
    if update_data.phase is not None:
        req.phase = update_data.phase
    if update_data.procurement_item_id is not None:
        req.procurement_item_id = update_data.procurement_item_id
    if update_data.flows_to_contract is not None:
        req.flows_to_contract = update_data.flows_to_contract
    if update_data.source_section is not None:
        req.source_section = update_data.source_section


    req.validated_by = current_user.id
    req.validated_at = datetime.now(timezone.utc)

    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="UPDATE_REQUIREMENT",
        entity_type="CaseRequirementMatrix",
        entity_id=str(req.id),
        details=json.dumps({
            "old_value": old_status,
            "new_value": req.status,
            "reason": update_data.reason,
            "user": current_user.id,
            "timestamp": req.validated_at.isoformat()
        }),
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    db.refresh(req)

    return req

class ProcurementItemSpecificationResponse(BaseModel):
    id: int
    name: str
    normalized_name: Optional[str] = None
    value: str
    mandatory: bool = True
    source_page: Optional[int] = None
    confidence: Optional[float] = None

    class Config:
        from_attributes = True

class ProcurementItemResponse(BaseModel):
    id: int
    case_id: int
    item_number: Optional[str] = None
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    status: str
    source_document_id: Optional[int] = None
    source_page: Optional[int] = None
    source_requirement_id: Optional[int] = None
    confidence: Optional[float] = None
    specifications: List[ProcurementItemSpecificationResponse] = []

    class Config:
        from_attributes = True

@router.get("/cases/{case_id}/procurement-items", response_model=List[ProcurementItemResponse])
def get_procurement_items(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    from app.models.v6.case_procurement_item import CaseProcurementItem
    return db.query(CaseProcurementItem).options(selectinload(CaseProcurementItem.specifications)).filter(CaseProcurementItem.case_id == case_id).all()

class ProcurementItemCreate(BaseModel):
    item_number: Optional[str] = None
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    status: Optional[str] = "VALIDATED"

@router.post("/cases/{case_id}/procurement-items", response_model=ProcurementItemResponse)
def create_procurement_item(
    case_id: int,
    item_data: ProcurementItemCreate,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    from app.models.v6.case_procurement_item import CaseProcurementItem
    item = CaseProcurementItem(
        case_id=case_id,
        item_number=item_data.item_number,
        description=item_data.description,
        quantity=item_data.quantity,
        unit=item_data.unit,
        status=item_data.status,
        is_manual_edit=True
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@router.put("/cases/{case_id}/procurement-items/{item_id}", response_model=ProcurementItemResponse)
def update_procurement_item(
    case_id: int,
    item_id: int,
    item_data: ProcurementItemCreate,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    from app.models.v6.case_procurement_item import CaseProcurementItem
    item = db.query(CaseProcurementItem).filter(
        CaseProcurementItem.case_id == case_id,
        CaseProcurementItem.id == item_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.item_number = item_data.item_number
    item.description = item_data.description
    item.quantity = item_data.quantity
    item.unit = item_data.unit
    item.is_manual_edit = True
    if item_data.status:
        item.status = item_data.status

    db.commit()
    db.refresh(item)
    return item

@router.delete("/cases/{case_id}/procurement-items/{item_id}")
def delete_procurement_item(
    case_id: int,
    item_id: int,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    from app.models.v6.case_procurement_item import CaseProcurementItem
    item = db.query(CaseProcurementItem).filter(
        CaseProcurementItem.case_id == case_id,
        CaseProcurementItem.id == item_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(item)
    db.commit()
    return {"message": "Deleted"}
