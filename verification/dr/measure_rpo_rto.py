"""
Medidor y Evaluador Cuantitativo de RPO y RTO (Fase 7.4)
Calcula métricas exactas sin redondeo a favor y valida contra los umbrales de certificación:
RPO <= 5 min (300s), RTO <= 15 min (900s).
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.measure_rpo_rto")


def compute_dr_metrics(
    incident_declared_time_utc: str,
    latest_recovered_transaction_time_utc: str,
    latest_recovered_document_time_utc: str,
    restore_start_time_utc: str,
    e2e_validation_pass_time_utc: str,
    breakdown_timings: Optional[Dict[str, float]] = None,
    output_report_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calcula de forma determinista y estricta:
    1. RPO PostgreSQL = incident_declared_time - latest_recovered_transaction_time
    2. RPO Documental = incident_declared_time - latest_recovered_document_time
    3. RPO Efectivo = MAX(RPO PostgreSQL, RPO Documental)
    4. RTO Total = e2e_validation_pass_time - incident_declared_time
    """
    t_incident = datetime.fromisoformat(incident_declared_time_utc)
    t_pg_tx = datetime.fromisoformat(latest_recovered_transaction_time_utc)
    t_doc = datetime.fromisoformat(latest_recovered_document_time_utc)
    t_restore_start = datetime.fromisoformat(restore_start_time_utc)
    t_e2e_pass = datetime.fromisoformat(e2e_validation_pass_time_utc)

    # RPO Cálculos en segundos
    rpo_pg_sec = max(0.0, (t_incident - t_pg_tx).total_seconds())
    rpo_doc_sec = max(0.0, (t_incident - t_doc).total_seconds())
    rpo_effective_sec = max(rpo_pg_sec, rpo_doc_sec)

    # RTO Cálculos en segundos
    rto_total_sec = max(0.0, (t_e2e_pass - t_incident).total_seconds())
    rto_restore_execution_sec = max(0.0, (t_e2e_pass - t_restore_start).total_seconds())

    # Umbrales
    RPO_MAX_ALLOWED_SEC = 300.0   # 5 minutos
    RTO_MAX_ALLOWED_SEC = 900.0   # 15 minutos

    rpo_pass = rpo_effective_sec <= RPO_MAX_ALLOWED_SEC
    rto_pass = rto_total_sec <= RTO_MAX_ALLOWED_SEC
    overall_status = "PASS" if (rpo_pass and rto_pass) else "FAIL"

    timings = breakdown_timings or {}
    
    report: Dict[str, Any] = {
        "calculated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": overall_status,
        "timestamps": {
            "incident_declared_utc": incident_declared_time_utc,
            "latest_pg_tx_utc": latest_recovered_transaction_time_utc,
            "latest_doc_snapshot_utc": latest_recovered_document_time_utc,
            "restore_started_utc": restore_start_time_utc,
            "e2e_validation_pass_utc": e2e_validation_pass_time_utc,
        },
        "rpo_metrics": {
            "rpo_postgres_seconds": round(rpo_pg_sec, 3),
            "rpo_documents_seconds": round(rpo_doc_sec, 3),
            "rpo_effective_seconds": round(rpo_effective_sec, 3),
            "rpo_threshold_seconds": RPO_MAX_ALLOWED_SEC,
            "rpo_status": "PASS" if rpo_pass else "FAIL",
            "redis_rpo": "NOT_APPLICABLE_EPHEMERAL"
        },
        "rto_metrics": {
            "rto_total_seconds": round(rto_total_sec, 3),
            "rto_restore_execution_seconds": round(rto_restore_execution_sec, 3),
            "rto_threshold_seconds": RTO_MAX_ALLOWED_SEC,
            "rto_status": "PASS" if rto_pass else "FAIL",
            "breakdown_seconds": {
                "manifest_and_checksum_verification": round(timings.get("manifest_verification_seconds", 0.0), 3),
                "postgres_base_restore": round(timings.get("postgres_restore_seconds", 0.0), 3),
                "wal_replay_pitr": round(timings.get("wal_replay_seconds", 0.0), 3),
                "document_filesystem_restore": round(timings.get("document_restore_seconds", 0.0), 3),
                "redis_clean_rebuild": round(timings.get("redis_rebuild_seconds", 0.0), 3),
                "job_reconciliation_engine": round(timings.get("job_reconciliation_seconds", 0.0), 3),
                "worker_startup_and_health": round(timings.get("worker_startup_seconds", 0.0), 3),
                "functional_e2e_validation": round(timings.get("e2e_validation_seconds", 0.0), 3),
            }
        }
    }

    logger.info(f"=== RPO EFECTIVO: {rpo_effective_sec:.2f}s ({report['rpo_metrics']['rpo_status']}) ===")
    logger.info(f"=== RTO TOTAL: {rto_total_sec:.2f}s ({report['rto_metrics']['rto_status']}) ===")

    if output_report_path:
        p = Path(output_report_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    res = compute_dr_metrics(
        incident_declared_time_utc=now.isoformat(),
        latest_recovered_transaction_time_utc=now.isoformat(),
        latest_recovered_document_time_utc=now.isoformat(),
        restore_start_time_utc=now.isoformat(),
        e2e_validation_pass_time_utc=now.isoformat(),
        breakdown_timings={}
    )
    print(json.dumps(res, indent=2))
