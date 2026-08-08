"""
Schemas y Modelos de Datos para el Sistema de Alertamiento SRE e Incidentes (Fase 7.2)
Define enums, contratos de eventos de alerta, configuración de umbrales y payloads para dispatchers.
"""

from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class AlertSeverity(str, Enum):
    """Nivel de severidad de un incidente o alerta SRE."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    PAGE = "PAGE"


class AlertStatus(str, Enum):
    """Estado del ciclo de vida de una alerta."""
    FIRING = "FIRING"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class AlertType(str, Enum):
    """Taxonomía de tipos de alerta SRE."""
    SLA_BREACH = "SLA_BREACH"
    WORKER_DOWN = "WORKER_DOWN"
    ERROR_SPIKE = "ERROR_SPIKE"
    RECOVERY_FAILURE = "RECOVERY_FAILURE"
    # Tipos de alerta de Disaster Recovery & Continuidad (Fase 7.4)
    DR_BACKUP_FAILED = "DR_BACKUP_FAILED"
    DR_RESTORE_FAILED = "DR_RESTORE_FAILED"
    DR_RPO_BREACH = "DR_RPO_BREACH"
    DR_RTO_BREACH = "DR_RTO_BREACH"
    DR_WAL_ARCHIVE_LAG = "DR_WAL_ARCHIVE_LAG"
    DR_BACKUP_EXPIRED = "DR_BACKUP_EXPIRED"
    DR_CHECKSUM_INVALID = "DR_CHECKSUM_INVALID"


class AlertEvent(BaseModel):
    """Evento inmutable que describe una condición de alerta detectada."""
    model_config = ConfigDict(use_enum_values=True)

    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.FIRING
    tenant_id: Optional[str] = None
    entity_id: Optional[str] = None
    fingerprint: str
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metric_value: float
    threshold: float
    message: str
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AlertRuleConfig(BaseModel):
    """Configuración de umbrales e histéresis para las reglas del AlertEngine."""
    model_config = ConfigDict(validate_assignment=True)

    sla_p95_threshold_seconds: float = 30.0
    sla_consecutive_cycles_required: int = 3
    worker_down_threshold_seconds: float = 60.0
    error_spike_rate_threshold: float = 0.05  # 5%
    error_spike_window_minutes: int = 15
    error_spike_min_samples: int = 5
    cooldown_seconds: int = 900  # 15 minutos entre notificaciones repetidas
    # Umbrales DR (Fase 7.4)
    dr_rpo_threshold_seconds: float = 300.0  # 5 minutos
    dr_rto_threshold_seconds: float = 900.0  # 15 minutos
    dr_wal_lag_threshold_seconds: float = 300.0  # 5 minutos



class AlertEvaluationSummary(BaseModel):
    """Resumen de una corrida de evaluación de reglas SRE."""
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    alerts_evaluated: int = 0
    alerts_firing: int = 0
    alerts_resolved: int = 0
    alerts_suppressed: int = 0
    events: List[AlertEvent] = Field(default_factory=list)


class WebhookPayload(BaseModel):
    """Payload estándar para despacho de alertas a sistemas externos (Slack, PagerDuty, SIEM)."""
    version: str = "1.0"
    source: str = "abst_gp_sre_alert_engine"
    event: AlertEvent
    dispatched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
