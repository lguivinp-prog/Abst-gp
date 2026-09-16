from app.models.base import Base
from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property

class SupplierOfferItem(Base):
    __tablename__ = "supplier_offer_items"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_offer_id = Column(Integer, ForeignKey("supplier_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    procurement_item_id = Column(Integer, ForeignKey("case_procurement_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    description = Column(String, nullable=True) # snapshot for traceability
    quantity = Column(Numeric(18, 4), nullable=False)
    unit = Column(String, nullable=False)
    unit_price = Column(Numeric(18, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint('supplier_offer_id', 'procurement_item_id', name='uq_offer_procurement_item'),
    )

    procurement_item = relationship("CaseProcurementItem")

    @hybrid_property
    def subtotal(self):
        return float(self.quantity * self.unit_price) if self.quantity is not None and self.unit_price is not None else 0.0
