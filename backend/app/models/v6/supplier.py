from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class Supplier(Base):
    __tablename__ = "suppliers"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", onupdate="RESTRICT", ondelete="RESTRICT"), nullable=False, server_default="mega_tenant", index=True)
    ruc = Column(String(20), nullable=False, index=True)
    business_name = Column(String, nullable=False)
    legal_representative = Column(String, nullable=True)
    dni = Column(String(20), nullable=True)
    contact_email = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant = relationship("Tenant", foreign_keys=[tenant_id])
