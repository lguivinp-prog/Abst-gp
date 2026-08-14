from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func

class OutputTemplate(Base):
    __tablename__ = "output_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), nullable=False) # CONDICIONES, INFORME, PREVIEW
    version = Column(String(20), nullable=False)
    entity_name = Column(String, nullable=False)
    validity = Column(String(50), nullable=True)
    content = Column(Text, nullable=False) # Template string with secure placeholders
    status = Column(String(50), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
