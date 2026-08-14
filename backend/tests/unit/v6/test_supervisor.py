import pytest
from app.services.v6.engines.case_risk_engine import CaseRiskEngine
from app.models.v6.case_operational_snapshot import CaseOperationalSnapshot
from app.models.domain import AuditLog, CaseFile
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6 import Supplier
from sqlalchemy.orm import Session

def test_case_risk_engine(db_session: Session):
    # Setup
    case = CaseFile(name="Risk Case", type="BIENES", tenant_id="t1")
    supplier = Supplier(ruc="20000", business_name="S1", tenant_id="t1")
    db_session.add_all([case, supplier])
    db_session.commit()
    
    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id)
    profile = SupplierProfile(supplier_id=supplier.id, validation_status="BLOCKED")
    db_session.add_all([offer, profile])
    db_session.commit()
    
    engine = CaseRiskEngine()
    
    # 1. BLOCKED supplier should yield HIGH risk
    level1, reasons1 = engine.calculate_risk(db_session, case.id)
    assert level1 == "HIGH"
    assert any(r["type"] == "BLOCKED_VALIDATION" for r in reasons1)
    
    # 2. Change supplier to PENDING -> MEDIUM risk
    profile.validation_status = "PENDING"
    db_session.commit()
    
    level2, reasons2 = engine.calculate_risk(db_session, case.id)
    assert level2 == "MEDIUM"
    assert any(r["type"] == "INCOMPLETE_EVIDENCE" for r in reasons2)
    
    # 3. Add SUPERVISOR_EXCEPTION audit -> HIGH risk
    audit = AuditLog(
        user_id=1, tenant_id="t1", 
        action="SUPERVISOR_EXCEPTION_SELECT", 
        entity_type="CaseFile", 
        entity_id=str(case.id), 
        details="Override", 
        status="WARNING"
    )
    db_session.add(audit)
    db_session.commit()
    
    level3, reasons3 = engine.calculate_risk(db_session, case.id)
    assert level3 == "HIGH"
    assert any(r["type"] == "SUPERVISOR_EXCEPTION" for r in reasons3)
    
    # Snapshot update test
    snapshot = CaseOperationalSnapshot(
        case_id=case.id,
        current_status="EVALUATION",
        risk_level=level3,
        risk_reason=reasons3
    )
    db_session.add(snapshot)
    db_session.commit()
    assert snapshot.id is not None
