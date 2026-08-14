from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class ExperienceEvaluation(Base):
    __tablename__ = "experience_evaluations"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="PENDING") # PASSED, FAILED, OBSERVED
    explanation = Column(Text, nullable=True)
    validated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    offer = relationship("SupplierOffer")
