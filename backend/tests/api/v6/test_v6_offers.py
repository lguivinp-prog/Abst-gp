import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer

def test_offers_empty_list(client: TestClient, db_session: Session, reviewed_case_file):
    response = client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/offers",
        headers={"Authorization": "Bearer test_token"}
    )
    assert response.status_code == 200
    assert response.json() == []

def test_offers_create_and_list(client: TestClient, db_session: Session, reviewed_case_file):
    # First create a supplier
    supplier_data = {
        "ruc": "11111111111",
        "business_name": "Test Supplier"
    }
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )
    assert sup_res.status_code == 200
    supplier_id = sup_res.json()["id"]

    # Check that an offer was created automatically by Phase 4A (progressive)
    list_res = client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/offers",
        headers={"Authorization": "Bearer test_token"}
    )
    assert list_res.status_code == 200
    offers = list_res.json()
    assert len(offers) == 1
    offer_id = offers[0]["id"]
    assert offers[0]["supplier_id"] == supplier_id
    assert offers[0]["price"] is None

    # Update the offer with price
    update_res = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={"price": 1500.50, "status": "PENDING"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res.status_code == 200
    assert update_res.json()["price"] == 1500.50

def test_offers_update_with_documents(client: TestClient, db_session: Session, reviewed_case_file):
    # Create supplier
    supplier_data = {"ruc": "11111111111", "business_name": "Test Supplier"}
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )
    assert sup_res.status_code == 200
    supplier_id = sup_res.json()["id"]

    list_res = client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/offers",
        headers={"Authorization": "Bearer test_token"}
    )
    offers = list_res.json()
    offer_id = offers[0]["id"]

    from app.models.domain import UploadedDocument
    doc = UploadedDocument(
        case_id=reviewed_case_file.id,
        document_type="oferta",
        original_filename="offer.pdf",
        stored_path="test/offer.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # Test update with document_ids
    update_res = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={"document_ids": [doc.id]},
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert len(data["documents"]) == 1
    assert data["documents"][0]["document_id"] == doc.id

    # Test update with document_ids = []
    update_res_empty = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={"document_ids": []},
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res_empty.status_code == 200
    data_empty = update_res_empty.json()
    assert len(data_empty["documents"]) == 0

def test_offers_cross_tenant_check(other_client: TestClient, db_session: Session, reviewed_case_file):
    # Cross tenant check
    cross_res = other_client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/offers",
        headers={"Authorization": "Bearer other_tenant_token"}
    )
    # The user should not have access to the case
    assert cross_res.status_code == 403 or cross_res.status_code == 404

def test_offers_cross_case_not_modifiable(client: TestClient, db_session: Session, reviewed_case_file):
    # Create an offer
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json={"ruc": "22222222222", "business_name": "Test Supplier 2"},
        headers={"Authorization": "Bearer test_token"}
    )
    supplier_id = sup_res.json()["id"]
    list_res = client.get(f"/api/v6/cases/{reviewed_case_file.id}/offers", headers={"Authorization": "Bearer test_token"})
    offers = list_res.json()
    offer_id = [o for o in offers if o["supplier_id"] == supplier_id][0]["id"]

    # Try to modify with another case_id
    update_res = client.put(
        f"/api/v6/cases/999/offers/{offer_id}",
        json={"price": 2000.00},
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res.status_code == 403 or update_res.status_code == 404

def test_offers_delete(client: TestClient, db_session: Session, reviewed_case_file):
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json={"ruc": "33333333333", "business_name": "Test Supplier 3"},
        headers={"Authorization": "Bearer test_token"}
    )
    supplier_id = sup_res.json()["id"]
    list_res = client.get(f"/api/v6/cases/{reviewed_case_file.id}/offers", headers={"Authorization": "Bearer test_token"})
    offer_id = [o for o in list_res.json() if o["supplier_id"] == supplier_id][0]["id"]

    del_res = client.delete(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        headers={"Authorization": "Bearer test_token"}
    )
    assert del_res.status_code == 200

    list_res2 = client.get(f"/api/v6/cases/{reviewed_case_file.id}/offers", headers={"Authorization": "Bearer test_token"})
    assert offer_id not in [o["id"] for o in list_res2.json()]

def test_offers_itemized_calculations_and_rollback(client: TestClient, db_session: Session, reviewed_case_file):
    from app.models.v6.case_procurement_item import CaseProcurementItem
    # Create procurement items
    pi1 = CaseProcurementItem(case_id=reviewed_case_file.id, item_number="1", description="Item 1", quantity=10, unit="UNIDAD")
    pi2 = CaseProcurementItem(case_id=reviewed_case_file.id, item_number="2", description="Item 2", quantity=5, unit="CAJA")
    db_session.add(pi1)
    db_session.add(pi2)
    db_session.commit()
    db_session.refresh(pi1)
    db_session.refresh(pi2)

    # Create supplier and get offer
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json={"ruc": "44444444444", "business_name": "Test Supplier 4"},
        headers={"Authorization": "Bearer test_token"}
    )
    supplier_id = sup_res.json()["id"]
    list_res = client.get(f"/api/v6/cases/{reviewed_case_file.id}/offers", headers={"Authorization": "Bearer test_token"})
    offer_id = [o for o in list_res.json() if o["supplier_id"] == supplier_id][0]["id"]

    # A) Calculation & D) Server-side authority
    # Send client total_amount = 999.99, but server should recalculate
    # 10 * 12.50 = 125.00
    # 5 * 20.00 = 100.00
    # Total should be 225.00
    update_res = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={
            "total_amount": 999.99,
            "currency": "USD",
            "items": [
                {"procurement_item_id": pi1.id, "unit_price": 12.50},
                {"procurement_item_id": pi2.id, "unit_price": 20.00}
            ]
        },
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["currency"] == "USD"
    # Check if calculation is correct and total_amount sent by client is ignored
    assert float(data["total_amount"]) == 225.00
    assert len(data["items"]) == 2

    # B) Update idempotency & C) No duplicate items
    # Sending again with different prices should replace them
    update_res2 = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={
            "items": [
                {"procurement_item_id": pi1.id, "unit_price": 10.00},
                {"procurement_item_id": pi2.id, "unit_price": 10.00}
            ]
        },
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res2.status_code == 200
    data2 = update_res2.json()
    assert float(data2["total_amount"]) == 150.00
    assert len(data2["items"]) == 2

    # Check database to ensure no duplicates
    from app.models.v6.supplier_offer_item import SupplierOfferItem
    offer_items_count = db_session.query(SupplierOfferItem).filter_by(supplier_offer_id=offer_id).count()
    assert offer_items_count == 2

    # E) Rollback on invalid item
    update_res3 = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={
            "items": [
                {"procurement_item_id": pi1.id, "unit_price": 10.00},
                {"procurement_item_id": 99999, "unit_price": 10.00} # Invalid item
            ]
        },
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res3.status_code == 403
    # Check that it rolled back to previous valid state
    db_session.rollback() # just to clear any aborted transaction state
    offer_items_count = db_session.query(SupplierOfferItem).filter_by(supplier_offer_id=offer_id).count()
    assert offer_items_count == 2

def test_offer_items_contract_semantics(client: TestClient, db_session: Session, reviewed_case_file):
    from app.models.v6.case_procurement_item import CaseProcurementItem
    from app.models.v6.supplier_offer_item import SupplierOfferItem
    from app.models.v6.supplier_offer import SupplierOffer

    # Setup procurement items
    pi1 = CaseProcurementItem(
        case_id=reviewed_case_file.id,
        item_number="001",
        description="Monitor 27 inch",
        quantity=5.0,
        unit="UND"
    )
    pi2 = CaseProcurementItem(
        case_id=reviewed_case_file.id,
        item_number="002",
        description="Teclado mecanico",
        quantity=10.0,
        unit="UND"
    )
    db_session.add_all([pi1, pi2])
    db_session.commit()
    db_session.refresh(pi1)
    db_session.refresh(pi2)

    # Create supplier and offer
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json={"ruc": "20555666777", "business_name": "Tech Detail SAC"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert sup_res.status_code == 200
    offers = client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/offers",
        headers={"Authorization": "Bearer test_token"}
    ).json()
    offer_id = offers[0]["id"]

    # Initial detail substitution: 5*100 + 10*50 = 1000.00
    res_sub = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={
            "price": 1000.00,
            "currency": "PEN",
            "items": [
                {"procurement_item_id": pi1.id, "unit_price": 100.00},
                {"procurement_item_id": pi2.id, "unit_price": 50.00}
            ]
        },
        headers={"Authorization": "Bearer test_token"}
    )
    assert res_sub.status_code == 200
    data = res_sub.json()
    assert float(data["total_amount"]) == 1000.00
    assert len(data["items"]) == 2

    # Case 1: items OMITIDO (partial update: only change status) -> items and total_amount MUST be preserved
    res_omitted = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={"status": "UNDER_REVIEW"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert res_omitted.status_code == 200
    data_omitted = res_omitted.json()
    assert data_omitted["status"] == "UNDER_REVIEW"
    assert float(data_omitted["total_amount"]) == 1000.00
    assert len(data_omitted["items"]) == 2
    assert db_session.query(SupplierOfferItem).filter_by(supplier_offer_id=offer_id).count() == 2

    # Case 2: items = null (explicit null) -> items and total_amount MUST be preserved
    res_null = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={"items": None, "source_document": "cotizacion_v2.pdf"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert res_null.status_code == 200
    data_null = res_null.json()
    assert data_null["source_document"] == "cotizacion_v2.pdf"
    assert float(data_null["total_amount"]) == 1000.00
    assert len(data_null["items"]) == 2
    assert db_session.query(SupplierOfferItem).filter_by(supplier_offer_id=offer_id).count() == 2

    # Case 3: items = [] (empty list without clear_items) -> MUST NOT delete existing items
    res_empty = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={"items": []},
        headers={"Authorization": "Bearer test_token"}
    )
    assert res_empty.status_code == 200
    data_empty = res_empty.json()
    assert float(data_empty["total_amount"]) == 1000.00
    assert len(data_empty["items"]) == 2
    assert db_session.query(SupplierOfferItem).filter_by(supplier_offer_id=offer_id).count() == 2

    # Case 4: Detail substitution with new prices (5*120 + 10*40 = 1000.00)
    res_sub2 = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={
            "items": [
                {"procurement_item_id": pi1.id, "unit_price": 120.00},
                {"procurement_item_id": pi2.id, "unit_price": 40.00}
            ]
        },
        headers={"Authorization": "Bearer test_token"}
    )
    assert res_sub2.status_code == 200
    data_sub2 = res_sub2.json()
    assert float(data_sub2["total_amount"]) == 1000.00
    assert len(data_sub2["items"]) == 2
    items_in_db = db_session.query(SupplierOfferItem).filter_by(supplier_offer_id=offer_id).all()
    assert len(items_in_db) == 2
    prices = {it.procurement_item_id: float(it.unit_price) for it in items_in_db}
    assert prices[pi1.id] == 120.00
    assert prices[pi2.id] == 40.00

    # Case 5: Explicit clearing: clear_items = True -> Clears items and sets total_amount = None
    res_clear = client.put(
        f"/api/v6/cases/{reviewed_case_file.id}/offers/{offer_id}",
        json={"clear_items": True},
        headers={"Authorization": "Bearer test_token"}
    )
    assert res_clear.status_code == 200
    data_clear = res_clear.json()
    assert data_clear["total_amount"] is None
    assert len(data_clear["items"]) == 0
    assert db_session.query(SupplierOfferItem).filter_by(supplier_offer_id=offer_id).count() == 0

    # Case 6: Selection blocked when case requires procurement items and offer detail was cleared
    sel_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/selection",
        json={"supplier_offer_id": offer_id, "justification_comment": "Propuesta sin detalle"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert sel_res.status_code == 400
    assert "Incomplete offer" in sel_res.json()["detail"]
