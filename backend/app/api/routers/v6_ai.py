from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user
from app.models.domain import User
from app.services.v6.ai.assistant_service import AssistantService
from app.models.v6.ai_interaction_log import AIInteractionLog
from pydantic import BaseModel
from typing import List

router = APIRouter()
assistant_svc = AssistantService() # Defaults to MockProvider

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    interaction_id: int
    answer: str
    sources: List[str]
    evidence_references: List[str]

@router.post("/cases/{case_id}/ask", response_model=AskResponse)
def ask_ai(
    case_id: int,
    req: AskRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        result = assistant_svc.ask_question(
            db=db, 
            case_id=case_id, 
            question=req.question, 
            user_id=current_user.id,
            tenant_id=current_user.tenant_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/interactions/{interaction_id}")
def get_interaction(
    interaction_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    log_entry = db.query(AIInteractionLog).filter_by(id=interaction_id).first()
    if not log_entry:
        raise HTTPException(status_code=404, detail="Interaction not found")
        
    return {
        "id": log_entry.id,
        "question": log_entry.question,
        "response": log_entry.response,
        "timestamp": log_entry.timestamp,
        "provider": log_entry.provider
    }
