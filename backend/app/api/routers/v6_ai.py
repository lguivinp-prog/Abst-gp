from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access
from app.models.domain import User, CaseFile
from app.services.v6.ai.assistant_service import AssistantService
from app.models.v6.ai_interaction_log import AIInteractionLog
from app.services.v6.ai.provider_factory import AIProviderFactory
from pydantic import BaseModel
from typing import List

router = APIRouter()

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    interaction_id: int
    answer: str
    sources: List[str]
    evidence_references: List[str]

class AssistantStatusResponse(BaseModel):
    configured: bool
    provider_name: str
    model_version: str

@router.get("/cases/{case_id}/assistant/status", response_model=AssistantStatusResponse)
def get_assistant_status(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user)
):
    provider = AIProviderFactory.get_provider()
    is_configured = provider.provider_name != "NONE"
    
    return AssistantStatusResponse(
        configured=is_configured,
        provider_name=provider.provider_name,
        model_version=provider.model_version
    )

@router.post("/cases/{case_id}/assistant/chat", response_model=AskResponse)
def ask_ai(
    case_id: int,
    req: AskRequest,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    provider = AIProviderFactory.get_provider()
    if provider.provider_name == "NONE":
        raise HTTPException(status_code=400, detail="Asistente IA no configurado")
        
    assistant_svc = AssistantService(provider=provider)
    
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
        
    # Security: check if the interaction belongs to the user's tenant by checking case tenant
    case = db.query(CaseFile).filter_by(id=log_entry.case_id).first()
    if not case or case.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Interaction not found")
        
    return {
        "id": log_entry.id,
        "question": log_entry.question,
        "response": log_entry.response,
        "timestamp": log_entry.timestamp,
        "provider": log_entry.provider
    }
