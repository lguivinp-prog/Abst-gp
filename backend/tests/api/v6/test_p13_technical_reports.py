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

@pytest.fixture
def p13_case_fixture(db_session):
    # Tenant
    tenant = db_session.query(Tenant).filter_by(id="mega_tenant").first()
    if not tenant:
        tenant = Tenant(id="mega_tenant", name="Mega Tenant")
        db_session.add(tenant)
        db_session.flush()

    # Users
    op_user = db_session.query(User).filter_by(id=1).first()
    if not op_user:
        op_user = User(
            id=1,
            username="operator_p13",
            role="OPERATOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(op_user)
    else:
        op_user.role = "OPERATOR"
        op_user.tenant_id = "mega_tenant"

    sup_user = db_session.query(User).filter_by(id=2).first()
    if not sup_user:
        sup_user = User(
            id=2,
            username="supervisor_p13",
            role="SUPERVISOR",
            tenant_id="mega_tenant",
            password_hash="mock",
            tenant_resolution_status="RESOLVED",
            is_active=True
        )
        db_session.add(sup_user)
    else:
        sup_user.role = "SUPERVISOR"
        sup_user.tenant_id = "mega_tenant"

    db_session.flush()

    # CaseFile
    case = CaseFile(
        title="Expediente P13 E2E",
        contract_type="BIENES",
        status="APPROVED",
        tenant_id="mega_tenant",
        assigned_to_user_id=op_user.id,
        traceability_regime="P12_STRICT"
    )
    db_session.add(case)
    db_session.flush()

    # CaseWorkflow
    wf = CaseWorkflow(case_id=case.id, status="APPROVED", supervisor_id=sup_user.id)
    db_session.add(wf)

    # Supplier & Profile
    supplier = db_session.query(Supplier).filter_by(id=201).first()
    if not supplier:
        supplier = Supplier(
            id=201,
            tenant_id="mega_tenant",
            ruc="20800100209",
            business_name="Soluciones Técnicas SAC"
        )
        db_session.add(supplier)
        db_session.flush()
    else:
        supplier.ruc = "20800100209"
        db_session.flush()

    profile = db_session.query(SupplierProfile).filter_by(supplier_id=201).first()
    if not profile:
        profile = SupplierProfile(supplier_id=201, validation_status="VERIFIED")
        db_session.add(profile)
        db_session.flush()
    else:
        profile.validation_status = "VERIFIED"

    # SupplierOffer
    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=201,
        status="SELECTED",
        currency="PEN",
        price=28000.0,
        total_amount=28000.0
    )
    db_session.add(offer)
    db_session.flush()

    # Selection Chain
    attempt = SupplierSelectionAttempt(
        case_id=case.id,
        supplier_offer_id=offer.id,
        selected_by=op_user.id,
        status="UNDER_REVIEW"
    )
    db_session.add(attempt)
    db_session.flush()

    final_sel = SupplierSelectionFinal(case_id=case.id, attempt_id=attempt.id)
    db_session.add(final_sel)

    # Document (Real physical file on disk for R3-04)
    tmp_doc = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_doc.write(b"%PDF-1.4\n%Authentic Technical Specifications\n%%EOF\n")
    tmp_doc.flush()
    tmp_doc.close()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="especificaciones_tecnicas.pdf",
        stored_path=tmp_doc.name,
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.flush()

    # Mandatory requirement
    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima 12 meses",
        mandatory=True
    )
    db_session.add(req)
    db_session.flush()

    # Evaluation
    ev = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        status="PASSED",
        validated_by=op_user.id
    )
    db_session.add(ev)

    # Evidence
    offer_ev = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="Ficha Tecnica",
        fragment="Garantía de fábrica 12 meses incluida",
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
        page=1,
        fragment="Garantía de fábrica 12 meses incluida",
        verified_by=op_user.id,
        verification_status="VERIFIED"
    )
    db_session.add(ore)

    # Template P13
    template = db_session.query(OutputTemplate).filter_by(
        type="INFORME_TECNICO_EVALUACION", version="1.0"
    ).first()
    if not template:
        template = OutputTemplate(
            type="INFORME_TECNICO_EVALUACION",
            version="1.0",
            entity_name="Abast-gp",
            content="<div><h1>INFORME</h1><p>{{ selected_supplier_name }}</p><p>{{ total_amount }}</p></div>",
            status="ACTIVE"
        )
        db_session.add(template)

    db_session.commit()

    yield {
        "case": case,
        "operator": op_user,
        "supervisor": sup_user,
        "offer": offer
    }

    if os.path.exists(tmp_doc.name):
        try:
            os.remove(tmp_doc.name)
        except OSError:
            pass



def set_user_role(app_instance, user: User):
    def override():
        return user
    app_instance.dependency_overrides[get_current_user] = override
    app_instance.dependency_overrides[get_current_active_user] = override


def test_generate_p13_report_success(client: TestClient, p13_case_fixture):
    case = p13_case_fixture["case"]
    operator = p13_case_fixture["operator"]
    set_user_role(app, operator)

    res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/generate",
        json={"template_version": "1.0", "idempotency_key": "idemp-001"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == case.id
    assert data["version_number"] == 1
    assert data["status"] == "GENERATED"
    assert data["accuracy_gate_result"] == "ACCURACY_VERIFIED"
    assert data["snapshot_hash"] is not None
    assert data["html_hash"] is not None
    assert data["pdf_hash"] is None


def test_list_and_get_detail_p13_report(client: TestClient, p13_case_fixture):
    case = p13_case_fixture["case"]
    operator = p13_case_fixture["operator"]
    set_user_role(app, operator)

    # Generate report
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    assert gen_res.status_code == 200
    report_id = gen_res.json()["id"]

    # List reports
    list_res = client.get(f"/api/v6/cases/{case.id}/reports/p13")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(r["id"] == report_id for r in list_data["reports"])

    # Detail
    detail_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == report_id


def test_submit_review_and_idempotency(client: TestClient, p13_case_fixture):
    case = p13_case_fixture["case"]
    operator = p13_case_fixture["operator"]
    set_user_role(app, operator)

    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]

    # Submit to review
    sub_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review",
        json={"notes": "Listo para evaluación por supervisor"}
    )
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "UNDER_REVIEW"

    # Repeated submit is idempotent (200)
    sub2_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review",
        json={"notes": "Re-submit idempotente"}
    )
    assert sub2_res.status_code == 200
    assert sub2_res.json()["status"] == "UNDER_REVIEW"


def test_cannot_approve_or_reject_directly_from_generated(client: TestClient, p13_case_fixture):
    case = p13_case_fixture["case"]
    operator = p13_case_fixture["operator"]
    supervisor = p13_case_fixture["supervisor"]

    set_user_role(app, operator)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]

    set_user_role(app, supervisor)
    # Direct approve from GENERATED must fail (409)
    appr_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve",
        json={"approval_notes": "Aprobación directa indebida"}
    )
    assert appr_res.status_code == 409
    assert "UNDER_REVIEW" in appr_res.json()["detail"]

    # Direct reject from GENERATED must fail (409)
    rej_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/reject",
        json={"rejection_reason": "Rechazo directo indebido"}
    )
    assert rej_res.status_code == 409


def test_approve_report_success_and_pdf_generation(client: TestClient, p13_case_fixture):
    case = p13_case_fixture["case"]
    operator = p13_case_fixture["operator"]
    supervisor = p13_case_fixture["supervisor"]

    # 1. Operator generates
    set_user_role(app, operator)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]

    # 2. Operator submits to review
    sub_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})
    assert sub_res.status_code == 200

    # 3. Independent supervisor approves (SoD respected)
    set_user_role(app, supervisor)
    appr_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve",
        json={"approval_notes": "Aprobado sin observaciones"}
    )
    assert appr_res.status_code == 200
    appr_data = appr_res.json()
    assert appr_data["status"] == "APPROVED"
    assert appr_data["approved_by"] == supervisor.id
    assert appr_data["approved_at"] is not None
    assert appr_data["pdf_hash"] is not None
    assert appr_data["html_hash"] is not None


def test_reject_report_with_motivation_and_subsanacion(client: TestClient, p13_case_fixture):
    case = p13_case_fixture["case"]
    operator = p13_case_fixture["operator"]
    supervisor = p13_case_fixture["supervisor"]

    # Operator generates v1
    set_user_role(app, operator)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]

    # Operator submits to review
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    # Supervisor rejects
    set_user_role(app, supervisor)
    rej_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/reject",
        json={"rejection_reason": "Se requiere mayor detalle en las consideraciones técnicas"}
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"

    # v1 is terminal (cannot approve after rejection)
    appr_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve",
        json={"approval_notes": "Tratar de aprobar rechazado"}
    )
    assert appr_res.status_code == 409

    # Subsanación: Operator generates v2
    set_user_role(app, operator)
    gen2_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    assert gen2_res.status_code == 200
    v2_data = gen2_res.json()
    assert v2_data["version_number"] == 2
    assert v2_data["status"] == "GENERATED"


def test_reject_report_requires_valid_reason(client: TestClient, p13_case_fixture):
    case = p13_case_fixture["case"]
    operator = p13_case_fixture["operator"]
    supervisor = p13_case_fixture["supervisor"]

    set_user_role(app, operator)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})

    set_user_role(app, supervisor)
    # Reason < 5 characters returns 422
    rej_res = client.post(
        f"/api/v6/cases/{case.id}/reports/p13/{report_id}/reject",
        json={"rejection_reason": "mal"}
    )
    assert rej_res.status_code == 422


def test_exports_are_pure_reads_and_verify_integrity(client: TestClient, p13_case_fixture):
    case = p13_case_fixture["case"]
    operator = p13_case_fixture["operator"]
    supervisor = p13_case_fixture["supervisor"]

    set_user_role(app, operator)
    gen_res = client.post(f"/api/v6/cases/{case.id}/reports/p13/generate", json={})
    report_id = gen_res.json()["id"]

    # Export before approval must fail (400)
    exp_fail = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/export/pdf")
    assert exp_fail.status_code == 400

    # Advance to approval
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/submit-review", json={})
    set_user_role(app, supervisor)
    client.post(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/approve", json={"approval_notes": "OK"})

    # Export HTML (pure read)
    set_user_role(app, operator)
    html_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/export/html")
    assert html_res.status_code == 200
    assert "text/html" in html_res.headers["content-type"]
    assert "Soluciones Técnicas SAC" in html_res.text

    # Status must STILL be APPROVED (not EXPORTED!)
    chk_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}")
    assert chk_res.json()["status"] == "APPROVED"

    # Export PDF (pure read)
    pdf_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/export/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 1000

    # Status must STILL be APPROVED
    chk_res2 = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}")
    assert chk_res2.json()["status"] == "APPROVED"

    # Verify integrity endpoint
    int_res = client.get(f"/api/v6/cases/{case.id}/reports/p13/{report_id}/verify-integrity")
    assert int_res.status_code == 200
    int_data = int_res.json()
    assert int_data["snapshot_intact"] is True
    assert int_data["html_intact"] is True
    assert int_data["pdf_file_exists"] is True
    assert int_data["pdf_intact"] is True
    assert int_data["is_authentic"] is True
