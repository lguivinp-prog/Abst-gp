import json
from sqlalchemy.orm import Session
from app.models.v6.supplier_offer import SupplierOffer, SupplierOfferDocument
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
            currency=data.get("currency", "PEN"),
            source_document=data.get("source_document")
        )
        db.add(offer)
        db.flush()

        document_ids = data.get("document_ids", [])
        if document_ids:
            for doc_id in document_ids:
                offer_doc = SupplierOfferDocument(offer_id=offer.id, document_id=doc_id)
                db.add(offer_doc)

        items_data = data.get("items")
        if items_data is not None:
            from app.models.v6.supplier_offer_item import SupplierOfferItem
            from app.models.v6.case_procurement_item import CaseProcurementItem
            from decimal import Decimal, ROUND_HALF_UP

            seen_items = set()
            total_amount = Decimal('0.00')

            for item_data in items_data:
                proc_id = item_data["procurement_item_id"]
                if proc_id in seen_items:
                    raise ValueError(f"Procurement item {proc_id} is duplicated in the request")
                seen_items.add(proc_id)

                procurement_item = db.query(CaseProcurementItem).filter_by(id=proc_id).first()
                if not procurement_item or procurement_item.case_id != case_id:
                    raise ValueError(f"Procurement item {proc_id} is invalid or does not belong to the case")

                # Check for duplicate in DB
                existing = db.query(SupplierOfferItem).filter_by(
                    supplier_offer_id=offer.id,
                    procurement_item_id=procurement_item.id
                ).first()
                if existing:
                    raise ValueError(f"Procurement item {procurement_item.id} is already in the offer")

                if item_data.get("unit_price") is None or item_data["unit_price"] < 0:
                    raise ValueError("Invalid unit price")

                qty = Decimal(str(procurement_item.quantity)) if procurement_item.quantity is not None else Decimal('0')
                u_price = Decimal(str(item_data["unit_price"]))

                subtotal = (qty * u_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                total_amount += subtotal

                offer_item = SupplierOfferItem(
                    supplier_offer_id=offer.id,
                    procurement_item_id=procurement_item.id,
                    description=procurement_item.description,
                    quantity=procurement_item.quantity,
                    unit=procurement_item.unit,
                    unit_price=u_price
                )
                db.add(offer_item)

            offer.total_amount = total_amount
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
            document_type=evidence_type,
            fragment=json.dumps(
                {
                    "file_path": file_path,
                    "extracted_data": extracted_data
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str
    )
)
        db.add(evidence)
        db.commit()
        db.refresh(evidence)

        # Trigger Semantic External Validation on Anexo 4 (Supplier Sworn Statement)
        if evidence_type == "ANEXO_4" and offer.supplier_id:
            # Note: in a real Celery app this would be .delay()
            trigger_external_validation(offer.supplier_id, user_id, fallback_evidence=extracted_data)

        return evidence
