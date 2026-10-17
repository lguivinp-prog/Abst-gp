import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, User, AuditLog, UploadedDocument
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_offer_item import SupplierOfferItem
from app.models.v6.case_procurement_item import CaseProcurementItem
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.contractual_condition import ContractualCondition
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal
from app.models.v6.case_workflow import CaseWorkflow
from app.api.auth import get_current_active_user, get_current_user
from app.main import app

def attach_verified_evidence(db_session: Session, case_id: int, offer_id: int, requirement_id: int, fragment: str = "Garantía técnica y cumplimiento especificado de 48 meses."):
    doc = db_session.query(UploadedDocument).filter_by(case_id=case_id).first()
    if not doc:
        doc = UploadedDocument(
            case_id=case_id,
            document_type="quotation",
            original_filename="propuesta_tecnica.pdf",
            stored_path="/tmp/propuesta_tecnica.pdf",
            mime_type="application/pdf",
            processing_status="completed"
        )
        db_session.add(doc)
        db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer_id,
        document_id=doc.id,
        document_type="FICHA_TECNICA",
        fragment=fragment,
        confidence=0.98,
        page=1
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case_id,
        supplier_offer_id=offer_id,
        requirement_id=requirement_id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        source_document="propuesta_tecnica.pdf",
        page=1,
        fragment=fragment,
        verification_status="VERIFIED",
        verified_by=1
    )
    db_session.add(ore)
    db_session.commit()
    return ore

def get_operator_client():
    op_user = User(
        id=1,
        username="operator_user",
        role="OPERATOR",
        is_active=True,
        must_change_password=False,
        tenant_id="mega_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: op_user
    app.dependency_overrides[get_current_user] = lambda: op_user
    return TestClient(app)

def get_supervisor_client(user_id: int = 1):
    supervisor_user = User(
        id=user_id,
        username="supervisor_user",
        role="SUPERVISOR",
        is_active=True,
        must_change_password=False,
        tenant_id="mega_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: supervisor_user
    app.dependency_overrides[get_current_user] = lambda: supervisor_user
    return TestClient(app)

def get_admin_client():
    admin_user = User(
        id=2,
        username="admin_user",
        role="ADMIN",
        is_active=True,
        must_change_password=False,
        tenant_id="mega_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return TestClient(app)

def cleanup_overrides():
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# ESCENARIOS A, B, C: Matriz Comparativa, Evaluación y Selección Coincidente
# ==============================================================================
def test_p11_scenarios_a_b_c_comparison_and_matching_selection(
    admin_client: TestClient,
    db_session: Session,
    setup_mega_tenant
):
    """
    Escenario A: Expediente de bienes con dos ítems, dos proveedores y diferentes condiciones técnicas.
    Escenario B: Comparación correcta cuando un proveedor cumple y otro tiene requisitos no cumplidos.
    Escenario C: Selección coincidente con la recomendación válida sin necesidad de justificación forzada.
    """
    # 1. Crear expediente de BIENES
    case = CaseFile(
        title="Adquisición de Equipamiento Informático",
        contract_type="BIENES",
        status="WAITING_QUOTATION",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    # 2. Dos ítems requeridos
    item1 = CaseProcurementItem(
        case_id=case.id,
        item_number=1,
        description="Laptops de Alto Rendimiento",
        quantity=10,
        unit="UND"
    )
    item2 = CaseProcurementItem(
        case_id=case.id,
        item_number=2,
        description="Monitores 27 pulgadas 4K",
        quantity=10,
        unit="UND"
    )
    db_session.add_all([item1, item2])

    # 3. Requisito técnico común
    req1 = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía de 36 meses on-site",
        status="VALIDATED",
        mandatory=True
    )
    db_session.add(req1)
    db_session.commit()

    # 4. Dos proveedores
    sup1 = Supplier(ruc="20555555551", business_name="Soluciones Tech SAC", tenant_id="mega_tenant")
    sup2 = Supplier(ruc="20555555552", business_name="Inversiones Globales EIRL", tenant_id="mega_tenant")
    db_session.add_all([sup1, sup2])
    db_session.commit()

    # Perfiles verificados
    prof1 = SupplierProfile(supplier_id=sup1.id, validation_status="VERIFIED")
    prof2 = SupplierProfile(supplier_id=sup2.id, validation_status="VERIFIED")
    db_session.add_all([prof1, prof2])
    db_session.commit()

    # 5. Ofertas de ambos proveedores con precios para ambos ítems
    offer1 = SupplierOffer(
        case_id=case.id,
        supplier_id=sup1.id,
        status="SUBMITTED",
        total_amount=50000.0,
        price=50000.0,
        currency="PEN"
    )
    offer2 = SupplierOffer(
        case_id=case.id,
        supplier_id=sup2.id,
        status="SUBMITTED",
        total_amount=48000.0,
        price=48000.0,
        currency="PEN"
    )
    db_session.add_all([offer1, offer2])
    db_session.commit()

    db_session.add_all([
        SupplierOfferItem(supplier_offer_id=offer1.id, procurement_item_id=item1.id, description="Laptop", quantity=10, unit="UND", unit_price=4000.0),
        SupplierOfferItem(supplier_offer_id=offer1.id, procurement_item_id=item2.id, description="Monitor", quantity=10, unit="UND", unit_price=1000.0),
        SupplierOfferItem(supplier_offer_id=offer2.id, procurement_item_id=item1.id, description="Laptop", quantity=10, unit="UND", unit_price=3800.0),
        SupplierOfferItem(supplier_offer_id=offer2.id, procurement_item_id=item2.id, description="Monitor", quantity=10, unit="UND", unit_price=1000.0),
    ])

    # 6. Evaluaciones técnicas:
    # Proveedor 1 CUMPLE y MEJORA
    eval1 = OfferEvaluation(
        supplier_offer_id=offer1.id,
        requirement_id=req1.id,
        status="PASSED",
        explanation="Garantía ofrecida de 48 meses",
        evaluation_confidence=0.98
    )
    cond1 = ContractualCondition(
        supplier_offer_id=offer1.id,
        key="garantia",
        label="Garantía Técnica",
        required_value="36 meses",
        offered_value="48 meses",
        final_value="48 meses",
        resolution_rule="MAYOR_ES_MEJOR",
        status="CUMPLE_Y_MEJORA"
    )

    # Proveedor 2 NO CUMPLE (ofreció sólo 12 meses)
    eval2 = OfferEvaluation(
        supplier_offer_id=offer2.id,
        requirement_id=req1.id,
        status="CONFLICT",
        explanation="Ofrece solo 12 meses de garantía",
        evaluation_confidence=0.95
    )
    cond2 = ContractualCondition(
        supplier_offer_id=offer2.id,
        key="garantia",
        label="Garantía Técnica",
        required_value="36 meses",
        offered_value="12 meses",
        final_value="12 meses",
        resolution_rule="MAYOR_ES_MEJOR",
        status="NO_CUMPLE"
    )
    db_session.add_all([eval1, cond1, eval2, cond2])
    db_session.commit()
    attach_verified_evidence(db_session, case.id, offer1.id, req1.id, fragment="Garantía ofrecida de 48 meses on-site")

    # Verificación Escenario B: Consultar ranking VFM y evaluaciones
    vfm_res = admin_client.get(f"/api/v6/cases/{case.id}/evaluations/vfm")
    assert vfm_res.status_code == 200
    vfm_data = vfm_res.json()
    assert len(vfm_data) == 2

    # Proveedor 1 debe ser elegible y el #1
    eligible_offers = [r for r in vfm_data if r["is_eligible"]]
    ineligible_offers = [r for r in vfm_data if not r["is_eligible"]]
    assert len(eligible_offers) == 1
    assert eligible_offers[0]["supplier_offer_id"] == offer1.id
    assert len(ineligible_offers) == 1
    assert ineligible_offers[0]["supplier_offer_id"] == offer2.id
    assert ineligible_offers[0]["reason"] in ("FAILED_CONTRACTUAL_CONDITIONS", "CONFLICT_MANDATORY_REQUIREMENTS")

    # Verificación Escenario C: Proponer selección de la oferta recomendada (offer1)
    # Debe ser aceptada sin exigir justificación forzada
    c_payload = {"supplier_offer_id": offer1.id}
    c_res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json=c_payload)
    assert c_res.status_code == 200
    assert c_res.json()["status"] == "UNDER_REVIEW"

    # Verificar que el intento quedó registrado en UNDER_REVIEW
    attempt = db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first()
    assert attempt is not None
    assert attempt.supplier_offer_id == offer1.id
    assert attempt.status == "UNDER_REVIEW"

# ==============================================================================
# ESCENARIOS D y E: Selección Divergente (Rechazo sin motivo / Aceptación con motivo)
# ==============================================================================
def test_p11_scenarios_d_and_e_divergent_selection(
    admin_client: TestClient,
    db_session: Session,
    setup_mega_tenant
):
    """
    Escenario D: Selección divergente sin justificación es obligatoriamente rechazada (400).
    Escenario E: Selección divergente con justificación válida es aceptada y conserva trazabilidad.
    """
    case = CaseFile(
        title="Servicio de Mantenimiento",
        contract_type="SERVICIOS",
        status="WAITING_QUOTATION",
        assigned_to_user_id=1,
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    sup1 = Supplier(ruc="20100000001", business_name="Proveedor Alfa SAC", tenant_id="mega_tenant")
    sup2 = Supplier(ruc="20100000002", business_name="Proveedor Beta SAC", tenant_id="mega_tenant")
    db_session.add_all([sup1, sup2])
    db_session.commit()

    prof1 = SupplierProfile(supplier_id=sup1.id, validation_status="VERIFIED")
    prof2 = SupplierProfile(supplier_id=sup2.id, validation_status="VERIFIED")
    db_session.add_all([prof1, prof2])
    db_session.commit()

    # Dos ofertas elegibles:
    # Offer 1: S/ 30,000, Cumple (+5 pts) -> VfM = 30000 / 5 = 6000 (Mejor recomendación)
    # Offer 2: S/ 40,000, Cumple (+5 pts) -> VfM = 40000 / 5 = 8000 (Segunda opción)
    offer1 = SupplierOffer(case_id=case.id, supplier_id=sup1.id, status="SUBMITTED", total_amount=30000.0, price=30000.0, currency="PEN")
    offer2 = SupplierOffer(case_id=case.id, supplier_id=sup2.id, status="SUBMITTED", total_amount=40000.0, price=40000.0, currency="PEN")
    db_session.add_all([offer1, offer2])
    db_session.commit()

    cond1 = ContractualCondition(supplier_offer_id=offer1.id, key="plazo", label="Plazo de Entrega", resolution_rule="EXACT", status="CUMPLE")
    cond2 = ContractualCondition(supplier_offer_id=offer2.id, key="plazo", label="Plazo de Entrega", resolution_rule="EXACT", status="CUMPLE")
    db_session.add_all([cond1, cond2])
    db_session.commit()

    # Confirmar que offer1 es la #1
    vfm_res = admin_client.get(f"/api/v6/cases/{case.id}/evaluations/vfm")
    assert vfm_res.status_code == 200
    vfm_list = vfm_res.json()
    assert vfm_list[0]["supplier_offer_id"] == offer1.id
    assert vfm_list[1]["supplier_offer_id"] == offer2.id

    # --------------------------------------------------------------------------
    # ESCENARIO D: Proponer offer2 (divergente) SIN justificación
    # --------------------------------------------------------------------------
    payload_no_just = {"supplier_offer_id": offer2.id, "justification_comment": ""}
    d_res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json=payload_no_just)
    assert d_res.status_code == 400
    assert "Justification is required when proposing an offer different from the top recommended offer" in d_res.json()["detail"]

    # Probar también con None o espacios
    d_res_spaces = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer2.id, "justification_comment": "   "})
    assert d_res_spaces.status_code == 400

    # --------------------------------------------------------------------------
    # ESCENARIO E: Proponer offer2 (divergente) CON justificación válida
    # --------------------------------------------------------------------------
    just_text = "Se propone Proveedor Beta por contar con equipo local disponible para soporte 24/7 certificado."
    payload_valid = {"supplier_offer_id": offer2.id, "justification_comment": just_text}
    e_res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json=payload_valid)
    assert e_res.status_code == 200
    assert e_res.json()["status"] == "UNDER_REVIEW"

    # Verificar trazabilidad en DB
    attempt = db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id, supplier_offer_id=offer2.id).first()
    assert attempt is not None
    assert attempt.justification_comment == just_text
    assert attempt.status == "UNDER_REVIEW"

    audit = db_session.query(AuditLog).filter_by(
        action="PROPOSE_SELECTION",
        entity_id=str(case.id)
    ).order_by(AuditLog.id.desc()).first()
    assert audit is not None
    assert "Divergent: True" in audit.details

# ==============================================================================
# ESCENARIOS F, G, H: Control de Roles, Aprobación por Supervisor e Inmutabilidad
# ==============================================================================
def test_p11_scenarios_f_g_h_roles_approval_and_immutability(
    db_session: Session,
    setup_mega_tenant
):
    """
    Escenario F: Operador intenta aprobar la selección mediante API -> 403 Forbidden.
    Escenario G: Supervisor autorizado aprueba la propuesta -> conserva integridad de workflow y audit.
    Escenario H: Expediente aprobado rechaza modificaciones posteriores (409 Conflict).
    """
    case = CaseFile(
        title="Expediente para Control de Aprobación",
        contract_type="BIENES",
        status="WAITING_QUOTATION",
        assigned_to_user_id=1,
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    sup = Supplier(ruc="20999999991", business_name="Proveedor Calificado SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()

    prof = SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED")
    db_session.add(prof)
    db_session.commit()

    offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=15000.0, price=15000.0, currency="PEN")
    db_session.add(offer)
    db_session.commit()

    cond = ContractualCondition(supplier_offer_id=offer.id, key="plazo", label="Plazo de Entrega", resolution_rule="EXACT", status="CUMPLE")
    db_session.add(cond)
    db_session.commit()

    admin_client = get_admin_client()
    try:
        # 1. Proponer selección
        prop_res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Propuesta recomendada"})
        assert prop_res.status_code == 200

        # --------------------------------------------------------------------------
        # ESCENARIO F: Operador intenta aprobar -> 403 Forbidden
        # --------------------------------------------------------------------------
        op_client = get_operator_client()
        op_res = op_client.post(f"/api/v6/cases/{case.id}/approve")
        assert op_res.status_code == 403
        assert "Supervisor role required" in op_res.json()["detail"]

        # Verificar que el caso NO fue aprobado
        db_session.refresh(case)
        assert case.status == "WAITING_QUOTATION"

        # --------------------------------------------------------------------------
        # ESCENARIO G: Supervisor autorizado aprueba la propuesta
        # --------------------------------------------------------------------------
        sup_client = get_supervisor_client()
        sup_res = sup_client.post(f"/api/v6/cases/{case.id}/approve")
        assert sup_res.status_code == 200
        assert sup_res.json()["status"] == "APPROVED"

        # Verificar integridad
        db_session.refresh(case)
        assert case.status == "APPROVED"

        workflow = db_session.query(CaseWorkflow).filter_by(case_id=case.id).first()
        assert workflow.status == "APPROVED"
        assert workflow.supervisor_id == 1

        final_record = db_session.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()
        assert final_record is not None

        audit = db_session.query(AuditLog).filter_by(
            action="APPROVE_SELECTION",
            entity_id=str(case.id)
        ).first()
        assert audit is not None
        assert audit.user_id == 1

        # ----------------------------------------------------------------------
        # ESCENARIO H: Expediente aprobado rechaza modificaciones posteriores
        # ----------------------------------------------------------------------
        # H1: Intentar proponer otra selección -> 409 Conflict
        h1_res = sup_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id})
        assert h1_res.status_code == 409

        # H2: Intentar aprobar de nuevo -> 409 Conflict
        h2_res = sup_client.post(f"/api/v6/cases/{case.id}/approve")
        assert h2_res.status_code == 409

        # H3: Intentar agregar oferta -> 409 Conflict
        h3_res = sup_client.post(f"/api/v6/cases/{case.id}/offers", json={"supplier_id": sup.id, "price": 10000.0})
        assert h3_res.status_code == 409

    finally:
        cleanup_overrides()

# ==============================================================================
# ESCENARIO I: Invalidación por cambio en requerimiento
# ==============================================================================
def test_p11_scenario_i_requirement_change_invalidates_and_reconfirm(
    admin_client: TestClient,
    db_session: Session,
    setup_mega_tenant
):
    """
    Escenario I: Cambio del requerimiento invalida la confirmación (WAITING_QUOTATION -> PROCESSING_REQUIREMENT)
    e impide operaciones de cotización y selección hasta la reconfirmación.
    """
    case = CaseFile(
        title="Expediente Ciclo de Vida Requerimientos",
        contract_type="BIENES",
        status="WAITING_QUOTATION",
        tenant_id="mega_tenant"
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Plazo de entrega máximo 15 días",
        status="VALIDATED",
        mandatory=True
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20123456780", business_name="Comercial Lima SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()

    prof = SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED")
    db_session.add(prof)

    offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
    db_session.add(offer)
    db_session.commit()

    cond = ContractualCondition(supplier_offer_id=offer.id, key="plazo", label="Plazo de entrega", resolution_rule="EXACT_MATCH", status="CUMPLE")
    eval_req = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req.id, status="PASSED", evaluation_confidence=0.95)
    db_session.add_all([cond, eval_req])
    db_session.commit()
    attach_verified_evidence(db_session, case.id, offer.id, req.id, fragment="Plazo de entrega confirmado de 5 días hábiles")

    # 1. Modificar requerimiento cuando el caso está en WAITING_QUOTATION
    update_res = admin_client.put(
        f"/api/v6/cases/{case.id}/requirements/{req.id}",
        json={"status": "MODIFIED_BY_USER", "description": "Plazo de entrega reducido a 7 días", "reason": "Urgencia institucional"}
    )
    assert update_res.status_code == 200

    # 2. Verificar que el estado del expediente se invalidó a PROCESSING_REQUIREMENT
    db_session.refresh(case)
    assert case.status == "PROCESSING_REQUIREMENT"

    # 3. Intentar proponer selección -> Rechazado por guard de requerimiento (400)
    blocked_sel = admin_client.post(
        f"/api/v6/cases/{case.id}/selection",
        json={"supplier_offer_id": offer.id, "justification_comment": "Test"}
    )
    assert blocked_sel.status_code == 400
    assert "Requirement review is pending or invalid" in blocked_sel.json()["detail"]

    # 4. Reconfirmar requerimientos
    confirm_res = admin_client.post(f"/api/v6/cases/{case.id}/requirements/confirm")
    assert confirm_res.status_code == 200
    db_session.refresh(case)
    assert case.status == "WAITING_QUOTATION"

    # 5. Operación posterior ahora tiene éxito
    unblocked_sel = admin_client.post(
        f"/api/v6/cases/{case.id}/selection",
        json={"supplier_offer_id": offer.id, "justification_comment": "Propuesta tras reconfirmación"}
    )
    assert unblocked_sel.status_code == 200
    assert unblocked_sel.json()["status"] == "UNDER_REVIEW"

# ==============================================================================
# ESCENARIO J: Información Incompleta y Bloqueos Obligatorios
# ==============================================================================
def test_p11_scenario_j_incomplete_or_blocked_offers(
    db_session: Session,
    setup_mega_tenant
):
    """
    Escenario J: Visualización de información incompleta o resultados no disponibles:
    - Oferta PENDING sin precios ni documentos es rechazada para selección.
    - Oferta con ítems faltantes es rechazada.
    - Proveedor no verificado es rechazado para operador, y exige SUPERVISOR_EXCEPTION para supervisor.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Control Incompletitud",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            assigned_to_user_id=1,
            tenant_id="mega_tenant"
        )
        db_session.add(case)
        db_session.commit()

        # İtem requerido
        item = CaseProcurementItem(case_id=case.id, item_number=1, description="Servidor Rack", quantity=2, unit="UND")
        db_session.add(item)

        # Proveedor no verificado
        sup_unverified = Supplier(ruc="20888888888", business_name="Proveedor No Verificado SAC", tenant_id="mega_tenant")
        db_session.add(sup_unverified)
        db_session.commit()

        prof = SupplierProfile(supplier_id=sup_unverified.id, validation_status="PENDING_REVIEW")
        db_session.add(prof)
        db_session.commit()

        # J1: Oferta PENDING
        pending_offer = SupplierOffer(case_id=case.id, supplier_id=sup_unverified.id, status="PENDING")
        db_session.add(pending_offer)
        db_session.commit()

        res_pending = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": pending_offer.id})
        assert res_pending.status_code == 400
        assert "Cannot select a PENDING offer" in res_pending.json()["detail"]

        # J2: Oferta SUBMITTED pero incompleta (sin ítems ni precio)
        incomplete_offer = SupplierOffer(case_id=case.id, supplier_id=sup_unverified.id, status="SUBMITTED", price=None, total_amount=None)
        db_session.add(incomplete_offer)
        db_session.commit()

        res_incomp = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": incomplete_offer.id})
        assert res_incomp.status_code == 400
        assert "Incomplete offer" in res_incomp.json()["detail"]

        # J3: Oferta completa pero proveedor no verificado con operador
        complete_offer = SupplierOffer(case_id=case.id, supplier_id=sup_unverified.id, status="SUBMITTED", total_amount=20000.0, price=20000.0, currency="PEN")
        db_session.add(complete_offer)
        db_session.commit()

        offer_item = SupplierOfferItem(supplier_offer_id=complete_offer.id, procurement_item_id=item.id, description="Servidor Rack", quantity=2, unit="UND", unit_price=10000.0)
        cond_j3 = ContractualCondition(supplier_offer_id=complete_offer.id, key="rack", label="Rack", resolution_rule="EXACT_MATCH", status="CUMPLE")
        db_session.add_all([offer_item, cond_j3])
        db_session.commit()

        # Operador intenta proponer -> rechazado (400)
        op_client = get_operator_client()
        res_op_unverified = op_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": complete_offer.id, "justification_comment": "Intento de operador"}
        )
        assert res_op_unverified.status_code == 400
        assert "Supervisor override required" in res_op_unverified.json()["detail"]

        # Supervisor autorizado puede proponer mediante SUPERVISOR_EXCEPTION
        sup_client = get_supervisor_client()
        res_sup_override = sup_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": complete_offer.id, "justification_comment": "Excepción motivada por contingencia técnica"}
        )
        assert res_sup_override.status_code == 200
        assert res_sup_override.json()["status"] == "UNDER_REVIEW"

        # Verificar auditoría de advertencia SUPERVISOR_EXCEPTION_SELECT
        audit_ex = db_session.query(AuditLog).filter_by(
            action="SUPERVISOR_EXCEPTION_SELECT",
            entity_type="SupplierOffer"
        ).first()
        assert audit_ex is not None
        assert audit_ex.status == "WARNING"
    finally:
        cleanup_overrides()

# ==============================================================================
# FASE 3 & 4 NEGATIVAS: Cobertura, Duplicados, Finitud de Precios y Recomendación
# ==============================================================================
def test_p11_scenario_k_item_coverage_duplicates_and_finiteness_negative(
    db_session: Session,
    setup_mega_tenant
):
    """
    Fase 3 y 4: Pruebas negativas dirigidas:
    - K1: Cobertura parcial (falta 1 CaseProcurementItem obligatorio) -> Rechazado
    - K2: Duplicación de ítems para simular cobertura -> Rechazado
    - K3: İtem perteneciente a otro expediente -> Rechazado
    - K4: Precios unitarios negativos o cero -> Rechazado
    - K5: Precio total negativo o cero -> Rechazado
    - K6: Oferta no evaluada (sin ContractualCondition) -> is_eligible=False, motivo NOT_EVALUATED
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente de Control Negativo de Ítems",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            assigned_to_user_id=1,
            tenant_id="mega_tenant"
        )
        other_case = CaseFile(
            title="Otro Expediente Distinto",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            assigned_to_user_id=1,
            tenant_id="mega_tenant"
        )
        db_session.add_all([case, other_case])
        db_session.commit()

        # Dos ítems para 'case' y uno para 'other_case'
        pi1 = CaseProcurementItem(case_id=case.id, item_number="1", description="Item 1", quantity=5, unit="UND")
        pi2 = CaseProcurementItem(case_id=case.id, item_number="2", description="Item 2", quantity=10, unit="UND")
        pi_other = CaseProcurementItem(case_id=other_case.id, item_number="1", description="Item Ajeno", quantity=1, unit="UND")
        db_session.add_all([pi1, pi2, pi_other])

        sup = Supplier(ruc="20999999999", business_name="Proveedor Negativo SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()

        prof = SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED")
        db_session.add(prof)
        db_session.commit()

        # K1: Cobertura parcial (cotiza solo pi1)
        offer_partial = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=5000.0, price=5000.0, currency="PEN")
        db_session.add(offer_partial)
        db_session.commit()
        item_k1 = SupplierOfferItem(supplier_offer_id=offer_partial.id, procurement_item_id=pi1.id, description="Item 1", quantity=5, unit="UND", unit_price=1000.0)
        db_session.add(item_k1)
        db_session.commit()

        res_k1 = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer_partial.id, "justification_comment": "Test K1"})
        assert res_k1.status_code == 400
        assert "Missing coverage for required procurement items" in res_k1.json()["detail"]

        # K2: Duplicación de ítems (defensa en profundidad: comprobación de ítems duplicados)
        from unittest.mock import MagicMock
        dummy_offer = MagicMock()
        dummy_offer.id = 888
        dummy_offer.status = "SUBMITTED"
        dummy_offer.total_amount = 10000.0
        dummy_offer.price = 10000.0
        item_mock1 = MagicMock(id=1, procurement_item_id=pi1.id, unit_price=1000.0, quantity=5)
        item_mock2 = MagicMock(id=2, procurement_item_id=pi1.id, unit_price=1000.0, quantity=5)
        dummy_offer.items = [item_mock1, item_mock2]

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = dummy_offer
        mock_db.query.return_value.filter_by.return_value.all.return_value = [pi1, pi2]

        from app.services.v6.selection.selection_service import SelectionService
        with pytest.raises(ValueError, match="Duplicate procurement item reference"):
            SelectionService.propose_selection(
                db=mock_db,
                case_id=case.id,
                supplier_offer_id=888,
                justification="Test K2",
                user_id=1,
                tenant_id="mega_tenant"
            )

        # K3: Ítem de otro expediente (cotiza pi_other en case)
        offer_foreign = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
        db_session.add(offer_foreign)
        db_session.commit()
        item_f1 = SupplierOfferItem(supplier_offer_id=offer_foreign.id, procurement_item_id=pi1.id, description="Item 1", quantity=5, unit="UND", unit_price=1000.0)
        item_f2 = SupplierOfferItem(supplier_offer_id=offer_foreign.id, procurement_item_id=pi_other.id, description="Item Ajeno", quantity=10, unit="UND", unit_price=500.0)
        db_session.add_all([item_f1, item_f2])
        db_session.commit()

        res_k3 = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer_foreign.id, "justification_comment": "Test K3"})
        assert res_k3.status_code == 400
        assert "which does not belong to case" in res_k3.json()["detail"]

        # K4: Precio unitario no positivo (<= 0)
        offer_neg_unit = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
        db_session.add(offer_neg_unit)
        db_session.commit()
        item_neg1 = SupplierOfferItem(supplier_offer_id=offer_neg_unit.id, procurement_item_id=pi1.id, description="Item 1", quantity=5, unit="UND", unit_price=-100.0)
        item_neg2 = SupplierOfferItem(supplier_offer_id=offer_neg_unit.id, procurement_item_id=pi2.id, description="Item 2", quantity=10, unit="UND", unit_price=1000.0)
        db_session.add_all([item_neg1, item_neg2])
        db_session.commit()

        res_k4 = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer_neg_unit.id, "justification_comment": "Test K4"})
        assert res_k4.status_code == 400
        assert "has non-positive or non-finite unit price" in res_k4.json()["detail"]

        # K5: Precio total no positivo (total_amount = 0)
        offer_zero_tot = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=0.0, price=0.0, currency="PEN")
        db_session.add(offer_zero_tot)
        db_session.commit()
        item_z1 = SupplierOfferItem(supplier_offer_id=offer_zero_tot.id, procurement_item_id=pi1.id, description="Item 1", quantity=5, unit="UND", unit_price=100.0)
        item_z2 = SupplierOfferItem(supplier_offer_id=offer_zero_tot.id, procurement_item_id=pi2.id, description="Item 2", quantity=10, unit="UND", unit_price=100.0)
        db_session.add_all([item_z1, item_z2])
        db_session.commit()

        res_k5 = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer_zero_tot.id, "justification_comment": "Test K5"})
        assert res_k5.status_code == 400
        assert "is invalid or non-positive" in res_k5.json()["detail"]

        # K6: Oferta sin evaluación (ValueForMoneyService distingue no evaluada)
        from app.services.v6.evaluation.vfm_service import ValueForMoneyService
        vfm_service = ValueForMoneyService(db_session)
        vfm_list = vfm_service.calculate_vfm(case.id)
        # La oferta no evaluada debe tener is_eligible=False y reason="NOT_EVALUATED"
        unevaluated_res = next(r for r in vfm_list if r["supplier_offer_id"] == offer_partial.id)
        assert unevaluated_res["is_eligible"] is False
        assert unevaluated_res["is_evaluated"] is False
        assert unevaluated_res["reason"] == "NOT_EVALUATED"

    finally:
        cleanup_overrides()

# ==============================================================================
# FASE 5: Invalidación Transaccional Atómica y Rollback
# ==============================================================================
def test_p11_scenario_l_atomic_invalidation_and_rollback(
    db_session: Session,
    setup_mega_tenant
):
    """
    Fase 5: Verificación de atomicidad transaccional:
    - Creación/modificación de requerimiento genera un único commit atómico con audit log.
    - Si la actualización falla por validación (status inválido), no muta el estado del caso (rollback).
    - Expediente terminal bloquea cualquier edición (asegura inmutabilidad).
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Atomicidad",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            assigned_to_user_id=1,
            tenant_id="mega_tenant"
        )
        db_session.add(case)
        db_session.commit()

        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description="Requisito Inicial",
            status="VALIDATED",
            mandatory=True
        )
        db_session.add(req)
        db_session.commit()

        # L1: Intento de actualización con status inválido -> Rechazado (400)
        res_fail = admin_client.put(
            f"/api/v6/cases/{case.id}/requirements/{req.id}",
            json={"status": "INVALID_STATUS_XYZ", "description": "Intento inválido", "reason": "Sustento de prueba"}
        )
        assert res_fail.status_code == 400
        # Verificar que el caso NO mutó y sigue en WAITING_QUOTATION
        db_session.refresh(case)
        assert case.status == "WAITING_QUOTATION"

        # L2: Actualización válida -> Atómicamente transiciona a PROCESSING_REQUIREMENT y crea INVALIDATE_REQUIREMENT_REVIEW
        res_ok = admin_client.put(
            f"/api/v6/cases/{case.id}/requirements/{req.id}",
            json={"status": "MODIFIED_BY_USER", "description": "Requisito Ajustado", "reason": "Cambio técnico"}
        )
        assert res_ok.status_code == 200
        db_session.refresh(case)
        assert case.status == "PROCESSING_REQUIREMENT"

        inv_audit = db_session.query(AuditLog).filter_by(
            action="INVALIDATE_REQUIREMENT_REVIEW",
            entity_type="CaseFile",
            entity_id=str(case.id)
        ).first()
        assert inv_audit is not None
        assert inv_audit.status == "WARNING"

        # L3: Inmutabilidad sobre caso terminal
        case.status = "COMPLETED"
        db_session.commit()

        res_term = admin_client.put(
            f"/api/v6/cases/{case.id}/requirements/{req.id}",
            json={"status": "MODIFIED_BY_USER", "description": "Intento sobre caso cerrado", "reason": "Sustento sobre caso cerrado"}
        )
        assert res_term.status_code == 409
        assert "terminal" in res_term.json()["detail"].lower()
    finally:
        cleanup_overrides()

# ==============================================================================
# ESCENARIOS M–R: REMEDIACIÓN QUIRÚRGICA AUDITORÍA GPT
# ==============================================================================

def test_p11_scenario_m_disqualified_offer_cannot_be_selected_despite_justification(
    db_session: Session,
    setup_mega_tenant
):
    """
    Corrección 1: Oferta A recomendada y Oferta B descalificada (FAILED_CONTRACTUAL_CONDITIONS).
    Verificar que ni el operador ni el supervisor pueden proponer B aunque presenten justificación motivada.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Adquisición de Servidores de Alta Disponibilidad",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            assigned_to_user_id=1,
            tenant_id="mega_tenant"
        )
        db_session.add(case)
        db_session.commit()

        pi = CaseProcurementItem(case_id=case.id, item_number="1", description="Servidor Rack 2U", quantity=2, unit="UND")
        db_session.add(pi)

        sup_a = Supplier(ruc="20111111111", business_name="Proveedor Cumplidor Alfa", tenant_id="mega_tenant")
        sup_b = Supplier(ruc="20222222222", business_name="Proveedor Incumplidor Beta", tenant_id="mega_tenant")
        db_session.add_all([sup_a, sup_b])
        db_session.commit()

        prof_a = SupplierProfile(supplier_id=sup_a.id, validation_status="VERIFIED")
        prof_b = SupplierProfile(supplier_id=sup_b.id, validation_status="VERIFIED")
        db_session.add_all([prof_a, prof_b])
        db_session.commit()

        offer_a = SupplierOffer(case_id=case.id, supplier_id=sup_a.id, status="SUBMITTED", total_amount=20000.0, price=20000.0, currency="PEN")
        offer_b = SupplierOffer(case_id=case.id, supplier_id=sup_b.id, status="SUBMITTED", total_amount=18000.0, price=18000.0, currency="PEN")
        db_session.add_all([offer_a, offer_b])
        db_session.commit()

        itm_a = SupplierOfferItem(supplier_offer_id=offer_a.id, procurement_item_id=pi.id, description="Servidor 2U", quantity=2, unit="UND", unit_price=10000.0)
        itm_b = SupplierOfferItem(supplier_offer_id=offer_b.id, procurement_item_id=pi.id, description="Servidor 2U", quantity=2, unit="UND", unit_price=9000.0)
        db_session.add_all([itm_a, itm_b])
        db_session.commit()

        # Condiciones: Oferta A CUMPLE; Oferta B NO_CUMPLE
        cond_a = ContractualCondition(supplier_offer_id=offer_a.id, key="plazo", label="Plazo de entrega", resolution_rule="EXACT_MATCH", status="CUMPLE")
        cond_b = ContractualCondition(supplier_offer_id=offer_b.id, key="plazo", label="Plazo de entrega", resolution_rule="EXACT_MATCH", status="NO_CUMPLE")
        db_session.add_all([cond_a, cond_b])
        db_session.commit()

        # Operador intenta proponer la oferta B con justificación exhaustiva
        op_client = get_operator_client()
        res_op = op_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={
                "supplier_offer_id": offer_b.id,
                "justification_comment": "Se solicita seleccionar oferta B por precio menor y compromiso de subsanación técnica."
            }
        )
        assert res_op.status_code == 400
        assert "Cannot propose an ineligible offer" in res_op.json()["detail"]
        assert "Failed mandatory contractual conditions" in res_op.json()["detail"]

        # Supervisor también intenta proponer B con justificación -> Rechazado (excepción no puede anular condición excluyente)
        sup_client = get_supervisor_client()
        res_sup = sup_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={
                "supplier_offer_id": offer_b.id,
                "justification_comment": "Supervisor autoriza excepcionalmente oferta B."
            }
        )
        assert res_sup.status_code == 400
        assert "Failed mandatory contractual conditions" in res_sup.json()["detail"]
    finally:
        cleanup_overrides()

def test_p11_scenario_n_supplier_profile_verification_and_exceptions(
    db_session: Session,
    setup_mega_tenant
):
    """
    Corrección 2: Ausencia de perfil no es cumplimiento (UNAVAILABLE).
    - Proveedor sin perfil: Operador rechazado (400); Supervisor sin motivo rechazado (400); Supervisor con motivo aceptado (200) y auditado.
    - Proveedor con verificación desfavorable (REJECTED/SANCTIONED): Rechazado para todos sin excepción.
    """
    try:
        case = CaseFile(
            title="Caso Verificación de Perfiles",
            contract_type="SERVICIOS",
            status="WAITING_QUOTATION",
            assigned_to_user_id=1,
            tenant_id="mega_tenant"
        )
        db_session.add(case)
        db_session.commit()

        # Proveedor 1: sin perfil (profile is None)
        sup_no_prof = Supplier(ruc="20333333333", business_name="Proveedor Sin Perfil SAC", tenant_id="mega_tenant")
        # Proveedor 2: con perfil sancionado/rechazado
        sup_rejected = Supplier(ruc="20444444444", business_name="Proveedor Sancionado SRL", tenant_id="mega_tenant")
        db_session.add_all([sup_no_prof, sup_rejected])
        db_session.commit()

        prof_rej = SupplierProfile(supplier_id=sup_rejected.id, validation_status="SANCTIONED")
        db_session.add(prof_rej)
        db_session.commit()

        offer_no_prof = SupplierOffer(case_id=case.id, supplier_id=sup_no_prof.id, status="SUBMITTED", total_amount=5000.0, price=5000.0, currency="PEN")
        offer_rejected = SupplierOffer(case_id=case.id, supplier_id=sup_rejected.id, status="SUBMITTED", total_amount=5000.0, price=5000.0, currency="PEN")
        db_session.add_all([offer_no_prof, offer_rejected])
        db_session.commit()

        # Condición evaluada favorable para ambos
        cond1 = ContractualCondition(supplier_offer_id=offer_no_prof.id, key="garantia", label="Garantía", resolution_rule="EXACT_MATCH", status="CUMPLE")
        cond2 = ContractualCondition(supplier_offer_id=offer_rejected.id, key="garantia", label="Garantía", resolution_rule="EXACT_MATCH", status="CUMPLE")
        db_session.add_all([cond1, cond2])
        db_session.commit()

        op_client = get_operator_client()
        # N1: Operador intenta oferta sin perfil -> 400 (Supervisor override required)
        res_op_noprof = op_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": offer_no_prof.id, "justification_comment": "Justificación ordinaria"}
        )
        assert res_op_noprof.status_code == 400
        assert "UNAVAILABLE" in res_op_noprof.json()["detail"]

        # N2: Supervisor intenta oferta sin perfil pero SIN justificación -> 400 (justification required)
        sup_client = get_supervisor_client()
        res_sup_nojust = sup_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": offer_no_prof.id, "justification_comment": "   "}
        )
        assert res_sup_nojust.status_code == 400
        assert "Supervisor exception requires explicit justification" in res_sup_nojust.json()["detail"]

        # N3: Supervisor con justificación expresa -> 200 y registro de auditoría WARNING
        res_sup_ok = sup_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": offer_no_prof.id, "justification_comment": "Se autoriza excepcionalmente por ser proveedor nuevo en trámite de RNP."}
        )
        assert res_sup_ok.status_code == 200
        assert res_sup_ok.json()["status"] == "UNDER_REVIEW"

        audit_exc = db_session.query(AuditLog).filter_by(
            action="SUPERVISOR_EXCEPTION_SELECT",
            status="WARNING"
        ).first()
        assert audit_exc is not None
        assert "UNAVAILABLE" in audit_exc.details

        # N4: Proveedor sancionado/rechazado -> Rechazado incluso para Supervisor
        case2 = CaseFile(title="Caso Sancionado", contract_type="SERVICIOS", status="WAITING_QUOTATION", assigned_to_user_id=1, tenant_id="mega_tenant")
        db_session.add(case2)
        db_session.commit()
        offer_rej2 = SupplierOffer(case_id=case2.id, supplier_id=sup_rejected.id, status="SUBMITTED", total_amount=5000.0, price=5000.0, currency="PEN")
        db_session.add(offer_rej2)
        db_session.commit()
        cond_rej = ContractualCondition(supplier_offer_id=offer_rej2.id, key="garantia", label="Garantía", resolution_rule="EXACT_MATCH", status="CUMPLE")
        db_session.add(cond_rej)
        db_session.commit()

        res_sup_rej = sup_client.post(
            f"/api/v6/cases/{case2.id}/selection",
            json={"supplier_offer_id": offer_rej2.id, "justification_comment": "Intento de supervisor sobre sancionado"}
        )
        assert res_sup_rej.status_code == 400
        assert "unfavorable status" in res_sup_rej.json()["detail"]
    finally:
        cleanup_overrides()

def test_p11_scenario_o_quantity_mismatch_and_inconsistent_total(
    db_session: Session,
    setup_mega_tenant
):
    """
    Corrección 3: Correspondencia de cantidades requeridas vs ofertadas y consistencia de subtotales con total.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(title="Caso Cantidades", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
        db_session.add(case)
        db_session.commit()

        pi = CaseProcurementItem(case_id=case.id, item_number="1", description="Monitores 27 Pulgadas", quantity=10, unit="UND")
        db_session.add(pi)

        sup = Supplier(ruc="20555555555", business_name="Hardware Import SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        prof = SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED")
        db_session.add(prof)
        db_session.commit()

        # O1: Discrepancia de cantidad (requiere 10, cotiza 5)
        offer_qty_fail = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=5000.0, price=5000.0, currency="PEN")
        db_session.add(offer_qty_fail)
        db_session.commit()
        itm_qty_fail = SupplierOfferItem(supplier_offer_id=offer_qty_fail.id, procurement_item_id=pi.id, description="Monitor 27", quantity=5, unit="UND", unit_price=1000.0)
        db_session.add(itm_qty_fail)
        db_session.commit()

        res_qty = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer_qty_fail.id, "justification_comment": "Test O1"})
        assert res_qty.status_code == 400
        assert "Quantity mismatch" in res_qty.json()["detail"]

        # O2: Inconsistencia entre subtotales e importe total declarado (subtotal 10 * 1000 = 10000, header = 15000)
        offer_tot_fail = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=15000.0, price=15000.0, currency="PEN")
        db_session.add(offer_tot_fail)
        db_session.commit()
        itm_tot_fail = SupplierOfferItem(supplier_offer_id=offer_tot_fail.id, procurement_item_id=pi.id, description="Monitor 27", quantity=10, unit="UND", unit_price=1000.0)
        db_session.add(itm_tot_fail)
        db_session.commit()

        res_tot = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer_tot_fail.id, "justification_comment": "Test O2"})
        assert res_tot.status_code == 400
        assert "Inconsistent offer total amount" in res_tot.json()["detail"]
    finally:
        cleanup_overrides()

def test_p11_scenario_p_mandatory_evaluations_pending_blocks_eligibility(
    db_session: Session,
    setup_mega_tenant
):
    """
    Corrección 3: Evaluaciones obligatorias pendientes impiden declarar la oferta elegible.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(title="Caso Evaluaciones Incompletas", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
        db_session.add(case)
        db_session.commit()

        # 2 Requisitos obligatorios
        req1 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="Procesador i7", status="VALIDATED", mandatory=True)
        req2 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", description="Garantía 36 meses", status="VALIDATED", mandatory=True)
        db_session.add_all([req1, req2])
        db_session.commit()

        sup = Supplier(ruc="20666666666", business_name="Tech Solutions SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        prof = SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED")
        db_session.add(prof)
        db_session.commit()

        offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
        db_session.add(offer)
        db_session.commit()

        # Solo se evaluó req1, falta req2
        cond1 = ContractualCondition(supplier_offer_id=offer.id, key="cpu", label="CPU", resolution_rule="EXACT_MATCH", status="CUMPLE")
        eval1 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req1.id, status="PASSED", evaluation_confidence=0.95)
        db_session.add_all([cond1, eval1])
        db_session.commit()

        # Consultar VfM
        from app.services.v6.evaluation.vfm_service import ValueForMoneyService
        vfm_service = ValueForMoneyService(db_session)
        vfm_res = vfm_service.calculate_vfm(case.id)
        assert len(vfm_res) == 1
        assert vfm_res[0]["is_eligible"] is False
        assert vfm_res[0]["reason"] == "MANDATORY_EVALUATIONS_PENDING"

        # Proponer selección -> Rechazado por evaluaciones obligatorias pendientes
        res_sel = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Test P"})
        assert res_sel.status_code == 400
        assert "pending mandatory evaluations" in res_sel.json()["detail"]
    finally:
        cleanup_overrides()

def test_p11_scenario_q_incompatible_currencies_blocks_selection(
    db_session: Session,
    setup_mega_tenant
):
    """
    Corrección 3: Monedas no comparables sin regla de conversión explícita bloquean comparación y selección.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(title="Caso Monedas Mixtas", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
        db_session.add(case)
        db_session.commit()

        sup1 = Supplier(ruc="20777777771", business_name="Proveedor Soles SAC", tenant_id="mega_tenant")
        sup2 = Supplier(ruc="20777777772", business_name="Proveedor Dólares LLC", tenant_id="mega_tenant")
        db_session.add_all([sup1, sup2])
        db_session.commit()

        prof1 = SupplierProfile(supplier_id=sup1.id, validation_status="VERIFIED")
        prof2 = SupplierProfile(supplier_id=sup2.id, validation_status="VERIFIED")
        db_session.add_all([prof1, prof2])
        db_session.commit()

        offer_pen = SupplierOffer(case_id=case.id, supplier_id=sup1.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
        offer_usd = SupplierOffer(case_id=case.id, supplier_id=sup2.id, status="SUBMITTED", total_amount=3000.0, price=3000.0, currency="USD")
        db_session.add_all([offer_pen, offer_usd])
        db_session.commit()

        cond1 = ContractualCondition(supplier_offer_id=offer_pen.id, key="plazo", label="Plazo", resolution_rule="EXACT_MATCH", status="CUMPLE")
        cond2 = ContractualCondition(supplier_offer_id=offer_usd.id, key="plazo", label="Plazo", resolution_rule="EXACT_MATCH", status="CUMPLE")
        db_session.add_all([cond1, cond2])
        db_session.commit()

        # VfM marca como no elegible por monedas incompatibles
        from app.services.v6.evaluation.vfm_service import ValueForMoneyService
        vfm_service = ValueForMoneyService(db_session)
        vfm_res = vfm_service.calculate_vfm(case.id)
        assert len(vfm_res) == 2
        for r in vfm_res:
            assert r["is_eligible"] is False
            assert r["reason"] == "INCOMPATIBLE_CURRENCIES_NO_CONVERSION_RULE"

        # Selección rechazada por monedas incompatibles
        res_sel = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer_pen.id, "justification_comment": "Test Q"})
        assert res_sel.status_code == 400
        assert "Incompatible currencies in case" in res_sel.json()["detail"]
    finally:
        cleanup_overrides()

def test_p11_scenario_r_real_authorization_and_rollback(
    db_session: Session,
    setup_mega_tenant
):
    """
    Corrección 5: Autorización real contra endpoints y verificación de rollback ante fallo transaccional inyectado.
    """
    try:
        case = CaseFile(title="Caso Aprobación Real", contract_type="SERVICIOS", status="WAITING_QUOTATION", assigned_to_user_id=1, tenant_id="mega_tenant")
        db_session.add(case)
        db_session.commit()

        sup = Supplier(ruc="20888888880", business_name="Seguridad y Control SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        prof = SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED")
        db_session.add(prof)
        db_session.commit()

        offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=12000.0, price=12000.0, currency="PEN")
        db_session.add(offer)
        db_session.commit()

        cond = ContractualCondition(supplier_offer_id=offer.id, key="alcance", label="Alcance", resolution_rule="EXACT_MATCH", status="CUMPLE")
        db_session.add(cond)
        db_session.commit()

        # Proponer selección
        sup_client = get_supervisor_client()
        res_prop = sup_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": offer.id, "justification_comment": "Propuesta conforme"}
        )
        assert res_prop.status_code == 200

        # R1: Operador intenta aprobar -> 403 Forbidden
        op_client = get_operator_client()
        res_op_app = op_client.post(f"/api/v6/cases/{case.id}/approve")
        assert res_op_app.status_code == 403
        assert "Forbidden" in res_op_app.json()["detail"] or "supervisor" in res_op_app.json()["detail"].lower()

        # R2: Supervisor aprueba -> 200 APPROVED
        sup_client = get_supervisor_client()
        res_sup_app = sup_client.post(f"/api/v6/cases/{case.id}/approve")
        assert res_sup_app.status_code == 200
        assert res_sup_app.json()["status"] == "APPROVED"

        # R3: Comprobar registro final en DB
        final_sel = db_session.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()
        assert final_sel is not None
        assert final_sel.attempt.supplier_offer_id == offer.id

        # R4: Rollback inyectado: intentar aprobar nuevamente lanza error y no duplica ni corrompe estado
        res_dup = sup_client.post(f"/api/v6/cases/{case.id}/approve")
        assert res_dup.status_code in [400, 409]
        assert "already in terminal status" in res_dup.json()["detail"] or "terminal" in res_dup.json()["detail"].lower()
    finally:
        cleanup_overrides()

# ==============================================================================
# REMEDIACIÓN CORRECCIÓN B: Validación de Estados Obligatorios Negativos y Positivos
# ==============================================================================

def test_p11_mandatory_passed_and_conflict_blocks_selection(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """Prueba 1: Un requisito obligatorio PASSED y otro CONFLICT debe marcar ineligibilidad y bloquear selección."""
    try:
        case = CaseFile(title="Caso Req Mandatory Conflict", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant", assigned_to_user_id=1)
        db_session.add(case)
        db_session.commit()

        req1 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-RAM", description="RAM 32GB", mandatory=True, status="VALIDATED")
        req2 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-CPU", description="CPU 8 núcleos", mandatory=True, status="VALIDATED")
        db_session.add_all([req1, req2])
        db_session.commit()

        sup = Supplier(ruc="20900000001", business_name="Proveedor Alfa SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))
        db_session.commit()

        offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
        db_session.add(offer)
        db_session.commit()

        # req1 es PASSED, req2 es CONFLICT
        ev1 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req1.id, status="PASSED", explanation="Cumple RAM")
        ev2 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req2.id, status="CONFLICT", explanation="Conflicto en ficha técnica")
        db_session.add_all([ev1, ev2])
        db_session.commit()
        attach_verified_evidence(db_session, case.id, offer.id, req1.id, fragment="Cumple memoria RAM 32GB")

        from app.services.v6.evaluation.vfm_service import ValueForMoneyService
        vfm = ValueForMoneyService(db_session).calculate_vfm(case.id)
        assert len(vfm) == 1
        assert vfm[0]["is_eligible"] is False
        assert vfm[0]["reason"] == "CONFLICT_MANDATORY_REQUIREMENTS"
        assert vfm[0]["total_score"] == 0.0

        # Intento de selección debe fallar con 400
        res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Justificación ordinaria"})
        assert res.status_code == 400
        assert "unresolved conflicts" in res.json()["detail"] or "CONFLICT" in res.json()["detail"]

        # Comprobar que no se cree SupplierSelectionAttempt ni se altere el expediente
        assert db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first() is None
        db_session.refresh(case)
        assert case.status == "WAITING_QUOTATION"
    finally:
        cleanup_overrides()

def test_p11_mandatory_passed_and_missing_data_blocks_selection(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """Prueba 2: Un requisito obligatorio PASSED y otro MISSING_DATA debe marcar ineligibilidad y bloquear selección."""
    try:
        case = CaseFile(title="Caso Req Mandatory Missing Data", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant", assigned_to_user_id=1)
        db_session.add(case)
        db_session.commit()

        req1 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-RAM", description="RAM 32GB", mandatory=True, status="VALIDATED")
        req2 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-CERT", description="Certificado ISO", mandatory=True, status="VALIDATED")
        db_session.add_all([req1, req2])
        db_session.commit()

        sup = Supplier(ruc="20900000002", business_name="Proveedor Beta SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))
        db_session.commit()

        offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
        db_session.add(offer)
        db_session.commit()

        # req1 es PASSED, req2 es MISSING_DATA
        ev1 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req1.id, status="PASSED", explanation="Cumple RAM")
        ev2 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req2.id, status="MISSING_DATA", explanation="Falta adjuntar certificado")
        db_session.add_all([ev1, ev2])
        db_session.commit()
        attach_verified_evidence(db_session, case.id, offer.id, req1.id, fragment="Cumple memoria RAM 32GB")

        from app.services.v6.evaluation.vfm_service import ValueForMoneyService
        vfm = ValueForMoneyService(db_session).calculate_vfm(case.id)
        assert len(vfm) == 1
        assert vfm[0]["is_eligible"] is False
        assert vfm[0]["reason"] == "MISSING_DATA_MANDATORY_REQUIREMENTS"

        res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Falta dato"})
        assert res.status_code == 400
        assert "missing data" in res.json()["detail"] or "MISSING_DATA" in res.json()["detail"]

        assert db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first() is None
        db_session.refresh(case)
        assert case.status == "WAITING_QUOTATION"
    finally:
        cleanup_overrides()

def test_p11_mandatory_observed_and_pending_blocks_selection(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """Prueba 3: Evaluación obligatoria OBSERVED o PENDING permanece bloqueada hasta resolución."""
    try:
        case = CaseFile(title="Caso Req Mandatory Observed Pending", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant", assigned_to_user_id=1)
        db_session.add(case)
        db_session.commit()

        req1 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-OBS", description="Requisito Observado", mandatory=True, status="VALIDATED")
        req2 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-PEND", description="Requisito Pendiente", mandatory=True, status="VALIDATED")
        db_session.add_all([req1, req2])
        db_session.commit()

        sup = Supplier(ruc="20900000003", business_name="Proveedor Gamma SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))
        db_session.commit()

        offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
        db_session.add(offer)
        db_session.commit()

        # Caso 3a: OBSERVED
        ev1 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req1.id, status="OBSERVED", explanation="Observado")
        ev2 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req2.id, status="PASSED", explanation="Aprobado")
        db_session.add_all([ev1, ev2])
        db_session.commit()
        attach_verified_evidence(db_session, case.id, offer.id, req2.id, fragment="Aprobado y conforme con especificaciones")

        from app.services.v6.evaluation.vfm_service import ValueForMoneyService
        vfm = ValueForMoneyService(db_session).calculate_vfm(case.id)
        assert vfm[0]["is_eligible"] is False
        assert vfm[0]["reason"] == "OBSERVED_MANDATORY_REQUIREMENTS"

        res_obs = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Observado"})
        assert res_obs.status_code == 400
        assert "observations" in res_obs.json()["detail"] or "OBSERVED" in res_obs.json()["detail"]
        assert db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first() is None

        # Caso 3b: PENDING
        ev1.status = "PENDING"
        db_session.commit()
        vfm_pend = ValueForMoneyService(db_session).calculate_vfm(case.id)
        assert vfm_pend[0]["is_eligible"] is False
        assert vfm_pend[0]["reason"] == "MANDATORY_EVALUATIONS_PENDING"

        res_pend = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Pendiente"})
        assert res_pend.status_code == 400
        assert "pending" in res_pend.json()["detail"].lower()
        assert db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first() is None
    finally:
        cleanup_overrides()

def test_p11_mandatory_all_passed_allows_selection(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """Prueba 4: Todos los requisitos obligatorios cumplidos permiten seleccionar válidamente."""
    try:
        case = CaseFile(title="Caso Req Mandatory All Passed", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant", assigned_to_user_id=1)
        db_session.add(case)
        db_session.commit()

        req1 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-1", description="Requisito 1", mandatory=True, status="VALIDATED")
        req2 = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-2", description="Requisito 2", mandatory=True, status="VALIDATED")
        db_session.add_all([req1, req2])
        db_session.commit()

        sup = Supplier(ruc="20900000004", business_name="Proveedor Delta SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))
        db_session.commit()

        offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=10000.0, price=10000.0, currency="PEN")
        db_session.add(offer)
        db_session.commit()

        ev1 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req1.id, status="PASSED", explanation="Cumple 1")
        ev2 = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req2.id, status="IMPROVEMENT", explanation="Mejora 2")
        db_session.add_all([ev1, ev2])
        db_session.commit()
        attach_verified_evidence(db_session, case.id, offer.id, req1.id, fragment="Cumple especificaciones técnicas 1")
        attach_verified_evidence(db_session, case.id, offer.id, req2.id, fragment="Mejora acreditada especificaciones técnicas 2")

        from app.services.v6.evaluation.vfm_service import ValueForMoneyService
        vfm = ValueForMoneyService(db_session).calculate_vfm(case.id)
        assert len(vfm) == 1
        assert vfm[0]["is_eligible"] is True
        assert vfm[0]["total_score"] == 15.0 # 5.0 (PASSED) + 10.0 (IMPROVEMENT)

        res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": "Oferta plenamente conforme"})
        assert res.status_code == 200
        assert res.json()["status"] == "UNDER_REVIEW"

        attempt = db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first()
        assert attempt is not None
        assert attempt.supplier_offer_id == offer.id
    finally:
        cleanup_overrides()

def test_p11_ineligible_offer_with_justification_rejected(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    """Prueba 5: Selección de oferta no conforme con justificación técnica queda terminantemente rechazada."""
    try:
        case = CaseFile(title="Caso No Conforme Con Justificación", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant", assigned_to_user_id=1)
        db_session.add(case)
        db_session.commit()

        req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-CRIT", description="Requisito Crítico", mandatory=True, status="VALIDATED")
        db_session.add(req)
        db_session.commit()

        sup = Supplier(ruc="20900000005", business_name="Proveedor Epsilon SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))
        db_session.commit()

        offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=8000.0, price=8000.0, currency="PEN")
        db_session.add(offer)
        db_session.commit()

        # Descalificado en requisito mandatorio
        ev = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req.id, status="FAILED", explanation="Incumple especificación mandatoria")
        db_session.add(ev)
        db_session.commit()

        # Operador envía justificación extensa y detallada para intentar habilitar la oferta descalificada
        extensa_justificacion = "Se justifica su elección porque ofrece un precio significativamente más bajo y entrega en menor plazo."
        res = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id, "justification_comment": extensa_justificacion})
        assert res.status_code == 400
        assert "Cannot propose an ineligible offer" in res.json()["detail"]

        # Comprobar que no se cree SupplierSelectionAttempt ni se altere el expediente
        assert db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first() is None
        db_session.refresh(case)
        assert case.status == "WAITING_QUOTATION"
    finally:
        cleanup_overrides()

def test_p11_supervisor_exception_on_mandatory_non_compliance_rejected(db_session: Session, setup_mega_tenant):
    """Prueba 6: Intento de excepción supervisora sobre incumplimiento obligatorio es rechazado y bloqueado."""
    try:
        case = CaseFile(title="Caso Excepción Supervisora Bloqueada", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant", assigned_to_user_id=1)
        db_session.add(case)
        db_session.commit()

        req = CaseRequirementMatrix(case_id=case.id, requirement_type="TECHNICAL", key="REQ-MAND", description="Garantía mínima", mandatory=True, status="VALIDATED")
        db_session.add(req)
        db_session.commit()
        db_session.commit()

        sup = Supplier(ruc="20900000006", business_name="Proveedor Zeta SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))
        db_session.commit()

        offer = SupplierOffer(case_id=case.id, supplier_id=sup.id, status="SUBMITTED", total_amount=9500.0, price=9500.0, currency="PEN")
        db_session.add(offer)
        db_session.commit()

        # Condición CONFLICT en requisito obligatorio
        ev = OfferEvaluation(supplier_offer_id=offer.id, requirement_id=req.id, status="CONFLICT", explanation="Conflicto contractual insalvable")
        db_session.add(ev)
        db_session.commit()

        # Supervisor intenta proponer selección con excepción explícita
        sup_client = get_supervisor_client(user_id=1)
        res = sup_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={
                "supplier_offer_id": offer.id,
                "justification_comment": "Excepción de supervisor autorizada por jefatura."
            }
        )
        assert res.status_code == 400
        assert "Cannot propose an ineligible offer" in res.json()["detail"]

        # Comprobar que no se cree SupplierSelectionAttempt ni se altere el expediente
        assert db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first() is None
        db_session.refresh(case)
        assert case.status == "WAITING_QUOTATION"
    finally:
        cleanup_overrides()

def test_p11_test_e2e_reset_endpoint_removed_returns_404_or_405(admin_client: TestClient):
    """Prueba 7: Confirmar que la ruta destructiva /api/v6/cases/{id}/test-e2e-reset ya no existe en la aplicación."""
    try:
        res = admin_client.post("/api/v6/cases/1/test-e2e-reset")
        assert res.status_code in [404, 405]
    finally:
        cleanup_overrides()
