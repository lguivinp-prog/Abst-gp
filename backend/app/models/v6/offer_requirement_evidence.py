from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class OfferRequirementEvidence(Base):
    __tablename__ = "offer_requirement_evidences"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id = Column(Integer, ForeignKey("case_requirement_matrices.id", ondelete="CASCADE"), nullable=False, index=True)
    offer_evidence_id = Column(Integer, ForeignKey("offer_evidences.id", ondelete="CASCADE"), nullable=False, index=True)
    
    document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True, index=True)
    source_document = Column(String(255), nullable=True)
    page = Column(Integer, nullable=True)
    fragment = Column(Text, nullable=True)

    verification_status = Column(String(50), nullable=False, default="PENDING", index=True) # PENDING, VERIFIED, REJECTED, OBSERVED
    verified_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint('requirement_id', 'offer_evidence_id', name='uq_requirement_offer_evidence'),
    )

    case = relationship("CaseFile")
    offer = relationship("SupplierOffer", backref="requirement_evidence_associations")
    requirement = relationship("CaseRequirementMatrix", backref="offer_evidence_associations")
    evidence = relationship("OfferEvidence", back_populates="requirement_associations", passive_deletes=True)
    verifier = relationship("User", foreign_keys=[verified_by])
    document = relationship("UploadedDocument", foreign_keys=[document_id])
