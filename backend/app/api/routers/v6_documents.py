from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.services.v6.engines.document_quality_analyzer import DocumentQualityAnalyzer
from app.models.domain import AuditLog
import uuid
import os

router = APIRouter()

# Mock function for PDF Metrics extraction
def mock_extract_pdf_metrics(filepath: str):
    return {
        "dpi": 140, # Deliberately low to trigger warning
        "blur_score": 50.0, # Deliberately low to trigger exception
        "rotation_degrees": 2.0,
        "contrast_ratio": 5.0,
        "empty_pages": False
    }

@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Save to Temp Storage
    temp_id = str(uuid.uuid4())
    temp_path = f"/tmp/abast_uploads/{temp_id}.pdf"
    os.makedirs("/tmp/abast_uploads", exist_ok=True)
    
    # Simulating file write
    # with open(temp_path, "wb") as buffer:
    #    buffer.write(await file.read())
        
    # 2. Analyze Quality
    analyzer = DocumentQualityAnalyzer(db)
    metrics = mock_extract_pdf_metrics(temp_path)
    
    # Mock document ID
    doc_id = 999 
    
    assessment = analyzer.analyze(document_id=doc_id, mock_pdf_metrics=metrics)
    db.add(assessment)
    
    # Audit Exception
    if assessment.quality_status == "QUALITY_EXCEPTION_REQUIRED":
        audit = AuditLog(
            user_id=1, tenant_id="t1", 
            action="DOCUMENT_QUALITY_EXCEPTION", 
            entity_type="DocumentQualityAssessment", 
            entity_id=str(doc_id), 
            details=str(assessment.issues), 
            status="WARNING"
        )
        db.add(audit)
    
    db.commit()
    
    # 3. Decision Gate
    if assessment.quality_status == "QUALITY_BLOCKED":
        # Do not persist, return Error
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail={"msg": "Document Quality Blocked", "issues": assessment.issues})
        
    # If Good, Warning or Exception Required -> Persist document and start OCR
    # (Mock persistence here)
    # trigger_ocr_task.delay(doc_id)
    
    return {
        "document_id": doc_id,
        "quality_status": assessment.quality_status,
        "issues": assessment.issues,
        "msg": "Document accepted for processing (Exception/Warning may apply)"
    }
