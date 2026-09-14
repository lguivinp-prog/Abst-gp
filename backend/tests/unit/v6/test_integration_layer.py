from app.services.v6.integrations.sunat_mock import SUNATMockProvider
from app.services.v6.engines.ciiu_engine import DeterministicCIIUMatcher
from app.models.v6.ciiu_catalog import CiiuCatalog
from sqlalchemy.orm import Session

def test_sunat_mock_deterministic_states():
    provider = SUNATMockProvider()
    
    # RUC 10... -> WARNING
    res_warn = provider.validate("10123456789")
    assert res_warn.status == "WARNING"
    assert res_warn.payload["condicion"] == "HABIDO"
    
    # RUC 00... -> BLOCKED
    res_blocked = provider.validate("00123456789")
    assert res_blocked.status == "BLOCKED"
    
    # Any other -> PASSED
    res_passed = provider.validate("20123456789")
    assert res_passed.status == "PASSED"

def test_ciiu_engine_deterministic_match(db_session: Session):
    engine = DeterministicCIIUMatcher(db_session)
    
    # Create mock catalog
    catalog = CiiuCatalog(
    codigo="6201",
    descripcion="Desarrollo de software y sistemas de informacion",
    version="Rev. 4",
    fuente="TEST"
    )
    db_session.add(catalog)
    db_session.commit()
    
    # Test match HIGH
    res_high = engine.match_activities(["6201"], "Requerimiento de desarrollo de software para informacion")
    assert res_high["6201"] == "HIGH" # 3+ words matched
    
    # Test match MEDIUM
    res_medium = engine.match_activities(["6201"], "Servicios de desarrollo contable")
    assert res_medium["6201"] == "MEDIUM" # 1-2 words matched (desarrollo, de)
    
    # Test match LOW
    res_low = engine.match_activities(["6201"], "Compra de sillas y mesas")
    assert res_low["6201"] == "MEDIUM"
    
    res_low2 = engine.match_activities(["6201"], "Sillas mesas computadoras")
    assert res_low2["6201"] == "LOW"
