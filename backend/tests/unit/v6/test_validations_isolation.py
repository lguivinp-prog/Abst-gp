import pytest
from app.models.v6.validation_request import ValidationRequest
from app.models.v6.supplier_offer import SupplierOffer

def test_validation_request_isolation(db_session):
    from app.models.domain import CaseFile, Tenant
    from app.models.v6.supplier import Supplier

    # Ensure a tenant exists
    tenant = db_session.query(Tenant).first()
    if not tenant:
        tenant = Tenant(name="Test Tenant")
        db_session.add(tenant)
        db_session.commit()

    test_case = CaseFile(title="Test Case A", status="CREATED", tenant_id=tenant.id, created_by=1, contract_type="goods")
    db_session.add(test_case)
    
    test_supplier = Supplier(ruc="20000000000", business_name="Test Supplier", tenant_id=tenant.id)
    db_session.add(test_supplier)
    db_session.commit()
    case_b = CaseFile(title="Test Case B", status="CREATED", tenant_id=test_case.tenant_id, created_by=1, contract_type="goods")
    db_session.add(case_b)
    db_session.commit()

    # Link supplier to Case A
    offer_a = SupplierOffer(case_id=test_case.id, supplier_id=test_supplier.id, status="PENDING")
    db_session.add(offer_a)
    
    # Link supplier to Case B
    offer_b = SupplierOffer(case_id=case_b.id, supplier_id=test_supplier.id, status="PENDING")
    db_session.add(offer_b)
    db_session.commit()

    # Create validation for Case A
    val_a = ValidationRequest(supplier_id=test_supplier.id, case_id=test_case.id, source="SUNAT", status="PENDING")
    db_session.add(val_a)

    # Create legacy validation (no case_id)
    val_legacy = ValidationRequest(supplier_id=test_supplier.id, source="RNP", status="PENDING")
    db_session.add(val_legacy)
    db_session.commit()

    # Query using logic from get_case_validations
    validations_a = db_session.query(ValidationRequest).filter(
        ValidationRequest.supplier_id == test_supplier.id,
        ValidationRequest.case_id == test_case.id
    ).all()

    validations_b = db_session.query(ValidationRequest).filter(
        ValidationRequest.supplier_id == test_supplier.id,
        ValidationRequest.case_id == case_b.id
    ).all()

    assert len(validations_a) == 1
    assert validations_a[0].source == "SUNAT"
    assert len(validations_b) == 0
