from app.models.base import Base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

class ContractualCondition(Base):
    __tablename__ = "contractual_conditions"

    id = Column(Integer, primary_key=True, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True)
    label = Column(String(200), nullable=False)

    required_value = Column(String, nullable=True)
    offered_value = Column(String, nullable=True)
    final_value = Column(String, nullable=True)
    unit = Column(String(50), nullable=True)

    resolution_rule = Column(String(100), nullable=False) # OFFER_IMPROVEMENT, REQUIREMENT_DEFAULT, EXACT_MATCH, MANUAL_REVIEW_REQUIRED
    source_requirement = Column(String(255), nullable=True)
    source_offer = Column(String(255), nullable=True)
    status = Column(String(50), default="PENDING")

    offer = relationship("SupplierOffer", foreign_keys=[supplier_offer_id])
