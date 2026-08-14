from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.services.v6.engines.experience_extraction_engine import ExperienceExtractionEngine
from app.services.v6.engines.experience_evaluation_engine import ExperienceEvaluationEngine
from app.models.v6.experience_evidence import ExperienceEvidence

router = APIRouter()

@router.post("/suppliers/{offer_id}/experience/extract")
def extract_experience(offer_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    engine = ExperienceExtractionEngine()
    # Assuming case_id is derived from offer, skipping for mock
    results = engine.extract_candidates(db, offer_id, tenant_id=current_user.tenant_id, case_id=1)
    return {"extracted_count": len(results), "status": "PENDING_REVIEW"}

@router.get("/suppliers/{offer_id}/experience")
def get_experience(offer_id: int, db: Session = Depends(get_db)):
    evidences = db.query(ExperienceEvidence).filter_by(supplier_offer_id=offer_id).all()
    return evidences

@router.put("/experience/{evidence_id}/validate")
def validate_experience(evidence_id: int, action: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    action should be 'VALIDATE' or 'REJECT'
    """
    evidence = db.query(ExperienceEvidence).filter_by(id=evidence_id).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
        
    if action == "VALIDATE":
        evidence.evidence_status = "VALIDATED"
    elif action == "REJECT":
        evidence.evidence_status = "REJECTED"
        
    evidence.validated_by = current_user.id
    db.commit()
    
    # Optional: trigger evaluation engine here if needed
    
    return {"status": evidence.evidence_status}
