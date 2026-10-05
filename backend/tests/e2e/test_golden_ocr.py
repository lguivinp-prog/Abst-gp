import os
import io
import time
import pytest
from app.models.domain import CaseFile, UploadedDocument, OCRProcessingRun

def test_golden_ocr_quality_gate(admin_client, db_session):
    # 1. Setup case
    case = CaseFile(tenant_id="mega_tenant", title="V6 Native Upload Case Real OCR", contract_type="BIENES", status="DRAFT", created_by=1)
    db_session.add(case)
    db_session.commit()

    # 2. Get the golden pdf
    pdf_path = os.path.join(os.path.dirname(__file__), "golden_test_uat.pdf")
    with open(pdf_path, "rb") as f:
        file_content = f.read()

    # 3. Upload requirement directly to trigger the worker
    response = admin_client.post(
        f"/api/v6/cases/{case.id}/requirements/upload",
        files={"file": ("golden_test_uat.pdf", io.BytesIO(file_content), "application/pdf")}
    )

    assert response.status_code == 200, response.text
    data = response.json()
    document_id = data["document_id"]
    run_id = data["run_id"]

    # 4. Wait for worker to finish
    max_retries = 60
    final_status = "QUEUED"
    for _ in range(max_retries):
        db_session.expire_all()
        run = db_session.query(OCRProcessingRun).filter(OCRProcessingRun.run_id == run_id).first()
        if run and run.status in ["COMPLETED", "FAILED"]:
            final_status = run.status
            break
        time.sleep(2)

    assert final_status == "COMPLETED", f"Worker failed or timed out. Last status: {final_status}"

    # 5. Get the document and extraction result
    doc = db_session.query(UploadedDocument).filter(UploadedDocument.id == document_id).first()
    assert doc.processing_status == "finished"
    assert doc.text_extracted is not None

    text = doc.text_extracted

    # 6. Assertions on text
    assert "EPSON L14150" in text or "L14150" in text, "Debe recuperar EPSON L14150"
    assert "114150" not in text, "No debe sufrir regresion a 114150"
    assert "NEGRO" in text, "Debe recuperar NEGRO"

    # cantidades 3 y 2
    assert "3" in text, "Debe extraer cantidad 3"
    assert "2" in text, "Debe extraer cantidad 2"

    assert "CIAN" in text, "Debe recuperar CIAN correctamente"
    assert "FRASCO" in text, "Debe recuperar TIPO FRASCO"
    assert "100%" in text, "Debe recuperar ESTABILIDAD QUIMICA 100%"

    # RNP, RUC, CCI
    assert "RNP" in text, "Debe recuperar RNP"
    assert "RUC" in text, "Debe recuperar RUC"
    assert "CCI" in text, "Debe recuperar CCI"
