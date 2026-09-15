from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile, AuditLog
from pydantic import BaseModel
from typing import List
from datetime import datetime

router = APIRouter()

class AuditLogResponse(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: str
    details: str
    status: str
    created_at: datetime
    user_id: int

@router.get("/cases/{case_id}/history", response_model=List[AuditLogResponse])
def get_case_history(
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Audit log might be tied to case directly, or related entities.
    # The requirement is to show real events from the case.
    # Since we log everything with entity_type="CaseFile" and entity_id=case_id,
    # or we can just fetch all AuditLogs for this tenant where entity_id = case_id 
    # (assuming they are tied correctly, but supplier offer etc might have different entity types).
    # To keep it simple and safe for now, let's fetch everything that mentions this case id directly 
    # OR we can just fetch by tenant_id and entity_type="CaseFile", entity_id=str(case.id).
    
    logs = db.query(AuditLog).filter(
        AuditLog.tenant_id == current_user.tenant_id,
        AuditLog.entity_type == "CaseFile",
        AuditLog.entity_id == str(case.id)
    ).order_by(AuditLog.created_at.desc()).all()
    
    return logs
