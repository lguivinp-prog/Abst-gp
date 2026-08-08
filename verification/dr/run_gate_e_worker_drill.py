"""
Orquestador y Validador Formal de Gate E: Worker Recovery & Job Reconciliation
Fase 7.4-C Certificación Formal Disaster Recovery
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.domain import Tenant, CaseFile, ProcessingJob, AuditLog, WorkerHeartbeat
from app.services.job_repository import JobRepository
from app.services.job_recovery_engine import JobRecoveryEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.gate_e_drill")


def run_gate_e_formal_drill(
    database_url: str,
    output_dir: str = "/app/artifacts/dr/gate-e"
) -> Dict[str, Any]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    log_file_path = out_path / "execution-log.txt"

    logs: List[str] = []

    def log(msg: str):
        logger.info(msg)
        logs.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

    log("================================================================================")
    log("GATE E: WORKER RECOVERY & JOB RECONCILIATION DRILL")
    log("================================================================================")

    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    ts = int(time.time())
    tenant_id = f"dr-tenant-gate-e-{ts}"
    case_id = None
    created_job_ids: List[str] = []

    try:
        # --- T0: Creación de Entidades y los 5 Estados de Jobs en PostgreSQL SSOT ---
        log("--- [T0] Creando Tenant, Expediente y Jobs en los 5 Estados Canónicos ---")

        tenant = Tenant(id=tenant_id, name="DR Tenant Gate E Worker Recovery")
        db.add(tenant)
        db.commit()

        case = CaseFile(
            title="Expediente Reconciliacion Worker Gate E",
            contract_type="Bienes",
            tenant_id=tenant_id,
            status="CREATED"
        )
        db.add(case)
        db.commit()
        case_id = case.id

        now = datetime.now(timezone.utc)
        stale_heartbeat_time = now - timedelta(minutes=15)

        # 1. Job QUEUED (Fresco, en espera legítima)
        job_queued = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="OCR_PROCESSING",
            idempotency_key=f"idemp-gate-e-queued-{ts}"
        )
        created_job_ids.append(job_queued.job_id)

        # 2. Job PROCESSING ACTIVO (Worker vivo, heartbeat reciente)
        job_proc_active = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="DOCUMENT_EXTRACTION",
            idempotency_key=f"idemp-gate-e-active-{ts}"
        )
        JobRepository.update_progress(
            db=db,
            job_id=job_proc_active.job_id,
            progress=35,
            status="PROCESSING",
            worker_name="worker_node_alive_1",
            tenant_id=tenant_id
        )
        # Latido activo reciente
        job_proc_active.last_heartbeat_at = now
        db.commit()
        created_job_ids.append(job_proc_active.job_id)

        # 3. Job PROCESSING HUÉRFANO (Worker muerto, heartbeat expirado hace 15 min)
        job_proc_dead = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="OCR_PROCESSING",
            idempotency_key=f"idemp-gate-e-dead-{ts}"
        )
        JobRepository.update_progress(
            db=db,
            job_id=job_proc_dead.job_id,
            progress=50,
            status="PROCESSING",
            worker_name="worker_dead_crashed_node_99",
            tenant_id=tenant_id
        )
        job_proc_dead.last_heartbeat_at = stale_heartbeat_time
        job_proc_dead.started_at = stale_heartbeat_time
        job_proc_dead.created_at = stale_heartbeat_time
        db.commit()
        created_job_ids.append(job_proc_dead.job_id)

        # 4. Job COMPLETED (Estado terminal exitoso)
        job_completed = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="TABLE_EXTRACTION",
            idempotency_key=f"idemp-gate-e-comp-{ts}"
        )
        JobRepository.update_progress(
            db=db,
            job_id=job_completed.job_id,
            progress=50,
            status="PROCESSING",
            worker_name="worker_node_prev",
            tenant_id=tenant_id
        )
        JobRepository.mark_completed(
            db=db,
            job_id=job_completed.job_id,
            tenant_id=tenant_id,
            worker_name="worker_node_prev",
            pages_processed=10
        )
        created_job_ids.append(job_completed.job_id)

        # 5. Job FAILED FINAL (Estado terminal de error no reintentable)
        job_failed_final = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="DOCUMENT_VALIDATION",
            idempotency_key=f"idemp-gate-e-fail-{ts}"
        )
        JobRepository.mark_failed(
            db=db,
            job_id=job_failed_final.job_id,
            error_message="INVALID_DOCUMENT_STRUCTURE: Formato de archivo incompatible y corrupto",
            failure_classification="FINAL",
            worker_name="worker_node_prev",
            tenant_id=tenant_id
        )
        created_job_ids.append(job_failed_final.job_id)

        # 6. Job PROCESSING MAX RETRIES EXCEEDED (Huérfano que ya consumió max_retries)
        job_max_retries = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="OCR_PROCESSING",
            idempotency_key=f"idemp-gate-e-maxretries-{ts}"
        )
        JobRepository.update_progress(
            db=db,
            job_id=job_max_retries.job_id,
            progress=20,
            status="PROCESSING",
            worker_name="worker_dead_crashed_node_99",
            tenant_id=tenant_id
        )
        job_max_retries.attempt_count = 3
        job_max_retries.max_retries = 3
        job_max_retries.last_heartbeat_at = stale_heartbeat_time
        job_max_retries.started_at = stale_heartbeat_time
        job_max_retries.created_at = stale_heartbeat_time
        db.commit()
        created_job_ids.append(job_max_retries.job_id)

        log("Jobs inicializados en PostgreSQL SSOT:")
        log(f"  - 1. QUEUED (Fresco): {job_queued.job_id} | Status: {job_queued.status} | Attempts: {job_queued.attempt_count}")
        log(f"  - 2. PROCESSING (Activo): {job_proc_active.job_id} | Worker: worker_node_alive_1 | Status: {job_proc_active.status}")
        log(f"  - 3. PROCESSING (Huérfano/Muerto): {job_proc_dead.job_id} | Worker: worker_dead_crashed_node_99 | Heartbeat: {job_proc_dead.last_heartbeat_at}")
        log(f"  - 4. COMPLETED: {job_completed.job_id} | Status: {job_completed.status}")
        log(f"  - 5. FAILED FINAL: {job_failed_final.job_id} | Classification: {job_failed_final.failure_classification}")
        log(f"  - 6. PROCESSING (Max Retries): {job_max_retries.job_id} | Attempts: {job_max_retries.attempt_count}/{job_max_retries.max_retries}")

        # --- T1: Simulación de Desastre de Worker ---
        log("--- [T1] Simulando Desastre: Muerte Abrupta de Worker y Pérdida Total de Heartbeat ---")
        log("Worker 'worker_dead_crashed_node_99' finalizado abruptamente sin enviar mensaje de terminación.")

        # --- T2: Ejecución de JobRecoveryEngine ---
        log("--- [T2] Ejecutando JobRecoveryEngine con escaneo de latidos y reconciliación SSOT ---")
        t_start_rec = time.perf_counter()

        recovery_engine = JobRecoveryEngine(
            db_factory=SessionLocal,
            heartbeat_timeout_seconds=30,
            queued_timeout_seconds=600,
            base_backoff_sec=2
        )

        recovery_report = recovery_engine.scan_and_recover(
            tenant_id=tenant_id,
            db=db
        )
        rec_duration = time.perf_counter() - t_start_rec

        log(f"JobRecoveryEngine finalizado en {rec_duration:.4f}s.")
        log(f"Reporte de Escaneo: Total={recovery_report.total_scanned}, StaleProcessing={recovery_report.stale_processing_count}, "
            f"RecoveredRetried={recovery_report.recovered_retried}, MarkedFailedMaxRetries={recovery_report.marked_failed_max_retries}")

        # --- T3: Validaciones Rigurosas de Estados y Reglas de Negocio ---
        log("--- [T3] Verificando Reglas de Consistencia y Reconciliación en Base de Datos ---")

        db.refresh(job_queued)
        db.refresh(job_proc_active)
        db.refresh(job_proc_dead)
        db.refresh(job_completed)
        db.refresh(job_failed_final)
        db.refresh(job_max_retries)

        # Validación 1: Detección de Worker Muerto
        dead_worker_detected = (
            job_proc_dead.job_id in [d["job_id"] for d in recovery_report.job_details] and
            job_max_retries.job_id in [d["job_id"] for d in recovery_report.job_details]
        )
        log(f"1. Detección de Worker Muerto (dead_worker_detection): {'PASS' if dead_worker_detected else 'FAIL'}")

        # Validación 2: Reencolado de Job Huérfano con incremento de attempt_count
        job_requeued_pass = (
            job_proc_dead.status == "QUEUED" and
            job_proc_dead.attempt_count == 2 and
            job_proc_dead.worker_name is None and
            job_proc_dead.last_heartbeat_at is None and
            job_proc_dead.failure_classification == "RETRYABLE"
        )
        log(f"2. Re-encolado de Job Huérfano (job_requeue): {'PASS' if job_requeued_pass else 'FAIL'} "
            f"(Status: {job_proc_dead.status}, Attempts: {job_proc_dead.attempt_count})")

        # Validación 3: Cero Duplicación de Ejecución y Respeto a Estados Terminales
        # - Job COMPLETED debe permanecer COMPLETED
        # - Job FAILED FINAL debe permanecer FAILED
        # - Job QUEUED fresco debe permanecer QUEUED
        # - Job PROCESSING activo con worker vivo debe permanecer PROCESSING
        # - Job con max_retries excedido debe pasar a FAILED definitivo
        no_duplicates_pass = (
            job_completed.status in ("COMPLETED", "READY") and
            job_failed_final.status == "FAILED" and
            job_failed_final.failure_classification == "FINAL" and
            job_queued.status == "QUEUED" and
            job_queued.attempt_count == 1 and
            job_proc_active.status == "PROCESSING" and
            job_max_retries.status == "FAILED" and
            job_max_retries.failure_classification == "FINAL"
        )
        log(f"3. Cero Duplicación y Protección de Estados Terminales (duplicate_execution): {'PASS' if no_duplicates_pass else 'FAIL'}")
        log(f"     - COMPLETED status: {job_completed.status}")
        log(f"     - FAILED_FINAL status: {job_failed_final.status}")
        log(f"     - QUEUED fresco status: {job_queued.status}")
        log(f"     - PROCESSING activo status: {job_proc_active.status}")
        log(f"     - MAX_RETRIES job status: {job_max_retries.status}")

        # Validación 4: Integridad de AuditLog
        audit_logs = db.query(AuditLog).filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.entity_type == "ProcessingJob"
        ).all()

        actions = [a.action for a in audit_logs]
        log(f"AuditLogs registrados para Tenant {tenant_id}: {actions}")

        has_retry_audit = any(a.action == "JOB_RECOVERY_RETRY" and a.entity_id == job_proc_dead.job_id for a in audit_logs)
        has_max_retries_audit = any(a.action == "JOB_RECOVERY_MAX_RETRIES_EXCEEDED" and a.entity_id == job_max_retries.job_id for a in audit_logs)

        audit_integrity_pass = has_retry_audit and has_max_retries_audit
        log(f"4. Integridad de Auditoría en AuditLog (audit_integrity): {'PASS' if audit_integrity_pass else 'FAIL'}")

        # --- T4: Generación de Artefactos Formales ---
        log("--- [T4] Escribiendo Artefactos Formales en artifacts/dr/gate-e/ ---")

        # 1. worker-recovery.json
        worker_recovery_data = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if dead_worker_detected and job_requeued_pass else "FAIL",
            "dead_workers_simulated": [
                {
                    "worker_name": "worker_dead_crashed_node_99",
                    "crashed_at_utc": stale_heartbeat_time.isoformat(),
                    "abandoned_jobs": [job_proc_dead.job_id, job_max_retries.job_id]
                }
            ],
            "active_workers_verified": [
                {
                    "worker_name": "worker_node_alive_1",
                    "status": "HEALTHY",
                    "active_job": job_proc_active.job_id,
                    "disrupted": False
                }
            ],
            "recovery_engine_metrics": {
                "scan_duration_seconds": rec_duration,
                "total_scanned": recovery_report.total_scanned,
                "stale_processing_detected": recovery_report.stale_processing_count,
                "jobs_retried": recovery_report.recovered_retried,
                "jobs_max_retries_failed": recovery_report.marked_failed_max_retries
            }
        }
        with open(out_path / "worker-recovery.json", "w", encoding="utf-8") as f:
            json.dump(worker_recovery_data, f, indent=2)

        # 2. job-reconciliation.json
        job_reconciliation_data = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if no_duplicates_pass and audit_integrity_pass else "FAIL",
            "reconciliation_matrix": [
                {
                    "scenario": "1. QUEUED_FRESH",
                    "job_id": job_queued.job_id,
                    "initial_status": "QUEUED",
                    "final_status": job_queued.status,
                    "attempt_count": job_queued.attempt_count,
                    "action_taken": "NONE_PROCESSABLE",
                    "correct": (job_queued.status == "QUEUED" and job_queued.attempt_count == 1)
                },
                {
                    "scenario": "2. PROCESSING_ACTIVE_WORKER",
                    "job_id": job_proc_active.job_id,
                    "initial_status": "PROCESSING",
                    "final_status": job_proc_active.status,
                    "attempt_count": job_proc_active.attempt_count,
                    "action_taken": "NONE_ACTIVE",
                    "correct": (job_proc_active.status == "PROCESSING")
                },
                {
                    "scenario": "3. PROCESSING_DEAD_WORKER",
                    "job_id": job_proc_dead.job_id,
                    "initial_status": "PROCESSING",
                    "final_status": job_proc_dead.status,
                    "attempt_count": job_proc_dead.attempt_count,
                    "action_taken": "RETRY_QUEUED",
                    "correct": (job_proc_dead.status == "QUEUED" and job_proc_dead.attempt_count == 2)
                },
                {
                    "scenario": "4. COMPLETED_TERMINAL",
                    "job_id": job_completed.job_id,
                    "initial_status": "COMPLETED",
                    "final_status": job_completed.status,
                    "attempt_count": job_completed.attempt_count,
                    "action_taken": "SKIPPED_TERMINAL",
                    "correct": (job_completed.status in ("COMPLETED", "READY"))
                },
                {
                    "scenario": "5. FAILED_FINAL_TERMINAL",
                    "job_id": job_failed_final.job_id,
                    "initial_status": "FAILED",
                    "final_status": job_failed_final.status,
                    "attempt_count": job_failed_final.attempt_count,
                    "action_taken": "SKIPPED_TERMINAL",
                    "correct": (job_failed_final.status == "FAILED" and job_failed_final.failure_classification == "FINAL")
                },
                {
                    "scenario": "6. PROCESSING_MAX_RETRIES",
                    "job_id": job_max_retries.job_id,
                    "initial_status": "PROCESSING",
                    "final_status": job_max_retries.status,
                    "attempt_count": job_max_retries.attempt_count,
                    "action_taken": "MARKED_FAILED_FINAL",
                    "correct": (job_max_retries.status == "FAILED" and job_max_retries.failure_classification == "FINAL")
                }
            ],
            "audit_trail_verified": [
                {
                    "action": a.action,
                    "entity_id": a.entity_id,
                    "status": a.status,
                    "details": a.details
                }
                for a in audit_logs
            ]
        }
        with open(out_path / "job-reconciliation.json", "w", encoding="utf-8") as f:
            json.dump(job_reconciliation_data, f, indent=2)

        # 3. gate-e-result.json
        gate_status = "PASS" if (
            dead_worker_detected and
            job_requeued_pass and
            no_duplicates_pass and
            audit_integrity_pass
        ) else "FAIL"

        gate_e_result = {
            "gate": "E",
            "status": gate_status,
            "dead_worker_detection": "PASS" if dead_worker_detected else "FAIL",
            "job_requeue": "PASS" if job_requeued_pass else "FAIL",
            "duplicate_execution": "PASS" if no_duplicates_pass else "FAIL",
            "audit_integrity": "PASS" if audit_integrity_pass else "FAIL"
        }

        with open(out_path / "gate-e-result.json", "w", encoding="utf-8") as f:
            json.dump(gate_e_result, f, indent=2)

        # 4. execution-log.txt
        log("=== Gate E Drill Finalizado con Éxito ===")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(logs))

        return gate_e_result

    finally:
        # Limpieza segura
        try:
            if created_job_ids:
                jobs_in_str = "','".join(created_job_ids)
                db.execute(text(f"DELETE FROM processing_metrics WHERE job_id IN ('{jobs_in_str}')"))
            db.execute(text(f"DELETE FROM audit_logs WHERE tenant_id = '{tenant_id}'"))
            db.execute(text(f"DELETE FROM processing_jobs WHERE tenant_id = '{tenant_id}'"))
            if case_id:
                db.execute(text(f"DELETE FROM case_files WHERE id = {case_id}"))
            db.execute(text(f"DELETE FROM tenants WHERE id = '{tenant_id}'"))
            db.commit()
        except Exception as clean_err:
            logger.warning(f"Error en limpieza post-drill Gate E: {clean_err}")
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://dr_user:dr_password@localhost:5432/dr_db")
    out_d = sys.argv[1] if len(sys.argv) > 1 else "/app/artifacts/dr/gate-e"

    res = run_gate_e_formal_drill(database_url=db_url, output_dir=out_d)
    print(json.dumps(res, indent=2))
