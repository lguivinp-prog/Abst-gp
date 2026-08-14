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
    description: str
    value: Optional[str] = None
    mandatory: bool
    status: str
    evidences: List[EvidenceResponse] = []
    
    class Config:
        from_attributes = True

class RequirementUpdate(BaseModel):
    status: str # VALIDATED, MODIFIED_BY_USER, OBSERVED, REJECTED
    description: Optional[str] = None
    value: Optional[str] = None
    reason: str

@router.post("/cases/{case_id}/requirements/extract", response_model=List[RequirementResponse])
def extract_requirements(
    case_id: int,
    req: ExtractionRequest,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    doc = db.query(UploadedDocument).filter(UploadedDocument.id == req.document_id, UploadedDocument.case_id == case_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    text = doc.text_extracted or "Simulated OCR Text for Extraction"
    
    return extraction_service.process_text_and_propose(
        db=db,
        case_id=case_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        text=text,
        document_name=doc.original_filename
    )

@router.get("/cases/{case_id}/requirements", response_model=List[RequirementResponse])
def get_requirements(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    return db.query(CaseRequirementMatrix).filter(CaseRequirementMatrix.case_id == case_id).all()

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
    if update_data.description:
        req.description = update_data.description
    if update_data.value is not None:
        req.value = update_data.value
        
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
