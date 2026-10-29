from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, AuditLog
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.case_workflow import CaseWorkflow

def test_propose_and_approve_selection(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    case = CaseFile(title="Laptop Purchase", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    db_session.add(case)
    supplier = Supplier(ruc="20123456789", business_name="Tech Corp", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.commit()

    offer = SupplierOffer(case_id=case.id, supplier_id=supplier.id, status="SUBMITTED")
    db_session.add(offer)
    db_session.commit()

    # 1. Propose Selection
    payload = {"supplier_offer_id": offer.id, "justification_comment": "Mejor precio y plazo"}
    response = admin_client.post(f"/api/v6/cases/{case.id}/selection", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "UNDER_REVIEW"

    # Verify Selection and Workflow State
    attempt = db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first()
    assert attempt is not None
    assert attempt.selected_by is not None

    workflow = db_session.query(CaseWorkflow).filter_by(case_id=case.id).first()
    assert workflow.status == "UNDER_REVIEW"

    # 2. Approve Selection
    approve_res = admin_client.post(f"/api/v6/cases/{case.id}/approve")
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    db_session.refresh(workflow)
    assert workflow.status == "APPROVED"
    assert workflow.supervisor_id is not None

    final_sel = db_session.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()
    assert final_sel is not None

def test_selection_arithmetic_discrepancy_requires_motivation(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    from app.models.v6.case_procurement_item import CaseProcurementItem
    from app.models.v6.supplier_offer_item import SupplierOfferItem
    from app.models.v6.supplier_profile import SupplierProfile
    from decimal import Decimal

    case = CaseFile(title="Supply Office", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    db_session.add(case)
    supplier = Supplier(ruc="20555666777", business_name="Papelera Central EIRL", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.flush()

    profile = SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED")
    db_session.add(profile)

    item1 = CaseProcurementItem(case_id=case.id, item_number="1", description="Papel bond A4", quantity=50, unit="MILLAR")
    item2 = CaseProcurementItem(case_id=case.id, item_number="2", description="Toner laser", quantity=4, unit="UNIDAD")
    db_session.add_all([item1, item2])
    db_session.flush()

    # Offer with declared PDF price = 2500.0, but unit prices sum to 2360.0
    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        price=2500.0,
        total_amount=Decimal("2360.00"),
        status="APPROVED",
        currency="PEN"
    )
    db_session.add(offer)
    db_session.flush()

    off_item1 = SupplierOfferItem(supplier_offer_id=offer.id, procurement_item_id=item1.id, description="Papel bond", quantity=50, unit="MILLAR", unit_price=Decimal("24.00"))
    off_item2 = SupplierOfferItem(supplier_offer_id=offer.id, procurement_item_id=item2.id, description="Toner laser", quantity=4, unit="UNIDAD", unit_price=Decimal("290.00"))
    db_session.add_all([off_item1, off_item2])
    db_session.commit()

    # 1. Propose without motivation -> Rejected
    res_no_just = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={
        "supplier_offer_id": offer.id,
        "justification_comment": ""
    })
    assert res_no_just.status_code == 400
    assert "Inconsistencia aritmética" in res_no_just.json()["detail"]
    assert "detectada" in res_no_just.json()["detail"]

    # 2. Propose with explicit motivation -> Accepted
    motivation_text = "Conforme a las reglas del procedimiento, prevalecen los precios unitarios (S/ 2,360.00) sobre la carátula (S/ 2,500.00)."
    res_with_just = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={
        "supplier_offer_id": offer.id,
        "justification_comment": motivation_text
    })
    assert res_with_just.status_code == 200
    assert res_with_just.json()["status"] == "UNDER_REVIEW"

    # Verify reconciliation audit log
    audit_rec = db_session.query(AuditLog).filter_by(
        action="RECONCILE_ARITHMETIC_DISCREPANCY",
        entity_id=str(offer.id)
    ).first()
    assert audit_rec is not None
    assert f"Expediente {case.id}: Revisión administrativa de conciliación económica" in audit_rec.details
    assert f"Oferta #{offer.id}" in audit_rec.details
    assert "Importe declarado: S/ 2,500.00" in audit_rec.details
    assert "Importe calculado: S/ 2,360.00" in audit_rec.details
    assert "Diferencia detectada: S/ 140.00" in audit_rec.details
    assert "Responsable autorizado:" in audit_rec.details
    assert f"Motivación íntegra: {motivation_text}" in audit_rec.details

    # 3. Approve selection
    approve_res = admin_client.post(f"/api/v6/cases/{case.id}/approve")
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"


def test_selection_arithmetic_discrepancy_accepts_substantive_motivation_without_keywords(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    from app.models.v6.case_procurement_item import CaseProcurementItem
    from app.models.v6.supplier_offer_item import SupplierOfferItem
    from app.models.v6.supplier_profile import SupplierProfile
    from decimal import Decimal

    case = CaseFile(title="Service Procurement", contract_type="SERVICIOS", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    db_session.add(case)
    supplier = Supplier(ruc="20444333222", business_name="Servicios Generales SRL", tenant_id="mega_tenant")
    db_session.add(supplier)
    db_session.flush()

    profile = SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED")
    db_session.add(profile)

    item1 = CaseProcurementItem(case_id=case.id, item_number="1", description="Mantenimiento preventivo", quantity=1, unit="SERVICIO")
    db_session.add(item1)
    db_session.flush()

    # Discrepancy: declared total 5000.0 vs unit price 4800.0
    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        price=5000.0,
        total_amount=Decimal("4800.00"),
        status="APPROVED",
        currency="PEN",
        source_document="Cotizacion_Firmada_001.pdf"
    )
    db_session.add(offer)
    db_session.flush()

    off_item1 = SupplierOfferItem(supplier_offer_id=offer.id, procurement_item_id=item1.id, description="Mantenimiento preventivo", quantity=1, unit="SERVICIO", unit_price=Decimal("4800.00"))
    db_session.add(off_item1)
    db_session.commit()

    # Motivation contains NONE of the old keywords ("aritmetic", "unitario", "prevalec", "concilia", "discrepanc", "error", "rectifica", "diferencia", "caratula")
    pure_administrative_motivation = "Validación funcional y técnica completada por el área usuaria conforme a bases administrativas; se autoriza la adjudicación por el monto evaluado."
    res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={
        "supplier_offer_id": offer.id,
        "justification_comment": pure_administrative_motivation
    })
    assert res.status_code == 200
    assert res.json()["status"] == "UNDER_REVIEW"

    # Verify audit log details contain source document, exact amounts, user, and verbatim motivation
    audit = db_session.query(AuditLog).filter_by(
        action="RECONCILE_ARITHMETIC_DISCREPANCY",
        entity_id=str(offer.id)
    ).first()
    assert audit is not None
    assert f"Expediente {case.id}: Revisión administrativa de conciliación económica" in audit.details
    assert "Documento fuente: Cotizacion_Firmada_001.pdf" in audit.details
    assert "Importe declarado: S/ 5,000.00" in audit.details
    assert "Importe calculado: S/ 4,800.00" in audit.details
    assert "Diferencia detectada: S/ 200.00" in audit.details
    assert f"Motivación íntegra: {pure_administrative_motivation}" in audit.details


