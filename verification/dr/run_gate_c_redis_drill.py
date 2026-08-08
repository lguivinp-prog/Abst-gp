"""
Orquestador y Validador Formal de Gate C: Pérdida Total de Redis y Reconstrucción SSOT
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

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.domain import Tenant, CaseFile, UploadedDocument, ProcessingJob, AuditLog
from app.services.job_repository import JobRepository
from app.services.job_recovery_engine import JobRecoveryEngine
from verification.dr.rebuild_redis import rebuild_redis_instance
from verification.dr.reconcile_jobs import reconcile_platform_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.gate_c_drill")


def run_gate_c_formal_drill(
    database_url: str,
    redis_url: str,
    output_dir: str = "/tmp/gate_c_artifacts"
) -> Dict[str, Any]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    log_file_path = out_path / "execution-log.txt"

    logs: List[str] = []

    def log(msg: str):
        logger.info(msg)
        logs.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

    log("================================================================================")
    log("GATE C: REDIS LOSS & REBUILD CERTIFICATION DRILL")
    log("================================================================================")

    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    r = redis.from_url(redis_url)

    now_utc = datetime.now(timezone.utc)
    ts = int(time.time())
    tenant_id = f"dr-tenant-gate-c-{ts}"

    try:
        # --- T0: Crear Datos y Estados de Jobs en PostgreSQL SSOT ---
        log("--- [T0] Creando Entidades y Estados de Jobs en PostgreSQL SSOT ---")
        tenant = Tenant(id=tenant_id, name="DR Gate C Redis Loss Enterprise Tenant")
        db.add(tenant)
        db.commit()

        case = CaseFile(
            title="Expediente Reconstruccion Redis",
            contract_type="Bienes",
            tenant_id=tenant_id,
            status="CREATED"
        )
        db.add(case)
        db.commit()

        doc = UploadedDocument(
            case_id=case.id,
            document_type="requirement",
            original_filename="Bases_Administrativas_GateC.pdf",
            stored_path=f"uploads/gate_c_{tenant_id}.pdf",
            mime_type="application/pdf",
            processing_status="pending"
        )
        db.add(doc)
        db.commit()

        # 1. Job QUEUED (Recuperable)
        job_queued = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="OCR_PROCESSING",
            idempotency_key=f"idemp-queued-{ts}",
            document_id=doc.id
        )
        log(f"Job QUEUED creado: {job_queued.job_id} (ID: {job_queued.id})")

        # 2. Job PROCESSING (Huérfano / Abortado en pleno procesamiento con heartbeat atrasado)
        job_processing = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="DOCUMENT_PARSING",
            idempotency_key=f"idemp-proc-{ts}",
            document_id=doc.id
        )
        JobRepository.update_progress(
            db=db,
            job_id=job_processing.job_id,
            progress=45,
            status="PROCESSING",
            worker_name="worker_dr_lost_instance_01",
            tenant_id=tenant_id
        )
        # Forzar created_at y heartbeat pasados para que califique como huérfano
        past_time = now_utc - timedelta(seconds=120)
        db.execute(text(f"UPDATE processing_jobs SET created_at = '{past_time.isoformat()}', started_at = '{past_time.isoformat()}', last_heartbeat_at = '{past_time.isoformat()}' WHERE id = {job_processing.id}"))
        db.commit()
        log(f"Job PROCESSING creado: {job_processing.job_id} (Worker: worker_dr_lost_instance_01, Heartbeat: Stale)")

        # 3. Job COMPLETED / READY (Estado terminal exitoso - NO debe re-ejecutarse)
        job_completed = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="SECTION_SPLIT",
            idempotency_key=f"idemp-comp-{ts}",
            document_id=doc.id
        )
        JobRepository.update_progress(
            db=db,
            job_id=job_completed.job_id,
            progress=50,
            status="PROCESSING",
            worker_name="worker_dr_normal_02",
            tenant_id=tenant_id
        )
        JobRepository.mark_completed(
            db=db,
            job_id=job_completed.job_id,
            tenant_id=tenant_id,
            worker_name="worker_dr_normal_02",
            pages_processed=12
        )
        log(f"Job COMPLETED creado: {job_completed.job_id} (Status: {job_completed.status})")

        # 4. Job FAILED FINAL (Estado terminal fallido no reintentable - NO debe modificarse)
        job_failed = JobRepository.create_job(
            db=db,
            case_id=case.id,
            tenant_id=tenant_id,
            user_id=None,
            job_type="TABLE_EXTRACTION",
            idempotency_key=f"idemp-fail-{ts}",
            document_id=doc.id
        )
        JobRepository.mark_failed(
            db=db,
            job_id=job_failed.job_id,
            error_message="PDF con firma digital ilegible o corrupta",
            error_category="CORRUPT_INPUT",
            failure_classification="FINAL",
            tenant_id=tenant_id
        )
        log(f"Job FAILED FINAL creado: {job_failed.job_id} (Status: {job_failed.status}, Class: {job_failed.failure_classification})")

        # --- T1: Inyectar Estado Efímero en Redis ---
        log("--- [T1] Inyectando Estado Efímero en Redis (Colas RQ, Locks, Cache) ---")
        r.set(f"rq:job:{job_queued.job_id}", json.dumps({"status": "queued", "tenant": tenant_id}))
        r.set(f"rq:job:{job_processing.job_id}", json.dumps({"status": "started", "worker": "worker_dr_lost_instance_01"}))
        r.rpush("rq:queue:default", job_queued.job_id)
        r.rpush("rq:queue:parsing", job_processing.job_id)
        r.set(f"cache:tenant:{tenant_id}:session", "active_session_token_123")
        r.set(f"lock:document:{doc.id}", "locked_by_worker")

        redis_initial_keys = r.dbsize()
        log(f"Redis poblado exitosamente con {redis_initial_keys} keys efímeras.")
        assert redis_initial_keys >= 5, f"Redis keys esperadas >= 5, obtenidas {redis_initial_keys}"

        # --- T2: Inyección de Desastre (Destrucción Total de Redis) ---
        log("--- [T2] Inyectando Desastre: Destrucción Total de Redis (FLUSHALL) ---")
        r.flushall()
        redis_destroyed_keys = r.dbsize()
        log(f"Redis tras FLUSHALL: {redis_destroyed_keys} keys.")
        redis_destroyed_pass = (redis_destroyed_keys == 0)

        # --- T3: Verificar Integridad de PostgreSQL como SSOT ---
        log("--- [T3] Verificando que PostgreSQL mantiene el 100% de los datos y estados ---")
        db.expire_all()
        jobs_in_db = db.query(ProcessingJob).filter(ProcessingJob.tenant_id == tenant_id).all()
        log(f"Total jobs encontrados en PostgreSQL SSOT tras desastre Redis: {len(jobs_in_db)}")
        postgres_ssot_pass = (len(jobs_in_db) == 4)

        # --- T4: Reconstrucción de Redis ---
        log("--- [T4] Reconstruyendo Redis Limpio (rebuild_redis_instance) ---")
        rebuild_report = rebuild_redis_instance(
            redis_url=redis_url,
            output_report_path=str(out_path / "redis-rebuild.json")
        )
        redis_rebuild_pass = (rebuild_report["status"] == "PASS" and rebuild_report["final_keys_count"] == 0)
        log(f"Resultado rebuild_redis_instance: {rebuild_report['status']}")

        # --- T5: Reconciliación Canónica de Jobs con JobRecoveryEngine ---
        log("--- [T5] Ejecutando Reconciliación Canónica desde SSOT PostgreSQL ---")
        reconciliation_report = reconcile_platform_jobs(
            database_url=database_url,
            output_report_path=str(out_path / "job-reconciliation.json")
        )
        log(f"Resultado reconcile_platform_jobs: {reconciliation_report['status']}")
        log(f"Scanned: {reconciliation_report['scanned_jobs_count']}, Retried/Requeued: {reconciliation_report['recovered_retried_count']}, Final Failed: {reconciliation_report['marked_failed_final_count']}")

        # --- T6: Validar Estados Finales Post-Reconciliación ---
        log("--- [T6] Validando Estados Finales en PostgreSQL SSOT ---")
        db.expire_all()

        j_queued_after = db.query(ProcessingJob).filter_by(job_id=job_queued.job_id).first()
        j_proc_after = db.query(ProcessingJob).filter_by(job_id=job_processing.job_id).first()
        j_comp_after = db.query(ProcessingJob).filter_by(job_id=job_completed.job_id).first()
        j_fail_after = db.query(ProcessingJob).filter_by(job_id=job_failed.job_id).first()

        log(f"Job QUEUED post-reconciliation: status={j_queued_after.status}, attempts={j_queued_after.attempt_count}")
        log(f"Job PROCESSING post-reconciliation: status={j_proc_after.status}, attempts={j_proc_after.attempt_count}")
        log(f"Job COMPLETED post-reconciliation: status={j_comp_after.status}, attempts={j_comp_after.attempt_count}")
        log(f"Job FAILED post-reconciliation: status={j_fail_after.status}, attempts={j_fail_after.attempt_count}, class={j_fail_after.failure_classification}")

        # Validar no re-ejecución duplicada de COMPLETED
        duplicate_execution_pass = (
            j_comp_after.status in ("READY", "COMPLETED") and
            j_comp_after.attempt_count == 1
        )

        # Validar consistencia de FAILED final
        failed_consistency_pass = (
            j_fail_after.status == "FAILED" and
            j_fail_after.failure_classification == "FINAL"
        )

        # Validar recuperación de job PROCESSING huérfano a QUEUED
        proc_recovered_pass = (
            j_proc_after.status in ("QUEUED", "pending") and
            j_proc_after.attempt_count >= 2
        )

        job_consistency_pass = duplicate_execution_pass and failed_consistency_pass and proc_recovered_pass

        # Validar presencia de auditoría
        audits = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).all()
        log(f"Total eventos de auditoría registrados: {len(audits)}")

        # Determinar estado global
        gate_status = "PASS" if (
            redis_destroyed_pass and
            postgres_ssot_pass and
            redis_rebuild_pass and
            duplicate_execution_pass and
            job_consistency_pass
        ) else "FAIL"

        gate_c_result = {
            "gate": "C",
            "status": gate_status,
            "redis_destroyed": "PASS" if redis_destroyed_pass else "FAIL",
            "postgres_ssot_verified": "PASS" if postgres_ssot_pass else "FAIL",
            "redis_rebuild": "PASS" if redis_rebuild_pass else "FAIL",
            "duplicate_execution": "PASS" if duplicate_execution_pass else "FAIL",
            "job_consistency": "PASS" if job_consistency_pass else "FAIL",
            "metrics": {
                "initial_redis_keys": redis_initial_keys,
                "redis_keys_post_disaster": redis_destroyed_keys,
                "rebuilt_redis_keys": rebuild_report["final_keys_count"],
                "postgres_jobs_tracked": len(jobs_in_db),
                "recovered_jobs_count": reconciliation_report["recovered_retried_count"],
                "completed_jobs_intact": duplicate_execution_pass,
                "failed_jobs_intact": failed_consistency_pass
            },
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }

        with open(out_path / "gate-c-result.json", "w", encoding="utf-8") as f:
            json.dump(gate_c_result, f, indent=2)

        # Guardar log completo
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(logs))

        log("=== Gate C Drill Finalizado con Éxito ===")
        return gate_c_result

    finally:
        # Limpieza de datos de prueba
        try:
            db.rollback()
            db.execute(text(f"DELETE FROM audit_logs WHERE tenant_id = '{tenant_id}'"))
            db.execute(text(f"DELETE FROM processing_metrics WHERE tenant_id = '{tenant_id}'"))
            db.execute(text(f"DELETE FROM processing_jobs WHERE tenant_id = '{tenant_id}'"))
            db.execute(text(f"DELETE FROM uploaded_documents WHERE stored_path LIKE '%{tenant_id}%'"))
            db.execute(text(f"DELETE FROM case_files WHERE tenant_id = '{tenant_id}'"))
            db.execute(text(f"DELETE FROM tenants WHERE id = '{tenant_id}'"))
            db.commit()
        except Exception as clean_err:
            logger.warning(f"Error en limpieza post-drill: {clean_err}")
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://dr_user:dr_password@localhost:5432/dr_db")
    r_url = os.getenv("REDIS_URL", "redis://redis-dr:6379/2")
    out_d = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gate_c_artifacts"

    res = run_gate_c_formal_drill(db_url, r_url, out_d)
    print(json.dumps(res, indent=2))
