"""
ABAST GP V6 — P20 Alert Dispatcher
Gestor autónomo de alertas operativas con deduplicación, supresión de flapping,
enmascaramiento estricto de secretos y soporte multicanal (Consola, Archivo, Webhook, Telegram).
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("abst_gp.p20.alerts")

# Palabras clave y patrones sensibles para saneamiento estricto
SENSITIVE_KEYS = {"password", "secret", "token", "key", "dsn", "authorization", "mfa_secret"}

def sanitize_payload(obj: Any) -> Any:
    """Enmascara recursivamente cualquier dato sensible o credencial."""
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = sanitize_payload(v)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    elif isinstance(obj, str):
        # Sanitizar URLs con credenciales: user:pass@host
        import re
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***REDACTED***@", obj)
    return obj


class AlertDispatcher:
    def __init__(
        self,
        state_file: Optional[Path] = None,
        history_file: Optional[Path] = None,
        cooldown_seconds: int = 3600
    ):
        base_dir = Path(__file__).resolve().parent
        self.state_file = state_file or (base_dir / "alert_state.json")
        self.history_file = history_file or (base_dir / "alerts_history.jsonl")
        self.cooldown_seconds = cooldown_seconds
        self.state: Dict[str, Any] = self._load_state()

        # Configuración de canales externos desde variables de entorno
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL", "")
        self.telegram_bot_token = os.getenv("ALERT_TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("ALERT_TELEGRAM_CHAT_ID", "")
        self.alert_channel = os.getenv("ALERT_CHANNEL", "console").lower()

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_state(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Error persistiendo estado de alertas: {e}")

    def dispatch(
        self,
        component: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Emite una alerta si el componente no se encuentra en periodo de enfriamiento (cooldown)
        o si cambio su severidad. Retorna True si la alerta fue efectivamente despachada.
        """
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        component_key = component.lower()
        severity = severity.upper()

        current_state = self.state.get(component_key, {})
        last_severity = current_state.get("severity")
        last_dispatched = current_state.get("last_dispatched", 0)

        # Regla de deduplicacion:
        # Si la severidad no ha cambiado y ha pasado menos del tiempo de cooldown, suprimir duplicado
        if last_severity == severity and (now - last_dispatched) < self.cooldown_seconds:
            logger.debug(f"Alerta suprimida por deduplicacion: {component} [{severity}] (Cooldown activo)")
            return False

        # Registrar nuevo estado
        self.state[component_key] = {
            "severity": severity,
            "message": message,
            "last_dispatched": now,
            "last_dispatched_iso": now_iso
        }
        self._save_state()

        # Construir registro saneado
        safe_details = sanitize_payload(details or {})
        alert_record = {
            "timestamp": now_iso,
            "component": component,
            "severity": severity,
            "message": message,
            "details": safe_details
        }

        # 1. Registro local y en discos independientes (append-only)
        primary_alert_log = Path(os.getenv("ALERT_LOG_PRIMARY", r"D:\BACKUPS_PROYECTOS\ABAST_GP_P19_MIGRATION\logs\alerts.jsonl"))
        secondary_alert_log = Path(os.getenv("ALERT_LOG_SECONDARY", r"C:\Users\PC\Documents\AbastLG\ABAST_GP_P19_SECONDARY_CUSTODY\logs\alerts.jsonl"))
        log_paths = [self.history_file, primary_alert_log, secondary_alert_log]
        for lp in log_paths:
            try:
                lp.parent.mkdir(parents=True, exist_ok=True)
                with open(lp, "a", encoding="utf-8") as f:
                    f.write(json.dumps(alert_record) + "\n")
            except Exception as e:
                logger.error(f"Error escribiendo log de alertas en {lp}: {e}")

        # 2. Consola estandar
        print(f"[{now_iso}] [ALERTA OPERATIVA] [{severity}] {component}: {message}")

        # 3. Canales remotos opcionales si estan configurados
        if self.webhook_url and self.alert_channel in ("webhook", "all"):
            self._send_webhook(alert_record)

        if self.telegram_bot_token and self.telegram_chat_id and self.alert_channel in ("telegram", "all"):
            self._send_telegram(alert_record)

        return True

    def resolve(self, component: str, message: str = "Servicio recuperado y operativo.") -> bool:
        """Emite aviso de recuperacion si el servicio estaba previamente degradado o caido."""
        component_key = component.lower()
        if component_key in self.state and self.state[component_key].get("severity") in ("CRITICAL", "ERROR", "WARNING", "DEGRADED", "DOWN"):
            now_iso = datetime.now(timezone.utc).isoformat()
            self.state[component_key] = {
                "severity": "HEALTHY",
                "message": message,
                "last_dispatched": time.time(),
                "last_dispatched_iso": now_iso
            }
            self._save_state()

            alert_record = {
                "timestamp": now_iso,
                "component": component,
                "severity": "RECOVERY",
                "message": message,
                "details": {"previous_state": "RESOLVED"}
            }

            primary_alert_log = Path(os.getenv("ALERT_LOG_PRIMARY", r"D:\BACKUPS_PROYECTOS\ABAST_GP_P19_MIGRATION\logs\alerts.jsonl"))
            secondary_alert_log = Path(os.getenv("ALERT_LOG_SECONDARY", r"C:\Users\PC\Documents\AbastLG\ABAST_GP_P19_SECONDARY_CUSTODY\logs\alerts.jsonl"))
            log_paths = [self.history_file, primary_alert_log, secondary_alert_log]
            for lp in log_paths:
                try:
                    lp.parent.mkdir(parents=True, exist_ok=True)
                    with open(lp, "a", encoding="utf-8") as f:
                        f.write(json.dumps(alert_record) + "\n")
                except Exception:
                    pass

            print(f"[{now_iso}] [RECUPERACION OPERATIVA] [HEALTHY] {component}: {message}")
            return True
        return False

    def _send_webhook(self, record: Dict[str, Any]) -> None:
        try:
            import urllib.request
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(record).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status < 300:
                    logger.info("Alerta despachada a webhook exitosamente.")
        except Exception as e:
            logger.warning(f"No se pudo despachar alerta a webhook: {e}")

    def _send_telegram(self, record: Dict[str, Any]) -> None:
        try:
            import urllib.request
            import urllib.parse
            text_msg = (
                f"🚨 *ABAST GP V6 — ALERTA OPERATIVA*\n"
                f"*Componente:* `{record['component']}`\n"
                f"*Severidad:* `{record['severity']}`\n"
                f"*Hora:* `{record['timestamp']}`\n"
                f"*Mensaje:* {record['message']}"
            )
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": self.telegram_chat_id,
                "text": text_msg,
                "parse_mode": "Markdown"
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status < 300:
                    logger.info("Alerta despachada a Telegram exitosamente.")
        except Exception as e:
            logger.warning(f"No se pudo despachar alerta a Telegram: {e}")
