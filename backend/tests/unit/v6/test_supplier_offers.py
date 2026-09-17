import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.domain import CaseFile
from app.models.v6.case_procurement_item import CaseProcurementItem
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier import Supplier
from app.services.v6.supplier_offer_service import SupplierOfferService
from app.api.routers.v6_offers import SupplierOfferCreate, SupplierOfferItemCreate

def test_cross_case_validation(db_session: Session):
    case1 = CaseFile(title="Case 1", contract_type="BIENES", tenant_id="mega_tenant")
    case2 = CaseFile(title="Case 2", contract_type="BIENES", tenant_id="mega_tenant")
    db_session.add(case1)
    db_session.add(case2)
    db_session.commit()

    item1 = CaseProcurementItem(case_id=case1.id, description="Item 1", quantity=10, unit="UN")
    item2 = CaseProcurementItem(case_id=case2.id, description="Item 2", quantity=5, unit="UN")
    db_session.add(item1)
    db_session.add(item2)
    
    supplier = Supplier(id=1, business_name="Supplier 1", ruc="11111111111", tenant_id="mega_tenant")
    db_session.merge(supplier)
    db_session.commit()

    # Attempt to create an offer in Case 1 using an item from Case 2
    create_data = SupplierOfferCreate(
        supplier_id=1,
        currency="PEN",
        items=[
            SupplierOfferItemCreate(procurement_item_id=item2.id, unit_price=10.0)
        ]
    )
    
    with pytest.raises(ValueError) as excinfo:
        SupplierOfferService.attach_offer(db_session, case1.id, 1, 1, "mega_tenant", create_data.model_dump())
    
    assert "is invalid or does not belong to the case" in str(excinfo.value)

def test_duplicate_item_validation(db_session: Session):
    case1 = CaseFile(title="Case 1", contract_type="BIENES", tenant_id="mega_tenant")
    db_session.add(case1)
    db_session.commit()

    item1 = CaseProcurementItem(case_id=case1.id, description="Item 1", quantity=10, unit="UN")
    db_session.add(item1)
    
    supplier = Supplier(id=1, business_name="Supplier 1", ruc="11111111111", tenant_id="mega_tenant")
    db_session.merge(supplier)
    db_session.commit()

    # Attempt to create an offer with duplicate items
    create_data = SupplierOfferCreate(
        supplier_id=1,
        currency="PEN",
        items=[
            SupplierOfferItemCreate(procurement_item_id=item1.id, unit_price=10.0),
            SupplierOfferItemCreate(procurement_item_id=item1.id, unit_price=15.0)
        ]
    )
    
    with pytest.raises(ValueError) as excinfo:
        SupplierOfferService.attach_offer(db_session, case1.id, 1, 1, "mega_tenant", create_data.model_dump())
    
    assert "is duplicated in the request" in str(excinfo.value)

def test_monetary_exactitude(db_session: Session):
    case1 = CaseFile(title="Case 1", contract_type="BIENES", tenant_id="mega_tenant")
    db_session.add(case1)
    db_session.commit()

    item1 = CaseProcurementItem(case_id=case1.id, description="Item 1", quantity=10.1234, unit="UN")
    db_session.add(item1)
    
    supplier = Supplier(id=1, business_name="Supplier 1", ruc="11111111111", tenant_id="mega_tenant")
    db_session.merge(supplier)
    db_session.commit()

    # Create offer with an item
    create_data = SupplierOfferCreate(
        supplier_id=1,
        currency="PEN",
        items=[
            SupplierOfferItemCreate(procurement_item_id=item1.id, unit_price=20.55)
        ]
    )
    
    offer = SupplierOfferService.attach_offer(db_session, case1.id, 1, 1, "mega_tenant", create_data.model_dump())
    
    assert len(offer.items) == 1
    assert float(offer.items[0].subtotal) == pytest.approx(10.1234 * 20.55, rel=1e-5)
    assert round(float(offer.total_amount), 2) == round(float(offer.items[0].subtotal), 2)
