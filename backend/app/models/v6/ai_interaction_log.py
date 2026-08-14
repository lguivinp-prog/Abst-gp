from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class AIInteractionLog(Base):
    __tablename__ = "ai_interaction_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=True)
    
    provider = Column(String(50), nullable=False)
    model_version = Column(String(50), nullable=False)
    prompt_version = Column(String(50), nullable=False)
    
    question = Column(Text, nullable=False)
    context_hash = Column(String(255), nullable=False)
    
    response = Column(Text, nullable=False)
    response_hash = Column(String(255), nullable=False)
    
    retrieval_strategy_version = Column(String(50), nullable=True)
    retrieved_chunks = Column(JSONB, nullable=True)
    
    tokens_used = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    case = relationship("CaseFile")
