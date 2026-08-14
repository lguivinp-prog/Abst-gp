from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class ExperienceEvidence(Base):
    __tablename__ = "experience_evidences"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, nullable=True) 
    document_type = Column(String(50), nullable=False) # Anexo 3, Contrato, Orden, Conformidad, Comprobante
    page = Column(Integer, nullable=True)
    raw_fragment = Column(Text, nullable=False)
    normalized_fragment = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    
    # Sprint 14 Added Fields
    evidence_status = Column(String(50), nullable=False, default="EXTRACTED") # EXTRACTED, UNDER_REVIEW, VALIDATED, REJECTED
    entidad_contratante = Column(String(255), nullable=True)
    objeto = Column(Text, nullable=True)
    monto = Column(Float, nullable=True)
    fecha = Column(DateTime(timezone=True), nullable=True)
    
    validated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    offer = relationship("SupplierOffer")
