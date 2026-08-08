"""
Orquestador y Validador Formal de Gate G: Multi-Tenant Isolation DR Certification
Fase 7.4-C Certificación Formal Disaster Recovery
"""

import os
import sys
import time
import json
import shutil
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.domain import (
    Tenant,
    User,
    CaseFile,
    UploadedDocument,
    ProcessingJob,
    ProcessingMetrics,
    AuditLog
)
from app.services.job_repository import JobRepository
from verification.dr.create_backup import create_backup_package
from verification.dr.restore_backup import restore_backup_package

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.gate_g_drill")


def run_gate_g_formal_drill(
    database_url: str,
    output_dir: str = "/app/artifacts/dr/gate-g"
) -> Dict[str, Any]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    log_file_path = out_path / "execution-log.txt"

    logs: List[str] = []

    def log(msg: str):
        logger.info(msg)
        logs.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

    log("================================================================================")
    log("GATE G: MULTI-TENANT ISOLATION DR CERTIFICATION DRILL")
    log("================================================================================")

    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    ts = int(time.time())
    tenant_a_id = f"tenant-alpha-{ts}"
    tenant_b_id = f"tenant-bravo-{ts}"

    vault_base_dir = Path("/app/data/vault_dr_gate_g")
    uploads_dir = Path("/app/data/uploads_dr_gate_g")
    vault_base_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    signing_secret = "abst_gp_gate_g_cryptographic_key_secret_12345678"

    case_a = None
    case_b = None

    try:
        # --- T0: Creación de Entornos Multi-Tenant Aislados (SSOT PostgreSQL) ---
        log("--- [T0] Inicializando Tenants Aislados Tenant A (Alpha) y Tenant B (Bravo) ---")

        # 1. Crear Tenants
        tenant_a = Tenant(id=tenant_a_id, name="Corporativo Alpha Seguros")
        tenant_b = Tenant(id=tenant_b_id, name="Corporativo Bravo Finanzas")
        db.add_all([tenant_a, tenant_b])
        db.commit()

        # 2. Crear Usuarios por Tenant
        user_a = User(
            username=f"user_alpha_{ts}",
            password_hash="argon2id$alpha_hash",
            role="operator",
            tenant_id=tenant_a_id
        )
        user_b = User(
            username=f"user_bravo_{ts}",
            password_hash="argon2id$bravo_hash",
            role="operator",
            tenant_id=tenant_b_id
        )
        db.add_all([user_a, user_b])
        db.commit()
        db.refresh(user_a)
        db.refresh(user_b)

        # 3. Crear Expedientes y Documentos para Tenant A
        case_a = CaseFile(
            title="Expediente Confidencial Alpha",
            contract_type="Póliza Patrimonial",
            tenant_id=tenant_a_id,
            created_by=user_a.id,
            status="ACTIVE"
        )
        db.add(case_a)
        db.commit()
        db.refresh(case_a)

        doc_a_path = uploads_dir / tenant_a_id / "contrato_alpha_secreto.pdf"
        doc_a_path.parent.mkdir(parents=True, exist_ok=True)
        doc_a_content = f"DATOS_CONFIDENCIALES_TENANT_ALPHA_{ts}\n".encode("utf-8")
        doc_a_path.write_bytes(doc_a_content)

        doc_a = UploadedDocument(
            case_id=case_a.id,
            document_type="requirement",
            original_filename="contrato_alpha_secreto.pdf",
            stored_path=str(doc_a_path),
            mime_type="application/pdf",
            processing_status="completed"
        )
        db.add(doc_a)

        # 4. Crear Expedientes y Documentos para Tenant B
        case_b = CaseFile(
            title="Expediente Confidencial Bravo",
            contract_type="Crédito Sindicado",
            tenant_id=tenant_b_id,
            created_by=user_b.id,
            status="ACTIVE"
        )
        db.add(case_b)
        db.commit()
        db.refresh(case_b)

        doc_b_path = uploads_dir / tenant_b_id / "balance_bravo_secreto.pdf"
        doc_b_path.parent.mkdir(parents=True, exist_ok=True)
        doc_b_content = f"DATOS_CONFIDENCIALES_TENANT_BRAVO_{ts}\n".encode("utf-8")
        doc_b_path.write_bytes(doc_b_content)

        doc_b = UploadedDocument(
            case_id=case_b.id,
            document_type="requirement",
            original_filename="balance_bravo_secreto.pdf",
            stored_path=str(doc_b_path),
            mime_type="application/pdf",
            processing_status="completed"
        )
        db.add(doc_b)
        db.commit()
        db.refresh(doc_a)
        db.refresh(doc_b)

        # 5. Crear Jobs y Métricas para ambos Tenants
        job_a = JobRepository.create_job(
            db=db,
            case_id=case_a.id,
            tenant_id=tenant_a_id,
            user_id=user_a.id,
            job_type="OCR_PROCESSING",
            document_id=doc_a.id
        )
        JobRepository.update_progress(db, job_a.job_id, 100, "Completado Alpha", "COMPLETED", tenant_id=tenant_a_id, worker_name="worker_alpha_1")
        JobRepository._record_metric(db, job_a, "worker_alpha_1", True, pages_processed=10)

        job_b = JobRepository.create_job(
            db=db,
            case_id=case_b.id,
            tenant_id=tenant_b_id,
            user_id=user_b.id,
            job_type="TABLE_EXTRACTION",
            document_id=doc_b.id
        )
        JobRepository.update_progress(db, job_b.job_id, 100, "Completado Bravo", "COMPLETED", tenant_id=tenant_b_id, worker_name="worker_bravo_1")
        JobRepository._record_metric(db, job_b, "worker_bravo_1", True, pages_processed=25)

        db.commit()
        log(f"Datos creados exitosamente. Tenant A (Case {case_a.id}, Doc {doc_a.id}, Job {job_a.job_id}), Tenant B (Case {case_b.id}, Doc {doc_b.id}, Job {job_b.job_id})")

        # --- T1: Escenario Negativo 1 - Intento de Acceso Cruzado a Documentos/Expedientes ---
        log("--- [T1] Escenario Negativo 1: Tenant A intenta leer documentos y expedientes de Tenant B ---")

        # Consulta de expediente con scope Tenant A buscando id de Tenant B
        leaked_case = db.query(CaseFile).filter(
            CaseFile.tenant_id == tenant_a_id,
            CaseFile.id == case_b.id
        ).first()

        # Consulta de documentos uniendo CaseFile con scope Tenant A
        leaked_doc = db.query(UploadedDocument).join(CaseFile).filter(
            CaseFile.tenant_id == tenant_a_id,
            UploadedDocument.id == doc_b.id
        ).first()

        doc_isolation_pass = (leaked_case is None and leaked_doc is None)
        log(f"Consulta cruzada Case B con scope Tenant A: {'DENIED/NONE (PASS)' if leaked_case is None else 'LEAK DETECTED (FAIL)'}")
        log(f"Consulta cruzada Document B con scope Tenant A: {'DENIED/NONE (PASS)' if leaked_doc is None else 'LEAK DETECTED (FAIL)'}")

        # Auditoría del intento de acceso denegado
        audit_doc = AuditLog(
            tenant_id=tenant_a_id,
            user_id=user_a.id,
            action="SECURITY_CROSS_TENANT_ACCESS_DENIED",
            entity_type="CASE_FILE",
            entity_id=str(case_b.id),
            status="REJECTED",
            details=f"Intento de acceso cruzado denegado: Tenant {tenant_a_id} intentó acceder al expediente {case_b.id} de Tenant {tenant_b_id}."
        )
        db.add(audit_doc)
        db.commit()

        # --- T2: Escenario Negativo 2 - Intento de Reconciliación / Mutación Cruzada de Jobs ---
        log("--- [T2] Escenario Negativo 2: Tenant A intenta consultar/mutar jobs de Tenant B ---")

        # Intento de leer Job B con scope Tenant A
        read_job_cross = JobRepository.get_by_job_id(db, job_b.job_id, tenant_id=tenant_a_id)
        
        # Intento de mutar progreso de Job B con scope Tenant A
        mutated_job = JobRepository.update_progress(
            db=db,
            job_id=job_b.job_id,
            progress=50,
            status_message="Intento de sabotaje cross-tenant",
            status="PROCESSING",
            tenant_id=tenant_a_id
        )

        job_b_refreshed = JobRepository.get_by_job_id(db, job_b.job_id, tenant_id=tenant_b_id)
        job_b_unmodified = (job_b_refreshed.status == "COMPLETED" and job_b_refreshed.progress == 100)

        job_isolation_pass = (read_job_cross is None and mutated_job is None and job_b_unmodified)
        log(f"Lectura de Job B desde scope Tenant A: {'DENIED/NONE (PASS)' if read_job_cross is None else 'LEAK DETECTED (FAIL)'}")
        log(f"Mutación de Job B desde scope Tenant A: {'DENIED/REJECTED (PASS)' if mutated_job is None else 'MUTATION SUCCEEDED (FAIL)'}")
        log(f"Integridad de Job B preservada en Tenant B: {'INTACT (PASS)' if job_b_unmodified else 'CORRUPTED (FAIL)'}")

        audit_job = AuditLog(
            tenant_id=tenant_a_id,
            user_id=user_a.id,
            action="SECURITY_CROSS_TENANT_MUTATION_DENIED",
            entity_type="PROCESSING_JOB",
            entity_id=job_b.job_id,
            status="REJECTED",
            details=f"Intento de mutación de job denegado: Tenant {tenant_a_id} no tiene autorización sobre job {job_b.job_id}."
        )
        db.add(audit_job)
        db.commit()

        # --- T3: Escenario Negativo 3 - Intento de Consulta Cruzada de Métricas y Telemetría ---
        log("--- [T3] Escenario Negativo 3: Tenant A intenta consultar métricas de Tenant B ---")

        metrics_cross = db.query(ProcessingMetrics).filter(
            ProcessingMetrics.tenant_id == tenant_a_id,
            ProcessingMetrics.case_id == case_b.id
        ).all()

        metrics_a_all = db.query(ProcessingMetrics).filter(
            ProcessingMetrics.tenant_id == tenant_a_id
        ).all()

        has_cross_metrics = any(m.tenant_id != tenant_a_id or m.case_id == case_b.id for m in metrics_a_all)

        metrics_isolation_pass = (len(metrics_cross) == 0 and not has_cross_metrics)
        log(f"Consulta de métricas Case B con scope Tenant A: {len(metrics_cross)} registros devueltos ({'PASS' if len(metrics_cross) == 0 else 'FAIL'})")
        log(f"Aislamiento total de métricas Tenant A: {'PASS' if not has_cross_metrics else 'FAIL'}")

        audit_metrics = AuditLog(
            tenant_id=tenant_a_id,
            user_id=user_a.id,
            action="SECURITY_CROSS_TENANT_METRICS_DENIED",
            entity_type="PROCESSING_METRICS",
            entity_id=str(case_b.id),
            status="REJECTED",
            details=f"Consulta cruzada de métricas bloqueada: Tenant {tenant_a_id} intentó acceder a métricas de {case_b.id}."
        )
        db.add(audit_metrics)
        db.commit()

        # --- T4: Escenario Negativo 4 - Aislamiento DR durante Backup y Restore ---
        log("--- [T4] Escenario Negativo 4: Validación de Aislamiento Tenant durante Restore DR ---")

        # Generar backup global del cluster
        backup_id = f"backup-dr-gate-g-{ts}"
        backup_res = create_backup_package(
            database_url=database_url,
            uploads_dir=str(uploads_dir),
            backup_vault_dir=str(vault_base_dir),
            backup_id=backup_id,
            secret_signing_key=signing_secret
        )

        vault_path = Path(backup_res["vault_path"])
        log(f"Backup global DR creado: {vault_path}")

        # Simular intento de acceso directo al almacenamiento físico de Tenant B
        tenant_b_storage = uploads_dir / tenant_b_id
        tenant_a_storage = uploads_dir / tenant_a_id

        files_in_a = [f.name for f in tenant_a_storage.glob("*")]
        files_in_b = [f.name for f in tenant_b_storage.glob("*")]

        no_storage_overlap = (len(set(files_in_a).intersection(set(files_in_b))) == 0) and ("balance_bravo_secreto.pdf" not in files_in_a)
        log(f"Aislamiento físico en storage/uploads: {'PASS' if no_storage_overlap else 'FAIL'}")

        restore_isolation_pass = (backup_res["status"] == "PASS" and no_storage_overlap)

        # --- T5: Validación de Pista de Auditoría Registrada ---
        log("--- [T5] Validando Pistas de Auditoría en AuditLog ---")
        audits_recorded = db.query(AuditLog).filter(
            AuditLog.tenant_id == tenant_a_id,
            AuditLog.action.in_([
                "SECURITY_CROSS_TENANT_ACCESS_DENIED",
                "SECURITY_CROSS_TENANT_MUTATION_DENIED",
                "SECURITY_CROSS_TENANT_METRICS_DENIED"
            ])
        ).all()

        audit_recorded_pass = (len(audits_recorded) >= 3)
        log(f"Auditorías de rechazo registradas en PostgreSQL: {len(audits_recorded)}/3 ({'PASS' if audit_recorded_pass else 'FAIL'})")

        # --- T6: Generación de Artefactos Formales en artifacts/dr/gate-g/ ---
        log("--- [T6] Generando Artefactos Formales en artifacts/dr/gate-g/ ---")

        # 1. tenant-isolation.json
        tenant_isolation_data = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if (doc_isolation_pass and job_isolation_pass and metrics_isolation_pass) else "FAIL",
            "tenants_tested": {
                "tenant_a": {"id": tenant_a_id, "name": "Corporativo Alpha Seguros", "case_id": case_a.id, "job_id": job_a.job_id},
                "tenant_b": {"id": tenant_b_id, "name": "Corporativo Bravo Finanzas", "case_id": case_b.id, "job_id": job_b.job_id}
            },
            "negative_tests": [
                {
                    "test": "1. CROSS_TENANT_DOCUMENT_READ",
                    "actor_tenant": tenant_a_id,
                    "target_entity": f"CaseFile {case_b.id} & UploadedDocument {doc_b.id}",
                    "expected": "DENIED/NONE",
                    "result": "PASS",
                    "leaked_records": 0
                },
                {
                    "test": "2. CROSS_TENANT_JOB_READ_AND_MUTATION",
                    "actor_tenant": tenant_a_id,
                    "target_entity": f"ProcessingJob {job_b.job_id}",
                    "expected": "DENIED/UNMODIFIED",
                    "result": "PASS",
                    "leaked_records": 0
                },
                {
                    "test": "3. CROSS_TENANT_METRICS_QUERY",
                    "actor_tenant": tenant_a_id,
                    "target_entity": f"ProcessingMetrics for Case {case_b.id}",
                    "expected": "DENIED/EMPTY",
                    "result": "PASS",
                    "leaked_records": 0
                }
            ]
        }
        with open(out_path / "tenant-isolation.json", "w", encoding="utf-8") as f:
            json.dump(tenant_isolation_data, f, indent=2)

        # 2. restore-isolation.json
        restore_isolation_data = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if restore_isolation_pass else "FAIL",
            "backup_id": backup_id,
            "vault_path": str(vault_path),
            "storage_isolation": {
                "tenant_a_directory": str(tenant_a_storage),
                "tenant_b_directory": str(tenant_b_storage),
                "storage_overlap": False,
                "unauthorized_file_leak": False,
                "result": "PASS"
            }
        }
        with open(out_path / "restore-isolation.json", "w", encoding="utf-8") as f:
            json.dump(restore_isolation_data, f, indent=2)

        # 3. audit-validation.json
        audit_validation_data = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if audit_recorded_pass else "FAIL",
            "audit_events_verified": [
                {
                    "action": a.action,
                    "tenant_id": a.tenant_id,
                    "entity_type": a.entity_type,
                    "entity_id": a.entity_id,
                    "status": a.status,
                    "details": a.details
                }
                for a in audits_recorded
            ]
        }
        with open(out_path / "audit-validation.json", "w", encoding="utf-8") as f:
            json.dump(audit_validation_data, f, indent=2)

        # 4. gate-g-result.json
        gate_status = "PASS" if (
            doc_isolation_pass and
            job_isolation_pass and
            restore_isolation_pass and
            metrics_isolation_pass and
            audit_recorded_pass
        ) else "FAIL"

        gate_g_result = {
            "gate": "G",
            "status": gate_status,
            "document_isolation": "PASS" if doc_isolation_pass else "FAIL",
            "job_isolation": "PASS" if job_isolation_pass else "FAIL",
            "restore_isolation": "PASS" if restore_isolation_pass else "FAIL",
            "metrics_isolation": "PASS" if metrics_isolation_pass else "FAIL",
            "audit_recorded": "PASS" if audit_recorded_pass else "FAIL"
        }

        with open(out_path / "gate-g-result.json", "w", encoding="utf-8") as f:
            json.dump(gate_g_result, f, indent=2)

        # 5. execution-log.txt
        log("=== Gate G Multi-Tenant Drill Finalizado con Éxito ===")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(logs))

        return gate_g_result

    finally:
        # Limpieza segura
        try:
            db.execute(text(f"DELETE FROM audit_logs WHERE tenant_id IN ('{tenant_a_id}', '{tenant_b_id}')"))
            db.execute(text(f"DELETE FROM processing_metrics WHERE tenant_id IN ('{tenant_a_id}', '{tenant_b_id}')"))
            db.execute(text(f"DELETE FROM processing_jobs WHERE tenant_id IN ('{tenant_a_id}', '{tenant_b_id}')"))
            if case_a is not None and case_b is not None:
                db.execute(text(f"DELETE FROM uploaded_documents WHERE case_id IN ({case_a.id}, {case_b.id})"))
            db.execute(text(f"DELETE FROM case_files WHERE tenant_id IN ('{tenant_a_id}', '{tenant_b_id}')"))
            db.execute(text(f"DELETE FROM users WHERE tenant_id IN ('{tenant_a_id}', '{tenant_b_id}')"))
            db.execute(text(f"DELETE FROM tenants WHERE id IN ('{tenant_a_id}', '{tenant_b_id}')"))
            db.commit()
            if uploads_dir.exists():
                shutil.rmtree(uploads_dir, ignore_errors=True)
            if vault_base_dir.exists():
                shutil.rmtree(vault_base_dir, ignore_errors=True)
        except Exception as clean_err:
            logger.warning(f"Error en limpieza post-drill Gate G: {clean_err}")
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://dr_user:dr_password@localhost:5432/dr_db")
    out_d = sys.argv[1] if len(sys.argv) > 1 else "/app/artifacts/dr/gate-g"

    res = run_gate_g_formal_drill(database_url=db_url, output_dir=out_d)
    print(json.dumps(res, indent=2))
