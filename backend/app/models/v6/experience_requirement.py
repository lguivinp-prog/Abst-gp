from app.models.base import Base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship

class ExperienceRequirement(Base):
    __tablename__ = "experience_requirements"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    monto_requerido = Column(Float, nullable=True)
    periodo_anios = Column(Integer, nullable=True)
    objeto_similar = Column(String, nullable=True)
    cantidad_minima = Column(Integer, nullable=True)
    condicion = Column(String, nullable=True)
    
    case = relationship("CaseFile")
