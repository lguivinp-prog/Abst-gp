import logging
import uuid
import hashlib
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import SessionLocal
from app.models.domain import CaseFile, UploadedDocument, ProcessingJob
from app.core.redis import task_queue

logger = logging.getLogger(__name__)

def sweep_and_reprocess(db: Session) -> int:
    """
    Scans for CaseFiles in REQUIRES_REPROCESSING status idempotently.
    Uses an outbox pattern to ensure RQ jobs are durably enqueued.
    """
    # 1. Atomic claim using FOR UPDATE SKIP LOCKED
    cases = db.query(CaseFile).filter(
        CaseFile.status == 'REQUIRES_REPROCESSING'
    ).with_for_update(skip_locked=True).all()
    
    if not cases:
        # Also try to resume any stuck REPROCESSING_QUEUING cases
        cases = db.query(CaseFile).filter(
            CaseFile.status == 'REPROCESSING_QUEUING'
        ).with_for_update(skip_locked=True).all()
        if not cases:
            return 0

    count = 0
    for case in cases:
        try:
            logger.info(f"Initiating reprocessing for case {case.id}")
            docs = db.query(UploadedDocument).filter(UploadedDocument.case_id == case.id).all()
            
            if not docs:
                case.status = 'REPROCESSING_FAILED'
                logger.error(f"Case {case.id} has no documents")
                continue

            missing_path = False
            for doc in docs:
                if not doc.stored_path:
                    missing_path = True
                    break
            
            if missing_path:
                case.status = 'REPROCESSING_FAILED'
                logger.error(f"Case {case.id} is missing stored_path on a document")
                continue

            # Check if jobs already created in a previous failed queuing attempt
            jobs_created = []
            if case.status != 'REPROCESSING_QUEUING':
                # Generate jobs
                for doc in docs:
                    pj = db.query(ProcessingJob).filter_by(document_id=doc.id, worker_type="ocr_reprocess").first()
                    if not pj:
                        pj = ProcessingJob(
                            document_id=doc.id,
                            worker_type="ocr_reprocess",
                            status="pending"
                        )
                        db.add(pj)
                        db.flush()
                    jobs_created.append(pj)
                
                case.status = 'REPROCESSING_QUEUING'
                # 5. Commit before dispatch
                db.commit()
            else:
                for doc in docs:
                    pj = db.query(ProcessingJob).filter_by(document_id=doc.id, worker_type="ocr_reprocess").first()
                    if pj:
                        jobs_created.append(pj)

            # 6. Dispatch to RQ with deterministic ID
            for pj in jobs_created:
                doc = db.query(UploadedDocument).get(pj.document_id)
                # RQ enqueue ignores if job with same ID already exists in queue, providing idempotency
                try:
                    task_queue.enqueue(
                        "app.worker.tasks.process_requirement_task",
                        args=(case.id, doc.stored_path),
                        job_id=str(pj.id),
                        job_timeout=3600
                    )
                except Exception as e:
                    logger.error(f"Failed to enqueue RQ job for document {doc.id}: {e}")
                    raise e
            
            # 7. Transition only when all documents have durable jobs
            case.status = 'OCR_QUEUED'
            db.commit()
            count += 1
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing case {case.id}: {e}")

    return count

if __name__ == "__main__":
    db = SessionLocal()
    try:
        count = sweep_and_reprocess(db)
        print(f"Swept and reprocessed {count} cases.")
    finally:
        db.close()
