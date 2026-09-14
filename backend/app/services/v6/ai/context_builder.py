from sqlalchemy.orm import Session
from typing import Dict, Any
from app.models.domain import CaseFile
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.offer_evaluation import OfferEvaluation

class CaseContextBuilder:
    @staticmethod
    def build_context(db: Session, case_id: int) -> Dict[str, Any]:
        """
        Builds a safe, constrained context for the AI, strictly pulling from validated models.
        """
        case = db.query(CaseFile).filter_by(id=case_id).first()
        if not case:
            raise ValueError("Case not found")
            
        reqs = db.query(CaseRequirementMatrix).filter_by(case_id=case_id).all()
        offers = db.query(SupplierOffer).filter_by(case_id=case_id).all()
        
        offer_ids = [o.id for o in offers]
        evals = db.query(OfferEvaluation).filter(OfferEvaluation.supplier_offer_id.in_(offer_ids)).all()
        
        # Build sanitized dict
        context = {
            "case_metadata": {
                "name": case.title,
                "type": case.contract_type
             },
            "requirements": [{"desc": r.description, "value": r.value} for r in reqs],
            "offers": [{"id": o.id, "status": o.status} for o in offers],
            "evaluations": [{"offer_id": e.supplier_offer_id, "status": e.status} for e in evals]
        }
        return context
