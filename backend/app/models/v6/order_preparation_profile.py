from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class OrderPreparationProfile(Base):
    __tablename__ = "order_preparation_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_selection_final_id = Column(Integer, ForeignKey("supplier_selection_final.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    supplier_data = Column(JSONB, nullable=False)
    contracting_data = Column(JSONB, nullable=False)
    improvements_data = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    selection_final = relationship("SupplierSelectionFinal")
