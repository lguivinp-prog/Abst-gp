"""
Motor de Alertamiento Activo & Incidentes SRE (Fase 7.2)
Responsable de evaluar periódicamente reglas SRE sobre el estado de la plataforma,
gestionar deduplicación, cooldown e histéresis, registrar auditoría inmutable
y despachar eventos a canales externos (Webhooks, SIEM, Logs).
"""

import json
import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc

from app.models.domain import ProcessingMetrics, WorkerHeartbeat, ProcessingJob, AuditLog
from app.schemas.alerts import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    AlertEvent,
    AlertRuleConfig,
    AlertEvaluationSummary,
    WebhookPayload,
)
from app.core.telemetry import record_alert_event

logger = logging.getLogger("abst_gp.sre.alert_engine")


# ---------------------------------------------------------------------------
# Interfaces y Adaptadores de Despacho (Dispatchers)
# ---------------------------------------------------------------------------
class AlertDispatcher(ABC):
    """Interfaz base para adaptadores de notificación de incidentes SRE."""

    @abstractmethod
    def dispatch(self, alert: AlertEvent) -> bool:
        """Despacha un evento de alerta a su destino. Retorna True si tuvo éxito."""
        pass


class LogDispatcher(AlertDispatcher):
    """Dispatcher estructurado que emite registros de log con formato JSON."""

    def dispatch(self, alert: AlertEvent) -> bool:
        log_payload = {
            "source": "SRE_ALERT_ENGINE",
            "fingerprint": alert.fingerprint,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "status": alert.status,
            "tenant_id": alert.tenant_id,
            "entity_id": alert.entity_id,
            "metric_value": alert.metric_value,
            "threshold": alert.threshold,
            "message": alert.message,
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        }
        msg = f"[SRE ALERT {alert.status}] {alert.message} | Payload: {json.dumps(log_payload)}"
        if alert.severity in (AlertSeverity.CRITICAL, AlertSeverity.PAGE):
            logger.error(msg)
        elif alert.severity == AlertSeverity.WARNING:
            logger.warning(msg)
        else:
            logger.info(msg)
        return True


class WebhookDispatcher(AlertDispatcher):
    """Dispatcher HTTP para notificación externa (Slack, PagerDuty, SIEM, Webhooks institucionales)."""

    def __init__(
        self,
        webhook_url: str,
        timeout_seconds: float = 5.0,
        headers: Optional[Dict[str, str]] = None,
        client: Optional[httpx.Client] = None,
    ):
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds
        self.headers = headers or {"Content-Type": "application/json"}
        self._client = client

    def dispatch(self, alert: AlertEvent) -> bool:
        payload_obj = WebhookPayload(
            source="abst_gp_sre_alert_engine",
            event=alert,
            dispatched_at=datetime.now(timezone.utc),
        )
        payload_dict = json.loads(payload_obj.model_dump_json())

        try:
            if self._client:
                resp = self._client.post(
                    self.webhook_url,
                    json=payload_dict,
                    headers=self.headers,
                )
                return 200 <= resp.status_code < 300
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(
                        self.webhook_url,
                        json=payload_dict,
                        headers=self.headers,
                    )
                    return 200 <= resp.status_code < 300
        except Exception as exc:
            logger.error(
                f"Error al despachar alerta vía Webhook a {self.webhook_url}: {str(exc)}"
            )
            return False


class InMemoryDispatcher(AlertDispatcher):
    """Dispatcher en memoria para pruebas unitarias e inspección de estado."""

    def __init__(self):
        self.dispatched_alerts: List[AlertEvent] = []
        self._lock = threading.Lock()

    def dispatch(self, alert: AlertEvent) -> bool:
        with self._lock:
            self.dispatched_alerts.append(alert.model_copy(deep=True))
        return True

    def clear(self) -> None:
        with self._lock:
            self.dispatched_alerts.clear()


# ---------------------------------------------------------------------------
# Motor Central de Reglas SRE e Incidentes
# ---------------------------------------------------------------------------
class AlertEngine:
    """
    Motor de evaluación proactiva de salud operacional y gestión de incidentes SRE.
    Garantiza:
    - Evaluación periódica de métricas y heartbeats desde PostgreSQL (SSOT).
    - Deduplicación por huella digital (alert_type + tenant_id + entity_id).
    - Período de enfriamiento (cooldown) y prevención de tormentas de alertas.
    - Histéresis de resolución (transición FIRING -> RESOLVED).
    - Auditoría inmutable en AuditLog y telemetría Prometheus (abst_alerts_total).
    """

    def __init__(
        self,
        config: Optional[AlertRuleConfig] = None,
        dispatchers: Optional[List[AlertDispatcher]] = None,
    ):
        self.config = config or AlertRuleConfig()
        self.dispatchers: List[AlertDispatcher] = dispatchers or [LogDispatcher()]
        self._lock = threading.Lock()

        # Estado en memoria
        self._active_alerts: Dict[str, AlertEvent] = {}
        self._last_dispatched: Dict[str, datetime] = {}
        self._sla_consecutive_cycles: Dict[str, int] = {}

    @staticmethod
    def build_fingerprint(
        alert_type: AlertType,
        tenant_id: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> str:
        """Construye la clave única de deduplicación (fingerprint)."""
        safe_tenant = str(tenant_id).strip() if tenant_id else "global"
        safe_entity = str(entity_id).strip() if entity_id else "*"
        return f"{alert_type.value}:{safe_tenant}:{safe_entity}"

    def get_active_alerts(self) -> List[AlertEvent]:
        """Retorna una copia de las alertas actualmente en estado FIRING."""
        with self._lock:
            return [a.model_copy(deep=True) for a in self._active_alerts.values()]

    def _persist_audit_log(self, db: Session, alert: AlertEvent, action_suffix: str) -> None:
        """Registra un evento de alerta en AuditLog de forma inmutable."""
        try:
            audit = AuditLog(
                tenant_id=alert.tenant_id if alert.tenant_id and alert.tenant_id != "global" else "mega_tenant",
                user_id=None,
                action=f"SRE_ALERT_{action_suffix}",
                entity_type="SRE_INCIDENT",
                entity_id=alert.fingerprint,
                status=alert.status,
                details=json.dumps({
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "metric_value": alert.metric_value,
                    "threshold": alert.threshold,
                    "message": alert.message,
                    "actor": "SYSTEM_SRE_ALERT_ENGINE"
                })
            )
            db.add(audit)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error(f"Error al registrar AuditLog de alerta SRE: {str(exc)}")

    def _dispatch_to_all(self, alert: AlertEvent) -> None:
        """Envía el evento de alerta a todos los dispatchers configurados."""
        for d in self.dispatchers:
            try:
                d.dispatch(alert)
            except Exception as exc:
                logger.error(f"Fallo en dispatcher {d.__class__.__name__}: {str(exc)}")

    def process_firing_alert(self, db: Session, alert: AlertEvent) -> AlertEvent:
        """
        Procesa una condición anómala detectada:
        - Si es nueva o el cooldown expiró: marca FIRING, despacha y audita.
        - Si está dentro de cooldown: marca SUPPRESSED y no re-notifica.
        """
        now = datetime.now(timezone.utc)
        fp = alert.fingerprint

        with self._lock:
            is_active = fp in self._active_alerts
            last_sent = self._last_dispatched.get(fp)

            if is_active and last_sent:
                elapsed_seconds = (now - last_sent).total_seconds()
                if elapsed_seconds < self.config.cooldown_seconds:
                    # Enfriamiento activo: silenciar notificación repetida
                    alert.status = AlertStatus.SUPPRESSED
                    return alert

            # Disparo confirmado (nuevo o cooldown expirado)
            alert.status = AlertStatus.FIRING
            alert.triggered_at = now
            self._active_alerts[fp] = alert.model_copy(deep=True)
            self._last_dispatched[fp] = now

        # Telemetría técnica Prometheus (sin tenant_id)
        record_alert_event(
            alert_type=alert.alert_type,
            severity=alert.severity,
            status=AlertStatus.FIRING.value,
        )

        # Auditoría SSOT en PostgreSQL
        self._persist_audit_log(db, alert, "FIRING")

        # Notificación a dispatchers
        self._dispatch_to_all(alert)
        return alert

    def process_resolved_alert(
        self,
        db: Session,
        alert_type: AlertType,
        tenant_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        recovery_message: str = "Condición anómala resuelta.",
    ) -> Optional[AlertEvent]:
        """
        Procesa la recuperación de una condición:
        - Si existía una alerta FIRING previa: emite evento RESOLVED, limpia estado y audita.
        """
        fp = self.build_fingerprint(alert_type, tenant_id, entity_id)
        now = datetime.now(timezone.utc)

        with self._lock:
            if fp not in self._active_alerts:
                return None

            prev_alert = self._active_alerts.pop(fp)
            self._sla_consecutive_cycles.pop(fp, None)

            resolved_event = AlertEvent(
                alert_type=prev_alert.alert_type,
                severity=prev_alert.severity,
                status=AlertStatus.RESOLVED,
                tenant_id=prev_alert.tenant_id,
                entity_id=prev_alert.entity_id,
                fingerprint=fp,
                triggered_at=prev_alert.triggered_at,
                resolved_at=now,
                metric_value=prev_alert.metric_value,
                threshold=prev_alert.threshold,
                message=recovery_message,
                metadata=prev_alert.metadata,
            )

        # Telemetría técnica Prometheus
        record_alert_event(
            alert_type=resolved_event.alert_type,
            severity=resolved_event.severity,
            status=AlertStatus.RESOLVED.value,
        )

        # Auditoría SSOT en PostgreSQL
        self._persist_audit_log(db, resolved_event, "RESOLVED")

        # Notificación a dispatchers
        self._dispatch_to_all(resolved_event)
        return resolved_event

    # -----------------------------------------------------------------------
    # Reglas SRE Específicas
    # -----------------------------------------------------------------------

    def evaluate_sla_breaches(self, db: Session) -> List[AlertEvent]:
        """
        Regla 1: SLA Breach
        Condición: p95(duración_total) > 30s durante 3 ciclos consecutivos.
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=self.config.error_spike_window_minutes)
        events: List[AlertEvent] = []

        # Agrupar métricas recientes por tenant y job_type
        # Usamos cálculo directo en Python sobre las duraciones de la ventana para máxima compatibilidad
        records = (
            db.query(
                ProcessingMetrics.tenant_id,
                ProcessingMetrics.job_type,
                ProcessingMetrics.total_time_ms,
            )
            .filter(ProcessingMetrics.created_at >= window_start)
            .all()
        )

        grouped: Dict[Tuple[str, str], List[float]] = {}
        for t_id, j_type, t_ms in records:
            key = (t_id, j_type)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(float(t_ms or 0) / 1000.0)

        evaluated_fps = set()

        for (t_id, j_type), durations in grouped.items():
            if not durations:
                continue

            durations.sort()
            # Cálculo de percentil 95
            k = (len(durations) - 1) * 0.95
            f = int(k)
            c = min(f + 1, len(durations) - 1)
            d0 = durations[f] * (c - k)
            d1 = durations[c] * (k - f)
            p95 = d0 + d1

            fp = self.build_fingerprint(AlertType.SLA_BREACH, t_id, j_type)
            evaluated_fps.add(fp)

            if p95 > self.config.sla_p95_threshold_seconds:
                with self._lock:
                    count = self._sla_consecutive_cycles.get(fp, 0) + 1
                    self._sla_consecutive_cycles[fp] = count

                if count >= self.config.sla_consecutive_cycles_required:
                    severity = (
                        AlertSeverity.CRITICAL
                        if p95 > (self.config.sla_p95_threshold_seconds * 2)
                        else AlertSeverity.WARNING
                    )
                    event = AlertEvent(
                        alert_type=AlertType.SLA_BREACH,
                        severity=severity,
                        tenant_id=t_id,
                        entity_id=j_type,
                        fingerprint=fp,
                        metric_value=round(p95, 2),
                        threshold=self.config.sla_p95_threshold_seconds,
                        message=(
                            f"SLA Breach detectado para tenant '{t_id}' ({j_type}): "
                            f"p95={p95:.2f}s > umbral {self.config.sla_p95_threshold_seconds}s "
                            f"durante {count} ciclos consecutivos."
                        ),
                    )
                    events.append(self.process_firing_alert(db, event))
            else:
                # Condición saludable: resetear ciclos y resolver si estaba activa
                with self._lock:
                    self._sla_consecutive_cycles[fp] = 0
                res = self.process_resolved_alert(
                    db,
                    AlertType.SLA_BREACH,
                    t_id,
                    j_type,
                    f"Latencia SLA normalizada ({j_type}): p95={p95:.2f}s <= {self.config.sla_p95_threshold_seconds}s.",
                )
                if res:
                    events.append(res)

        return events

    def evaluate_workers_down(self, db: Session) -> List[AlertEvent]:
        """
        Regla 2: Worker Down
        Condición: Worker sin latido (last_seen > 60s) y status != 'OFFLINE'.
        """
        now = datetime.now(timezone.utc)
        threshold_dt = now - timedelta(seconds=self.config.worker_down_threshold_seconds)
        events: List[AlertEvent] = []

        workers = db.query(WorkerHeartbeat).all()

        for w in workers:
            fp = self.build_fingerprint(AlertType.WORKER_DOWN, w.tenant_id, w.worker_name)
            last_seen = w.last_seen
            if last_seen and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)

            is_unresponsive = (
                w.status != "OFFLINE"
                and last_seen
                and last_seen < threshold_dt
            )

            if is_unresponsive:
                seconds_dead = (now - last_seen).total_seconds()
                event = AlertEvent(
                    alert_type=AlertType.WORKER_DOWN,
                    severity=AlertSeverity.CRITICAL,
                    tenant_id=w.tenant_id,
                    entity_id=w.worker_name,
                    fingerprint=fp,
                    metric_value=round(seconds_dead, 1),
                    threshold=self.config.worker_down_threshold_seconds,
                    message=(
                        f"Worker '{w.worker_name}' ({w.worker_type}) en estado UNRESPONSIVE: "
                        f"sin latido hace {seconds_dead:.1f}s (> {self.config.worker_down_threshold_seconds}s)."
                    ),
                    metadata={"hostname": w.hostname, "worker_type": w.worker_type},
                )
                events.append(self.process_firing_alert(db, event))
            else:
                # Worker recuperado o apagado ordenadamente
                res = self.process_resolved_alert(
                    db,
                    AlertType.WORKER_DOWN,
                    w.tenant_id,
                    w.worker_name,
                    f"Worker '{w.worker_name}' recuperó conectividad operativa (status={w.status}).",
                )
                if res:
                    events.append(res)

        return events

    def evaluate_error_spikes(self, db: Session) -> List[AlertEvent]:
        """
        Regla 3: Error Spike
        Condición: failure_rate > 5% en una ventana de 15 minutos con muestra mínima >= 5.
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=self.config.error_spike_window_minutes)
        events: List[AlertEvent] = []

        # Agrupar métricas por tenant_id
        metrics = (
            db.query(ProcessingMetrics)
            .filter(ProcessingMetrics.created_at >= window_start)
            .all()
        )

        by_tenant: Dict[str, List[ProcessingMetrics]] = {}
        for m in metrics:
            t_id = m.tenant_id or "mega_tenant"
            if t_id not in by_tenant:
                by_tenant[t_id] = []
            by_tenant[t_id].append(m)

        for t_id, sample in by_tenant.items():
            total_count = len(sample)
            if total_count < self.config.error_spike_min_samples:
                # Muestra insuficiente: evitar falsos positivos
                continue

            failed_count = sum(1 for m in sample if not m.success)
            failure_rate = failed_count / total_count

            fp = self.build_fingerprint(AlertType.ERROR_SPIKE, t_id, "cluster")

            if failure_rate > self.config.error_spike_rate_threshold:
                severity = (
                    AlertSeverity.CRITICAL
                    if failure_rate > 0.20
                    else AlertSeverity.WARNING
                )
                event = AlertEvent(
                    alert_type=AlertType.ERROR_SPIKE,
                    severity=severity,
                    tenant_id=t_id,
                    entity_id="cluster",
                    fingerprint=fp,
                    metric_value=round(failure_rate * 100, 2),
                    threshold=round(self.config.error_spike_rate_threshold * 100, 2),
                    message=(
                        f"Pico de errores detectado para tenant '{t_id}': "
                        f"tasa de fallos {failure_rate * 100:.1f}% ({failed_count}/{total_count} jobs) "
                        f"> umbral {self.config.error_spike_rate_threshold * 100:.1f}% en los últimos 15 min."
                    ),
                    metadata={"failed_count": failed_count, "total_count": total_count},
                )
                events.append(self.process_firing_alert(db, event))
            else:
                res = self.process_resolved_alert(
                    db,
                    AlertType.ERROR_SPIKE,
                    t_id,
                    "cluster",
                    f"Tasa de fallos normalizada para tenant '{t_id}': {failure_rate * 100:.1f}% ({failed_count}/{total_count} jobs).",
                )
                if res:
                    events.append(res)

        return events

    def evaluate_recovery_failures(self, db: Session) -> List[AlertEvent]:
        """
        Regla 4: Recovery Failure
        Condición: Jobs que alcanzaron attempt_count >= max_retries o fallo definitivo FINAL.
        """
        events: List[AlertEvent] = []

        exhausted_jobs = (
            db.query(ProcessingJob)
            .filter(
                or_(
                    ProcessingJob.attempt_count >= ProcessingJob.max_retries,
                    and_(
                        ProcessingJob.status == "FAILED",
                        ProcessingJob.failure_classification == "FINAL",
                    ),
                )
            )
            .all()
        )

        for job in exhausted_jobs:
            fp = self.build_fingerprint(
                AlertType.RECOVERY_FAILURE, job.tenant_id, job.job_id
            )
            event = AlertEvent(
                alert_type=AlertType.RECOVERY_FAILURE,
                severity=AlertSeverity.CRITICAL,
                tenant_id=job.tenant_id,
                entity_id=job.job_id,
                fingerprint=fp,
                metric_value=float(job.attempt_count),
                threshold=float(job.max_retries),
                message=(
                    f"Fallo definitivo de recuperación para job '{job.job_id}' ({job.job_type}) "
                    f"en tenant '{job.tenant_id}': superó max_retries ({job.attempt_count}/{job.max_retries}) "
                    f"o clasificación FINAL. Error: {job.error_message or 'N/A'}."
                ),
                metadata={"job_type": job.job_type, "worker_name": job.worker_name},
            )
            events.append(self.process_firing_alert(db, event))

        return events

    def evaluate_all(self, db: Session) -> AlertEvaluationSummary:
        """Ejecuta una ronda completa de evaluación de todas las reglas SRE."""
        now = datetime.now(timezone.utc)
        all_events: List[AlertEvent] = []

        all_events.extend(self.evaluate_sla_breaches(db))
        all_events.extend(self.evaluate_workers_down(db))
        all_events.extend(self.evaluate_error_spikes(db))
        all_events.extend(self.evaluate_recovery_failures(db))

        firing_count = sum(1 for e in all_events if e.status == AlertStatus.FIRING)
        resolved_count = sum(1 for e in all_events if e.status == AlertStatus.RESOLVED)
        suppressed_count = sum(
            1 for e in all_events if e.status == AlertStatus.SUPPRESSED
        )

        return AlertEvaluationSummary(
            evaluated_at=now,
            alerts_evaluated=len(all_events),
            alerts_firing=firing_count,
            alerts_resolved=resolved_count,
            alerts_suppressed=suppressed_count,
            events=all_events,
        )

    def emit_dr_alert(
        self,
        db: Session,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        metric_value: float = 0.0,
        threshold: float = 0.0,
        tenant_id: Optional[str] = None,
        entity_id: Optional[str] = "disaster_recovery",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AlertEvent:
        """
        Emite una alerta explícita de Disaster Recovery / Continuidad Operacional (Fase 7.4).
        Cumple deduplicación, cooldown, auditoría inmutable en PostgreSQL y despacho sin secretos.
        """
        # Sanitizar metadatos para nunca filtrar secretos o URLs con credenciales
        sanitized_meta = {}
        if metadata:
            for k, v in metadata.items():
                if any(secret_key in k.lower() for secret_key in ("secret", "password", "token", "key", "url")):
                    sanitized_meta[k] = "[REDACTED]"
                else:
                    sanitized_meta[k] = v

        fp = self.build_fingerprint(alert_type, tenant_id, entity_id)
        event = AlertEvent(
            alert_type=alert_type,
            severity=severity,
            status=AlertStatus.FIRING,
            tenant_id=tenant_id,
            entity_id=entity_id,
            fingerprint=fp,
            metric_value=metric_value,
            threshold=threshold,
            message=message,
            metadata=sanitized_meta,
        )
        return self.process_firing_alert(db, event)



# Singleton del AlertEngine para la aplicación
global_alert_engine = AlertEngine()
