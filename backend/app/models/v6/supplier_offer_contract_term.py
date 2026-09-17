from app.models.base import Base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship

class SupplierOfferContractTerm(Base):
    __tablename__ = "supplier_offer_contract_terms"

    id = Column(Integer, primary_key=True, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True) # e.g., DELIVERY_TERM, WARRANTY, USEFUL_LIFE
    label = Column(String(200), nullable=True)
    value_text = Column(Text, nullable=True)
    numeric_value = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)

    source_document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True)
    source_page = Column(Integer, nullable=True)
    source_quote = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    extraction_method = Column(String(50), nullable=True) # native_text, table, ocr

    review_status = Column(String(50), default="PENDING_REVIEW") # AUTO_ACCEPTED, REVIEW_REQUIRED, MANUALLY_CONFIRMED
    is_manual_edit = Column(Boolean, default=False)

    offer = relationship("SupplierOffer", foreign_keys=[supplier_offer_id])
