import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.v6.supplier_offer import SupplierOffer

def test_selection_propose_and_get(client: TestClient, db_session: Session, reviewed_case_file):
    # Create supplier & offer
    supplier_data = {
        "ruc": "40404040404",
        "business_name": "Selection Supplier"
    }
    client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )

    offer = db_session.query(SupplierOffer).filter_by(case_id=reviewed_case_file.id).first()
    offer.status = "SUBMITTED"
    db_session.commit()

    # Propose selection
    propose_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/selection",
        json={
            "supplier_offer_id": offer.id,
            "justification_comment": "Best offer"
        },
        headers={"Authorization": "Bearer test_token"}
    )
    assert propose_res.status_code == 200
    assert propose_res.json()["status"] == "UNDER_REVIEW"

    # Get selection
    get_res = client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/selection",
        headers={"Authorization": "Bearer test_token"}
    )
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["supplier_offer_id"] == offer.id
    assert data["justification_comment"] == "Best offer"

def test_selection_approve_and_result(admin_client: TestClient, db_session: Session, reviewed_case_file):
    # Propose selection first
    supplier_data = {
        "ruc": "50505050505",
        "business_name": "Selection Supplier 2"
    }
    admin_client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer admin_token"}
    )

    offer = db_session.query(SupplierOffer).filter_by(case_id=reviewed_case_file.id).first()
    offer.status = "SUBMITTED"
    db_session.commit()

    admin_client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/selection",
        json={
            "supplier_offer_id": offer.id,
            "justification_comment": "Best offer 2"
        },
        headers={"Authorization": "Bearer admin_token"}
    )

    # Approve selection
    approve_res = admin_client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/approve",
        headers={"Authorization": "Bearer admin_token"}
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    # Get result
    result_res = admin_client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/result",
        headers={"Authorization": "Bearer admin_token"}
    )
    assert result_res.status_code == 200
    assert result_res.json()["case_id"] == reviewed_case_file.id

def test_selection_cross_tenant_rejected(other_client: TestClient, db_session: Session, reviewed_case_file):
    cross_res = other_client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/selection",
        headers={"Authorization": "Bearer other_tenant_token"}
    )
    assert cross_res.status_code in [403, 404]

def test_selection_propose_pending_rejected(client: TestClient, db_session: Session, reviewed_case_file):
    supplier_data = {
        "ruc": "60606060606",
        "business_name": "Selection Supplier 3"
    }
    client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )

    offer = db_session.query(SupplierOffer).filter_by(case_id=reviewed_case_file.id).first()
    # Ensure offer is PENDING (default behavior)
    assert offer.status == "PENDING"

    # Propose selection should fail
    propose_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/selection",
        json={
            "supplier_offer_id": offer.id,
            "justification_comment": "Try to propose PENDING offer"
        },
        headers={"Authorization": "Bearer test_token"}
    )
    assert propose_res.status_code == 400
