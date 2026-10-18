import os
import tempfile
import hashlib
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.models.domain import CaseFile, User, Tenant, UploadedDocument, AuditLog
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.contractual_condition import ContractualCondition
from app.models.v6.output_template import OutputTemplate
from app.models.v6.generated_output import GeneratedOutput

from app.services.v6.reporting.canonical_serializer import CanonicalSerializer
from app.services.v6.reporting.accuracy_gate import TechnicalReportAccuracyGate
from app.services.v6.reporting.technical_report_service import TechnicalReportService
from app.services.v6.reporting.pdf_report_generator import PdfReportGenerator
from app.services.v6.reporting.report_template_engine import ReportTemplateEngine
from app.api.routers.v6_outputs import prepare_output, export_output, export_p13_report_html


@pytest.fixture
def r2_setup(db_session):
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Municipalidad Provincial de Prueba")
        db_session.add(tenant)
        db_session.flush()

    operator = db_session.query(User).filter_by(username="operator_r2_test").first()
    if not operator:
        operator = User(
            username="operator_r2_test",
            role="OPERATOR",
            tenant_id="mega_tenant",
            password_hash="fake",
            tenant_resolution_status="RESOLVED"
        )
        db_session.add(operator)
        db_session.flush()

    supervisor = db_session.query(User).filter_by(username="supervisor_r2_test").first()
    if not supervisor:
        supervisor = User(
            username="supervisor_r2_test",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="fake",
            tenant_resolution_status="RESOLVED"
        )
        db_session.add(supervisor)
        db_session.flush()

    case = CaseFile(
        title="Expediente de Cumplimiento R2",
        contract_type="BIENES",
        status="APPROVED",
        tenant_id="mega_tenant",
        assigned_to_user_id=operator.id,
        traceability_regime="P12_STRICT"
    )
    db_session.add(case)
    db_session.flush()

    workflow = CaseWorkflow(case_id=case.id, status="APPROVED", supervisor_id=supervisor.id)
    db_session.add(workflow)

    supplier = Supplier(
        tenant_id="mega_tenant",
        ruc="20555666773",
        business_name="Soluciones Informáticas Integrales SAC"
    )
    db_session.add(supplier)
    db_session.flush()

    profile = SupplierProfile(
        supplier_id=supplier.id,
        validation_status="VERIFIED"
    )
    db_session.add(profile)
    db_session.flush()

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        status="SELECTED",
        evaluation_status="SELECTED",
        price=18500.0,
        total_amount=18500.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(
        case_id=case.id,
        supplier_offer_id=offer.id,
        selected_by=operator.id,
        status="UNDER_REVIEW",
        justification_comment="Decisión fundada en mayor respaldo de servicio postventa local."
    )
    db_session.add(attempt)
    db_session.flush()

    final_sel = SupplierSelectionFinal(
        case_id=case.id,
        attempt_id=attempt.id
    )
    db_session.add(final_sel)
    db_session.flush()

    return {
        "tenant": tenant,
        "operator": operator,
        "supervisor": supervisor,
        "case": case,
        "supplier": supplier,
        "profile": profile,
        "offer": offer,
        "attempt": attempt,
        "final_sel": final_sel
    }


def test_r2_01_contractual_conditions_use_real_orm_columns(db_session, r2_setup):
    """
    R2-01: ContractualCondition usa únicamente las columnas reales del ORM:
    key, label, required_value, offered_value, final_value, unit, resolution_rule, status.
    No existen condition_type ni value.
    """
    offer = r2_setup["offer"]

    cond1 = ContractualCondition(
        supplier_offer_id=offer.id,
        key="PLAZO_ENTREGA",
        label="Plazo de Entrega en Almacén",
        required_value="15 días calendario",
        offered_value="10 días calendario",
        final_value="10 días calendario",
        unit="días",
        resolution_rule="OFFER_PREFERRED",
        status="RESOLVED"
    )
    cond2 = ContractualCondition(
        supplier_offer_id=offer.id,
        key="GARANTIA_FABRICA",
        label="Garantía de Fábrica",
        required_value="24 meses",
        offered_value="36 meses",
        final_value="36 meses",
        unit="meses",
        resolution_rule="OFFER_PREFERRED",
        status="RESOLVED"
    )
    db_session.add_all([cond1, cond2])
    db_session.flush()

    case = r2_setup["case"]
    snapshot = TechnicalReportService.build_snapshot(db_session, case, 1)
    s9 = snapshot.get("section_9_contractual_conditions", {})

    assert s9.get("has_conditions") is True
    conditions = s9.get("conditions", [])
    assert len(conditions) == 2

    c1 = next(c for c in conditions if c["key"] == "PLAZO_ENTREGA")
    assert c1["label"] == "Plazo de Entrega en Almacén"
    assert c1["required_value"] == "15 días calendario"
    assert c1["offered_value"] == "10 días calendario"
    assert c1["final_value"] == "10 días calendario"
    assert c1["unit"] == "días"
    assert c1["resolution_rule"] == "OFFER_PREFERRED"

    # Verificar que el motor de plantillas HTML renderiza estas condiciones
    sections = ReportTemplateEngine._build_12_sections_html(snapshot, {})
    s9_html = sections["section_9_contractual_conditions_html"]
    assert "Plazo de Entrega en Almacén" in s9_html
    assert "10 días calendario" in s9_html
    assert "Garantía de Fábrica" in s9_html
    assert "36 meses" in s9_html


def test_r2_02_prepare_output_missing_supplier_or_price_rejects(db_session, r2_setup):
    """
    R2-02: prepare_output rechaza con HTTP 400 cuando el proveedor o el precio están incompletos
    o son inválidos, sin persistir perfil ficticio ni recurrir a Tech Corp, 20123456789 o 5000.0.
    """
    case = r2_setup["case"]
    operator = r2_setup["operator"]
    offer = r2_setup["offer"]
    supplier = r2_setup["supplier"]

    # Caso A: Precio None o <= 0
    offer.total_amount = 0.0
    offer.price = 0.0
    db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        prepare_output(case_id=case.id, case=case, current_user=operator, db=db_session)
    assert exc_info.value.status_code == 400
    assert "Importe de la oferta" in exc_info.value.detail

    # Restaurar precio
    offer.total_amount = 25000.0
    offer.price = 25000.0
    db_session.flush()

    # Caso B: RUC inválido ("NO_RUC" o vacío)
    supplier.ruc = "NO_RUC"
    db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        prepare_output(case_id=case.id, case=case, current_user=operator, db=db_session)
    assert exc_info.value.status_code == 400
    assert "Datos del proveedor incompletos" in exc_info.value.detail


def test_r2_03_authentic_document_binary_sha256(db_session, r2_setup):
    """
    R2-03: SHA-256 de documento original solo se declara verificado si los bytes físicos
    son legibles en el almacenamiento. Si el archivo no existe, no se inventa DOC-REG-{id}.
    """
    case = r2_setup["case"]

    # Crear archivo temporal real
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(b"%PDF-1.4 Fake Authentic Document Content for R2 Test")
        tmp_path = tmp.name

    expected_sha256 = hashlib.sha256(b"%PDF-1.4 Fake Authentic Document Content for R2 Test").hexdigest()

    doc_real = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="terminos_referencia.pdf",
        stored_path=tmp_path,
        mime_type="application/pdf",
        processing_status="completed"
    )
    doc_missing = UploadedDocument(
        case_id=case.id,
        document_type="offer",
        original_filename="propuesta_desaparecida.pdf",
        stored_path="/storage/inaccessible/path_non_existent.pdf",
        mime_type="application/pdf",
        processing_status="completed"
    )
    db_session.add_all([doc_real, doc_missing])
    db_session.flush()

    try:
        snapshot = TechnicalReportService.build_snapshot(db_session, case, 1)
        s3_docs = snapshot.get("section_3_examined_documents", [])

        real_entry = next(d for d in s3_docs if d["filename"] == "terminos_referencia.pdf")
        assert real_entry["binary_hash_verified"] is True
        assert real_entry["binary_sha256"] == expected_sha256

        missing_entry = next(d for d in s3_docs if d["filename"] == "propuesta_desaparecida.pdf")
        assert missing_entry["binary_hash_verified"] is False
        assert missing_entry["binary_sha256"] is None
        assert not str(missing_entry.get("sha256", "")).startswith("DOC-REG-")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_r2_04_vfm_real_motivation_and_divergence(db_session, r2_setup):
    """
    R2-04: Sustitución de justificación fija por la motivación real registrada.
    Si hay divergencia del ranking, se consigna explícitamente sin mérito ficticio.
    Eliminada la recomendación automática de perfeccionamiento contractual.
    """
    case = r2_setup["case"]
    attempt = r2_setup["attempt"]
    attempt.justification_comment = "Decisión fundada en mayor respaldo de servicio postventa local."
    db_session.flush()

    snapshot = TechnicalReportService.build_snapshot(db_session, case, 1)
    s11 = snapshot.get("section_11_motivation_selection", {})
    assert "Decisión fundada en mayor respaldo de servicio postventa local." in s11.get("justification_comment", "")

    s12 = snapshot.get("section_12_conclusion_audit", {})
    assert "perfeccionamiento" not in s12.get("final_recommendation", "").lower()
    assert "buena pro" not in s12.get("final_recommendation", "").lower()


def test_r2_05_accuracy_gate_cross_document_divergence_fails(db_session, r2_setup):
    """
    R2-05: TechnicalReportAccuracyGate rechaza divergencias de document_id entre
    OfferRequirementEvidence y OfferEvidence, o ausencia de página/fragmento.
    """
    case = r2_setup["case"]
    offer = r2_setup["offer"]
    operator = r2_setup["operator"]

    doc1 = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="doc1.pdf",
        stored_path="/tmp/doc1.pdf",
        mime_type="application/pdf",
        processing_status="completed"
    )
    doc2 = UploadedDocument(
        case_id=case.id,
        document_type="offer",
        original_filename="doc2.pdf",
        stored_path="/tmp/doc2.pdf",
        mime_type="application/pdf",
        processing_status="completed"
    )
    db_session.add_all([doc1, doc2])
    db_session.flush()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        key="REQ-CRITICAL",
        description="Capacidad operativa certificada",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.flush()

    eval_rec = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        status="PASSED",
        explanation="Cumple requisito",
        evaluation_confidence=0.98,
        validated_by=operator.id
    )
    db_session.add(eval_rec)
    db_session.flush()

    from app.models.v6.offer_evidence import OfferEvidence
    ev = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc1.id,
        document_type="PROPUESTA",
        fragment="Acreditación conforme",
        page=3
    )
    db_session.add(ev)
    db_session.flush()

    # Inconsistencia deliberada: req_evidence asocia doc2 mientras offer_ev apunta a doc1
    link = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=ev.id,
        document_id=doc2.id,  # DIVERGENCIA!
        source_document="doc2.pdf",
        page=3,
        fragment="Acreditación conforme",
        verification_status="VERIFIED",
        verified_by=operator.id
    )
    db_session.add(link)
    db_session.flush()

    gate_result = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert gate_result["status"] == "FAIL"


def test_r2_08_post_commit_pdf_file_preserved(db_session, r2_setup, monkeypatch):
    """
    R2-08: Distinción de tramo pre-commit y post-commit.
    Si db.refresh() o un paso posterior al commit falla, el archivo PDF aprobado
    en disco NO se elimina (permanece durable).
    """
    case = r2_setup["case"]
    operator = r2_setup["operator"]
    supervisor = r2_setup["supervisor"]

    # Crear plantilla P13 si no existe
    tpl = db_session.query(OutputTemplate).filter_by(type="INFORME_TECNICO_EVALUACION").first()
    if not tpl:
        tpl = OutputTemplate(
            type="INFORME_TECNICO_EVALUACION",
            version="1.0",
            entity_name="Abast-gp",
            content="<div>Informe R2 Test</div>",
            checksum="fake",
            status="ACTIVE"
        )
        db_session.add(tpl)
        db_session.flush()

    # Mockear gate para que pase la generación
    monkeypatch.setattr(
        TechnicalReportAccuracyGate,
        "validate_for_p13",
        lambda db, c_id, t_id=None: {"status": "PASS", "errors": []}
    )

    report = TechnicalReportService.generate_report(
        db=db_session,
        case_id=case.id,
        user_id=operator.id,
        tenant_id="mega_tenant"
    )
    TechnicalReportService.submit_for_review(
        db=db_session,
        report_id=report.id,
        user_id=operator.id,
        tenant_id="mega_tenant"
    )

    # Simular fallo en db.refresh después del commit
    original_refresh = db_session.refresh

    def fail_refresh(obj, *args, **kwargs):
        if isinstance(obj, GeneratedOutput):
            raise RuntimeError("Simulated Post-Commit DB Refresh Failure")
        return original_refresh(obj, *args, **kwargs)

    monkeypatch.setattr(db_session, "refresh", fail_refresh)

    # Aprobación devuelve exitosamente el reporte y preserva el archivo
    approved = TechnicalReportService.approve_report(
        db=db_session,
        report_id=report.id,
        supervisor_id=supervisor.id,
        tenant_id="mega_tenant",
        user_role="SUPERVISOR",
        approval_notes="Aprobado en test de fallo post-commit"
    )
    assert approved.status == "APPROVED"
    assert approved.pdf_storage_path is not None
    assert os.path.exists(approved.pdf_storage_path)


def test_r2_09_canonical_serializer_set_and_utc_determinism():
    """
    R2-09: CanonicalSerializer normaliza sets de manera determinista
    (ordenados lexicográficamente) y timestamps a UTC con 'Z'.
    """
    obj1 = {"tags": {"bravo", "alfa", "charlie"}, "timestamp": datetime(2026, 10, 18, 10, 30, 0, tzinfo=timezone.utc)}
    obj2 = {"tags": {"charlie", "bravo", "alfa"}, "timestamp": datetime(2026, 10, 18, 10, 30, 0, tzinfo=timezone.utc)}

    h1 = CanonicalSerializer.calculate_hash(obj1)
    h2 = CanonicalSerializer.calculate_hash(obj2)
    assert h1 == h2

    # Verificación de timestamp a UTC con 'Z'
    now_utc = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    now_naive = datetime(2026, 10, 18, 12, 0, 0)
    assert CanonicalSerializer._normalize_obj(now_utc) == "2026-10-18T12:00:00Z"
    assert CanonicalSerializer._normalize_obj(now_naive) == "2026-10-18T12:00:00Z"


def test_r2_10_export_endpoints_semantics(db_session, r2_setup, monkeypatch):
    """
    R2-10:
    - /outputs/{output_id}/export entrega PDF auténtico para P13 sin mutar a EXPORTED.
    - /cases/{case_id}/reports/p13/{report_id}/export/html establece Content-Disposition.
    """
    case = r2_setup["case"]
    operator = r2_setup["operator"]
    supervisor = r2_setup["supervisor"]

    # Crear un reporte P13 aprobado con PDF dummy
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(b"%PDF-1.4 Certified Report Content")
        tmp_pdf_path = tmp.name

    pdf_hash = hashlib.sha256(b"%PDF-1.4 Certified Report Content").hexdigest()

    snapshot = {"case_id": case.id}
    snap_bytes = CanonicalSerializer.serialize_to_bytes(snapshot)
    snap_hash = hashlib.sha256(snap_bytes).hexdigest()

    html_content = "<html><body>Informe Aprobado</body></html>"
    html_hash = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

    tpl = db_session.query(OutputTemplate).first()
    report = GeneratedOutput(
        case_id=case.id,
        template_id=tpl.id if tpl else 1,
        content_rendered=html_content,
        generation_hash=snap_hash,
        template_version="1.0",
        accuracy_gate_result="ACCURACY_PASSED",
        source_snapshot=snapshot,
        snapshot_hash=snap_hash,
        status="APPROVED",
        report_kind=TechnicalReportService.REPORT_KIND,
        html_output=html_content,
        html_hash=html_hash,
        pdf_storage_path=tmp_pdf_path,
        pdf_hash=pdf_hash
    )
    db_session.add(report)
    db_session.commit()

    try:
        # 1. Llamada a export_output para P13
        res = export_output(
            output_id=report.id,
            current_user=supervisor,
            db=db_session
        )
        # Debe entregar Response con media_type application/pdf y Content-Disposition
        assert res.media_type == "application/pdf"
        assert "attachment; filename=" in res.headers["Content-Disposition"]
        assert res.body == b"%PDF-1.4 Certified Report Content"

        # Estado en BD debe conservarse en APPROVED
        db_session.refresh(report)
        assert report.status == "APPROVED"

        # 2. Llamada a export_p13_report_html
        html_res = export_p13_report_html(
            case_id=case.id,
            report_id=report.id,
            case=case,
            current_user=supervisor,
            db=db_session
        )
        assert html_res.status_code == 200
        assert "attachment; filename=" in html_res.headers["Content-Disposition"]
    finally:
        if os.path.exists(tmp_pdf_path):
            os.unlink(tmp_pdf_path)


def test_r2_12_accuracy_gate_supervisor_exception_strict(db_session, r2_setup):
    """
    R2-12: TechnicalReportAccuracyGate valida estrictamente la excepción del supervisor:
    tenant_id coincidente, rol SUPERVISOR o ADMIN, y justificación sustantiva >= 10 chars.
    """
    case = r2_setup["case"]
    operator = r2_setup["operator"]
    supervisor = r2_setup["supervisor"]
    offer = r2_setup["offer"]
    profile = r2_setup["profile"]

    # Cambiar estado del perfil a UNVERIFIED para requerir excepción
    profile.validation_status = "UNVERIFIED"
    db_session.flush()

    # 1. Sin auditoría de excepción -> Falla
    res1 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert res1["status"] == "FAIL"
    assert any("sin excepción autorizada" in e for e in res1["errors"])

    # 2. Excepción por usuario OPERADOR (no autorizado) -> Falla
    audit_op = AuditLog(
        user_id=operator.id,
        tenant_id="mega_tenant",
        action="SUPERVISOR_EXCEPTION_SELECT",
        entity_type="SupplierOffer",
        entity_id=str(offer.id),
        details="Aprobación no autorizada por operador",
        status="SUCCESS"
    )
    db_session.add(audit_op)
    db_session.flush()

    res2 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert res2["status"] == "FAIL"
    assert any("no fue emitida por un actor con rol SUPERVISOR o ADMIN" in e for e in res2["errors"])

    # 3. Excepción por SUPERVISOR pero con detalle trivial (<10 caracteres) -> Falla
    audit_trivial = AuditLog(
        user_id=supervisor.id,
        tenant_id="mega_tenant",
        action="SUPERVISOR_EXCEPTION_SELECT",
        entity_type="SupplierOffer",
        entity_id=str(offer.id),
        details="ok",
        status="SUCCESS"
    )
    db_session.add(audit_trivial)
    db_session.flush()

    res3 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert res3["status"] == "FAIL"
    assert any("carece de justificación/motivación material suficiente" in e for e in res3["errors"])

    # 4. Excepción legítima con rol SUPERVISOR y detalle sustantivo >= 10 caracteres (status WARNING conforme a P12)
    audit_valid = AuditLog(
        user_id=supervisor.id,
        tenant_id="mega_tenant",
        action="SUPERVISOR_EXCEPTION_SELECT",
        entity_type="SupplierOffer",
        entity_id=str(offer.id),
        details="Excepción autorizada conforme a directiva institucional por urgencia acreditada.",
        status="WARNING"
    )
    db_session.add(audit_valid)
    db_session.flush()

    res4 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    # Ya no debe fallar por motivo del proveedor/excepción
    assert not any("sin excepción autorizada" in e or "carece de justificación" in e or "SUPERVISOR o ADMIN" in e for e in res4["errors"])


def test_r2_13_pdf_export_single_read_toctou_prevention(db_session, r2_setup):
    """
    R2-13: get_export_pdf_bytes lee el archivo del PDF una sola vez en memoria,
    calcula el hash sobre esos mismos bytes y retorna exactamente esos bytes,
    eliminando la ventana de concurrencia TOCTOU.
    """
    case = r2_setup["case"]
    supervisor = r2_setup["supervisor"]

    content = b"%PDF-1.4 Single-Read Authentic Content"
    expected_hash = hashlib.sha256(content).hexdigest()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    snapshot = {"case_id": case.id}
    snap_bytes = CanonicalSerializer.serialize_to_bytes(snapshot)
    snap_hash = hashlib.sha256(snap_bytes).hexdigest()

    html_content = "<html><body>Informe Test</body></html>"
    html_hash = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

    tpl = db_session.query(OutputTemplate).first()
    report = GeneratedOutput(
        case_id=case.id,
        template_id=tpl.id if tpl else 1,
        content_rendered=html_content,
        generation_hash=snap_hash,
        template_version="1.0",
        accuracy_gate_result="ACCURACY_PASSED",
        source_snapshot=snapshot,
        snapshot_hash=snap_hash,
        status="APPROVED",
        report_kind=TechnicalReportService.REPORT_KIND,
        html_output=html_content,
        html_hash=html_hash,
        pdf_storage_path=tmp_path,
        pdf_hash=expected_hash
    )
    db_session.add(report)
    db_session.commit()

    try:
        pdf_bytes, filename = TechnicalReportService.get_export_pdf_bytes(
            db=db_session,
            report_id=report.id,
            user_id=supervisor.id,
            tenant_id="mega_tenant"
        )
        assert pdf_bytes == content
        assert filename.endswith(".pdf")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_r2_14_no_synthetic_fallbacks_in_sections_4_and_6(db_session, r2_setup):
    """
    R2-14: Erradicación de valores sintéticos por defecto.
    s4_offers exige RUC y monto positivo reales (no 'NO_RUC' ni 0).
    s6_evidences no genera evidencias de reserva inventadas ni páginas arbitrarias.
    """
    case = r2_setup["case"]
    snapshot = TechnicalReportService.build_snapshot(db_session, case, 1)

    # Verificar ofertas en snapshot
    for offer_item in snapshot.get("section_4_suppliers_offers", []):
        assert offer_item.get("supplier_ruc") != "NO_RUC"
        assert offer_item.get("supplier_name") != "Tech Corp"
        assert offer_item.get("total_amount") > 0

    # Verificar evidencias en snapshot
    for ev_item in snapshot.get("section_6_evidence_traceability", []):
        assert ev_item.get("verification_notes") != "Conformidad técnica verificada"
        assert ev_item.get("verified_by_name") != "Evaluador Autorizado"
