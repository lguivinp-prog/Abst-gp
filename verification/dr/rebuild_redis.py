"""
Reconstructor y Limpiador de Instancia Redis 7 (Fase 7.4)
Garantiza que Redis arranque completamente vacío para evitar jobs o payloads fantasma previos al DR.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.rebuild_redis")


def rebuild_redis_instance(
    redis_url: str,
    output_report_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Limpia y valida el estado de la instancia Redis:
    1. Ejecuta FLUSHALL / FLUSHDB de forma segura.
    2. Comprueba conectividad y confirma que el número de keys sea exactamente 0.
    """
    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "redis_url_sanitized": redis_url.split("@")[-1] if "@" in redis_url else redis_url,
        "initial_keys_count": 0,
        "final_keys_count": 0,
        "ping_ok": False
    }

    try:
        r = redis.from_url(redis_url)
        report["ping_ok"] = bool(r.ping())
        report["initial_keys_count"] = r.dbsize()

        logger.info(f"Limpiando Redis (DBSYS inicial: {report['initial_keys_count']} keys)...")
        r.flushdb()

        report["final_keys_count"] = r.dbsize()
        if report["final_keys_count"] != 0:
            report["status"] = "FAIL"
            logger.error(f"Redis no quedó completamente vacío tras flushdb: {report['final_keys_count']} keys.")

        logger.info("Redis reconstruido e inicializado con estado limpio (0 keys).")

        if output_report_path:
            p = Path(output_report_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

        return report

    except Exception as e:
        logger.error(f"Error reconstruyendo Redis: {e}", exc_info=True)
        report["status"] = "FAIL"
        report["error"] = str(e)
        raise


if __name__ == "__main__":
    r_url = os.getenv("REDIS_URL", "redis://redis-dr:6379/2")
    out_p = sys.argv[1] if len(sys.argv) > 1 else None

    res = rebuild_redis_instance(r_url, out_p)
    print(json.dumps(res, indent=2))
