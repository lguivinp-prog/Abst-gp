from app.services.v6.engines.accuracy_gate import ContractAccuracyGate
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.domain import CaseFile
from sqlalchemy.orm import Session

def test_accuracy_gate_fails_if_not_approved(db_session: Session):
    case = CaseFile(name="Test", type="BIENES", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    workflow = CaseWorkflow(case_id=case.id, status="UNDER_REVIEW")
    db_session.add(workflow)
    db_session.commit()
    
    result = ContractAccuracyGate.validate_for_generation(db_session, case.id)
    assert result == "ACCURACY_FAILED"

def test_accuracy_gate_fails_if_conflict_exists(db_session: Session):
    case = CaseFile(name="Test 2", type="BIENES", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    workflow = CaseWorkflow(case_id=case.id, status="APPROVED")
    db_session.add(workflow)
    
    offer = SupplierOffer(case_id=case.id, supplier_id=1, status="PENDING", evaluation_status="HAS_CONFLICTS")
    db_session.add(offer)
    db_session.commit()
    
    result = ContractAccuracyGate.validate_for_generation(db_session, case.id)
    assert result == "ACCURACY_FAILED"
