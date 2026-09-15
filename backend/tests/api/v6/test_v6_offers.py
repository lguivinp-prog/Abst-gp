import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer

def test_offers_empty_list(client: TestClient, db: Session, test_case_file):
    response = client.get(
        f"/api/v6/cases/{test_case_file.id}/offers",
        headers={"Authorization": "Bearer test_token"}
    )
    assert response.status_code == 200
    assert response.json() == []

def test_offers_create_and_list(client: TestClient, db: Session, test_case_file):
    # First create a supplier
    supplier_data = {
        "ruc": "11111111111",
        "business_name": "Test Supplier"
    }
    sup_res = client.post(
        f"/api/v6/cases/{test_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )
    assert sup_res.status_code == 200
    supplier_id = sup_res.json()["id"]

    # Check that an offer was created automatically by Phase 4A (progressive)
    list_res = client.get(
        f"/api/v6/cases/{test_case_file.id}/offers",
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
        f"/api/v6/cases/{test_case_file.id}/offers/{offer_id}",
        json={"price": 1500.50, "status": "PENDING"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res.status_code == 200
    assert update_res.json()["price"] == 1500.50

    # Cross tenant check
    cross_res = client.get(
        f"/api/v6/cases/{test_case_file.id}/offers",
        headers={"Authorization": "Bearer other_tenant_token"}
    )
    # The user should not have access to the case
    assert cross_res.status_code == 403 or cross_res.status_code == 404

def test_offers_cross_case_not_modifiable(client: TestClient, db: Session, test_case_file):
    # Create an offer
    sup_res = client.post(
        f"/api/v6/cases/{test_case_file.id}/suppliers",
        json={"ruc": "22222222222", "business_name": "Test Supplier 2"},
        headers={"Authorization": "Bearer test_token"}
    )
    supplier_id = sup_res.json()["id"]
    list_res = client.get(f"/api/v6/cases/{test_case_file.id}/offers", headers={"Authorization": "Bearer test_token"})
    offers = list_res.json()
    offer_id = [o for o in offers if o["supplier_id"] == supplier_id][0]["id"]

    # Try to modify with another case_id
    update_res = client.put(
        f"/api/v6/cases/999/offers/{offer_id}",
        json={"price": 2000.00},
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res.status_code == 403 or update_res.status_code == 404

def test_offers_delete(client: TestClient, db: Session, test_case_file):
    sup_res = client.post(
        f"/api/v6/cases/{test_case_file.id}/suppliers",
        json={"ruc": "33333333333", "business_name": "Test Supplier 3"},
        headers={"Authorization": "Bearer test_token"}
    )
    supplier_id = sup_res.json()["id"]
    list_res = client.get(f"/api/v6/cases/{test_case_file.id}/offers", headers={"Authorization": "Bearer test_token"})
    offer_id = [o for o in list_res.json() if o["supplier_id"] == supplier_id][0]["id"]

    del_res = client.delete(
        f"/api/v6/cases/{test_case_file.id}/offers/{offer_id}",
        headers={"Authorization": "Bearer test_token"}
    )
    assert del_res.status_code == 200

    list_res2 = client.get(f"/api/v6/cases/{test_case_file.id}/offers", headers={"Authorization": "Bearer test_token"})
    assert offer_id not in [o["id"] for o in list_res2.json()]
