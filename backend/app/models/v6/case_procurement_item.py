from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Float, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class CaseProcurementItem(Base):
    __tablename__ = "case_procurement_items"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    item_number = Column(String, nullable=True)
    description = Column(String, nullable=False)
    quantity = Column(Numeric(18, 4), nullable=False)
    unit = Column(String, nullable=False)
    source_document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True)
    source_page = Column(Integer, nullable=True)
    source_requirement_id = Column(Integer, ForeignKey("case_requirement_matrices.id", ondelete="SET NULL"), nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('case_id', 'item_number', name='uq_case_item_number'),
    )

    case = relationship("CaseFile", foreign_keys=[case_id])
