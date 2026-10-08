import pytest
from app.models.domain import CaseFile
from app.models.v6.supplier import Supplier
from app.models.v6.case_procurement_item import CaseProcurementItem

def test_quotation_gate_enforcement(admin_client, db_session):
    # Setup Case in PROCESSING_REQUIREMENT
    case = CaseFile(
        tenant_id="mega_tenant", 
        title="Quotation Gate Test", 
        contract_type="BIENES", 
        status="PROCESSING_REQUIREMENT", 
        created_by=1
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    # Pre-create a supplier in the DB (since create_supplier doesn't take case_id and is not gated by case status)
    supplier_payload = {
        "ruc": "12345678901",
        "business_name": "Test Supplier"
    }
    res = admin_client.post("/api/v6/suppliers", json=supplier_payload)
    assert res.status_code == 200
    supplier_id = res.json()["id"]

    # Pre-create a procurement item for the offer
    item = CaseProcurementItem(
        case_id=case.id,
        item_number="1",
        description="Test item",
        quantity=5,
        unit="UNIDAD"
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    # ---------------------------------------------------------
    # SCENARIO A: PROCESSING_REQUIREMENT -> supplier link rejected
    # ---------------------------------------------------------
    link_res = admin_client.post(f"/api/v6/cases/{case.id}/suppliers", json=supplier_payload)
    assert link_res.status_code == 400
    assert "Requirement review is pending" in link_res.json()["detail"]

    # ---------------------------------------------------------
    # SCENARIO B: PROCESSING_REQUIREMENT -> offer create rejected
    # ---------------------------------------------------------
    offer_payload = {
        "supplier_id": supplier_id,
        "items": [
            {
                "procurement_item_id": item.id,
                "unit_price": 10.0
            }
        ]
    }
    offer_res = admin_client.post(f"/api/v6/cases/{case.id}/offers", json=offer_payload)
    assert offer_res.status_code == 400
    assert "Requirement review is pending" in offer_res.json()["detail"]

    # ---------------------------------------------------------
    # SCENARIO C: rejected supplier attempt has no side effect
    # ---------------------------------------------------------
    get_suppliers = admin_client.get(f"/api/v6/cases/{case.id}/suppliers")
    assert get_suppliers.status_code == 200
    assert len(get_suppliers.json()) == 0

    # ---------------------------------------------------------
    # SCENARIO D: rejected offer attempt has no side effect
    # ---------------------------------------------------------
    get_offers = admin_client.get(f"/api/v6/cases/{case.id}/offers")
    assert get_offers.status_code == 200
    assert len(get_offers.json()) == 0

    # ---------------------------------------------------------
    # SCENARIO E: WAITING_QUOTATION -> supplier link succeeds
    # ---------------------------------------------------------
    # Confirm requirements
    confirm_res = admin_client.post(f"/api/v6/cases/{case.id}/requirements/confirm")
    assert confirm_res.status_code == 200

    link_res_2 = admin_client.post(f"/api/v6/cases/{case.id}/suppliers", json=supplier_payload)
    assert link_res_2.status_code == 200
    assert link_res_2.json()["ruc"] == "12345678901"

    # ---------------------------------------------------------
    # SCENARIO F: WAITING_QUOTATION -> offer creation succeeds
    # ---------------------------------------------------------
    offer_res_2 = admin_client.post(f"/api/v6/cases/{case.id}/offers", json=offer_payload)
    assert offer_res_2.status_code == 200
    offer_id = offer_res_2.json()["id"]

    # ---------------------------------------------------------
    # SCENARIO G: confirmation followed by item edit invalidates review
    # ---------------------------------------------------------
    edit_item_res = admin_client.put(f"/api/v6/cases/{case.id}/procurement-items/{item.id}", json={
        "description": "Test item modified",
        "quantity": 10
    })
    assert edit_item_res.status_code == 200
    db_session.refresh(case)
    assert case.status == "PROCESSING_REQUIREMENT"

    # ---------------------------------------------------------
    # SCENARIO H: invalidated case cannot continue quotation mutation
    # ---------------------------------------------------------
    update_offer_payload = {
        "price": 100.0,
        "status": "APPROVED"
    }
    update_offer_res = admin_client.put(f"/api/v6/cases/{case.id}/offers/{offer_id}", json=update_offer_payload)
    assert update_offer_res.status_code == 400
    assert "Requirement review is pending" in update_offer_res.json()["detail"]

    # ---------------------------------------------------------
    # SCENARIO J: read-only supplier/offer retrieval remains available
    # ---------------------------------------------------------
    get_offers_again = admin_client.get(f"/api/v6/cases/{case.id}/offers")
    assert get_offers_again.status_code == 200
    assert len(get_offers_again.json()) > 0

    # ---------------------------------------------------------
    # SCENARIO I: reconfirmation restores ability to continue
    # ---------------------------------------------------------
    confirm_again = admin_client.post(f"/api/v6/cases/{case.id}/requirements/confirm")
    assert confirm_again.status_code == 200

    update_offer_res_2 = admin_client.put(f"/api/v6/cases/{case.id}/offers/{offer_id}", json=update_offer_payload)
    assert update_offer_res_2.status_code == 200
    assert update_offer_res_2.json()["status"] == "APPROVED"

    # ---------------------------------------------------------
    # SCENARIO K: cross-case rules remain intact
    # ---------------------------------------------------------
    # Create another case in PROCESSING_REQUIREMENT
    case2 = CaseFile(
        tenant_id="mega_tenant", 
        title="Quotation Gate Test 2", 
        contract_type="BIENES", 
        status="PROCESSING_REQUIREMENT", 
        created_by=1
    )
    db_session.add(case2)
    db_session.commit()

    link_res_case2 = admin_client.post(f"/api/v6/cases/{case2.id}/suppliers", json=supplier_payload)
    assert link_res_case2.status_code == 400

    # ---------------------------------------------------------
    # SCENARIO L: legitimate later reviewed workflow states are not accidentally rejected
    # ---------------------------------------------------------
    case.status = "COMPARING"
    db_session.commit()

    update_offer_res_3 = admin_client.put(f"/api/v6/cases/{case.id}/offers/{offer_id}", json={"price": 200.0})
    assert update_offer_res_3.status_code == 200
