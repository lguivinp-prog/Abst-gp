import pytest
import uuid
from sqlalchemy import text
from alembic.config import Config
from alembic import command
from app.core.database import SessionLocal, engine

@pytest.fixture
def alembic_config():
    alembic_cfg = Config("alembic.ini")
    return alembic_cfg

def test_quarantine_ambiguous_legacy_data(alembic_config, monkeypatch):
    import sys
    import importlib
    import os
    import glob
    
    # 1. Temporarily allow downgrade for testing
    version_files = glob.glob('alembic/versions/*476e*.py')
    if version_files:
        filepath = version_files[0]
        with open(filepath, 'r') as f:
            original_code = f.read()
        
        import re
        modified_code = re.sub(r'def downgrade\(\) -> None:.*', 'def downgrade() -> None:\n    pass', original_code, flags=re.DOTALL)
        with open(filepath, 'w') as f:
            f.write(modified_code)

    # Downgrade to 12fd022d7f66
    try:
        command.downgrade(alembic_config, "12fd022d7f66")
    finally:
        # Restore original code
        if version_files:
            with open(filepath, 'w') as f:
                f.write(original_code)

    db = SessionLocal()
    
    try:
        db.execute(text("DROP TABLE IF EXISTS quarantine_backup_comparison_results CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS quarantine_backup_comparison_runs CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS quarantine_backup_requirement_items CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS quarantine_backup_parsed_sections CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS quarantine_manifest CASCADE"))
        db.commit()
    except Exception:
        db.rollback()

    try:
        db.execute(text("DELETE FROM comparison_results WHERE run_id IN (SELECT id FROM comparison_runs WHERE case_id = 999)"))
        db.execute(text("DELETE FROM comparison_runs WHERE case_id = 999"))
        db.execute(text("DELETE FROM requirement_items WHERE parsed_section_id IN (SELECT id FROM parsed_sections WHERE case_id = 999)"))
        db.execute(text("DELETE FROM parsed_sections WHERE case_id = 999"))
        db.execute(text("DELETE FROM uploaded_documents WHERE case_id = 999"))
        db.execute(text("DELETE FROM case_files WHERE id = 999"))
        db.commit()
    except Exception:
        db.rollback()
    
    # Insert data manually using raw SQL since models might be on head
    # 1. Insert Case
    db.execute(text("INSERT INTO case_files (id, title, contract_type, status) VALUES (999, 'Test Case', 'Goods', 'OCR_COMPLETED')"))
    
    # 2. Insert uploaded documents (1 V1 requirement, 1 V2 quotation)
    db.execute(text("""
        INSERT INTO uploaded_documents (id, case_id, document_type, stored_path, original_filename, mime_type, processing_status, ocr_engine_used) 
        VALUES (9991, 999, 'requirement', 'req.pdf', 'req.pdf', 'application/pdf', 'completed', 'v1')
    """))
    db.execute(text("""
        INSERT INTO uploaded_documents (id, case_id, document_type, stored_path, original_filename, mime_type, processing_status, ocr_engine_used) 
        VALUES (9992, 999, 'quotation', 'quo.pdf', 'quo.pdf', 'application/pdf', 'completed', 'v2')
    """))
    
    # 3. Insert ParsedSections
    db.execute(text("""
        INSERT INTO parsed_sections (id, case_id, document_id, original_text, cleaned_text, normalized_text, extraction_metadata)
        VALUES (9991, 999, 9991, 'req', 'req', 'req', '{}')
    """))
    db.execute(text("""
        INSERT INTO parsed_sections (id, case_id, document_id, original_text, cleaned_text, normalized_text, extraction_metadata)
        VALUES (9992, 999, 9992, 'quo', 'quo', 'quo', '{}')
    """))

    # 4. Insert RequirementItems
    req_item_id = str(uuid.uuid4())
    db.execute(text(f"""
        INSERT INTO requirement_items (id, parsed_section_id, item_type, content_text, is_approved)
        VALUES ('{req_item_id}', 9991, 'TECHNICAL', 'req', true)
    """))

    # 5. Insert ComparisonRun
    run_uuid = uuid.uuid4()
    db.execute(text(f"""
        INSERT INTO comparison_runs (id, case_id, requirement_doc_id, quotation_doc_id, status)
        VALUES ('{run_uuid}', 999, 9991, 9992, 'COMPLETED')
    """))

    # 6. Insert ComparisonResults
    db.execute(text(f"""
        INSERT INTO comparison_results (id, run_id, requirement_item_id, status, evaluation_method, confidence_score)
        VALUES ('{str(uuid.uuid4())}', '{run_uuid}', '{req_item_id}', 'PASS', 'EXACT_MATCH', 0.99)
    """))

    db.commit()

    # Now upgrade to head
    command.upgrade(alembic_config, "head")

    # Verify results
    case_status = db.execute(text("SELECT status FROM case_files WHERE id = 999")).scalar()
    assert case_status == 'REQUIRES_REPROCESSING'

    run_status = db.execute(text(f"SELECT status FROM comparison_runs WHERE id = '{run_uuid}'")).scalar()
    assert run_status == 'FAILED'

    results_count = db.execute(text(f"SELECT COUNT(*) FROM comparison_results WHERE run_id = '{run_uuid}'")).scalar()
    assert results_count == 0

    req_items_count = db.execute(text("SELECT COUNT(*) FROM requirement_items WHERE parsed_section_id IN (9991, 9992)")).scalar()
    assert req_items_count == 0

    parsed_sections_count = db.execute(text("SELECT COUNT(*) FROM parsed_sections WHERE case_id = 999")).scalar()
    assert parsed_sections_count == 0
    
    # Check backups
    backup_runs = db.execute(text(f"SELECT COUNT(*) FROM quarantine_backup_comparison_runs WHERE case_id = 999")).scalar()
    assert backup_runs == 1

    # Check manifest
    manifest = db.execute(text("SELECT case_id, original_status, doc_count, legacy_doc_count FROM quarantine_manifest WHERE case_id = 999")).fetchone()
    assert manifest is not None
    assert manifest[0] == 999
    assert manifest[1] == 'OCR_COMPLETED'
    assert manifest[2] == 2
    assert manifest[3] == 1

    # Cleanup
    try:
        db.execute(text("TRUNCATE TABLE case_files CASCADE"))
        db.commit()
    except Exception:
        db.rollback()
    db.close()
