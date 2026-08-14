from app.models.base import Base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class CalculationTrace(Base):
    __tablename__ = "calculation_traces"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    evidencias_usadas = Column(JSONB, nullable=False) # list of IDs
    montos = Column(JSONB, nullable=False) # list of floats
    fechas = Column(JSONB, nullable=False) # list of dates/strings
    resultado_calculo = Column(String(255), nullable=False) # e.g. "Total: 100,000"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    offer = relationship("SupplierOffer")
