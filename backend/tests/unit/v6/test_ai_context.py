from app.services.v6.ai.context_builder import CaseContextBuilder
from app.models.domain import CaseFile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.supplier_offer import SupplierOffer
from sqlalchemy.orm import Session
import pytest

def test_context_builder_retrieves_clean_data(db_session: Session):
    case = CaseFile(name="AI Case", type="BIENES", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    req = CaseRequirementMatrix(case_id=case.id, type="TECHNICAL", description="RAM", value="16GB", weight=1.0)
    db_session.add(req)
    
    offer = SupplierOffer(case_id=case.id, supplier_id=1, status="PENDING")
    db_session.add(offer)
    db_session.commit()
    
    context = CaseContextBuilder.build_context(db_session, case.id)
    
    assert context["case_metadata"]["name"] == "AI Case"
    assert len(context["requirements"]) == 1
    assert context["requirements"][0]["value"] == "16GB"
    assert len(context["offers"]) == 1
    assert "evaluations" in context

def test_context_builder_fails_on_invalid_case(db_session: Session):
    with pytest.raises(ValueError, match="Case not found"):
        CaseContextBuilder.build_context(db_session, 99999)
