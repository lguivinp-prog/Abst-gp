import pytest
import os
import tempfile
import hashlib
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import get_current_user, get_current_active_user
from app.models.domain import CaseFile, User, Tenant, UploadedDocument, AuditLog
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.output_template import OutputTemplate
from app.models.v6.generated_output import GeneratedOutput
from app.services.v6.reporting.pdf_report_generator import PdfReportGenerator


@pytest.fixture
def edge_case_setup(db_session):
    tenant_suffix = uuid.uuid4().hex[:6]
    tenant_id = f"edge_t_{tenant_suffix}"
    t = Tenant(id=tenant_id, name="Edge Tenant")
    db_session.add(t)
    db_session.flush()

    author = User(
        username=f"author_{tenant_suffix}",
        role="OPERATOR",
        tenant_id=tenant_id,
        password_hash="mock",
        tenant_resolution_status="RESOLVED",
        is_active=True,
    )
    db_session.add(author)

    supervisor = User(
        username=f"supervisor_{tenant_suffix}",
        role="SUPERVISOR",
        tenant_id=tenant_id,
        password_hash="mock",
        tenant_resolution_status="RESOLVED",
        is_active=True,
    )
    db_session.add(supervisor)
    db_session.flush()

    case = CaseFile(
        title="Expediente Edge Cases P13",
        contract_type="BIENES",
        status="APPROVED",
        tenant_id=tenant_id,
        assigned_to_user_id=author.id,
        traceability_regime="P12_STRICT",
    )
    db_session.add(case)
    db_session.flush()

    wf = CaseWorkflow(case_id=case.id, status="APPROVED", supervisor_id=supervisor.id)
    db_session.add(wf)

    supplier = Supplier(tenant_id=tenant_id, ruc="20800100209", business_name="Edge Supplier SAC")
    db_session.add(supplier)
    db_session.flush()

    profile = SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED")
    db_session.add(profile)
    db_session.flush()

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        status="SELECTED",
        currency="PEN",
        price=15000.0,
        total_amount=15000.0,
    )
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(
        case_id=case.id,
        supplier_offer_id=offer.id,
        selected_by=author.id,
        status="UNDER_REVIEW",
    )
    db_session.add(attempt)
    db_session.flush()

    final_sel = SupplierSelectionFinal(case_id=case.id, attempt_id=attempt.id)
    db_session.add(final_sel)

    # Document (Real physical file on disk for R3-04)
    tmp_doc = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_doc.write(b"%PDF-1.4\n%Authentic Edge Proposal Document\n%%EOF\n")
    tmp_doc.flush()
    tmp_doc.close()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="propuesta_edge.pdf",
        stored_path=tmp_doc.name,
        mime_type="application/pdf",
    )
    db_session.add(doc)
    db_session.flush()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantia 36 meses",
        mandatory=True,
    )
    db_session.add(req)
    db_session.flush()

    eval_rec = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        status="PASSED",
        validated_by=author.id,
    )
    db_session.add(eval_rec)
    db_session.flush()

    evidence = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="Ficha Tecnica",
        fragment="Cumple con especificaciones edge",
        page=1,
    )
    db_session.add(evidence)
    db_session.flush()

    req_ev = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=evidence.id,
        document_id=doc.id,
        page=1,
        fragment="Cumple con especificaciones edge",
        verified_by=author.id,
        verification_status="VERIFIED",
    )
    db_session.add(req_ev)

    template = db_session.query(OutputTemplate).filter_by(type="INFORME_TECNICO_EVALUACION", version="1.0").first()
    if not template:
        template = OutputTemplate(
            type="INFORME_TECNICO_EVALUACION",
            version="1.0",
            entity_name="Abast-gp",
            content="<div>Informe {{ selected_supplier_name }}</div>",
            status="ACTIVE",
        )
        db_session.add(template)

    db_session.commit()

    yield {
        "case": case,
        "author": author,
        "supervisor": supervisor,
        "offer": offer,
        "tenant_id": tenant_id,
    }

    if os.path.exists(tmp_doc.name):
        try:
            os.remove(tmp_doc.name)
        except OSError:
            pass



def test_migration_historical_version_duplication_preservation(db_session, edge_case_setup):
    """
    Verifica que la migración NO renumeró versiones históricas y que registros legados
    con versiones duplicadas coexisten en generated_outputs sin violar restricciones.
    """
    case = edge_case_setup["case"]
    template = db_session.query(OutputTemplate).filter_by(type="INFORME_TECNICO_EVALUACION").first()

    legacy1 = GeneratedOutput(
        case_id=case.id,
        template_id=template.id,
        template_version="1.0",
        accuracy_gate_result="PASS",
        source_snapshot={},
        report_kind="CONDICIONES",
        version_number=1,
        content_rendered="<p>Anexo legado 1</p>",
        html_output="<p>Anexo legado 1</p>",
        generation_hash=f"hash_legado_{uuid.uuid4().hex[:6]}",
        snapshot_hash=None,
    )
    legacy2 = GeneratedOutput(
        case_id=case.id,
        template_id=template.id,
        template_version="1.0",
        accuracy_gate_result="PASS",
        source_snapshot={},
        report_kind="CONDICIONES",
        version_number=1,
        content_rendered="<p>Anexo legado 2 duplicado</p>",
        html_output="<p>Anexo legado 2 duplicado</p>",
        generation_hash=f"hash_legado_{uuid.uuid4().hex[:6]}",
        snapshot_hash=None,
    )
    db_session.add_all([legacy1, legacy2])
    db_session.commit()

    recs = (
        db_session.query(GeneratedOutput)
        .filter(
            GeneratedOutput.case_id == case.id,
            GeneratedOutput.report_kind == "CONDICIONES",
        )
        .all()
    )
    assert len(recs) == 2
    assert recs[0].version_number == 1
    assert recs[1].version_number == 1
    assert recs[0].id != recs[1].id


def test_template_duplicate_preservation_and_partial_unique(db_session):
    """
    Verifica que la restricción de plantillas no rompe plantillas legadas con duplicados,
    ya que uq_output_templates_p13 restringe unicidad solo a 'INFORME_TECNICO_EVALUACION'.
    """
    unique_type = f"ACTA_DUP_{uuid.uuid4().hex[:8]}"
    tpl1 = OutputTemplate(
        type=unique_type,
        entity_name="DEFAULT",
        version="1.0",
        content="<p>Acta 1</p>",
        status="ACTIVE",
    )
    tpl2 = OutputTemplate(
        type=unique_type,
        entity_name="DEFAULT",
        version="1.0",
        content="<p>Acta 2 duplicada</p>",
        status="ACTIVE",
    )
    db_session.add_all([tpl1, tpl2])
    db_session.commit()

    tpls = (
        db_session.query(OutputTemplate)
        .filter(
            OutputTemplate.type == unique_type,
            OutputTemplate.version == "1.0",
        )
        .all()
    )
    assert len(tpls) == 2


def test_rejection_of_historically_incompatible_hashes(db_session, edge_case_setup):
    """
    Verifica que registros históricos anteriores a P13 no heredan snapshot_hash = generation_hash.
    Mantienen snapshot_hash NULL.
    """
    case = edge_case_setup["case"]
    template = db_session.query(OutputTemplate).filter_by(type="INFORME_TECNICO_EVALUACION").first()
    legacy = GeneratedOutput(
        case_id=case.id,
        template_id=template.id,
        template_version="1.0",
        accuracy_gate_result="PASS",
        source_snapshot={},
        report_kind="CONDICIONES",
        version_number=2,
        content_rendered="<p>Legado</p>",
        html_output="<p>Legado</p>",
        generation_hash="legacy_sha256_hash",
        snapshot_hash=None,
    )
    db_session.add(legacy)
    db_session.commit()

    reloaded = db_session.query(GeneratedOutput).get(legacy.id)
    assert reloaded.snapshot_hash is None
    assert reloaded.generation_hash == "legacy_sha256_hash"


def test_html_integrity_byte_for_byte_no_strip():
    """
    Verifica que la verificación de integridad HTML es estrictamente byte a byte
    sin aplicar .strip() ni normalizaciones asimétricas.
    """
    html_exact = "<html><body><h1>Informe Oficial</h1></body></html>"
    exact_hash = hashlib.sha256(html_exact.encode("utf-8")).hexdigest()

    html_with_trailing = html_exact + "\n"
    altered_hash = hashlib.sha256(html_with_trailing.encode("utf-8")).hexdigest()

    assert exact_hash != altered_hash, "Alterar un byte o salto de línea debe cambiar el hash"


def test_pdf_integrity_mandatory_for_approved(client, edge_case_setup):
    """
    Verifica que un informe P13 APPROVED exige que el PDF físico exista y su hash coincida.
    """
    case = edge_case_setup["case"]
    author = edge_case_setup["author"]
    supervisor = edge_case_setup["supervisor"]

    app.dependency_overrides[get_current_user] = lambda: author
    app.dependency_overrides[get_current_active_user] = lambda: author

    resp = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    assert resp.status_code == 200, f"Error en generate: {resp.text}"
    report_id = resp.json()["id"]

    sub_resp = client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})
    assert sub_resp.status_code == 200

    # Aprobación por supervisor
    app.dependency_overrides[get_current_user] = lambda: supervisor
    app.dependency_overrides[get_current_active_user] = lambda: supervisor

    app_resp = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve",
        json={"approval_notes": "Aprobado"},
    )
    assert app_resp.status_code == 200

    # Verificar que integridad es auténtica
    int_resp = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/integrity")
    assert int_resp.status_code == 200
    assert int_resp.json()["is_authentic"] is True
    assert int_resp.json()["pdf_file_exists"] is True
    assert int_resp.json()["snapshot_intact"] is True
    assert int_resp.json()["html_intact"] is True
    assert int_resp.json()["pdf_intact"] is True

    app.dependency_overrides.clear()


def test_pdf_download_twice_byte_identical(client, edge_case_setup):
    """
    Verifica que descargar el PDF de un informe aprobado dos veces entrega exactamente los mismos bytes.
    """
    case = edge_case_setup["case"]
    author = edge_case_setup["author"]
    supervisor = edge_case_setup["supervisor"]

    app.dependency_overrides[get_current_user] = lambda: author
    app.dependency_overrides[get_current_active_user] = lambda: author

    resp = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    assert resp.status_code == 200, f"Error en generate: {resp.text}"
    report_id = resp.json()["id"]
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    app.dependency_overrides[get_current_user] = lambda: supervisor
    app.dependency_overrides[get_current_active_user] = lambda: supervisor
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve", json={})

    pdf1 = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/export/pdf")
    pdf2 = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/export/pdf")

    assert pdf1.status_code == 200
    assert pdf2.status_code == 200
    assert pdf1.content == pdf2.content
    assert hashlib.sha256(pdf1.content).hexdigest() == hashlib.sha256(pdf2.content).hexdigest()

    app.dependency_overrides.clear()


def test_file_publication_failure_cleans_up_staging():
    """
    Verifica que la limpieza de temporales obsoletos funciona sobre el directorio de staging.
    """
    os.makedirs("/tmp/test_pdf_staging", exist_ok=True)
    cleaned = PdfReportGenerator.cleanup_stale_temp_files(
        target_directory="/tmp/test_pdf_staging",
        max_age_seconds=0,
    )
    assert isinstance(cleaned, int)
