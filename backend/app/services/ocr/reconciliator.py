import os
import hashlib
import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.domain import OCRProcessingRun

class DBFSReconciliator:
    """
    Reconciles the database state with the filesystem state for structured documents.
    Detects:
    - Missing files: DB says it exists, but FS doesn't have it.
    - Orphan files: FS has it, but DB doesn't know about it.
    - Checksum mismatches: DB checksum doesn't match FS checksum.
    """
    
    def __init__(self, session: Session, base_dir: str):
        self.session = session
        self.base_dir = os.path.abspath(base_dir)
        
    def reconcile(self) -> Dict[str, Any]:
        report = {
            "missing_files": [],
            "orphan_files": [],
            "checksum_mismatches": [],
            "total_db_records": 0,
            "total_fs_files": 0,
            "healthy_files": 0
        }
        
        # 1. Fetch all DB records that claim to have a structured document
        db_records = self.session.query(
            OCRProcessingRun.run_id, 
            OCRProcessingRun.structured_document_path,
            OCRProcessingRun.structured_document_checksum
        ).filter(
            OCRProcessingRun.structured_document_path.isnot(None)
        ).all()
        
        report["total_db_records"] = len(db_records)
        
        db_expected_paths = {}
        for record in db_records:
            # We expect structured_document_path to be relative or absolute, normalize to absolute
            abs_path = os.path.abspath(os.path.join(self.base_dir, os.path.basename(record.structured_document_path)))
            db_expected_paths[abs_path] = {
                "run_id": str(record.run_id),
                "checksum": record.structured_document_checksum
            }
            
            # Check for missing
            if not os.path.exists(abs_path):
                report["missing_files"].append({
                    "run_id": str(record.run_id),
                    "expected_path": abs_path
                })
                continue
                
            # Check checksum
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    doc_dict = json.load(f)
                    
                embedded_checksum = doc_dict.get("checksum")
                
                from app.services.ocr.checksum import calculate_structured_document_checksum
                actual_checksum = calculate_structured_document_checksum(doc_dict)
                
                if actual_checksum != record.structured_document_checksum:
                    report["checksum_mismatches"].append({
                        "run_id": str(record.run_id),
                        "path": abs_path,
                        "expected_db_checksum": record.structured_document_checksum,
                        "embedded_checksum": embedded_checksum,
                        "actual_checksum": actual_checksum
                    })
                else:
                    report["healthy_files"] += 1
            except Exception as e:
                report["missing_files"].append({
                    "run_id": str(record.run_id),
                    "expected_path": abs_path,
                    "error": f"JSON parse error or IO error: {str(e)}"
                })

        # 2. Scan FS to find orphans
        if os.path.exists(self.base_dir):
            for filename in os.listdir(self.base_dir):
                if not filename.endswith(".json"):
                    continue # Ignore tmp files and other non-json files
                    
                abs_path = os.path.abspath(os.path.join(self.base_dir, filename))
                report["total_fs_files"] += 1
                
                if abs_path not in db_expected_paths:
                    report["orphan_files"].append(abs_path)
                    
        return report
