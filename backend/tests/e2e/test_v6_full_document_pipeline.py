import pytest
import os
import io
import time
from app.models.domain import CaseFile, UploadedDocument, OCRProcessingRun, AuditLog
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import fitz

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
    max_retries = 150
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
    assert len(proc_items) >= 2, f"Expected >= 2 items from golden_test_uat.pdf, got {len(proc_items)}"
    assert proc_items[0]["item_number"] == "1"
    assert proc_items[0]["quantity"] == 3.0
    assert proc_items[1]["item_number"] == "2"
    assert proc_items[1]["quantity"] == 2.0

    # STEP 5.5 - CONFIRM REQUIREMENTS
    response = admin_client.post(f"/api/v6/cases/{case_id}/requirements/confirm")
    assert response.status_code == 200, response.text

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

    # Establecer y verificar el estado del perfil del proveedor sintético para el entorno aislado de pruebas
    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier_id).first()
    if not profile:
        profile = SupplierProfile(
            supplier_id=supplier_id,
            validation_status="VERIFIED",
            status_summary="VERIFIED",
            aggregated_score=100.0
        )
        db_session.add(profile)
    else:
        profile.validation_status = "VERIFIED"
        profile.status_summary = "VERIFIED"
    db_session.commit()
    db_session.refresh(profile)
    assert profile.validation_status == "VERIFIED"

    # STEP 7 — SYNTHETIC OFFER DOCUMENT GENERATION AND UPLOAD (INDEPENDENT SOURCE)
    offer_pdf_buffer = io.BytesIO()
    c = canvas.Canvas(offer_pdf_buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 750, "OFERTA TECNICA Y ECONOMICA - E2E TEST SUPPLIER SAC")
    c.setFont("Helvetica", 10)
    c.drawString(50, 720, "Item 1: Tinta original para EPSON L14150 negro frasco 65-130 mL aprox.")
    c.drawString(50, 700, "Item 2: Tinta original para EPSON L14150 cian frasco 65-130 mL estabilidad 100%")
    c.drawString(50, 680, "Disponibilidad permanente para atencion y entrega de suministros urgentes.")
    c.drawString(50, 660, "Plazo de entrega garantizado de 2 dias calendario posteriores a notificacion.")
    c.drawString(50, 640, "Entrega sujeta a verificacion con sello de recepcion V B.")
    c.save()
    offer_pdf_bytes = offer_pdf_buffer.getvalue()

    # Comprobar que la oferta es independiente del documento de requerimientos
    assert offer_pdf_bytes != file_content, "La oferta sintética debe ser independiente del requerimiento"

    # Extraer texto del PDF de oferta para verificar procedencia real de fragmentos
    offer_doc_fitz = fitz.open(stream=offer_pdf_bytes, filetype="pdf")
    extracted_offer_text = "".join(p.get_text() for p in offer_doc_fitz)
    offer_doc_fitz.close()
    assert "OFERTA TECNICA Y ECONOMICA" in extracted_offer_text

    resp = admin_client.post(
        f"/api/v6/cases/{case_id}/documents",
        data={"document_type": "oferta"},
        files={"file": ("synthetic_offer_e2e.pdf", io.BytesIO(offer_pdf_bytes), "application/pdf")}
    )
    assert resp.status_code == 200, resp.text
    offer_doc_data = resp.json()
    offer_doc_id = offer_doc_data["id"]

    # STEP 8 — COMPLETE OFFER WITH CONSISTENT ECONOMIC TOTAL
    offer_items = []
    for item in proc_items:
        offer_items.append({
            "procurement_item_id": item["id"],
            "unit_price": 100.00
        })

    # Consistencia estricta: proc_items[0] (qty 3.0) + proc_items[1] (qty 2.0) a 100.00 = 500.00 PEN
    offer_update = {
        "price": 500.00,
        "currency": "PEN",
        "source_document": "synthetic_offer_e2e.pdf",
        "document_ids": [offer_doc_id],
        "status": "EVALUATED",
        "items": offer_items
    }
    resp = admin_client.put(f"/api/v6/cases/{case_id}/offers/{offer_id}", json=offer_update)
    assert resp.status_code == 200, resp.text
    updated_offer = resp.json()
    assert updated_offer["status"] == "EVALUATED"

    # STEP 9A — EVALUATION PRE-EVIDENCE (MISSING DATA)
    resp = admin_client.post(f"/api/v6/cases/{case_id}/offers/{offer_id}/evaluate")
    assert resp.status_code == 200, resp.text
    eval_pre = resp.json()
    assert len(eval_pre) > 0
    assert any(e["status"] == "MISSING_DATA" for e in eval_pre), "Sin evidencias, la evaluación obligatoria debe arrojar MISSING_DATA"

    # STEP 9B — PRUEBA NEGATIVA OBLIGATORIA (MISSING_DATA)
    # Proponer una oferta con MISSING_DATA debe ser rechazado con HTTP 400
    neg_selection_payload = {
        "supplier_offer_id": offer_id,
        "justification_comment": "Intento de selección sobre oferta con datos faltantes"
    }
    neg_resp = admin_client.post(f"/api/v6/cases/{case_id}/selection", json=neg_selection_payload)
    assert neg_resp.status_code == 400, neg_resp.text
    assert "MISSING_DATA" in neg_resp.text or "missing data" in neg_resp.text.lower()

    # Verificar que no se crea SupplierSelectionAttempt, no se altera workflow y no hay selección final
    attempts = db_session.query(SupplierSelectionAttempt).filter_by(case_id=case_id).all()
    assert len(attempts) == 0, "No debe registrarse ningún SupplierSelectionAttempt tras intento inválido"

    workflow = db_session.query(CaseWorkflow).filter_by(case_id=case_id).first()
    assert workflow is None or workflow.status != "UNDER_REVIEW", "El workflow no debe alterarse a UNDER_REVIEW"

    final_sel = db_session.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
    assert final_sel is None, "No debe existir SupplierSelectionFinal"

    # STEP 9C — RELACIONAR EVIDENCIAS DOCUMENTALES REALES DE LA OFERTA SINTÉTICA
    matrix_reqs = db_session.query(CaseRequirementMatrix).filter_by(case_id=case_id).all()
    assert len(matrix_reqs) > 0, "Debe existir al menos un requisito en la matriz"

    frag_supplies = "Disponibilidad permanente para atencion y entrega de suministros urgentes."
    frag_delivery = "Plazo de entrega garantizado de 2 dias calendario posteriores a notificacion."
    frag_reception = "Entrega sujeta a verificacion con sello de recepcion V B."
    frag_items = "Item 1: Tinta original para EPSON L14150 negro frasco 65-130 mL aprox."

    # Comprobar procedencia documental de cada fragmento frente al texto del PDF de oferta
    for frag in [frag_supplies, frag_delivery, frag_reception, frag_items]:
        assert frag in extracted_offer_text, f"Fragmento no coincide con el texto extraído del PDF de oferta: {frag}"

    ev_supplies = OfferEvidence(
        supplier_offer_id=offer_id,
        document_id=offer_doc_id,
        document_type="OFERTA_TECNICA",
        fragment=frag_supplies,
        confidence=0.98,
        page=1
    )
    ev_delivery = OfferEvidence(
        supplier_offer_id=offer_id,
        document_id=offer_doc_id,
        document_type="OFERTA_TECNICA",
        fragment=frag_delivery,
        confidence=0.98,
        page=1
    )
    ev_reception = OfferEvidence(
        supplier_offer_id=offer_id,
        document_id=offer_doc_id,
        document_type="OFERTA_TECNICA",
        fragment=frag_reception,
        confidence=0.98,
        page=1
    )
    ev_items = OfferEvidence(
        supplier_offer_id=offer_id,
        document_id=offer_doc_id,
        document_type="OFERTA_TECNICA",
        fragment=frag_items,
        confidence=0.98,
        page=1
    )
    db_session.add_all([ev_supplies, ev_delivery, ev_reception, ev_items])
    db_session.commit()

    for req in matrix_reqs:
        desc_lower = (req.description or "").lower()
        if "suministros" in desc_lower or "impresoras" in desc_lower:
            target_evidence = ev_supplies
        elif "plazo" in desc_lower or "entrega" in desc_lower or "dias" in desc_lower:
            target_evidence = ev_delivery
        elif "sello" in desc_lower or "recepcion" in desc_lower:
            target_evidence = ev_reception
        else:
            target_evidence = ev_items

        link_resp = admin_client.post(
            f"/api/v6/cases/{case_id}/offers/{offer_id}/requirements/{req.id}/evidence",
            json={"offer_evidence_id": target_evidence.id}
        )
        assert link_resp.status_code == 200, link_resp.text
        link_id = link_resp.json()["id"]
        rev_resp = admin_client.put(
            f"/api/v6/cases/{case_id}/evidence/{link_id}/review",
            json={
                "verification_status": "VERIFIED",
                "review_notes": f"Verificación conforme de evidencia documental para requisito {req.id}"
            }
        )
        assert rev_resp.status_code == 200, rev_resp.text

    # STEP 9D — RE-EVALUACIÓN AUTOMÁTICA Y VERIFICACIÓN DE REQUIERE_REVISION
    resp = admin_client.post(f"/api/v6/cases/{case_id}/offers/{offer_id}/evaluate")
    assert resp.status_code == 200, resp.text
    eval_post = resp.json()
    assert len(eval_post) > 0

    # Comprobar que la evaluación automática es no concluyente cuando corresponde
    supplies_eval = next((e for e in eval_post if "suministros" in (e.get("requirement_description") or "").lower()), None)
    assert supplies_eval is not None, "Debe existir evaluación para el requisito de suministros"
    assert supplies_eval["status"] == "REQUIERE_REVISION", (
        f"El motor debe devolver legítimamente REQUIERE_REVISION para el requisito de suministros contextual: {supplies_eval}"
    )

    unresolved_evals = [e for e in eval_post if e["status"] == "REQUIERE_REVISION"]
    assert len(unresolved_evals) > 0, "Debe existir al menos un requisito en REQUIERE_REVISION antes de revisión humana"

    # STEP 9E — PRUEBA NEGATIVA: BLOQUEO DE SELECCIÓN CON REQUIERE_REVISION ANTES DE REVISIÓN HUMANA
    neg_sel_payload = {
        "supplier_offer_id": offer_id,
        "justification_comment": "Intento de selección mientras persisten requisitos en REQUIERE_REVISION"
    }
    neg_resp = admin_client.post(f"/api/v6/cases/{case_id}/selection", json=neg_sel_payload)
    assert neg_resp.status_code == 400, f"Debe rechazarse la selección con requisitos en REQUIERE_REVISION: {neg_resp.text}"
    assert "pending mandatory evaluations" in neg_resp.text.lower() or "ineligible" in neg_resp.text.lower()

    # Comprobar que no hubo mutación de SupplierSelectionAttempt, SupplierSelectionFinal ni workflow
    attempts_review = db_session.query(SupplierSelectionAttempt).filter_by(case_id=case_id).all()
    assert len(attempts_review) == 0, "No debe registrarse SupplierSelectionAttempt con evaluaciones pendientes"

    workflow_review = db_session.query(CaseWorkflow).filter_by(case_id=case_id).first()
    assert workflow_review is None or workflow_review.status != "UNDER_REVIEW", "El workflow no debe estar en UNDER_REVIEW"

    final_review = db_session.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
    assert final_review is None, "No debe existir SupplierSelectionFinal antes de decisión humana"

    sel_get = admin_client.get(f"/api/v6/cases/{case_id}/selection")
    assert sel_get.status_code == 200
    assert sel_get.json() is None

    # STEP 9F — REVISIÓN TÉCNICA HUMANA MOTIVADA Y AUDITADA MEDIANTE ENDPOINT AUTORIZADO
    for ev in eval_post:
        if ev["status"] == "REQUIERE_REVISION":
            desc = ev.get("requirement_description", "")
            if "suministros" in desc.lower():
                explanation = (
                    "Acreditación técnica humana motivada: Se verifica en la oferta técnica la disponibilidad permanente "
                    "de stock y atención de suministros urgentes para la operatividad de las oficinas."
                )
            elif "plazo" in desc.lower() or "entrega" in desc.lower():
                explanation = (
                    "Acreditación técnica humana motivada: El plazo de entrega ofertado de 2 días calendario satisface "
                    "plenamente el requerimiento institucional."
                )
            elif "sello" in desc.lower() or "recepcion" in desc.lower():
                explanation = (
                    "Acreditación técnica humana motivada: La recepción de los bienes se encuentra conforme con la "
                    "verificación en almacén y sello de recepción institucional."
                )
            else:
                explanation = (
                    f"Acreditación técnica humana motivada con sustento en la oferta técnica del proveedor para: {desc}"
                )

            update_payload = {
                "status": "PASSED",
                "explanation": explanation
            }
            put_resp = admin_client.put(
                f"/api/v6/cases/{case_id}/evaluations/{ev['id']}",
                json=update_payload
            )
            assert put_resp.status_code == 200, f"Fallo al actualizar evaluación {ev['id']}: {put_resp.text}"
            ev_updated = put_resp.json()
            assert ev_updated["status"] == "PASSED"
            assert ev_updated["validated_by"] is not None, "validated_by debe estar persistido"
            assert ev_updated["validated_at"] is not None, "validated_at debe estar persistido"

            # Verificar auditoría de la decisión humana
            audit_entry = db_session.query(AuditLog).filter_by(
                action="UPDATE_EVALUATION",
                entity_id=str(ev["id"])
            ).first()
            assert audit_entry is not None, f"Debe existir registro de auditoría para evaluación {ev['id']}"
            assert audit_entry.status == "SUCCESS"

    # STEP 9G — VERIFICAR QUE TODOS LOS REQUISITOS OBLIGATORIOS ESTÉN ACREDITADOS SIN SOBRESCRITURA
    get_evals_resp = admin_client.get(f"/api/v6/cases/{case_id}/offers/{offer_id}/evaluations")
    assert get_evals_resp.status_code == 200
    final_evals_list = get_evals_resp.json()
    assert len(final_evals_list) > 0
    for fe in final_evals_list:
        assert fe["status"] in ["PASSED", "IMPROVEMENT"], f"Evaluación no conforme antes de selección: {fe}"
        assert fe["validated_by"] is not None or (fe.get("evaluation_confidence") or 0) >= 0.85

    # STEP 10 — SELECTION CONFORME MEDIANTE API REAL
    selection_payload = {
        "supplier_offer_id": offer_id,
        "justification_comment": "Oferta conforme con evidencia documental técnica, revisión humana motivada y mejor precio"
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
    assert float(result_data["offer_total_amount"]) == 500.00

    # STEP 13 — VERIFICACIÓN FINAL EN BASE DE DATOS Y AUDITORÍA
    final_db = db_session.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
    assert final_db is not None, "SupplierSelectionFinal debe existir en base de datos"

    case_db = db_session.query(CaseFile).filter_by(id=case_id).first()
    assert case_db.status == "APPROVED", "CaseFile debe tener estado terminal APPROVED"

    workflow_db = db_session.query(CaseWorkflow).filter_by(case_id=case_id).first()
    assert workflow_db.status == "APPROVED", "CaseWorkflow debe estar en APPROVED"

    audits = db_session.query(AuditLog).filter_by(entity_id=str(case_id)).all()
    assert len(audits) > 0, "Deben existir eventos de auditoría para el expediente"

    # Comprobar ausencia de reevaluación automática posterior que sobrescriba la decisión humana
    terminal_evals = db_session.query(OfferEvaluation).filter_by(supplier_offer_id=offer_id).all()
    assert len(terminal_evals) > 0
    for te in terminal_evals:
        assert te.status in ["PASSED", "IMPROVEMENT"]
        if te.validated_by is not None:
            assert te.validated_at is not None

    # Verify entity chain consistency (no hardcoded DB IDs)
    assert result_data["case_id"] == case_id
    assert case_id > 0
    assert offer_id > 0
    assert document_id > 0
