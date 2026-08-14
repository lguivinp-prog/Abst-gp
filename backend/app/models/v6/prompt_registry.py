from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

class PromptRegistry(Base):
    __tablename__ = "prompt_registries"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    version = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="ACTIVE") # ACTIVE, DEPRECATED
    created_at = Column(DateTime(timezone=True), server_default=func.now())
