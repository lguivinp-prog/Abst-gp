import pytest
from app.models.domain import CaseFile, UploadedDocument
from app.models.v6.case_procurement_item import CaseProcurementItem
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix

def test_v6_extraction_api_endpoint(admin_client, db_session):
    # Setup case
    case = CaseFile(tenant_id="mega_tenant", title="V6 API Extraction", contract_type="BIENES", status="DRAFT", created_by=1)
    db_session.add(case)
    db_session.commit()

    # Pre-populate a document with "extracted text" simulating OCR
    text_extracted = """
3. CARACTERÍSTICAS TÉCNICAS DE LOS BIENES
ITEM CANTIDAD DESCRIPCIÓN UNIDAD MEDIDA
1 3 Tinta original para EPSON L14150 COD. REF. 504 - NEGRO UNIDAD
2 2 Tinta original para EPSON L14150 COD. REF. 504 - CIAN UNIDAD

4. PLAZO DE ENTREGA
El contratista deberá proveer los bienes en 5 días.
"""
    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="golden_test_uat.pdf",
        stored_path="test/path.pdf",
        mime_type="application/pdf",
        text_extracted=text_extracted,
        processing_status="finished"
    )
    db_session.add(doc)
    db_session.commit()

    # Hit the extraction endpoint
    response = admin_client.post(f"/api/v6/cases/{case.id}/requirements/extract", json={"document_id": doc.id})
    assert response.status_code == 200, response.text

    # Assert Items were created
    items = db_session.query(CaseProcurementItem).filter_by(case_id=case.id).all()
    assert len(items) == 2, "Expected exactly 2 procurement items to be created in DB"
    assert items[0].item_number == "1"
    assert items[0].quantity == 3.0
    assert items[1].item_number == "2"
    assert items[1].quantity == 2.0

    # Assert requirements were created
    reqs = db_session.query(CaseRequirementMatrix).filter_by(case_id=case.id).all()
    assert len(reqs) >= 1

def test_v6_requirement_confirmation_flow(admin_client, db_session):
    # Setup case
    case = CaseFile(tenant_id="mega_tenant", title="Review Flow", contract_type="BIENES", status="CREATED", created_by=1)
    db_session.add(case)
    db_session.commit()

    # 1. Cannot confirm if not processing requirement
    res = admin_client.post(f"/api/v6/cases/{case.id}/requirements/confirm")
    assert res.status_code == 400

    # set status to processing requirement
    case.status = "PROCESSING_REQUIREMENT"
    db_session.commit()

    # 2. Confirm -> goes to WAITING_QUOTATION
    res = admin_client.post(f"/api/v6/cases/{case.id}/requirements/confirm")
    assert res.status_code == 200
    assert res.json()["status"] == "WAITING_QUOTATION"

    db_session.refresh(case)
    assert case.status == "WAITING_QUOTATION"

    # 3. Create an item -> reverts to PROCESSING_REQUIREMENT
    item_payload = {
        "item_number": "3",
        "description": "Papel A4",
        "quantity": 10,
        "unit": "MILLARES"
    }
    res = admin_client.post(f"/api/v6/cases/{case.id}/procurement-items", json=item_payload)
    assert res.status_code == 200
    item_id = res.json()["id"]

    db_session.refresh(case)
    assert case.status == "PROCESSING_REQUIREMENT"

    # 4. Confirm again
    res = admin_client.post(f"/api/v6/cases/{case.id}/requirements/confirm")
    assert res.status_code == 200

    # 5. Update an item -> reverts to PROCESSING_REQUIREMENT
    res = admin_client.put(f"/api/v6/cases/{case.id}/procurement-items/{item_id}", json={
        "description": "Papel A4 Modificado",
        "quantity": 15
    })
    assert res.status_code == 200

    db_session.refresh(case)
    assert case.status == "PROCESSING_REQUIREMENT"

    # 6. Confirm again
    res = admin_client.post(f"/api/v6/cases/{case.id}/requirements/confirm")
    assert res.status_code == 200

    # 7. Delete an item -> reverts to PROCESSING_REQUIREMENT
    res = admin_client.delete(f"/api/v6/cases/{case.id}/procurement-items/{item_id}")
    assert res.status_code == 200

    db_session.refresh(case)
    assert case.status == "PROCESSING_REQUIREMENT"
