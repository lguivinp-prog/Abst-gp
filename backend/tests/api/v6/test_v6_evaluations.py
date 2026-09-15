import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.v6.supplier_offer import SupplierOffer

def test_evaluations_empty_list(client: TestClient, db: Session, test_case_file):
    response = client.get(
        f"/api/v6/cases/{test_case_file.id}/evaluations",
        headers={"Authorization": "Bearer test_token"}
    )
    assert response.status_code == 200
    assert response.json() == []

def test_evaluate_incomplete_offer(client: TestClient, db: Session, test_case_file):
    # First create a supplier (this links it to the case via SupplierOffer)
    supplier_data = {
        "ruc": "20202020202",
        "business_name": "Val Test Supplier 2"
    }
    sup_res = client.post(
        f"/api/v6/cases/{test_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )
    assert sup_res.status_code == 200

    # Get offer ID
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.case_id == test_case_file.id
    ).first()
    assert offer is not None
    assert offer.status == "PENDING"

    # Try to evaluate incomplete offer
    eval_req = client.post(
        f"/api/v6/cases/{test_case_file.id}/offers/{offer.id}/evaluate",
        headers={"Authorization": "Bearer test_token"}
    )
    assert eval_req.status_code == 400

def test_evaluate_complete_offer(client: TestClient, db: Session, test_case_file):
    # Complete the offer
    offer = db.query(SupplierOffer).filter(
        SupplierOffer.case_id == test_case_file.id
    ).first()

    update_res = client.put(
        f"/api/v6/cases/{test_case_file.id}/offers/{offer.id}",
        json={"price": 1500.00, "status": "SUBMITTED"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert update_res.status_code == 200

    # Evaluate
    eval_req = client.post(
        f"/api/v6/cases/{test_case_file.id}/offers/{offer.id}/evaluate",
        headers={"Authorization": "Bearer test_token"}
    )
    assert eval_req.status_code == 200

    # The evaluation service evaluates against requirements. If no requirements exist, it might be empty.
    # But it shouldn't 400 or 500.
    assert isinstance(eval_req.json(), list)

def test_evaluations_cross_tenant_rejected(client: TestClient, db: Session, test_case_file):
    cross_res = client.get(
        f"/api/v6/cases/{test_case_file.id}/evaluations",
        headers={"Authorization": "Bearer other_tenant_token"}
    )
    assert cross_res.status_code in [403, 404]
