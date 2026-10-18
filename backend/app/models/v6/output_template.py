from app.models.base import Base
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Index, text
from sqlalchemy.sql import func

class OutputTemplate(Base):
    __tablename__ = "output_templates"
    __table_args__ = (
        Index(
            'uq_output_templates_p13',
            'type', 'entity_name', 'version',
            unique=True,
            postgresql_where=text("type = 'INFORME_TECNICO_EVALUACION'")
        ),
        {'extend_existing': True}
    )
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), nullable=False) # CONDICIONES, INFORME, PREVIEW, INFORME_TECNICO_EVALUACION
    version = Column(String(20), nullable=False)
    entity_name = Column(String, nullable=False)
    validity = Column(String(50), nullable=True)
    content = Column(Text, nullable=False) # Template string with secure placeholders
    checksum = Column(String(64), nullable=True) # Checksum SHA-256 congelado del contenido
    status = Column(String(50), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
