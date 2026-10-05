import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.v6.validation_request import ValidationRequest

def test_validations_empty_list(client: TestClient, db_session: Session, reviewed_case_file):
    response = client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/validations",
        headers={"Authorization": "Bearer test_token"}
    )
    assert response.status_code == 200
    assert response.json() == []

def test_validations_create_and_list(client: TestClient, db_session: Session, reviewed_case_file):
    # First create a supplier (this links it to the case via SupplierOffer)
    supplier_data = {
        "ruc": "10101010101",
        "business_name": "Val Test Supplier"
    }
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )
    assert sup_res.status_code == 200
    supplier_id = sup_res.json()["id"]

    # Request a validation
    val_req = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers/{supplier_id}/validations",
        json={"source": "SUNAT"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert val_req.status_code == 200
    validation = val_req.json()
    assert validation["supplier_id"] == supplier_id
    assert validation["source"] == "SUNAT"
    assert validation["status"] == "PENDING"
    val_id = validation["id"]

    # List validations
    list_res = client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/validations",
        headers={"Authorization": "Bearer test_token"}
    )
    assert list_res.status_code == 200
    validations = list_res.json()
    assert len(validations) == 1
    assert validations[0]["id"] == val_id

    # Get detail
    detail_res = client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/validations/{val_id}",
        headers={"Authorization": "Bearer test_token"}
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == val_id

def test_validations_supplier_not_in_case(client: TestClient, db_session: Session, reviewed_case_file):
    # Request validation for an unlinked supplier (e.g. supplier 999)
    val_req = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers/999/validations",
        json={"source": "RNP"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert val_req.status_code == 400

def test_validations_cross_tenant_rejected(other_client: TestClient, db_session: Session, reviewed_case_file):
    cross_res = other_client.get(
        f"/api/v6/cases/{reviewed_case_file.id}/validations",
        headers={"Authorization": "Bearer other_tenant_token"}
    )
    assert cross_res.status_code in [403, 404]

def test_manual_validation_create_success(client: TestClient, db_session: Session, reviewed_case_file):
    supplier_data = {"ruc": "20202020202", "business_name": "Manual Test Supplier"}
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )
    supplier_id = sup_res.json()["id"]

    val_req = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers/{supplier_id}/validations/manual",
        json={
            "source": "SUNAT",
            "result": "VALIDATED",
            "observation": "Everything is fine",
            "evidence_reference": "Test Evidence"
        },
        headers={"Authorization": "Bearer test_token"}
    )
    assert val_req.status_code == 200
    validation = val_req.json()
    assert validation["validation_mode"] == "MANUAL"
    assert validation["manual_result"] == "VALIDATED"
    assert validation["manual_observation"] == "Everything is fine"
    assert validation["status"] == "PASSED"
    assert validation["verified_by_user_id"] is not None
    assert validation["verified_at"] is not None
    assert validation["completed_at"] is not None

def test_manual_validation_invalid_source_and_observation(client: TestClient, db_session: Session, reviewed_case_file):
    supplier_data = {"ruc": "30303030303", "business_name": "Invalid Test Supplier"}
    sup_res = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers",
        json=supplier_data,
        headers={"Authorization": "Bearer test_token"}
    )
    supplier_id = sup_res.json()["id"]

    # Invalid source
    res1 = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers/{supplier_id}/validations/manual",
        json={"source": "UNKNOWN", "result": "VALIDATED", "observation": "Obs"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert res1.status_code == 422

    # Empty observation
    res2 = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers/{supplier_id}/validations/manual",
        json={"source": "SUNAT", "result": "VALIDATED", "observation": " "},
        headers={"Authorization": "Bearer test_token"}
    )
    assert res2.status_code == 422

    # Unlinked supplier
    res3 = client.post(
        f"/api/v6/cases/{reviewed_case_file.id}/suppliers/999/validations/manual",
        json={"source": "SUNAT", "result": "VALIDATED", "observation": "Obs"},
        headers={"Authorization": "Bearer test_token"}
    )
    assert res3.status_code == 400
