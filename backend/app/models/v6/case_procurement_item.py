from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Float, UniqueConstraint, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class CaseProcurementItem(Base):
    __tablename__ = "case_procurement_items"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    item_number = Column(String, nullable=True)
    description = Column(String, nullable=False)
    quantity = Column(Numeric(18, 4), nullable=True)
    unit = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default='VALIDATED')
    source_document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True)
    source_page = Column(Integer, nullable=True)
    source_requirement_id = Column(Integer, ForeignKey("case_requirement_matrices.id", ondelete="SET NULL"), nullable=True)
    confidence = Column(Float, nullable=True)
    is_manual_edit = Column(Boolean, nullable=False, server_default='false')
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('case_id', 'item_number', name='uq_case_item_number'),
    )

    case = relationship("CaseFile", foreign_keys=[case_id])
    specifications = relationship("CaseProcurementItemSpecification", back_populates="item", cascade="all, delete-orphan")

class CaseProcurementItemSpecification(Base):
    __tablename__ = "case_procurement_item_specifications"

    id = Column(Integer, primary_key=True, index=True)
    procurement_item_id = Column(Integer, ForeignKey("case_procurement_items.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    normalized_name = Column(String, nullable=False, index=True)
    value = Column(String, nullable=False)
    mandatory = Column(String, nullable=True) # Usually boolean or string yes/no, but String is safer if it's text
    source_document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True)
    source_page = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)

    item = relationship("CaseProcurementItem", back_populates="specifications")
