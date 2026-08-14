from app.services.v6.evaluation.experience_engine import ExperienceEvaluationEngine
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.experience_evidence import ExperienceEvidence
from app.models.domain import CaseFile
from sqlalchemy.orm import Session

def test_experience_evaluation_engine_passed(db_session: Session):
    engine = ExperienceEvaluationEngine()
    
    # Mock data
    case = CaseFile(name="Exp", tenant_id="mega_tenant", type="BIENES")
    db_session.add(case)
    db_session.commit()
    
    offer = SupplierOffer(case_id=case.id, supplier_id=1, status="PENDING")
    db_session.add(offer)
    db_session.commit()
    
    ev = ExperienceEvidence(
        supplier_offer_id=offer.id, 
        document_type="Contrato", 
        raw_fragment="contrato por 10", 
        normalized_fragment="contrato por 10"
    )
    db_session.add(ev)
    db_session.commit()
    
    result = engine.evaluate_experience(db_session, offer.id, 1, "mega_tenant")
    assert result.status == "PASSED"
