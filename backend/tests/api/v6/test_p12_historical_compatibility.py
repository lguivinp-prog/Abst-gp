import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, User, AuditLog, UploadedDocument
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal
from app.services.v6.evaluation.vfm_service import ValueForMoneyService
from app.api.auth import get_current_active_user, get_current_user
from app.main import app

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

def get_operator_client(user_id: int = 1):
    op_user = User(
        id=user_id,
        username=f"operator_{user_id}",
        role="OPERATOR",
        is_active=True,
        must_change_password=False,
        tenant_id="mega_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: op_user
    app.dependency_overrides[get_current_user] = lambda: op_user
    return TestClient(app)

def cleanup_overrides():
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# 1. EXPEDIENTE HISTÓRICO EXISTENTE CON DECISIÓN PASADA (INMUTABLE Y PRESERVADO)
# ==============================================================================
def test_historical_case_with_past_terminal_decision_preserved(db_session: Session, setup_mega_tenant):
    """
    Expediente histórico migrado (HISTORICAL_P11) con decisión terminal previa (APPROVED/SupplierSelectionFinal):
    Se conserva intacto, elegible en consulta VFM sin exigir retroactivamente trazabilidad documental P12.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Histórico Terminal P11",
            contract_type="BIENES",
            status="APPROVED",
            tenant_id="mega_tenant",
            traceability_regime="HISTORICAL_P11",
            assigned_to_user_id=1
        )
        db_session.add(case)
        db_session.commit()

        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description="Requisito Histórico Aprobado",
            mandatory=True,
            status="VALIDATED"
        )
        db_session.add(req)
        db_session.commit()

        sup = Supplier(ruc="20111111111", business_name="Proveedor Historico SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

        offer = SupplierOffer(
            case_id=case.id,
            supplier_id=sup.id,
            status="APPROVED",
            total_amount=30000.0,
            price=30000.0,
            currency="PEN"
        )
        db_session.add(offer)
        db_session.commit()

        # Evaluación histórica sin OfferRequirementEvidence
        eval_hist = OfferEvaluation(
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            status="PASSED",
            explanation="Evaluación histórica P11 sin evidencia vinculada",
            evaluation_confidence=0.9
        )
        db_session.add(eval_hist)

        # Decisión terminal previa registrada
        attempt_hist = SupplierSelectionAttempt(
            case_id=case.id,
            supplier_offer_id=offer.id,
            status="APPROVED",
            justification_comment="Selección histórica formalmente aprobada en P11",
            selected_by=1
        )
        db_session.add(attempt_hist)
        db_session.commit()

        final_sel = SupplierSelectionFinal(
            case_id=case.id,
            attempt_id=attempt_hist.id
        )
        db_session.add(final_sel)
        db_session.commit()

        # Consultar VFM: debe preservar la elegibilidad histórica
        vfm_service = ValueForMoneyService(db_session)
        vfm = vfm_service.calculate_vfm(case.id)
        assert len(vfm) == 1
        assert vfm[0]["is_eligible"] is True
        assert vfm[0]["supplier_offer_id"] == offer.id

        # Comprobar inmutabilidad: no se permite proponer nueva selección en caso aprobado (409 Conflict)
        res_conflict = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id})
        assert res_conflict.status_code == 409
    finally:
        cleanup_overrides()


# ==============================================================================
# 2. EXPEDIENTE HISTÓRICO CON NUEVA OFERTA (EXIGE TRAZABILIDAD P12)
# ==============================================================================
def test_historical_case_with_new_offer_requires_strict_traceability(db_session: Session, setup_mega_tenant):
    """
    Expediente con régimen HISTORICAL_P11 pero activo (sin decisión terminal previa):
    Cualquier nueva oferta incorporada DEBE satisfacer la trazabilidad documental estricta.
    Si la nueva oferta carece de evidencia verificada, resulta inelegible (MISSING_DOCUMENTARY_EVIDENCE).
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Histórico Activo",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            tenant_id="mega_tenant",
            traceability_regime="HISTORICAL_P11",
            assigned_to_user_id=1
        )
        db_session.add(case)
        db_session.commit()

        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description="Garantía técnica mínima 24 meses",
            mandatory=True,
            status="VALIDATED"
        )
        db_session.add(req)
        db_session.commit()

        sup = Supplier(ruc="20222222222", business_name="Proveedor Nuevo en Caso Historico SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

        # Nueva oferta incorporada
        offer = SupplierOffer(
            case_id=case.id,
            supplier_id=sup.id,
            status="SUBMITTED",
            total_amount=45000.0,
            price=45000.0,
            currency="PEN"
        )
        db_session.add(offer)
        db_session.commit()

        # Evaluación con PASSED pero SIN evidencia vinculada
        eval_new = OfferEvaluation(
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            status="PASSED",
            explanation="Cumple pero carece de documento de respaldo",
            evaluation_confidence=0.9
        )
        db_session.add(eval_new)
        db_session.commit()

        # Al calcular VFM, no opera la exención histórica porque no es decisión terminal previa
        vfm_service = ValueForMoneyService(db_session)
        vfm = vfm_service.calculate_vfm(case.id)
        assert len(vfm) == 1
        assert vfm[0]["is_eligible"] is False
        assert vfm[0]["reason"] in ("MISSING_DOCUMENTARY_EVIDENCE", "MISSING_DATA_MANDATORY_REQUIREMENTS")
    finally:
        cleanup_overrides()


# ==============================================================================
# 3. EXPEDIENTE HISTÓRICO CON NUEVA PROPUESTA DE SELECCIÓN (BLOQUEADA SIN EVIDENCIA)
# ==============================================================================
def test_historical_case_with_new_selection_proposal_blocked_without_evidence(db_session: Session, setup_mega_tenant):
    """
    En un expediente HISTORICAL_P11 activo, proponer una selección sobre una oferta
    sin respaldo documental verificado es terminantemente rechazado (400 Bad Request).
    HISTORICAL_P11 no funciona como exención para nuevas decisiones de selección.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Histórico para Selección",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            tenant_id="mega_tenant",
            traceability_regime="HISTORICAL_P11",
            assigned_to_user_id=1
        )
        db_session.add(case)
        db_session.commit()

        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description="Requisito Técnico Mandatorio",
            mandatory=True,
            status="VALIDATED"
        )
        db_session.add(req)
        db_session.commit()

        sup = Supplier(ruc="20333333333", business_name="Proveedor Seleccion Historico SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

        offer = SupplierOffer(
            case_id=case.id,
            supplier_id=sup.id,
            status="SUBMITTED",
            total_amount=50000.0,
            price=50000.0,
            currency="PEN"
        )
        db_session.add(offer)
        db_session.commit()

        # Evaluación sin evidencia documental
        eval_req = OfferEvaluation(
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            status="PASSED",
            explanation="Pretende aprobarse sin evidencia documental",
            evaluation_confidence=0.9
        )
        db_session.add(eval_req)
        db_session.commit()

        # Intento de selección debe ser rechazado
        res = admin_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": offer.id, "justification_comment": "Intento de evadir P12 con régimen histórico"}
        )
        assert res.status_code == 400
        assert "Cannot propose an ineligible offer" in res.json()["detail"]
        assert db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first() is None
    finally:
        cleanup_overrides()


# ==============================================================================
# 4. EXPEDIENTE NUEVO P12 SIN EVIDENCIA VINCULADA (RECHAZADO)
# ==============================================================================
def test_new_p12_case_without_evidence_rejected(db_session: Session, setup_mega_tenant):
    """
    Expediente nuevo bajo régimen P12_STRICT:
    Una evaluación PASSED sin OfferRequirementEvidence vinculada con estado VERIFIED
    convierte la oferta en inelegible y bloquea la selección.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Nuevo P12 Estricto",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            tenant_id="mega_tenant",
            traceability_regime="P12_STRICT",
            assigned_to_user_id=1
        )
        db_session.add(case)
        db_session.commit()

        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description="Certificación ISO 9001",
            mandatory=True,
            status="VALIDATED"
        )
        db_session.add(req)
        db_session.commit()

        sup = Supplier(ruc="20444444444", business_name="Proveedor P12 Sin Evidencia SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

        offer = SupplierOffer(
            case_id=case.id,
            supplier_id=sup.id,
            status="SUBMITTED",
            total_amount=60000.0,
            price=60000.0,
            currency="PEN"
        )
        db_session.add(offer)
        db_session.commit()

        eval_untraced = OfferEvaluation(
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            status="PASSED",
            explanation="Aprobado en base de datos pero sin documento",
            evaluation_confidence=0.95
        )
        db_session.add(eval_untraced)
        db_session.commit()

        vfm_service = ValueForMoneyService(db_session)
        vfm = vfm_service.calculate_vfm(case.id)
        assert len(vfm) == 1
        assert vfm[0]["is_eligible"] is False
        assert vfm[0]["reason"] in ("MISSING_DOCUMENTARY_EVIDENCE", "MISSING_DATA_MANDATORY_REQUIREMENTS")

        sel_res = admin_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": offer.id}
        )
        assert sel_res.status_code == 400
        assert "Cannot propose an ineligible offer" in sel_res.json()["detail"]
    finally:
        cleanup_overrides()


# ==============================================================================
# 5. EXPEDIENTE NUEVO P12 CON EVIDENCIA Y CUMPLIMIENTO ACREDITADOS (ACEPTADO)
# ==============================================================================
def test_new_p12_case_with_verified_evidence_and_compliance_accepted(db_session: Session, setup_mega_tenant):
    """
    Expediente nuevo bajo régimen P12_STRICT:
    Con documento real, fragmento de oferta conforme, evidencia con estado VERIFIED y evaluación PASSED:
    La oferta es plenamente elegible y la propuesta de selección es aceptada (UNDER_REVIEW).
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Nuevo P12 Conforme",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            tenant_id="mega_tenant",
            traceability_regime="P12_STRICT",
            assigned_to_user_id=1
        )
        db_session.add(case)
        db_session.commit()

        doc = UploadedDocument(
            case_id=case.id,
            document_type="quotation",
            original_filename="propuesta_p12_valida.pdf",
            stored_path="/tmp/propuesta_p12_valida.pdf",
            mime_type="application/pdf",
            processing_status="completed"
        )
        db_session.add(doc)
        db_session.commit()

        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description="Garantía técnica mínima de 24 meses",
            mandatory=True,
            status="VALIDATED"
        )
        db_session.add(req)
        db_session.commit()

        sup = Supplier(ruc="20555555555", business_name="Proveedor P12 Conforme SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

        offer = SupplierOffer(
            case_id=case.id,
            supplier_id=sup.id,
            status="SUBMITTED",
            total_amount=70000.0,
            price=70000.0,
            currency="PEN"
        )
        db_session.add(offer)
        db_session.commit()

        oe = OfferEvidence(
            supplier_offer_id=offer.id,
            document_id=doc.id,
            document_type="FICHA_TECNICA",
            fragment="Garantía de fábrica extendida de 36 meses con repuestos.",
            confidence=0.98,
            page=3
        )
        db_session.add(oe)
        db_session.commit()

        ore = OfferRequirementEvidence(
            case_id=case.id,
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            offer_evidence_id=oe.id,
            document_id=doc.id,
            source_document="propuesta_p12_valida.pdf",
            page=3,
            fragment="Garantía de fábrica extendida de 36 meses con repuestos.",
            verification_status="VERIFIED",
            verified_by=1,
            verified_at=datetime.now(timezone.utc)
        )
        db_session.add(ore)
        db_session.commit()

        eval_passed = OfferEvaluation(
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            status="PASSED",
            explanation="Garantía de 36 meses supera el mínimo requerido de 24 meses",
            evaluation_confidence=0.98,
            validated_by=1,
            validated_at=datetime.now(timezone.utc)
        )
        db_session.add(eval_passed)
        db_session.commit()

        vfm_service = ValueForMoneyService(db_session)
        vfm = vfm_service.calculate_vfm(case.id)
        assert len(vfm) == 1
        assert vfm[0]["is_eligible"] is True
        assert vfm[0]["supplier_offer_id"] == offer.id

        sel_res = admin_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": offer.id, "justification_comment": "Propuesta plenamente respaldada con evidencia documental"}
        )
        assert sel_res.status_code == 200
        assert sel_res.json()["status"] == "UNDER_REVIEW"

        attempt = db_session.query(SupplierSelectionAttempt).filter_by(case_id=case.id).first()
        assert attempt is not None
        assert attempt.supplier_offer_id == offer.id
    finally:
        cleanup_overrides()


# ==============================================================================
# 6. PRUEBA OBLIGATORIA DEFECTO 1:
#    REQUISITO GARANTÍA 36 MESES; OFERTA 12 MESES; EVIDENCIA VERIFICADA.
#    EL RESULTADO NO PUEDE SER PASSED NI IMPROVEMENT.
# ==============================================================================
def test_mandatory_defect_1_warranty_36m_offered_12m_verified_cannot_be_passed(db_session: Session, setup_mega_tenant):
    """
    Prueba obligatoria:
    Requisito de garantía mínima 36 meses.
    Oferta documentada de 12 meses.
    Evidencia auténtica y verificada (VERIFIED).
    
    El resultado del contraste técnico NO PUEDE SER 'PASSED' ni 'IMPROVEMENT'.
    Debe ser 'FAILED'.
    Tampoco se debe permitir al operador forzar 'PASSED' mediante actualización manual.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Defecto 1 Contraste Técnico",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            tenant_id="mega_tenant",
            traceability_regime="P12_STRICT",
            assigned_to_user_id=1
        )
        db_session.add(case)
        db_session.commit()

        doc = UploadedDocument(
            case_id=case.id,
            document_type="quotation",
            original_filename="ficha_garantia_12m.pdf",
            stored_path="/tmp/ficha_garantia_12m.pdf",
            mime_type="application/pdf",
            processing_status="completed"
        )
        db_session.add(doc)
        db_session.commit()

        # Requisito mandatorio de garantía mínima 36 meses
        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description="Garantía mínima de fábrica 36 meses",
            value="36 meses",
            mandatory=True,
            status="VALIDATED"
        )
        db_session.add(req)
        db_session.commit()

        sup = Supplier(ruc="20666666666", business_name="Proveedor Oferta Corta SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

        offer = SupplierOffer(
            case_id=case.id,
            supplier_id=sup.id,
            status="SUBMITTED",
            total_amount=35000.0,
            price=35000.0,
            currency="PEN"
        )
        db_session.add(offer)
        db_session.commit()

        # Fragmento real de oferta: ofrece únicamente 12 meses
        fragment_12m = "Garantía estándar de fábrica: 12 meses para componentes electrónicos."
        oe = OfferEvidence(
            supplier_offer_id=offer.id,
            document_id=doc.id,
            document_type="FICHA_TECNICA",
            fragment=fragment_12m,
            confidence=0.99,
            page=2
        )
        db_session.add(oe)
        db_session.commit()

        # Evidencia auténtica y verificada documentalmente (el documento y fragmento son auténticos)
        ore = OfferRequirementEvidence(
            case_id=case.id,
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            offer_evidence_id=oe.id,
            document_id=doc.id,
            source_document="ficha_garantia_12m.pdf",
            page=2,
            fragment=fragment_12m,
            verification_status="VERIFIED", # VERIFICADO DOCUMENTALMENTE
            verified_by=1,
            verified_at=datetime.now(timezone.utc)
        )
        db_session.add(ore)
        db_session.commit()

        # 1. Ejecutar evaluación técnica formal a través del endpoint de evaluación
        eval_run_res = admin_client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
        assert eval_run_res.status_code == 200
        evals = eval_run_res.json()
        assert len(evals) == 1

        ev_result = evals[0]
        # REGLA FUNDAMENTAL: A pesar de que la evidencia esté VERIFIED, el resultado técnico NO PUEDE SER PASSED
        assert ev_result["status"] != "PASSED", "Una evidencia verificada que ofrece 12m cuando se exigen 36m NUNCA puede producir PASSED"
        assert ev_result["status"] != "IMPROVEMENT", "Una oferta que ofrece menos de lo requerido no puede producir IMPROVEMENT"
        assert ev_result["status"] == "FAILED"
        assert "Incumplimiento técnico" in ev_result["explanation"]
        assert "36 meses" in ev_result["explanation"] and "12 meses" in ev_result["explanation"]

        # 2. Comprobar que el usuario operador NO puede ignorar la contradicción forzando 'PASSED'
        update_res = admin_client.put(
            f"/api/v6/cases/{case.id}/evaluations/{ev_result['id']}",
            json={
                "status": "PASSED",
                "explanation": "Intento de ignorar la contradicción documental"
            }
        )
        assert update_res.status_code == 400
        detail_msg = update_res.json()["detail"].lower()
        assert "non-compliance" in detail_msg or "incumplimiento" in detail_msg

        # 3. La oferta debe quedar descalificada para selección (400)
        sel_attempt = admin_client.post(f"/api/v6/cases/{case.id}/selection", json={"supplier_offer_id": offer.id})
        assert sel_attempt.status_code == 400
        assert "Cannot propose an ineligible offer" in sel_attempt.json()["detail"]
    finally:
        cleanup_overrides()


# ==============================================================================
# 7. COMPARACIÓN INCONCLUSA CONSERVA ESTADO REQUIERE_REVISION
# ==============================================================================
def test_inconclusive_comparison_yields_requiere_revision(db_session: Session, setup_mega_tenant):
    """
    Cuando la evidencia está verificada pero los fragmentos no permiten una comparación técnica
    concluyente automática, el motor conserva el estado REQUIERE_REVISION exigiendo
    una decisión humana explícita, motivada y auditada.
    """
    admin_client = get_admin_client()
    try:
        case = CaseFile(
            title="Expediente Inconcluso",
            contract_type="BIENES",
            status="WAITING_QUOTATION",
            tenant_id="mega_tenant",
            traceability_regime="P12_STRICT",
            assigned_to_user_id=1
        )
        db_session.add(case)
        db_session.commit()

        doc = UploadedDocument(
            case_id=case.id,
            document_type="quotation",
            original_filename="propuesta_inconclusa.pdf",
            stored_path="/tmp/propuesta_inconclusa.pdf",
            mime_type="application/pdf",
            processing_status="completed"
        )
        db_session.add(doc)
        db_session.commit()

        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description="Capacidad de almacenamiento 10TB con redundancia RAID",
            mandatory=True,
            status="VALIDATED"
        )
        db_session.add(req)
        db_session.commit()

        sup = Supplier(ruc="20777777777", business_name="Proveedor Almacenamiento SAC", tenant_id="mega_tenant")
        db_session.add(sup)
        db_session.commit()
        db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

        offer = SupplierOffer(
            case_id=case.id,
            supplier_id=sup.id,
            status="SUBMITTED",
            total_amount=25000.0,
            price=25000.0,
            currency="PEN"
        )
        db_session.add(offer)
        db_session.commit()

        oe = OfferEvidence(
            supplier_offer_id=offer.id,
            document_id=doc.id,
            document_type="FICHA_TECNICA",
            fragment="Sistema de almacenamiento de alta densidad para centros de cómputo.",
            confidence=0.8,
            page=1
        )
        db_session.add(oe)
        db_session.commit()

        ore = OfferRequirementEvidence(
            case_id=case.id,
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            offer_evidence_id=oe.id,
            document_id=doc.id,
            source_document="propuesta_inconclusa.pdf",
            page=1,
            fragment="Sistema de almacenamiento de alta densidad para centros de cómputo.",
            verification_status="VERIFIED",
            verified_by=1,
            verified_at=datetime.now(timezone.utc)
        )
        db_session.add(ore)
        db_session.commit()

        # Ejecutar evaluación automática
        eval_res = admin_client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
        assert eval_res.status_code == 200
        ev = eval_res.json()[0]
        # Al no haber valores concluyentes, debe permanecer en REQUIERE_REVISION
        assert ev["status"] == "REQUIERE_REVISION"
        assert "revisión técnica humana" in ev["explanation"]

        # El operador humano decide validar técnicamente con fundamentación explícita
        human_update = admin_client.put(
            f"/api/v6/cases/{case.id}/evaluations/{ev['id']}",
            json={
                "status": "PASSED",
                "explanation": "Revisión técnica de ingeniería confirma que la configuración de alta densidad incluye 12TB netos con RAID 5."
            }
        )
        assert human_update.status_code == 200
        updated = human_update.json()
        assert updated["status"] == "PASSED"
        assert updated["validated_by"] == 2 # Admin user ID
        assert updated["validated_at"] is not None

        # Comprobar que se registró en auditoría
        audit = db_session.query(AuditLog).filter_by(
            action="UPDATE_EVALUATION",
            entity_type="OfferEvaluation",
            entity_id=str(ev["id"])
        ).first()
        assert audit is not None
        import json
        audit_details = json.loads(audit.details)
        assert "Revisión técnica de ingeniería confirma" in audit_details.get("reason", "")
    finally:
        cleanup_overrides()
