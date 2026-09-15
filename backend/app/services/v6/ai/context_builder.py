from sqlalchemy.orm import Session
from typing import Dict, Any
from app.models.domain import CaseFile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.v6.supplier_selection import SupplierSelectionFinal
from app.models.v6.supplier import Supplier
from app.models.v6.validation_request import ValidationRequest

class CaseContextBuilder:
    @staticmethod
    def build_context(db: Session, case_id: int) -> Dict[str, Any]:
        """
        Builds a safe, constrained context for the AI, strictly pulling from validated models.
        It must be case-scoped and exclude any sensitive tenant-level configuration.
        """
        case = db.query(CaseFile).filter_by(id=case_id).first()
        if not case:
            raise ValueError("Case not found")
            
        reqs = db.query(CaseRequirementMatrix).filter_by(case_id=case_id).all()
        offers = db.query(SupplierOffer).filter_by(case_id=case_id).all()
        
        # In this domain, Supplier is global, but connected to Case through SupplierOffer
        # Let's just pull suppliers that have offers in this case
        offer_ids = [o.id for o in offers]
        supplier_ids = [o.supplier_id for o in offers]
        suppliers = db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
        
        evals = db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id.in_(offer_ids)).all()
        
        validations = db.query(ValidationRequest).filter(ValidationRequest.supplier_id.in_(supplier_ids)).all()
        selection = db.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
        
        # Build sanitized dict
        context = {
            "case_metadata": {
                "id": case.id,
                "title": case.title,
                "type": case.contract_type,
                "status": case.status
             },
            "requirements": [{"id": r.id, "desc": r.description, "value": r.value, "type": r.req_type} for r in reqs],
            "suppliers": [{"id": s.id, "ruc": s.ruc, "name": s.business_name} for s in suppliers],
            "offers": [{"id": o.id, "supplier_id": o.supplier_id, "status": o.status, "evaluation_status": o.evaluation_status} for o in offers],
            "evaluations": [{"offer_id": e.supplier_offer_id, "status": e.status, "comments": e.comments} for e in evals],
            "validations": [{"id": v.id, "type": v.validation_type, "status": v.status, "result": v.result} for v in validations]
        }
        
        if selection:
            context["selection"] = {
                "status": selection.status,
                "selected_supplier_id": selection.selected_supplier_id,
                "justification": selection.justification
            }
            
        return context
