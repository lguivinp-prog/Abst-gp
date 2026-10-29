"""
ABAST GP V6 — P20 Real Health Monitor
Supervisión autónoma y comprobaciones reales de infraestructura:
PostgreSQL, Redis, Workers RQ, API, Caddy TLS, Volúmenes y Contenedores.
Categoriza cada subsistema en HEALTHY, DEGRADED, DOWN o UNKNOWN sin divulgar secretos.
"""

import os
import sys
import json
import time
import socket
import ssl
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Asegurar encoding UTF-8 en Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Importar despachador de alertas
try:
    from monitoring.p20_alert_dispatcher import AlertDispatcher
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from p20_alert_dispatcher import AlertDispatcher

PILOT_CONTAINERS = [
    "abst_lan_api",
    "abst_lan_db",
    "abst_lan_redis",
    "abst_lan_proxy",
    "abst_lan_web",
    "abst_lan_worker",
    "abst_lan_worker_ocr"
]

EXPECTED_IP = os.getenv("PILOT_EXPECTED_IP", "192.168.100.7")
HTTPS_BASE_URL = os.getenv("PILOT_HTTPS_URL", f"https://{EXPECTED_IP}")
COMPOSE_PROJECT = os.getenv("PILOT_COMPOSE_PROJECT", "abst_p17_pilot")


class RealHealthMonitor:
    def __init__(self, alert_dispatcher: AlertDispatcher = None):
        self.alert_dispatcher = alert_dispatcher or AlertDispatcher()

    def check_postgresql(self) -> Dict[str, Any]:
        """Comprueba conectividad real a PostgreSQL, SELECT 1, latencia y estado de cuarentena."""
        t0 = time.time()
        script = (
            "import time, json\n"
            "from sqlalchemy import create_engine, text\n"
            "from app.core.config import settings\n"
            "t0 = time.time()\n"
            "engine = create_engine(settings.DATABASE_URL)\n"
            "with engine.connect() as conn:\n"
            "    r1 = conn.execute(text('SELECT 1')).scalar()\n"
            "    act = conn.execute(text(\"SELECT count(*) FROM pg_stat_activity WHERE datname = 'abst_gp_pilot'\")).scalar()\n"
            "    quar = conn.execute(text(\"SELECT to_regclass('public._dr_restoration_quarantine') IS NOT NULL\")).scalar()\n"
            "latency = round((time.time() - t0) * 1000, 2)\n"
            "print(json.dumps({'select_1': r1 == 1, 'connections': act, 'quarantine': bool(quar), 'latency_ms': latency}))\n"
        )
        cmd = [
            "docker", "compose", "--env-file", ".env.lan", "-f", "docker-compose.lan.yml",
            "-p", "abst_p17_pilot", "exec", "-T", "api", "python", "-c", script
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                data = json.loads(res.stdout.strip().split("\n")[-1])
                latency = data.get("latency_ms", round((time.time() - t0) * 1000, 2))
                quarantine = data.get("quarantine", False)

                if quarantine:
                    status = "DOWN"
                    msg = "Base de datos en CUARENTENA por fallo previo (_dr_restoration_quarantine detectada)."
                elif latency > 1500:
                    status = "DEGRADED"
                    msg = f"PostgreSQL responde con alta latencia ({latency}ms)."
                else:
                    status = "HEALTHY"
                    msg = f"SELECT 1 exitoso ({latency}ms, {data.get('connections')} conexiones activas, cuarentena limpia)."

                return {
                    "status": status,
                    "latency_ms": latency,
                    "details": {
                        "active_connections": data.get("connections"),
                        "quarantine_active": quarantine,
                        "query_verified": data.get("select_1")
                    },
                    "message": msg
                }
            else:
                return {
                    "status": "DOWN",
                    "latency_ms": round((time.time() - t0) * 1000, 2),
                    "details": {"error": "Error ejecutando consulta en PostgreSQL"},
                    "message": f"Fallo al conectar con PostgreSQL: {res.stderr[:200]}"
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "DOWN",
                "latency_ms": 10000,
                "details": {"error": "Timeout agotado (10s)"},
                "message": "Timeout agotado esperando respuesta de PostgreSQL."
            }
        except Exception as e:
            return {
                "status": "UNKNOWN",
                "latency_ms": 0,
                "details": {"error": str(e)},
                "message": f"Excepción durante comprobación PostgreSQL: {e}"
            }

    def check_redis(self) -> Dict[str, Any]:
        """Comprueba PING autenticado a Redis, latencia y telemetria de memoria."""
        t0 = time.time()
        script = (
            "import time, json\n"
            "from redis import Redis\n"
            "from app.core.config import settings\n"
            "t0 = time.time()\n"
            "r = Redis.from_url(settings.REDIS_URL)\n"
            "ping_ok = r.ping()\n"
            "info = r.info()\n"
            "latency = round((time.time() - t0) * 1000, 2)\n"
            "print(json.dumps({'ping': ping_ok, 'latency_ms': latency, 'used_memory_human': info.get('used_memory_human'), 'clients': info.get('connected_clients'), 'uptime_seconds': info.get('uptime_in_seconds')}))\n"
        )
        cmd = [
            "docker", "compose", "--env-file", ".env.lan", "-f", "docker-compose.lan.yml",
            "-p", "abst_p17_pilot", "exec", "-T", "api", "python", "-c", script
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                data = json.loads(res.stdout.strip().split("\n")[-1])
                latency = data.get("latency_ms", round((time.time() - t0) * 1000, 2))
                ping_ok = data.get("ping", False)

                if ping_ok:
                    status = "HEALTHY" if latency < 500 else "DEGRADED"
                    msg = f"PING exitoso ({latency}ms, memoria: {data.get('used_memory_human')}, clientes: {data.get('clients')})."
                else:
                    status = "DOWN"
                    msg = "Redis no respondio satisfactoriamente al comando PING."

                return {
                    "status": status,
                    "latency_ms": latency,
                    "details": {
                        "used_memory": data.get("used_memory_human"),
                        "connected_clients": data.get("clients"),
                        "uptime_seconds": data.get("uptime_seconds")
                    },
                    "message": msg
                }
            else:
                return {
                    "status": "DOWN",
                    "latency_ms": round((time.time() - t0) * 1000, 2),
                    "details": {"error": res.stderr[:200]},
                    "message": "Fallo de conexión o autenticación contra Redis."
                }
        except Exception as e:
            return {
                "status": "UNKNOWN",
                "latency_ms": 0,
                "details": {"error": str(e)},
                "message": f"Excepción durante comprobación Redis: {e}"
            }

    def check_rq_workers(self) -> Dict[str, Any]:
        """Comprueba el registro efectivo de workers RQ en Redis, sus colas y la frescura de su heartbeat."""
        script = (
            "import json, time\n"
            "from datetime import datetime, timezone\n"
            "from redis import Redis\n"
            "from app.core.config import settings\n"
            "from rq import Worker\n"
            "r = Redis.from_url(settings.REDIS_URL)\n"
            "workers = Worker.all(connection=r)\n"
            "now = datetime.now(timezone.utc)\n"
            "queues = ['default', 'ocr_tasks']\n"
            "covered = [q for q in queues if r.scard(f'rq:workers:{q}') > 0]\n"
            "result = {'workers': [], 'queues_covered': covered}\n"
            "for w in workers:\n"
            "    hb_age = round((now - w.last_heartbeat).total_seconds(), 1) if w.last_heartbeat else 9999\n"
            "    result['workers'].append({'name': w.name, 'state': w.get_state(), 'heartbeat_age_s': hb_age})\n"
            "print(json.dumps(result))\n"
        )
        cmd = [
            "docker", "compose", "--env-file", ".env.lan", "-f", "docker-compose.lan.yml",
            "-p", "abst_p17_pilot", "exec", "-T", "api", "python", "-c", script
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                data = json.loads(res.stdout.strip().split("\n")[-1])
                workers_data = data.get("workers", [])
                total_workers = len(workers_data)
                queues_covered = set(data.get("queues_covered", []))
                stale_workers = 0

                for w in workers_data:
                    # En RQ, el TTL/frecuencia de heartbeat por defecto es 420 segundos (7 min)
                    if w.get("heartbeat_age_s", 999) > 420:
                        stale_workers += 1

                expected_queues = {"default", "ocr_tasks"}
                missing_queues = expected_queues - queues_covered

                if total_workers >= 2 and not missing_queues and stale_workers == 0:
                    status = "HEALTHY"
                    msg = f"{total_workers} workers activos y operando en colas {sorted(list(queues_covered))} (heartbeat fresco)."
                elif total_workers > 0 and not missing_queues:
                    status = "DEGRADED"
                    msg = f"Workers activos ({total_workers}) pero detectados heartbeats demorados ({stale_workers} lentos)."
                elif total_workers > 0 and missing_queues:
                    status = "DEGRADED"
                    msg = f"Workers presentes pero falta cobertura en cola(s): {missing_queues}."
                else:
                    status = "DOWN"
                    msg = "No se detectaron workers RQ activos registrados en Redis."

                return {
                    "status": status,
                    "total_workers": total_workers,
                    "queues_covered": list(queues_covered),
                    "stale_workers": stale_workers,
                    "details": workers_data,
                    "message": msg
                }
            else:
                return {
                    "status": "DOWN",
                    "total_workers": 0,
                    "details": {"error": res.stderr[:200]},
                    "message": "Fallo al consultar workers RQ en Redis."
                }
        except Exception as e:
            return {
                "status": "UNKNOWN",
                "total_workers": 0,
                "details": {"error": str(e)},
                "message": f"Excepción durante comprobación de workers RQ: {e}"
            }

    def check_api_https(self) -> Dict[str, Any]:
        """Comprueba operacion real del endpoint HTTPS /api/v6/health."""
        t0 = time.time()
        import urllib.request
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        url = f"{HTTPS_BASE_URL}/api/v6/health"
        req = urllib.request.Request(url, headers={"User-Agent": "ABAST-P20-HealthMonitor"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                latency = round((time.time() - t0) * 1000, 2)
                body = json.loads(resp.read().decode("utf-8"))
                if resp.status == 200 and body.get("api") == "ok":
                    status = "HEALTHY" if latency < 1000 else "DEGRADED"
                    msg = f"HTTP 200 OK en {latency}ms ({url})."
                else:
                    status = "DEGRADED"
                    msg = f"Respuesta inesperada: HTTP {resp.status}, payload={body}"
                return {
                    "status": status,
                    "status_code": resp.status,
                    "latency_ms": latency,
                    "payload": body,
                    "message": msg
                }
        except urllib.error.HTTPError as e:
            return {
                "status": "DOWN",
                "status_code": e.code,
                "latency_ms": round((time.time() - t0) * 1000, 2),
                "message": f"Error HTTP {e.code} desde {url}"
            }
        except Exception as e:
            return {
                "status": "DOWN",
                "status_code": 0,
                "latency_ms": round((time.time() - t0) * 1000, 2),
                "message": f"Fallo al contactar API HTTPS: {e}"
            }

    def check_caddy_tls(self) -> Dict[str, Any]:
        """Inspecciona handshake TLS en puerto 443, emisor, validez y fecha de vencimiento."""
        t0 = time.time()
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with socket.create_connection((EXPECTED_IP, 443), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=EXPECTED_IP) as ssock:
                    cert_der = ssock.getpeercert(binary_form=True)
                    tls_version = ssock.version()
                    cipher = ssock.cipher()
                    latency = round((time.time() - t0) * 1000, 2)

            from cryptography import x509
            cert = x509.load_der_x509_certificate(cert_der)
            now = datetime.now(timezone.utc)
            not_after = cert.not_valid_after_utc
            time_remaining = not_after - now
            hours_remaining = round(time_remaining.total_seconds() / 3600, 1)

            # Caddy gestiona certificados locales de 12 horas y renueva a las 8 horas.
            # Solo degradar si quedan menos de 1 hora y no ha rotado.
            if hours_remaining <= 0:
                status = "DOWN"
                msg = f"Certificado TLS EXPIRADO hace {abs(hours_remaining)} horas."
            elif hours_remaining < 1.0:
                status = "DEGRADED"
                msg = f"Certificado TLS próximo a vencer en {hours_remaining} horas."
            else:
                status = "HEALTHY"
                msg = f"TLS activo ({tls_version}, {cipher[0]}), emisor '{cert.issuer.rfc4514_string()}', vence en {hours_remaining}h."

            return {
                "status": status,
                "latency_ms": latency,
                "tls_version": tls_version,
                "cipher": cipher[0],
                "issuer": cert.issuer.rfc4514_string(),
                "expires_at": not_after.isoformat(),
                "hours_remaining": hours_remaining,
                "message": msg
            }
        except Exception as e:
            return {
                "status": "DOWN",
                "latency_ms": round((time.time() - t0) * 1000, 2),
                "message": f"Fallo en conexión o handshake TLS en puerto 443: {e}"
            }

    def check_volumes_and_storage(self) -> Dict[str, Any]:
        """Comprueba espacio disponible en C: y D:, y verifica capacidad de escritura con canario temporal."""
        disk_c = os.getenv("MONITOR_DISK_PRIMARY", "C:\\" if os.name == "nt" else "/")
        disk_d = os.getenv("MONITOR_DISK_SECONDARY", "D:\\" if os.name == "nt" else "/")
        c_usage = shutil.disk_usage(disk_c)
        d_usage = shutil.disk_usage(disk_d) if (os.name == "nt" and os.path.exists(disk_d)) else c_usage

        c_free_pct = round((c_usage.free / c_usage.total) * 100, 1)
        d_free_pct = round((d_usage.free / d_usage.total) * 100, 1)

        # Prueba de escritura canario dentro del volumen persistente /data/uploads del contenedor
        canary_token = f"canary_p20_{int(time.time())}"
        script = (
            "import os\n"
            f"path = '/data/uploads/.{canary_token}.tmp'\n"
            "with open(path, 'w') as f:\n"
            "    f.write('P20_CANARY_OK')\n"
            "with open(path, 'r') as f:\n"
            "    content = f.read()\n"
            "os.remove(path)\n"
            "print(content == 'P20_CANARY_OK')\n"
        )
        cmd_write = [
            "docker", "compose", "--env-file", ".env.lan", "-f", "docker-compose.lan.yml",
            "-p", "abst_p17_pilot", "exec", "-T", "api", "python", "-c", script
        ]
        try:
            res = subprocess.run(cmd_write, capture_output=True, text=True, timeout=8)
            write_ok = res.returncode == 0 and "True" in res.stdout
        except Exception:
            write_ok = False

        if not write_ok:
            status = "DOWN"
            msg = "Fallo de escritura en el volumen persistente /data/uploads del piloto."
        elif c_free_pct < 5 or d_free_pct < 5:
            status = "DEGRADED"
            msg = f"Espacio crítico en disco: C: {c_free_pct}% libre, D: {d_free_pct}% libre."
        elif c_free_pct < 10 or d_free_pct < 10:
            status = "DEGRADED"
            msg = f"Espacio bajo en disco: C: {c_free_pct}% libre, D: {d_free_pct}% libre."
        else:
            status = "HEALTHY"
            msg = f"Almacenamiento y volumen operacional: C: {c_free_pct}% libre, D: {d_free_pct}% libre, escritura verificada."

        return {
            "status": status,
            "disks": {
                "C": {"free_gb": round(c_usage.free / (1024**3), 2), "free_pct": c_free_pct},
                "D": {"free_gb": round(d_usage.free / (1024**3), 2), "free_pct": d_free_pct}
            },
            "volume_write_verified": write_ok,
            "message": msg
        }

    def check_containers(self) -> Dict[str, Any]:
        """Comprueba estado real, politicas de reinicio y fallos OOM en los 7 contenedores del piloto."""
        cmd = [
            "docker", "inspect",
            "--format", "{{.Name}}|{{.State.Status}}|{{.HostConfig.RestartPolicy.Name}}|{{.State.OOMKilled}}"
        ] + PILOT_CONTAINERS
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            if res.returncode == 0:
                lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
                containers_status = {}
                down_count = 0
                policy_violations = 0
                oom_detected = 0

                for line in lines:
                    parts = line.split("|")
                    if len(parts) == 4:
                        name = parts[0].lstrip("/")
                        state = parts[1]
                        policy = parts[2]
                        oom = parts[3].lower() == "true"

                        containers_status[name] = {
                            "state": state,
                            "restart_policy": policy,
                            "oom_killed": oom
                        }

                        if state != "running":
                            down_count += 1
                        if policy not in ("unless-stopped", "always"):
                            policy_violations += 1
                        if oom:
                            oom_detected += 1

                if down_count == 0 and policy_violations == 0 and oom_detected == 0:
                    status = "HEALTHY"
                    msg = "Los 7 contenedores del piloto se encuentran en ejecución con política 'unless-stopped'."
                elif down_count > 0:
                    status = "DOWN"
                    msg = f"{down_count} contenedor(es) del piloto no están en ejecución."
                else:
                    status = "DEGRADED"
                    msg = f"Contenedores operando pero con observaciones (Políticas: {policy_violations}, OOM: {oom_detected})."

                return {
                    "status": status,
                    "running_count": len(PILOT_CONTAINERS) - down_count,
                    "total_count": len(PILOT_CONTAINERS),
                    "details": containers_status,
                    "message": msg
                }
            else:
                return {
                    "status": "DOWN",
                    "details": {"error": res.stderr[:200]},
                    "message": "Fallo al inspeccionar contenedores Docker del piloto."
                }
        except Exception as e:
            return {
                "status": "UNKNOWN",
                "details": {"error": str(e)},
                "message": f"Excepción durante inspección de contenedores: {e}"
            }

    def check_network_ip_drift(self) -> Dict[str, Any]:
        """Verifica que la direccion IP esperada (192.168.100.7) siga asignada a un adaptador activo."""
        try:
            import socket
            hostname = socket.gethostname()
            all_ips = socket.gethostbyname_ex(hostname)[2]

            if EXPECTED_IP in all_ips:
                status = "HEALTHY"
                msg = f"Dirección IP del piloto verificada en adaptador activo: {EXPECTED_IP}."
            else:
                status = "DEGRADED"
                msg = f"DERIVA DE IP DETECTADA: {EXPECTED_IP} no figura entre las IPs activas del host ({all_ips})."

            return {
                "status": status,
                "expected_ip": EXPECTED_IP,
                "current_host_ips": all_ips,
                "message": msg
            }
        except Exception as e:
            return {
                "status": "UNKNOWN",
                "message": f"Error comprobando configuración de red IP: {e}"
            }

    def run_full_diagnostic(self) -> Dict[str, Any]:
        """Ejecuta todos los chequeos de infraestructura y coordina las alertas pertinentes."""
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target": EXPECTED_IP,
            "components": {}
        }

        checks = [
            ("postgresql", self.check_postgresql),
            ("redis", self.check_redis),
            ("rq_workers", self.check_rq_workers),
            ("api_https", self.check_api_https),
            ("caddy_tls", self.check_caddy_tls),
            ("volumes_storage", self.check_volumes_and_storage),
            ("containers", self.check_containers),
            ("network_ip", self.check_network_ip_drift)
        ]

        overall_status = "HEALTHY"
        for name, fn in checks:
            try:
                res = fn()
            except Exception as e:
                res = {"status": "UNKNOWN", "message": f"Fallo ejecutando comprobacion {name}: {e}"}

            results["components"][name] = res

            c_status = res.get("status", "UNKNOWN")
            if c_status in ("DOWN", "CRITICAL"):
                overall_status = "DOWN"
                self.alert_dispatcher.dispatch(name, "CRITICAL", res.get("message", "Fallo crítico en componente"), res.get("details"))
            elif c_status == "DEGRADED" and overall_status != "DOWN":
                overall_status = "DEGRADED"
                self.alert_dispatcher.dispatch(name, "WARNING", res.get("message", "Componente degradado"), res.get("details"))
            elif c_status == "HEALTHY":
                self.alert_dispatcher.resolve(name, f"Componente {name} reporta estado HEALTHY.")

        results["overall_status"] = overall_status

        # Persistir resultados en disco (D: y C:) de forma autónoma
        log_dirs = [
            Path(os.getenv("MONITOR_LOG_PRIMARY", r"D:\BACKUPS_PROYECTOS\ABAST_GP_P19_MIGRATION\logs")),
            Path(os.getenv("MONITOR_LOG_SECONDARY", r"C:\Users\PC\Documents\AbastLG\ABAST_GP_P19_SECONDARY_CUSTODY\logs"))
        ]
        for ldir in log_dirs:
            try:
                ldir.mkdir(parents=True, exist_ok=True)
                (ldir / "last_health_status.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                with open(ldir / "health_history.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(results) + "\n")
            except Exception:
                pass

        return results


def main():
    monitor = RealHealthMonitor()
    results = monitor.run_full_diagnostic()

    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
        return

    # Formato reporte estructurado
    print("\n" + "=" * 75)
    print("      ABAST GP V6 — DIAGNÓSTICO REAL DE INFRAESTRUCTURA (P20)")
    print("=" * 75)
    print(f"Timestamp:       {results['timestamp']}")
    print(f"Estado Global:   [{results['overall_status']}]")
    print("-" * 75)

    for comp, data in results["components"].items():
        st = data.get("status", "UNKNOWN")
        msg = data.get("message", "")
        tag = "[OK]  " if st == "HEALTHY" else ("[WARN]" if st == "DEGRADED" else "[FAIL]")
        print(f"{tag} {comp.upper():<16} [{st:<8}] : {msg}")

    print("=" * 75 + "\n")

if __name__ == "__main__":
    main()
