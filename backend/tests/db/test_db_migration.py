import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import uuid

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql://abst_user:abst_password@db:5432/test_abst_gp"

from app.models.domain import User, CaseFile, UploadedDocument, ValidationDocumentCase, OCRProcessingRun, ProcessingJob

engine = create_engine(os.environ["DATABASE_URL"])
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def assert_raises(db, func, expected_err=(IntegrityError, ValueError), msg=""):
    try:
        func()
        db.commit()
        print(f"ERROR: {msg} was allowed!")
        sys.exit(1)
    except expected_err:
        db.rollback()
        print(f"SUCCESS: {msg} rejected.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {msg} failed with unexpected error {e}")
        sys.exit(1)

def test_db_constraints(db_session):
    db = db_session
    
    # 1. Setup minimal requirements
    user = User(username=f"testuser_{uuid.uuid4()}", password_hash="hash", tenant_id="mega_tenant")
    db.add(user)
    db.commit()
    
    case = CaseFile(title="Test Case", contract_type="Bienes", status="CREATED", created_by=user.id)
    db.add(case)
    db.commit()
    
    doc = UploadedDocument(case_id=case.id, document_type="requirement", original_filename="test.pdf", stored_path="/data/test.pdf", mime_type="application/pdf")
    db.add(doc)
    db.commit()
    
    job = ProcessingJob(document_id=doc.id, worker_type="ocr")
    db.add(job)
    db.commit()

    print("Setup completed.")

    # 4. Scope XOR entre validación y ProcessingJob
    # Test valid XOR (Validation only)
    val_run_id = uuid.uuid4()
    pdf_sha = "a" * 64
    case_val = ValidationDocumentCase(
        validation_run_id=val_run_id,
        uploaded_document_id=doc.id,
        pdf_sha256=pdf_sha,
        request_idempotency_key=uuid.uuid4().hex + uuid.uuid4().hex
    )
    db.add(case_val)
    db.commit()

    run_dedup_1 = "c" * 64
    
    # Valid validation run
    valid_run = OCRProcessingRun(
        uploaded_document_id=doc.id,
        validation_case_id=case_val.case_id,
        processing_job_id=None,
        execution_role="PRIMARY",
        engine="v2",
        status="RUNNING",
        started_at=datetime.now(timezone.utc),
        run_dedup_key=run_dedup_1
    )
    db.add(valid_run)
    db.commit()
    print("SUCCESS: Valid XOR (Validation) allowed.")
    
    # Invalid XOR (Both)
    def test_both_scopes():
        bad_run = OCRProcessingRun(
            uploaded_document_id=doc.id,
            validation_case_id=case_val.case_id,
            processing_job_id=job.id,
            execution_role="PRIMARY",
            engine="v2",
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            run_dedup_key="d" * 64
        )
        db.add(bad_run)
    assert_raises(db, test_both_scopes, msg="Both scopes (Validation + Job)")
    
    # Invalid XOR (None)
    def test_no_scopes():
        bad_run = OCRProcessingRun(
            uploaded_document_id=doc.id,
            validation_case_id=None,
            processing_job_id=None,
            execution_role="PRIMARY",
            engine="v2",
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            run_dedup_key="e" * 64
        )
        db.add(bad_run)
    assert_raises(db, test_no_scopes, msg="No scopes")
    
    # 1. Duplicación de run_dedup_key
    def test_duplicate_run_dedup():
        dup = OCRProcessingRun(
            uploaded_document_id=doc.id,
            processing_job_id=job.id,
            execution_role="PRIMARY",
            engine="v2",
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            run_dedup_key=run_dedup_1
        )
        db.add(dup)
    assert_raises(db, test_duplicate_run_dedup, msg="Duplicate run_dedup_key")

    # 2. Duplicación de rq_job_id no nulo
    rq_id = "job-123"
    valid_run.rq_job_id = rq_id
    db.commit()
    
    def test_duplicate_rq_job():
        dup = OCRProcessingRun(
            uploaded_document_id=doc.id,
            processing_job_id=job.id,
            execution_role="PRIMARY",
            engine="v2",
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            run_dedup_key="1" * 64,
            rq_job_id=rq_id
        )
        db.add(dup)
    assert_raises(db, test_duplicate_rq_job, msg="Duplicate rq_job_id")
    
    # 3. Múltiples filas con rq_job_id = NULL
    null_rq_1 = OCRProcessingRun(
        uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="PRIMARY", engine="v2",
        status="RUNNING", started_at=datetime.now(timezone.utc), run_dedup_key="2" * 64, rq_job_id=None
    )
    db.add(null_rq_1)
    db.commit()
    
    null_rq_2 = OCRProcessingRun(
        uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="PRIMARY", engine="v2",
        status="RUNNING", started_at=datetime.now(timezone.utc), run_dedup_key="3" * 64, rq_job_id=None
    )
    db.add(null_rq_2)
    db.commit()
    print("SUCCESS: Multiple rq_job_id=NULL allowed.")
    
    # 5. PRIMARY con source inválido
    def test_primary_source():
        bad = OCRProcessingRun(
            uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="PRIMARY", engine="v2",
            status="RUNNING", started_at=datetime.now(timezone.utc), run_dedup_key="4" * 64, source_run_id=valid_run.run_id
        )
        db.add(bad)
    assert_raises(db, test_primary_source, msg="PRIMARY with source")

    # 6. SHADOW sin source
    def test_shadow_no_source():
        bad = OCRProcessingRun(
            uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="SHADOW", engine="v2",
            status="RUNNING", started_at=datetime.now(timezone.utc), run_dedup_key="5" * 64, source_run_id=None
        )
        db.add(bad)
    assert_raises(db, test_shadow_no_source, msg="SHADOW without source")

    # 7. FALLBACK con engine v2
    def test_fallback_v2():
        bad = OCRProcessingRun(
            uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="FALLBACK", engine="v2",
            status="PENDING_DISPATCH", run_dedup_key="6" * 64, source_run_id=valid_run.run_id
        )
        db.add(bad)
    assert_raises(db, test_fallback_v2, msg="FALLBACK with engine v2")

    # 8. Quality status en estado no completado
    def test_quality_status_running():
        bad = OCRProcessingRun(
            uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="PRIMARY", engine="v2",
            status="RUNNING", started_at=datetime.now(timezone.utc), quality_status="APPROVED", run_dedup_key="7" * 64
        )
        db.add(bad)
    assert_raises(db, test_quality_status_running, msg="quality_status on RUNNING")

    # 9. Hash de 64 caracteres no hexadecimales
    def test_bad_hash_format():
        bad = OCRProcessingRun(
            uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="PRIMARY", engine="v2",
            status="RUNNING", started_at=datetime.now(timezone.utc), run_dedup_key="g" * 64
        )
        db.add(bad)
    assert_raises(db, test_bad_hash_format, msg="Non-hexadecimal run_dedup_key")
    
    # 10. Restricciones ON DELETE RESTRICT
    def test_delete_restrict():
        db.delete(doc)
    assert_raises(db, test_delete_restrict, msg="Delete restricted document")

    # 11. Corrida FAILED antes de comenzar (started_at=NULL)
    failed_no_start = OCRProcessingRun(
        uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="PRIMARY", engine="v2",
        status="FAILED", finished_at=datetime.now(timezone.utc), failure_code="OOM", run_dedup_key="8" * 64
    )
    db.add(failed_no_start)
    db.commit()
    print("SUCCESS: FAILED without started_at allowed.")

    # 12. Corrida COMPLETED sin quality_status
    def test_completed_no_quality():
        bad = OCRProcessingRun(
            uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="PRIMARY", engine="v2",
            status="COMPLETED", started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
            run_dedup_key="9" * 64
        )
        db.add(bad)
    assert_raises(db, test_completed_no_quality, msg="COMPLETED without quality_status")

    # 13. PRIMARY, SHADOW y FALLBACK válidos relacionados
    primary2 = OCRProcessingRun(
        uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="PRIMARY", engine="v2",
        status="FAILED", started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
        failure_code="ERR", run_dedup_key="a" * 64
    )
    db.add(primary2)
    db.commit()
    
    shadow2 = OCRProcessingRun(
        uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="SHADOW", engine="v2",
        status="COMPLETED", quality_status="APPROVED", started_at=datetime.now(timezone.utc), 
        finished_at=datetime.now(timezone.utc), source_run_id=primary2.run_id, run_dedup_key="b" * 64
    )
    db.add(shadow2)
    
    fallback2 = OCRProcessingRun(
        uploaded_document_id=doc.id, processing_job_id=job.id, execution_role="FALLBACK", engine="v1",
        status="PENDING_DISPATCH", source_run_id=primary2.run_id, run_dedup_key="2" * 63 + "f"
    )
    db.add(fallback2)
    db.commit()
    print("SUCCESS: Valid PRIMARY, SHADOW, FALLBACK relations allowed.")



    print("All tests passed.")
