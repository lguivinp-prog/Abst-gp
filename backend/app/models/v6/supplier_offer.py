from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Table, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class SupplierOfferDocument(Base):
    __tablename__ = "supplier_offer_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SupplierOffer(Base):
    __tablename__ = "supplier_offers"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="PENDING") # PENDING, APPROVED, REJECTED, OBSERVED
    evaluation_status = Column(String(50), nullable=False, default="PENDING") # PENDING, UNDER_REVIEW, HAS_CONFLICTS, READY, APPROVED
    price = Column(Float, nullable=True)
    currency = Column(String(3), nullable=False, default="PEN")
    total_amount = Column(Numeric(precision=18, scale=2), nullable=True)
    source_document = Column(String, nullable=True) # Legacy text field
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    case = relationship("CaseFile", foreign_keys=[case_id])
    supplier = relationship("Supplier", foreign_keys=[supplier_id])
    documents = relationship("SupplierOfferDocument", backref="offer", cascade="all, delete-orphan")
    items = relationship("SupplierOfferItem", backref="offer", cascade="all, delete-orphan")

