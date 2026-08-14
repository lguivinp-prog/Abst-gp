from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class RequirementEvidence(Base):
    __tablename__ = "requirement_evidences"
    
    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("case_requirement_matrices.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document = Column(String, nullable=False)
    source_page = Column(Integer, nullable=True)
    source_fragment = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    requirement = relationship("CaseRequirementMatrix", back_populates="evidences")
