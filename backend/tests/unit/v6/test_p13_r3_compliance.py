import os
import tempfile
import hashlib
import time
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest

from app.core.config import settings
from app.models.domain import CaseFile, User, Tenant, UploadedDocument, AuditLog
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.generated_output import GeneratedOutput
from app.models.v6.output_template import OutputTemplate

from app.services.v6.reporting.accuracy_gate import TechnicalReportAccuracyGate
from app.services.v6.reporting.technical_report_service import TechnicalReportService
from app.services.v6.reporting.pdf_report_generator import PdfReportGenerator
from app.services.v6.reporting.canonical_serializer import CanonicalSerializer
from fastapi import HTTPException


@pytest.fixture
def r3_setup(db_session):
    """Fixture determinista aislado para pruebas R3."""
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        db_session.flush()

    op_user = db_session.query(User).filter_by(username="r3_op").first()
    if not op_user:
        op_user = User(
            username="r3_op",
            role="OPERATOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(op_user)
        db_session.flush()

    sup_user = db_session.query(User).filter_by(username="r3_sup").first()
    if not sup_user:
        sup_user = User(
            username="r3_sup",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(sup_user)
        db_session.flush()

    case = CaseFile(
        title="Expediente R3 Auditoría",
        status="APPROVED",
        contract_type="BIENES",
        tenant_id="mega_tenant",
        assigned_to_user_id=op_user.id,
        traceability_regime="P12_STRICT",
        siga_number="EXP-R3-001"
    )
    db_session.add(case)
    db_session.flush()

    workflow = CaseWorkflow(case_id=case.id, status="APPROVED", supervisor_id=sup_user.id)
    db_session.add(workflow)

    # Proveedor con RUC formalmente válido (SUNAT 20131312955)
    supplier = Supplier(
        tenant_id="mega_tenant",
        ruc="20131312955",
        business_name="Consorcio R3 Oficial SAC"
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
        price=25000.0,
        total_amount=25000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(
        case_id=case.id,
        supplier_offer_id=offer.id,
        selected_by=op_user.id,
        status="UNDER_REVIEW",
        justification_comment="Selección justificada con propuesta técnica conforme."
    )
    db_session.add(attempt)
    db_session.flush()

    final_sel = SupplierSelectionFinal(case_id=case.id, attempt_id=attempt.id)
    db_session.add(final_sel)
    db_session.flush()

    # Archivo físico auténtico
    doc_file = os.path.join(tempfile.gettempdir(), f"r3_doc_{case.id}.pdf")
    with open(doc_file, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 35 >>\nstream\nBT /F1 12 Tf 100 700 Td (Garantia 24 meses) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000201 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n287\n%%EOF\n")

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="especificaciones_r3.pdf",
        stored_path=doc_file,
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.flush()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía técnica de fábrica",
        mandatory=True
    )
    db_session.add(req)
    db_session.flush()

    ev = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        status="PASSED",
        validated_by=op_user.id
    )
    db_session.add(ev)
    db_session.flush()

    offer_ev = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="FICHA_TECNICA",
        fragment="Garantia 24 meses",
        confidence=0.99,
        page=1
    )
    db_session.add(offer_ev)
    db_session.flush()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=offer_ev.id,
        document_id=doc.id,
        source_document="especificaciones_r3.pdf",
        page=1,
        fragment="Garantia 24 meses",
        verification_status="VERIFIED",
        verified_by=op_user.id
    )
    db_session.add(ore)
    db_session.commit()

    yield {
        "tenant": tenant,
        "operator": op_user,
        "supervisor": sup_user,
        "case": case,
        "supplier": supplier,
        "profile": profile,
        "offer": offer,
        "attempt": attempt,
        "final_sel": final_sel,
        "doc": doc,
        "doc_file": doc_file,
        "req": req,
        "ore": ore
    }

    if os.path.exists(doc_file):
        try:
            os.remove(doc_file)
        except OSError:
            pass


def test_r3_02_p12_warning_exception_compatibility_real_service(db_session, r3_setup):
    """
    R3-02: Compatibilidad real P12.
    El servicio de selección de P12 genera SUPERVISOR_EXCEPTION_SELECT con status='WARNING'.
    TechnicalReportAccuracyGate debe aceptar exactamente este evento legítimo si está correlacionado
    con el actor, la oferta, el tenant y justificación material suficiente.
    """
    case = r3_setup["case"]
    offer = r3_setup["offer"]
    supervisor = r3_setup["supervisor"]
    profile = r3_setup["profile"]

    # Perfil UNVERIFIED requiere excepción
    profile.validation_status = "UNVERIFIED"
    db_session.commit()

    # 1. Sin auditoría -> Falla
    gate_res1 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert gate_res1["status"] == "FAIL"
    assert any("sin excepción autorizada" in e for e in gate_res1["errors"])

    # 2. Excepción con status='WARNING' legítimo de P12
    p12_audit = AuditLog(
        user_id=supervisor.id,
        tenant_id="mega_tenant",
        action="SUPERVISOR_EXCEPTION_SELECT",
        entity_type="SupplierOffer",
        entity_id=str(offer.id),
        details="Supervisor autoriza contratación por necesidad técnica urgente acreditada.",
        status="WARNING"
    )
    db_session.add(p12_audit)
    db_session.commit()

    # 3. Gate debe aceptar la excepción legítima en estado WARNING
    gate_res2 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert gate_res2["status"] == "PASS"

    # 4. Negativo: Proveedor SANCTIONED no puede ser autorizado ni con excepción
    profile.validation_status = "SANCTIONED"
    db_session.commit()
    gate_res3 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert gate_res3["status"] == "FAIL"
    assert any("SANCTIONED" in e for e in gate_res3["errors"])


def test_r3_03_export_pdf_fail_closed_null_hashes_and_tampering(db_session, r3_setup):
    """
    R3-03: Exportación PDF fail-closed para hashes nulos, vacíos, mal formados o manipulados.
    """
    case = r3_setup["case"]
    supervisor = r3_setup["supervisor"]

    # Crear PDF real en disco
    valid_pdf_content = b"%PDF-1.4\nAuthentic P13 Report Content\n%%EOF\n"
    pdf_sha = hashlib.sha256(valid_pdf_content).hexdigest()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(valid_pdf_content)
        tmp_path = tmp.name

    snapshot = {"case_id": case.id, "winner": {"supplier_name": "Consorcio R3"}}
    snap_bytes = CanonicalSerializer.serialize_to_bytes(snapshot)
    snap_sha = CanonicalSerializer.calculate_hash(snap_bytes)

    html_content = "<html><body>Informe P13</body></html>"
    html_sha = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

    tpl = db_session.query(OutputTemplate).first()
    report = GeneratedOutput(
        case_id=case.id,
        template_id=tpl.id if tpl else 1,
        content_rendered=html_content,
        generation_hash=snap_sha,
        template_version="1.0",
        accuracy_gate_result="ACCURACY_PASSED",
        source_snapshot=snapshot,
        snapshot_hash=snap_sha,
        status="APPROVED",
        report_kind=TechnicalReportService.REPORT_KIND,
        html_output=html_content,
        html_hash=html_sha,
        pdf_storage_path=tmp_path,
        pdf_hash=pdf_sha
    )
    db_session.add(report)
    db_session.commit()

    try:
        # A) Caso normal: debe descargar exitosamente
        pdf_bytes, filename = TechnicalReportService.get_export_pdf_bytes(
            db_session, report.id, supervisor.id, "mega_tenant"
        )
        assert pdf_bytes == valid_pdf_content

        # B) pdf_hash es NULL -> Bloqueo fail-closed
        report.pdf_hash = None
        db_session.commit()
        with pytest.raises(HTTPException) as exc1:
            TechnicalReportService.get_export_pdf_bytes(db_session, report.id, supervisor.id, "mega_tenant")
        assert exc1.value.status_code == 500

        # C) snapshot_hash es cadena vacía -> Bloqueo fail-closed
        report.pdf_hash = pdf_sha
        report.snapshot_hash = ""
        db_session.commit()
        with pytest.raises(HTTPException) as exc2:
            TechnicalReportService.get_export_pdf_bytes(db_session, report.id, supervisor.id, "mega_tenant")
        assert exc2.value.status_code == 500

        # D) html_hash tiene longitud errónea (63 caracteres) -> Bloqueo fail-closed
        report.snapshot_hash = snap_sha
        report.html_hash = html_sha[:-1]
        db_session.commit()
        with pytest.raises(HTTPException) as exc3:
            TechnicalReportService.get_export_pdf_bytes(db_session, report.id, supervisor.id, "mega_tenant")
        assert exc3.value.status_code == 500

        # E) Manipulación de 1 solo byte en disco -> Discrepancia criptográfica
        report.html_hash = html_sha
        db_session.commit()
        with open(tmp_path, "wb") as f:
            f.write(valid_pdf_content[:-1] + b"X")

        with pytest.raises(HTTPException) as exc4:
            TechnicalReportService.get_export_pdf_bytes(db_session, report.id, supervisor.id, "mega_tenant")
        assert exc4.value.status_code == 500
        assert "difiere de la firma registrada" in exc4.value.detail

        # F) Archivo PDF no existente en almacenamiento -> Bloqueo fail-closed
        os.remove(tmp_path)
        with pytest.raises(HTTPException) as exc5:
            TechnicalReportService.get_export_pdf_bytes(db_session, report.id, supervisor.id, "mega_tenant")
        assert exc5.value.status_code == 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_r3_04_p12_strict_physical_document_verification(db_session, r3_setup):
    """
    R3-04: Documentos acreditados bajo P12_STRICT.
    La inexistencia física del binario original en almacenamiento bloquea la certificación.
    """
    case = r3_setup["case"]
    doc = r3_setup["doc"]
    doc_file = r3_setup["doc_file"]

    # 1. Con archivo físico existente en almacenamiento -> Pasa
    res1 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert res1["status"] == "PASS"

    # 2. Si el archivo físico desaparece de disco -> Falla fail-closed
    os.remove(doc_file)
    res2 = TechnicalReportAccuracyGate.validate_for_p13(db_session, case.id, "mega_tenant")
    assert res2["status"] == "FAIL"
    assert any("no es accesible o no existe en el almacenamiento autorizado" in e for e in res2["errors"])


def test_r3_08_safe_resolve_storage_path_adversarial():
    """
    R3-08: Defensa estricta contra path traversal, symlinks y rutas absolutas externas.
    """
    with tempfile.TemporaryDirectory() as safe_root:
        # Archivo legítimo dentro de la raíz
        legit_file = os.path.join(safe_root, "legit.pdf")
        with open(legit_file, "wb") as f:
            f.write(b"%PDF-1.4 test")

        resolved = TechnicalReportService.safe_resolve_storage_path(legit_file, allowed_roots=[safe_root])
        assert resolved == os.path.realpath(legit_file)

        # 1. Path traversal con ../
        traversal = os.path.join(safe_root, "subdir", "..", "..", "etc", "passwd")
        assert TechnicalReportService.safe_resolve_storage_path(traversal, allowed_roots=[safe_root]) is None

        # 2. Ruta absoluta fuera de safe_root
        with tempfile.NamedTemporaryFile() as ext_file:
            assert TechnicalReportService.safe_resolve_storage_path(ext_file.name, allowed_roots=[safe_root]) is None

        # 3. Enlace simbólico hacia archivo externo
        with tempfile.NamedTemporaryFile() as target_ext:
            symlink_path = os.path.join(safe_root, "link_to_ext.pdf")
            try:
                os.symlink(target_ext.name, symlink_path)
                assert TechnicalReportService.safe_resolve_storage_path(symlink_path, allowed_roots=[safe_root]) is None
            except (OSError, NotImplementedError):
                pass  # En Windows sin privilegios de symlink


def test_r3_09_orphan_reconciliation_durability(db_session):
    """
    R3-09: Reconciliación de huérfanos durable y fail-safe.
    - No elimina archivos .pdf definitivos si valid_paths es None o vacío.
    - Elimina archivos .tmp_* con antigüedad >= max_age_seconds.
    - Elimina archivos .pdf huérfanos solo si valid_paths está explícitamente poblado y el archivo no está en él.
    """
    with tempfile.TemporaryDirectory() as target_dir:
        tmp_file = os.path.join(target_dir, ".tmp_uuid123_report.pdf")
        valid_pdf = os.path.join(target_dir, "report_p13_v1.pdf")
        orphan_pdf = os.path.join(target_dir, "report_p13_v2_abandoned.pdf")

        for p in [tmp_file, valid_pdf, orphan_pdf]:
            with open(p, "wb") as f:
                f.write(b"%PDF-1.4 dummy")

        # Modificar mtime para simular antigüedad de 2 horas (7200s)
        old_time = time.time() - 7200
        for p in [tmp_file, valid_pdf, orphan_pdf]:
            os.utime(p, (old_time, old_time))

        # 1. Fail-safe: si valid_paths es None, SOLO elimina temporales .tmp_*, NUNCA .pdf
        cleaned1 = PdfReportGenerator.reconcile_orphans(target_dir, valid_paths=None, max_age_seconds=3600)
        assert cleaned1 == 1
        assert not os.path.exists(tmp_file)
        assert os.path.exists(valid_pdf)
        assert os.path.exists(orphan_pdf)

        # 2. Con valid_paths explícito: purga orphan_pdf pero preserva valid_pdf
        cleaned2 = PdfReportGenerator.reconcile_orphans(target_dir, valid_paths=[valid_pdf], max_age_seconds=3600)
        assert cleaned2 == 1
        assert not os.path.exists(orphan_pdf)
        assert os.path.exists(valid_pdf)


def test_r3_10_peruvian_ruc_modulo_11_validation():
    """
    R3-10: Validación formal de RUC peruano según algoritmo módulo 11 de SUNAT.
    """
    # RUCs válidos oficiales
    sunat_ruc = "20131312955"  # SUNAT
    bn_ruc = "20100030595"     # Banco de la Nación
    valid_res1 = TechnicalReportService.validate_peruvian_ruc(sunat_ruc)
    assert valid_res1["is_valid"] is True
    assert valid_res1["formal_validation"] == "FORMALLY_VALID_MOD11"
    assert valid_res1["taxpayer_category"] == "PERSONA_JURIDICA"
    assert valid_res1["sunat_online_status"] == "OFFLINE_FORMAL_VERIFICATION_ONLY"

    valid_res2 = TechnicalReportService.validate_peruvian_ruc(bn_ruc)
    assert valid_res2["is_valid"] is True

    # RUCs inválidos
    # 1. Longitud incorrecta
    inv_len = TechnicalReportService.validate_peruvian_ruc("2013131295")
    assert inv_len["is_valid"] is False
    assert inv_len["formal_validation"] == "INVALID_LENGTH"

    # 2. Caracteres no numéricos
    inv_num = TechnicalReportService.validate_peruvian_ruc("2013131295A")
    assert inv_num["is_valid"] is False
    assert inv_num["formal_validation"] == "INVALID_FORMAT"

    # 3. Prefijo no admitido (e.g. 30...)
    inv_pre = TechnicalReportService.validate_peruvian_ruc("30131312955")
    assert inv_pre["is_valid"] is False
    assert inv_pre["formal_validation"] == "INVALID_PREFIX"

    # 4. Dígito verificador alterado (debe ser 5, se pasa 4)
    inv_chk = TechnicalReportService.validate_peruvian_ruc("20131312954")
    assert inv_chk["is_valid"] is False
    assert inv_chk["formal_validation"] == "INVALID_CHECKSUM"


def test_r3_reconcile_all_orphans_executes_against_real_model_and_preserves_other_pdfs():
    """Regression: actual DB-backed reconciler must resolve the real GeneratedOutput ORM module."""
    from unittest.mock import MagicMock
    with tempfile.TemporaryDirectory() as reports_root:
        case_dir = os.path.join(reports_root, "tenant", "case_1")
        os.makedirs(case_dir)
        valid = os.path.join(case_dir, "report_p13_v1_abcdef12.pdf")
        orphan = os.path.join(case_dir, "report_p13_v2_abcdef34.pdf")
        unrelated = os.path.join(case_dir, "other_module.pdf")
        for f in (valid, orphan, unrelated):
            with open(f, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            os.utime(f, (time.time() - 7200, time.time() - 7200))
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [(valid,)]
        count = PdfReportGenerator.reconcile_all_orphans(db, reports_root, max_age_seconds=3600)
        assert count == 1
        assert os.path.exists(valid)
        assert not os.path.exists(orphan)
        assert os.path.exists(unrelated), "Reconciler must not delete other module files"
        db.query.assert_called_once()
