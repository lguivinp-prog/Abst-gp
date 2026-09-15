from sqlalchemy.orm import Session
from app.services.v6.ai.provider_interface import AIProviderInterface
from app.services.v6.rag.retrieval_service import EvidenceRetrievalService
from app.services.v6.ai.context_builder import CaseContextBuilder
from app.models.v6.prompt_registry import PromptRegistry
from app.models.v6.ai_interaction_log import AIInteractionLog
import json
import hashlib

class AssistantService:
    def __init__(self, provider: AIProviderInterface, retriever: EvidenceRetrievalService = None):
        self.provider = provider
        self.retriever = retriever or EvidenceRetrievalService()
        
    def ask_question(self, db: Session, case_id: int, question: str, user_id: int, tenant_id: str) -> dict:
        # 1. Get Prompt Template
        prompt = db.query(PromptRegistry).filter_by(name="case_assistant_v6").first()
        prompt_content = prompt.content if prompt else "Contexto provisto. Responde a la pregunta."
        prompt_version = prompt.version if prompt else "fallback-v1"
        
        # 2. Build Structural Case Context
        structural_context = CaseContextBuilder.build_context(db, case_id)
        
        # 3. RAG Retrieval (Optional supplemental context)
        retrieved_chunks = self.retriever.retrieve(db, query=question, tenant_id=tenant_id, case_id=case_id)
        
        # Merge contexts
        full_context = {
            "structured_data": structural_context,
            "document_snippets": retrieved_chunks
        }
        
        context_str = json.dumps(full_context)
        context_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()
        
        # Replace context placeholder in prompt if present
        if "{context_json}" in prompt_content:
            final_prompt = prompt_content.replace("{context_json}", json.dumps(structural_context, default=str))
        else:
            final_prompt = prompt_content
            
        # 4. Call AI
        ai_response = self.provider.ask(final_prompt, full_context, question)
        
        # 5. Hash response
        response_hash = hashlib.sha256(ai_response.answer.encode('utf-8')).hexdigest()
        
        # 6. Log Interaction
        log_entry = AIInteractionLog(
            user_id=user_id,
            case_id=case_id,
            provider=self.provider.provider_name,
            model_version=self.provider.model_version,
            prompt_version=prompt_version,
            question=question,
            context_hash=context_hash,
            response=ai_response.answer,
            response_hash=response_hash,
            retrieval_strategy_version="structured+rag-v1",
            retrieved_chunks=[{"chunk_id": c.get("chunk_id", "unknown"), "score": c.get("score", 0)} for c in retrieved_chunks],
            tokens_used=0 # Provider logic handles this in a real system
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        
        return {
            "interaction_id": log_entry.id,
            "answer": ai_response.answer,
            "sources": ai_response.sources,
            "evidence_references": ai_response.evidence_references,
            "retrieved_chunks_count": len(retrieved_chunks)
        }
