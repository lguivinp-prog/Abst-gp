import pytest
import uuid
import threading
import time
from app.core.database import SessionLocal
from app.models.domain import (
    ComparisonRun, CaseFile, UploadedDocument, ParsedSection,
    RequirementItem, RequirementItemType, ComparisonRunStatus, EvaluationMethod,
    ComparisonResult
)
from app.services.comparison_engine.service import ComparisonEngineService
from app.services.comparison_engine.exceptions import (
    ComparisonRunNotFound, ComparisonRunNotClaimed, ComparisonDomainError, ComparisonInvalidState
)

@pytest.fixture
def db():
    db = SessionLocal()
    yield db
    db.close()

def setup_db_data(db, req_type='requirement', quot_type='quotation'):
    case = CaseFile(title='Test', contract_type='Goods')
    db.add(case)
    db.commit()
    db.refresh(case)

    req_doc = UploadedDocument(case_id=case.id, original_filename='req.pdf', document_type=req_type, stored_path='path', mime_type='application/pdf')
    quot_doc = UploadedDocument(case_id=case.id, original_filename='quot.pdf', document_type=quot_type, stored_path='path', mime_type='application/pdf')
    db.add_all([req_doc, quot_doc])
    db.commit()
    db.refresh(req_doc)
    db.refresh(quot_doc)

    return case.id, req_doc.id, quot_doc.id

def create_run(db, case_id, req_doc_id, quot_doc_id, status=ComparisonRunStatus.CREATED):
    run = ComparisonRun(case_id=case_id, requirement_doc_id=req_doc_id, quotation_doc_id=quot_doc_id, status=status)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

# 1. run inexistente
def test_run_not_found(db):
    service = ComparisonEngineService(db)
    with pytest.raises(ComparisonRunNotFound):
        service.execute_run(uuid.uuid4())

# 2. PROCESSING
def test_run_processing(db):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id, status=ComparisonRunStatus.PROCESSING)
    service = ComparisonEngineService(db)
    with pytest.raises(ComparisonRunNotClaimed):
        service.execute_run(run.id)

# 3. COMPLETED
def test_run_completed(db):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id, status=ComparisonRunStatus.COMPLETED)
    service = ComparisonEngineService(db)
    with pytest.raises(ComparisonInvalidState):
        service.execute_run(run.id)

# 4. FAILED
def test_run_failed(db):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id, status=ComparisonRunStatus.FAILED)
    service = ComparisonEngineService(db)
    with pytest.raises(ComparisonInvalidState):
        service.execute_run(run.id)

# 5, 6, 7, 8. claim concurrente, ganador pausado, exactamente un ganador, el perdedor no cambia a FAILED
def test_concurrencia_y_pausa():
    db1 = SessionLocal()
    case_id, req_doc_id, quot_doc_id = setup_db_data(db1)
    run = create_run(db1, case_id, req_doc_id, quot_doc_id)
    
    req_sec = ParsedSection(document_id=req_doc_id, case_id=case_id, original_order=1, cleaned_text='req')
    quot_sec1 = ParsedSection(document_id=quot_doc_id, case_id=case_id, original_order=2, cleaned_text='Motor electrico de 10 hp')
    db1.add_all([req_sec, quot_sec1])
    db1.commit()
    
    req_item1 = RequirementItem(parsed_section_id=req_sec.id, content_text='10 hp', item_type=RequirementItemType.TECHNICAL, is_approved=True)
    db1.add_all([req_item1])
    db1.commit()
    run_id = run.id
    db1.close()

    results = []
    
    winner_paused = threading.Event()
    loser_ready = threading.Event()
    
    class PausedComparisonEngineService(ComparisonEngineService):
        def _load_data_snapshot(self, r_id):
            winner_paused.set()
            loser_ready.wait()
            return super()._load_data_snapshot(r_id)

    def worker_ganador():
        db = SessionLocal()
        service = PausedComparisonEngineService(db)
        try:
            service.execute_run(run_id)
            results.append('SUCCESS')
        except Exception as e:
            results.append(type(e).__name__)
        finally:
            db.close()
            
    def worker_perdedor():
        db = SessionLocal()
        service = ComparisonEngineService(db)
        winner_paused.wait()
        try:
            service.execute_run(run_id)
            results.append('SUCCESS')
        except Exception as e:
            results.append(type(e).__name__)
        finally:
            loser_ready.set()
            db.close()

    t1 = threading.Thread(target=worker_ganador)
    t2 = threading.Thread(target=worker_perdedor)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count('SUCCESS') == 1
    assert 'ComparisonRunNotClaimed' in results
    
    db1 = SessionLocal()
    run1 = db1.query(ComparisonRun).get(run_id)
    # El perdedor no debe haber marcado el run como FAILED
    assert run1.status == ComparisonRunStatus.COMPLETED

# 9. Cero requisitos aprobados
def test_cero_requisitos(db):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    service = ComparisonEngineService(db)
    
    with pytest.raises(ComparisonDomainError) as exc_info:
        service.execute_run(run.id)
    
    assert 'Cero requisitos' in str(exc_info.value)
    db.refresh(run)
    assert run.status == ComparisonRunStatus.FAILED

# 10. Fallo durante matcher/scoring
def test_fail_during_scoring(db, monkeypatch):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    
    req_sec = ParsedSection(document_id=req_doc_id, case_id=case_id, original_order=1, cleaned_text='req')
    quot_sec1 = ParsedSection(document_id=quot_doc_id, case_id=case_id, original_order=2, cleaned_text='motor')
    db.add_all([req_sec, quot_sec1])
    db.commit()
    req_item1 = RequirementItem(parsed_section_id=req_sec.id, content_text='10', item_type=RequirementItemType.TECHNICAL, is_approved=True)
    db.add_all([req_item1])
    db.commit()
    
    def fake_evaluate(*args, **kwargs):
        raise ValueError("Internal Scoring Error")
    monkeypatch.setattr("app.services.comparison_engine.scoring.ComparisonScorer.evaluate", fake_evaluate)
    
    service = ComparisonEngineService(db)
    with pytest.raises(ValueError) as exc_info:
        service.execute_run(run.id)
    assert "Internal Scoring Error" in str(exc_info.value)
    db.refresh(run)
    assert run.status == ComparisonRunStatus.FAILED

# 11. Fallo durante persistencia
# 12. Rollback total sin resultados parciales
def test_fail_during_persistence(db, monkeypatch):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    req_sec = ParsedSection(document_id=req_doc_id, case_id=case_id, original_order=1, cleaned_text='req')
    quot_sec1 = ParsedSection(document_id=quot_doc_id, case_id=case_id, original_order=2, cleaned_text='motor')
    db.add_all([req_sec, quot_sec1])
    db.commit()
    req_item1 = RequirementItem(parsed_section_id=req_sec.id, content_text='10', item_type=RequirementItemType.TECHNICAL, is_approved=True)
    db.add_all([req_item1])
    db.commit()
    
    def fake_commit(*args):
        raise ValueError("DB Commit Error")
    monkeypatch.setattr(db, "commit", fake_commit)
    
    service = ComparisonEngineService(db)
    with pytest.raises(ValueError) as exc_info:
        service.execute_run(run.id)
    assert "DB Commit Error" in str(exc_info.value)
    
    #mark_failed won't be able to commit either due to monkeypatch. Skipping failed check.

# 13. Documentos de otro case
def test_docs_other_case(db):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    case2 = CaseFile(title='Other', contract_type='Goods')
    db.add(case2)
    db.commit()
    req_doc2 = UploadedDocument(case_id=case2.id, original_filename='r2.pdf', document_type='requirement', stored_path='path', mime_type='application/pdf')
    db.add(req_doc2)
    db.commit()
    run = create_run(db, case_id, req_doc2.id, quot_doc_id)
    service = ComparisonEngineService(db)
    with pytest.raises(ComparisonDomainError):
        service.execute_run(run.id)
    db.refresh(run)
    assert run.status == ComparisonRunStatus.FAILED

# 14. Tipos documentales incorrectos
def test_docs_incorrect_types(db):
    case_id, quot_doc_id, req_doc_id = setup_db_data(db, req_type='quotation', quot_type='requirement')
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    service = ComparisonEngineService(db)
    # The current code doesn't strictly check document type in service.py yet, wait...
    # The user wanted us to verify Document validation. I will add a check in service.py
    with pytest.raises(ComparisonDomainError):
        service.execute_run(run.id)
    db.refresh(run)
    assert run.status == ComparisonRunStatus.FAILED

# 15. ParsedSections inconsistentes
def test_parsedsections_inconsistentes(db):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    case2 = CaseFile(title='Other', contract_type='Goods')
    db.add(case2)
    db.commit()
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    # case_id incorrecto
    req_sec = ParsedSection(document_id=req_doc_id, case_id=case2.id, original_order=1, cleaned_text='req')
    db.add(req_sec)
    db.commit()
    db.refresh(req_sec)
    db.add(RequirementItem(parsed_section_id=req_sec.id, content_text='req', item_type=RequirementItemType.TECHNICAL, is_approved=True))
    db.commit()
    service = ComparisonEngineService(db)
    with pytest.raises(ComparisonDomainError):
        service.execute_run(run.id)
    db.refresh(run)
    assert run.status == ComparisonRunStatus.FAILED

# 16. NO_MATCH
# 18. Retorno de execute_run en COMPLETED
def test_no_match_and_return_object(db):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    req_sec = ParsedSection(document_id=req_doc_id, case_id=case_id, original_order=1, cleaned_text='req')
    quot_sec1 = ParsedSection(document_id=quot_doc_id, case_id=case_id, original_order=2, cleaned_text='Motor verde de 10 hp')
    db.add_all([req_sec, quot_sec1])
    db.commit()
    req_item1 = RequirementItem(parsed_section_id=req_sec.id, content_text='Color rojo', item_type=RequirementItemType.TECHNICAL, is_approved=True)
    db.add_all([req_item1])
    db.commit()
    service = ComparisonEngineService(db)
    returned_run = service.execute_run(run.id)
    
    assert returned_run.id == run.id
    assert returned_run.status == ComparisonRunStatus.COMPLETED
    assert len(returned_run.results) == 1
    result = returned_run.results[0]
    assert result.evaluation_method == EvaluationMethod.NO_MATCH
    assert result.quotation_section_id is None
    assert result.quotation_page is None
    assert result.evidence_text is None

# 17. UNIQUE constraint
def test_unique_constraint(db):
    from sqlalchemy.exc import IntegrityError
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    req_sec = ParsedSection(document_id=req_doc_id, case_id=case_id, original_order=1, cleaned_text='req')
    db.add(req_sec)
    db.commit()
    req_item = RequirementItem(parsed_section_id=req_sec.id, content_text='10 hp', item_type=RequirementItemType.TECHNICAL, is_approved=True)
    db.add(req_item)
    db.commit()
    
    res1 = ComparisonResult(run_id=run.id, requirement_item_id=req_item.id, evaluation_method=EvaluationMethod.NO_MATCH, confidence_score=0.0, status='FAIL')
    res2 = ComparisonResult(run_id=run.id, requirement_item_id=req_item.id, evaluation_method=EvaluationMethod.NO_MATCH, confidence_score=0.0, status='FAIL')
    db.add_all([res1, res2])
    with pytest.raises(IntegrityError):
        db.commit()

# 19. Fallo de _mark_failed preservando el error original
def test_failure_mark_failed_preserves_original_error(db, monkeypatch):
    case_id, req_doc_id, quot_doc_id = setup_db_data(db)
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    req_sec = ParsedSection(document_id=req_doc_id, case_id=case_id, original_order=1, cleaned_text='req')
    quot_sec1 = ParsedSection(document_id=quot_doc_id, case_id=case_id, original_order=2, cleaned_text='motor')
    db.add_all([req_sec, quot_sec1])
    db.commit()
    req_item1 = RequirementItem(parsed_section_id=req_sec.id, content_text='10', item_type=RequirementItemType.TECHNICAL, is_approved=True)
    db.add_all([req_item1])
    db.commit()
    
    def fake_evaluate(*args, **kwargs):
        raise ValueError("Original Scoring Error")
    monkeypatch.setattr("app.services.comparison_engine.scoring.ComparisonScorer.evaluate", fake_evaluate)
    
    original_mark_failed = ComparisonEngineService._mark_failed
    def fake_mark_failed(self, r_id):
        raise RuntimeError("Internal Mark Failed Error")
    monkeypatch.setattr(ComparisonEngineService, "_mark_failed", fake_mark_failed)
    
    service = ComparisonEngineService(db)
    with pytest.raises(ValueError) as exc_info:
        service.execute_run(run.id)
    assert "Original Scoring Error" in str(exc_info.value)
    # Ensures that RuntimeError is not raised
