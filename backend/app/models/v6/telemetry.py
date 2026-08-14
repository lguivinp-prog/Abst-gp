from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.db.base_class import Base

class InstitutionalTelemetryEvent(Base):
    __tablename__ = "institutional_telemetry_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False) # Hashed or abstracted tenant identifier
    system_version = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 1. Rendimiento / Performance
    avg_rag_latency_ms = Column(Float, nullable=True)
    avg_ocr_latency_ms = Column(Float, nullable=True)
    
    # 2. Conteos Operacionales (Anonimizados)
    total_cases_processed = Column(Integer, default=0)
    total_supervisor_exceptions = Column(Integer, default=0)
    
    # 3. Errores / Bloqueos
    blocked_by_quality_gate = Column(Integer, default=0) # Sum of QUALITY_BLOCKED
    api_fallback_events = Column(Integer, default=0) # Sum of MANUAL_REQUIRED fallbacks
    
    # 4. Indicadores de Calidad IA (Gobernanza)
    rag_human_correction_rate = Column(Float, nullable=True) # Percentage of times human edited RAG output
    
    # Flags de Privacidad
    telemetry_policy_version = Column(String, nullable=False)
    opt_in_status = Column(Boolean, nullable=False, default=False)
    
    # NEVER store RUC, supplier names, contract texts, or specific case IDs here.
