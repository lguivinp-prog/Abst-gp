import uuid
import hashlib
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.models.domain import UploadedDocument, OCRProcessingRun, ProcessingJob
from app.storage.factory import get_storage
from app.core.redis import ocr_queue

class RequirementIngestionService:
    @staticmethod
    def ingest_requirement(db: Session, case_id: int, file: UploadFile, tenant_id: str):
        # 1. Almacenar el archivo
        storage = get_storage()
        file_id = f"{uuid.uuid4()}.pdf"
        file.file.seek(0)
        file_path = storage.put(
            tenant_id=tenant_id,
            document_id=file_id,
            file_stream=file.file
        )

        # 2. Crear UploadedDocument
        job_id = str(uuid.uuid4())
        document = UploadedDocument(
            case_id=case_id,
            document_type="requirement",
            original_filename=file.filename,
            stored_path=file_path,
            mime_type="application/pdf",
            processing_job_id=job_id,
            processing_status="queued"
        )
        db.add(document)
        db.flush()

        # 3. Crear ProcessingJob (requerido por orchestrator)
        pj = ProcessingJob(
            document_id=document.id,
            worker_type="ocr_v2",
            status="pending"
        )
        db.add(pj)
        db.flush()

        # 4. Crear OCRProcessingRun (canonical V2 run)
        run_id = uuid.uuid4()
        dedup_key = hashlib.sha256(str(run_id).encode()).hexdigest()
        run = OCRProcessingRun(
            run_id=run_id,
            uploaded_document_id=document.id,
            processing_job_id=pj.id,
            execution_role="PRIMARY",
            engine="v2",
            status="QUEUED",
            run_dedup_key=dedup_key
        )
        db.add(run)

        # Confirmar en DB ANTES de despachar a la cola
        db.commit()
        db.refresh(document)

        # 5. Despachar a ocr_queue usando process_run_v2
        # NOTA: En el V2 canónico real (ExtractionOrchestrator._execute_v2_pipeline),
        # se despacha "app.worker.ocr_worker_tasks.process_run_v2"
        try:
            job = ocr_queue.enqueue(
                "app.worker.ocr_worker_tasks.process_run_v2",
                args=(str(run_id),),
                job_timeout=3600
            )
        except Exception as e:
            from datetime import datetime, timezone
            # Mark state as failed to avoid orphans
            run.status = "FAILED"
            run.finished_at = datetime.now(timezone.utc)
            run.failure_code = "DISPATCH_FAILURE"
            run.failure_detail = str(e)

            document.processing_status = "error"
            document.processing_error = "Dispatch failure"
            pj.status = "failed"
            db.commit()
            raise

        return {
            "document_id": document.id,
            "run_id": str(run_id),
            "processing_status": "QUEUED"
        }
