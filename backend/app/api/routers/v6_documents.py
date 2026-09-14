from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.core.database import get_db
from app.api.auth import verify_case_access
from app.models.domain import CaseFile, UploadedDocument
from pydantic import BaseModel, ConfigDict

router = APIRouter()

class DocumentResponse(BaseModel):
    id: int
    case_id: int
    original_filename: str
    processing_status: Optional[str] = None
    created_at: Optional[datetime] = None
    document_type: Optional[str] = None
    extraction_ready: bool

    model_config = ConfigDict(from_attributes=True)

@router.get("/cases/{case_id}/documents", response_model=List[DocumentResponse])
def get_case_documents(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    docs = (
        db.query(UploadedDocument)
        .filter(UploadedDocument.case_id == case_id)
        .order_by(UploadedDocument.created_at.desc())
        .all()
    )

    response = []
    for doc in docs:
        response.append(DocumentResponse(
            id=doc.id,
            case_id=doc.case_id,
            original_filename=doc.original_filename,
            processing_status=doc.processing_status,
            created_at=doc.created_at,
            document_type=doc.document_type,
            extraction_ready=bool(doc.text_extracted)
        ))

    return response
