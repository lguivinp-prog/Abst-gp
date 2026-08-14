from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.models.base import Base

class TenantConfiguration(Base):
    __tablename__ = "tenant_configurations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, unique=True, index=True, nullable=False)
    
    # Operational Config
    min_dpi_threshold = Column(Integer, default=150)
    min_rag_confidence = Column(Integer, default=70)
    
    # Critical Config
    telemetry_opt_in = Column(Boolean, default=False)
    
    # Versioning
    configuration_version = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TenantConfigurationHistory(Base):
    __tablename__ = "tenant_configuration_history"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    version = Column(Integer, nullable=False)
    
    field_changed = Column(String, nullable=False)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    
    changed_by_user_id = Column(Integer, nullable=False)
    reason = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

