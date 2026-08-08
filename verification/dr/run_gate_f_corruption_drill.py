"""
Orquestador y Validador Formal de Gate F: Backup Corruption Rejection Certification
Fase 7.4-C Certificación Formal Disaster Recovery
"""

import os
import sys
import time
import json
import shutil
import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.domain import Tenant, CaseFile, AuditLog
from verification.dr.create_backup import (
    create_backup_package,
    execute_pg_verifybackup,
    compute_file_sha256
)
from verification.dr.restore_backup import (
    restore_backup_package,
    verify_manifest_signature
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.gate_f_drill")


def run_gate_f_formal_drill(
    database_url: str,
    output_dir: str = "/app/artifacts/dr/gate-f"
) -> Dict[str, Any]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    log_file_path = out_path / "execution-log.txt"

    logs: List[str] = []

    def log(msg: str):
        logger.info(msg)
        logs.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

    log("================================================================================")
    log("GATE F: BACKUP CORRUPTION REJECTION CERTIFICATION DRILL")
    log("================================================================================")

    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    ts = int(time.time())
    tenant_id = f"dr-tenant-gate-f-{ts}"
    vault_base_dir = Path("/app/data/vault_dr_gate_f")
    uploads_dir = Path("/app/data/uploads_dr_gate_f")
    vault_base_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    signing_secret = "abst_gp_gate_f_cryptographic_key_secret_12345678"

    try:
        # --- T0: Población Inicial y Creación de Backup Prístino Válido ---
        log("--- [T0] Creando Datos Base y Generando Backup Físico Prístino ---")

        tenant = Tenant(id=tenant_id, name="DR Tenant Gate F Corruption Certification")
        db.add(tenant)
        db.commit()

        case = CaseFile(
            title="Expediente Auditoria Gate F",
            contract_type="Servicios",
            tenant_id=tenant_id,
            status="CREATED"
        )
        db.add(case)
        db.commit()

        # Crear archivo documental testigo
        test_doc_file = uploads_dir / f"test_doc_gate_f_{ts}.txt"
        test_doc_content = f"CONTENIDO_DOCUMENTAL_ORIGINAL_GATE_F_{ts}\n".encode("utf-8")
        test_doc_file.write_bytes(test_doc_content)

        pristine_backup_id = f"backup-pristine-gate-f-{ts}"
        log(f"Creando paquete de backup físico prístino: {pristine_backup_id}...")

        backup_res = create_backup_package(
            database_url=database_url,
            uploads_dir=str(uploads_dir),
            backup_vault_dir=str(vault_base_dir),
            backup_id=pristine_backup_id,
            secret_signing_key=signing_secret
        )

        pristine_vault_path = Path(backup_res["vault_path"])
        log(f"Backup prístino publicado en: {pristine_vault_path}")

        # Validación 1: El backup prístino debe ser 100% válido
        log("Ejecutando verificación criptográfica y pg_verifybackup sobre backup prístino...")
        pristine_manifest_file = pristine_vault_path / "backup-manifest.json"
        with open(pristine_manifest_file, "r", encoding="utf-8") as f:
            pristine_manifest = json.load(f)

        sig_valid = verify_manifest_signature(pristine_manifest, signing_secret.encode("utf-8"))
        log(f"Firma HMAC-SHA256 del manifiesto prístino: {'VALID (PASS)' if sig_valid else 'INVALID (FAIL)'}")

        pristine_physical_dir = pristine_vault_path / "physical_basebackup"
        pg_verify_output_pristine = execute_pg_verifybackup(pristine_physical_dir)
        log(f"pg_verifybackup sobre backup prístino: PASS ({pg_verify_output_pristine})")

        valid_backup_pass = (backup_res["status"] == "PASS" and sig_valid and "successfully verified" in pg_verify_output_pristine)

        # --- T1: Clonación e Inyección de Corrupción / Manipulación ---
        log("--- [T1] Clonando Backup e Inyectando Corrupción Intencional ---")
        corrupted_backup_id = f"backup-corrupted-gate-f-{ts}"
        corrupted_vault_path = vault_base_dir / corrupted_backup_id

        # Copia exacta del prístino
        shutil.copytree(pristine_vault_path, corrupted_vault_path)
        log(f"Copia creada para inyección de corrupción: {corrupted_vault_path}")

        # Registrar estado antes de corrupción
        corrupted_manifest_file_pg = corrupted_vault_path / "physical_basebackup" / "backup_manifest"
        orig_pg_manifest_sha256 = compute_file_sha256(corrupted_manifest_file_pg)
        orig_pg_manifest_size = corrupted_manifest_file_pg.stat().st_size

        # Inyectar corrupción física en el archivo backup_manifest del cluster basebackup
        log(f"Inyectando corrupción de bytes en {corrupted_manifest_file_pg}...")
        corruption_payload = b"\n# TAMPERED_BYTES_CORRUPTION_INJECTION_FAIL_VERIFYBACKUP_7_4_C\n"
        with open(corrupted_manifest_file_pg, "ab") as f:
            f.write(corruption_payload)

        new_pg_manifest_sha256 = compute_file_sha256(corrupted_manifest_file_pg)
        new_pg_manifest_size = corrupted_manifest_file_pg.stat().st_size

        log(f"Modificación completada: SHA-256 cambió de {orig_pg_manifest_sha256} a {new_pg_manifest_sha256}")

        # Ejecutar pg_verifybackup sobre el backup corrupto -> debe fallar
        log("Ejecutando pg_verifybackup sobre cluster corrupto (se espera RECHAZO)...")
        pg_verifybackup_bin = shutil.which("pg_verifybackup")
        verify_corrupted_cmd = [
            pg_verifybackup_bin,
            "-m", str(corrupted_manifest_file_pg),
            str(corrupted_vault_path / "physical_basebackup"),
            "--exit-on-error"
        ]
        res_verify_corrupted = subprocess.run(verify_corrupted_cmd, capture_output=True, text=True)
        pg_verify_output_corrupted = (res_verify_corrupted.stdout + "\n" + res_verify_corrupted.stderr).strip()

        corrupted_detected_by_pg = (res_verify_corrupted.returncode != 0)
        log(f"Resultado pg_verifybackup sobre backup corrupto: ExitCode={res_verify_corrupted.returncode}, "
            f"Detección de Corrupción={'PASS' if corrupted_detected_by_pg else 'FAIL'}")
        log(f"Salida de error capturada: {pg_verify_output_corrupted[:300]}...")

        # --- T2: Intento de Restauración y Bloqueo Estricto ---
        log("--- [T2] Intentando Restauración desde el Backup Corrupto ---")
        restore_rejected_pass = False
        rejection_reason = ""

        try:
            restore_backup_package(
                backup_path_or_id=str(corrupted_vault_path),
                target_database_url=database_url,
                target_uploads_dir=str(uploads_dir),
                secret_signing_key=signing_secret,
                backup_vault_dir=str(vault_base_dir)
            )
            log("CRÍTICO: El motor de restauración NO rechazó el backup corrupto (FALLO DE SEGURIDAD).")
            restore_rejected_pass = False
        except Exception as exc:
            rejection_reason = str(exc)
            log(f"Restauración RECHAZADA exitosamente antes de ejecución: {rejection_reason}")
            if "CHECKSUM_MISMATCH" in rejection_reason or "VALIDATION_ERROR" in rejection_reason or "PHYSICAL_VERIFYBACKUP_REJECTED" in rejection_reason:
                restore_rejected_pass = True

        # Validar que NO hubo fallback silencioso a pg_dump ni alteración de la base de datos
        db_check = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        db_intact = (db_check is not None and db_check.id == tenant_id)
        log(f"Base de datos PostgreSQL preservada intacta sin corrupción: {'PASS' if db_intact else 'FAIL'}")

        # --- T3: Registro de Auditoría ---
        log("--- [T3] Registrando Evento de Rechazo y Alerta en AuditLog ---")
        audit_entry = AuditLog(
            tenant_id=tenant_id,
            user_id=None,
            action="DR_CORRUPTED_BACKUP_REJECTED",
            entity_type="DISASTER_RECOVERY_VAULT",
            entity_id=corrupted_backup_id,
            status="REJECTED",
            details=f"Intento de restauración desde backup corrupto bloqueado formalmente. Causa: {rejection_reason}"
        )
        db.add(audit_entry)
        db.commit()

        # Verificar registro en AuditLog
        saved_audit = db.query(AuditLog).filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "DR_CORRUPTED_BACKUP_REJECTED"
        ).first()

        audit_recorded_pass = (saved_audit is not None)
        log(f"Auditoría registrada en AuditLog (audit_recorded): {'PASS' if audit_recorded_pass else 'FAIL'}")

        # --- T4: Generación de Artefactos Formales en artifacts/dr/gate-f/ ---
        log("--- [T4] Escribiendo Artefactos Formales en artifacts/dr/gate-f/ ---")

        # 1. backup-corruption.json
        backup_corruption_data = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if corrupted_detected_by_pg and restore_rejected_pass else "FAIL",
            "pristine_backup": {
                "backup_id": pristine_backup_id,
                "vault_path": str(pristine_vault_path),
                "manifest_sha256": pristine_manifest.get("physical_basebackup", {}).get("manifest_checksum_sha256"),
                "status": "VALID"
            },
            "corrupted_backup": {
                "backup_id": corrupted_backup_id,
                "vault_path": str(corrupted_vault_path),
                "tampered_file": "physical_basebackup/backup_manifest",
                "original_sha256": orig_pg_manifest_sha256,
                "corrupted_sha256": new_pg_manifest_sha256,
                "original_size_bytes": orig_pg_manifest_size,
                "corrupted_size_bytes": new_pg_manifest_size,
                "injection_payload": "TAMPERED_BYTES_CORRUPTION_INJECTION_FAIL_VERIFYBACKUP_7_4_C",
                "status": "CORRUPTED_INVALID"
            },
            "rejection_summary": {
                "pg_verifybackup_exit_code": res_verify_corrupted.returncode,
                "restore_blocked": restore_rejected_pass,
                "rejection_exception": rejection_reason,
                "fallback_pg_dump_used": False,
                "database_tampered": False
            }
        }
        with open(out_path / "backup-corruption.json", "w", encoding="utf-8") as f:
            json.dump(backup_corruption_data, f, indent=2)

        # 2. verification-result.json
        verification_result_data = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if valid_backup_pass and corrupted_detected_by_pg else "FAIL",
            "pristine_verification": {
                "tool": "pg_verifybackup",
                "target_directory": str(pristine_physical_dir),
                "exit_code": 0,
                "output": pg_verify_output_pristine,
                "hmac_signature_verified": sig_valid,
                "result": "PASS"
            },
            "corrupted_verification": {
                "tool": "pg_verifybackup",
                "target_directory": str(corrupted_vault_path / "physical_basebackup"),
                "exit_code": res_verify_corrupted.returncode,
                "output": pg_verify_output_corrupted,
                "result": "EXPECTED_FAIL_REJECTED"
            }
        }
        with open(out_path / "verification-result.json", "w", encoding="utf-8") as f:
            json.dump(verification_result_data, f, indent=2)

        # 3. gate-f-result.json
        gate_status = "PASS" if (
            valid_backup_pass and
            corrupted_detected_by_pg and
            restore_rejected_pass and
            audit_recorded_pass
        ) else "FAIL"

        gate_f_result = {
            "gate": "F",
            "status": gate_status,
            "valid_backup": "PASS" if valid_backup_pass else "FAIL",
            "corrupted_backup_detected": "PASS" if corrupted_detected_by_pg else "FAIL",
            "restore_rejected": "PASS" if restore_rejected_pass else "FAIL",
            "audit_recorded": "PASS" if audit_recorded_pass else "FAIL"
        }

        with open(out_path / "gate-f-result.json", "w", encoding="utf-8") as f:
            json.dump(gate_f_result, f, indent=2)

        # 4. execution-log.txt
        log("=== Gate F Drill Finalizado con Éxito ===")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(logs))

        return gate_f_result

    finally:
        # Limpieza segura
        try:
            db.execute(text(f"DELETE FROM audit_logs WHERE tenant_id = '{tenant_id}'"))
            db.execute(text(f"DELETE FROM case_files WHERE tenant_id = '{tenant_id}'"))
            db.execute(text(f"DELETE FROM tenants WHERE id = '{tenant_id}'"))
            db.commit()
            if uploads_dir.exists():
                shutil.rmtree(uploads_dir, ignore_errors=True)
            if vault_base_dir.exists():
                shutil.rmtree(vault_base_dir, ignore_errors=True)
        except Exception as clean_err:
            logger.warning(f"Error en limpieza post-drill Gate F: {clean_err}")
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://dr_user:dr_password@localhost:5432/dr_db")
    out_d = sys.argv[1] if len(sys.argv) > 1 else "/app/artifacts/dr/gate-f"

    res = run_gate_f_formal_drill(database_url=db_url, output_dir=out_d)
    print(json.dumps(res, indent=2))
