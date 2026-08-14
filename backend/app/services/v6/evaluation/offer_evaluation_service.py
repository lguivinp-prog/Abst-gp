from sqlalchemy.orm import Session
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.offer_evidence import OfferEvidence
from app.models.v6.offer_evaluation import OfferEvaluation
from app.models.domain import AuditLog
from app.services.v6.engines.improvement_engine import DeterministicImprovementEngine
import json

class OfferEvaluationService:
    def __init__(self, engine: DeterministicImprovementEngine = None):
        self.engine = engine or DeterministicImprovementEngine()

    def evaluate_offer(self, db: Session, supplier_offer_id: int, user_id: int, tenant_id: str) -> list:
        offer = db.query(SupplierOffer).filter_by(id=supplier_offer_id).first()
        if not offer:
            return []
            
        requirements = db.query(CaseRequirementMatrix).filter_by(case_id=offer.case_id).all()
        evaluations = []
        has_conflicts = False
        
        for req in requirements:
            # Get evidences linked to this offer for this specific requirement type 
            # (In a real system, there'd be an AI semantic matching phase first. For Sprint 4, we assume evidences are pre-linked or we mock it)
            evidences = db.query(OfferEvidence).filter_by(supplier_offer_id=offer.id).all() # Mock: taking all for demo
            
            status = "PASSED"
            explanation = "Evaluacion automatica OK"
            
            if self.engine.detect_conflict(evidences):
                status = "CONFLICT"
                explanation = "Conflicto documental detectado entre Anexos y Fichas"
                has_conflicts = True
            elif evidences and self.engine.detect_improvement(req.value, evidences[0].fragment):
                status = "IMPROVEMENT"
                explanation = "Se detecto condicion superior a lo requerido"
            elif not evidences:
                status = "MISSING_DATA"
                explanation = "No se encontro evidencia documental"
                
            eval_entry = OfferEvaluation(
                supplier_offer_id=offer.id,
                requirement_id=req.id,
                status=status,
                explanation=explanation,
                evaluation_confidence=0.85
            )
            db.add(eval_entry)
            evaluations.append(eval_entry)
            
        if has_conflicts:
            offer.evaluation_status = "HAS_CONFLICTS"
        else:
            offer.evaluation_status = "UNDER_REVIEW"
            
        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="EVALUATE_OFFER",
            entity_type="SupplierOffer",
            entity_id=str(offer.id),
            details=json.dumps({"has_conflicts": has_conflicts}),
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        
        return evaluations

    def update_evaluation(self, db: Session, eval_id: int, new_status: str, explanation: str, user_id: int, tenant_id: str) -> OfferEvaluation:
        eval_entry = db.query(OfferEvaluation).filter_by(id=eval_id).first()
        if not eval_entry:
            return None
            
        old_status = eval_entry.status
        eval_entry.status = new_status
        eval_entry.explanation = explanation
        
        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="UPDATE_EVALUATION",
            entity_type="OfferEvaluation",
            entity_id=str(eval_entry.id),
            details=json.dumps({"old_status": old_status, "new_status": new_status, "reason": explanation}),
            status="SUCCESS"
        )
        db.add(audit)
        
        # Check if parent offer can be unblocked
        offer = db.query(SupplierOffer).filter_by(id=eval_entry.supplier_offer_id).first()
        still_conflicts = db.query(OfferEvaluation).filter_by(supplier_offer_id=offer.id, status="CONFLICT").count()
        if still_conflicts == 0 and offer.evaluation_status == "HAS_CONFLICTS":
            offer.evaluation_status = "UNDER_REVIEW"
            
        db.commit()
        db.refresh(eval_entry)
        return eval_entry
