import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, User, UploadedDocument
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.offer_evaluation import OfferEvaluation
from app.services.v6.engines.improvement_engine import DeterministicImprovementEngine
from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
from app.services.v6.evaluation.vfm_service import ValueForMoneyService
from app.services.v6.selection.selection_service import SelectionService


# ==============================================================================
# 1. PRUEBAS DIRECTAS DEL MOTOR: CASO A, CASO B Y REGRESIONES DE CONTRASTE
# ==============================================================================

def test_engine_caso_a_warranty_vs_support_false_positive():
    """
    Caso A:
    Requisito: «Garantía mínima de fábrica 36 meses».
    Evidencia: «La licencia de soporte tiene 36 meses. La garantía del equipo es de 12 meses».
    Resultado esperado: FAILED (garantía 12m < 36m requeridos, no PASSED por los 36m de soporte).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima de fábrica 36 meses",
        req_value=None,
        fragments=["La licencia de soporte tiene 36 meses. La garantía del equipo es de 12 meses"]
    )
    assert res["status"] == "FAILED", f"Caso A debe ser FAILED, obtuvo: {res}"
    assert "garantía" in res["explanation"].lower()
    assert "12 meses" in res["explanation"]
    assert res["confidence"] == 1.0


def test_engine_caso_b_installation_vs_delivery_false_positive():
    """
    Caso B:
    Requisito: «Entrega en 30 días e instalación en 15 días».
    Evidencia: «Instalación en 15 días, entrega final en 60 días».
    Resultado esperado: FAILED (entrega 60d > 30d requeridos, no IMPROVEMENT por instalación de 15d).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Entrega en 30 días e instalación en 15 días",
        req_value=None,
        fragments=["Instalación en 15 días, entrega final en 60 días"]
    )
    assert res["status"] == "FAILED", f"Caso B debe ser FAILED, obtuvo: {res}"
    assert "entrega" in res["explanation"].lower()
    assert "60" in res["explanation"]
    assert res["confidence"] == 1.0


def test_engine_caso_c_unpunctuated_multi_attribute_false_positive():
    """
    Caso C (P12 Gate Final):
    Requisito: «Garantía mínima 36 meses».
    Evidencia: «Licencia soporte 36 meses garantía 12 meses».
    Resultado incorrecto previo: PASSED (asociaba 36 meses de soporte a garantía).
    Resultado esperado: FAILED (garantía ofrecida 12m < 36m requeridos).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses",
        req_value=None,
        fragments=["Licencia soporte 36 meses garantía 12 meses"]
    )
    assert res["status"] == "FAILED", f"Caso C debe ser FAILED, obtuvo: {res}"
    assert "garantía" in res["explanation"].lower()
    assert "12 meses" in res["explanation"]
    assert res["confidence"] == 1.0


def test_engine_caso_d_explicit_negation_false_positive():
    """
    Caso D (P12 Gate Final):
    Requisito: «Garantía mínima 36 meses».
    Evidencia: «No incluye garantía de 36 meses».
    Resultado incorrecto previo: PASSED (ignoraba negación «No incluye»).
    Resultado esperado: FAILED (negación inequívoca del atributo requerido).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses",
        req_value=None,
        fragments=["No incluye garantía de 36 meses"]
    )
    assert res["status"] == "FAILED", f"Caso D debe ser FAILED, obtuvo: {res}"
    assert "garantía" in res["explanation"].lower()
    assert "negación" in res["explanation"].lower() or "exclusión" in res["explanation"].lower()
    assert res["confidence"] == 1.0


def test_engine_caso_e_unpunctuated_multi_prestation_delivery_false_positive():
    """
    Caso E (P12 Gate Final):
    Requisito: «Entrega 30 días e instalación 15 días».
    Evidencia: «Instalación 15 días entrega 60 días».
    Resultado incorrecto previo: IMPROVEMENT (asignaba 15 días a entrega e instalación).
    Resultado esperado: FAILED (entrega ofrecida 60d excede plazo máximo de 30d).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Entrega 30 días e instalación 15 días",
        req_value=None,
        fragments=["Instalación 15 días entrega 60 días"]
    )
    assert res["status"] == "FAILED", f"Caso E debe ser FAILED, obtuvo: {res}"
    assert "entrega" in res["explanation"].lower()
    assert "60" in res["explanation"]
    assert res["confidence"] == 1.0


def test_engine_negation_variants():
    """
    Detección conservadora de formulaciones de negación explícita frente a garantía requerida:
    - «Sin garantía de fábrica» => FAILED
    - «No ofrece garantía alguna» => FAILED
    - «No garantiza repuestos» => FAILED
    - «Garantía excluida de la propuesta» => FAILED
    - «Garantía: no aplica» => FAILED
    - «Garantía del equipo no menor a 36 meses» => PASSED (cuantificador positivo, no negación)
    """
    engine = DeterministicImprovementEngine()
    assert engine.contrast_technical_compliance("Garantía mínima 36 meses", None, ["Sin garantía de fábrica"])["status"] == "FAILED"
    assert engine.contrast_technical_compliance("Garantía mínima 36 meses", None, ["No ofrece garantía alguna"])["status"] == "FAILED"
    assert engine.contrast_technical_compliance("Garantía mínima 36 meses", None, ["No garantiza repuestos ni equipos"])["status"] == "FAILED"
    assert engine.contrast_technical_compliance("Garantía mínima 36 meses", None, ["Garantía excluida de la propuesta"])["status"] == "FAILED"
    assert engine.contrast_technical_compliance("Garantía mínima 36 meses", None, ["Garantía: no aplica"])["status"] == "FAILED"
    assert engine.contrast_technical_compliance("Garantía mínima 36 meses", None, ["Garantía del equipo no menor a 36 meses"])["status"] == "PASSED"


def test_engine_conflation_single_metric_multiple_attributes():
    """
    Regla 3: Prohibido aplicar indiscriminadamente un único valor numérico a varias prestaciones.
    Requisito: «Garantía mínima 36 meses y soporte de 24 meses».
    Evidencia: «Garantía y soporte técnico de 36 meses».
    Resultado esperado: REQUIERE_REVISION (asociación no inequívoca entre atributo y cantidad).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses y soporte de 24 meses",
        req_value=None,
        fragments=["Garantía y soporte técnico de 36 meses"]
    )
    assert res["status"] == "REQUIERE_REVISION"
    assert res["confidence"] == 0.5



def test_engine_warranty_passes_but_support_fails():
    """
    Escenario: La garantía cumple pero el soporte no.
    Requisito: «Garantía mínima 36 meses y soporte de 24 meses».
    Evidencia: «Garantía de 36 meses y soporte de 12 meses».
    Resultado esperado: FAILED (soporte 12m < 24m).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses y soporte de 24 meses",
        req_value=None,
        fragments=["Garantía de 36 meses y soporte técnico de 12 meses"]
    )
    assert res["status"] == "FAILED"
    assert "soporte" in res["explanation"].lower()
    assert "12 meses" in res["explanation"]
    assert res["confidence"] == 1.0


def test_engine_support_passes_but_warranty_fails():
    """
    Escenario: El soporte cumple pero la garantía no.
    Requisito: «Garantía mínima 36 meses y soporte de 24 meses».
    Evidencia: «Garantía de 12 meses y soporte de 24 meses».
    Resultado esperado: FAILED (garantía 12m < 36m).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses y soporte de 24 meses",
        req_value=None,
        fragments=["Garantía de 12 meses y soporte de 24 meses"]
    )
    assert res["status"] == "FAILED"
    assert "garantía" in res["explanation"].lower()
    assert "12 meses" in res["explanation"]
    assert res["confidence"] == 1.0


def test_engine_installation_improved_but_delivery_exceeds():
    """
    Escenario: La instalación es más rápida pero la entrega excede el máximo.
    Requisito: «Entrega en 30 días e instalación en 15 días».
    Evidencia: «Instalación en 10 días, entrega en 45 días».
    Resultado esperado: FAILED (entrega excede 30 días).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Entrega en 30 días e instalación en 15 días",
        req_value=None,
        fragments=["Instalación en 10 días, entrega en 45 días"]
    )
    assert res["status"] == "FAILED"
    assert "entrega" in res["explanation"].lower()
    assert "45" in res["explanation"]
    assert res["confidence"] == 1.0


def test_engine_contradictory_warranty_durations():
    """
    Escenario: Existen dos duraciones de garantía contradictorias.
    Requisito: «Garantía mínima 36 meses».
    Evidencia: «Garantía de 36 meses en hoja 1, pero la garantía del fabricante es de 12 meses».
    Resultado esperado: REQUIERE_REVISION (no concluyente por contradicción interna).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses",
        req_value=None,
        fragments=["Garantía de 36 meses en hoja 1, pero la garantía del fabricante es de 12 meses"]
    )
    assert res["status"] == "REQUIERE_REVISION"
    assert "contradictorios" in res["explanation"].lower() or "contradicción" in res["explanation"].lower()
    assert res["confidence"] == 0.5


def test_engine_ambiguous_attribute_unidentifiable():
    """
    Escenario: El texto no permite identificar inequívocamente el atributo.
    Requisito: «Garantía mínima de fábrica 36 meses».
    Evidencia: «El plazo general del contrato es de 36 meses».
    Resultado esperado: REQUIERE_REVISION (no atribuible inequívocamente a garantía).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima de fábrica 36 meses",
        req_value=None,
        fragments=["El plazo general del contrato es de 36 meses"]
    )
    assert res["status"] == "REQUIERE_REVISION"
    assert "garantía" in res["explanation"].lower()
    assert res["confidence"] == 0.5


def test_engine_unequivocal_passed():
    """
    Escenario: Comparación inequívoca que sí permite PASSED.
    Requisito: «Garantía mínima de 36 meses».
    Evidencia: «Garantía del equipo de 36 meses».
    Resultado esperado: PASSED.
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima de 36 meses",
        req_value=None,
        fragments=["Garantía del equipo de 36 meses"]
    )
    assert res["status"] == "PASSED"
    assert res["confidence"] == 1.0


def test_engine_unequivocal_improvement():
    """
    Escenario: Comparación inequívoca que sí permite IMPROVEMENT.
    Requisito: «Garantía mínima de 24 meses».
    Evidencia: «Garantía del equipo de 36 meses».
    Resultado esperado: IMPROVEMENT.
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima de 24 meses",
        req_value=None,
        fragments=["Garantía del equipo de 36 meses"]
    )
    assert res["status"] == "IMPROVEMENT"
    assert res["confidence"] == 1.0


def test_engine_unequivocal_failed():
    """
    Escenario: Comparación inequívoca que sí permite FAILED.
    Requisito: «Plazo de entrega máximo 30 días».
    Evidencia: «Plazo de entrega de 45 días».
    Resultado esperado: FAILED.
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Plazo de entrega máximo 30 días",
        req_value=None,
        fragments=["Plazo de entrega de 45 días"]
    )
    assert res["status"] == "FAILED"
    assert res["confidence"] == 1.0


# ==============================================================================
# 2. PRUEBAS INTEGRALES CON OfferEvaluationService, VFM Y SELECTION
# ==============================================================================

def test_service_caso_a_blocks_selection_and_manual_positive_override(db_session: Session, setup_mega_tenant):
    """
    Ejecución del Caso A a través de OfferEvaluationService y VFM:
    - Requisito: Garantía mínima de fábrica 36 meses.
    - Evidencia: «La licencia de soporte tiene 36 meses. La garantía del equipo es de 12 meses».
    - La reevaluación automática produce FAILED.
    - La validación manual positiva (PASSED/IMPROVEMENT) debe ser BLOQUEADA con ValueError.
    - VFM marca la oferta como no elegible (FAILED_MANDATORY_REQUIREMENTS).
    - SelectionService rechaza la adjudicación.
    """
    case = CaseFile(
        title="Expediente Caso A Falso Positivo",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima de fábrica 36 meses",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999001", business_name="Proveedor Caso A SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=50000.0,
        price=50000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_a.pdf",
        stored_path="mock/caso_a.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="La licencia de soporte tiene 36 meses. La garantía del equipo es de 12 meses",
        confidence=0.95
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "FAILED"
    assert "12 meses" in eval_entry[0].explanation

    # Regla 7: Una contradicción/incumplimiento cierto debe impedir la validación manual positiva injustificada
    with pytest.raises(ValueError, match="Cannot assign positive compliance when documentary evidence demonstrates non-compliance"):
        eval_svc.update_evaluation(
            db=db_session,
            eval_id=eval_entry[0].id,
            new_status="PASSED",
            explanation="Validación manual indebida ignorando incumplimiento de garantía",
            user_id=1,
            tenant_id="mega_tenant"
        )

    # VFM debe declarar la oferta inelegible
    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is False
    assert vfm_res[0]["reason"] == "FAILED_MANDATORY_REQUIREMENTS"

    # SelectionService debe bloquear la selección de la oferta que falló el requisito obligatorio
    with pytest.raises(ValueError, match="Cannot propose an ineligible offer"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento indebido de adjudicar oferta no conforme",
            user_id=1,
            tenant_id="mega_tenant"
        )


def test_service_caso_b_blocks_selection_and_manual_positive_override(db_session: Session, setup_mega_tenant):
    """
    Ejecución del Caso B a través de OfferEvaluationService y VFM:
    - Requisito: «Entrega en 30 días e instalación en 15 días».
    - Evidencia: «Instalación en 15 días, entrega final en 60 días».
    - Reevaluación automática produce FAILED.
    - Validación manual positiva es BLOQUEADA.
    - VFM y Selección impiden selección de la oferta.
    """
    case = CaseFile(
        title="Expediente Caso B Falso Positivo",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Entrega en 30 días e instalación en 15 días",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999002", business_name="Proveedor Caso B SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=40000.0,
        price=40000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_b.pdf",
        stored_path="mock/caso_b.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Instalación en 15 días, entrega final en 60 días",
        confidence=0.90
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "FAILED"
    assert "60" in eval_entry[0].explanation

    with pytest.raises(ValueError, match="Cannot assign positive compliance when documentary evidence demonstrates non-compliance"):
        eval_svc.update_evaluation(
            db=db_session,
            eval_id=eval_entry[0].id,
            new_status="PASSED",
            explanation="Validación manual indebida ignorando exceso de plazo de entrega",
            user_id=1,
            tenant_id="mega_tenant"
        )

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is False
    assert vfm_res[0]["reason"] == "FAILED_MANDATORY_REQUIREMENTS"


def test_service_ambiguous_evidence_requires_human_justification_before_vfm(db_session: Session, setup_mega_tenant):
    """
    Escenario: Evidencia ambigua/no atribuible produce REQUIERE_REVISION.
    - VFM no habilita selección en REQUIERE_REVISION.
    - Un revisor humano calificado fundamenta la decisión y cambia a PASSED con auditoría.
    - Tras la validación justificada, VFM habilita la oferta.
    """
    case = CaseFile(
        title="Expediente Ambigüedad Técnica",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima de fábrica 36 meses",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999003", business_name="Proveedor Ambiguo SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=35000.0,
        price=35000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_ambigua.pdf",
        stored_path="mock/caso_ambiguo.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="El periodo de vigencia ofrecido es de 36 meses",
        confidence=0.80
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "REQUIERE_REVISION"

    # En REQUIERE_REVISION la oferta no es elegible en VFM
    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert vfm_res[0]["is_eligible"] is False
    assert vfm_res[0]["reason"] == "REQUIRES_REVIEW_MANDATORY_REQUIREMENTS"

    # Revisión humana fundamentada
    updated_eval = eval_svc.update_evaluation(
        db=db_session,
        eval_id=eval_entry[0].id,
        new_status="PASSED",
        explanation="Se revisó el folio 15 de la oferta técnica y se verificó que la vigencia de 36 meses corresponde íntegramente a la garantía de fábrica.",
        user_id=1,
        tenant_id="mega_tenant"
    )
    assert updated_eval.status == "PASSED"
    assert updated_eval.validated_by == 1

    # Ahora sí es elegible en VFM
    vfm_res_after = vfm_svc.calculate_vfm(case.id)
    assert vfm_res_after[0]["is_eligible"] is True


def test_service_caso_c_blocks_selection_and_manual_positive_override(db_session: Session, setup_mega_tenant):
    """
    Ejecución del Caso C a través de OfferEvaluationService y VFM:
    - Requisito: Garantía mínima 36 meses.
    - Evidencia: «Licencia soporte 36 meses garantía 12 meses».
    - Reevaluación automática produce FAILED (12 meses < 36 meses).
    - Validación manual positiva es BLOQUEADA con ValueError.
    - VFM marca la oferta como no elegible (FAILED_MANDATORY_REQUIREMENTS).
    - SelectionService rechaza la adjudicación.
    """
    case = CaseFile(
        title="Expediente Caso C Falso Positivo",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima 36 meses",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999004", business_name="Proveedor Caso C SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=45000.0,
        price=45000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_c.pdf",
        stored_path="mock/caso_c.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Licencia soporte 36 meses garantía 12 meses",
        confidence=0.92
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "FAILED"
    assert "12 meses" in eval_entry[0].explanation

    with pytest.raises(ValueError, match="Cannot assign positive compliance when documentary evidence demonstrates non-compliance"):
        eval_svc.update_evaluation(
            db=db_session,
            eval_id=eval_entry[0].id,
            new_status="PASSED",
            explanation="Intento indebido de validar garantía ignorando que es de 12 meses",
            user_id=1,
            tenant_id="mega_tenant"
        )

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is False
    assert vfm_res[0]["reason"] == "FAILED_MANDATORY_REQUIREMENTS"

    with pytest.raises(ValueError, match="Cannot propose an ineligible offer"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento indebido de seleccionar oferta Caso C",
            user_id=1,
            tenant_id="mega_tenant"
        )


def test_service_caso_d_blocks_selection_and_manual_positive_override(db_session: Session, setup_mega_tenant):
    """
    Ejecución del Caso D a través de OfferEvaluationService y VFM:
    - Requisito: Garantía mínima 36 meses.
    - Evidencia: «No incluye garantía de 36 meses».
    - Reevaluación automática produce FAILED (negación expresa).
    - Validación manual positiva es BLOQUEADA con ValueError.
    - VFM marca la oferta como no elegible (FAILED_MANDATORY_REQUIREMENTS).
    - SelectionService rechaza la adjudicación.
    """
    case = CaseFile(
        title="Expediente Caso D Falso Positivo",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima 36 meses",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999005", business_name="Proveedor Caso D SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=38000.0,
        price=38000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_d.pdf",
        stored_path="mock/caso_d.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="No incluye garantía de 36 meses",
        confidence=0.95
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "FAILED"
    assert "negación" in eval_entry[0].explanation.lower() or "exclusión" in eval_entry[0].explanation.lower()

    with pytest.raises(ValueError, match="Cannot assign positive compliance when documentary evidence demonstrates non-compliance"):
        eval_svc.update_evaluation(
            db=db_session,
            eval_id=eval_entry[0].id,
            new_status="PASSED",
            explanation="Intento indebido de validar oferta con garantía expresamente excluida",
            user_id=1,
            tenant_id="mega_tenant"
        )

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is False
    assert vfm_res[0]["reason"] == "FAILED_MANDATORY_REQUIREMENTS"

    with pytest.raises(ValueError, match="Cannot propose an ineligible offer"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento indebido de seleccionar oferta Caso D",
            user_id=1,
            tenant_id="mega_tenant"
        )


def test_service_caso_e_blocks_selection_and_manual_positive_override(db_session: Session, setup_mega_tenant):
    """
    Ejecución del Caso E a través de OfferEvaluationService y VFM:
    - Requisito: «Entrega 30 días e instalación 15 días».
    - Evidencia: «Instalación 15 días entrega 60 días».
    - Reevaluación automática produce FAILED (entrega 60d > 30d).
    - Validación manual positiva es BLOQUEADA con ValueError.
    - VFM marca la oferta como no elegible (FAILED_MANDATORY_REQUIREMENTS).
    - SelectionService rechaza la adjudicación.
    """
    case = CaseFile(
        title="Expediente Caso E Falso Positivo",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Entrega 30 días e instalación 15 días",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999006", business_name="Proveedor Caso E SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=42000.0,
        price=42000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_e.pdf",
        stored_path="mock/caso_e.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Instalación 15 días entrega 60 días",
        confidence=0.88
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "FAILED"
    assert "60" in eval_entry[0].explanation

    with pytest.raises(ValueError, match="Cannot assign positive compliance when documentary evidence demonstrates non-compliance"):
        eval_svc.update_evaluation(
            db=db_session,
            eval_id=eval_entry[0].id,
            new_status="PASSED",
            explanation="Intento indebido de validar oferta con plazo de entrega excedido",
            user_id=1,
            tenant_id="mega_tenant"
        )

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is False
    assert vfm_res[0]["reason"] == "FAILED_MANDATORY_REQUIREMENTS"

    with pytest.raises(ValueError, match="Cannot propose an ineligible offer"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento indebido de seleccionar oferta Caso E",
            user_id=1,
            tenant_id="mega_tenant"
        )


def test_service_unequivocal_positive_passes_and_allows_vfm_and_selection(db_session: Session, setup_mega_tenant):
    """
    Control positivo inequívoco a través de OfferEvaluationService, VFM y SelectionService:
    - Requisito: «Garantía mínima 36 meses».
    - Evidencia: «Garantía de fábrica del equipo de 36 meses».
    - Evaluación automática produce PASSED.
    - VFM marca la oferta como elegible (is_eligible=True).
    - SelectionService permite adjudicación.
    """
    case = CaseFile(
        title="Expediente Control Positivo Inequívoco",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima 36 meses",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999007", business_name="Proveedor Positivo SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=30000.0,
        price=30000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_positiva.pdf",
        stored_path="mock/caso_pos.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Garantía de fábrica del equipo de 36 meses",
        confidence=0.98
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "PASSED"

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is True

    prop = SelectionService.propose_selection(
        db=db_session,
        case_id=case.id,
        supplier_offer_id=offer.id,
        justification="Adjudicación conforme basada en cumplimiento técnico inequívoco",
        user_id=1,
        tenant_id="mega_tenant"
    )
    assert prop is not None
    assert prop.status == "UNDER_REVIEW"


# ==============================================================================
# 3. REGRESIONES P12 CIERRE DE RANGOS Y UNIDADES NO EQUIVALENTES (CASOS 1 A 5)
# ==============================================================================

def test_engine_caso_1_range_a_requires_revision():
    """
    Caso 1 (P12 Cierre de Rangos):
    Requisito: «Garantía mínima 36 meses».
    Evidencia: «Garantía de 12 a 36 meses».
    Resultado esperado: REQUIERE_REVISION (rango condicional no equiparable a cumplimiento estricto).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses",
        req_value=None,
        fragments=["Garantía de 12 a 36 meses"]
    )
    assert res["status"] == "REQUIERE_REVISION", f"Caso 1 debe ser REQUIERE_REVISION, obtuvo: {res}"
    assert "rango" in res["explanation"].lower() or "condicional" in res["explanation"].lower()
    assert res["confidence"] == 0.5
    assert engine.detect_improvement("Garantía mínima 36 meses", "Garantía de 12 a 36 meses") is False


def test_engine_caso_2_limit_hasta_requires_revision():
    """
    Caso 2 (P12 Cierre de Límites y Cotas):
    Requisito: «Garantía mínima 36 meses».
    Evidencia: «Garantía hasta 36 meses».
    Resultado esperado: REQUIERE_REVISION (cota máxima «hasta» no garantiza el cumplimiento de la garantía mínima requerida).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses",
        req_value=None,
        fragments=["Garantía hasta 36 meses"]
    )
    assert res["status"] == "REQUIERE_REVISION", f"Caso 2 debe ser REQUIERE_REVISION, obtuvo: {res}"
    assert "cota" in res["explanation"].lower() or "límite" in res["explanation"].lower() or "mínimo" in res["explanation"].lower()
    assert res["confidence"] == 0.5
    assert engine.detect_improvement("Garantía mínima 36 meses", "Garantía hasta 36 meses") is False


def test_engine_caso_3_range_hyphen_requires_revision():
    """
    Caso 3 (P12 Cierre de Rangos con Guion):
    Requisito: «Garantía mínima 36 meses».
    Evidencia: «Garantía de 12-36 meses».
    Resultado esperado: REQUIERE_REVISION (ambos extremos del rango son reconocidos sin descartar el inferior por falta de unidad).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses",
        req_value=None,
        fragments=["Garantía de 12-36 meses"]
    )
    assert res["status"] == "REQUIERE_REVISION", f"Caso 3 debe ser REQUIERE_REVISION, obtuvo: {res}"
    assert "rango" in res["explanation"].lower() or "condicional" in res["explanation"].lower()
    assert res["confidence"] == 0.5
    assert engine.detect_improvement("Garantía mínima 36 meses", "Garantía de 12-36 meses") is False


def test_engine_caso_4_limit_maxima_requires_revision():
    """
    Caso 4 (P12 Cierre de Límites Superiores):
    Requisito: «Garantía mínima 36 meses».
    Evidencia: «Garantía máxima de 36 meses».
    Resultado esperado: REQUIERE_REVISION (garantía máxima/tope de 36 meses no equivale a asegurar un mínimo de 36 meses).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Garantía mínima 36 meses",
        req_value=None,
        fragments=["Garantía máxima de 36 meses"]
    )
    assert res["status"] == "REQUIERE_REVISION", f"Caso 4 debe ser REQUIERE_REVISION, obtuvo: {res}"
    assert "cota" in res["explanation"].lower() or "límite" in res["explanation"].lower() or "mínimo" in res["explanation"].lower()
    assert res["confidence"] == 0.5
    assert engine.detect_improvement("Garantía mínima 36 meses", "Garantía máxima de 36 meses") is False


def test_engine_caso_5_temporal_modality_mismatch_requires_revision():
    """
    Caso 5 (P12 Cierre de Unidades Temporales No Equivalentes):
    Requisito: «Entrega máximo 30 días calendario».
    Evidencia: «Entrega en 20 días hábiles».
    Resultado esperado: REQUIERE_REVISION (días hábiles no equivale a días calendario sin conversión acreditada; no IMPROVEMENT).
    """
    engine = DeterministicImprovementEngine()
    res = engine.contrast_technical_compliance(
        req_desc="Entrega máximo 30 días calendario",
        req_value=None,
        fragments=["Entrega en 20 días hábiles"]
    )
    assert res["status"] == "REQUIERE_REVISION", f"Caso 5 debe ser REQUIERE_REVISION, obtuvo: {res}"
    assert "temporal" in res["explanation"].lower() or "hábiles" in res["explanation"].lower() or "calendario" in res["explanation"].lower()
    assert res["confidence"] == 0.5
    assert engine.detect_improvement("Entrega máximo 30 días calendario", "Entrega en 20 días hábiles") is False


def test_engine_detect_improvement_safety_blocks_ranges_and_temporal_mismatch():
    """
    Verifica que detect_improvement() nunca devuelva True para rangos, cotas o bases temporales dispares.
    """
    engine = DeterministicImprovementEngine()
    assert engine.detect_improvement("Garantía mínima 36 meses", "Garantía de 12 a 36 meses") is False
    assert engine.detect_improvement("Garantía mínima 36 meses", "Garantía hasta 36 meses") is False
    assert engine.detect_improvement("Garantía mínima 36 meses", "Garantía de 12-36 meses") is False
    assert engine.detect_improvement("Garantía mínima 36 meses", "Garantía máxima de 36 meses") is False
    assert engine.detect_improvement("Entrega máximo 30 días calendario", "Entrega en 20 días hábiles") is False
    assert engine.detect_improvement("30 días calendario", "20 días hábiles") is False
    assert engine.detect_improvement("Garantía 24 meses", "Garantía de 12 a 36 meses") is False
    assert engine.detect_improvement("Entrega 30 días", "Entrega hasta 20 días") is False


def test_engine_temporal_modality_matching_positive_controls():
    """
    Controles positivos deterministas para modalidades temporales equivalentes:
    - Ambos días calendario: 20 días calendario vs 30 días calendario => IMPROVEMENT
    - Ambos días hábiles: 15 días hábiles vs 20 días hábiles => IMPROVEMENT
    - Ambos días calendario: 30 días calendario vs 30 días calendario => PASSED
    """
    engine = DeterministicImprovementEngine()
    res_cal = engine.contrast_technical_compliance(
        req_desc="Entrega máximo 30 días calendario",
        req_value=None,
        fragments=["Entrega en 20 días calendario"]
    )
    assert res_cal["status"] == "IMPROVEMENT"
    assert res_cal["confidence"] == 1.0
    assert engine.detect_improvement("Entrega máximo 30 días calendario", "Entrega en 20 días calendario") is True

    res_hab = engine.contrast_technical_compliance(
        req_desc="Plazo de entrega máximo 20 días hábiles",
        req_value=None,
        fragments=["Plazo de entrega de 15 días hábiles"]
    )
    assert res_hab["status"] == "IMPROVEMENT"
    assert res_hab["confidence"] == 1.0
    assert engine.detect_improvement("Plazo de entrega máximo 20 días hábiles", "Plazo de entrega de 15 días hábiles") is True

    res_pass = engine.contrast_technical_compliance(
        req_desc="Entrega máximo 30 días calendario",
        req_value=None,
        fragments=["Entrega en 30 días calendario"]
    )
    assert res_pass["status"] == "PASSED"
    assert res_pass["confidence"] == 1.0


# ------------------------------------------------------------------------------
# INTEGRACIÓN SERVICE LEVEL (OFFER EVALUATION, VFM Y SELECTION)
# ------------------------------------------------------------------------------

def test_service_caso_1_range_leaves_offer_ineligible_until_human_review(db_session: Session, setup_mega_tenant):
    """
    Caso 1 a nivel servicio:
    - Evidencia con rango: «Garantía de 12 a 36 meses».
    - OfferEvaluationService produce REQUIERE_REVISION.
    - VFM marca oferta inelegible (REQUIRES_REVIEW_MANDATORY_REQUIREMENTS).
    - SelectionService bloquea adjudicación directa.
    """
    case = CaseFile(
        title="Expediente Caso 1 Rango",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima 36 meses",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999011", business_name="Proveedor Caso 1 SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=50000.0,
        price=50000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_1.pdf",
        stored_path="mock/caso_1.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Garantía de 12 a 36 meses",
        confidence=0.90
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "REQUIERE_REVISION"
    assert "rango" in eval_entry[0].explanation.lower() or "condicional" in eval_entry[0].explanation.lower()

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is False
    assert vfm_res[0]["reason"] == "REQUIRES_REVIEW_MANDATORY_REQUIREMENTS"

    with pytest.raises(ValueError, match="Cannot propose an offer with pending mandatory evaluations."):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento indebido de adjudicar oferta con rango",
            user_id=1,
            tenant_id="mega_tenant"
        )


def test_service_caso_2_limit_hasta_leaves_offer_ineligible_until_human_review(db_session: Session, setup_mega_tenant):
    """
    Caso 2 a nivel servicio:
    - Evidencia con cota máxima: «Garantía hasta 36 meses».
    - OfferEvaluationService produce REQUIERE_REVISION.
    - VFM marca oferta inelegible.
    - SelectionService bloquea adjudicación directa.
    """
    case = CaseFile(
        title="Expediente Caso 2 Hasta",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima 36 meses",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999012", business_name="Proveedor Caso 2 SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=48000.0,
        price=48000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_2.pdf",
        stored_path="mock/caso_2.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Garantía hasta 36 meses",
        confidence=0.90
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "REQUIERE_REVISION"

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert vfm_res[0]["is_eligible"] is False

    with pytest.raises(ValueError, match="Cannot propose an offer with pending mandatory evaluations."):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento indebido de adjudicar oferta con cota hasta",
            user_id=1,
            tenant_id="mega_tenant"
        )


def test_service_caso_4_limit_maxima_leaves_offer_ineligible_until_human_review(db_session: Session, setup_mega_tenant):
    """
    Caso 4 a nivel servicio:
    - Evidencia con cota máxima: «Garantía máxima de 36 meses».
    - OfferEvaluationService produce REQUIERE_REVISION.
    - VFM marca oferta inelegible.
    - SelectionService bloquea adjudicación directa.
    """
    case = CaseFile(
        title="Expediente Caso 4 Maxima",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Garantía mínima 36 meses",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999014", business_name="Proveedor Caso 4 SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=47000.0,
        price=47000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_4.pdf",
        stored_path="mock/caso_4.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Garantía máxima de 36 meses",
        confidence=0.91
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "REQUIERE_REVISION"

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert vfm_res[0]["is_eligible"] is False

    with pytest.raises(ValueError, match="Cannot propose an offer with pending mandatory evaluations."):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento indebido de adjudicar oferta con cota máxima",
            user_id=1,
            tenant_id="mega_tenant"
        )


def test_service_caso_5_temporal_modality_mismatch_leaves_offer_ineligible(db_session: Session, setup_mega_tenant):
    """
    Caso 5 a nivel servicio:
    - Requisito: «Entrega máximo 30 días calendario».
    - Evidencia: «Entrega en 20 días hábiles».
    - OfferEvaluationService produce REQUIERE_REVISION (no IMPROVEMENT).
    - VFM marca la oferta como no elegible.
    - SelectionService bloquea adjudicación directa.
    """
    case = CaseFile(
        title="Expediente Caso 5 Base Temporal",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Entrega máximo 30 días calendario",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999015", business_name="Proveedor Caso 5 SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=41000.0,
        price=41000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_caso_5.pdf",
        stored_path="mock/caso_5.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Entrega en 20 días hábiles",
        confidence=0.92
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "REQUIERE_REVISION"
    assert "temporal" in eval_entry[0].explanation.lower() or "hábiles" in eval_entry[0].explanation.lower()

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is False
    assert vfm_res[0]["reason"] == "REQUIRES_REVIEW_MANDATORY_REQUIREMENTS"

    with pytest.raises(ValueError, match="Cannot propose an offer with pending mandatory evaluations."):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento indebido de adjudicar con discrepancia temporal sin acreditación",
            user_id=1,
            tenant_id="mega_tenant"
        )


def test_service_temporal_modality_matching_passes_and_allows_selection(db_session: Session, setup_mega_tenant):
    """
    Control positivo inequívoco con modalidad temporal equivalente:
    - Requisito: «Entrega máximo 30 días calendario».
    - Evidencia: «Entrega en 20 días calendario».
    - OfferEvaluationService produce IMPROVEMENT.
    - VFM marca oferta elegible.
    - SelectionService permite adjudicación.
    """
    case = CaseFile(
        title="Expediente Control Positivo Calendario",
        contract_type="BIENES",
        status="UNDER_REVIEW",
        tenant_id="mega_tenant",
        traceability_regime="P12_STRICT",
        assigned_to_user_id=1
    )
    db_session.add(case)
    db_session.commit()

    req = CaseRequirementMatrix(
        case_id=case.id,
        requirement_type="TECHNICAL",
        description="Entrega máximo 30 días calendario",
        mandatory=True,
        status="VALIDATED"
    )
    db_session.add(req)
    db_session.commit()

    sup = Supplier(ruc="20999999016", business_name="Proveedor Calendario Positivo SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.commit()
    db_session.add(SupplierProfile(supplier_id=sup.id, validation_status="VERIFIED"))

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=sup.id,
        status="UNDER_REVIEW",
        total_amount=35000.0,
        price=35000.0,
        currency="PEN"
    )
    db_session.add(offer)
    db_session.commit()

    doc = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_pos_cal.pdf",
        stored_path="mock/caso_pos_cal.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()

    oe = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc.id,
        document_type="TECHNICAL_SPEC",
        fragment="Entrega en 20 días calendario",
        confidence=0.96
    )
    db_session.add(oe)
    db_session.commit()

    ore = OfferRequirementEvidence(
        case_id=case.id,
        supplier_offer_id=offer.id,
        requirement_id=req.id,
        offer_evidence_id=oe.id,
        document_id=doc.id,
        fragment=oe.fragment,
        verification_status="VERIFIED",
        verified_by=1,
        verified_at=datetime.now(timezone.utc)
    )
    db_session.add(ore)
    db_session.commit()

    eval_svc = OfferEvaluationService()
    eval_entry = eval_svc.evaluate_offer(db=db_session, supplier_offer_id=offer.id, user_id=1, tenant_id="mega_tenant")
    assert len(eval_entry) == 1
    assert eval_entry[0].status == "IMPROVEMENT"

    vfm_svc = ValueForMoneyService(db_session)
    vfm_res = vfm_svc.calculate_vfm(case.id)
    assert len(vfm_res) == 1
    assert vfm_res[0]["is_eligible"] is True

    prop = SelectionService.propose_selection(
        db=db_session,
        case_id=case.id,
        supplier_offer_id=offer.id,
        justification="Adjudicación conforme basada en mejora técnica inequívoca en días calendario",
        user_id=1,
        tenant_id="mega_tenant"
    )
    assert prop is not None
    assert prop.status == "UNDER_REVIEW"



