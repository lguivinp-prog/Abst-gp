from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, UploadedDocument, AuditLog
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence

def test_full_v6_end_to_end_flow(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Validates the end-to-end V6 flow without automated mocks interfering with the happy path.
    Steps: Case -> Reqs -> Supplier -> Document -> Offer & Evidence -> Verify -> Evaluate -> Human Review -> Select -> Approve -> Output
    """
    # 1. Create CaseFile (Simulated as existing legacy domain)
    case = CaseFile(title="E2E Servers", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    # 2. Extract Requirements (Simulate existing req)
    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="RAM", value="16GB", mandatory=True)
    db_session.add(req)
    db_session.commit()
    
    # 3. Create Supplier & Profile
    supplier = Supplier(ruc="20111111111", business_name="E2E Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    # Precondición sintética de prueba: perfil de proveedor verificado (no institucional SUNAT/RNP)
    db_session.add(SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED"))
    db_session.commit()

    # 3.1 Create verifiable UploadedDocument in the same case
    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_e2e.pdf",
        stored_path="mock/propuesta_e2e.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()
    
    # 4. Load Offer & Evidence
    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, status="SUBMITTED", price=1000.0)
    db_session.add(offer)
    db_session.commit()
    ev = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="Ficha Tecnica",
        fragment="32GB RAM",
        confidence=0.95
    )
    db_session.add(ev)
    db_session.commit()

    # Link requirement evidence (P12 traceability)
    link_res = admin_client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req.id}/evidence",
        json={"offer_evidence_id": ev.id}
    )
    assert link_res.status_code == 200
    link_data = link_res.json()
    assert link_data["document_id"] == doc.id
    link_id = link_data["id"]

    # Human verification of documentary evidence
    rev_res = admin_client.put(
        f"/api/v6/cases/{case.id}/evidence/{link_id}/review",
        json={"verification_status": "VERIFIED", "review_notes": "Acreditado tecnicamente"}
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["verification_status"] == "VERIFIED"

    # 5. Trigger Validation
    val_res = admin_client.post(f"/api/v6/cases/{case.id}/suppliers/{supplier.id}/validations", json={"source": "SUNAT"})
    assert val_res.status_code == 200
    
    # 6. Evaluate Offer
    eval_res = admin_client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 200
    evals = eval_res.json()
    assert len(evals) >= 1
    ram_eval = next(e for e in evals if e["requirement_id"] == req.id)
    # Al no interpretar RAM automáticamente el comparador determinista, devuelve REQUIERE_REVISION
    assert ram_eval["status"] == "REQUIERE_REVISION"
    eval_id = ram_eval["id"]

    # 7. Intentar selección antes de la decisión humana (debe ser rechazada)
    sel_fail = admin_client.post(
        f"/api/v6/cases/{case.id}/selection",
        json={"supplier_offer_id": offer.id, "justification_comment": "Intento de seleccionar antes de revision humana"}
    )
    assert sel_fail.status_code == 400
    assert "pending mandatory evaluations" in sel_fail.json()["detail"].lower() or "ineligible" in sel_fail.json()["detail"].lower()

    get_sel = admin_client.get(f"/api/v6/cases/{case.id}/selection")
    assert get_sel.status_code == 200
    assert get_sel.json() is None

    # 8. Decisión técnica humana: Registrar PASSED con fundamentación expresa
    put_res = admin_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_id}",
        json={"status": "PASSED", "explanation": "Acreditación técnica humana validada: memoria RAM 32GB supera el mínimo de 16GB"}
    )
    assert put_res.status_code == 200
    put_data = put_res.json()
    assert put_data["status"] == "PASSED"
    assert put_data["validated_by"] is not None
    assert put_data["validated_at"] is not None

    # Comprobar evento de auditoría
    audit = db_session.query(AuditLog).filter_by(action="UPDATE_EVALUATION", entity_id=str(eval_id)).first()
    assert audit is not None
    assert audit.status == "SUCCESS"

    # Confirmar estado positivo mediante nueva consulta GET
    get_evals = admin_client.get(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluations")
    assert get_evals.status_code == 200
    assert any(e["id"] == eval_id and e["status"] == "PASSED" for e in get_evals.json())

    # 9. Supplier Selection válida tras decisión humana
    sel_res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Cumple tecnico"})
    assert sel_res.status_code == 200
    assert sel_res.json()["status"] == "UNDER_REVIEW"
    
    # 10. Supervisor Approval
    app_res = admin_client.post(f"/api/v6/cases/{case.id}/approve")
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"
    
    # 11. Generate Output
    out_res = admin_client.post(f"/api/v6/cases/{case.id}/prepare-output")
    assert out_res.status_code == 200
    assert out_res.json()["status"] == "GENERATED"
    out_id = out_res.json()["id"]
    
    # 12. Approve & Export Output
    admin_client.post(f"/api/v6/outputs/{out_id}/approve")
    export_res = admin_client.post(f"/api/v6/outputs/{out_id}/export")
    assert export_res.status_code == 200
    assert export_res.json()["status"] == "EXPORTED"
