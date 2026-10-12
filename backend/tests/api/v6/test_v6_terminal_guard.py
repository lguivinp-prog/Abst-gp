"""
Comprehensive test suite for V6 terminal state immutability.

Tests that APPROVED and COMPLETED cases reject business mutations (HTTP 409)
while allowing legitimate read operations without side-effects.
Validates before/after record integrity, authorization boundaries, and tenant isolation.
"""
import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.domain import CaseFile, UploadedDocument
from app.models.v6.supplier import Supplier
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.contractual_condition import ContractualCondition
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.case_procurement_item import CaseProcurementItem
from app.models.v6.supplier_offer_contract_term import SupplierOfferContractTerm
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.validation_request import ValidationRequest
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def terminal_cases(db_session: Session, setup_mega_tenant):
    """
    Create APPROVED and COMPLETED cases with complete linked entity graphs:
    suppliers, offers, requirements, procurement items, contract terms,
    evaluations, contractual conditions, documents, validations, and selections.
    """
    case_approved = CaseFile(
        title="Test V6 Case Approved",
        contract_type="Bienes",
        status="APPROVED",
        tenant_id="mega_tenant",
        assigned_to_user_id=1,
    )
    case_completed = CaseFile(
        title="Test V6 Case Completed",
        contract_type="Bienes",
        status="COMPLETED",
        tenant_id="mega_tenant",
        assigned_to_user_id=1,
    )
    db_session.add_all([case_approved, case_completed])
    db_session.commit()

    supplier = db_session.query(Supplier).filter_by(ruc="12345678901").first()
    if not supplier:
        supplier = Supplier(
            tenant_id="mega_tenant",
            ruc="12345678901",
            business_name="Test Supplier",
        )
        db_session.add(supplier)
        db_session.commit()

    # Synchronize sequence to avoid duplicate primary key collisions
    db_session.execute(text("SELECT setval('suppliers_id_seq', (SELECT COALESCE(MAX(id), 1) FROM suppliers))"))
    db_session.commit()

    for case in [case_approved, case_completed]:
        # Offer
        offer = SupplierOffer(
            case_id=case.id,
            supplier_id=supplier.id,
            total_amount=150.0,
            status="PENDING",
        )
        db_session.add(offer)
        db_session.flush()

        # Requirement
        req = CaseRequirementMatrix(
            case_id=case.id,
            requirement_type="TECHNICAL",
            description=f"Server requirement for case {case.id}",
            mandatory=True,
            status="VALIDATED",
        )
        db_session.add(req)
        db_session.flush()

        # Procurement Item
        item = CaseProcurementItem(
            case_id=case.id,
            item_number=f"ITEM-{case.id}",
            description=f"Hardware item for case {case.id}",
            quantity=2,
            unit="UNIDAD",
            status="VALIDATED",
        )
        db_session.add(item)

        # Contract Term
        term = SupplierOfferContractTerm(
            supplier_offer_id=offer.id,
            key="DELIVERY_TERM",
            label="Plazo de entrega",
            value_text="30 dias",
            numeric_value=30.0,
            unit="DIAS",
        )
        db_session.add(term)

        # Offer Evaluation
        eval_row = OfferEvaluation(
            supplier_offer_id=offer.id,
            requirement_id=req.id,
            status="PASSED",
            explanation="Cumple especificaciones",
            evaluation_confidence=0.98,
        )
        db_session.add(eval_row)

        # Contractual Condition
        cond = ContractualCondition(
            supplier_offer_id=offer.id,
            key="WARRANTY",
            label="Garantia",
            required_value="24 meses",
            offered_value="24 meses",
            resolution_rule="EXACT",
            status="MET",
        )
        db_session.add(cond)

        # Uploaded Document
        doc = UploadedDocument(
            case_id=case.id,
            original_filename=f"bases_case_{case.id}.pdf",
            document_type="bases",
            stored_path=f"/data/uploads/bases_case_{case.id}.pdf",
            mime_type="application/pdf",
            text_extracted="Contenido de bases tecnicas",
            processing_status="completed",
        )
        db_session.add(doc)

        # Validation Request
        val_req = ValidationRequest(
            case_id=case.id,
            supplier_id=supplier.id,
            source="SUNAT",
            status="COMPLETED",
            validation_mode="AUTOMATIC",
        )
        db_session.add(val_req)

    # Add Selection attempt and final result for APPROVED case
    offer_approved = db_session.query(SupplierOffer).filter_by(case_id=case_approved.id).first()
    attempt = SupplierSelectionAttempt(
        case_id=case_approved.id,
        supplier_offer_id=offer_approved.id,
        status="APPROVED",
        justification_comment="Oferta adjudicada validada",
        selected_by=1,
    )
    db_session.add(attempt)
    db_session.flush()

    final = SupplierSelectionFinal(
        case_id=case_approved.id,
        attempt_id=attempt.id,
    )
    db_session.add(final)
    db_session.commit()

    return {"APPROVED": case_approved, "COMPLETED": case_completed}


@pytest.fixture
def active_case(db_session, setup_mega_tenant):
    """Create an active (CREATED) case for positive-path tests."""
    case = CaseFile(
        title="Test V6 Active Case",
        contract_type="Bienes",
        status="CREATED",
        tenant_id="mega_tenant",
        assigned_to_user_id=1,
    )
    db_session.add(case)
    db_session.commit()
    return case


@pytest.fixture
def waiting_case(db_session, setup_mega_tenant):
    """Create a WAITING_QUOTATION case with supplier/offer for positive tests."""
    case = CaseFile(
        title="Test V6 Waiting Case",
        contract_type="Bienes",
        status="WAITING_QUOTATION",
        tenant_id="mega_tenant",
        assigned_to_user_id=1,
    )
    db_session.add(case)
    db_session.commit()

    supplier = db_session.query(Supplier).filter_by(ruc="12345678901").first()
    if not supplier:
        supplier = Supplier(
            tenant_id="mega_tenant",
            ruc="12345678901",
            business_name="Test Supplier",
        )
        db_session.add(supplier)
        db_session.commit()

    db_session.execute(text("SELECT setval('suppliers_id_seq', (SELECT COALESCE(MAX(id), 1) FROM suppliers))"))
    db_session.commit()

    offer = SupplierOffer(
        case_id=case.id,
        supplier_id=supplier.id,
        total_amount=0,
        status="PENDING",
    )
    db_session.add(offer)
    db_session.commit()

    return {"case": case, "offer": offer, "supplier": supplier}


@pytest.fixture
def other_tenant_client(db_session):
    """Client authenticated as ADMIN for a completely different tenant."""
    from app.main import app
    from app.api.auth import get_current_active_user, get_current_user
    from app.models.domain import User, Tenant

    tenant = db_session.query(Tenant).filter_by(id="other_tenant").first()
    if not tenant:
        tenant = Tenant(id="other_tenant", name="Other Tenant")
        db_session.add(tenant)
        db_session.commit()

    def override_other_user():
        return User(
            id=99,
            username="other_admin",
            role="ADMIN",
            is_active=True,
            must_change_password=False,
            tenant_id="other_tenant",
        )

    app.dependency_overrides[get_current_active_user] = override_other_user
    app.dependency_overrides[get_current_user] = override_other_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unassigned_operator_client(db_session):
    """Client authenticated as OPERATOR within mega_tenant but NOT assigned to the case."""
    from app.main import app
    from app.api.auth import get_current_active_user, get_current_user
    from app.models.domain import User

    def override_unassigned_op():
        return User(
            id=88,
            username="unassigned_op",
            role="OPERATOR",
            is_active=True,
            must_change_password=False,
            tenant_id="mega_tenant",
        )

    app.dependency_overrides[get_current_active_user] = override_unassigned_op
    app.dependency_overrides[get_current_user] = override_unassigned_op
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauthenticated_client():
    """Client with zero credentials."""
    from app.main import app
    from app.api.auth import get_current_active_user, get_current_user

    old_active = app.dependency_overrides.pop(get_current_active_user, None)
    old_user = app.dependency_overrides.pop(get_current_user, None)
    with TestClient(app) as c:
        yield c
    if old_active:
        app.dependency_overrides[get_current_active_user] = old_active
    if old_user:
        app.dependency_overrides[get_current_user] = old_user


# ===========================================================================
# A. Terminal guard blocks mutations — 21 endpoints parametrized over APPROVED & COMPLETED
# ===========================================================================

@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
class TestTerminalGuardBlocksMutations:
    """All 21 mutating endpoints MUST return 409 for terminal cases."""

    # --- 1-3. Requirements ---

    def test_post_requirements(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/requirements",
            json={"requirement_type": "TECHNICAL", "description": "Desc", "mandatory": True},
        )
        assert resp.status_code == 409

    def test_put_requirements(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.put(
            f"/api/v6/cases/{case.id}/requirements/999",
            json={"status": "VALIDATED", "description": "X", "reason": "test"},
        )
        assert resp.status_code == 409

    def test_post_requirements_confirm(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.post(f"/api/v6/cases/{case.id}/requirements/confirm")
        assert resp.status_code == 409

    # --- 4-6. Procurement Items ---

    def test_post_procurement_items(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/procurement-items",
            json={"item_number": "1", "description": "D", "quantity": 1, "unit": "U"},
        )
        assert resp.status_code == 409

    def test_put_procurement_items(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.put(
            f"/api/v6/cases/{case.id}/procurement-items/999",
            json={"description": "D", "quantity": 1, "unit": "U"},
        )
        assert resp.status_code == 409

    def test_delete_procurement_items(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.delete(f"/api/v6/cases/{case.id}/procurement-items/999")
        assert resp.status_code == 409

    # --- 7-8. Suppliers ---

    def test_post_suppliers(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/suppliers",
            json={"ruc": "12345678901", "business_name": "Test"},
        )
        assert resp.status_code == 409

    def test_delete_suppliers(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        supplier = db_session.query(Supplier).filter_by(ruc="12345678901").first()
        resp = admin_client.delete(f"/api/v6/cases/{case.id}/suppliers/{supplier.id}")
        assert resp.status_code == 409

    # --- 9-11. Offers ---

    def test_post_offers(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        supplier = db_session.query(Supplier).filter_by(ruc="12345678901").first()
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/offers",
            json={"supplier_id": supplier.id},
        )
        assert resp.status_code == 409

    def test_put_offers(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
        resp = admin_client.put(
            f"/api/v6/cases/{case.id}/offers/{offer.id}",
            json={"price": 999.99},
        )
        assert resp.status_code == 409

    def test_delete_offers(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
        resp = admin_client.delete(f"/api/v6/cases/{case.id}/offers/{offer.id}")
        assert resp.status_code == 409

    # --- 12-13. Evaluations ---

    def test_put_evaluations(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.put(
            f"/api/v6/cases/{case.id}/evaluations/999",
            json={"status": "MET", "explanation": "Ok"},
        )
        assert resp.status_code == 409

    def test_post_evaluate_offer(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
        resp = admin_client.post(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluate")
        assert resp.status_code == 409

    # --- 14-15. Selection & Approval ---

    def test_post_selection(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/selection",
            json={"supplier_offer_id": offer.id, "justification_comment": "Ok"},
        )
        assert resp.status_code == 409

    def test_post_approve(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.post(f"/api/v6/cases/{case.id}/approve")
        assert resp.status_code == 409

    # --- 16. Documents ---

    def test_post_documents(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake")
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/documents",
            data={"document_type": "oferta"},
            files={"file": ("test.pdf", fake_pdf, "application/pdf")},
        )
        assert resp.status_code == 409

    # --- 17-18. Validations ---

    def test_post_validations(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        supplier = db_session.query(Supplier).filter_by(ruc="12345678901").first()
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/suppliers/{supplier.id}/validations",
            json={"source": "SUNAT"},
        )
        assert resp.status_code == 409

    def test_post_manual_validations(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        supplier = db_session.query(Supplier).filter_by(ruc="12345678901").first()
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/suppliers/{supplier.id}/validations/manual",
            json={"source": "SUNAT", "result": "VALIDATED", "observation": "Test"},
        )
        assert resp.status_code == 409

    # --- 19. Offer Terms Extraction ---

    def test_post_offer_terms_extract(self, admin_client, db_session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/offers/{offer.id}/terms/extract",
            params={"text": "test text", "document_name": "test.pdf"},
        )
        assert resp.status_code == 409

    # --- 20-21. Requirement Upload & Extraction ---

    def test_post_requirements_upload(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake")
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/requirements/upload",
            files={"file": ("test.pdf", fake_pdf, "application/pdf")},
        )
        assert resp.status_code == 409

    def test_post_requirements_extract(self, admin_client, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.post(
            f"/api/v6/cases/{case.id}/requirements/extract",
            json={"document_id": 999},
        )
        assert resp.status_code == 409


# ===========================================================================
# B. 409 response body validation
# ===========================================================================

@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_terminal_guard_response_body(admin_client, terminal_cases, status_key):
    """Verify the 409 response includes the standard terminal message."""
    case = terminal_cases[status_key]
    resp = admin_client.post(
        f"/api/v6/cases/{case.id}/requirements",
        json={"requirement_type": "TECHNICAL", "description": "D", "mandatory": True},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert "terminal" in body.get("detail", "").lower()


# ===========================================================================
# C. GET endpoints are strictly side-effect-free with record-level comparison
# ===========================================================================

@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
class TestTerminalGetSideEffectFree:
    """
    GET endpoints must return 200, match seeded records, and NOT alter any database
    rows, values, or case status.
    """

    def test_get_requirements(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        before_rows = (
            db_session.query(CaseRequirementMatrix)
            .filter_by(case_id=case.id)
            .order_by(CaseRequirementMatrix.id)
            .all()
        )
        before_data = [
            {"id": r.id, "type": r.requirement_type, "desc": r.description, "mandatory": r.mandatory, "status": r.status}
            for r in before_rows
        ]
        assert len(before_data) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/requirements")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_data)

        db_session.expire_all()
        after_rows = (
            db_session.query(CaseRequirementMatrix)
            .filter_by(case_id=case.id)
            .order_by(CaseRequirementMatrix.id)
            .all()
        )
        after_data = [
            {"id": r.id, "type": r.requirement_type, "desc": r.description, "mandatory": r.mandatory, "status": r.status}
            for r in after_rows
        ]
        assert before_data == after_data, "Requirements must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_procurement_items(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        before_rows = (
            db_session.query(CaseProcurementItem)
            .filter_by(case_id=case.id)
            .order_by(CaseProcurementItem.id)
            .all()
        )
        before_data = [
            {"id": r.id, "item_number": r.item_number, "desc": r.description, "qty": float(r.quantity), "unit": r.unit}
            for r in before_rows
        ]
        assert len(before_data) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/procurement-items")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_data)

        db_session.expire_all()
        after_rows = (
            db_session.query(CaseProcurementItem)
            .filter_by(case_id=case.id)
            .order_by(CaseProcurementItem.id)
            .all()
        )
        after_data = [
            {"id": r.id, "item_number": r.item_number, "desc": r.description, "qty": float(r.quantity), "unit": r.unit}
            for r in after_rows
        ]
        assert before_data == after_data, "Procurement items must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_offers(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        before_rows = (
            db_session.query(SupplierOffer)
            .filter_by(case_id=case.id)
            .order_by(SupplierOffer.id)
            .all()
        )
        before_data = [
            {"id": r.id, "supplier_id": r.supplier_id, "total": float(r.total_amount), "status": r.status}
            for r in before_rows
        ]
        assert len(before_data) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/offers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_data)

        db_session.expire_all()
        after_rows = (
            db_session.query(SupplierOffer)
            .filter_by(case_id=case.id)
            .order_by(SupplierOffer.id)
            .all()
        )
        after_data = [
            {"id": r.id, "supplier_id": r.supplier_id, "total": float(r.total_amount), "status": r.status}
            for r in after_rows
        ]
        assert before_data == after_data, "Offers must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_offer_detail(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
        before_snapshot = {
            "id": offer.id,
            "case_id": offer.case_id,
            "supplier_id": offer.supplier_id,
            "total_amount": float(offer.total_amount),
            "status": offer.status,
        }

        resp = admin_client.get(f"/api/v6/cases/{case.id}/offers/{offer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == offer.id
        assert float(data["total_amount"]) == before_snapshot["total_amount"]

        db_session.expire_all()
        after_offer = db_session.query(SupplierOffer).filter_by(id=offer.id).first()
        after_snapshot = {
            "id": after_offer.id,
            "case_id": after_offer.case_id,
            "supplier_id": after_offer.supplier_id,
            "total_amount": float(after_offer.total_amount),
            "status": after_offer.status,
        }
        assert before_snapshot == after_snapshot, "Offer detail must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_offer_terms(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
        before_rows = (
            db_session.query(SupplierOfferContractTerm)
            .filter_by(supplier_offer_id=offer.id)
            .order_by(SupplierOfferContractTerm.id)
            .all()
        )
        before_data = [
            {"id": r.id, "key": r.key, "label": r.label, "val": r.value_text, "num": r.numeric_value, "unit": r.unit}
            for r in before_rows
        ]
        assert len(before_data) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/offers/{offer.id}/terms")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_data)

        db_session.expire_all()
        after_rows = (
            db_session.query(SupplierOfferContractTerm)
            .filter_by(supplier_offer_id=offer.id)
            .order_by(SupplierOfferContractTerm.id)
            .all()
        )
        after_data = [
            {"id": r.id, "key": r.key, "label": r.label, "val": r.value_text, "num": r.numeric_value, "unit": r.unit}
            for r in after_rows
        ]
        assert before_data == after_data, "Contract terms must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_evaluations(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offers = db_session.query(SupplierOffer).filter_by(case_id=case.id).all()
        offer_ids = [o.id for o in offers]
        before_rows = (
            db_session.query(OfferEvaluation)
            .filter(OfferEvaluation.supplier_offer_id.in_(offer_ids))
            .order_by(OfferEvaluation.id)
            .all()
        )
        before_data = [
            {"id": r.id, "offer_id": r.supplier_offer_id, "req_id": r.requirement_id, "status": r.status, "exp": r.explanation}
            for r in before_rows
        ]
        assert len(before_data) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/evaluations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_data)

        db_session.expire_all()
        after_rows = (
            db_session.query(OfferEvaluation)
            .filter(OfferEvaluation.supplier_offer_id.in_(offer_ids))
            .order_by(OfferEvaluation.id)
            .all()
        )
        after_data = [
            {"id": r.id, "offer_id": r.supplier_offer_id, "req_id": r.requirement_id, "status": r.status, "exp": r.explanation}
            for r in after_rows
        ]
        assert before_data == after_data, "Evaluations must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_offer_evaluations(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
        before_rows = (
            db_session.query(OfferEvaluation)
            .filter_by(supplier_offer_id=offer.id)
            .order_by(OfferEvaluation.id)
            .all()
        )
        before_data = [
            {"id": r.id, "req_id": r.requirement_id, "status": r.status, "exp": r.explanation}
            for r in before_rows
        ]
        assert len(before_data) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/offers/{offer.id}/evaluations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_data)

        db_session.expire_all()
        after_rows = (
            db_session.query(OfferEvaluation)
            .filter_by(supplier_offer_id=offer.id)
            .order_by(OfferEvaluation.id)
            .all()
        )
        after_data = [
            {"id": r.id, "req_id": r.requirement_id, "status": r.status, "exp": r.explanation}
            for r in after_rows
        ]
        assert before_data == after_data, "Offer evaluations must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_suppliers(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        offers = db_session.query(SupplierOffer).filter_by(case_id=case.id).all()
        before_suppliers = [
            {"id": o.supplier.id, "ruc": o.supplier.ruc, "name": o.supplier.business_name}
            for o in offers
        ]
        assert len(before_suppliers) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/suppliers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_suppliers)

        db_session.expire_all()
        after_offers = db_session.query(SupplierOffer).filter_by(case_id=case.id).all()
        after_suppliers = [
            {"id": o.supplier.id, "ruc": o.supplier.ruc, "name": o.supplier.business_name}
            for o in after_offers
        ]
        assert before_suppliers == after_suppliers, "Suppliers must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_documents(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        before_rows = (
            db_session.query(UploadedDocument)
            .filter_by(case_id=case.id)
            .order_by(UploadedDocument.id)
            .all()
        )
        before_data = [
            {"id": r.id, "filename": r.original_filename, "doc_type": r.document_type, "status": r.processing_status}
            for r in before_rows
        ]
        assert len(before_data) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_data)

        db_session.expire_all()
        after_rows = (
            db_session.query(UploadedDocument)
            .filter_by(case_id=case.id)
            .order_by(UploadedDocument.id)
            .all()
        )
        after_data = [
            {"id": r.id, "filename": r.original_filename, "doc_type": r.document_type, "status": r.processing_status}
            for r in after_rows
        ]
        assert before_data == after_data, "Documents must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_validations(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        before_rows = (
            db_session.query(ValidationRequest)
            .filter_by(case_id=case.id)
            .order_by(ValidationRequest.id)
            .all()
        )
        before_data = [
            {"id": r.id, "source": r.source, "status": r.status, "mode": r.validation_mode}
            for r in before_rows
        ]
        assert len(before_data) > 0

        resp = admin_client.get(f"/api/v6/cases/{case.id}/validations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(before_data)

        db_session.expire_all()
        after_rows = (
            db_session.query(ValidationRequest)
            .filter_by(case_id=case.id)
            .order_by(ValidationRequest.id)
            .all()
        )
        after_data = [
            {"id": r.id, "source": r.source, "status": r.status, "mode": r.validation_mode}
            for r in after_rows
        ]
        assert before_data == after_data, "Validations must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_selection(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        before_attempt = (
            db_session.query(SupplierSelectionAttempt)
            .filter_by(case_id=case.id)
            .order_by(SupplierSelectionAttempt.id.desc())
            .first()
        )
        before_status = before_attempt.status if before_attempt else None

        resp = admin_client.get(f"/api/v6/cases/{case.id}/selection")
        assert resp.status_code == 200

        db_session.expire_all()
        after_attempt = (
            db_session.query(SupplierSelectionAttempt)
            .filter_by(case_id=case.id)
            .order_by(SupplierSelectionAttempt.id.desc())
            .first()
        )
        after_status = after_attempt.status if after_attempt else None
        assert before_status == after_status, "Selection attempt must remain unmodified after GET"
        db_session.refresh(case)
        assert case.status == status_key

    def test_get_vfm(self, admin_client, db_session: Session, terminal_cases, status_key):
        case = terminal_cases[status_key]
        resp = admin_client.get(f"/api/v6/cases/{case.id}/evaluations/vfm")
        assert resp.status_code == 200

        db_session.refresh(case)
        assert case.status == status_key


@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_contractual_get_side_effect_free(
    admin_client: TestClient, db_session: Session, terminal_cases, status_key
):
    """
    Contractual GET must NOT delete or re-resolve ContractualCondition rows
    for terminal cases. Validates all field values before and after.
    """
    case = terminal_cases[status_key]
    offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()

    # Pre-existing condition snapshot
    before_rows = (
        db_session.query(ContractualCondition)
        .filter_by(supplier_offer_id=offer.id)
        .order_by(ContractualCondition.id)
        .all()
    )
    assert len(before_rows) > 0, "Precondition: terminal case must have seeded conditions"

    before_snapshot = [
        {
            "id": r.id,
            "key": r.key,
            "label": r.label,
            "required_value": r.required_value,
            "offered_value": r.offered_value,
            "resolution_rule": r.resolution_rule,
            "status": r.status,
        }
        for r in before_rows
    ]

    response = admin_client.get(f"/api/v6/cases/{case.id}/evaluations/contractual")
    assert response.status_code == 200
    resp_data = response.json()
    assert len(resp_data) == len(before_snapshot)

    # Compare response payload against DB snapshot
    resp_snapshot = [
        {
            "id": item["id"],
            "key": item["key"],
            "label": item["label"],
            "required_value": item["required_value"],
            "offered_value": item["offered_value"],
            "resolution_rule": item["resolution_rule"],
            "status": item["status"],
        }
        for item in resp_data
    ]
    assert resp_snapshot == before_snapshot

    # Re-query DB to verify zero mutation
    db_session.expire_all()
    after_rows = (
        db_session.query(ContractualCondition)
        .filter_by(supplier_offer_id=offer.id)
        .order_by(ContractualCondition.id)
        .all()
    )
    after_snapshot = [
        {
            "id": r.id,
            "key": r.key,
            "label": r.label,
            "required_value": r.required_value,
            "offered_value": r.offered_value,
            "resolution_rule": r.resolution_rule,
            "status": r.status,
        }
        for r in after_rows
    ]

    assert before_snapshot == after_snapshot, (
        "Contractual GET must not delete, recreate, or mutate condition rows on terminal cases"
    )

    db_session.refresh(case)
    assert case.status == status_key


def test_approved_case_get_result(admin_client, db_session: Session, terminal_cases):
    """GET /cases/{case_id}/result on APPROVED case returns final selection without side effects."""
    case = terminal_cases["APPROVED"]
    before_final = db_session.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()
    assert before_final is not None

    resp = admin_client.get(f"/api/v6/cases/{case.id}/result")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == case.id
    assert data["status"] == "APPROVED"
    assert data["supplier_name"] == "Test Supplier"

    db_session.expire_all()
    after_final = db_session.query(SupplierSelectionFinal).filter_by(case_id=case.id).first()
    assert after_final.attempt_id == before_final.attempt_id


# ===========================================================================
# D. Active case allows mutations (positive path)
# ===========================================================================

def test_active_case_allows_create_requirement(admin_client, active_case):
    """A CREATED case must accept requirement creation (status 200)."""
    resp = admin_client.post(
        f"/api/v6/cases/{active_case.id}/requirements",
        json={"requirement_type": "TECHNICAL", "description": "16GB RAM", "mandatory": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "16GB RAM"


def test_active_case_allows_create_procurement_item(admin_client, active_case):
    """A CREATED case must accept procurement item creation."""
    resp = admin_client.post(
        f"/api/v6/cases/{active_case.id}/procurement-items",
        json={"description": "Laptop", "quantity": 5, "unit": "UNIDAD"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "Laptop"


def test_waiting_case_allows_link_supplier(admin_client, waiting_case):
    """A WAITING_QUOTATION case must accept supplier linking."""
    case = waiting_case["case"]
    resp = admin_client.post(
        f"/api/v6/cases/{case.id}/suppliers",
        json={"ruc": "20999888777", "business_name": "New Supplier SAC"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ruc"] == "20999888777"
    assert data["business_name"] == "New Supplier SAC"


# ===========================================================================
# E. Data persistence — mutations are truly rejected, not just error-coded
# ===========================================================================

@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_terminal_mutation_does_not_persist(
    admin_client, db_session, terminal_cases, status_key
):
    """After a rejected mutation, verify no data was created in the DB."""
    case = terminal_cases[status_key]
    before_count = (
        db_session.query(CaseRequirementMatrix)
        .filter_by(case_id=case.id)
        .count()
    )

    resp = admin_client.post(
        f"/api/v6/cases/{case.id}/requirements",
        json={"requirement_type": "LEGAL", "description": "Ghost row", "mandatory": True},
    )
    assert resp.status_code == 409

    after_count = (
        db_session.query(CaseRequirementMatrix)
        .filter_by(case_id=case.id)
        .count()
    )
    assert before_count == after_count, "Rejected mutation must not create any rows"


@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_terminal_offer_delete_does_not_persist(
    admin_client, db_session, terminal_cases, status_key
):
    """Offer delete on terminal case must not remove the offer from DB."""
    case = terminal_cases[status_key]
    offer = db_session.query(SupplierOffer).filter_by(case_id=case.id).first()
    assert offer is not None

    resp = admin_client.delete(f"/api/v6/cases/{case.id}/offers/{offer.id}")
    assert resp.status_code == 409

    db_session.expire_all()
    still_exists = db_session.query(SupplierOffer).filter_by(id=offer.id).first()
    assert still_exists is not None, "Offer must still exist after rejected delete"


# ===========================================================================
# F. Authorization, Role Checks & Tenant Isolation
# ===========================================================================

@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_operator_assigned_gets_409(client, terminal_cases, status_key):
    """
    An OPERATOR assigned to the terminal case is authorized to access it,
    but gets 409 Conflict when attempting mutation (terminal guard fires).
    """
    case = terminal_cases[status_key]
    resp = client.post(
        f"/api/v6/cases/{case.id}/requirements",
        json={"requirement_type": "TECHNICAL", "description": "D", "mandatory": True},
    )
    assert resp.status_code == 409


@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_operator_unassigned_gets_404(unassigned_operator_client, terminal_cases, status_key):
    """
    An OPERATOR not assigned to the case gets 404 Not Found (IDOR protection).
    The terminal state is never leaked to unauthorized operators.
    """
    case = terminal_cases[status_key]
    resp = unassigned_operator_client.post(
        f"/api/v6/cases/{case.id}/requirements",
        json={"requirement_type": "TECHNICAL", "description": "D", "mandatory": True},
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_cross_tenant_gets_404(other_tenant_client, terminal_cases, status_key):
    """
    A user from another tenant receives 404 Not Found for both read and write,
    ensuring multi-tenant boundary is strictly preserved.
    """
    case = terminal_cases[status_key]
    # Write attempt
    resp_post = other_tenant_client.post(
        f"/api/v6/cases/{case.id}/requirements",
        json={"requirement_type": "TECHNICAL", "description": "D", "mandatory": True},
    )
    assert resp_post.status_code == 404

    # Read attempt
    resp_get = other_tenant_client.get(f"/api/v6/cases/{case.id}/requirements")
    assert resp_get.status_code == 404


@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_unauthenticated_client_gets_401(unauthenticated_client, terminal_cases, status_key):
    """
    An unauthenticated request must receive 401 Unauthorized before any business
    or lifecycle checks take place.
    """
    case = terminal_cases[status_key]
    resp = unauthenticated_client.post(
        f"/api/v6/cases/{case.id}/requirements",
        json={"requirement_type": "TECHNICAL", "description": "D", "mandatory": True},
    )
    assert resp.status_code == 401


# ===========================================================================
# G. Case status is never altered by blocked operations
# ===========================================================================

@pytest.mark.parametrize("status_key", ["APPROVED", "COMPLETED"])
def test_case_status_unchanged_after_blocked_mutation(
    admin_client, db_session, terminal_cases, status_key
):
    """Case status must remain exactly the same after multiple blocked mutations."""
    case = terminal_cases[status_key]
    original_status = case.status

    admin_client.post(
        f"/api/v6/cases/{case.id}/requirements",
        json={"requirement_type": "LEGAL", "description": "X", "mandatory": True},
    )
    admin_client.post(
        f"/api/v6/cases/{case.id}/suppliers",
        json={"ruc": "11111111111", "business_name": "Phantom"},
    )
    admin_client.post(f"/api/v6/cases/{case.id}/approve")

    db_session.refresh(case)
    assert case.status == original_status
