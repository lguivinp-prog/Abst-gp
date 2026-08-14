from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class CaseOperationalSnapshot(Base):
    __tablename__ = "case_operational_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    current_status = Column(String(50), nullable=False)
    pending_actions = Column(JSONB, nullable=True)
    risk_level = Column(String(20), nullable=False, default="LOW") # LOW, MEDIUM, HIGH
    risk_reason = Column(JSONB, nullable=True) # Explains why risk is what it is
    last_activity = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    case = relationship("CaseFile")
