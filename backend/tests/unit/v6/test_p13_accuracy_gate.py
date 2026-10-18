import os
import tempfile
import pytest
from app.models.domain import CaseFile, User, Tenant, UploadedDocument, AuditLog
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.services.v6.reporting.accuracy_gate import TechnicalReportAccuracyGate

@pytest.fixture
def base_case_setup(db_session):
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        db_session.flush()

    user = db_session.query(User).filter_by(username="operator_p13_gate").first()
    if not user:
        user = User(
            username="operator_p13_gate",
            role="OPERATOR",
            tenant_id="mega_tenant",
            password_hash="fake",
            tenant_resolution_status="RESOLVED"
        )
        db_session.add(user)
        db_session.flush()

    case = CaseFile(
        title="Expediente de Prueba P13",
        contract_type="BIENES",
        status="APPROVED",
        tenant_id="mega_tenant",
        assigned_to_user_id=user.id,
        traceability_regime="P12_STRICT"
    )
    db_session.add(case)
    db_session.flush()

    workflow = CaseWorkflow(case_id=case.id, status="APPROVED", supervisor_id=user.id)
    db_session.add(workflow)

    supplier = db_session.query(Supplier).filter_by(ruc="20100200301", tenant_id="mega_tenant").first()
    if not supplier:
        supplier = Supplier(
            tenant_id="mega_tenant",
            ruc="20100200301",
            business_name="Proveedor Ganador SAC"
        )
        db_session.add(supplier)
        db_session.flush()

    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    if not profile:
        profile = SupplierProfile(
            supplier_id=supplier.id,
            validation_status="VERIFIED"
        )
        db_session.add(profile)
        db_session.flush()
    else:
        profile.validation_status = "VERIFIED"

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        status="SELECTED",
        currency="PEN",
        price=15000.0,
        total_amount=15000.0
    )
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(
        case_id=case.id,
        supplier_offer_id=offer.id,
        selected_by=user.id,
        status="UNDER_REVIEW"
    )
    db_session.add(attempt)
    db_session.flush()

    final_sel = SupplierSelectionFinal(case_id=case.id, attempt_id=attempt.id)
    db_session.add(final_sel)

    # R3-04: Crear archivo físico auténtico en almacenamiento autorizado
    real_doc_path = os.path.join(tempfile.gettempdir(), f"sustento_gate_{case.id}.pdf")
    with open(real_doc_path, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 32 >>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Fragmento) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000201 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n284\n%%EOF\n")

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="sustento_propuesta.pdf",
        stored_path=real_doc_path,
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.flush()

    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="Requisito Técnico 1", mandatory=True)
    db_session.add(req)
    db_session.flush()

    ev = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        status="PASSED",
        validated_by=user.id
    )
    db_session.add(ev)

    from app.models.v6.offer_evidence import OfferEvidence
    offer_ev = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="Ficha Tecnica",
        fragment="Fragmento de sustento verificado"
    )
    db_session.add(offer_ev)
    db_session.flush()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=offer_ev.id,
        document_id=doc.id,
        page=1,
        fragment="Fragmento de sustento verificado",
        verified_by=user.id,
        verification_status="VERIFIED"
    )
    db_session.add(ore)
    db_session.commit()

    return {
        "case": case,
        "workflow": workflow,
        "offer": offer,
        "supplier": supplier,
        "profile": profile,
        "attempt": attempt,
        "final_sel": final_sel,
        "doc": doc,
        "req": req,
        "ev": ev,
        "ore": ore,
        "user": user
    }

def test_accuracy_gate_pass(db_session, base_case_setup):
    case = base_case_setup["case"]
    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert result["status"] == "PASS"
    assert len(result["errors"]) == 0
    assert result["winner_offer_id"] == base_case_setup["offer"].id

def test_accuracy_gate_fails_case_not_approved(db_session, base_case_setup):
    case = base_case_setup["case"]
    case.status = "UNDER_REVIEW"
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("APPROVED" in e for e in result["errors"])

def test_accuracy_gate_fails_workflow_not_approved(db_session, base_case_setup):
    case = base_case_setup["case"]
    wf = base_case_setup["workflow"]
    wf.status = "UNDER_REVIEW"
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("flujo de trabajo" in e for e in result["errors"])

def test_accuracy_gate_fails_missing_selection_final(db_session, base_case_setup):
    case = base_case_setup["case"]
    db_session.delete(base_case_setup["final_sel"])
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("SupplierSelectionFinal" in e for e in result["errors"])

def test_accuracy_gate_fails_winning_offer_different_case(db_session, base_case_setup):
    case2 = CaseFile(
        title="Expediente Alterno",
        contract_type="BIENES",
        status="APPROVED",
        tenant_id="mega_tenant"
    )
    db_session.add(case2)
    db_session.flush()

    offer = base_case_setup["offer"]
    offer.case_id = case2.id
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("no pertenece al expediente" in e for e in result["errors"])

def test_accuracy_gate_supplier_unfavorable_status_without_exception(db_session, base_case_setup):
    profile = base_case_setup["profile"]
    profile.validation_status = "SANCTIONED"
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("SANCTIONED" in e for e in result["errors"])

def test_accuracy_gate_supplier_supervisor_exception_allowed(db_session, base_case_setup):
    profile = base_case_setup["profile"]
    profile.validation_status = "OBSERVED"
    
    # Agregar usuario con rol SUPERVISOR para emitir la excepcion valida
    sup_user = db_session.query(User).filter_by(username="supervisor_p13_gate").first()
    if not sup_user:
        sup_user = User(
            username="supervisor_p13_gate",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="fake",
            tenant_resolution_status="RESOLVED"
        )
        db_session.add(sup_user)
        db_session.flush()

    # Agregar log de excepcion del supervisor conforme a R2-12
    audit_ex = AuditLog(
        user_id=sup_user.id,
        tenant_id="mega_tenant",
        action="SUPERVISOR_EXCEPTION_SELECT",
        entity_type="SupplierOffer",
        entity_id=str(base_case_setup["offer"].id),
        details="Supervisor bypass justified with sufficient substantive detail",
        status="WARNING"
    )
    db_session.add(audit_ex)
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "PASS"

def test_accuracy_gate_fails_missing_mandatory_eval(db_session, base_case_setup):
    db_session.delete(base_case_setup["ev"])
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("no cuenta con evaluación" in e for e in result["errors"])

def test_accuracy_gate_fails_negative_mandatory_eval(db_session, base_case_setup):
    ev = base_case_setup["ev"]
    ev.status = "FAILED"
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("no aprobatoria" in e for e in result["errors"])

def test_accuracy_gate_fails_missing_evidence_in_p12_strict(db_session, base_case_setup):
    db_session.delete(base_case_setup["ore"])
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("carece de evidencia VERIFIED" in e for e in result["errors"])

def test_accuracy_gate_historical_p11_regime_allows_missing_p12_evidence(db_session, base_case_setup):
    case = base_case_setup["case"]
    case.traceability_regime = "HISTORICAL_P11"
    db_session.delete(base_case_setup["ore"])
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert result["status"] == "PASS"

def test_accuracy_gate_preserves_discarded_offers_without_failing(db_session, base_case_setup):
    case = base_case_setup["case"]
    # Agregar segundo proveedor y oferta descartada
    s2 = db_session.query(Supplier).filter_by(ruc="20999888777", tenant_id="mega_tenant").first()
    if not s2:
        s2 = Supplier(tenant_id="mega_tenant", ruc="20999888777", business_name="Descartado SAC")
        db_session.add(s2)
        db_session.flush()

    offer2 = SupplierOffer(
        case_id=case.id,
        supplier_id=s2.id,
        status="REJECTED",
        currency="PEN",
        price=99000.0,
        total_amount=99000.0
    )
    db_session.add(offer2)
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert result["status"] == "PASS"

def test_accuracy_gate_fails_zero_mandatory_requirements(db_session, base_case_setup):
    db_session.delete(base_case_setup["ore"])
    db_session.delete(base_case_setup["ev"])
    db_session.delete(base_case_setup["req"])
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("carece de requisitos obligatorios" in e for e in result["errors"])

def test_accuracy_gate_fails_empty_fragment(db_session, base_case_setup):
    ore = base_case_setup["ore"]
    ore.fragment = "   "
    from app.models.v6.offer_evidence import OfferEvidence
    offer_ev = db_session.query(OfferEvidence).filter_by(id=ore.offer_evidence_id).first()
    offer_ev.fragment = ""
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("fragmento original vacío" in e for e in result["errors"])

def test_accuracy_gate_fails_invalid_page(db_session, base_case_setup):
    ore = base_case_setup["ore"]
    ore.page = 0
    from app.models.v6.offer_evidence import OfferEvidence
    offer_ev = db_session.query(OfferEvidence).filter_by(id=ore.offer_evidence_id).first()
    offer_ev.page = None
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("número de página" in e for e in result["errors"])

def test_accuracy_gate_fails_missing_verified_by(db_session, base_case_setup):
    ore = base_case_setup["ore"]
    ore.verified_by = None
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("verified_by nulo" in e for e in result["errors"])

def test_accuracy_gate_fails_ineligible_vfm(db_session, base_case_setup):
    offer = base_case_setup["offer"]
    offer.status = "OBSERVED" # Causes VfM to mark offer as ineligible
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("no es elegible según Value for Money" in e for e in result["errors"])


def test_accuracy_gate_fails_missing_physical_document_in_p12_strict(db_session, base_case_setup):
    """R3-04: En régimen P12_STRICT, la falta o inaccesibilidad del archivo físico original bloquea la certificación."""
    doc = base_case_setup["doc"]
    doc.stored_path = "/nonexistent/path/never_uploaded.pdf"
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("no es accesible o no existe en el almacenamiento autorizado" in e for e in result["errors"])


def test_accuracy_gate_fails_sanctioned_supplier_even_with_exception(db_session, base_case_setup):
    """R3-02: Proveedores sancionados están terminantemente prohibidos incluso con excepción."""
    profile = base_case_setup["profile"]
    profile.validation_status = "SANCTIONED"

    sup_user = db_session.query(User).filter_by(role="SUPERVISOR", tenant_id="mega_tenant").first()
    if not sup_user:
        sup_user = User(
            username="supervisor_p13_gate",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="fake",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(sup_user)
        db_session.flush()

    audit_ex = AuditLog(
        user_id=sup_user.id,
        tenant_id="mega_tenant",
        action="SUPERVISOR_EXCEPTION_SELECT",
        entity_type="SupplierOffer",
        entity_id=str(base_case_setup["offer"].id),
        details="Supervisor bypass justified with sufficient substantive detail",
        status="WARNING"
    )
    db_session.add(audit_ex)
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("SANCTIONED" in e for e in result["errors"])


def test_accuracy_gate_fails_supervisor_exception_after_selection(db_session, base_case_setup):
    """R3-02: La excepción no puede ser posterior a la selección final (causalidad temporal)."""
    from datetime import datetime, timezone, timedelta
    profile = base_case_setup["profile"]
    profile.validation_status = "UNVERIFIED"

    final_sel = base_case_setup["final_sel"]
    final_sel.created_at = datetime.now(timezone.utc) - timedelta(hours=2)

    sup_user = db_session.query(User).filter_by(role="SUPERVISOR", tenant_id="mega_tenant").first()
    if not sup_user:
        sup_user = User(
            username="supervisor_p13_gate",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="fake",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(sup_user)
        db_session.flush()

    audit_ex = AuditLog(
        user_id=sup_user.id,
        tenant_id="mega_tenant",
        action="SUPERVISOR_EXCEPTION_SELECT",
        entity_type="SupplierOffer",
        entity_id=str(base_case_setup["offer"].id),
        details="Excepción registrada a posteriori sin causalidad válida.",
        status="WARNING",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(audit_ex)
    db_session.commit()

    result = TechnicalReportAccuracyGate.validate_for_p13(db_session, base_case_setup["case"].id, "mega_tenant")
    assert result["status"] == "FAIL"
    assert any("violando la causalidad temporal" in e for e in result["errors"])


