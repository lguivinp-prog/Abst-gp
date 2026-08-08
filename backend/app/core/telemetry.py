"""
Módulo de Telemetría Externa & Trazabilidad Distribuida (Fase 7.1)
Provee exportación de métricas nativas en formato Prometheus y propagación de trazas W3C / OpenTelemetry.

Restricciones Arquitectónicas:
- PostgreSQL permanece como SSOT.
- NO usar tenant_id como label en métricas de Prometheus para evitar explosión de cardinalidad y fugas de privacidad.
- Recolección atómica thread-safe en memoria sin bloqueo del bucle asíncrono.
"""

import re
import time
import uuid
import secrets
import threading
from contextvars import ContextVar
from typing import Dict, Tuple, List, Optional, Any, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Contexto de Trazabilidad Distribuida (W3C TraceContext / OpenTelemetry)
# ---------------------------------------------------------------------------
current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="")
current_span_id: ContextVar[str] = ContextVar("current_span_id", default="")


def generate_trace_id() -> str:
    """Genera un trace_id hexadecimal de 32 caracteres (128 bits W3C compliant)."""
    return secrets.token_hex(16)


def generate_span_id() -> str:
    """Genera un span_id hexadecimal de 16 caracteres (64 bits W3C compliant)."""
    return secrets.token_hex(8)


def parse_traceparent(traceparent: Optional[str]) -> Tuple[str, str, str]:
    """
    Parsea una cabecera W3C traceparent (versión-trace_id-parent_id-trace_flags).
    Formato: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
    """
    if not traceparent:
        return generate_trace_id(), generate_span_id(), "01"

    parts = traceparent.strip().split("-")
    if len(parts) == 4 and len(parts[1]) == 32 and len(parts[2]) == 16:
        return parts[1], generate_span_id(), parts[3]

    return generate_trace_id(), generate_span_id(), "01"


def format_traceparent(trace_id: str, span_id: str, flags: str = "01") -> str:
    """Formatea la cabecera W3C traceparent."""
    return f"00-{trace_id}-{span_id}-{flags}"


# ---------------------------------------------------------------------------
# Primitivas de Métricas Prometheus Thread-Safe
# ---------------------------------------------------------------------------
class _Counter:
    """Contador monótono thread-safe con soporte de etiquetas."""

    def __init__(self, name: str, description: str, label_names: Tuple[str, ...]):
        self.name = name
        self.description = description
        self.label_names = label_names
        self._lock = threading.Lock()
        self._values: Dict[Tuple[str, ...], float] = {}

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        if amount < 0:
            raise ValueError("Los contadores solo pueden incrementarse.")
        key = tuple(str(labels.get(lbl, "")) for lbl in self.label_names)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def get_sample(self, **labels: str) -> float:
        key = tuple(str(labels.get(lbl, "")) for lbl in self.label_names)
        with self._lock:
            return self._values.get(key, 0.0)

    def collect(self) -> List[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} counter"
        ]
        with self._lock:
            if not self._values:
                # Si no hay muestras, emitir al menos un valor base si no hay labels requeridas
                if not self.label_names:
                    lines.append(f"{self.name} 0.0")
                return lines

            for key, val in sorted(self._values.items()):
                if self.label_names:
                    label_str = ",".join(f'{k}="{v}"' for k, v in zip(self.label_names, key))
                    lines.append(f"{self.name}{{{label_str}}} {val}")
                else:
                    lines.append(f"{self.name} {val}")
        return lines


class _Gauge:
    """Métrica de valor arbitrario thread-safe con soporte de etiquetas."""

    def __init__(self, name: str, description: str, label_names: Tuple[str, ...]):
        self.name = name
        self.description = description
        self.label_names = label_names
        self._lock = threading.Lock()
        self._values: Dict[Tuple[str, ...], float] = {}

    def set(self, value: float, **labels: str) -> None:
        key = tuple(str(labels.get(lbl, "")) for lbl in self.label_names)
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(str(labels.get(lbl, "")) for lbl in self.label_names)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(str(labels.get(lbl, "")) for lbl in self.label_names)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) - amount

    def get_sample(self, **labels: str) -> float:
        key = tuple(str(labels.get(lbl, "")) for lbl in self.label_names)
        with self._lock:
            return self._values.get(key, 0.0)

    def collect(self) -> List[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} gauge"
        ]
        with self._lock:
            if not self._values:
                if not self.label_names:
                    lines.append(f"{self.name} 0.0")
                return lines

            for key, val in sorted(self._values.items()):
                if self.label_names:
                    label_str = ",".join(f'{k}="{v}"' for k, v in zip(self.label_names, key))
                    lines.append(f"{self.name}{{{label_str}}} {val}")
                else:
                    lines.append(f"{self.name} {val}")
        return lines


class _Histogram:
    """Histograma thread-safe con distribución de cubos (_bucket), _sum y _count."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

    def __init__(self, name: str, description: str, label_names: Tuple[str, ...], buckets: Optional[Tuple[float, ...]] = None):
        self.name = name
        self.description = description
        self.label_names = label_names
        self.buckets = tuple(sorted(buckets or self.DEFAULT_BUCKETS))
        self._lock = threading.Lock()
        # key -> { "sum": float, "count": int, "buckets": { bucket: int } }
        self._data: Dict[Tuple[str, ...], Dict[str, Any]] = {}

    def observe(self, value: float, **labels: str) -> None:
        val = float(value)
        key = tuple(str(labels.get(lbl, "")) for lbl in self.label_names)
        with self._lock:
            if key not in self._data:
                self._data[key] = {
                    "sum": 0.0,
                    "count": 0,
                    "buckets": {b: 0 for b in self.buckets}
                }
            entry = self._data[key]
            entry["sum"] += val
            entry["count"] += 1
            for b in self.buckets:
                if val <= b:
                    entry["buckets"][b] += 1

    def get_count(self, **labels: str) -> int:
        key = tuple(str(labels.get(lbl, "")) for lbl in self.label_names)
        with self._lock:
            entry = self._data.get(key)
            return entry["count"] if entry else 0

    def collect(self) -> List[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} histogram"
        ]
        with self._lock:
            for key, entry in sorted(self._data.items()):
                base_labels = [f'{k}="{v}"' for k, v in zip(self.label_names, key)]
                
                # Buckets
                cum_count = 0
                for b in self.buckets:
                    cum_count = entry["buckets"][b]
                    b_label = f'le="{b}"'
                    lbls = ",".join(base_labels + [b_label]) if base_labels else b_label
                    lines.append(f"{self.name}_bucket{{{lbls}}} {cum_count}")

                # +Inf bucket
                inf_label = 'le="+Inf"'
                lbls_inf = ",".join(base_labels + [inf_label]) if base_labels else inf_label
                lines.append(f"{self.name}_bucket{{{lbls_inf}}} {entry['count']}")

                # Sum and Count
                lbls_base = "{" + ",".join(base_labels) + "}" if base_labels else ""
                lines.append(f"{self.name}_sum{lbls_base} {entry['sum']:.6f}")
                lines.append(f"{self.name}_count{lbls_base} {entry['count']}")
        return lines


# ---------------------------------------------------------------------------
# Registro Central de Métricas SRE Abst-gp V5.5 / Fase 7.1
# ---------------------------------------------------------------------------
class PrometheusRegistry:
    """Registro unificado para métricas de observabilidad externa."""

    def __init__(self):
        # 1. Total de trabajos procesados (Labels: job_type, status)
        self.jobs_total = _Counter(
            name="abst_jobs_total",
            description="Total acumulado de trabajos de procesamiento por tipo y estado.",
            label_names=("job_type", "status")
        )

        # 2. Duración de procesamiento de trabajos (Labels: job_type, status)
        self.job_duration_seconds = _Histogram(
            name="abst_job_duration_seconds",
            description="Distribución de duración en segundos de trabajos procesados.",
            label_names=("job_type", "status"),
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
        )

        # 3. Estado de workers en clúster (Labels: worker_type, status)
        self.worker_status = _Gauge(
            name="abst_worker_status",
            description="Cantidad de workers por tipo y estado operativo (BUSY, IDLE, UNRESPONSIVE).",
            label_names=("worker_type", "status")
        )

        # 4. Profundidad de colas de mensajes (Labels: queue_name)
        self.queue_depth = _Gauge(
            name="abst_queue_depth",
            description="Número de tareas pendientes encoladas por nombre de cola.",
            label_names=("queue_name",)
        )

        # 5. Duración y conteo de peticiones HTTP (Labels: method, endpoint, status_code)
        self.http_request_duration_seconds = _Histogram(
            name="abst_http_request_duration_seconds",
            description="Latencia de peticiones HTTP en segundos por método, endpoint y código de estado.",
            label_names=("method", "endpoint", "status_code"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
        )

        # 6. Alertas e incidentes SRE evaluados y emitidos (Labels: alert_type, severity, status)
        self.alerts_total = _Counter(
            name="abst_alerts_total",
            description="Total acumulado de eventos de alerta emitidos por tipo, severidad y estado.",
            label_names=("alert_type", "severity", "status")
        )

        # 7. Reclamos de capacidad (Fase 7.3) (Labels: result, reason)
        self.capacity_claims_total = _Counter(
            name="abst_capacity_claims_total",
            description="Total acumulado de intentos de reclamo de capacidad por resultado y causa.",
            label_names=("result", "reason")
        )

        # 8. Duración de evaluación del gobernador de capacidad (Fase 7.3)
        self.capacity_governor_duration_seconds = _Histogram(
            name="abst_capacity_governor_duration_seconds",
            description="Distribución de duración en segundos de evaluación del gobernador de capacidad.",
            label_names=(),
            buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
        )

        # 9. Total de trabajos retenidos en QUEUED por cuota o capacidad (Fase 7.3) (Labels: reason)
        self.jobs_retained_total = _Counter(
            name="abst_jobs_retained_total",
            description="Total acumulado de trabajos retenidos en QUEUED por motivo de capacidad.",
            label_names=("reason",)
        )

        # 10. Métricas del Connection Pool de base de datos (Fase 7.3)
        self.db_pool_timeout_total = _Counter(
            name="abst_db_pool_timeout_total",
            description="Total acumulado de eventos de timeout en adquisición del connection pool.",
            label_names=()
        )
        self.db_pool_checked_out = _Gauge(
            name="abst_db_pool_checked_out",
            description="Conexiones actualmente en uso (checked out) del pool de base de datos.",
            label_names=()
        )
        self.db_pool_overflow = _Gauge(
            name="abst_db_pool_overflow",
            description="Conexiones de desbordamiento (overflow) activas en el pool de base de datos.",
            label_names=()
        )

        # 11. Métricas de Disaster Recovery y Continuidad Operacional (Fase 7.4)
        self.dr_backup_total = _Counter(
            name="abst_dr_backup_total",
            description="Total acumulado de operaciones de backup por resultado (success, failure, rejected).",
            label_names=("result",)
        )
        self.dr_restore_total = _Counter(
            name="abst_dr_restore_total",
            description="Total acumulado de operaciones de restauración por resultado (success, failure, rejected).",
            label_names=("result",)
        )
        self.dr_restore_duration_seconds = _Histogram(
            name="abst_dr_restore_duration_seconds",
            description="Distribución de duración en segundos de procesos de restauración completa de desastre.",
            label_names=(),
            buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 900.0)
        )
        self.dr_reconciliation_total = _Counter(
            name="abst_dr_reconciliation_total",
            description="Total acumulado de reconciliaciones DR post-restore por resultado (success, failure, rejected).",
            label_names=("result",)
        )

    def generate_latest(self) -> str:
        """Genera la salida de texto en formato Prometheus OpenMetrics (text/plain)."""
        metrics = [
            self.jobs_total,
            self.job_duration_seconds,
            self.worker_status,
            self.queue_depth,
            self.http_request_duration_seconds,
            self.alerts_total,
            self.capacity_claims_total,
            self.capacity_governor_duration_seconds,
            self.jobs_retained_total,
            self.db_pool_timeout_total,
            self.db_pool_checked_out,
            self.db_pool_overflow,
            self.dr_backup_total,
            self.dr_restore_total,
            self.dr_restore_duration_seconds,
            self.dr_reconciliation_total,
        ]
        output_lines = []
        for m in metrics:
            output_lines.extend(m.collect())
        output_lines.append("")  # Línea en blanco final requerida por la especificación Prometheus
        return "\n".join(output_lines)


# Singleton del registro de telemetría
metrics_registry = PrometheusRegistry()


# ---------------------------------------------------------------------------
# Funciones Helper de Emisión de Métricas
# ---------------------------------------------------------------------------
def record_job_lifecycle(job_type: str, status: str, duration_seconds: Optional[float] = None) -> None:
    """Registra la finalización o transición de estado de un ProcessingJob."""
    safe_type = str(job_type or "UNKNOWN").upper()
    safe_status = str(status or "UNKNOWN").upper()
    metrics_registry.jobs_total.inc(job_type=safe_type, status=safe_status)
    if duration_seconds is not None and duration_seconds >= 0:
        metrics_registry.job_duration_seconds.observe(duration_seconds, job_type=safe_type, status=safe_status)


def record_capacity_claim(result: str, reason: str, duration_seconds: Optional[float] = None) -> None:
    """
    Registra un intento de reclamo de capacidad (Fase 7.3).
    Valores controlados de result: 'claimed', 'retained', 'failed'.
    Valores controlados de reason: 'tenant_limit', 'system_limit', 'no_candidate', 'lock_timeout', 'database_error', 'success'.
    """
    safe_result = str(result or "unknown").lower()
    safe_reason = str(reason or "unknown").lower()
    metrics_registry.capacity_claims_total.inc(result=safe_result, reason=safe_reason)
    if duration_seconds is not None and duration_seconds >= 0:
        metrics_registry.capacity_governor_duration_seconds.observe(duration_seconds)


def record_job_retained(reason: str) -> None:
    """Registra un job retenido en QUEUED por límite de cuota o capacidad global."""
    safe_reason = str(reason or "unknown").lower()
    metrics_registry.jobs_retained_total.inc(reason=safe_reason)


def record_db_pool_metrics(checked_out: int, overflow: int, timeout_increment: int = 0) -> None:
    """Actualiza las métricas instantáneas del pool de conexiones de SQLAlchemy."""
    metrics_registry.db_pool_checked_out.set(float(max(0, checked_out)))
    metrics_registry.db_pool_overflow.set(float(max(0, overflow)))
    if timeout_increment > 0:
        metrics_registry.db_pool_timeout_total.inc(amount=float(timeout_increment))


def record_worker_telemetry(worker_type: str, status: str, count: int = 1) -> None:
    """Registra el conteo actual de un tipo de worker en un estado determinado."""
    safe_type = str(worker_type or "general_worker").lower()
    safe_status = str(status or "UNKNOWN").upper()
    metrics_registry.worker_status.set(float(count), worker_type=safe_type, status=safe_status)


def record_queue_telemetry(queue_name: str, depth: int) -> None:
    """Registra la profundidad actual de una cola de procesamiento."""
    safe_queue = str(queue_name or "default")
    metrics_registry.queue_depth.set(float(max(0, depth)), queue_name=safe_queue)


def record_alert_event(alert_type: str, severity: str, status: str) -> None:
    """Registra la emisión de un evento de alerta en Prometheus (Labels: alert_type, severity, status)."""
    safe_type = str(alert_type or "UNKNOWN").upper()
    safe_sev = str(severity or "INFO").upper()
    safe_st = str(status or "FIRING").upper()
    metrics_registry.alerts_total.inc(alert_type=safe_type, severity=safe_sev, status=safe_st)


def record_dr_backup(result: str) -> None:
    """
    Registra el resultado de una operación de backup DR (Fase 7.4).
    Valores controlados de result: 'success', 'failure', 'rejected'.
    """
    safe_result = str(result or "unknown").lower()
    if safe_result not in ("success", "failure", "rejected"):
        safe_result = "failure"
    metrics_registry.dr_backup_total.inc(result=safe_result)


def record_dr_restore(result: str, duration_seconds: Optional[float] = None) -> None:
    """
    Registra el resultado y duración de una operación de restauración DR (Fase 7.4).
    Valores controlados de result: 'success', 'failure', 'rejected'.
    """
    safe_result = str(result or "unknown").lower()
    if safe_result not in ("success", "failure", "rejected"):
        safe_result = "failure"
    metrics_registry.dr_restore_total.inc(result=safe_result)
    if duration_seconds is not None and duration_seconds >= 0:
        metrics_registry.dr_restore_duration_seconds.observe(duration_seconds)


def record_dr_reconciliation(result: str) -> None:
    """
    Registra el resultado de una reconciliación de jobs post-restore DR (Fase 7.4).
    Valores controlados de result: 'success', 'failure', 'rejected'.
    """
    safe_result = str(result or "unknown").lower()
    if safe_result not in ("success", "failure", "rejected"):
        safe_result = "failure"
    metrics_registry.dr_reconciliation_total.inc(result=safe_result)



# ---------------------------------------------------------------------------
# Normalización de Rutas HTTP para Evitar Explosión de Cardinalidad
# ---------------------------------------------------------------------------
UUID_REGEX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
NUMERIC_REGEX = re.compile(r"^\d+$")


def normalize_endpoint_path(path: str) -> str:
    """
    Normaliza rutas dinámicas como /cases/123 o /cases/abc-uuid/quotations a /cases/{id}
    para garantizar baja cardinalidad en las etiquetas de Prometheus.
    """
    if not path or path == "/":
        return "/"

    segments = path.strip("/").split("/")
    normalized = []

    for seg in segments:
        if NUMERIC_REGEX.match(seg) or UUID_REGEX.match(seg) or (len(seg) > 20 and not seg.startswith("req_")):
            normalized.append("{id}")
        else:
            normalized.append(seg)

    return "/" + "/".join(normalized)


# ---------------------------------------------------------------------------
# ASGI Middleware para Telemetría y Trazabilidad Distribuida
# ---------------------------------------------------------------------------
class OpenTelemetryMiddleware(BaseHTTPMiddleware):
    """
    Middleware ASGI que instrumenta cada petición HTTP entrante:
    1. Extrae o genera trace_id y span_id compatibles con W3C.
    2. Almacena el contexto en ContextVar.
    3. Mide la latencia de la petición con time.perf_counter().
    4. Emite la métrica abst_http_request_duration_seconds.
    5. Inyecta x-trace-id y x-span-id en la respuesta.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        traceparent = request.headers.get("traceparent")
        trace_id, span_id, flags = parse_traceparent(traceparent)

        t_token = current_trace_id.set(trace_id)
        s_token = current_span_id.set(span_id)

        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start_time
            norm_path = normalize_endpoint_path(request.url.path)
            method = request.method.upper()

            # No registrar el endpoint de scraping /metrics para evitar bucles de ruido
            if norm_path != "/metrics":
                metrics_registry.http_request_duration_seconds.observe(
                    duration,
                    method=method,
                    endpoint=norm_path,
                    status_code=str(status_code)
                )

            current_trace_id.reset(t_token)
            current_span_id.reset(s_token)

        # Inyectar cabeceras de trazabilidad en la respuesta
        response.headers["x-trace-id"] = trace_id
        response.headers["x-span-id"] = span_id
        response.headers["traceparent"] = format_traceparent(trace_id, span_id, flags)
        return response
