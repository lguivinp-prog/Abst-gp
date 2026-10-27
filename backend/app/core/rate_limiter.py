"""
Limitador de Tasa Atomico (Rate Limiter) para ABST-GP V6 (P14 Hardening).
Implementa:
1. Ventanas deslizantes estrictamente atomicas en Redis mediante script Lua (P14-R1-07).
2. Determinacion segura de IP cliente con ipaddress y comprobacion de subredes CIDR.
3. Fallback en memoria thread-safe con threading.Lock.
"""

import time
import logging
import threading
import ipaddress
from typing import Tuple, List, Optional
from fastapi import Request, HTTPException, status
from app.core.config import settings

try:
    from redis import Redis
except ImportError:
    Redis = None

logger = logging.getLogger("app.security.rate_limiter")

# Fallback en memoria con cerrojo de exclusion mutua para concurrencia segura
_LOCAL_FALLBACK_LOCK = threading.Lock()
_LOCAL_FALLBACK_CACHE = {}

# Script Lua para evaluacion atomica de ventana deslizante en Redis
# KEYS[1]: Nombre de la clave de rate limit (ej. rl:login_ip:192.168.1.50)
# ARGV[1]: Marca de tiempo actual (segundos flotantes)
# ARGV[2]: Tamano de ventana (segundos)
# ARGV[3]: Maximo de intentos permitidos
# ARGV[4]: Identificador unico del intento (tiempo + nanosegundos aleatorios)
LUA_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_attempts = tonumber(ARGV[3])
local member_id = ARGV[4]

local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)

if count >= max_attempts then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = window
    if oldest and #oldest >= 2 then
        local oldest_time = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(window - (now - oldest_time)))
    end
    return {0, retry_after}
else
    redis.call('ZADD', key, now, member_id)
    redis.call('EXPIRE', key, math.ceil(window + 10))
    return {1, 0}
end
"""


def is_trusted_proxy_ip(ip_str: str, trusted_proxies: List[str]) -> bool:
    """
    Comprueba si una direccion IP pertenece a la lista o subredes CIDR de proxies confiables.
    Aplica analisis estricto mediante el modulo ipaddress (P14-R1-07).
    """
    try:
        candidate_ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False

    for proxy_entry in trusted_proxies:
        p_clean = proxy_entry.strip()
        if not p_clean:
            continue
        try:
            if "/" in p_clean:
                network = ipaddress.ip_network(p_clean, strict=False)
                if candidate_ip in network:
                    return True
            else:
                trusted_ip = ipaddress.ip_address(p_clean)
                if candidate_ip == trusted_ip:
                    return True
        except ValueError:
            # Ignorar entradas mal formadas o no IP
            continue

    return False


def get_trusted_client_ip(request: Request, trusted_proxies: Optional[List[str]] = None) -> str:
    """
    Obtiene la IP efectiva del cliente.
    SOLO confia en cabeceras X-Forwarded-For si la conexion directa (peer)
    procede comprobadamente de un proxy confiable en trusted_proxies.
    De lo contrario, retorna la IP directa de la conexion para impedir IP-spoofing (P14-R1-07).
    """
    direct_ip = "127.0.0.1"
    if request.client and request.client.host:
        direct_ip = request.client.host.strip()

    if not trusted_proxies:
        trusted_proxies = ["127.0.0.1", "::1"]

    if not is_trusted_proxy_ip(direct_ip, trusted_proxies):
        return direct_ip

    x_forwarded = request.headers.get("X-Forwarded-For")
    if not x_forwarded:
        return direct_ip

    # Analizar la cadena de IPs de X-Forwarded-For
    raw_hops = [h.strip() for h in x_forwarded.split(",") if h.strip()]
    if not raw_hops:
        return direct_ip

    # Validar que el primer hop sea una IP valida
    first_hop = raw_hops[0]
    try:
        ipaddress.ip_address(first_hop)
        return first_hop
    except ValueError:
        return direct_ip


def check_rate_limit(
    redis_client: Optional[object],
    key: str,
    max_attempts: int = 10,
    window_seconds: int = 300,
    now: Optional[float] = None
) -> Tuple[bool, int]:
    """
    Verifica un limite de tasa por ventana deslizante atoma.
    
    Retorna: (is_allowed, retry_after_seconds)
    - is_allowed: True si la peticion esta permitida, False si se ha excedido la cuota.
    - retry_after_seconds: Segundos restantes para que expire la restriccion.
    """
    current_time = now if now is not None else time.time()
    full_key = f"rl:{key}"
    member_id = f"{current_time}:{time.time_ns()}"

    app_env = getattr(settings, "APP_ENV", "development").lower()
    is_prod_or_lan = app_env in ("lan", "production", "prod")

    if redis_client is not None:
        try:
            # Evaluacion atomica en servidor Redis mediante LUA
            result = redis_client.eval(
                LUA_SLIDING_WINDOW_SCRIPT,
                1,
                full_key,
                current_time,
                window_seconds,
                max_attempts,
                member_id
            )
            # result[0] == 1 -> permitido, result[0] == 0 -> bloqueado
            is_allowed = bool(result[0] == 1)
            retry_after = int(result[1])
            return is_allowed, retry_after
        except Exception as e:
            logger.critical(f"Fallo critico en evaluacion de rate limit en Redis ({e}) bajo entorno {app_env}.")
            if is_prod_or_lan:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Servicio de control de tasa y seguridad temporalmente no disponible (fail-closed)."
                )
    elif is_prod_or_lan:
        logger.critical(f"Redis no configurado para rate limiting bajo entorno {app_env}.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de seguridad no configurado adecuadamente (fail-closed)."
        )

    # Fallback local seguro en memoria con Lock: PERMITIDO UNICAMENTE en test, development o local
    cutoff_time = current_time - window_seconds
    with _LOCAL_FALLBACK_LOCK:
        records = _LOCAL_FALLBACK_CACHE.get(full_key, [])
        valid_records = [t for t in records if t > cutoff_time]

        if len(valid_records) >= max_attempts:
            oldest_time = valid_records[0]
            retry_after = max(1, int(window_seconds - (current_time - oldest_time)))
            _LOCAL_FALLBACK_CACHE[full_key] = valid_records
            return False, retry_after

        valid_records.append(current_time)
        _LOCAL_FALLBACK_CACHE[full_key] = valid_records
        return True, 0


def reset_rate_limit(redis_client: Optional[object], key: str) -> None:
    """Restablece el contador de intentos tras una autenticacion exitosa."""
    full_key = f"rl:{key}"
    if redis_client is not None:
        try:
            redis_client.delete(full_key)
        except Exception as e:
            logger.warning(f"Error reseteando rate limit en Redis ({e}).")

    with _LOCAL_FALLBACK_LOCK:
        _LOCAL_FALLBACK_CACHE.pop(full_key, None)
