from sqlalchemy.orm import Session
from app.services.v6.ai.provider_interface import AIProviderInterface, MockAIProvider
from app.services.v6.rag.retrieval_service import EvidenceRetrievalService
from app.services.v6.rag.rag_context_builder import RAGContextBuilder
from app.models.v6.prompt_registry import PromptRegistry
from app.models.v6.ai_interaction_log import AIInteractionLog
from app.models.domain import User
import json
import hashlib

class AssistantService:
    def __init__(self, provider: AIProviderInterface = None, retriever: EvidenceRetrievalService = None):
        self.provider = provider or MockAIProvider()
        self.retriever = retriever or EvidenceRetrievalService()
        
    def ask_question(self, db: Session, case_id: int, question: str, user_id: int, tenant_id: str) -> dict:
        # 1. Get Prompt Template
        prompt = db.query(PromptRegistry).filter_by(name="case_summary", status="ACTIVE").first()
        prompt_content = prompt.content if prompt else "Contexto provisto. Responde a la pregunta."
        prompt_version = prompt.version if prompt else "fallback-v1"
        
        # 2. RAG Retrieval
        retrieved_chunks = self.retriever.retrieve(db, query=question, tenant_id=tenant_id, case_id=case_id)
        
        # 3. Build Reduced RAG Context
        context = RAGContextBuilder.build_context(retrieved_chunks)
        context_str = json.dumps(context)
        context_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()
        
        # 4. Call AI
        ai_response = self.provider.ask(prompt_content, context, question)
        
        # 5. Hash response
        response_hash = hashlib.sha256(ai_response.answer.encode('utf-8')).hexdigest()
        
        # 6. Log Interaction with RAG chunks
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
            retrieval_strategy_version="deterministic-mock-v1",
            retrieved_chunks=[{"chunk_id": c["chunk_id"], "score": c["score"]} for c in retrieved_chunks],
            tokens_used=100
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
