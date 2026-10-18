import pytest
import os
import tempfile
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
from app.services.v6.reporting.technical_report_service import TechnicalReportService

@pytest.fixture
def adversarial_setup(db_session):
    # Tenants
    t1 = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not t1:
        t1 = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(t1)

    t2 = db_session.query(Tenant).filter_by(id="other_tenant").first()
    if not t2:
        t2 = Tenant(id="other_tenant", name="Other Tenant")
        db_session.add(t2)
    db_session.flush()

    # Users
    author_op = db_session.query(User).filter_by(id=10).first()
    if not author_op:
        author_op = User(
            id=10,
            username="author_op",
            role="OPERATOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(author_op)

    author_admin = db_session.query(User).filter_by(id=11).first()
    if not author_admin:
        author_admin = User(
            id=11,
            username="author_admin",
            role="ADMIN",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(author_admin)

    independent_sup = db_session.query(User).filter_by(id=12).first()
    if not independent_sup:
        independent_sup = User(
            id=12,
            username="independent_sup",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(independent_sup)

    unassigned_op = db_session.query(User).filter_by(id=13).first()
    if not unassigned_op:
        unassigned_op = User(
            id=13,
            username="unassigned_op",
            role="OPERATOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(unassigned_op)

    other_tenant_user = db_session.query(User).filter_by(id=14).first()
    if not other_tenant_user:
        other_tenant_user = User(
            id=14,
            username="other_tenant_user",
            role="ADMIN",
            tenant_id="other_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(other_tenant_user)

    readonly_user = db_session.query(User).filter_by(id=15).first()
    if not readonly_user:
        readonly_user = User(
            id=15,
            username="readonly_user",
            role="readonly",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(readonly_user)

    db_session.flush()

    # Case
    case = CaseFile(
        title="Expediente Adversarial",
        contract_type="BIENES",
        status="APPROVED",
        tenant_id="mega_tenant",
        assigned_to_user_id=author_op.id,
        traceability_regime="P12_STRICT"
    )
    db_session.add(case)
    db_session.flush()

    wf = CaseWorkflow(case_id=case.id, status="APPROVED", supervisor_id=independent_sup.id)
    db_session.add(wf)

    supplier = db_session.query(Supplier).filter_by(ruc="20131312955", tenant_id="mega_tenant").first()
    if not supplier:
        supplier = Supplier(tenant_id="mega_tenant", ruc="20131312955", business_name="Seguridad Total SAC")
        db_session.add(supplier)
        db_session.flush()

    profile = db_session.query(SupplierProfile).filter_by(supplier_id=supplier.id).first()
    if not profile:
        profile = SupplierProfile(supplier_id=supplier.id, validation_status="VERIFIED")
        db_session.add(profile)
        db_session.flush()
    else:
        profile.validation_status = "VERIFIED"

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        status="SELECTED",
        currency="PEN",
        price=10000.0,
        total_amount=10000.0
    )
    db_session.add(offer)
    db_session.flush()

    attempt = SupplierSelectionAttempt(
        case_id=case.id,
        supplier_offer_id=offer.id,
        selected_by=author_op.id,
        status="UNDER_REVIEW"
    )
    db_session.add(attempt)
    db_session.flush()

    final_sel = SupplierSelectionFinal(case_id=case.id, attempt_id=attempt.id)
    db_session.add(final_sel)

    # Document (Real physical file on disk for R3-04)
    tmp_doc = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_doc.write(b"%PDF-1.4\n%Authentic Security Specifications\n%%EOF\n")
    tmp_doc.flush()
    tmp_doc.close()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="doc_seguridad.pdf",
        stored_path=tmp_doc.name,
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.flush()

    req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="Requisito Único", mandatory=True)
    db_session.add(req)
    db_session.flush()

    ev = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req.id, status="PASSED", validated_by=author_op.id)
    db_session.add(ev)

    offer_ev = OfferEvidence(supplier_offer_id=offer.id, document_id=doc.id, document_type="Ficha Tecnica", fragment="Cumple", page=1)
    db_session.add(offer_ev)
    db_session.flush()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=offer_ev.id,
        document_id=doc.id,
        page=1,
        fragment="Cumple",
        verified_by=author_op.id,
        verification_status="VERIFIED"
    )
    db_session.add(ore)

    # Active Template
    template = db_session.query(OutputTemplate).filter_by(type="INFORME_TECNICO_EVALUACION", version="1.0").first()
    if not template:
        template = OutputTemplate(
            type="INFORME_TECNICO_EVALUACION",
            version="1.0",
            entity_name="Abast-gp",
            content="<div>Informe {{ selected_supplier_name }}</div>",
            status="ACTIVE"
        )
        db_session.add(template)

    db_session.commit()

    yield {
        "case": case,
        "author_op": author_op,
        "author_admin": author_admin,
        "independent_sup": independent_sup,
        "unassigned_op": unassigned_op,
        "other_tenant_user": other_tenant_user,
        "readonly_user": readonly_user
    }

    if os.path.exists(tmp_doc.name):
        try:
            os.remove(tmp_doc.name)
        except OSError:
            pass


def set_user(user: User):
    def override():
        return user
    app.dependency_overrides[get_current_user] = override
    app.dependency_overrides[get_current_active_user] = override

def test_sod_violation_author_cannot_approve_own_report(client: TestClient, db_session, adversarial_setup):
    case = adversarial_setup["case"]
    author_admin = adversarial_setup["author_admin"]

    # Author generates as admin
    set_user(author_admin)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    assert gen_res.status_code == 200
    report_id = gen_res.json()["id"]

    # Submit to review
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    # Author attempts to approve own report
    appr_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve",
        json={"approval_notes": "Auto-aprobación"}
    )
    assert appr_res.status_code == 403
    assert "Separación de funciones" in appr_res.json()["detail"] or "SoD" in appr_res.json()["detail"]

    # Verify durable security audit log was written
    sod_log = db_session.query(AuditLog).filter_by(action="SOD_VIOLATION_ATTEMPT").first()
    assert sod_log is not None
    assert sod_log.status == "BLOCKED"
    assert sod_log.user_id == author_admin.id

def test_approval_forbidden_when_generated_by_is_null(client: TestClient, db_session, adversarial_setup):
    case = adversarial_setup["case"]
    independent_sup = adversarial_setup["independent_sup"]
    author_op = adversarial_setup["author_op"]

    set_user(author_op)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    # Forzar generated_by = None en base de datos
    report = db_session.query(GeneratedOutput).filter_by(id=report_id).first()
    report.generated_by = None
    db_session.commit()

    set_user(independent_sup)
    appr_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve", json={})
    assert appr_res.status_code == 403
    assert "sin autor registrado" in appr_res.json()["detail"]

def test_role_enforcement_operator_cannot_approve_or_reject(client: TestClient, adversarial_setup):
    case = adversarial_setup["case"]
    author_op = adversarial_setup["author_op"]

    set_user(author_op)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    # Operator cannot approve
    appr_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve", json={})
    assert appr_res.status_code == 403

    # Operator cannot reject
    rej_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/reject", json={"rejection_reason": "Motivo"})
    assert rej_res.status_code == 403

def test_role_enforcement_readonly_cannot_mutate(client: TestClient, db_session, adversarial_setup):
    case = adversarial_setup["case"]
    readonly_user = adversarial_setup["readonly_user"]
    case.assigned_to_user_id = readonly_user.id
    db_session.commit()
    set_user(readonly_user)

    # Readonly cannot generate even if assigned to case
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    assert gen_res.status_code == 403

def test_tenant_isolation_cross_tenant_access_blocked(client: TestClient, adversarial_setup):
    case = adversarial_setup["case"]
    other_tenant_user = adversarial_setup["other_tenant_user"]
    author_op = adversarial_setup["author_op"]

    set_user(author_op)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]

    # User from other tenant tries to access
    set_user(other_tenant_user)
    detail_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}")
    assert detail_res.status_code in [403, 404]

def test_unassigned_operator_cannot_access_case_report(client: TestClient, adversarial_setup):
    case = adversarial_setup["case"]
    author_op = adversarial_setup["author_op"]
    unassigned_op = adversarial_setup["unassigned_op"]

    set_user(author_op)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]

    # Unassigned operator tries to access
    set_user(unassigned_op)
    detail_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}")
    assert detail_res.status_code in [403, 404]

def test_legacy_route_approve_enforces_sod_and_status(client: TestClient, adversarial_setup):
    case = adversarial_setup["case"]
    author_admin = adversarial_setup["author_admin"]

    set_user(author_admin)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]

    # Attempting to use legacy approve from GENERATED fails (409)
    appr_res = client.post(f"/api/v6/outputs/{report_id}/approve")
    assert appr_res.status_code in [403, 409]

def test_legacy_route_export_does_not_mutate_p13_status(client: TestClient, adversarial_setup):
    case = adversarial_setup["case"]
    author_op = adversarial_setup["author_op"]
    independent_sup = adversarial_setup["independent_sup"]

    set_user(author_op)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    set_user(independent_sup)
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve", json={"approval_notes": "OK"})

    # Call legacy export - for P13 outputs it delivers the authentic PDF bytes (R2-10)
    exp_res = client.post(f"/api/v6/outputs/{report_id}/export")
    assert exp_res.status_code == 200
    assert exp_res.headers["content-type"] == "application/pdf"
    assert exp_res.content.startswith(b"%PDF-")

    # Verify report status in DB remains APPROVED (must NOT mutate to EXPORTED)
    detail_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "APPROVED"

def test_export_fails_if_html_hash_tampered(client: TestClient, db_session, adversarial_setup):
    case = adversarial_setup["case"]
    author_op = adversarial_setup["author_op"]
    independent_sup = adversarial_setup["independent_sup"]

    set_user(author_op)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    set_user(independent_sup)
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve", json={"approval_notes": "OK"})

    # Manipular HTML en base de datos
    report = db_session.query(GeneratedOutput).filter_by(id=report_id).first()
    report.content_rendered = report.content_rendered + "<!-- tampered -->"
    report.html_output = report.content_rendered
    db_session.commit()

    set_user(author_op)
    exp_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/export/html")
    assert exp_res.status_code == 500
    assert "Fallo de integridad" in exp_res.json()["detail"]

def test_export_fails_if_pdf_tampered_or_missing(client: TestClient, db_session, adversarial_setup):
    case = adversarial_setup["case"]
    author_op = adversarial_setup["author_op"]
    independent_sup = adversarial_setup["independent_sup"]

    set_user(author_op)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    set_user(independent_sup)
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve", json={"approval_notes": "OK"})

    # Corromper bytes del archivo físico en disco
    report = db_session.query(GeneratedOutput).filter_by(id=report_id).first()
    assert report.pdf_storage_path is not None
    with open(report.pdf_storage_path, "wb") as f:
        f.write(b"TAMPERED_BYTES")

    set_user(author_op)
    exp_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/export/pdf")
    assert exp_res.status_code == 500
    assert "Fallo de integridad" in exp_res.json()["detail"]
