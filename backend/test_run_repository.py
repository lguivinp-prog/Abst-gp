import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.domain import Base, UploadedDocument, ValidationDocumentCase, OCRProcessingRun
from app.services.ocr.run_repository import OCRRunRepository

# Connection for tests
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://abst_user:abst_password@db:5432/test_alembic_v2")

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    # We do not drop tables so we can debug, but each test uses a transaction

@pytest.fixture
def session(setup_database):
    session = TestingSessionLocal()
    # Create test data
    doc1 = UploadedDocument(original_filename="doc1.pdf", document_type="requirement", stored_path="/tmp/1.pdf", mime_type="application/pdf")
    doc2 = UploadedDocument(original_filename="doc2.pdf", document_type="requirement", stored_path="/tmp/2.pdf", mime_type="application/pdf")
    session.add_all([doc1, doc2])
    session.flush()
    
    val_case = ValidationDocumentCase(
        validation_run_id="00000000-0000-0000-0000-000000000001",
        uploaded_document_id=doc1.id,
        pdf_sha256="a"*64,
        request_idempotency_key="a"*64
    )
    val_case_diff_doc = ValidationDocumentCase(
        validation_run_id="00000000-0000-0000-0000-000000000002",
        uploaded_document_id=doc2.id,
        pdf_sha256="b"*64,
        request_idempotency_key="b"*64
    )
    session.add_all([val_case, val_case_diff_doc])
    session.commit()
    
    yield session, doc1, doc2, val_case, val_case_diff_doc
    
    session.rollback()
    for run in session.query(OCRProcessingRun).all():
        session.delete(run)
    for vc in session.query(ValidationDocumentCase).all():
        session.delete(vc)
    for doc in session.query(UploadedDocument).all():
        session.delete(doc)
    session.commit()
    session.close()

def test_create_primary_success(session):
    sess, doc1, doc2, val_case, val_case_diff_doc = session
    repo = OCRRunRepository(sess)
    
    run = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="PRIMARY",
        engine="v1",
        status="PENDING_DISPATCH",
        run_dedup_key="c"*64
    )
    saved_run = repo.create_run(run)
    sess.commit()
    assert saved_run.run_id is not None

def test_create_run_wrong_document(session):
    sess, doc1, doc2, val_case, val_case_diff_doc = session
    repo = OCRRunRepository(sess)
    
    run = OCRProcessingRun(
        uploaded_document_id=doc2.id, # Wrong document!
        validation_case_id=val_case.case_id,
        execution_role="PRIMARY",
        engine="v1",
        status="PENDING_DISPATCH",
        run_dedup_key="d"*64
    )
    with pytest.raises(ValueError, match="OCRProcessingRun document does not match ValidationDocumentCase document"):
        repo.create_run(run)

def test_shadow_creates_fallback_blocked(session):
    sess, doc1, doc2, val_case, val_case_diff_doc = session
    repo = OCRRunRepository(sess)
    
    # Create PRIMARY run first
    primary = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="PRIMARY",
        engine="v1",
        status="COMPLETED",
        started_at="2026-07-14T00:00:00Z",
        finished_at="2026-07-14T00:00:01Z",
        quality_status="APPROVED",
        run_dedup_key="c1"*32
    )
    sess.add(primary)
    sess.flush()
    
    # Create SHADOW run
    shadow_run = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="SHADOW",
        engine="v2",
        status="FAILED",
        failure_code="OOM",
        finished_at="2026-07-14T00:00:00Z",
        source_run_id=primary.run_id,
        run_dedup_key="e"*64
    )
    sess.add(shadow_run)
    sess.flush()
    
    # Try to create FALLBACK from SHADOW
    fallback = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="FALLBACK",
        engine="v1",
        status="PENDING_DISPATCH",
        source_run_id=shadow_run.run_id,
        run_dedup_key="f"*64
    )
    with pytest.raises(ValueError, match="Source run must have role PRIMARY."):
        repo.create_run(fallback)

def test_fallback_origin_must_be_v2_and_failed(session):
    sess, doc1, doc2, val_case, val_case_diff_doc = session
    repo = OCRRunRepository(sess)
    
    # Create PRIMARY v1
    primary_v1 = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="PRIMARY",
        engine="v1",
        status="FAILED",
        failure_code="OOM",
        finished_at="2026-07-14T00:00:00Z",
        run_dedup_key="a1"*32
    )
    sess.add(primary_v1)
    sess.flush()
    
    # Try to create FALLBACK from PRIMARY v1 (should be blocked, must be from v2)
    fallback_from_v1 = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="FALLBACK",
        engine="v1",
        status="PENDING_DISPATCH",
        source_run_id=primary_v1.run_id,
        run_dedup_key="a2"*32
    )
    with pytest.raises(ValueError, match="FALLBACK runs must originate from a v2 source"):
        repo.create_run(fallback_from_v1)
        
    # Create PRIMARY v2 (COMPLETED)
    primary_v2 = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="PRIMARY",
        engine="v2",
        status="COMPLETED",
        failure_code=None,
        started_at="2026-07-14T00:00:00Z",
        finished_at="2026-07-14T00:00:01Z",
        quality_status="APPROVED",
        run_dedup_key="a3"*32
    )
    sess.add(primary_v2)
    sess.flush()
    
    # Try to create FALLBACK from successful PRIMARY v2
    fallback_from_success = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="FALLBACK",
        engine="v1",
        status="PENDING_DISPATCH",
        source_run_id=primary_v2.run_id,
        run_dedup_key="a4"*32
    )
    with pytest.raises(ValueError, match="FALLBACK runs must originate from a FAILED source"):
        repo.create_run(fallback_from_success)

def test_shadow_wrong_scope(session):
    sess, doc1, doc2, val_case, val_case_diff_doc = session
    repo = OCRRunRepository(sess)
    
    # Create PRIMARY on val_case
    primary = OCRProcessingRun(
        uploaded_document_id=doc1.id,
        validation_case_id=val_case.case_id,
        execution_role="PRIMARY",
        engine="v1",
        status="COMPLETED",
        started_at="2026-07-14T00:00:00Z",
        finished_at="2026-07-14T00:00:01Z",
        quality_status="APPROVED",
        run_dedup_key="a5"*32
    )
    sess.add(primary)
    sess.flush()
    
    # Try to create SHADOW for it but on a DIFFERENT val_case
    shadow = OCRProcessingRun(
        uploaded_document_id=doc2.id, # Wrong doc
        validation_case_id=val_case_diff_doc.case_id, # Wrong scope
        execution_role="SHADOW",
        engine="v2",
        status="PENDING_DISPATCH",
        source_run_id=primary.run_id,
        run_dedup_key="a6"*32
    )
    with pytest.raises(ValueError, match="Source run document does not match this run's document"):
        repo.create_run(shadow)
        
    shadow.uploaded_document_id = doc1.id
    with pytest.raises(ValueError, match="OCRProcessingRun document does not match ValidationDocumentCase document"):
        repo.create_run(shadow)
        
    shadow.validation_case_id = val_case.case_id # Now it matches doc1, let's see if the source scope is caught
    shadow.processing_job_id = 999 # Add a diff scope
    with pytest.raises(ValueError, match="Source run scope does not match this run's scope"):
        repo.create_run(shadow)

if __name__ == "__main__":
    pytest.main(["-v", __file__])
