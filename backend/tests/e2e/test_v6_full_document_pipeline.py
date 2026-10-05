import pytest
import os
import io
import time
from app.models.domain import CaseFile, UploadedDocument, OCRProcessingRun
from app.models.v6.supplier_selection import SupplierSelectionFinal

def test_v6_full_document_pipeline(admin_client, db_session):
    # STEP 1 — LOGIN
    # admin_client already logs in as admin/supervisor in standard fixtures
    # We will just verify it works by hitting a protected endpoint, or we can use admin_token explicitly if needed.
    # We will assume admin_client provides the correct token headers.

    # Let's get the auth token via API to strictly follow the prompt if needed,
    # but admin_client is an authenticated TestClient.
    response = admin_client.get("/health")
    assert response.status_code == 200

    # STEP 2 — CREATE CASE
    case_payload = {
        "title": "V6 Native E2E Test Case",
        "description": "Full workflow test",
        "contract_type": "BIENES"
    }
    response = admin_client.post("/cases/", json=case_payload)
    assert response.status_code == 200, response.text
    case_data = response.json()
    case_id = case_data["id"]

    # STEP 3 — NATIVE V6 REQUIREMENT UPLOAD
    pdf_path = os.path.join(os.path.dirname(__file__), "golden_test_uat.pdf")
    with open(pdf_path, "rb") as f:
        file_content = f.read()

    response = admin_client.post(
        f"/api/v6/cases/{case_id}/requirements/upload",
        files={"file": ("golden_test_uat.pdf", io.BytesIO(file_content), "application/pdf")}
    )
    assert response.status_code == 200, response.text
    upload_data = response.json()
    document_id = upload_data["document_id"]
    run_id = upload_data["run_id"]

    # STEP 4 — REAL OCR POLLING
    max_retries = 60
    final_status = "QUEUED"
    extraction_ready = False

    for _ in range(max_retries):
        resp = admin_client.get(f"/api/v6/cases/{case_id}/documents")
        assert resp.status_code == 200
        docs = resp.json()
        doc = next((d for d in docs if d["id"] == document_id), None)
        assert doc is not None

        if doc["processing_status"] in ["finished", "failed"]:
            final_status = doc["processing_status"]
            extraction_ready = doc["extraction_ready"]
            break
        time.sleep(2)

    assert final_status == "finished", f"Worker failed or timed out. Last status: {final_status}"
    assert extraction_ready is True, "Document extraction not ready"

    # STEP 5 — REQUIREMENT EXTRACTION
    response = admin_client.post(f"/api/v6/cases/{case_id}/requirements/extract", json={"document_id": document_id})
    assert response.status_code == 200, response.text
    reqs = response.json()
    assert len(reqs) >= 1
    assert any(r.get("description") for r in reqs), "Should have non-empty business content"

    # Let's get procurement items to fulfill selection requirements
    resp = admin_client.get(f"/api/v6/cases/{case_id}/procurement-items")
    assert resp.status_code == 200
    proc_items = resp.json()
    # It's okay if proc_items is empty if the deterministic extractor didn't find any.

    # STEP 6 — CREATE/LINK SUPPLIER
    supplier_payload = {
        "ruc": "20123456789",
        "business_name": "E2E Test Supplier SAC",
        "contact_email": "test@e2e.com"
    }
    response = admin_client.post(f"/api/v6/cases/{case_id}/suppliers", json=supplier_payload)
    assert response.status_code == 200, response.text
    supplier_data = response.json()
    supplier_id = supplier_data["id"]

    # Check if offer was auto-created (P40.1 established this)
    resp = admin_client.get(f"/api/v6/cases/{case_id}/offers")
    assert resp.status_code == 200
    offers = resp.json()
    offer = next((o for o in offers if o["supplier_id"] == supplier_id), None)
    assert offer is not None, "SupplierOffer should be auto-created"
    offer_id = offer["id"]
    assert offer["status"] == "PENDING"

    # SUPPLIER VALIDATION PRECONDITION
    # Use API to do manual validation
    val_payload = {
        "source": "SUNAT",
        "result": "VALIDATED",
        "observation": "Manual validation for E2E"
    }
    resp = admin_client.post(f"/api/v6/cases/{case_id}/suppliers/{supplier_id}/validations/manual", json=val_payload)
    assert resp.status_code == 200, resp.text

    # STEP 7 — OFFER DOCUMENT UPLOAD
    with open(pdf_path, "rb") as f:
        offer_content = f.read()

    resp = admin_client.post(
        f"/api/v6/cases/{case_id}/documents",
        data={"document_type": "oferta"},
        files={"file": ("offer_doc.pdf", io.BytesIO(offer_content), "application/pdf")}
    )
    assert resp.status_code == 200, resp.text
    offer_doc_data = resp.json()
    offer_doc_id = offer_doc_data["id"]

    # STEP 8 — COMPLETE OFFER
    offer_items = []
    for item in proc_items:
        offer_items.append({
            "procurement_item_id": item["id"],
            "unit_price": 100.00
        })

    offer_update = {
        "price": 1500.00,
        "currency": "PEN",
        "source_document": "offer_doc.pdf",
        "document_ids": [offer_doc_id],
        "status": "EVALUATED",
        "items": offer_items
    }
    resp = admin_client.put(f"/api/v6/cases/{case_id}/offers/{offer_id}", json=offer_update)
    assert resp.status_code == 200, resp.text
    updated_offer = resp.json()
    assert updated_offer["status"] == "EVALUATED"

    # STEP 9 — EVALUATION
    resp = admin_client.post(f"/api/v6/cases/{case_id}/offers/{offer_id}/evaluate")
    assert resp.status_code == 200, resp.text

    # STEP 10 — SELECTION
    selection_payload = {
        "supplier_offer_id": offer_id,
        "justification_comment": "Best offer overall"
    }
    resp = admin_client.post(f"/api/v6/cases/{case_id}/selection", json=selection_payload)
    assert resp.status_code == 200, resp.text
    selection_data = resp.json()
    assert selection_data["status"] == "UNDER_REVIEW"

    # STEP 11 — FINAL SELECTION APPROVAL
    resp = admin_client.post(f"/api/v6/cases/{case_id}/approve")
    assert resp.status_code == 200, resp.text
    approval_data = resp.json()
    assert approval_data["status"] == "APPROVED"

    # STEP 12 — FINAL RESULT
    resp = admin_client.get(f"/api/v6/cases/{case_id}/result")
    assert resp.status_code == 200, resp.text
    result_data = resp.json()
    assert result_data["status"] == "APPROVED"
    assert result_data["supplier_ruc"] == "20123456789"
    assert result_data["offer_total_amount"] is not None

    # Verify entity chain consistency (no hardcoded DB IDs)
    assert result_data["case_id"] == case_id
    assert case_id > 0
    assert offer_id > 0
    assert document_id > 0
