from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class SupplierOffer(Base):
    __tablename__ = "supplier_offers"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="PENDING") # PENDING, APPROVED, REJECTED, OBSERVED
    evaluation_status = Column(String(50), nullable=False, default="PENDING") # PENDING, UNDER_REVIEW, HAS_CONFLICTS, READY, APPROVED
    price = Column(Float, nullable=True)
    source_document = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    case = relationship("CaseFile", foreign_keys=[case_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])
