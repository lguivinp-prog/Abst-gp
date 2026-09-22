import pytest
from app.services.v6.engines.experience_extraction_engine import ExperienceExtractionEngine
from app.services.v6.engines.experience_evaluation_engine import ExperienceEvaluationEngine
from app.services.v6.selection.selection_service import SelectionService
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.experience_requirement import ExperienceRequirement
from app.models.v6.experience_evidence import ExperienceEvidence
from app.models.domain import CaseFile
from app.models.v6 import Supplier
from sqlalchemy.orm import Session

def test_experience_flow(db_session: Session):
    # Setup
    tenant_id = "test_tenant"
    from sqlalchemy import text
    db_session.execute(text(f"INSERT INTO tenants (id, name, created_at) VALUES ('{tenant_id}', 'Test', NOW()) ON CONFLICT DO NOTHING"))
    case = CaseFile(title="Case Exp", contract_type="SERVICIOS", tenant_id=tenant_id)
    supplier = Supplier(ruc="2055", business_name="Mock S.A.", tenant_id=tenant_id)
    db_session.add_all([case, supplier])
    db_session.commit()
    
    profile = SupplierProfile(supplier_id=supplier.id, validation_status="PARTIAL")
    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id)
    req = ExperienceRequirement(case_id=case.id, monto_requerido=100000.0)
    
    db_session.add_all([profile, offer, req])
    db_session.commit()
    
    # 1. Extraction (RAG -> Candidate)
    extractor = ExperienceExtractionEngine()
    candidates = extractor.extract_candidates(db_session, offer.id, tenant_id, case.id)
    assert len(candidates) == 1
    assert candidates[0].evidence_status == "EXTRACTED"
    
    # 2. Evaluation BEFORE validation -> should return OBSERVED
    evaluator = ExperienceEvaluationEngine()
    eval_res1 = evaluator.evaluate(db_session, offer.id, req.id)
    assert eval_res1["status"] == "OBSERVED"
    
    # 3. User validates evidence
    candidates[0].evidence_status = "VALIDATED"
    db_session.commit()
    
    # 4. Evaluation AFTER validation -> should return PASSED
    eval_res2 = evaluator.evaluate(db_session, offer.id, req.id)
    assert eval_res2["status"] == "PASSED"
    assert eval_res2["total_calculated"] == 150000.0
    
    # 5. Selection blocked because profile is PARTIAL
    with pytest.raises(PermissionError):
        SelectionService.select_supplier(db_session, offer.id, user_id=1, user_role="OPERATOR", tenant_id=tenant_id)
        
    # 6. Supervisor Override
    selected_offer = SelectionService.select_supplier(db_session, offer.id, user_id=2, user_role="SUPERVISOR", tenant_id=tenant_id, reason="Emergency procurement")
    assert selected_offer.status == "SELECTED"
