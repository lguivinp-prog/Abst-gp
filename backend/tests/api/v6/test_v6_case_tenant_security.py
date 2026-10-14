import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import Tenant, User, CaseFile, ParsedSection, UploadedDocument, QuotationExtraction, ProcessingJob
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.output_template import OutputTemplate
from app.models.v6.supplier_selection import SupplierSelectionFinal, SupplierSelectionAttempt
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.generated_output import GeneratedOutput

@pytest.fixture
def multi_tenant_fixture(db_session: Session):
    # Setup Tenants
    t_a = db_session.query(Tenant).filter_by(id="tenant_a").first()
    if not t_a:
        t_a = Tenant(id="tenant_a", name="Tenant A")
        db_session.add(t_a)

    t_b = db_session.query(Tenant).filter_by(id="tenant_b").first()
    if not t_b:
        t_b = Tenant(id="tenant_b", name="Tenant B")
        db_session.add(t_b)

    # Setup Users for Tenant A
    admin_a = User(id=301, username="admin_a", password_hash="mock", role="ADMIN", is_active=True, must_change_password=False, tenant_id="tenant_a", tenant_resolution_status="RESOLVED")
    op_a_assigned = User(id=302, username="op_a_assigned", password_hash="mock", role="OPERATOR", is_active=True, must_change_password=False, tenant_id="tenant_a", tenant_resolution_status="RESOLVED")
    op_a_unassigned = User(id=303, username="op_a_unassigned", password_hash="mock", role="OPERATOR", is_active=True, must_change_password=False, tenant_id="tenant_a", tenant_resolution_status="RESOLVED")
    ro_a = User(id=304, username="ro_a", password_hash="mock", role="READONLY", is_active=True, must_change_password=False, tenant_id="tenant_a", tenant_resolution_status="RESOLVED")

    # Setup Users for Tenant B
    admin_b = User(id=401, username="admin_b", password_hash="mock", role="ADMIN", is_active=True, must_change_password=False, tenant_id="tenant_b", tenant_resolution_status="RESOLVED")
    op_b = User(id=402, username="op_b", password_hash="mock", role="OPERATOR", is_active=True, must_change_password=False, tenant_id="tenant_b", tenant_resolution_status="RESOLVED")

    db_session.add_all([admin_a, op_a_assigned, op_a_unassigned, ro_a, admin_b, op_b])
    db_session.commit()

    # Active Case in Tenant A (assigned to op_a_assigned)
    case_a_active = CaseFile(
        id=7001,
        title="Expediente Activo Tenant A",
        contract_type="BIENES",
        status="REVIEW_SECTIONS",
        tenant_id="tenant_a",
        created_by=301,
        assigned_to_user_id=302
    )

    # Approved Case in Tenant A
    case_a_approved = CaseFile(
        id=7002,
        title="Expediente Aprobado Tenant A",
        contract_type="BIENES",
        status="APPROVED",
        tenant_id="tenant_a",
        created_by=301,
        assigned_to_user_id=302
    )

    # Completed Case in Tenant A
    case_a_completed = CaseFile(
        id=7003,
        title="Expediente Completado Tenant A",
        contract_type="BIENES",
        status="COMPLETED",
        tenant_id="tenant_a",
        created_by=301,
        assigned_to_user_id=302
    )

    # Case in Tenant B
    case_b = CaseFile(
        id=8001,
        title="Expediente Tenant B",
        contract_type="SERVICIOS",
        status="REVIEW_SECTIONS",
        tenant_id="tenant_b",
        created_by=401,
        assigned_to_user_id=402
    )

    # Case in Tenant A assigned to ro_a (for testing assigned READONLY permissions)
    case_a_ro_assigned = CaseFile(
        id=7004,
        title="Expediente Asignado a Readonly",
        contract_type="BIENES",
        status="REVIEW_SECTIONS",
        tenant_id="tenant_a",
        created_by=301,
        assigned_to_user_id=304
    )

    db_session.add_all([case_a_active, case_a_approved, case_a_completed, case_a_ro_assigned, case_b])
    db_session.commit()

    # Document & Section for Active Case A
    doc_a = UploadedDocument(
        id=7201,
        case_id=case_a_active.id,
        document_type="requirement",
        original_filename="req_a.pdf",
        stored_path="/data/uploads/req_a.pdf",
        mime_type="application/pdf",
        processing_status="finished"
    )
    db_session.add(doc_a)
    db_session.commit()

    sec_a_active = ParsedSection(
        id=7101,
        case_id=case_a_active.id,
        document_id=doc_a.id,
        title="Sección Activa 1",
        original_text="Texto Inicial Activo",
        current_text="Texto Inicial Activo",
        is_selected=True,
        review_status="pending_review",
        original_order=1
    )

    # Document & Section for Approved Case A
    doc_a_appr = UploadedDocument(
        id=7202,
        case_id=case_a_approved.id,
        document_type="requirement",
        original_filename="req_appr.pdf",
        stored_path="/data/uploads/req_appr.pdf",
        mime_type="application/pdf",
        processing_status="finished"
    )
    db_session.add(doc_a_appr)
    db_session.commit()

    sec_a_approved = ParsedSection(
        id=7102,
        case_id=case_a_approved.id,
        document_id=doc_a_appr.id,
        title="Sección Aprobada",
        original_text="Texto Aprobado Inmutable",
        current_text="Texto Aprobado Inmutable",
        is_selected=True,
        review_status="validated",
        original_order=1
    )

    # Document & Section for RO Assigned Case
    doc_a_ro = UploadedDocument(
        id=7203,
        case_id=case_a_ro_assigned.id,
        document_type="requirement",
        original_filename="req_ro.pdf",
        stored_path="/data/uploads/req_ro.pdf",
        mime_type="application/pdf",
        processing_status="finished"
    )
    db_session.add(doc_a_ro)
    db_session.commit()

    sec_a_ro = ParsedSection(
        id=7103,
        case_id=case_a_ro_assigned.id,
        document_id=doc_a_ro.id,
        title="Sección Readonly Asignada",
        original_text="Texto Readonly Original",
        current_text="Texto Readonly Original",
        is_selected=True,
        review_status="pending_review",
        original_order=1
    )

    # Template
    tmpl = db_session.query(OutputTemplate).filter_by(type="CONDICIONES").first()
    if not tmpl:
        tmpl = OutputTemplate(
            type="CONDICIONES",
            version="1.0",
            entity_name="Abast-gp",
            content="Template Content",
            status="ACTIVE"
        )
        db_session.add(tmpl)

    db_session.add_all([sec_a_active, sec_a_approved, sec_a_ro])
    db_session.commit()

    # Output for Approved Case A
    output_a = GeneratedOutput(
        id=7501,
        case_id=case_a_approved.id,
        template_id=tmpl.id,
        template_version=tmpl.version,
        accuracy_gate_result="PASSED",
        source_snapshot={"supplier_name": "Supplier A"},
        content_rendered="<p>Documento Aprobado</p>",
        generation_hash="hash_7501",
        status="GENERATED",
        version_number=1
    )
    # Output for RO Assigned Case
    output_a_ro = GeneratedOutput(
        id=7502,
        case_id=case_a_ro_assigned.id,
        template_id=tmpl.id,
        template_version=tmpl.version,
        accuracy_gate_result="PASSED",
        source_snapshot={"supplier_name": "Supplier RO"},
        content_rendered="<p>Documento Readonly</p>",
        generation_hash="hash_7502",
        status="GENERATED",
        version_number=1
    )
    db_session.add_all([output_a, output_a_ro])
    db_session.commit()

    return {
        "admin_a": admin_a,
        "op_a_assigned": op_a_assigned,
        "op_a_unassigned": op_a_unassigned,
        "ro_a": ro_a,
        "admin_b": admin_b,
        "op_b": op_b,
        "case_a_active": case_a_active,
        "case_a_approved": case_a_approved,
        "case_a_completed": case_a_completed,
        "case_a_ro_assigned": case_a_ro_assigned,
        "case_b": case_b,
        "sec_a_active": sec_a_active,
        "sec_a_approved": sec_a_approved,
        "sec_a_ro": sec_a_ro,
        "output_a": output_a,
        "output_a_ro": output_a_ro,
        "tmpl": tmpl
    }

def set_user(user: User):
    from app.main import app
    from app.api.auth import get_current_active_user, get_current_user
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user

def clear_overrides():
    from app.main import app
    from app.api.auth import get_current_active_user, get_current_user
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)


# =========================================================================
# 1. AISLAMIENTO ENTRE TENANT A Y TENANT B
# =========================================================================

def test_tenant_isolation_get_cases(multi_tenant_fixture, db_session):
    """GET /cases/ solo debe retornar expedientes del tenant del usuario."""
    from app.main import app
    set_user(multi_tenant_fixture["admin_b"])
    client = TestClient(app)
    try:
        res = client.get("/cases/")
        assert res.status_code == 200
        cases = res.json()
        case_ids = [c["id"] for c in cases]
        assert multi_tenant_fixture["case_b"].id in case_ids
        assert multi_tenant_fixture["case_a_active"].id not in case_ids
        assert multi_tenant_fixture["case_a_approved"].id not in case_ids
        assert multi_tenant_fixture["case_a_completed"].id not in case_ids
    finally:
        clear_overrides()

def test_tenant_isolation_endpoints_return_404(multi_tenant_fixture, db_session):
    """Usuario de Tenant B consultando recursos de Tenant A debe recibir 404 (IDOR guard)."""
    from app.main import app
    set_user(multi_tenant_fixture["admin_b"])
    client = TestClient(app)
    case_a_id = multi_tenant_fixture["case_a_active"].id
    sec_a_id = multi_tenant_fixture["sec_a_active"].id
    out_a_id = multi_tenant_fixture["output_a"].id

    try:
        # GET case
        assert client.get(f"/cases/{case_a_id}").status_code == 404
        # GET sections
        assert client.get(f"/cases/{case_a_id}/sections").status_code == 404
        # PUT section direct ID
        payload = {"is_selected": False, "review_status": "validated", "current_text": "X"}
        assert client.put(f"/cases/sections/{sec_a_id}", json=payload).status_code == 404
        # POST confirm sections
        assert client.post(f"/cases/{case_a_id}/sections/confirm").status_code == 404
        # GET outputs
        assert client.get(f"/api/v6/cases/{case_a_id}/outputs").status_code == 404
        # POST approve output direct ID
        assert client.post(f"/api/v6/outputs/{out_a_id}/approve").status_code == 404
        # POST export output direct ID
        assert client.post(f"/api/v6/outputs/{out_a_id}/export").status_code == 404
    finally:
        clear_overrides()


# =========================================================================
# 2. PERMISOS ADMIN, OPERATOR, READONLY Y NO AUTENTICADO
# =========================================================================

def test_unauthenticated_requests_fail(multi_tenant_fixture):
    """Solicitudes sin credenciales deben fallar con 401."""
    from app.main import app
    clear_overrides()
    anon_client = TestClient(app)

    case_a_id = multi_tenant_fixture["case_a_active"].id
    sec_a_id = multi_tenant_fixture["sec_a_active"].id
    out_a_id = multi_tenant_fixture["output_a"].id

    assert anon_client.get("/cases/").status_code == 401
    assert anon_client.get(f"/cases/{case_a_id}").status_code == 401
    assert anon_client.put(f"/cases/sections/{sec_a_id}", json={"is_selected": True}).status_code == 401
    assert anon_client.get(f"/api/v6/cases/{case_a_id}/outputs").status_code == 401
    assert anon_client.post(f"/api/v6/outputs/{out_a_id}/approve").status_code == 401

def test_readonly_user_assigned_cannot_mutate(multi_tenant_fixture, db_session):
    """Usuario READONLY asignado a su caso puede leerlo pero tiene bloqueadas todas las mutaciones con 403."""
    from app.main import app
    set_user(multi_tenant_fixture["ro_a"])
    client = TestClient(app)
    case_ro_id = multi_tenant_fixture["case_a_ro_assigned"].id
    sec_ro_id = multi_tenant_fixture["sec_a_ro"].id
    out_ro_id = multi_tenant_fixture["output_a_ro"].id

    # 1. Snapshot previo de base de datos
    db_session.expire_all()
    orig_sec = db_session.query(ParsedSection).filter_by(id=sec_ro_id).first()
    orig_case = db_session.query(CaseFile).filter_by(id=case_ro_id).first()
    orig_sec_text = orig_sec.current_text
    orig_sec_status = orig_sec.review_status
    orig_case_assigned = orig_case.assigned_to_user_id
    orig_case_status = orig_case.status
    orig_output_count = db_session.query(GeneratedOutput).filter_by(case_id=case_ro_id).count()

    try:
        # A. Lecturas autorizadas para READONLY asignado -> 200 OK
        assert client.get(f"/cases/{case_ro_id}").status_code == 200
        assert client.get(f"/cases/{case_ro_id}/sections").status_code == 200
        assert client.get(f"/api/v6/cases/{case_ro_id}/outputs").status_code == 200

        # B. Mutaciones bloqueadas estrictamente con 403 Forbidden
        # Edición de sección
        update_sec_payload = {"is_selected": True, "review_status": "validated", "current_text": "Illegal RO Edit"}
        assert client.put(f"/cases/sections/{sec_ro_id}", json=update_sec_payload).status_code == 403

        # Confirmación de secciones
        assert client.post(f"/cases/{case_ro_id}/sections/confirm").status_code == 403

        # Reasignación de expediente
        assign_payload = {"assigned_to_user_id": multi_tenant_fixture["op_a_assigned"].id}
        assert client.post(f"/cases/{case_ro_id}/assign", json=assign_payload).status_code == 403

        # Generación de HTML
        assert client.post(f"/cases/{case_ro_id}/generate/html").status_code == 403

        # Preparación de salida
        assert client.post(f"/api/v6/cases/{case_ro_id}/prepare-output").status_code == 403

        # Aprobación de salida
        assert client.post(f"/api/v6/outputs/{out_ro_id}/approve").status_code == 403

        # Exportación de salida
        assert client.post(f"/api/v6/outputs/{out_ro_id}/export").status_code == 403

        # 2. Snapshot posterior: verificar inmutabilidad absoluta de base de datos
        db_session.expire_all()
        post_sec = db_session.query(ParsedSection).filter_by(id=sec_ro_id).first()
        post_case = db_session.query(CaseFile).filter_by(id=case_ro_id).first()
        post_output_count = db_session.query(GeneratedOutput).filter_by(case_id=case_ro_id).count()

        assert post_sec.current_text == orig_sec_text
        assert post_sec.review_status == orig_sec_status
        assert post_case.assigned_to_user_id == orig_case_assigned
        assert post_case.status == orig_case_status
        assert post_output_count == orig_output_count
    finally:
        clear_overrides()

def test_readonly_user_unassigned_denied(multi_tenant_fixture, db_session):
    """Usuario READONLY no asignado al caso recibe 404 (IDOR guard) en lectura y mutación."""
    from app.main import app
    set_user(multi_tenant_fixture["ro_a"])
    client = TestClient(app)
    case_a_id = multi_tenant_fixture["case_a_active"].id
    sec_a_id = multi_tenant_fixture["sec_a_active"].id

    # 1. Snapshot previo de base de datos
    db_session.expire_all()
    orig_sec = db_session.query(ParsedSection).filter_by(id=sec_a_id).first()
    orig_case = db_session.query(CaseFile).filter_by(id=case_a_id).first()
    orig_sec_text = orig_sec.current_text
    orig_sec_status = orig_sec.review_status
    orig_case_assigned = orig_case.assigned_to_user_id
    orig_case_status = orig_case.status

    try:
        # A. Lecturas no autorizadas -> 404 Not Found
        assert client.get(f"/cases/{case_a_id}").status_code == 404
        assert client.get(f"/cases/{case_a_id}/sections").status_code == 404
        assert client.get(f"/api/v6/cases/{case_a_id}/outputs").status_code == 404

        # B. Mutaciones sobre caso no asignado
        update_sec_payload = {"is_selected": True, "review_status": "validated", "current_text": "Illegal Unassigned RO Edit"}
        assert client.put(f"/cases/sections/{sec_a_id}", json=update_sec_payload).status_code == 403

        assert client.post(f"/cases/{case_a_id}/sections/confirm").status_code == 404

        assign_payload = {"assigned_to_user_id": multi_tenant_fixture["ro_a"].id}
        assert client.post(f"/cases/{case_a_id}/assign", json=assign_payload).status_code == 404

        assert client.post(f"/cases/{case_a_id}/generate/html").status_code == 404

        assert client.post(f"/api/v6/cases/{case_a_id}/prepare-output").status_code == 404

        # 2. Snapshot posterior: verificar inmutabilidad absoluta de base de datos
        db_session.expire_all()
        post_sec = db_session.query(ParsedSection).filter_by(id=sec_a_id).first()
        post_case = db_session.query(CaseFile).filter_by(id=case_a_id).first()

        assert post_sec.current_text == orig_sec_text
        assert post_sec.review_status == orig_sec_status
        assert post_case.assigned_to_user_id == orig_case_assigned
        assert post_case.status == orig_case_status
    finally:
        clear_overrides()

def test_operator_cannot_assign_or_approve_output(multi_tenant_fixture):
    """Operador no puede asignar casos ni aprobar outputs (requiere ADMIN / SUPERVISOR)."""
    from app.main import app
    set_user(multi_tenant_fixture["op_a_assigned"])
    client = TestClient(app)
    case_a_id = multi_tenant_fixture["case_a_active"].id
    out_a_id = multi_tenant_fixture["output_a"].id

    try:
        # Assign case requires ADMIN -> 403
        assign_payload = {"assigned_to_user_id": multi_tenant_fixture["op_a_assigned"].id}
        assert client.post(f"/cases/{case_a_id}/assign", json=assign_payload).status_code == 403

        # Approve output requires ADMIN/SUPERVISOR -> 403
        assert client.post(f"/api/v6/outputs/{out_a_id}/approve").status_code == 403
    finally:
        clear_overrides()


# =========================================================================
# 3. ACCESO A EXPEDIENTES ASIGNADOS Y NO ASIGNADOS
# =========================================================================

def test_unassigned_operator_denied(multi_tenant_fixture):
    """Operador no asignado dentro del mismo tenant debe recibir 404 en operaciones del caso."""
    from app.main import app
    set_user(multi_tenant_fixture["op_a_unassigned"])
    client = TestClient(app)
    case_a_id = multi_tenant_fixture["case_a_active"].id
    sec_a_id = multi_tenant_fixture["sec_a_active"].id

    try:
        # GET case -> 404
        assert client.get(f"/cases/{case_a_id}").status_code == 404

        # PUT section -> 404
        payload = {"is_selected": False, "review_status": "validated", "current_text": "Hacked"}
        assert client.put(f"/cases/sections/{sec_a_id}", json=payload).status_code == 404

        # GET outputs -> 404
        assert client.get(f"/api/v6/cases/{case_a_id}/outputs").status_code == 404
    finally:
        clear_overrides()

def test_assigned_operator_allowed(multi_tenant_fixture, db_session):
    """Operador asignado dentro del mismo tenant tiene acceso a su caso."""
    from app.main import app
    set_user(multi_tenant_fixture["op_a_assigned"])
    client = TestClient(app)
    case_a_id = multi_tenant_fixture["case_a_active"].id
    sec_a_id = multi_tenant_fixture["sec_a_active"].id

    try:
        # GET case -> 200
        res = client.get(f"/cases/{case_a_id}")
        assert res.status_code == 200

        # PUT section -> 200
        payload = {"is_selected": True, "review_status": "validated", "current_text": "Texto Valido"}
        res_sec = client.put(f"/cases/sections/{sec_a_id}", json=payload)
        assert res_sec.status_code == 200
        assert res_sec.json()["current_text"] == "Texto Valido"
    finally:
        clear_overrides()


# =========================================================================
# 4. MODIFICACIONES SOBRE EXPEDIENTES APPROVED Y COMPLETED (INMUTABILIDAD)
# =========================================================================

def test_terminal_states_block_mutations_in_cases_py(multi_tenant_fixture, db_session):
    """Rutas heredadas de mutacion en cases.py deben retornar 409 Conflict en casos APPROVED o COMPLETED."""
    from app.main import app
    set_user(multi_tenant_fixture["admin_a"])
    client = TestClient(app)
    case_appr_id = multi_tenant_fixture["case_a_approved"].id
    case_comp_id = multi_tenant_fixture["case_a_completed"].id
    sec_appr_id = multi_tenant_fixture["sec_a_approved"].id

    try:
        # 1. assign_case en APPROVED -> 409
        assign_payload = {"assigned_to_user_id": multi_tenant_fixture["op_a_assigned"].id}
        assert client.post(f"/cases/{case_appr_id}/assign", json=assign_payload).status_code == 409

        # 2. assign_case en COMPLETED -> 409
        assert client.post(f"/cases/{case_comp_id}/assign", json=assign_payload).status_code == 409

        # 3. update_section en APPROVED -> 409
        update_sec = {"is_selected": True, "review_status": "validated", "current_text": "Illegal Edit"}
        assert client.put(f"/cases/sections/{sec_appr_id}", json=update_sec).status_code == 409

        # 4. confirm_sections en APPROVED -> 409
        assert client.post(f"/cases/{case_appr_id}/sections/confirm").status_code == 409

        # 5. run_comparison en APPROVED -> 409
        assert client.post(f"/cases/{case_appr_id}/comparison/run").status_code == 409
    finally:
        clear_overrides()


# =========================================================================
# 5. CREACIÓN DE EXPEDIENTES CON TENANT CORRECTO
# =========================================================================

def test_create_case_tenant_assignment(multi_tenant_fixture, db_session):
    """create_case debe heredar el tenant_id del usuario autenticado."""
    from app.main import app
    # Tenant A
    set_user(multi_tenant_fixture["op_a_assigned"])
    client_a = TestClient(app)
    try:
        res_a = client_a.post("/cases/", json={"title": "Caso Nuevo Tenant A", "contract_type": "BIENES"})
        assert res_a.status_code == 200
        id_a = res_a.json()["id"]

        db_session.expire_all()
        created_case_a = db_session.query(CaseFile).filter_by(id=id_a).first()
        assert created_case_a.tenant_id == "tenant_a"
    finally:
        clear_overrides()

    # Tenant B
    set_user(multi_tenant_fixture["op_b"])
    client_b = TestClient(app)
    try:
        res_b = client_b.post("/cases/", json={"title": "Caso Nuevo Tenant B", "contract_type": "SERVICIOS"})
        assert res_b.status_code == 200
        id_b = res_b.json()["id"]

        db_session.expire_all()
        created_case_b = db_session.query(CaseFile).filter_by(id=id_b).first()
        assert created_case_b.tenant_id == "tenant_b"
    finally:
        clear_overrides()


# =========================================================================
# 6. DOCUMENTOS: CONSULTA, APROBACIÓN Y EXPORTACIÓN LEGÍTIMOS
# =========================================================================

def test_legitimate_document_lifecycle(multi_tenant_fixture, db_session):
    """Flujo legítimo: Listar outputs, Aprobar (ADMIN) y Exportar (OPERATOR asignado)."""
    from app.main import app
    case_appr_id = multi_tenant_fixture["case_a_approved"].id
    out_id = multi_tenant_fixture["output_a"].id

    try:
        # 1. List outputs by assigned operator -> 200 con 1 item
        set_user(multi_tenant_fixture["op_a_assigned"])
        client = TestClient(app)
        res_list = client.get(f"/api/v6/cases/{case_appr_id}/outputs")
        assert res_list.status_code == 200
        assert len(res_list.json()) >= 1

        # 2. Export before approve -> 400 Bad Request
        res_early_exp = client.post(f"/api/v6/outputs/{out_id}/export")
        assert res_early_exp.status_code == 400

        # 3. Approve by Admin -> 200
        set_user(multi_tenant_fixture["admin_a"])
        client_admin = TestClient(app)
        res_app = client_admin.post(f"/api/v6/outputs/{out_id}/approve")
        assert res_app.status_code == 200
        assert res_app.json()["status"] == "APPROVED"

        # 4. Export by assigned operator -> 200
        set_user(multi_tenant_fixture["op_a_assigned"])
        client_op = TestClient(app)
        res_exp = client_op.post(f"/api/v6/outputs/{out_id}/export")
        assert res_exp.status_code == 200
        assert res_exp.json()["status"] == "EXPORTED"

        # 5. Verify DB state
        db_session.expire_all()
        out_db = db_session.query(GeneratedOutput).filter_by(id=out_id).first()
        assert out_db.status == "EXPORTED"
    finally:
        clear_overrides()


# =========================================================================
# 7. PERSISTENCIA E INTEGRIDAD DE DATOS ANTE SOLICITUDES RECHAZADAS
# =========================================================================

def test_db_integrity_after_rejected_requests(multi_tenant_fixture, db_session):
    """La base de datos debe permanecer intacta tras rechazos 404, 403 y 409."""
    from app.main import app
    sec = multi_tenant_fixture["sec_a_approved"]
    case = multi_tenant_fixture["case_a_approved"]

    orig_sec_text = sec.current_text
    orig_sec_status = sec.review_status
    orig_case_status = case.status
    orig_case_assigned = case.assigned_to_user_id

    try:
        # Solicitud 1: Cross-tenant IDOR rechazada con 404
        set_user(multi_tenant_fixture["admin_b"])
        client_b = TestClient(app)
        client_b.put(f"/cases/sections/{sec.id}", json={"current_text": "Corrupted by B"})

        # Solicitud 2: Mutación en terminal rechazada con 409
        set_user(multi_tenant_fixture["admin_a"])
        client_a_admin = TestClient(app)
        client_a_admin.put(f"/cases/sections/{sec.id}", json={"current_text": "Corrupted by Immutability"})

        # Solicitud 3: Reasignación en terminal rechazada con 409
        client_a_admin.post(f"/cases/{case.id}/assign", json={"assigned_to_user_id": multi_tenant_fixture["admin_a"].id})

        # Verificación estricta de persistencia en PostgreSQL
        db_session.expire_all()
        sec_db = db_session.query(ParsedSection).filter_by(id=sec.id).first()
        case_db = db_session.query(CaseFile).filter_by(id=case.id).first()

        assert sec_db.current_text == orig_sec_text
        assert sec_db.review_status == orig_sec_status
        assert case_db.status == orig_case_status
        assert case_db.assigned_to_user_id == orig_case_assigned
    finally:
        clear_overrides()


# =========================================================================
# 8. GET /cases/jobs/{job_id}: AISLAMIENTO MULTI-TENANT Y ASIGNACIÓN (SIN FUGAS)
# =========================================================================

def test_job_status_tenant_and_assignment_authorization(multi_tenant_fixture, db_session):
    """GET /cases/jobs/{job_id} debe exigir tenant y asignación (incluso en fallback), sin fugar metadatos."""
    from app.main import app
    from app.services.job_repository import JobRepository
    case_a = multi_tenant_fixture["case_a_active"]

    # 1. Crear un job en JobRepository para Tenant A (asociado a case_a_active, asignado a op_a_assigned)
    job_id = "test_job_auth_9001"
    JobRepository.create_job(
        db=db_session,
        case_id=case_a.id,
        tenant_id="tenant_a",
        user_id=302,
        job_type="QUOTATION_EXTRACTION",
        job_id=job_id
    )

    try:
        # A. Tenant B intentando consultar job de Tenant A -> 404 (sin fugas)
        set_user(multi_tenant_fixture["admin_b"])
        client_b = TestClient(app)
        res_b = client_b.get(f"/cases/jobs/{job_id}")
        assert res_b.status_code == 404
        assert res_b.json().get("detail") == "Job not found" or res_b.json().get("error", {}).get("message") == "Job not found"

        # B. Operador no asignado en Tenant A consultando job -> 404 (sin fugas)
        set_user(multi_tenant_fixture["op_a_unassigned"])
        client_unassigned = TestClient(app)
        res_unassigned = client_unassigned.get(f"/cases/jobs/{job_id}")
        assert res_unassigned.status_code == 404
        assert res_unassigned.json().get("detail") == "Job not found" or res_unassigned.json().get("error", {}).get("message") == "Job not found"

        # C. Operador asignado en Tenant A consultando job -> 200 OK con metadatos
        set_user(multi_tenant_fixture["op_a_assigned"])
        client_assigned = TestClient(app)
        res_assigned = client_assigned.get(f"/cases/jobs/{job_id}")
        assert res_assigned.status_code == 200
        data_assigned = res_assigned.json()
        assert data_assigned["job_id"] == job_id
        assert data_assigned["case_status"] == case_a.status

        # D. Administrador en Tenant A consultando job -> 200 OK
        set_user(multi_tenant_fixture["admin_a"])
        client_admin = TestClient(app)
        res_admin = client_admin.get(f"/cases/jobs/{job_id}")
        assert res_admin.status_code == 200
        assert res_admin.json()["job_id"] == job_id

        # E. Fallback Redis con job inexistente o ajeno -> 404 (sin fugas)
        set_user(multi_tenant_fixture["admin_b"])
        res_redis_b = client_b.get("/cases/jobs/nonexistent_or_other_tenant_job")
        assert res_redis_b.status_code == 404
        assert res_redis_b.json().get("detail") == "Job not found" or res_redis_b.json().get("error", {}).get("message") == "Job not found"
    finally:
        clear_overrides()


# =========================================================================
# 9. GENERACIÓN DOCUMENTAL POST-APROBACIÓN Y CONTROL DE ROLES DE ESCRITURA
# =========================================================================

def test_generate_html_write_permissions_and_post_approval(multi_tenant_fixture, db_session):
    """POST /{case_id}/generate/html exige rol de escritura pero permite la generación documental legítima tras la aprobación."""
    from app.main import app
    case_appr = multi_tenant_fixture["case_a_approved"]
    case_ro = multi_tenant_fixture["case_a_ro_assigned"]

    db_session.expire_all()
    orig_output_count = db_session.query(GeneratedOutput).filter_by(case_id=case_appr.id).count()

    try:
        # 1. Operador asignado sobre caso APPROVED: permitido legítimamente -> 200 OK
        set_user(multi_tenant_fixture["op_a_assigned"])
        client_op = TestClient(app)
        res_gen = client_op.post(f"/cases/{case_appr.id}/generate/html")
        assert res_gen.status_code == 200

        # Snapshot posterior: se persistió un nuevo GeneratedOutput legítimo
        db_session.expire_all()
        post_output_count = db_session.query(GeneratedOutput).filter_by(case_id=case_appr.id).count()
        assert post_output_count == orig_output_count + 1

        # 2. READONLY asignado intentando generar documento -> 403 Forbidden
        set_user(multi_tenant_fixture["ro_a"])
        client_ro = TestClient(app)
        res_ro = client_ro.post(f"/cases/{case_ro.id}/generate/html")
        assert res_ro.status_code == 403

        # 3. READONLY no asignado intentando generar documento -> 404 Not Found
        res_ro_unassigned = client_ro.post(f"/cases/{case_appr.id}/generate/html")
        assert res_ro_unassigned.status_code == 404
    finally:
        clear_overrides()


# =========================================================================
# 10. CONTROL RBAC ESTRICTO: READONLY NO PUEDE CREAR CASOS NI CARGAR REQUERIMIENTOS
# =========================================================================

def test_readonly_user_cannot_create_case_or_upload_requirement(multi_tenant_fixture, db_session, monkeypatch):
    """
    Usuarios con rol READONLY tienen prohibido crear expedientes (POST /cases/)
    y cargar documentos de requerimiento (POST /cases/{case_id}/requirement/upload).
    Se comprueba con solicitudes válidas que se responde HTTP 403 Forbidden
    y que existe ausencia absoluta de efectos secundarios en base de datos.
    """
    from app.main import app

    ro_user = multi_tenant_fixture["ro_a"]
    case_ro = multi_tenant_fixture["case_a_ro_assigned"]
    case_active = multi_tenant_fixture["case_a_active"]

    # Mock RQ queue si acaso para upload de requerimiento
    mock_queue = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "mock_rq_job_ro_deny"
    mock_queue.enqueue.return_value = mock_job
    monkeypatch.setattr("app.api.routers.cases.task_queue", mock_queue)

    # 1. Snapshot previo de la base de datos
    db_session.expire_all()
    orig_cases_count = db_session.query(CaseFile).count()
    orig_docs_count = db_session.query(UploadedDocument).count()
    orig_jobs_count = db_session.query(ProcessingJob).count()

    try:
        set_user(ro_user)
        client = TestClient(app)

        # A. Intento de creación de expediente con payload válido por usuario READONLY
        valid_case_payload = {
            "title": "Expediente Prohibido Readonly",
            "contract_type": "BIENES"
        }
        res_create = client.post("/cases/", json=valid_case_payload)
        assert res_create.status_code == 403
        err_msg = res_create.json().get("detail") or res_create.json().get("error", {}).get("message", "")
        assert "permission" in err_msg.lower() or "forbidden" in err_msg.lower() or "not allowed" in err_msg.lower()

        # B. Intento de carga de requerimiento con archivo PDF válido por usuario READONLY (en caso asignado)
        valid_pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        files = {
            "file": ("requerimiento_legal.pdf", valid_pdf_content, "application/pdf")
        }
        res_upload_assigned = client.post(f"/cases/{case_ro.id}/requirement/upload", files=files)
        assert res_upload_assigned.status_code == 403

        # C. Intento de carga de requerimiento por usuario READONLY (en caso no asignado)
        files_unassigned = {
            "file": ("requerimiento_unassigned.pdf", valid_pdf_content, "application/pdf")
        }
        res_upload_unassigned = client.post(f"/cases/{case_active.id}/requirement/upload", files=files_unassigned)
        assert res_upload_unassigned.status_code in (403, 404)

        # 2. Verificación rigurosa de ausencia total de efectos secundarios en base de datos
        db_session.expire_all()
        post_cases_count = db_session.query(CaseFile).count()
        post_docs_count = db_session.query(UploadedDocument).count()
        post_jobs_count = db_session.query(ProcessingJob).count()

        assert post_cases_count == orig_cases_count, "No debe haberse creado ningún expediente"
        assert post_docs_count == orig_docs_count, "No debe haberse insertado ningún documento"
        assert post_jobs_count == orig_jobs_count, "No debe haberse encolado ningún trabajo de procesamiento"

        assert db_session.query(CaseFile).filter_by(title="Expediente Prohibido Readonly").first() is None
        assert db_session.query(UploadedDocument).filter_by(original_filename="requerimiento_legal.pdf").first() is None
        assert db_session.query(UploadedDocument).filter_by(original_filename="requerimiento_unassigned.pdf").first() is None

        # D. Comprobar que usuarios con rol de escritura (ADMIN / OPERATOR asignado) SÍ pueden crear y subir
        set_user(multi_tenant_fixture["op_a_assigned"])
        client_op = TestClient(app)
        res_create_op = client_op.post("/cases/", json={"title": "Expediente Legitimo Operador", "contract_type": "BIENES"})
        assert res_create_op.status_code == 200
        created_case_id = res_create_op.json()["id"]

        # Cargar requerimiento legítimamente
        files_legit = {
            "file": ("requerimiento_legit.pdf", valid_pdf_content, "application/pdf")
        }
        res_upload_legit = client_op.post(f"/cases/{created_case_id}/requirement/upload", files=files_legit)
        assert res_upload_legit.status_code == 200
    finally:
        clear_overrides()
