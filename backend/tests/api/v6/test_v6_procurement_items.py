import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, AuditLog
from app.models.v6.case_procurement_item import CaseProcurementItem

def test_procurement_item_auto_correlative(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    case = CaseFile(title="Correlative Test", contract_type="BIENES", status="PROCESSING_REQUIREMENT", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()

    # 1. Create first item without item_number
    res1 = admin_client.post(f"/api/v6/cases/{case.id}/procurement-items", json={
        "description": "Papel bond A4",
        "quantity": 50,
        "unit": "MILLAR"
    })
    assert res1.status_code == 200
    item1 = res1.json()
    assert item1["item_number"] == "1"

    # 2. Create second item with item_number empty string
    res2 = admin_client.post(f"/api/v6/cases/{case.id}/procurement-items", json={
        "item_number": "",
        "description": "Tóner para láser",
        "quantity": 4,
        "unit": "UNIDAD"
    })
    assert res2.status_code == 200
    item2 = res2.json()
    assert item2["item_number"] == "2"

    # 3. Create third item with custom correlative
    res3 = admin_client.post(f"/api/v6/cases/{case.id}/procurement-items", json={
        "item_number": "5",
        "description": "Cinta de embalaje",
        "quantity": 10,
        "unit": "ROLLO"
    })
    assert res3.status_code == 200
    item3 = res3.json()
    assert item3["item_number"] == "5"

    # 4. Next auto-correlative should skip to 6
    res4 = admin_client.post(f"/api/v6/cases/{case.id}/procurement-items", json={
        "description": "Clips metálicos",
        "quantity": 20,
        "unit": "CAJA"
    })
    assert res4.status_code == 200
    item4 = res4.json()
    assert item4["item_number"] == "6"

    # 5. Duplicate item_number should be rejected with controlled 409
    dup_res = admin_client.post(f"/api/v6/cases/{case.id}/procurement-items", json={
        "item_number": "1",
        "description": "Papel duplicado",
        "quantity": 5
    })
    assert dup_res.status_code == 409
    assert "Ya existe un ítem con el correlativo '1'" in dup_res.json()["detail"]

    # 6. AuditLog created for item creation
    audit = db_session.query(AuditLog).filter_by(
        entity_type="CaseProcurementItem",
        action="CREATE_PROCUREMENT_ITEM",
        entity_id=str(item1["id"])
    ).first()
    assert audit is not None
    assert "Ítem 1 registrado" in audit.details
