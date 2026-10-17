import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile, User, UploadedDocument
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_offer_item import SupplierOfferItem
from app.models.v6.case_procurement_item import CaseProcurementItem
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_requirement_evidence import OfferRequirementEvidence
from app.models.v6.offer_evaluation import OfferEvaluation
from app.api.auth import get_current_active_user, get_current_user
from app.main import app

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

def get_supervisor_client(user_id: int = 2):
    sup_user = User(
        id=user_id,
        username=f"supervisor_{user_id}",
        role="SUPERVISOR",
        is_active=True,
        must_change_password=False,
        tenant_id="mega_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: sup_user
    app.dependency_overrides[get_current_user] = lambda: sup_user
    return TestClient(app)

def get_other_tenant_client():
    other_user = User(
        id=99,
        username="other_tenant_user",
        role="ADMIN",
        is_active=True,
        must_change_password=False,
        tenant_id="other_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: other_user
    app.dependency_overrides[get_current_user] = lambda: other_user
    return TestClient(app)

def get_readonly_client(user_id: int = 3):
    ro_user = User(
        id=user_id,
        username=f"readonly_{user_id}",
        role="READONLY",
        is_active=True,
        must_change_password=False,
        tenant_id="mega_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: ro_user
    app.dependency_overrides[get_current_user] = lambda: ro_user
    return TestClient(app)

def get_unassigned_operator_client(user_id: int = 4):
    unassigned_op = User(
        id=user_id,
        username=f"operator_unassigned_{user_id}",
        role="OPERATOR",
        is_active=True,
        must_change_password=False,
        tenant_id="mega_tenant"
    )
    app.dependency_overrides[get_current_active_user] = lambda: unassigned_op
    app.dependency_overrides[get_current_user] = lambda: unassigned_op
    return TestClient(app)

def cleanup_overrides():
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture(autouse=True)
def clean_deps():
    yield
    cleanup_overrides()

def setup_base_case_data(db_session: Session):
    case = CaseFile(
        title="P12 Traceability Case",
        contract_type="goods",
        tenant_id="mega_tenant",
        assigned_to_user_id=1,
        status="WAITING_QUOTATION"
    )
    db_session.add(case)
    db_session.flush()

    supplier = Supplier(
        ruc="20999888777",
        business_name="P12 Tech Solutions SAC",
        tenant_id="mega_tenant"
    )
    db_session.add(supplier)
    db_session.flush()

    profile = SupplierProfile(
        supplier_id=supplier.id,
        validation_status="VERIFIED"
    )
    db_session.add(profile)

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        status="SUBMITTED",
        currency="PEN",
        price=10000.0,
        total_amount=10000.0,
        evaluation_status="PENDING"
    )
    db_session.add(offer)
    db_session.flush()

    p_item = CaseProcurementItem(
        case_id=case.id,
        item_number=1,
        description="Servidor Empresarial",
        quantity=1.0,
        unit="UND"
    )
    db_session.add(p_item)
    db_session.flush()

    o_item = SupplierOfferItem(
        supplier_offer_id=offer.id,
        procurement_item_id=p_item.id,
        description="Servidor Empresarial",
        quantity=1.0,
        unit="UND",
        unit_price=10000.0
    )
    db_session.add(o_item)

    req_a = CaseRequirementMatrix(
        case_id=case.id,
        category="TECHNICAL",
        description="Garantia minima 12 meses",
        value="12 meses",
        mandatory=True,
        requirement_type="MINIMO"
    )
    req_b = CaseRequirementMatrix(
        case_id=case.id,
        category="TECHNICAL",
        description="Plazo maximo 30 dias",
        value="30 dias",
        mandatory=True,
        requirement_type="MAXIMO"
    )
    db_session.add_all([req_a, req_b])
    db_session.flush()

    doc1 = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="propuesta_tecnica.pdf",
        stored_path="/tmp/propuesta_tecnica.pdf",
        mime_type="application/pdf"
    )
    doc2 = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="anexo_plazo.pdf",
        stored_path="/tmp/anexo_plazo.pdf",
        mime_type="application/pdf"
    )
    db_session.add_all([doc1, doc2])
    db_session.flush()

    ev_1 = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc1.id,
        document_type="propuesta_tecnica.pdf",
        page=3,
        fragment="Garantia de 24 meses incluida",
        confidence=0.9
    )
    ev_2 = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc2.id,
        document_type="anexo_plazo.pdf",
        page=1,
        fragment="Plazo de entrega 20 dias",
        confidence=0.9
    )
    db_session.add_all([ev_1, ev_2])
    db_session.commit()
    db_session.refresh(case)
    db_session.refresh(offer)
    db_session.refresh(req_a)
    db_session.refresh(req_b)
    db_session.refresh(ev_1)
    db_session.refresh(ev_2)

    return case, offer, req_a, req_b, ev_1, ev_2

# 1. Una evidencia asociada al requisito A no acredita automáticamente el requisito B.
def test_evidence_association_isolation(db_session: Session):
    case, offer, req_a, req_b, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # Link ev_1 to req_a only
    link_res = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    )
    assert link_res.status_code == 200
    evidence_link_id = link_res.json()["id"]

    # Verify evidence for req_a
    rev_res = client.put(
        f"/api/v6/cases/{case.id}/evidence/{evidence_link_id}/review",
        json={"verification_status": "VERIFIED", "notes": "Garantia verificada"}
    )
    assert rev_res.status_code == 200

    # Evaluate offer
    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 200
    evals = eval_res.json()

    eval_a = next(e for e in evals if e["requirement_id"] == req_a.id)
    eval_b = next(e for e in evals if e["requirement_id"] == req_b.id)

    # Req A is satisfied (IMPROVEMENT because 24 meses > 12 meses)
    assert eval_a["status"] in ["PASSED", "IMPROVEMENT"]
    # Req B has NO evidence -> strictly MISSING_DATA
    assert eval_b["status"] == "MISSING_DATA"

# 2. La ausencia de evidencia impide cumplimiento positivo.
def test_missing_evidence_blocks_compliance(db_session: Session):
    case, offer, req_a, req_b, _, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 200
    evals = eval_res.json()

    for ev in evals:
        assert ev["status"] == "MISSING_DATA"
        assert ev["status"] not in ["PASSED", "IMPROVEMENT"]

# 3. Evidencia de otro expediente o tenant es rechazada sin mutación.
def test_cross_case_or_cross_tenant_rejected(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    other_client = get_other_tenant_client()

    # Cross tenant access is rejected (404/403)
    res = other_client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    )
    assert res.status_code in [403, 404]

    # Verification that no link was created
    links_count = db_session.query(OfferRequirementEvidence).filter_by(case_id=case.id).count()
    assert links_count == 0

# 4. Evidencia pendiente no puede justificar selección.
def test_pending_evidence_blocks_selection(db_session: Session):
    case, offer, req_a, req_b, ev_1, ev_2 = setup_base_case_data(db_session)
    client = get_operator_client()

    # Link both evidences but keep them PENDING
    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id})
    l2 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_b.id}/evidence", json={"offer_evidence_id": ev_2.id})
    assert l1.status_code == 200
    assert l2.status_code == 200

    # Evaluate -> both should be REQUIERE_REVISION
    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 200
    for e in eval_res.json():
        assert e["status"] == "REQUIERE_REVISION"

    # Selection proposal must be rejected
    from app.services.v6.selection.selection_service import SelectionService
    with pytest.raises(ValueError, match="pending mandatory evaluations"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Propuesta para adjudicar",
            user_id=1,
            tenant_id="mega_tenant"
        )

# 5. Evidencia conflictiva bloquea la elegibilidad.
def test_conflicting_evidence_blocks_eligibility(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # Add a second contradictory evidence for req_a
    doc_conflict = UploadedDocument(
        case_id=case.id,
        document_type="quotation",
        original_filename="anexo_contradictorio.pdf",
        stored_path="/tmp/anexo_contradictorio.pdf",
        mime_type="application/pdf"
    )
    db_session.add(doc_conflict)
    db_session.flush()

    ev_conflict = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=doc_conflict.id,
        document_type="anexo_contradictorio.pdf",
        page=2,
        fragment="Garantia de 6 meses unicamente",
        confidence=0.8
    )
    db_session.add(ev_conflict)
    db_session.commit()

    # Link both to req_a
    client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id})
    client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_conflict.id})

    # Evaluate
    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    eval_a = next(e for e in eval_res.json() if e["requirement_id"] == req_a.id)
    assert eval_a["status"] == "CONFLICT"

    from app.services.v6.selection.selection_service import SelectionService
    with pytest.raises(ValueError, match="CONFLICT"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Propuesta",
            user_id=1,
            tenant_id="mega_tenant"
        )

# 6. Evidencia verificada permite cumplimiento cuando realmente procede.
def test_verified_evidence_allows_compliance(db_session: Session):
    case, offer, req_a, req_b, ev_1, ev_2 = setup_base_case_data(db_session)
    client = get_operator_client()

    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()
    l2 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_b.id}/evidence", json={"offer_evidence_id": ev_2.id}).json()

    # Verify both
    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "VERIFIED"})
    client.put(f"/api/v6/cases/{case.id}/evidence/{l2['id']}/review", json={"verification_status": "VERIFIED"})

    # Evaluate
    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    for e in eval_res.json():
        assert e["status"] in ["PASSED", "IMPROVEMENT"]

    # Propose selection succeeds
    from app.services.v6.selection.selection_service import SelectionService
    proposal = SelectionService.propose_selection(
        db=db_session,
        case_id=case.id,
        supplier_offer_id=offer.id,
        justification="Cumplimiento acreditado y validado",
        user_id=1,
        tenant_id="mega_tenant"
    )
    assert proposal.status == "UNDER_REVIEW"

# 7. Cambiar evidencia invalida evaluaciones dependientes.
def test_changing_evidence_invalidates_evaluation(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # Link and verify
    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()
    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "VERIFIED"})

    # Check evaluation is PASSED/IMPROVEMENT
    ev_entry = db_session.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id, requirement_id=req_a.id).first()
    assert ev_entry.status in ["PASSED", "IMPROVEMENT"]

    # Rejection of evidence immediately invalidates evaluation to FAILED
    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "REJECTED", "notes": "No cumple garantia"})
    db_session.refresh(ev_entry)
    assert ev_entry.status == "FAILED"

    # Resetting to PENDING invalidates to REQUIERE_REVISION
    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "PENDING"})
    db_session.refresh(ev_entry)
    assert ev_entry.status == "REQUIERE_REVISION"

    # Unlinking evidence immediately invalidates to MISSING_DATA
    del_res = client.delete(f"/api/v6/cases/{case.id}/evidence/{l1['id']}")
    assert del_res.status_code == 200
    db_session.refresh(ev_entry)
    assert ev_entry.status == "MISSING_DATA"

# 8. Reevaluar dos veces no produce duplicaciones (idempotencia y unicidad).
def test_reevaluation_idempotency_no_duplication(db_session: Session):
    case, offer, req_a, req_b, _, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    eval_1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_1.status_code == 200
    count_1 = db_session.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id).count()

    eval_2 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_2.status_code == 200
    count_2 = db_session.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id).count()

    assert count_1 == 2
    assert count_2 == 2

# 9. Un fallo inyectado revierte toda la transacción.
def test_injected_failure_reverts_transaction(db_session: Session, monkeypatch):
    case, offer, req_a, req_b, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # Link and verify ev_1
    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()
    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "VERIFIED"})

    ev_a_before = db_session.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id, requirement_id=req_a.id).first()
    status_before = ev_a_before.status

    # Inject failure inside _evaluate_single_requirement_in_tx
    from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
    def faulty_eval(*args, **kwargs):
        raise RuntimeError("Injected database failure during evaluation")

    monkeypatch.setattr(OfferEvaluationService, "_evaluate_single_requirement_in_tx", faulty_eval)

    with pytest.raises(RuntimeError):
        client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")

    # Ensure transaction was rolled back and previous state preserved
    ev_a_after = db_session.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id, requirement_id=req_a.id).first()
    assert ev_a_after.status == status_before

# 10. Operadores sin autorización no pueden validar evidencia ajena.
def test_unauthorized_operator_cannot_review_other_case(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client(user_id=1) # Case is assigned to user_id=1

    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()

    # Other operator not assigned to this case
    unauthorized_operator_client = get_operator_client(user_id=55)
    rev_res = unauthorized_operator_client.put(
        f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review",
        json={"verification_status": "VERIFIED"}
    )
    # verify_case_access raises 404 or router raises 403
    assert rev_res.status_code in [403, 404]

# 11. Expedientes aprobados permanecen inmutables.
def test_terminal_case_immutability(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()

    # Set case to terminal status APPROVED
    case.status = "APPROVED"
    db_session.commit()

    # Attempt to review evidence
    rev_res = client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "VERIFIED"})
    assert rev_res.status_code == 409

    # Attempt to unlink evidence
    del_res = client.delete(f"/api/v6/cases/{case.id}/evidence/{l1['id']}")
    assert del_res.status_code == 409

    # Attempt to evaluate offer
    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 409

# 12. La selección P11 continúa rechazando ofertas no elegibles.
def test_p11_selection_still_rejects_ineligible_offers(db_session: Session):
    case, offer, req_a, req_b, ev_1, ev_2 = setup_base_case_data(db_session)
    client = get_operator_client()

    # Link both evidences: one verified, one rejected
    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()
    l2 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_b.id}/evidence", json={"offer_evidence_id": ev_2.id}).json()

    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "VERIFIED"})
    client.put(f"/api/v6/cases/{case.id}/evidence/{l2['id']}/review", json={"verification_status": "REJECTED"})

    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    assert eval_res.status_code == 200

    from app.services.v6.selection.selection_service import SelectionService
    with pytest.raises(ValueError, match="Failed mandatory"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento de adjudicar oferta con requisito rechazado",
            user_id=1,
            tenant_id="mega_tenant"
        )

# =========================================================================
# AUDITORÍA DE INTEGRIDAD GPT — CONTROLES 1 A 4
# =========================================================================

# CONTROL 1: Integridad de la fuente documental y comportamiento fail-closed ante eliminación
def test_control1_fail_closed_on_source_deletion_or_unlinking(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # 1. Vincular y verificar evidencia -> PASSED
    link_res = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    ).json()
    client.put(
        f"/api/v6/cases/{case.id}/evidence/{link_res['id']}/review",
        json={"verification_status": "VERIFIED"}
    )
    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate").json()
    assert any(e["requirement_id"] == req_a.id and e["status"] in ["PASSED", "IMPROVEMENT"] for e in eval_res)

    # 2. Eliminación física de la fuente OfferEvidence de la base de datos
    db_session.delete(ev_1)
    db_session.commit()

    # 3. Comportamiento Fail-Closed en el motor: reevaluación no puede otorgar PASSED sin fuente viva
    from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
    engine_eval = OfferEvaluationService().reevaluate_requirement(
        db_session, offer.id, req_a.id, user_id=1, tenant_id="mega_tenant"
    )
    assert engine_eval.status == "MISSING_DATA"
    assert "No se encontro evidencia documental verificable" in engine_eval.explanation

    # 4. Comportamiento Fail-Closed en selección: propuesta rechazada
    from app.services.v6.selection.selection_service import SelectionService
    with pytest.raises(ValueError, match="MISSING_DATA"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Adjudicación inválida sin fuente documental",
            user_id=1,
            tenant_id="mega_tenant"
        )

# CONTROL 2: Concurrencia real y unicidad estricta de OfferEvaluation frente a PostgreSQL
def test_control2_real_concurrency_offer_evaluation_uniqueness(db_session: Session):
    import concurrent.futures
    from sqlalchemy.exc import IntegrityError
    from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService

    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()
    link_res = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    ).json()
    client.put(
        f"/api/v6/cases/{case.id}/evidence/{link_res['id']}/review",
        json={"verification_status": "VERIFIED"}
    )

    eval_service = OfferEvaluationService()

    # Ejecutar 10 solicitudes concurrentes de reevaluación sobre la misma pareja (offer.id, req_a.id)
    from tests.conftest import TestingSessionLocal
    def run_eval():
        with TestingSessionLocal() as session:
            return eval_service.reevaluate_requirement(
                session, offer.id, req_a.id, user_id=1, tenant_id="mega_tenant"
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_eval) for _ in range(10)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    # Comprobar que en PostgreSQL existe EXACTAMENTE una evaluación activa para la pareja
    records = db_session.query(OfferEvaluation).filter_by(
        supplier_offer_id=offer.id,
        requirement_id=req_a.id
    ).all()
    assert len(records) == 1

    # Comprobar que la restricción UNIQUE uq_offer_evaluations_offer_req rechaza duplicados directos
    duplicate_eval = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req_a.id,
        status="PASSED",
        explanation="Intento de duplicación manual",
        evaluation_confidence=1.0
    )
    db_session.add(duplicate_eval)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

# CONTROL 2 (Cont.): Prueba de rollback atómico ante fallo transaccional
def test_control2_rollback_preserves_atomic_state(db_session: Session, monkeypatch):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # Estado previo: REQUIERE_REVISION
    client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    )
    eval_res = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate").json()
    prev_status = next(e["status"] for e in eval_res if e["requirement_id"] == req_a.id)
    assert prev_status == "REQUIERE_REVISION"

    # Inyectar fallo en reevaluación atómica
    from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
    def faulty_step(*args, **kwargs):
        raise RuntimeError("Fallo transaccional inyectado simulando caída de PostgreSQL")

    monkeypatch.setattr(OfferEvaluationService, "_evaluate_single_requirement_in_tx", faulty_step)

    with pytest.raises(RuntimeError):
        OfferEvaluationService().reevaluate_requirement(
            db_session, offer.id, req_a.id, user_id=1, tenant_id="mega_tenant"
        )

    # Verificar que el rollback conservó el estado anterior sin mutación
    db_session.rollback()
    current_eval = db_session.query(OfferEvaluation).filter_by(
        supplier_offer_id=offer.id,
        requirement_id=req_a.id
    ).first()
    assert current_eval.status == "REQUIERE_REVISION"

# CONTROL 3: Auditoría integral de PUT /api/v6/cases/{case_id}/evaluations/{eval_id}
def test_control3_put_evaluation_audited_strict_security(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    # Crear evaluación inicial en base de datos
    eval_entry = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req_a.id,
        status="MISSING_DATA",
        explanation="Sin evidencia inicial",
        evaluation_confidence=0.0
    )
    db_session.add(eval_entry)
    db_session.commit()

    operator_assigned_client = get_operator_client(user_id=1) # Asignado

    # 3A. Rechazo de asignación manual de PASSED sin evidencia documental verificada
    res_no_ev = operator_assigned_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_entry.id}",
        json={"status": "PASSED", "explanation": "Intento de bypass sin evidencia"}
    )
    assert res_no_ev.status_code == 400
    assert "without specific verified documentary evidence" in res_no_ev.json()["detail"]

    # 3B. Rechazo de PASSED cuando la evidencia está en PENDING
    l1 = operator_assigned_client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    ).json()
    res_pending = operator_assigned_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_entry.id}",
        json={"status": "PASSED", "explanation": "Intento con evidencia PENDING"}
    )
    assert res_pending.status_code == 400

    # 3C. Rechazo a usuario READONLY
    readonly_client = get_readonly_client()
    res_ro = readonly_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_entry.id}",
        json={"status": "OBSERVED", "explanation": "Observación por solo lectura"}
    )
    assert res_ro.status_code == 403

    # 3D. Rechazo a operador sin asignación al expediente
    unassigned_client = get_unassigned_operator_client(user_id=88)
    res_unassigned = unassigned_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_entry.id}",
        json={"status": "OBSERVED", "explanation": "Operador no asignado"}
    )
    assert res_unassigned.status_code in [403, 404]

    # 3E. Rechazo ante tenant ajeno
    foreign_client = get_other_tenant_client()
    res_foreign = foreign_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_entry.id}",
        json={"status": "OBSERVED", "explanation": "Tenant ajeno"}
    )
    assert res_foreign.status_code in [403, 404]

    # 3F. Rechazo cuando el expediente está en aprobación (UNDER_REVIEW)
    operator_assigned_client = get_operator_client(user_id=1)
    case.status = "UNDER_REVIEW"
    db_session.commit()
    res_under_app = operator_assigned_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_entry.id}",
        json={"status": "OBSERVED", "explanation": "Caso en aprobación"}
    )
    assert res_under_app.status_code == 400
    assert "approval" in res_under_app.json()["detail"].lower()

    # 3G. Rechazo cuando el expediente está en estado terminal (APPROVED)
    case.status = "APPROVED"
    db_session.commit()
    res_terminal = operator_assigned_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_entry.id}",
        json={"status": "OBSERVED", "explanation": "Caso terminal"}
    )
    assert res_terminal.status_code == 409

    # 3H. Aceptación autorizada cuando la evidencia SÍ fue formalmente verificada
    case.status = "WAITING_QUOTATION"
    db_session.commit()
    operator_assigned_client.put(
        f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review",
        json={"verification_status": "VERIFIED"}
    )
    res_authorized = operator_assigned_client.put(
        f"/api/v6/cases/{case.id}/evaluations/{eval_entry.id}",
        json={"status": "PASSED", "explanation": "Cumplimiento verificado conforme por operador"}
    )
    assert res_authorized.status_code == 200
    assert res_authorized.json()["status"] == "PASSED"

# CONTROL 4: Coherencia entre evidencia y cumplimiento con dos requisitos independientes
def test_control4_evidence_coherence_two_requirements_isolated(db_session: Session):
    case, offer, req_a, req_b, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # Fragmento con confianza OCR del 99% asociado EXCLUSIVAMENTE a Req A
    l1 = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    ).json()

    # Validar únicamente Req A
    client.put(
        f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review",
        json={"verification_status": "VERIFIED"}
    )

    # Evaluar oferta completa
    evals = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate").json()
    eval_a = next(e for e in evals if e["requirement_id"] == req_a.id)
    eval_b = next(e for e in evals if e["requirement_id"] == req_b.id)

    # Req A está acreditado porque cuenta con evidencia vinculada y verificada
    assert eval_a["status"] in ["PASSED", "IMPROVEMENT"]

    # Req B se mantiene estrictamente en MISSING_DATA sin herencia indebida ni automatismo por OCR
    assert eval_b["status"] == "MISSING_DATA"
    assert "No se encontro evidencia documental" in eval_b["explanation"]

    # Reevaluación de una evaluación antigua preexistente sin vínculos
    # Simular evaluación histórica manual PASSED en req_b
    eval_b_db = db_session.query(OfferEvaluation).filter_by(
        supplier_offer_id=offer.id,
        requirement_id=req_b.id
    ).first()
    eval_b_db.status = "PASSED"
    db_session.commit()

    # Al ser reevaluada formalmente por el motor, la evaluación sin vínculos es revocada a MISSING_DATA
    from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
    revoked = OfferEvaluationService().reevaluate_requirement(
        db_session, offer.id, req_b.id, user_id=1, tenant_id="mega_tenant"
    )
    assert revoked.status == "MISSING_DATA"


# =========================================================================
# REMEDIACIÓN P12: TESTS NEGATIVOS Y DE REGRESIÓN DE LOS 5 BLOQUEANTES
# =========================================================================

# --- CORRECCIÓN 1: Exigir Documento Fuente Verificable ---

def test_c1_missing_document_rejected_at_link(db_session: Session):
    case, offer, req_a, _, _, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # Crear evidencia sin documento asociado
    ev_no_doc = OfferEvidence(
        supplier_offer_id=offer.id,
        document_id=None,
        document_type="sin_documento.pdf",
        fragment="Garantia sin documento real",
        page=1
    )
    db_session.add(ev_no_doc)
    db_session.commit()

    # Intento de vinculación sin documento real debe ser rechazado con 400
    res = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_no_doc.id}
    )
    assert res.status_code == 400
    assert "verifiable UploadedDocument is required" in res.json()["detail"]

def test_c1_invalid_or_alien_document_rejected(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # 1. Document ID inexistente
    res_nonexistent = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id, "document_id": 999999}
    )
    assert res_nonexistent.status_code == 400

    # 2. Document ID de otro caso
    alien_case = CaseFile(title="Alien Case", contract_type="goods", tenant_id="mega_tenant", status="WAITING_QUOTATION")
    db_session.add(alien_case)
    db_session.flush()
    alien_doc = UploadedDocument(case_id=alien_case.id, document_type="quotation", original_filename="alien.pdf", stored_path="/tmp/alien.pdf", mime_type="application/pdf")
    db_session.add(alien_doc)
    db_session.commit()

    res_alien = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id, "document_id": alien_doc.id}
    )
    assert res_alien.status_code == 400
    assert "does not belong to this case" in res_alien.json()["detail"]

def test_c1_client_text_does_not_replace_origin_fragment(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    orig_fragment = ev_1.fragment
    # Cliente intenta enviar texto libre sustituto
    res = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={
            "offer_evidence_id": ev_1.id,
            "fragment": "TEXTO LIBRE INYECTADO POR EL CLIENTE",
            "source_document": "archivo_falso.pdf",
            "notes": "Nota adicional del operador"
        }
    )
    assert res.status_code == 200
    data = res.json()

    # El fragmento originario debe preservarse intacto
    assert data["fragment"] == orig_fragment
    # El source_document proviene del registro UploadedDocument real, no del cliente
    assert data["source_document"] == "propuesta_tecnica.pdf"
    # El texto libre manual se traslada a notes como anotación
    assert "TEXTO LIBRE INYECTADO" in data["notes"]

def test_c1_deleted_uploaded_document_invalidates_verified_status(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # 1. Vincular y verificar
    link_res = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    ).json()
    client.put(
        f"/api/v6/cases/{case.id}/evidence/{link_res['id']}/review",
        json={"verification_status": "VERIFIED"}
    )

    # Evaluación positiva inicial
    evals = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate").json()
    assert any(e["requirement_id"] == req_a.id and e["status"] in ["PASSED", "IMPROVEMENT"] for e in evals)

    # 2. El documento UploadedDocument es eliminado físicamente
    doc = db_session.query(UploadedDocument).filter_by(id=ev_1.document_id).first()
    db_session.delete(doc)
    db_session.commit()

    # 3. La reevaluación debe producir MISSING_DATA a pesar de que el registro diga VERIFIED
    from app.services.v6.evaluation.offer_evaluation_service import OfferEvaluationService
    revoked = OfferEvaluationService().reevaluate_requirement(
        db_session, offer.id, req_a.id, user_id=1, tenant_id="mega_tenant"
    )
    assert revoked.status == "MISSING_DATA"
    assert "No se encontro evidencia documental verificable" in revoked.explanation

    # 4. VFM debe rechazar la oferta
    from app.services.v6.evaluation.vfm_service import ValueForMoneyService
    vfm = ValueForMoneyService(db_session).calculate_vfm(case.id)
    offer_vfm = next(r for r in vfm if r["supplier_offer_id"] == offer.id)
    assert not offer_vfm["is_eligible"]
    assert offer_vfm["reason"] == "MISSING_DATA_MANDATORY_REQUIREMENTS"


# --- CORRECCIÓN 2: Atomicidad de Operación Completa (Zero Mutations on Rollback) ---

def test_c2_injected_failure_before_commit_leaves_zero_mutations(db_session: Session, monkeypatch):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    initial_links_count = db_session.query(OfferRequirementEvidence).count()

    # Evaluar oferta para tener estado base
    client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    eval_base = db_session.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id, requirement_id=req_a.id).first()
    base_eval_status = eval_base.status

    # Inyectar fallo en AuditLog antes del commit final
    from app.models.domain import AuditLog
    orig_init = AuditLog.__init__
    def faulty_audit_init(self, *args, **kwargs):
        if kwargs.get("action") == "LINK_REQUIREMENT_EVIDENCE":
            raise RuntimeError("Injected crash right before audit registration and commit")
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(AuditLog, "__init__", faulty_audit_init)

    with pytest.raises(RuntimeError, match="Injected crash"):
        client.post(
            f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
            json={"offer_evidence_id": ev_1.id}
        )

    # DEMOSTRAR CERO MUTACIONES PERSISTIDAS TRAS EL FALLO:
    # 1. Cero registros creados en offer_requirement_evidences
    after_links_count = db_session.query(OfferRequirementEvidence).count()
    assert after_links_count == initial_links_count

    # 2. Cero registros creados en audit_logs para LINK_REQUIREMENT_EVIDENCE
    link_audits = db_session.query(AuditLog).filter_by(action="LINK_REQUIREMENT_EVIDENCE").count()
    assert link_audits == 0

    # 3. Estado de evaluación inalterado
    db_session.refresh(eval_base)
    assert eval_base.status == base_eval_status


# --- CORRECCIÓN 3: Cerrar el Bypass de VFM ---

def test_c3_new_case_without_associations_and_old_passed_rejected(db_session: Session):
    case, offer, req_a, req_b, _, _ = setup_base_case_data(db_session)
    case.traceability_regime = "P12_STRICT"
    db_session.commit()

    # Simular evaluación PASSED histórica o manual sin asociaciones para ambos requisitos obligatorios
    ev_entry_a = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req_a.id,
        status="PASSED",
        explanation="Evaluacion positiva simulada sin evidencia A"
    )
    ev_entry_b = OfferEvaluation(
        supplier_offer_id=offer.id,
        requirement_id=req_b.id,
        status="PASSED",
        explanation="Evaluacion positiva simulada sin evidencia B"
    )
    db_session.add_all([ev_entry_a, ev_entry_b])
    db_session.commit()

    # VFM debe rechazar la elegibilidad directamente sin requerir reevaluación previa
    from app.services.v6.evaluation.vfm_service import ValueForMoneyService
    vfm = ValueForMoneyService(db_session).calculate_vfm(case.id)
    offer_vfm = next(r for r in vfm if r["supplier_offer_id"] == offer.id)
    assert not offer_vfm["is_eligible"]
    assert offer_vfm["reason"] == "MISSING_DATA_MANDATORY_REQUIREMENTS"

    # SelectionService también debe rechazar sin exigir reevaluación manual
    from app.services.v6.selection.selection_service import SelectionService
    with pytest.raises(ValueError, match="MISSING_DATA"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Intento de proponer oferta con PASSED huerfano",
            user_id=1,
            tenant_id="mega_tenant"
        )

def test_c3_case_loses_last_verified_association_rejected_by_vfm(db_session: Session):
    case, offer, req_a, _, ev_1, _ = setup_base_case_data(db_session)
    client = get_operator_client()

    # Vincular y verificar
    l1 = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence",
        json={"offer_evidence_id": ev_1.id}
    ).json()
    client.put(
        f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review",
        json={"verification_status": "VERIFIED"}
    )
    # Acreditar req_b también para que la oferta sea elegible
    ev_b = db_session.query(OfferEvidence).filter_by(supplier_offer_id=offer.id, document_type="anexo_plazo.pdf").first()
    req_b = db_session.query(CaseRequirementMatrix).filter_by(case_id=case.id, description="Plazo maximo 30 dias").first()
    l2 = client.post(
        f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_b.id}/evidence",
        json={"offer_evidence_id": ev_b.id}
    ).json()
    client.put(
        f"/api/v6/cases/{case.id}/evidence/{l2['id']}/review",
        json={"verification_status": "VERIFIED"}
    )

    # Evaluar: elegible
    from app.services.v6.evaluation.vfm_service import ValueForMoneyService
    vfm_before = ValueForMoneyService(db_session).calculate_vfm(case.id)
    assert next(r for r in vfm_before if r["supplier_offer_id"] == offer.id)["is_eligible"]

    # Desvincular la última evidencia de req_a
    del_res = client.delete(f"/api/v6/cases/{case.id}/evidence/{l1['id']}")
    assert del_res.status_code == 200

    # VFM debe rechazar inmediatamente sin requerir reevaluación manual
    vfm_after = ValueForMoneyService(db_session).calculate_vfm(case.id)
    offer_after = next(r for r in vfm_after if r["supplier_offer_id"] == offer.id)
    assert not offer_after["is_eligible"]
    assert offer_after["reason"] == "MISSING_DATA_MANDATORY_REQUIREMENTS"

def test_c3_evidence_deleted_directly_in_postgresql_rejected(db_session: Session):
    case, offer, req_a, req_b, ev_1, ev_2 = setup_base_case_data(db_session)
    client = get_operator_client()

    # Vincular ambas evidencias
    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()
    l2 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_b.id}/evidence", json={"offer_evidence_id": ev_2.id}).json()
    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "VERIFIED"})
    client.put(f"/api/v6/cases/{case.id}/evidence/{l2['id']}/review", json={"verification_status": "VERIFIED"})

    # Evaluar: inicialmente elegible
    client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
    from app.services.v6.evaluation.vfm_service import ValueForMoneyService
    vfm = ValueForMoneyService(db_session).calculate_vfm(case.id)
    assert next(r for r in vfm if r["supplier_offer_id"] == offer.id)["is_eligible"]

    # Eliminar OfferEvidence directamente de la base de datos (simulando SQL manual)
    db_session.delete(ev_1)
    db_session.commit()

    # VFM debe detectar la falta de respaldo activo y rechazar la elegibilidad inmediatamente
    vfm_direct = ValueForMoneyService(db_session).calculate_vfm(case.id)
    offer_direct = next(r for r in vfm_direct if r["supplier_offer_id"] == offer.id)
    assert not offer_direct["is_eligible"]
    assert offer_direct["reason"] == "MISSING_DATA_MANDATORY_REQUIREMENTS"

def test_c3_two_offers_two_requirements_independent(db_session: Session):
    case, offer_1, req_a, req_b, ev_1, ev_2 = setup_base_case_data(db_session)
    client = get_operator_client()

    # Crear una segunda oferta
    sup2 = Supplier(ruc="20999111222", business_name="Segunda Empresa SAC", tenant_id="mega_tenant")
    db_session.add(sup2)
    db_session.flush()
    db_session.add(SupplierProfile(supplier_id=sup2.id, validation_status="VERIFIED"))
    offer_2 = SupplierOffer(case_id=case.id, supplier_id=sup2.id, status="SUBMITTED", currency="PEN", price=12000.0, total_amount=12000.0, evaluation_status="PENDING")
    db_session.add(offer_2)
    db_session.flush()
    p_item = db_session.query(CaseProcurementItem).filter_by(case_id=case.id).first()
    db_session.add(SupplierOfferItem(supplier_offer_id=offer_2.id, procurement_item_id=p_item.id, description="Servidor Empresarial", quantity=1.0, unit="UND", unit_price=12000.0))
    doc_2 = UploadedDocument(case_id=case.id, document_type="quotation", original_filename="doc_oferta2.pdf", stored_path="/tmp/doc2.pdf", mime_type="application/pdf")
    db_session.add(doc_2)
    db_session.flush()
    ev_2_a = OfferEvidence(supplier_offer_id=offer_2.id, document_id=doc_2.id, document_type="doc_oferta2.pdf", page=1, fragment="Garantia 36 meses", confidence=0.95)
    db_session.add(ev_2_a)
    db_session.commit()

    # Oferta 1: se vincula y verifica para AMBOS requisitos
    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer_1.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()
    l2 = client.post(f"/api/v6/cases/{case.id}/offers/{offer_1.id}/requirements/{req_b.id}/evidence", json={"offer_evidence_id": ev_2.id}).json()
    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "VERIFIED"})
    client.put(f"/api/v6/cases/{case.id}/evidence/{l2['id']}/review", json={"verification_status": "VERIFIED"})

    # Oferta 2: solo vincula req_a pero NO req_b
    l2_a = client.post(f"/api/v6/cases/{case.id}/offers/{offer_2.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_2_a.id}).json()
    client.put(f"/api/v6/cases/{case.id}/evidence/{l2_a['id']}/review", json={"verification_status": "VERIFIED"})

    client.post(f"/api/v6/cases/{case.id}/offers/{offer_1.id}/evaluate")
    client.post(f"/api/v6/cases/{case.id}/offers/{offer_2.id}/evaluate")

    from app.services.v6.evaluation.vfm_service import ValueForMoneyService
    vfm = ValueForMoneyService(db_session).calculate_vfm(case.id)
    vfm_1 = next(r for r in vfm if r["supplier_offer_id"] == offer_1.id)
    vfm_2 = next(r for r in vfm if r["supplier_offer_id"] == offer_2.id)

    # Oferta 1 tiene respaldo completo -> elegible
    assert vfm_1["is_eligible"]
    # Oferta 2 carece de respaldo en req_b -> no elegible
    assert not vfm_2["is_eligible"]

def test_c3_supervisor_cannot_propose_offer_with_deleted_evidence(db_session: Session):
    case, offer, req_a, req_b, ev_1, ev_2 = setup_base_case_data(db_session)
    client = get_operator_client()

    l1 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_a.id}/evidence", json={"offer_evidence_id": ev_1.id}).json()
    l2 = client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/requirements/{req_b.id}/evidence", json={"offer_evidence_id": ev_2.id}).json()
    client.put(f"/api/v6/cases/{case.id}/evidence/{l1['id']}/review", json={"verification_status": "VERIFIED"})
    client.put(f"/api/v6/cases/{case.id}/evidence/{l2['id']}/review", json={"verification_status": "VERIFIED"})
    client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")

    # Eliminar evidencia de PostgreSQL
    db_session.delete(ev_1)
    db_session.commit()

    # Supervisor intenta proponer la oferta
    from app.services.v6.selection.selection_service import SelectionService
    with pytest.raises(ValueError, match="Cannot propose an ineligible offer: Mandatory requirement evaluation has missing data"):
        SelectionService.propose_selection(
            db=db_session,
            case_id=case.id,
            supplier_offer_id=offer.id,
            justification="Supervisor propone oferta sin evidencia documental viva",
            user_id=2, # supervisor
            user_role="SUPERVISOR",
            tenant_id="mega_tenant"
        )

