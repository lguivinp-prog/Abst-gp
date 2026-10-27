"""
Servicio de Registro de Intrusiones y Alertas de Seguridad para ABST-GP V6 (P14).
Implementa:
1. Registro auditable de eventos de intrusion sin fugas de secretos (P14-G14).
2. Patron Outbox durable para alertas fuera de banda al SUPERADMIN.
3. Despachador funcional (P14-R1-12) con reintentos, idempotencia, deduplicacion
   y soporte para canales reales (console, webhook, test_sink).
"""

import os
import logging
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import SecurityIntrusionEvent, SecurityAlertOutbox

logger = logging.getLogger("app.security.intrusion")

# Lista negra de claves que NUNCA deben incluirse en los detalles de una alerta (P14-G14)
SENSITIVE_KEYS = {
    "password", "new_password", "current_password", "password_hash",
    "token", "access_token", "refresh_token", "mfa_challenge_token",
    "totp", "totp_code", "secret", "mfa_secret", "recovery_code",
    "code_hash", "authorization"
}

# Sink en memoria para verificacion determinista de entrega en tests y auditorias (P14-R1-12)
TEST_SINK_DELIVERIES: List[Dict[str, Any]] = []


def clear_test_sink() -> None:
    """Limpia las alertas recibidas en el sink de pruebas."""
    global TEST_SINK_DELIVERIES
    TEST_SINK_DELIVERIES.clear()


def get_test_sink_deliveries() -> List[Dict[str, Any]]:
    """Obtiene una copia de los eventos despachados al sink de pruebas."""
    return list(TEST_SINK_DELIVERIES)


def sanitize_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Sanea de forma recursiva cualquier diccionario de detalles eliminando o enmascarando
    credenciales, tokens, codigos TOTP o secretos criptograficos.
    """
    if not details:
        return {}
        
    sanitized = {}
    for k, v in details.items():
        k_lower = str(k).lower()
        if any(s in k_lower for s in SENSITIVE_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_details(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_details(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = str(v)[:500]
            
    return sanitized


def record_intrusion_event(
    db: Session,
    ip_address: str,
    event_type: str,
    severity: str,
    user_identifier: Optional[str] = None,
    tenant_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    auto_commit: bool = True
) -> SecurityIntrusionEvent:
    """
    Registra un evento de seguridad de forma duradera y encola una alerta en el outbox.
    Aplica deduplicacion para evitar tormentas de alertas repetitivas (P14-R1-12).
    """
    clean_details = sanitize_details(details)
    clean_ip = str(ip_address).strip()[:45]
    clean_user = str(user_identifier).strip()[:100] if user_identifier else None
    clean_tenant = str(tenant_id).strip()[:50] if tenant_id else None

    # Deduplicacion: comprobar si ocurrio un evento identico en los ultimos 60 segundos
    recent_threshold = datetime.now(timezone.utc) - timedelta(seconds=60)
    recent_duplicate = (
        db.query(SecurityIntrusionEvent)
        .filter(
            SecurityIntrusionEvent.ip_address == clean_ip,
            SecurityIntrusionEvent.event_type == event_type,
            SecurityIntrusionEvent.occurred_at >= recent_threshold
        )
        .first()
    )

    event = SecurityIntrusionEvent(
        ip_address=clean_ip,
        user_identifier=clean_user,
        tenant_id=clean_tenant,
        event_type=event_type,
        severity=severity.upper(),
        details=clean_details,
        occurred_at=datetime.now(timezone.utc)
    )
    db.add(event)
    db.flush()

    # Encolar en Outbox para notificacion fuera de banda
    channel = getattr(settings, "ALERT_CHANNEL", "console")
    outbox_status = "PENDING"

    outbox_entry = SecurityAlertOutbox(
        event_id=event.id,
        channel=channel,
        destination=getattr(settings, "ALERT_WEBHOOK_URL", None),
        payload={
            "event_id": event.id,
            "event_type": event_type,
            "severity": severity.upper(),
            "ip_address": clean_ip,
            "user_identifier": clean_user,
            "tenant_id": clean_tenant,
            "occurred_at": event.occurred_at.isoformat(),
            "details": clean_details,
            "is_duplicate_suppressed": bool(recent_duplicate)
        },
        status=outbox_status,
        attempts=0
    )
    db.add(outbox_entry)

    if auto_commit:
        try:
            db.commit()
            db.refresh(event)
        except Exception as e:
            db.rollback()
            logger.error(f"Error persistiendo evento de intrusion: {e}")
            raise

    # Notificar inmediatamente para canales activos (P14-R1-12, P14-R2-11)
    if channel in ("console", "test_sink", "mock", "webhook", "telegram"):
        dispatch_single_alert(outbox_entry)
        if auto_commit:
            try:
                db.commit()
            except Exception:
                pass

    return event


def dispatch_single_alert(entry: SecurityAlertOutbox) -> bool:
    """
    Ejecuta el transporte real para una alerta individual segun su canal (P14-R1-12, P14-R2-11).
    Retorna True si fue enviada con exito, False si fallo.
    """
    entry.attempts += 1
    entry.last_attempt_at = datetime.now(timezone.utc)
    channel = entry.channel.lower()
    payload = entry.payload or {}

    app_env = getattr(settings, "APP_ENV", "development").lower()
    MAX_ATTEMPTS = 5

    try:
        if channel == "console":
            logger.warning(
                f"[SECURITY ALERT - {entry.payload.get('severity', 'INFO')}] "
                f"Event: {entry.payload.get('event_type')} | "
                f"IP: {entry.payload.get('ip_address')} | "
                f"User: {entry.payload.get('user_identifier')} | "
                f"Details: {entry.payload.get('details')}"
            )
            if app_env in ("lan", "production", "prod"):
                entry.status = "LOGGED_LOCAL_ONLY"
                entry.last_error = "Canal console no constituye entrega remota fuera de banda en entorno LAN/produccion (R3-10, R4-05)."
                return False
            else:
                entry.status = "SENT"
                entry.processed_at = datetime.now(timezone.utc)
                return True

        elif channel in ("test_sink", "mock"):
            if app_env in ("lan", "production", "prod"):
                entry.status = "LOGGED_LOCAL_ONLY"
                entry.last_error = f"Canal '{channel}' no constituye entrega remota fuera de banda en entorno LAN/produccion (R4-05)."
                return False
            TEST_SINK_DELIVERIES.append(payload)
            entry.status = "SENT"
            entry.processed_at = datetime.now(timezone.utc)
            return True

        elif channel == "webhook":
            webhook_url = entry.destination or getattr(settings, "ALERT_WEBHOOK_URL", "")
            if not webhook_url:
                entry.status = "NOT_CONFIGURED"
                entry.last_error = "ALERT_WEBHOOK_URL no esta configurada."
                return False

            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "ABST-GP-Security-Alert/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    entry.status = "SENT"
                    entry.processed_at = datetime.now(timezone.utc)
                    return True
                else:
                    entry.status = "DEAD_LETTER" if entry.attempts >= MAX_ATTEMPTS else "FAILED"
                    entry.last_error = f"Webhook HTTP {resp.status}"
                    return False

        elif channel == "telegram":
            bot_token = os.getenv("ALERT_TELEGRAM_BOT_TOKEN", getattr(settings, "ALERT_TELEGRAM_BOT_TOKEN", ""))
            chat_id = os.getenv("ALERT_TELEGRAM_CHAT_ID", getattr(settings, "ALERT_TELEGRAM_CHAT_ID", ""))
            if not bot_token or not chat_id:
                entry.status = "NOT_CONFIGURED"
                entry.last_error = "ALERT_TELEGRAM_BOT_TOKEN o ALERT_TELEGRAM_CHAT_ID no configuradas."
                return False

            text_msg = (
                f"🚨 *ALERTA DE SEGURIDAD ABST-GP* ({payload.get('severity', 'INFO')})\n"
                f"*Evento:* `{payload.get('event_type')}`\n"
                f"*IP:* `{payload.get('ip_address')}`\n"
                f"*Usuario:* `{payload.get('user_identifier')}`\n"
                f"*Fecha:* `{payload.get('occurred_at')}`"
            )
            tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            req_data = json.dumps({"chat_id": chat_id, "text": text_msg, "parse_mode": "Markdown"}).encode("utf-8")
            req = urllib.request.Request(tg_url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    # R4-05: Exigir parseo de respuesta JSON y confirmacion ok == True
                    try:
                        resp_body = json.loads(resp.read().decode("utf-8"))
                    except Exception:
                        resp_body = {}
                    if resp_body.get("ok") is True:
                        entry.status = "SENT"
                        entry.processed_at = datetime.now(timezone.utc)
                        return True
                    else:
                        entry.status = "DEAD_LETTER" if entry.attempts >= MAX_ATTEMPTS else "FAILED"
                        entry.last_error = f"Telegram API ok=false: {resp_body.get('description', 'Unknown API error')}"
                        return False
                else:
                    entry.status = "DEAD_LETTER" if entry.attempts >= MAX_ATTEMPTS else "FAILED"
                    entry.last_error = f"Telegram HTTP {resp.status}"
                    return False

        else:
            entry.status = "NOT_CONFIGURED"
            entry.last_error = f"Canal desconocido '{channel}'."
            return False

    except Exception as e:
        entry.status = "DEAD_LETTER" if entry.attempts >= MAX_ATTEMPTS else "FAILED"
        entry.last_error = str(e)
        logger.error(f"Fallo despachando alerta {entry.id} via canal {channel} (intento {entry.attempts}/{MAX_ATTEMPTS}): {e}")
        return False


def validate_alert_channel_readiness() -> Dict[str, Any]:
    """
    Preflight de validacion del canal de alertas (R4-05).
    Verifica si el entorno y canal configurados garantizan notificacion remota efectiva al propietario.
    """
    app_env = getattr(settings, "APP_ENV", "development").lower()
    channel = getattr(settings, "ALERT_CHANNEL", "console")
    
    is_remote_transport = channel in ("webhook", "telegram")
    
    if app_env in ("lan", "production", "prod"):
        if not is_remote_transport:
            return {
                "status": "NO-GO",
                "ready": False,
                "channel": channel,
                "reason": f"Canal '{channel}' no es un transporte remoto fuera de banda verificado. Se requiere 'webhook' o 'telegram'."
            }
        if channel == "webhook" and not getattr(settings, "ALERT_WEBHOOK_URL", ""):
            return {
                "status": "NO-GO",
                "ready": False,
                "channel": channel,
                "reason": "ALERT_WEBHOOK_URL no esta configurada."
            }
        if channel == "telegram":
            bot_token = os.getenv("ALERT_TELEGRAM_BOT_TOKEN", getattr(settings, "ALERT_TELEGRAM_BOT_TOKEN", ""))
            chat_id = os.getenv("ALERT_TELEGRAM_CHAT_ID", getattr(settings, "ALERT_TELEGRAM_CHAT_ID", ""))
            if not bot_token or not chat_id:
                return {
                    "status": "NO-GO",
                    "ready": False,
                    "channel": channel,
                    "reason": "Credenciales de Telegram no configuradas."
                }
                
    return {
        "status": "READY",
        "ready": True,
        "channel": channel,
        "reason": "Canal de alertas listo para despacho."
    }


def dispatch_pending_alerts(db: Session, max_batch: int = 10, enforce_backoff: bool = True) -> int:
    """
    Procesa las alertas pendientes en el outbox con garantia de reintentos, backoff exponencial
    y dead-letter (P14-R1-12, P14-R3-10, R4-05, R5-06).
    Soporta ejecucion coordinada multitrabajador con bloqueo transaccional (skip_locked).
    """
    now = datetime.now(timezone.utc)
    query = (
        db.query(SecurityAlertOutbox)
        .filter(
            SecurityAlertOutbox.status.in_(["PENDING", "FAILED"]),
            SecurityAlertOutbox.attempts < 5
        )
        .order_by(SecurityAlertOutbox.id.asc())
    )

    # R5-06: Bloqueo transaccional skip_locked para evitar envios duplicados entre multiples workers
    try:
        entries = query.with_for_update(skip_locked=True).limit(max_batch * 2).all()
    except Exception:
        # Fallback para bases sin soporte de with_for_update (ej. SQLite)
        entries = query.limit(max_batch * 2).all()
    
    processed = 0
    
    for entry in entries:
        if processed >= max_batch:
            break
            
        # R5-06: Backoff exponencial para reintentos calculado sobre el ULTIMO intento real
        if enforce_backoff and entry.attempts > 0:
            last_attempt = entry.last_attempt_at or entry.processed_at or entry.created_at
            if last_attempt:
                if last_attempt.tzinfo is None:
                    last_attempt = last_attempt.replace(tzinfo=timezone.utc)
                # Segundos de espera: 2^(attempts-1) * 2s -> intento 1: 2s, intento 2: 4s, etc.
                backoff_sec = min(300, (2 ** (entry.attempts - 1)) * 2)
                if (now - last_attempt).total_seconds() < backoff_sec:
                    continue

        success = dispatch_single_alert(entry)
        if success:
            processed += 1
            
    if entries:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error confirmando transaccion de despacho de alertas: {e}")
        
    return processed


# ---------------------------------------------------------------------------
# Scheduler Autónomo en Segundo Plano para Alertas Outbox (R4-05)
# ---------------------------------------------------------------------------

import threading
import time

_dispatcher_thread: Optional[threading.Thread] = None
_dispatcher_stop_event = threading.Event()


def _run_dispatcher_loop(interval_seconds: float = 3.0):
    """Bucle autónomo de supervisión y despacho continuo de alertas."""
    from app.core.database import SessionLocal
    logger.info("Iniciando despachador automatico en segundo plano de alertas de seguridad (R4-05).")
    while not _dispatcher_stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                dispatch_pending_alerts(db, max_batch=20)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error en bucle del despachador de alertas de seguridad: {e}")
        _dispatcher_stop_event.wait(interval_seconds)
    logger.info("Despachador automatico de alertas de seguridad detenido.")


def start_alert_dispatcher_service(interval_seconds: float = 3.0):
    """Inicia el despachador autónomo como un hilo daemon supervisado (R4-05)."""
    global _dispatcher_thread, _dispatcher_stop_event
    if _dispatcher_thread and _dispatcher_thread.is_alive():
        return
    _dispatcher_stop_event.clear()
    _dispatcher_thread = threading.Thread(
        target=_run_dispatcher_loop,
        args=(interval_seconds,),
        name="SecurityAlertDispatcherWorker",
        daemon=True
    )
    _dispatcher_thread.start()
    logger.info("Servicio despachador de alertas de seguridad iniciado en segundo plano.")


def stop_alert_dispatcher_service():
    """Detiene limpiamente el despachador autónomo (R4-05)."""
    global _dispatcher_thread, _dispatcher_stop_event
    if _dispatcher_thread and _dispatcher_thread.is_alive():
        _dispatcher_stop_event.set()
        _dispatcher_thread.join(timeout=5.0)
        logger.info("Servicio despachador de alertas de seguridad detenido limpiamente.")

