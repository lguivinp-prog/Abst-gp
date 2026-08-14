from sqlalchemy.orm import Session
from app.models.v6.supplier_offer import SupplierOffer
from app.models.domain import AuditLog
from app.models.v6.offer_evidence import OfferEvidence
from app.workers.validation_worker import trigger_external_validation

class SupplierOfferService:
    @staticmethod
    def attach_offer(db: Session, case_id: int, supplier_id: int, user_id: int, tenant_id: str, data: dict) -> SupplierOffer:
        offer = SupplierOffer(
            case_id=case_id,
            supplier_id=supplier_id,
            price=data.get("price"),
            source_document=data.get("source_document")
        )
        db.add(offer)
        db.flush()
        
        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="CREATE_SUPPLIER_OFFER",
            entity_type="SupplierOffer",
            entity_id=str(offer.id),
            details=f"Created offer for case {case_id} supplier {supplier_id}",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        db.refresh(offer)
        return offer

    @staticmethod
    def add_evidence(db: Session, offer_id: int, evidence_type: str, file_path: str, user_id: int, extracted_data: dict = None):
        """
        Adds evidence to the offer and runs semantic triggers.
        """
        offer = db.query(SupplierOffer).filter_by(id=offer_id).first()
        if not offer:
            raise ValueError("Offer not found")
            
        evidence = OfferEvidence(
            supplier_offer_id=offer.id,
            evidence_type=evidence_type,
            file_path=file_path,
            extracted_data=extracted_data
        )
        db.add(evidence)
        db.commit()
        db.refresh(evidence)
        
        # Trigger Semantic External Validation on Anexo 4 (Supplier Sworn Statement)
        if evidence_type == "ANEXO_4" and offer.supplier_id:
            # Note: in a real Celery app this would be .delay()
            trigger_external_validation(offer.supplier_id, user_id, fallback_evidence=extracted_data)
            
        return evidence
