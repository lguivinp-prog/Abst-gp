import pytest
from app.services.v6.integrations.validation_orchestrator import SupplierValidationOrchestrator
from app.services.v6.supplier_offer_service import SupplierOfferService
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.validation_request import ValidationRequest
from app.models.v6.supplier_offer import SupplierOffer
from app.models.domain import CaseFile
from sqlalchemy.orm import Session

def test_external_validation_hybrid_fallback(db_session: Session):
    # API keys are missing in the environment by default, so it triggers fallback logic
    supplier = Supplier(ruc="20555555555", business_name="Supplier S.A.", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    
    # 1. Run without fallback (API keys missing) -> Expect MANUAL_REQUIRED or WARNING
    orchestrator = SupplierValidationOrchestrator()
    orchestrator.run_async_validation(db_session, supplier.id)
    
    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    assert profile.status_summary in ["WARNING", "MANUAL_REQUIRED"]
    
    # 2. Run with Fallback (Simulating parsed Anexo 4 data)
    fallback = {
        "SUNAT": {"estado": "ACTIVO"},
        "FUP": {"sancionado": False},
        "RNP": {"vigente": True}
    }
    
    orchestrator.run_async_validation(db_session, supplier.id, fallback_evidence=fallback)
    
    profile2 = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    assert profile2.status_summary == "VERIFIED"
    
    # Verify Requests
    # Verify Requests
    reqs = (
        db_session.query(ValidationRequest)
        .filter_by(supplier_id=supplier.id)
        .order_by(ValidationRequest.id.asc())
        .all()
    )

    assert len(reqs) == 6

    first_run = reqs[:3]
    second_run = reqs[-3:]

    assert any(
        r.status in ["WARNING", "MANUAL_REQUIRED"]
        for r in first_run
    )

    assert all(
        r.status == "PASSED"
        for r in second_run
    )

def test_anexo4_auto_trigger(db_session: Session):
    # Setup
    supplier = Supplier(ruc="10444444444", business_name="Supplier 2", tenant_id="mega_tenant")
    case = CaseFile(title="Case External", contract_type="BIENES", tenant_id="mega_tenant")
    db_session.add_all([supplier, case])
    db_session.commit()
    
    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, status="PENDING")
    db_session.add(offer)
    db_session.commit()
    
    fallback_data = {
        "SUNAT": {"estado": "ACTIVO"},
        "FUP": {"sancionado": False},
        "RNP": {"vigente": True}
    }
    
    # Trigger Anexo 4 adding
    SupplierOfferService.add_evidence(
        db=db_session, 
        offer_id=offer.id, 
        evidence_type="ANEXO_4", 
        file_path="/docs/anexo4.pdf", 
        user_id=1, 
        extracted_data=fallback_data
    )
    
    # Validation orchestrator should have been triggered synchronously (mocked celery)
    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    assert profile is not None
    assert profile.status_summary == "VERIFIED"
