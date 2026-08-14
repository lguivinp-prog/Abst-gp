from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import datetime

from app.core.database import get_db
from app.api.auth import get_current_user
from sqlalchemy.orm import Session
from app.models.domain import User, UploadedDocument, CaseFile
from app.storage.factory import get_storage
from app.core.config import settings

router = APIRouter(prefix="/v2/documents/upload", tags=["Upload V2"])

class InitiateUploadRequest(BaseModel):
    case_id: int
    document_type: str
    filename: str
    content_type: str
    size_bytes: int

class InitiateUploadResponse(BaseModel):
    upload_id: str
    document_id: int
    presigned_url: str
    expires_in: int

class CompleteUploadRequest(BaseModel):
    document_id: int
    upload_id: str
    sha256_checksum: str

class CompleteUploadResponse(BaseModel):
    status: str
    message: str

def check_v2_enabled():
    if settings.DOCUMENT_UPLOAD_MODE != "v2":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="V2 upload is not enabled. Please use the legacy endpoint."
        )

@router.post("/initiate", response_model=InitiateUploadResponse)
def initiate_upload(
    req: InitiateUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_v2_enabled()
    
    # 1. Validate Tenant & Case
    case = db.query(CaseFile).filter(CaseFile.id == req.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    if current_user.tenant_id and case.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant isolation breach")
        
    # 2. Size Limit Validation
    max_size = getattr(settings, 'max_file_size', 104857600)
    if req.size_bytes > max_size:
        raise HTTPException(status_code=413, detail="Payload Too Large")

    # 3. Create Upload ID and Document record
    upload_id = str(uuid.uuid4())
    tenant = case.tenant_id or "mega_tenant"
    
    doc = UploadedDocument(
        case_id=req.case_id,
        document_type=req.document_type,
        original_filename=req.filename,
        mime_type=req.content_type,
        stored_path="", # Will be set on complete or we can set the URI now
        processing_status="UPLOADING",
        ocr_metadata={"v6_upload_id": upload_id, "v6_status": "UPLOADING"}
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    # Object Key
    object_key = f"{tenant}/{doc.id}_{req.filename}"
    doc.stored_path = object_key
    db.commit()

    # 4. Generate Presigned URL
    storage = get_storage()
    expiration = 3600
    presigned_url = storage.generate_presigned_url(object_key, expiration=expiration)
    
    return InitiateUploadResponse(
        upload_id=upload_id,
        document_id=doc.id,
        presigned_url=presigned_url,
        expires_in=expiration
    )

@router.post("/complete", response_model=CompleteUploadResponse)
def complete_upload(
    req: CompleteUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_v2_enabled()
    
    doc = db.query(UploadedDocument).filter(UploadedDocument.id == req.document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    case = db.query(CaseFile).filter(CaseFile.id == doc.case_id).first()
    if current_user.tenant_id and case.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant isolation breach")
        
    meta = doc.ocr_metadata or {}
    if meta.get("v6_upload_id") != req.upload_id:
        raise HTTPException(status_code=400, detail="Invalid upload_id")
        
    if doc.processing_status == "EXPIRED":
        raise HTTPException(status_code=400, detail="Upload expired")
        
    # 1. Check Object exists in Storage
    storage = get_storage()
    if not storage.exists(doc.stored_path):
        doc.processing_status = "FAILED"
        meta["v6_status"] = "FAILED"
        db.commit()
        raise HTTPException(status_code=404, detail="File not found in storage. Did you upload it?")
        
    # 2. Checksum validation
    actual_checksum = storage.checksum(doc.stored_path)
    if actual_checksum != req.sha256_checksum:
        doc.processing_status = "FAILED"
        meta["v6_status"] = "FAILED"
        db.commit()
        raise HTTPException(status_code=400, detail=f"Checksum mismatch. Expected {req.sha256_checksum}, got {actual_checksum}")
        
    # 3. Transition State
    doc.processing_status = "VALIDATING"
    meta["v6_status"] = "VALIDATING"
    doc.ocr_metadata = meta
    db.commit()
    
    # Ideally, here we would trigger an async validation job, but for now we immediately move to AVAILABLE
    doc.processing_status = "AVAILABLE"
    meta["v6_status"] = "AVAILABLE"
    doc.ocr_metadata = meta
    db.commit()
    
    return CompleteUploadResponse(
        status="AVAILABLE",
        message="Upload completed and validated successfully."
    )
