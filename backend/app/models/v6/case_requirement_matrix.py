from app.models.base import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class CaseRequirementMatrix(Base):
    __tablename__ = "case_requirement_matrices"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_type = Column(String(50), nullable=False) # e.g., TECHNICAL, LEGAL
    description = Column(Text, nullable=False)
    value = Column(String, nullable=True)
    mandatory = Column(Boolean, default=True, nullable=False)
    status = Column(String(50), default="PENDING_REVIEW", nullable=False) # PENDING_REVIEW, VALIDATED, MODIFIED_BY_USER, OBSERVED, REJECTED
    validated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    case = relationship("CaseFile", foreign_keys=[case_id])
    evidences = relationship("RequirementEvidence", back_populates="requirement", cascade="all, delete-orphan")
