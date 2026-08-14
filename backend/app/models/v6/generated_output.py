from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class GeneratedOutput(Base):
    __tablename__ = "generated_outputs"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("output_templates.id", ondelete="RESTRICT"), nullable=False)
    content_rendered = Column(Text, nullable=False)
    generation_hash = Column(String, nullable=False)
    generated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    template_version = Column(String(20), nullable=False)
    accuracy_gate_result = Column(String(50), nullable=False)
    source_snapshot = Column(JSONB, nullable=False)
    status = Column(String(50), nullable=False, default="GENERATED") # GENERATED, UNDER_REVIEW, APPROVED, EXPORTED, REJECTED
    
    case = relationship("CaseFile")
    template = relationship("OutputTemplate")
