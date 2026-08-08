"""
Suite de Pruebas Unitarias para el Motor de Alertamiento SRE e Incidentes (Fase 7.2)
Valida:
1. Detección de SLA Breach tras ciclos consecutivos requeridos.
2. Detección y resolución de Worker Down (heartbeats expirados).
3. Detección de Error Spike con filtro de tamaño mínimo de muestra.
4. Detección de Recovery Failure (jobs con max_retries agotados).
5. Deduplicación por fingerprint y período de enfriamiento (cooldown).
6. Histéresis y despacho de evento RESOLVED al normalizarse la condición.
7. Aislamiento estricto multi-tenant en eventos de alerta.
8. Registro de auditoría inmutable en AuditLog (actor SYSTEM_SRE_ALERT_ENGINE).
9. Despacho HTTP en WebhookDispatcher con tolerancia a fallos.
10. Incremento de métricas Prometheus (abst_alerts_total).
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Generator, Optional
import pytest
import httpx
from sqlalchemy.orm import Session

from app.models.domain import (
    Tenant,
    CaseFile,
    ProcessingJob,
    ProcessingMetrics,
    WorkerHeartbeat,
    AuditLog,
)
from app.schemas.alerts import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    AlertEvent,
    AlertRuleConfig,
)
from app.services.alert_engine import (
    AlertEngine,
    InMemoryDispatcher,
    WebhookDispatcher,
    LogDispatcher,
)
from app.core.telemetry import metrics_registry


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def dispatcher() -> InMemoryDispatcher:
    return InMemoryDispatcher()


@pytest.fixture(scope="function")
def alert_engine(dispatcher: InMemoryDispatcher) -> AlertEngine:
    config = AlertRuleConfig(
        sla_p95_threshold_seconds=30.0,
        sla_consecutive_cycles_required=3,
        worker_down_threshold_seconds=60.0,
        error_spike_rate_threshold=0.05,
        error_spike_window_minutes=15,
        error_spike_min_samples=5,
        cooldown_seconds=900,
    )
    return AlertEngine(config=config, dispatchers=[dispatcher])


@pytest.fixture(autouse=True)
def setup_tenants(db_session: Session):
    """Garantiza que existan tenants de prueba en la base de datos."""
    for t_id, name in [
        ("tenant_alpha", "Alpha Corp"),
        ("tenant_beta", "Beta Corp"),
        ("mega_tenant", "Mega Tenant"),
    ]:
        existing = db_session.query(Tenant).filter(Tenant.id == t_id).first()
        if not existing:
            db_session.add(Tenant(id=t_id, name=name))
    db_session.commit()


def create_metric_with_job(
    db_session: Session,
    tenant_id: str,
    job_type: str = "REQUIREMENT_OCR",
    total_time_ms: int = 1000,
    success: bool = True,
    error_code: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> ProcessingMetrics:
    """Helper que crea un ProcessingJob válido y su respectivo ProcessingMetrics asociado."""
    j_id = f"job_{uuid.uuid4()}"
    job = ProcessingJob(
        job_id=j_id,
        tenant_id=tenant_id,
        job_type=job_type,
        status="READY" if success else "FAILED",
    )
    db_session.add(job)
    db_session.flush()

    metric = ProcessingMetrics(
        job_id=j_id,
        tenant_id=tenant_id,
        job_type=job_type,
        queue_time_ms=100,
        processing_time_ms=max(0, total_time_ms - 100),
        total_time_ms=total_time_ms,
        success=success,
        error_code=error_code,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(metric)
    db_session.commit()
    return metric


# ---------------------------------------------------------------------------
# Test 1: SLA Breach Detection (Ciclos Consecutivos)
# ---------------------------------------------------------------------------
def test_sla_breach_detection_consecutive_cycles(db_session: Session, alert_engine: AlertEngine, dispatcher: InMemoryDispatcher):
    """Verifica que SLA_BREACH requiera 3 ciclos consecutivos de p95 > 30s para disparar FIRING."""
    # Limpiar métricas previas de este tipo
    db_session.query(ProcessingMetrics).filter(
        ProcessingMetrics.tenant_id == "tenant_alpha",
        ProcessingMetrics.job_type == "QUOTATION_EXTRACTION"
    ).delete()
    db_session.commit()

    # Insertar métricas con duración de 45s (45000ms)
    for _ in range(10):
        create_metric_with_job(
            db_session=db_session,
            tenant_id="tenant_alpha",
            job_type="QUOTATION_EXTRACTION",
            total_time_ms=45000,
            success=True,
        )

    # Ciclo 1: detecta p95 > 30s pero cuenta = 1 < 3 -> No dispara alerta
    events_1 = alert_engine.evaluate_sla_breaches(db_session)
    assert len(events_1) == 0
    assert len(dispatcher.dispatched_alerts) == 0

    # Ciclo 2: cuenta = 2 < 3 -> No dispara alerta
    events_2 = alert_engine.evaluate_sla_breaches(db_session)
    assert len(events_2) == 0
    assert len(dispatcher.dispatched_alerts) == 0

    # Ciclo 3: cuenta = 3 >= 3 -> DISPARA FIRING
    events_3 = alert_engine.evaluate_sla_breaches(db_session)
    assert len(events_3) == 1
    assert events_3[0].status == AlertStatus.FIRING
    assert events_3[0].alert_type == AlertType.SLA_BREACH
    assert events_3[0].tenant_id == "tenant_alpha"
    assert events_3[0].metric_value >= 45.0
    assert len(dispatcher.dispatched_alerts) == 1


# ---------------------------------------------------------------------------
# Test 2: SLA Breach Resolution
# ---------------------------------------------------------------------------
def test_sla_breach_resolution(db_session: Session, alert_engine: AlertEngine, dispatcher: InMemoryDispatcher):
    """Verifica que al normalizarse la latencia se emita un evento RESOLVED y se limpie el estado."""
    db_session.query(ProcessingMetrics).filter(
        ProcessingMetrics.tenant_id == "tenant_alpha",
        ProcessingMetrics.job_type == "COMPARISON_RUN"
    ).delete()
    db_session.commit()

    # 1. Crear condición de violación
    for _ in range(5):
        create_metric_with_job(
            db_session=db_session,
            tenant_id="tenant_alpha",
            job_type="COMPARISON_RUN",
            total_time_ms=50000,
            success=True,
        )

    # Ejecutar 3 ciclos para activar la alerta
    alert_engine.evaluate_sla_breaches(db_session)
    alert_engine.evaluate_sla_breaches(db_session)
    firing_events = alert_engine.evaluate_sla_breaches(db_session)
    assert len(firing_events) == 1
    assert firing_events[0].status == AlertStatus.FIRING

    # 2. Reemplazar con métricas rápidas (500ms) para bajar el p95 a < 30s
    db_session.query(ProcessingMetrics).filter(
        ProcessingMetrics.tenant_id == "tenant_alpha",
        ProcessingMetrics.job_type == "COMPARISON_RUN"
    ).delete()
    db_session.commit()

    for _ in range(10):
        create_metric_with_job(
            db_session=db_session,
            tenant_id="tenant_alpha",
            job_type="COMPARISON_RUN",
            total_time_ms=500,
            success=True,
        )

    # 3. Siguiente evaluación: p95 baja y emite RESOLVED
    res_events = alert_engine.evaluate_sla_breaches(db_session)
    assert len(res_events) == 1
    assert res_events[0].status == AlertStatus.RESOLVED
    assert res_events[0].alert_type == AlertType.SLA_BREACH
    assert len(alert_engine.get_active_alerts()) == 0


# ---------------------------------------------------------------------------
# Test 3: Worker Down Detection and Recovery
# ---------------------------------------------------------------------------
def test_worker_down_detection_and_recovery(db_session: Session, alert_engine: AlertEngine, dispatcher: InMemoryDispatcher):
    """Verifica la detección de un worker sin latido (> 60s) y su posterior recuperación."""
    worker_name = f"worker_test_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(seconds=90)

    # Worker sin latido hace 90s
    worker = WorkerHeartbeat(
        worker_name=worker_name,
        worker_type="abst_worker_ocr",
        hostname="node-01.infra",
        status="BUSY",
        tenant_id="tenant_alpha",
        last_seen=expired_time,
    )
    db_session.add(worker)
    db_session.commit()

    # Evaluación: Debe disparar WORKER_DOWN para este worker
    events = alert_engine.evaluate_workers_down(db_session)
    worker_events = [e for e in events if e.entity_id == worker_name]
    assert len(worker_events) == 1
    assert worker_events[0].status == AlertStatus.FIRING
    assert worker_events[0].alert_type == AlertType.WORKER_DOWN
    assert worker_events[0].severity == AlertSeverity.CRITICAL

    # Recuperación: Worker envía heartbeat actualizado
    worker.last_seen = datetime.now(timezone.utc)
    worker.status = "IDLE"
    db_session.commit()

    # Evaluación: Debe resolver la alerta
    recovery_events = alert_engine.evaluate_workers_down(db_session)
    resolved_worker_events = [e for e in recovery_events if e.entity_id == worker_name]
    assert len(resolved_worker_events) == 1
    assert resolved_worker_events[0].status == AlertStatus.RESOLVED
    assert resolved_worker_events[0].alert_type == AlertType.WORKER_DOWN


# ---------------------------------------------------------------------------
# Test 4: Error Spike Detection with Min Sample Size
# ---------------------------------------------------------------------------
def test_error_spike_detection_with_min_sample_size(db_session: Session, alert_engine: AlertEngine, dispatcher: InMemoryDispatcher):
    """Verifica que no se disparen alertas de pico de error si la muestra es menor al mínimo (< 5)."""
    t_id = f"tenant_spike_{uuid.uuid4().hex[:6]}"
    db_session.add(Tenant(id=t_id, name="Spike Test Corp"))
    db_session.commit()

    # 1. Crear 2 fallos de 2 jobs (100% de fallo, pero muestra < 5)
    for _ in range(2):
        create_metric_with_job(
            db_session=db_session,
            tenant_id=t_id,
            job_type="REQUIREMENT_OCR",
            success=False,
            error_code="CORRUPT_PDF",
        )

    # Evaluación: No debe disparar por tamaño de muestra insuficiente
    events_low_sample = alert_engine.evaluate_error_spikes(db_session)
    t_events_low = [e for e in events_low_sample if e.tenant_id == t_id]
    assert len(t_events_low) == 0

    # 2. Agregar 8 trabajos más (4 fallidos, 4 exitosos) -> Total 10 jobs, 6 fallidos (60% > 5%)
    for _ in range(4):
        create_metric_with_job(
            db_session=db_session,
            tenant_id=t_id,
            job_type="REQUIREMENT_OCR",
            success=False,
            error_code="CORRUPT_PDF",
        )
    for _ in range(4):
        create_metric_with_job(
            db_session=db_session,
            tenant_id=t_id,
            job_type="REQUIREMENT_OCR",
            success=True,
        )

    # Evaluación: Con 10 muestras y 60% de fallo -> DISPARA ERROR_SPIKE
    events_spike = alert_engine.evaluate_error_spikes(db_session)
    t_events_spike = [e for e in events_spike if e.tenant_id == t_id]
    assert len(t_events_spike) == 1
    assert t_events_spike[0].status == AlertStatus.FIRING
    assert t_events_spike[0].alert_type == AlertType.ERROR_SPIKE
    assert t_events_spike[0].metric_value == 60.0


# ---------------------------------------------------------------------------
# Test 5: Recovery Failure Detection
# ---------------------------------------------------------------------------
def test_recovery_failure_detection(db_session: Session, alert_engine: AlertEngine, dispatcher: InMemoryDispatcher):
    """Verifica que se detecten trabajos que superaron max_retries o tienen fallo definitivo."""
    j_id = f"job_exhausted_{uuid.uuid4().hex[:8]}"
    job = ProcessingJob(
        job_id=j_id,
        tenant_id="tenant_beta",
        job_type="QUOTATION_EXTRACTION",
        status="FAILED",
        attempt_count=3,
        max_retries=3,
        failure_classification="FINAL",
        error_message="Document schema unrecoverable corrupt",
    )
    db_session.add(job)
    db_session.commit()

    events = alert_engine.evaluate_recovery_failures(db_session)
    job_events = [e for e in events if e.entity_id == j_id]
    assert len(job_events) == 1
    assert job_events[0].status == AlertStatus.FIRING
    assert job_events[0].alert_type == AlertType.RECOVERY_FAILURE
    assert job_events[0].tenant_id == "tenant_beta"


# ---------------------------------------------------------------------------
# Test 6: Deduplication and Cooldown Prevention
# ---------------------------------------------------------------------------
def test_fingerprint_deduplication_and_cooldown(db_session: Session, alert_engine: AlertEngine, dispatcher: InMemoryDispatcher):
    """Verifica que una condición anómala recurrente no genere tormenta de alertas dentro del cooldown."""
    alert_engine.config.cooldown_seconds = 600  # 10 minutos
    w_name = f"worker_cool_{uuid.uuid4().hex[:6]}"

    event = AlertEvent(
        alert_type=AlertType.WORKER_DOWN,
        severity=AlertSeverity.CRITICAL,
        tenant_id="tenant_alpha",
        entity_id=w_name,
        fingerprint=AlertEngine.build_fingerprint(AlertType.WORKER_DOWN, "tenant_alpha", w_name),
        metric_value=120.0,
        threshold=60.0,
        message="Worker unresponsive",
    )

    # 1. Primer disparo: FIRING -> Notificado al dispatcher
    res1 = alert_engine.process_firing_alert(db_session, event)
    assert res1.status == AlertStatus.FIRING
    assert len(dispatcher.dispatched_alerts) == 1

    # 2. Segundo disparo inmediato: SUPPRESSED -> No notificado al dispatcher
    event_repeat = event.model_copy(deep=True)
    res2 = alert_engine.process_firing_alert(db_session, event_repeat)
    assert res2.status == AlertStatus.SUPPRESSED
    assert len(dispatcher.dispatched_alerts) == 1  # No se incrementó

    # 3. Alertas activas contiene la entrada
    assert any(a.fingerprint == event.fingerprint for a in alert_engine.get_active_alerts())


# ---------------------------------------------------------------------------
# Test 7: Multi-Tenant Isolation
# ---------------------------------------------------------------------------
def test_multi_tenant_isolation_in_alerts(db_session: Session, alert_engine: AlertEngine, dispatcher: InMemoryDispatcher):
    """Verifica que métricas y fallos de un tenant no afecten ni disparen alertas en otro tenant."""
    t_iso_a = f"tenant_iso_a_{uuid.uuid4().hex[:6]}"
    t_iso_b = f"tenant_iso_b_{uuid.uuid4().hex[:6]}"
    db_session.add_all([Tenant(id=t_iso_a, name="Iso A"), Tenant(id=t_iso_b, name="Iso B")])
    db_session.commit()

    # Tenant Alpha: 10 jobs con 100% de fallos
    for _ in range(10):
        create_metric_with_job(
            db_session=db_session,
            tenant_id=t_iso_a,
            job_type="REQUIREMENT_OCR",
            success=False,
        )

    # Tenant Beta: 10 jobs con 100% de éxito
    for _ in range(10):
        create_metric_with_job(
            db_session=db_session,
            tenant_id=t_iso_b,
            job_type="REQUIREMENT_OCR",
            success=True,
        )

    events = alert_engine.evaluate_error_spikes(db_session)
    events_a = [e for e in events if e.tenant_id == t_iso_a]
    events_b = [e for e in events if e.tenant_id == t_iso_b]

    assert len(events_a) == 1
    assert events_a[0].metric_value == 100.0
    assert len(events_b) == 0


# ---------------------------------------------------------------------------
# Test 8: Immutable AuditLog Persistence
# ---------------------------------------------------------------------------
def test_audit_log_generation_on_firing_and_resolved(db_session: Session, alert_engine: AlertEngine, dispatcher: InMemoryDispatcher):
    """Verifica que tanto FIRING como RESOLVED generen registros inmutables en AuditLog con actor SYSTEM_SRE_ALERT_ENGINE."""
    w_name = f"worker_sec_{uuid.uuid4().hex[:6]}"
    event = AlertEvent(
        alert_type=AlertType.WORKER_DOWN,
        severity=AlertSeverity.CRITICAL,
        tenant_id="tenant_alpha",
        entity_id=w_name,
        fingerprint=AlertEngine.build_fingerprint(AlertType.WORKER_DOWN, "tenant_alpha", w_name),
        metric_value=85.0,
        threshold=60.0,
        message="Worker down test",
    )

    # 1. Disparar FIRING
    alert_engine.process_firing_alert(db_session, event)

    audit_firing = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "SRE_ALERT_FIRING", AuditLog.entity_id == event.fingerprint)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_firing is not None
    assert audit_firing.entity_type == "SRE_INCIDENT"
    assert "SYSTEM_SRE_ALERT_ENGINE" in audit_firing.details

    # 2. Disparar RESOLVED
    alert_engine.process_resolved_alert(
        db_session,
        alert_type=AlertType.WORKER_DOWN,
        tenant_id="tenant_alpha",
        entity_id=w_name,
    )

    audit_resolved = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "SRE_ALERT_RESOLVED", AuditLog.entity_id == event.fingerprint)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_resolved is not None
    assert audit_resolved.status == "RESOLVED"


# ---------------------------------------------------------------------------
# Test 9: Webhook Dispatcher Execution and Fault Tolerance
# ---------------------------------------------------------------------------
def test_webhook_dispatcher_execution_and_fault_tolerance():
    """Verifica que el WebhookDispatcher despache correctamente y tolere fallos HTTP sin propagar excepciones."""
    # Mock client que simula éxito 200
    mock_transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "received"}))
    mock_client = httpx.Client(transport=mock_transport)

    dispatcher = WebhookDispatcher(webhook_url="https://sre.internal.institucion/webhook", client=mock_client)
    event = AlertEvent(
        alert_type=AlertType.SLA_BREACH,
        severity=AlertSeverity.WARNING,
        tenant_id="tenant_alpha",
        fingerprint="SLA_BREACH:tenant_alpha:REQUIREMENT_OCR",
        metric_value=35.0,
        threshold=30.0,
        message="SLA breached",
    )

    success = dispatcher.dispatch(event)
    assert success is True

    # Mock client que simula error 500
    mock_error_transport = httpx.MockTransport(lambda request: httpx.Response(500, text="Internal Error"))
    mock_err_client = httpx.Client(transport=mock_error_transport)
    err_dispatcher = WebhookDispatcher(webhook_url="https://sre.internal.institucion/webhook", client=mock_err_client)

    failure = err_dispatcher.dispatch(event)
    assert failure is False  # No lanza excepción, retorna False de forma segura


# ---------------------------------------------------------------------------
# Test 10: Prometheus Metric abst_alerts_total
# ---------------------------------------------------------------------------
def test_telemetry_metric_increment_on_alert(db_session: Session, alert_engine: AlertEngine):
    """Verifica que la emisión de alertas incremente el contador técnico abst_alerts_total en Prometheus."""
    initial_sample = metrics_registry.alerts_total.get_sample(
        alert_type="WORKER_DOWN", severity="CRITICAL", status="FIRING"
    )

    w_prom = f"worker_prom_{uuid.uuid4().hex[:6]}"
    event = AlertEvent(
        alert_type=AlertType.WORKER_DOWN,
        severity=AlertSeverity.CRITICAL,
        tenant_id="tenant_beta",
        entity_id=w_prom,
        fingerprint=AlertEngine.build_fingerprint(AlertType.WORKER_DOWN, "tenant_beta", w_prom),
        metric_value=75.0,
        threshold=60.0,
        message="Prometheus metric test",
    )

    alert_engine.process_firing_alert(db_session, event)

    updated_sample = metrics_registry.alerts_total.get_sample(
        alert_type="WORKER_DOWN", severity="CRITICAL", status="FIRING"
    )
    assert updated_sample == initial_sample + 1.0
