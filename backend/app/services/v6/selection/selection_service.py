from sqlalchemy.orm import Session
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_selection import SupplierSelectionAttempt, SupplierSelectionFinal
from app.models.v6.case_workflow import CaseWorkflow
from app.models.domain import AuditLog

class SelectionService:
    @staticmethod
    def select_supplier(db: Session, offer_id: int, user_id: int, user_role: str, tenant_id: str, reason: str = ""):
        """
        Attempts to select an offer as the winner.
        Enforces that the supplier's validation_status must be VERIFIED.
        """
        offer = db.query(SupplierOffer).filter_by(id=offer_id).first()
        if not offer:
            raise ValueError("Offer not found")

        profile = db.query(SupplierProfile).filter_by(supplier_id=offer.supplier_id).first()
        if not profile:
            raise ValueError("Supplier Profile not found")

        if profile.validation_status != "VERIFIED":
            if user_role == "SUPERVISOR":
                # SUPERVISOR_EXCEPTION logic
                audit = AuditLog(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    action="SUPERVISOR_EXCEPTION_SELECT",
                    entity_type="SupplierOffer",
                    entity_id=str(offer.id),
                    details=f"Supervisor bypassed validation_status {profile.validation_status}. Reason: {reason}",
                    status="WARNING"
                )
                db.add(audit)
            else:
                raise PermissionError(f"Cannot select supplier with validation_status {profile.validation_status}. Supervisor override required.")

        # Proceed with selection...
        offer.status = "SELECTED"

        audit_sel = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="SELECT_SUPPLIER",
            entity_type="SupplierOffer",
            entity_id=str(offer.id),
            details="Offer selected as winner.",
            status="SUCCESS"
        )
        db.add(audit_sel)
        db.commit()
        return offer

    @staticmethod
    def propose_selection(db: Session, case_id: int, supplier_offer_id: int, justification: str, user_id: int, tenant_id: str):
        offer = db.query(SupplierOffer).filter_by(id=supplier_offer_id, case_id=case_id).first()
        if not offer:
            raise ValueError("Offer not found in this case")
            
        if offer.status == "PENDING":
            raise ValueError("Cannot select a PENDING offer")
            
        from app.models.v6.case_procurement_item import CaseProcurementItem
        procurement_items_count = db.query(CaseProcurementItem).filter_by(case_id=case_id).count()
        
        if procurement_items_count > 0:
            if not offer.items or len(offer.items) < procurement_items_count:
                raise ValueError("Incomplete offer: Missing prices for some procurement items")
            
        attempt = SupplierSelectionAttempt(
            case_id=case_id,
            supplier_offer_id=supplier_offer_id,
            justification_comment=justification,
            proposed_by=user_id,
            status="UNDER_REVIEW"
        )
        db.add(attempt)

        workflow = db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        if not workflow:
            workflow = CaseWorkflow(case_id=case_id, status="UNDER_REVIEW")
            db.add(workflow)
        else:
            workflow.status = "UNDER_REVIEW"

        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="PROPOSE_SELECTION",
            entity_type="CaseFile",
            entity_id=str(case_id),
            details="Selection proposed.",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()

    @staticmethod
    def approve_selection(db: Session, case_id: int, supervisor_id: int, tenant_id: str):
        attempt = db.query(SupplierSelectionAttempt).filter_by(case_id=case_id, status="UNDER_REVIEW").first()
        if not attempt:
            raise ValueError("No proposed selection found for this case")

        final = SupplierSelectionFinal(case_id=case_id, attempt_id=attempt.id)
        db.add(final)

        workflow = db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        if workflow:
            workflow.status = "APPROVED"
            workflow.supervisor_id = supervisor_id

        audit = AuditLog(
            user_id=supervisor_id,
            tenant_id=tenant_id,
            action="APPROVE_SELECTION",
            entity_type="CaseFile",
            entity_id=str(case_id),
            details="Selection approved.",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
