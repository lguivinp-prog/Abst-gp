import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import AuditLog, CaseFile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.case_procurement_item import CaseProcurementItem
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier import Supplier

def test_history_list(client: TestClient, db_session: Session, test_case_file):
    # Create dummy audit log
    audit = AuditLog(
        user_id=1,
        tenant_id="mega_tenant",
        action="TEST_ACTION",
        entity_type="CaseFile",
        entity_id=str(test_case_file.id),
        details="Test details",
        status="SUCCESS"
    )
    db_session.add(audit)
    db_session.commit()

    response = client.get(
        f"/api/v6/cases/{test_case_file.id}/history",
        headers={"Authorization": "Bearer test_token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["action"] == "TEST_ACTION"

def test_history_includes_related_entities_and_excludes_unrelated(client: TestClient, db_session: Session, test_case_file):
    # Related entities for test_case_file
    req = CaseRequirementMatrix(case_id=test_case_file.id, requirement_type="TECNICO", description="Papel 75g", mandatory=True)
    db_session.add(req)
    item = CaseProcurementItem(case_id=test_case_file.id, item_number="1", description="Papel bond", quantity=50, unit="MILLAR")
    db_session.add(item)
    sup = Supplier(ruc="20999888777", business_name="Papelera Test SAC", tenant_id="mega_tenant")
    db_session.add(sup)
    db_session.flush()
    offer = SupplierOffer(case_id=test_case_file.id, supplier_id=sup.id, price=2500.0, total_amount=2360.0, status="PENDING")
    db_session.add(offer)

    # Unrelated case in same tenant
    other_case = CaseFile(title="Other Case", contract_type="BIENES", status="WAITING_QUOTATION", tenant_id="mega_tenant")
    db_session.add(other_case)
    db_session.flush()
    other_req = CaseRequirementMatrix(case_id=other_case.id, requirement_type="TECNICO", description="Other Req", mandatory=True)
    db_session.add(other_req)
    db_session.flush()

    # Audit logs for test_case_file related entities
    log_case = AuditLog(user_id=1, tenant_id="mega_tenant", action="CASE_STATUS_CHANGE", entity_type="CaseFile", entity_id=str(test_case_file.id), details="Status WAITING_QUOTATION")
    log_req = AuditLog(user_id=1, tenant_id="mega_tenant", action="CREATE_REQUIREMENT", entity_type="CaseRequirementMatrix", entity_id=str(req.id), details="Req created")
    log_item = AuditLog(user_id=1, tenant_id="mega_tenant", action="CREATE_PROCUREMENT_ITEM", entity_type="CaseProcurementItem", entity_id=str(item.id), details="Item 1 created")
    log_offer = AuditLog(user_id=1, tenant_id="mega_tenant", action="CREATE_OFFER", entity_type="SupplierOffer", entity_id=str(offer.id), details="Offer created")

    # Audit logs for unrelated case
    log_other_case = AuditLog(user_id=1, tenant_id="mega_tenant", action="OTHER_CASE_ACTION", entity_type="CaseFile", entity_id=str(other_case.id), details="Other case event")
    log_other_req = AuditLog(user_id=1, tenant_id="mega_tenant", action="OTHER_REQ_ACTION", entity_type="CaseRequirementMatrix", entity_id=str(other_req.id), details="Other req event")

    db_session.add_all([log_case, log_req, log_item, log_offer, log_other_case, log_other_req])
    db_session.commit()

    response = client.get(
        f"/api/v6/cases/{test_case_file.id}/history",
        headers={"Authorization": "Bearer test_token"}
    )
    assert response.status_code == 200
    data = response.json()
    actions = [d["action"] for d in data]

    # Verify all related events are present
    assert "CASE_STATUS_CHANGE" in actions
    assert "CREATE_REQUIREMENT" in actions
    assert "CREATE_PROCUREMENT_ITEM" in actions
    assert "CREATE_OFFER" in actions

    # Verify unrelated events are NOT present
    assert "OTHER_CASE_ACTION" not in actions
    assert "OTHER_REQ_ACTION" not in actions

def test_history_cross_tenant_rejected(other_client: TestClient, db_session: Session, test_case_file):
    cross_res = other_client.get(
        f"/api/v6/cases/{test_case_file.id}/history",
        headers={"Authorization": "Bearer other_tenant_token"}
    )
    assert cross_res.status_code in [403, 404]

def test_history_includes_deleted_procurement_item_by_case_prefix(client: TestClient, db_session: Session, test_case_file):
    log_deleted_item = AuditLog(
        user_id=1,
        tenant_id="mega_tenant",
        action="DELETE_PROCUREMENT_ITEM",
        entity_type="CaseProcurementItem",
        entity_id="999",
        details=f"Expediente {test_case_file.id}: Ítem eliminado: 1: Papel bond",
        status="SUCCESS"
    )
    log_other_deleted_item = AuditLog(
        user_id=1,
        tenant_id="mega_tenant",
        action="DELETE_PROCUREMENT_ITEM",
        entity_type="CaseProcurementItem",
        entity_id="1000",
        details="Expediente 99999: Ítem eliminado: 1: Tóner",
        status="SUCCESS"
    )
    db_session.add_all([log_deleted_item, log_other_deleted_item])
    db_session.commit()

    response = client.get(
        f"/api/v6/cases/{test_case_file.id}/history",
        headers={"Authorization": "Bearer test_token"}
    )
    assert response.status_code == 200
    data = response.json()
    deleted_events = [d for d in data if d["action"] == "DELETE_PROCUREMENT_ITEM"]
    assert len(deleted_events) == 1
    assert deleted_events[0]["entity_id"] == "999"
    assert f"Expediente {test_case_file.id}:" in deleted_events[0]["details"]


