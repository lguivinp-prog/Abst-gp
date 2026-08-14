from sqlalchemy.orm import Session
from app.models.v6.experience_evidence import ExperienceEvidence
from app.models.v6.experience_requirement import ExperienceRequirement
from app.models.v6.calculation_trace import CalculationTrace
from typing import Dict, Any

class ExperienceEvaluationEngine:
    def evaluate(self, db: Session, offer_id: int, requirement_id: int) -> Dict[str, Any]:
        """
        Calculates if the VALIDATED ExperienceEvidences sum up to meet the ExperienceRequirement.
        Returns suggested status and saves CalculationTrace.
        """
        req = db.query(ExperienceRequirement).filter_by(id=requirement_id).first()
        if not req:
            return {"status": "MISSING_DATA", "reason": "No requirement found"}
            
        evidences = db.query(ExperienceEvidence).filter_by(supplier_offer_id=offer_id, evidence_status="VALIDATED").all()
        
        if not evidences:
            return {"status": "OBSERVED", "reason": "No VALIDATED evidence found. Review pending extractions."}
            
        total_monto = sum(e.monto for e in evidences if e.monto)
        
        # Suggested decision
        status = "PASSED" if req.monto_requerido and total_monto >= req.monto_requerido else "FAILED"
        
        # Trace
        trace = CalculationTrace(
            supplier_offer_id=offer_id,
            evidencias_usadas=[e.id for e in evidences],
            montos=[e.monto for e in evidences if e.monto],
            fechas=[e.fecha.isoformat() if e.fecha else None for e in evidences],
            resultado_calculo=f"Total: {total_monto} vs Required: {req.monto_requerido} -> {status}"
        )
        db.add(trace)
        db.commit()
        
        return {
            "status": status, 
            "total_calculated": total_monto,
            "required": req.monto_requerido,
            "trace_id": trace.id
        }
