from app.models.base import Base
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func

class CiiuCatalog(Base):
    __tablename__ = "ciiu_catalog"
    
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), nullable=False, index=True)
    descripcion = Column(Text, nullable=False)
    version = Column(String(50), nullable=False)
    fuente = Column(String(100), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_actualizacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
