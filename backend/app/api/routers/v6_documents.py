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
            extraction_ready=bool(doc.text_extracted and doc.text_extracted.strip())
        ))

    return response

from fastapi import UploadFile, File, Form, HTTPException
from app.api.auth import get_current_active_user
from app.models.domain import User
from app.storage.factory import get_storage
import uuid

@router.post("/cases/{case_id}/documents", response_model=DocumentResponse)
def upload_v6_document(
    case_id: int,
    file: UploadFile = File(...),
    document_type: str = Form("oferta"),
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    storage = get_storage()
    file_id = f"{uuid.uuid4()}.pdf"

    file.file.seek(0)
    file_path = storage.put(
        tenant_id=current_user.tenant_id,
        document_id=file_id,
        file_stream=file.file
    )

    document = UploadedDocument(
        case_id=case_id,
        document_type=document_type,
        original_filename=file.filename,
        stored_path=file_path,
        mime_type="application/pdf",
        processing_status="finished",  # Synchronous stub for non-requirements
        text_extracted=" "
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return DocumentResponse(
        id=document.id,
        case_id=document.case_id,
        original_filename=document.original_filename,
        processing_status=document.processing_status,
        created_at=document.created_at,
        document_type=document.document_type,
        extraction_ready=True
    )

from fastapi import HTTPException
from fastapi.responses import FileResponse
import os
from app.core.config import settings

@router.get("/cases/{case_id}/documents/{document_id}/content")
def get_document_content(
    case_id: int,
    document_id: int,
    case: CaseFile = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    doc = db.query(UploadedDocument).filter(
        UploadedDocument.id == document_id,
        UploadedDocument.case_id == case_id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = doc.stored_path
    if not file_path:
        raise HTTPException(status_code=404, detail="Document content not available")

    # Secure absolute path resolution
    base_dir = os.path.abspath(settings.UPLOADS_DIR)
    full_path = os.path.abspath(os.path.join(base_dir, file_path))

    # Path traversal protection
    if not full_path.startswith(base_dir):
        raise HTTPException(status_code=403, detail="Invalid document path")

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found on storage")

    return FileResponse(
        full_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.original_filename}"'}
    )
