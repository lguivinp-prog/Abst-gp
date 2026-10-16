from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, UploadedDocument, AuditLog
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence

def test_pilot_case_execution(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """
    Simulates a real-world operator flow during the pilot.
    No direct DB manipulation except for setup dependencies (simulating V5.5 existing state).
    """
    # 1. Setup V5.5 Legacy Case
    case = CaseFile(title="Pilot Case: Laptops", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    # 2. Extract Requirements (Simulate)
    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="RAM", value="32GB", mandatory=True)
    db_session.add(req)
    db_session.commit()
    
    # 3. Add Supplier & Profile
    supplier = Supplier(ruc="20555555555", business_name="Pilot Supplier SAC", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()
    # Precondición sintética de prueba: perfil de proveedor verificado (no institucional SUNAT/RNP)
    db_session.add(SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED"))
    db_session.commit()

    # 3.1 Create verifiable UploadedDocument in the same case
    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_piloto.pdf",
        stored_path="mock/propuesta_piloto.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()
    
    # 4. Add Offer
    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        status="SUBMITTED",
        price=1000.0
    )
    db_session.add(offer)
    db_session.commit()

    # 4.1 Add documentary evidence with verified document_id
    evidence = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="FICHA_TECNICA",
        fragment="32GB",
        confidence=0.99,
    )
    db_session.add(evidence)
    db_session.commit()

    # Link requirement evidence (P12 traceability)
    link_res = admin_client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req.id}/evidence",
        json={"offer_evidence_id": evidence.id}
    )
    assert link_res.status_code == 200
    link_data = link_res.json()
    assert link_data["document_id"] == doc.id
    link_id = link_data["id"]

    # Human review of documentary evidence
    rev_res = admin_client.put(
        f"/api/v6/cases/{case.id}/evidence/{link_id}/review",
        json={"verification_status": "VERIFIED", "review_notes": "Acreditado para piloto"}
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["verification_status"] == "VERIFIED"

    # 5. Evaluate Offer
    eval_res = admin_client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 200
    evals = eval_res.json()
    assert len(evals) >= 1
    ram_eval = next(e for e in evals if e["requirement_id"] == req.id)
    # Al no interpretar RAM automáticamente el comparador determinista, devuelve REQUIERE_REVISION
    assert ram_eval["status"] == "REQUIERE_REVISION"
    eval_id = ram_eval["id"]

    # 5.1 Intentar selección antes de la decisión humana (debe ser rechazada)
    sel_fail = admin_client.post(
        f"/api/v6/cases/{case.id}/selection",
        json={"supplier_offer_id": offer.id, "justification_comment": "Intento de seleccion previo a decision humana"}
    )
    assert sel_fail.status_code == 400
    assert "pending mandatory evaluations" in sel_fail.json()["detail"].lower() or "ineligible" in sel_fail.json()["detail"].lower()

    get_sel = admin_client.get(f"/api/v6/cases/{case.id}/selection")
    assert get_sel.status_code == 200
    assert get_sel.json() is None

    # 5.2 Decisión técnica humana: Registrar PASSED con fundamentación expresa
    put_res = admin_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_id}",
        json={"status": "PASSED", "explanation": "Acreditación técnica humana validada: cumple memoria RAM 32GB requerida"}
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

    # 6. Make Selection
    sel_res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Cumple tecnico para piloto"})
    assert sel_res.status_code == 200
    
    # 7. Supervisor Approves
    app_res = admin_client.post(f"/api/v6/cases/{case.id}/approve")
    assert app_res.status_code == 200
    
    # 8. Output Prep & Export
    out_res = admin_client.post(f"/api/v6/cases/{case.id}/prepare-output")
    assert out_res.status_code == 200
    out_id = out_res.json()["id"]
    
    admin_client.post(f"/api/v6/outputs/{out_id}/approve")
    exp_res = admin_client.post(f"/api/v6/outputs/{out_id}/export")
    assert exp_res.status_code == 200
    assert exp_res.json()["status"] == "EXPORTED"
