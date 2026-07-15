import os
import uuid
import hashlib
import secrets
import logging
import subprocess
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import UUID4
import time
from datetime import datetime

from app.core.database import get_db
from app.models.domain import UploadedDocument, ValidationDocumentCase, OCRProcessingRun
from app.services.ocr.run_repository import OCRRunRepository
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_PDF_SIZE = int(os.environ.get("VALIDATION_MAX_PDF_SIZE_MB", 20)) * 1024 * 1024
QPDF_TIMEOUT = int(os.environ.get("PDF_STRUCTURE_CHECK_TIMEOUT_SECONDS", 10))

def verify_token(x_api_key: str = Header(...)):
    expected_token = os.environ.get("VALIDATION_API_KEY", "supersecret_validation_token")
    if not secrets.compare_digest(x_api_key, expected_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
    return x_api_key

def validate_pdf_structure(file_path: str):
    """
    Validates PDF using qpdf.
    exit 0 -> OK
    exit 3 -> OK with warnings
    exit 2 -> ERROR
    """
    try:
        process = subprocess.run(
            ["qpdf", "--check", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=QPDF_TIMEOUT,
            text=True
        )
        
        if process.returncode == 0:
            return {"status": "ok", "warnings": None}
        elif process.returncode == 3:
            return {"status": "ok", "warnings": process.stderr}
        else:
            logger.error(f"qpdf validation failed: {process.stderr}")
            raise HTTPException(status_code=422, detail="Invalid PDF structure or encrypted/protected PDF")
            
    except subprocess.TimeoutExpired:
        logger.error("qpdf validation timed out")
        raise HTTPException(status_code=422, detail="PDF structure validation timed out")
    except FileNotFoundError:
        # Strict requirement: return 503 if qpdf not installed
        logger.error("qpdf not found, cannot validate structural integrity")
        raise HTTPException(status_code=503, detail="qpdf validation tool is not available")

@router.post("/upload")
def upload_validation_document(
    validation_run_id: UUID4 = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_token)
):
    if str(settings.OCR_ENGINE).lower() != "v1" or not settings.OCR_SHADOW_MODE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Endpoint is only active for OCR_ENGINE=v1 and OCR_SHADOW_MODE=true"
        )
        
    uploads_dir = os.environ.get("UPLOADS_DIR", "/data/uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    file_id = str(uuid.uuid4())
    file_path = os.path.join(uploads_dir, f"{file_id}.pdf")
    
    sha256_hash = hashlib.sha256()
    file_size = 0
    is_first_chunk = True
    
    try:
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(8192):
                if is_first_chunk:
                    if not chunk.startswith(b"%PDF-"):
                        raise HTTPException(status_code=422, detail="File does not start with PDF magic numbers")
                    is_first_chunk = False
                    
                file_size += len(chunk)
                if file_size > MAX_PDF_SIZE:
                    raise HTTPException(status_code=413, detail=f"File exceeds maximum allowed size of {MAX_PDF_SIZE} bytes")
                    
                sha256_hash.update(chunk)
                buffer.write(chunk)
                
        pdf_sha256 = sha256_hash.hexdigest()
        
        # Deep validation
        validation_result = validate_pdf_structure(file_path)
        
        request_idempotency_key = hashlib.sha256(f"{validation_run_id}:{pdf_sha256}".encode()).hexdigest()
        
        # Try finding it first to avoid unnecessary inserts if we know it exists
        existing_case = db.query(ValidationDocumentCase).filter(
            ValidationDocumentCase.request_idempotency_key == request_idempotency_key
        ).first()
        
        if existing_case:
            os.remove(file_path)
            primary_run = db.query(OCRProcessingRun).filter(
                OCRProcessingRun.validation_case_id == existing_case.case_id,
                OCRProcessingRun.execution_role == "PRIMARY"
            ).first()
            
            shadow_run = db.query(OCRProcessingRun).filter(
                OCRProcessingRun.validation_case_id == existing_case.case_id,
                OCRProcessingRun.execution_role == "SHADOW"
            ).first()
            
            return {
                "message": "Document already submitted",
                "validation_case_id": str(existing_case.case_id),
                "primary_run_id": str(primary_run.run_id) if primary_run else None,
                "shadow_run_id": str(shadow_run.run_id) if shadow_run else None,
                "shadow_status": shadow_run.status if shadow_run else "NOT_CREATED"
            }
            
        # Create records
        repo = OCRRunRepository(db)
        
        try:
            document = UploadedDocument(
                document_type="requirement",
                original_filename=file.filename,
                stored_path=file_path,
                mime_type="application/pdf",
                processing_status="queued",
                ocr_metadata={
                    "pdf_validation_status": validation_result["status"],
                    "pdf_validation_warnings": validation_result["warnings"],
                    "pdf_size_bytes": file_size,
                    "engine_primary": "v1",
                    "shadow_mode_active": True,
                    "review_threshold": settings.OCR_REVIEW_THRESHOLD,
                    "pipeline_version": "1.0/2.0",
                    "adapter_version": "1.0",
                    "validation_policy_version": "1.0"
                }
            )
            db.add(document)
            db.flush()
            
            val_case = ValidationDocumentCase(
                validation_run_id=validation_run_id,
                uploaded_document_id=document.id,
                pdf_sha256=pdf_sha256,
                request_idempotency_key=request_idempotency_key
            )
            db.add(val_case)
            db.flush()
            
            primary_run_dedup = hashlib.sha256(f"{val_case.case_id}:PRIMARY:v1:1".encode()).hexdigest()
            primary_run = OCRProcessingRun(
                uploaded_document_id=document.id,
                validation_case_id=val_case.case_id,
                execution_role="PRIMARY",
                engine="v1",
                status="PENDING_DISPATCH",
                run_dedup_key=primary_run_dedup
            )
            repo.create_run(primary_run)
            
            db.commit()
            
            return {
                "message": "Validation document ingested successfully",
                "validation_case_id": str(val_case.case_id),
                "primary_run_id": str(primary_run.run_id),
                "shadow_run_id": None,
                "shadow_status": "NOT_CREATED"
            }
            
        except IntegrityError:
            db.rollback()
            os.remove(file_path)
            
            # Race condition lost. Fetch the existing one with a short backoff retry
            for _ in range(3):
                time.sleep(0.1)
                existing_case = db.query(ValidationDocumentCase).filter(
                    ValidationDocumentCase.request_idempotency_key == request_idempotency_key
                ).first()
                if existing_case:
                    primary_run = db.query(OCRProcessingRun).filter(
                        OCRProcessingRun.validation_case_id == existing_case.case_id,
                        OCRProcessingRun.execution_role == "PRIMARY"
                    ).first()
                    shadow_run = db.query(OCRProcessingRun).filter(
                        OCRProcessingRun.validation_case_id == existing_case.case_id,
                        OCRProcessingRun.execution_role == "SHADOW"
                    ).first()
                    
                    return {
                        "message": "Document already submitted",
                        "validation_case_id": str(existing_case.case_id),
                        "primary_run_id": str(primary_run.run_id) if primary_run else None,
                        "shadow_run_id": str(shadow_run.run_id) if shadow_run else None,
                        "shadow_status": shadow_run.status if shadow_run else "NOT_CREATED"
                    }
            raise HTTPException(status_code=500, detail="Failed to resolve concurrent insertion")
            
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in upload: {str(e)}")
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="Internal server error during upload")
