from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class SupplierSelectionAttempt(Base):
    __tablename__ = "supplier_selection_attempts"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False)
    justification_reason = Column(String(255), nullable=True)
    justification_comment = Column(Text, nullable=True)
    justification_evidence_id = Column(Integer, nullable=True)
    selected_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, default="PROPOSED") # PROPOSED, REJECTED
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    case = relationship("CaseFile")
    offer = relationship("SupplierOffer")

class SupplierSelectionFinal(Base):
    __tablename__ = "supplier_selection_final"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    attempt_id = Column(Integer, ForeignKey("supplier_selection_attempts.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    case = relationship("CaseFile")
    attempt = relationship("SupplierSelectionAttempt")
