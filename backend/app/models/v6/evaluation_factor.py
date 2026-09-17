from app.models.base import Base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship

class EvaluationFactor(Base):
    __tablename__ = "evaluation_factors"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    key = Column(String(100), nullable=False)
    weight = Column(Float, nullable=True) # Percentage or weight
    max_score = Column(Float, nullable=True)
    formula = Column(Text, nullable=True)

    source_document_id = Column(Integer, ForeignKey("uploaded_documents.id", ondelete="SET NULL"), nullable=True)
    source_page = Column(Integer, nullable=True)
    source_quote = Column(Text, nullable=True)
    is_manual_edit = Column(Boolean, default=False)

    case = relationship("CaseFile", foreign_keys=[case_id])
