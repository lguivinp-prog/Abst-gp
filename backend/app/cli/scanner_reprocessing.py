import logging
from typing import List
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.domain import CaseFile, UploadedDocument
from app.services.extraction_engine.orchestrator import ExtractionOrchestrator

logger = logging.getLogger(__name__)

def sweep_and_reprocess(db: Session) -> int:
    """
    Scans for CaseFiles in REQUIRES_REPROCESSING status.
    For each case, it changes the status to OCR_QUEUED and enqueues
    a fresh extraction for all its UploadedDocuments.
    """
    cases = db.query(CaseFile).filter(
        CaseFile.status == 'REQUIRES_REPROCESSING'
    ).all()

    count = 0
    for case in cases:
        logger.info(f"Initiating reprocessing for case {case.id}")
        docs = db.query(UploadedDocument).filter(UploadedDocument.case_id == case.id).all()
        for doc in docs:
            # We bypass file upload and re-enqueue extraction from stored path
            if doc.stored_path:
                # We need to create a ProcessingJob since coordinate_extraction needs job_id
                from app.models.domain import ProcessingJob
                job = ProcessingJob(worker_type="ocr", status="pending")
                db.add(job)
                db.flush()
                ExtractionOrchestrator.coordinate_extraction(case.id, doc.stored_path, str(job.id))
                logger.info(f"Enqueued reprocessing for doc {doc.id}")
        
        # Move case out of quarantine to wait for new OCR results
        case.status = 'OCR_QUEUED'
        count += 1

    db.commit()
    return count

if __name__ == "__main__":
    db = SessionLocal()
    try:
        count = sweep_and_reprocess(db)
        print(f"Swept and reprocessed {count} cases.")
    finally:
        db.close()
