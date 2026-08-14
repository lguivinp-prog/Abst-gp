import pytest
from app.models.domain import ProcessingJob, UploadedDocument, OCRProcessingRun
from app.services.job_repository import JobRepository
from sqlalchemy.orm import Session
import uuid

def test_legacy_job_creation(db_session: Session, setup_mega_tenant):
    """
    Caracterización de JobRepository para asegurar que 
    la creación de jobs asíncronos legacy no se rompa por V6.
    """
    job = JobRepository.create_job(
        db=db_session,
        case_id=None,
        tenant_id="mega_tenant",
        user_id=1,
        job_type="REQUIREMENT_OCR"
    )
    assert job is not None
    assert job.status == "QUEUED"
    assert job.worker_type == "abst_worker"
    
def test_legacy_ocr_run_initialization(db_session: Session, setup_mega_tenant):
    """
    Caracterización del modelo OCRProcessingRun
    para asegurar restricciones de engine, role y estado legacy.
    """
    doc = UploadedDocument(
        document_type="requirement",
        original_filename="test.pdf",
        stored_path="/tmp/test.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()
    
    run_id = uuid.uuid4()
    run = OCRProcessingRun(
        run_id=run_id,
        uploaded_document_id=doc.id,
        execution_role="PRIMARY",
        engine="v1",
        status="PENDING_DISPATCH",
        run_dedup_key=str(uuid.uuid4()).replace("-", "") * 2 # 64 chars
    )
    db_session.add(run)
    db_session.commit()
    
    saved_run = db_session.query(OCRProcessingRun).filter_by(run_id=run_id).first()
    assert saved_run is not None
    assert saved_run.status == "PENDING_DISPATCH"
