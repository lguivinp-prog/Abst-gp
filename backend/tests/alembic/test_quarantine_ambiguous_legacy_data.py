import pytest
from sqlalchemy import text
from app.core.database import SessionLocal
from app.models.domain import (
    CaseFile, UploadedDocument, ParsedSection, RequirementItem, 
    ComparisonRun, ComparisonResult, ComparisonRunStatus, ProcessingJob
)
import uuid

def test_quarantine_ambiguous_legacy_data_migration():
    # Setup test data simulating the state BEFORE the migration
    db = SessionLocal()
    try:
        # Create a case file
        case = CaseFile(title="Mixed Legacy Case", contract_type="Goods")
        db.add(case)
        db.commit()
        
        # 1. Create a Requirement document processed by V1
        req_doc = UploadedDocument(
            case_id=case.id, document_type="requirement", 
            stored_path="req.pdf", original_filename="req.pdf", mime_type="application/pdf",
            ocr_engine_used="v1" # LEGACY V1
        )
        # 2. Create a Quotation document processed by V2
        quot_doc = UploadedDocument(
            case_id=case.id, document_type="quotation", 
            stored_path="quot.pdf", original_filename="quot.pdf", mime_type="application/pdf",
            ocr_engine_used="v2" # V2
        )
        db.add_all([req_doc, quot_doc])
        db.commit()

        # Create ambiguous ParsedSections (legacy mapped them all to req_doc or left null)
        sec_req = ParsedSection(case_id=case.id, document_id=req_doc.id, cleaned_text="Req Text")
        sec_quot = ParsedSection(case_id=case.id, document_id=req_doc.id, cleaned_text="Quot Text") # Wrongly mapped!
        db.add_all([sec_req, sec_quot])
        db.commit()

        # Create RequirementItems
        req_item = RequirementItem(parsed_section_id=sec_req.id, content_text="Req Text", item_type="technical", is_approved=True)
        db.add(req_item)
        db.commit()

        # Create ComparisonRun COMPLETED
        run_dedup = str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')
        run = ComparisonRun(case_id=case.id, requirement_doc_id=req_doc.id, quotation_doc_id=quot_doc.id, status=ComparisonRunStatus.COMPLETED)
        db.add(run)
        db.commit()

        # Create ComparisonResults
        result = ComparisonResult(run_id=run.id, requirement_item_id=req_item.id, status="MATCH", confidence_score=0.9, reasoning="Matches")
        db.add(result)
        db.commit()

        # Execute the upgrade function manually to simulate migration logic in testing
        # (Since we are testing the logic of the migration itself, we apply its SQL)
        from alembic.config import Config
        from alembic import command
        
        # We ensure it is upgraded to head
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")

        # Now test that it was detected and processed
        db.expire_all()
        
        case_after = db.query(CaseFile).filter(CaseFile.id == case.id).first()
        assert case_after.status == 'REQUIRES_REPROCESSING', "Case was not detected as ambiguous mixed V1/V2"

        # Check records deleted
        assert db.query(ParsedSection).filter(ParsedSection.case_id == case.id).count() == 0, "ParsedSections not deleted"
        assert db.query(RequirementItem).join(ParsedSection).filter(ParsedSection.case_id == case.id).count() == 0, "RequirementItems not deleted"
        assert db.query(ComparisonResult).join(ComparisonRun).filter(ComparisonRun.case_id == case.id).count() == 0, "ComparisonResults not deleted"
        
        # Check ComparisonRun invalidated
        run_after = db.query(ComparisonRun).filter(ComparisonRun.case_id == case.id).first()
        assert run_after.status == ComparisonRunStatus.FAILED
        assert run_after.failure_detail == 'Quarantined due to ambiguous legacy OCR'

        # Run the scanner
        from app.cli.scanner_reprocessing import sweep_and_reprocess
        count = sweep_and_reprocess(db)
        
        assert count == 1, "Expected exactly 1 request for reprocessing"
        case_requeued = db.query(CaseFile).filter(CaseFile.id == case.id).first()
        assert case_requeued.status == 'OCR_QUEUED'

        # Idempotency check: running sweep again should do nothing
        count2 = sweep_and_reprocess(db)
        assert count2 == 0

        # Run OCR V2 logic to reconstruct sections
        from app.worker.ocr_worker_tasks import process_run_v2
        
        # We expect jobs to be created
        jobs = db.query(ProcessingJob).all()
        assert len(jobs) >= 2, "Should have created jobs for the 2 documents"
        
    finally:
        db.close()
