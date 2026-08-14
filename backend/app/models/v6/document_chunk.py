from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    page = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    hash = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False) # e.g. Anexo3, FichaTecnica
    chunk_metadata = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    case = relationship("CaseFile")
