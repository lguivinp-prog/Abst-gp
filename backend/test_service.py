import sys
from uuid import uuid4
from app.core.database import SessionLocal
from app.models.domain import (
    ComparisonRun, ComparisonRunStatus, CaseFile, UploadedDocument,
    ParsedSection, RequirementItem, RequirementItemType, ComparisonResult, EvaluationMethod
)
from app.services.comparison_engine.service import ComparisonEngineService
from app.services.comparison_engine.exceptions import (
    ComparisonRunNotFound, ComparisonRunNotClaimed, ComparisonDomainError
)
import threading
import time

def setup_db():
    db = SessionLocal()
    try:
        # Create User if not exists
        from app.models.domain import User
        user = db.query(User).first()
        if not user:
            user = User(username="test_user", password_hash="hash", role="admin", is_active=True)
            db.add(user)
            db.commit()
            db.refresh(user)

        # Create Case
        case = CaseFile(title="Test Case", status="pending", contract_type="Goods", created_by=user.id)
        db.add(case)
        db.commit()
        db.refresh(case)

        # Create docs
        req_doc = UploadedDocument(case_id=case.id, original_filename="req.pdf", document_type="requirement", stored_path="path", mime_type="application/pdf")
        quot_doc = UploadedDocument(case_id=case.id, original_filename="quot.pdf", document_type="quotation", stored_path="path", mime_type="application/pdf")
        db.add_all([req_doc, quot_doc])
        db.commit()
        db.refresh(req_doc)
        db.refresh(quot_doc)

        return case.id, req_doc.id, quot_doc.id
    finally:
        db.close()

def create_run(db, case_id, req_doc_id, quot_doc_id, status=ComparisonRunStatus.CREATED):
    run = ComparisonRun(case_id=case_id, requirement_doc_id=req_doc_id, quotation_doc_id=quot_doc_id, status=status)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

def test_run_inexistente():
    print("\n--- Test 1: Run Inexistente ---")
    db = SessionLocal()
    service = ComparisonEngineService(db)
    try:
        service.execute_run(uuid4())
        print("FAIL: Expected exception")
    except ComparisonRunNotFound:
        print("PASS: ComparisonRunNotFound raised.")
    finally:
        db.close()

def test_run_not_created():
    print("\n--- Test 2: Run en estado distinto de CREATED ---")
    db = SessionLocal()
    case_id, req_doc_id, quot_doc_id = setup_db()
    run = create_run(db, case_id, req_doc_id, quot_doc_id, status=ComparisonRunStatus.PROCESSING)
    service = ComparisonEngineService(db)
    try:
        service.execute_run(run.id)
        print("FAIL: Expected exception")
    except ComparisonRunNotClaimed:
        print("PASS: ComparisonRunNotClaimed raised.")
    finally:
        db.close()

def test_concurrencia():
    print("\n--- Test 3: Dos ejecuciones concurrentes sobre el mismo run ---")
    db1 = SessionLocal()
    case_id, req_doc_id, quot_doc_id = setup_db()
    run = create_run(db1, case_id, req_doc_id, quot_doc_id)
    db1.close()

    results = []
    
    def worker_func():
        db = SessionLocal()
        service = ComparisonEngineService(db)
        try:
            service.execute_run(run.id)
            results.append("SUCCESS")
        except ComparisonRunNotClaimed:
            results.append("CLAIM_FAILED")
        except Exception as e:
            results.append(str(type(e)))
        finally:
            db.close()

    t1 = threading.Thread(target=worker_func)
    t2 = threading.Thread(target=worker_func)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    # Uno debe fallar por CLAIM_FAILED y otro por ComparisonDomainError (cero requisitos)
    if "CLAIM_FAILED" in results and "<class 'app.services.comparison_engine.exceptions.ComparisonDomainError'>" in results:
        print("PASS: Solo un worker logró reclamarlo.")
    else:
        print(f"FAIL/INFO: Results: {results}")

def test_cero_requisitos():
    print("\n--- Test 4: Cero requisitos aprobados ---")
    db = SessionLocal()
    case_id, req_doc_id, quot_doc_id = setup_db()
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    service = ComparisonEngineService(db)
    try:
        service.execute_run(run.id)
        print("FAIL: Expected exception")
    except ComparisonDomainError as e:
        print("PASS: ComparisonDomainError raised for 0 requirements.")
        # Ensure status is FAILED
        db.refresh(run)
        if run.status == ComparisonRunStatus.FAILED:
            print("PASS: Run marked as FAILED.")
        else:
            print(f"FAIL: Run status is {run.status}")
    finally:
        db.close()

def test_exito_y_no_match():
    print("\n--- Test 6 y 9: Ejecución completa y NO_MATCH ---")
    db = SessionLocal()
    case_id, req_doc_id, quot_doc_id = setup_db()
    run = create_run(db, case_id, req_doc_id, quot_doc_id)
    
    # Requirement section & item
    req_sec = ParsedSection(document_id=req_doc_id, case_id=case_id, original_order=1, cleaned_text="req")
    quot_sec1 = ParsedSection(document_id=quot_doc_id, case_id=case_id, original_order=2, cleaned_text="Motor eléctrico de 10 hp")
    quot_sec2 = ParsedSection(document_id=quot_doc_id, case_id=case_id, original_order=3, cleaned_text="Sección irrelevante")
    db.add_all([req_sec, quot_sec1, quot_sec2])
    db.commit()
    
    req_item1 = RequirementItem(parsed_section_id=req_sec.id, content_text="10 hp", item_type=RequirementItemType.TECHNICAL, is_approved=True)
    req_item2 = RequirementItem(parsed_section_id=req_sec.id, content_text="Color rojo", item_type=RequirementItemType.TECHNICAL, is_approved=True)
    db.add_all([req_item1, req_item2])
    db.commit()

    service = ComparisonEngineService(db)
    final_run = service.execute_run(run.id)
    print("PASS: Execute finished")
    
    if final_run.status == ComparisonRunStatus.COMPLETED:
        print("PASS: Status is COMPLETED")
    else:
        print("FAIL: Status is", final_run.status)
        
    results = db.query(ComparisonResult).filter_by(run_id=run.id).all()
    if len(results) == 2:
        print("PASS: 2 results generated")
        for r in results:
            if r.requirement_item_id == req_item1.id:
                if r.evaluation_method == EvaluationMethod.EXACT_MATCH:
                    print("PASS: req 1 resolved as EXACT_MATCH")
                else:
                    print("FAIL: req 1 is", r.evaluation_method)
            else:
                if r.evaluation_method == EvaluationMethod.NO_MATCH:
                    print("PASS: req 2 resolved as NO_MATCH")
                else:
                    print("FAIL: req 2 is", r.evaluation_method)
    else:
        print("FAIL: results length", len(results))
    
    db.close()

if __name__ == "__main__":
    test_run_inexistente()
    test_run_not_created()
    test_concurrencia()
    test_cero_requisitos()
    test_exito_y_no_match()
