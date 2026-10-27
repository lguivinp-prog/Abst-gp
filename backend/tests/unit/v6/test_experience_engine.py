from app.services.v6.evaluation.experience_engine import ExperienceEvaluationEngine
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.experience_evidence import ExperienceEvidence
from app.models.domain import CaseFile, User
from sqlalchemy.orm import Session

def test_experience_evaluation_engine_passed(db_session: Session):
    engine = ExperienceEvaluationEngine()
    
    # Mock data
    case = CaseFile(title="Exp", tenant_id="mega_tenant", contract_type="BIENES")
    supplier = Supplier(ruc="20999888777", business_name="Proveedor Experiencia S.A.", tenant_id="mega_tenant")
    user = db_session.query(User).filter_by(tenant_id="mega_tenant").first()
    if not user:
        user = User(username="eval_test_user", password_hash="dummy", role="operator", tenant_id="mega_tenant")
        db_session.add(user)
    db_session.add_all([case, supplier])
    db_session.commit()
    
    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, status="PENDING")
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
    
    result = engine.evaluate_experience(db_session, offer.id, user.id, "mega_tenant")
    assert result.status == "PASSED"
