from app.models.base import Base
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship

class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    address = Column(String, nullable=True)
    aggregated_score = Column(Float, nullable=True)
    status_summary = Column(String(50), nullable=True) # e.g. VERIFIED, PENDING_VERIFICATION, BLOCKED
    validation_status = Column(String(50), nullable=False, default="NOT_STARTED") # NOT_STARTED, PENDING, RUNNING, PARTIAL, VERIFIED, WARNING, BLOCKED
    
    supplier = relationship("Supplier", backref="profile")
