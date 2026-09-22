from app.models.base import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class RequirementCategory:
    CONTEXT = "CONTEXT"
    ITEM_SPECIFICATION = "ITEM_SPECIFICATION"
    GENERAL_OBLIGATION = "GENERAL_OBLIGATION"
    CONTRACTUAL_TERM = "CONTRACTUAL_TERM"
    SELECTION_REQUIREMENT = "SELECTION_REQUIREMENT"

class RequirementPhase:
    CONTEXT = "CONTEXT"
    SELECTION = "SELECTION"
    EVALUATION = "EVALUATION"
    CONTRACT_EXECUTION = "CONTRACT_EXECUTION"

class CaseRequirementMatrix(Base):
    __tablename__ = "case_requirement_matrices"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_type = Column(String(50), nullable=False) # e.g., TECHNICAL, LEGAL
    key = Column(String(100), nullable=True)
    description = Column(Text, nullable=False)
    value = Column(String, nullable=True)
    numeric_value = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)
    comparator = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    mandatory = Column(Boolean, default=True, nullable=False)
    status = Column(String(50), default="PENDING_REVIEW", nullable=False) # PENDING_REVIEW, VALIDATED, MODIFIED_BY_USER, OBSERVED, REJECTED
    validated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    source_document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = Column(String(50), nullable=True, index=True)
    phase = Column(String(50), nullable=True, index=True)
    procurement_item_id = Column(
        Integer,
        ForeignKey("case_procurement_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    flows_to_contract = Column(Boolean, nullable=False, default=False, server_default="false")
    source_section = Column(String(255), nullable=True)

    case = relationship("CaseFile", foreign_keys=[case_id])
    evidences = relationship("RequirementEvidence", back_populates="requirement", cascade="all, delete-orphan")
    procurement_item = relationship("CaseProcurementItem", foreign_keys=[procurement_item_id])
