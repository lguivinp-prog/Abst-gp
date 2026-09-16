from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class ValidationRequest(Base):
    __tablename__ = "validation_requests"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=True, index=True)
    source = Column(String(50), nullable=False) # SUNAT, RNP, FUP, CIIU
    status = Column(String(50), nullable=False, default="PENDING") # PENDING, RUNNING, PASSED, WARNING, BLOCKED, ERROR
    requested_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    response_hash = Column(String, nullable=True)
    response_payload = Column(JSONB, nullable=True)
    response_schema_version = Column(String(20), nullable=True)
    attempt_number = Column(Integer, default=1, nullable=False)
    expiration_cache = Column(DateTime(timezone=True), nullable=True)

    validation_mode = Column(String(50), nullable=False, default="EXTERNAL", server_default="EXTERNAL") # EXTERNAL, MANUAL
    manual_result = Column(String(50), nullable=True) # VALIDATED, REJECTED, REVIEW_REQUIRED
    manual_observation = Column(String, nullable=True)
    manual_evidence_reference = Column(String, nullable=True)
    verified_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    verified_by_user = relationship("User", foreign_keys=[verified_by_user_id])
    supplier = relationship("Supplier")
