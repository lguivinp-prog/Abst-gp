from sqlalchemy.orm import Session
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.experience_evidence import ExperienceEvidence
from app.models.v6.experience_evaluation import ExperienceEvaluation
from app.models.domain import AuditLog
from app.services.v6.engines.normalization_engine import NormalizationEngine
import json

class ExperienceEvaluationEngine:
    
    def evaluate_experience(self, db: Session, supplier_offer_id: int, user_id: int, tenant_id: str) -> ExperienceEvaluation:
        offer = db.query(SupplierOffer).filter_by(id=supplier_offer_id).first()
        if not offer:
            return None
            
        evidences = db.query(ExperienceEvidence).filter_by(supplier_offer_id=offer.id).all()
        
        # For Sprint 5 mock heuristic: if there are more than 2 valid evidences (Contratos/Conformidades) -> PASSED
        valid_count = 0
        for ev in evidences:
            if ev.normalized_fragment and ("contrato" in ev.normalized_fragment or "orden" in ev.normalized_fragment):
                valid_count += 1
                
        status = "PASSED" if valid_count >= 1 else "FAILED"
        if not evidences:
            status = "OBSERVED"
            
        eval_entry = ExperienceEvaluation(
            supplier_offer_id=offer.id,
            status=status,
            explanation=f"Evaluacion de experiencia completada. Evidencias validas: {valid_count}"
        )
        db.add(eval_entry)
        
        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="EVALUATE_EXPERIENCE",
            entity_type="SupplierOffer",
            entity_id=str(offer.id),
            details=json.dumps({"status": status, "valid_count": valid_count}),
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        db.refresh(eval_entry)
        
        return eval_entry
