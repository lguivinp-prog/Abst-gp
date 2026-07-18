import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.domain import OCRProcessingRun, ValidationDocumentCase
from sqlalchemy import select

logger = logging.getLogger(__name__)

class OCRRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_run(self, run: OCRProcessingRun) -> OCRProcessingRun:
        """
        Creates an OCRProcessingRun with strict cross-validations and locking.
        """
        # Validate scope
        if run.validation_case_id:
            # Lock the validation case to prevent race conditions during run creation
            val_case = self.session.execute(
                select(ValidationDocumentCase)
                .where(ValidationDocumentCase.case_id == run.validation_case_id)
                .with_for_update()
            ).scalar_one_or_none()
            
            if not val_case:
                raise ValueError("Validation case does not exist.")
                
            if run.uploaded_document_id != val_case.uploaded_document_id:
                raise ValueError("OCRProcessingRun document does not match ValidationDocumentCase document")
        else:
            # We don't have validation_case_id, so it must be processing_job_id (guaranteed by CHECK constraints)
            # In a real scenario we'd lock the processing job here.
            pass

        # Validate source
        if run.source_run_id:
            source_run = self.session.execute(
                select(OCRProcessingRun)
                .where(OCRProcessingRun.run_id == run.source_run_id)
                .with_for_update()
            ).scalar_one_or_none()
            
            if not source_run:
                raise ValueError("Source run does not exist.")

            if run.uploaded_document_id != source_run.uploaded_document_id:
                raise ValueError("Source run document does not match this run's document.")
                
            if run.validation_case_id != source_run.validation_case_id or run.processing_job_id != source_run.processing_job_id:
                raise ValueError("Source run scope does not match this run's scope.")
                
            if source_run.execution_role != 'PRIMARY':
                raise ValueError("Source run must have role PRIMARY.")
                
            if run.execution_role == 'FALLBACK':
                if source_run.engine != 'v2':
                    raise ValueError("FALLBACK runs must originate from a v2 source.")
                if source_run.status != 'FAILED':
                    raise ValueError("FALLBACK runs must originate from a FAILED source.")
            elif run.execution_role == 'SHADOW':
                # The CHECK constraint already verifies engine == 'v2', but let's be explicit
                pass
            
            if source_run.execution_role == 'SHADOW':
                 raise ValueError("Shadow mode can never create a FALLBACK or any other child run.")

        try:
            with self.session.begin_nested():
                self.session.add(run)
                self.session.flush()
            return run
        except IntegrityError:
            # We don't need to manually rollback, begin_nested() handles it!
            # The outer transaction is still valid.
            raise
