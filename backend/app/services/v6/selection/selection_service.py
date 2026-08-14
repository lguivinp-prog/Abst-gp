from sqlalchemy.orm import Session
from app.models.v6.supplier_profile import SupplierProfile
from app.models.v6.supplier_offer import SupplierOffer
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
