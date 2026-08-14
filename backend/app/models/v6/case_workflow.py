from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class CaseWorkflow(Base):
    __tablename__ = "case_workflows"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    status = Column(String(50), nullable=False, default="DRAFT") # DRAFT, UNDER_REVIEW, APPROVED, REJECTED
    supervisor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    case = relationship("CaseFile", backref="workflow")
