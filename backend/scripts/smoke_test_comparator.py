import os
import json
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import argparse
from typing import Dict, Any

from app.models.domain import ValidationDocumentCase, OCRProcessingRun, ParsedSection
from app.services.extraction_engine.v2_pipeline import StructuredDocument
from app.services.extraction_engine.adapters.structured_document_adapter import StructuredDocumentAdapter
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def compare_runs(validation_run_id: str):
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        cases = db.query(ValidationDocumentCase).filter(
            ValidationDocumentCase.validation_run_id == validation_run_id
        ).all()
        
        logger.info(f"Found {len(cases)} cases for validation run {validation_run_id}")
        
        report = {
            "total_cases": len(cases),
            "completed_cases": 0,
            "failed_primary": 0,
            "failed_shadow": 0,
            "comparisons": []
        }
        
        for case in cases:
            primary_run = db.query(OCRProcessingRun).filter(
                OCRProcessingRun.validation_case_id == case.case_id,
                OCRProcessingRun.execution_role == "PRIMARY"
            ).first()
            
            shadow_run = db.query(OCRProcessingRun).filter(
                OCRProcessingRun.validation_case_id == case.case_id,
                OCRProcessingRun.execution_role == "SHADOW"
            ).first()
            
            if not primary_run or primary_run.status != 'COMPLETED':
                report["failed_primary"] += 1
                continue
                
            if not shadow_run or shadow_run.status != 'COMPLETED':
                report["failed_shadow"] += 1
                continue
                
            report["completed_cases"] += 1
            
            # 1. Fetch Primary Results (V1)
            v1_sections = db.query(ParsedSection).filter(
                ParsedSection.case_id == case.uploaded_document.case_id
            ).order_by(ParsedSection.id).all()
            
            # 2. Fetch Shadow Results (V2)
            try:
                with open(shadow_run.structured_document_path, "r", encoding="utf-8") as f:
                    v2_dict = json.load(f)
                
                v2_structured_doc = StructuredDocument(**v2_dict)
                v2_sections = StructuredDocumentAdapter.to_parsed_sections(case.uploaded_document.case_id, v2_structured_doc)
            except Exception as e:
                logger.error(f"Failed to process shadow artifacts for run {shadow_run.run_id}: {str(e)}")
                continue
                
            # 3. Compare
            case_report = {
                "case_id": str(case.case_id),
                "primary_run_id": str(primary_run.run_id),
                "shadow_run_id": str(shadow_run.run_id),
                "v1_section_count": len(v1_sections),
                "v2_section_count": len(v2_sections),
                "v2_score": shadow_run.score
            }
            
            report["comparisons"].append(case_report)
            
        logger.info("\n=== COMPARISON REPORT ===")
        logger.info(json.dumps(report, indent=2))
        
        report_path = os.path.join(settings.UPLOADS_DIR, f"validation_report_{validation_run_id}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Report saved to {report_path}")
        
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare OCR V1 and V2 results")
    parser.add_argument("--validation-run-id", required=True, help="UUID of the validation run")
    args = parser.parse_args()
    
    compare_runs(args.validation_run_id)
