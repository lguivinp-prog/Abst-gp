from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class OfferEvidence(Base):
    __tablename__ = "offer_evidences"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, nullable=True) # References UploadedDocument loosely if needed, or string path
    document_type = Column(String(50), nullable=False) # Anexo 4, Ficha tecnica, Brochure
    page = Column(Integer, nullable=True)
    fragment = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    offer = relationship("SupplierOffer", backref="evidences")
