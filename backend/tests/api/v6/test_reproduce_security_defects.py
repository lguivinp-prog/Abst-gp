import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import Tenant, User, CaseFile, ParsedSection, UploadedDocument
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.output_template import OutputTemplate
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.generated_output import GeneratedOutput

@pytest.fixture
def reproduction_setup(db_session: Session):
    # Tenant A setup
    tenant_a = db_session.query(Tenant).filter_by(id="tenant_a").first()
    if not tenant_a:
        tenant_a = Tenant(id="tenant_a", name="Tenant A")
        db_session.add(tenant_a)

    # Tenant B setup
    tenant_b = db_session.query(Tenant).filter_by(id="tenant_b").first()
    if not tenant_b:
        tenant_b = Tenant(id="tenant_b", name="Tenant B")
        db_session.add(tenant_b)

    # User A Admin
    user_a_admin = User(id=101, username="admin_a", password_hash="mock", role="ADMIN", is_active=True, must_change_password=False, tenant_id="tenant_a", tenant_resolution_status="RESOLVED")
    # User A Operator Assigned
    user_a_op = User(id=102, username="op_a", password_hash="mock", role="OPERATOR", is_active=True, must_change_password=False, tenant_id="tenant_a", tenant_resolution_status="RESOLVED")
    # User A Operator Unassigned
    user_a_unassigned = User(id=103, username="unassigned_a", password_hash="mock", role="OPERATOR", is_active=True, must_change_password=False, tenant_id="tenant_a", tenant_resolution_status="RESOLVED")
    # User B Admin
    user_b_admin = User(id=201, username="admin_b", password_hash="mock", role="ADMIN", is_active=True, must_change_password=False, tenant_id="tenant_b", tenant_resolution_status="RESOLVED")

    db_session.add_all([user_a_admin, user_a_op, user_a_unassigned, user_b_admin])
    db_session.commit()

    # Case in Tenant A assigned to user_a_op
    case_a = CaseFile(
        id=9001,
        title="Expediente A",
        contract_type="BIENES",
        status="WAITING_QUOTATION",
        tenant_id="tenant_a",
        created_by=101,
        assigned_to_user_id=102
    )

    # Case in Tenant B
    case_b = CaseFile(
        id=9002,
        title="Expediente B",
        contract_type="SERVICIOS",
        status="WAITING_QUOTATION",
        tenant_id="tenant_b",
        created_by=201,
        assigned_to_user_id=201
    )

    db_session.add_all([case_a, case_b])
    db_session.commit()

    # Document for Case A
    doc_a = UploadedDocument(
        id=9201,
        case_id=9001,
        document_type="requirement",
        original_filename="req.pdf",
        stored_path="/data/uploads/req.pdf",
        mime_type="application/pdf",
        processing_status="finished"
    )
    db_session.add(doc_a)
    db_session.commit()

    # Section for Case A
    sec_a = ParsedSection(
        id=9101,
        case_id=9001,
        document_id=9201,
        title="Sección 1",
        original_text="Texto original",
        current_text="Texto original",
        is_selected=True,
        review_status="pending_review",
        original_order=1
    )

    # Template for outputs (query existing or create)
    tmpl = db_session.query(OutputTemplate).filter_by(type="CONDICIONES").first()
    if not tmpl:
        tmpl = OutputTemplate(
            type="CONDICIONES",
            version="1.0",
            entity_name="Abast-gp",
            content="Test content",
            status="ACTIVE"
        )
        db_session.add(tmpl)

    db_session.add(sec_a)
    db_session.commit()

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "user_a_admin": user_a_admin,
        "user_a_op": user_a_op,
        "user_a_unassigned": user_a_unassigned,
        "user_b_admin": user_b_admin,
        "case_a": case_a,
        "case_b": case_b,
        "sec_a": sec_a,
        "doc_a": doc_a,
        "tmpl": tmpl,
    }

def get_client_for_user(user: User):
    from app.main import app
    from app.api.auth import get_current_active_user, get_current_user

    def override():
        return user

    app.dependency_overrides[get_current_active_user] = override
    app.dependency_overrides[get_current_user] = override
    return TestClient(app)

def test_regression_section_idor_cross_tenant_blocked(reproduction_setup, db_session):
    """
    REGRESIÓN DE SEGURIDAD 1:
    Un ADMIN de Tenant B NO puede modificar una sección de Tenant A vía PUT /cases/sections/{section_id}.
    Debe retornar 404 NotFoundException para evitar enumeración IDOR,
    y el registro en base de datos debe permanecer inmutable.
    """
    user_b_admin = reproduction_setup["user_b_admin"]
    sec_a = reproduction_setup["sec_a"]

    # Estado previo en BD
    initial_text = sec_a.current_text
    initial_selected = sec_a.is_selected
    initial_status = sec_a.review_status

    client_b = get_client_for_user(user_b_admin)
    try:
        payload = {
            "is_selected": not initial_selected,
            "review_status": "validated",
            "current_text": "Texto malicioso inyectado por Tenant B"
        }
        res = client_b.put(f"/cases/sections/{sec_a.id}", json=payload)
        assert res.status_code == 404, f"Fallo de seguridad: esperado 404, obtenido {res.status_code}"

        # Verificación estricta de integridad de datos en DB
        db_session.expire_all()
        sec_after = db_session.query(ParsedSection).filter_by(id=sec_a.id).first()
        assert sec_after.current_text == initial_text, "Integridad violada: texto de sección fue alterado"
        assert sec_after.is_selected == initial_selected, "Integridad violada: is_selected fue alterado"
        assert sec_after.review_status == initial_status, "Integridad violada: review_status fue alterado"
    finally:
        from app.main import app
        from app.api.auth import get_current_active_user, get_current_user
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)

def test_regression_outputs_cross_tenant_blocked(reproduction_setup, db_session):
    """
    REGRESIÓN DE SEGURIDAD 2:
    Endpoints /api/v6/cases/{case_id}/outputs, /outputs/{id}/approve y /outputs/{id}/export
    deben rechazar con 404 cualquier acceso desde Tenant B sobre recursos de Tenant A.
    Verificar integridad: el estado del documento permanece GENERATED.
    """
    case_a = reproduction_setup["case_a"]
    user_b_admin = reproduction_setup["user_b_admin"]
    tmpl = reproduction_setup["tmpl"]

    out_a = GeneratedOutput(
        case_id=case_a.id,
        template_id=tmpl.id,
        template_version=tmpl.version,
        accuracy_gate_result="PASSED",
        source_snapshot={"supplier_name": "Tech Corp"},
        content_rendered="<p>Secreto Tenant A</p>",
        generation_hash="abc",
        status="GENERATED",
        version_number=1
    )
    db_session.add(out_a)
    db_session.commit()

    client_b = get_client_for_user(user_b_admin)
    try:
        # 1. List outputs cross-tenant debe retornar 404
        list_res = client_b.get(f"/api/v6/cases/{case_a.id}/outputs")
        assert list_res.status_code == 404, f"Fallo de seguridad: list_outputs retorno {list_res.status_code} en vez de 404"

        # 2. Approve output cross-tenant debe retornar 404
        app_res = client_b.post(f"/api/v6/outputs/{out_a.id}/approve")
        assert app_res.status_code == 404, f"Fallo de seguridad: approve_output retorno {app_res.status_code} en vez de 404"

        # 3. Export output cross-tenant debe retornar 404
        exp_res = client_b.post(f"/api/v6/outputs/{out_a.id}/export")
        assert exp_res.status_code == 404, f"Fallo de seguridad: export_output retorno {exp_res.status_code} en vez de 404"

        # 4. Verificación estricta de integridad de datos en DB
        db_session.expire_all()
        out_after = db_session.query(GeneratedOutput).filter_by(id=out_a.id).first()
        assert out_after.status == "GENERATED", f"Integridad violada: status del output cambio a {out_after.status}"
    finally:
        from app.main import app
        from app.api.auth import get_current_active_user, get_current_user
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)

def test_regression_create_case_preserves_tenant(reproduction_setup, db_session):
    """
    REGRESIÓN DE SEGURIDAD 3:
    POST /cases/ debe asignar tenant_id del usuario autenticado (tenant_a),
    no dependiendo del server_default 'mega_tenant'.
    """
    user_a_op = reproduction_setup["user_a_op"]
    client_a = get_client_for_user(user_a_op)
    try:
        res = client_a.post("/cases/", json={"title": "Caso de Tenant A", "contract_type": "BIENES"})
        assert res.status_code == 200, f"Error al crear caso: {res.text}"
        created_id = res.json()["id"]

        db_session.expire_all()
        case = db_session.query(CaseFile).filter_by(id=created_id).first()
        assert case is not None
        assert case.tenant_id == "tenant_a", f"Fallo de seguridad: tenant_id es '{case.tenant_id}', esperado 'tenant_a'"
        assert case.created_by == user_a_op.id
        assert case.assigned_to_user_id == user_a_op.id
    finally:
        from app.main import app
        from app.api.auth import get_current_active_user, get_current_user
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)
