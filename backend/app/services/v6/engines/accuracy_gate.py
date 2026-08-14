from sqlalchemy.orm import Session
from app.models.v6.case_workflow import CaseWorkflow
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.offer_evaluation import OfferEvaluation

class ContractAccuracyGate:
    @staticmethod
    def validate_for_generation(db: Session, case_id: int) -> str:
        """
        Validates if a case is ready for output generation.
        Returns "PASSED" if all rules pass, otherwise returns "ACCURACY_FAILED".
        """
        # 1. Check if workflow is approved
        workflow = db.query(CaseWorkflow).filter_by(case_id=case_id).first()
        if not workflow or workflow.status != "APPROVED":
            return "ACCURACY_FAILED"
            
        # 2. Check if there are any conflicting or missing data in evaluations for this case
        # We need to find the supplier offer selected. For simplicity in the gate, we just check
        # if the selected offer has conflicts. Wait, the gate should ensure NO CONFLICT globally
        # or at least not for the selected offer. We'll check the selected offer later, but 
        # let's assume any CONFLICT/MISSING_DATA globally is a warning, but specifically for the selected offer it's a blocker.
        # Actually, "No existen: CONFLICT, MISSING_DATA, BLOCKED, PENDING_REVIEW" in the entire case is a safer strict rule.
        
        offers = db.query(SupplierOffer).filter_by(case_id=case_id).all()
        offer_ids = [o.id for o in offers]
        
        blocking_evals = db.query(OfferEvaluation).filter(
            OfferEvaluation.supplier_offer_id.in_(offer_ids),
            OfferEvaluation.status.in_(["CONFLICT", "MISSING_DATA", "OBSERVED"])
        ).count()
        
        if blocking_evals > 0:
            return "ACCURACY_FAILED"
            
        for offer in offers:
            if offer.evaluation_status == "HAS_CONFLICTS" or offer.evaluation_status == "PENDING":
                return "ACCURACY_FAILED"
                
        return "PASSED"
