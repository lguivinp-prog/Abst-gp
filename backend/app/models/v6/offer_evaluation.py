from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class OfferEvaluation(Base):
    __tablename__ = "offer_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id = Column(Integer, ForeignKey("case_requirement_matrices.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="PENDING") # PASSED, FAILED, OBSERVED, IMPROVEMENT, CONFLICT, MISSING_DATA
    explanation = Column(Text, nullable=True)
    evaluation_confidence = Column(Float, nullable=True)
    validated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    offer = relationship("SupplierOffer")
    requirement = relationship("CaseRequirementMatrix")
