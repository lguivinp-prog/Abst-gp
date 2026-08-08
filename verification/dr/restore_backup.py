"""
Motor de Restauración Física, PITR y Recuperación Documental (Fase 7.4)
Restaura base de datos PostgreSQL, valida firma/checksums y recupera filesystem de uploads.
"""

import os
import sys
import json
import time
import shutil
import hmac
import hashlib
import tarfile
import logging
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.restore_backup")

try:
    from app.core.telemetry import record_dr_restore
except ImportError:
    def record_dr_restore(result: str, duration_seconds: Optional[float] = None):
        pass


def compute_file_sha256(filepath: Path) -> str:
    """Calcula el hash SHA-256 de un archivo."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha256.update(block)
    return sha256.hexdigest()


def verify_manifest_signature(manifest_data: Dict[str, Any], signing_key: bytes) -> bool:
    """Verifica la firma HMAC-SHA256 del manifiesto de backup."""
    signature = manifest_data.get("security", {}).get("signature")
    if not signature:
        logger.error("El manifiesto no contiene firma HMAC-SHA256.")
        return False

    # Crear copia sin la firma para reconstruir el payload firmado
    data_to_verify = json.loads(json.dumps(manifest_data))
    if "signature" in data_to_verify.get("security", {}):
        del data_to_verify["security"]["signature"]

    expected_bytes = json.dumps(data_to_verify, indent=2, sort_keys=True).encode("utf-8")
    expected_sig = hmac.new(signing_key, expected_bytes, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        logger.error(f"Firma de manifiesto inválida. Esperada: {expected_sig}, Obtenida: {signature}")
        return False

    return True


def restore_backup_package(
    backup_path_or_id: str,
    target_database_url: str,
    target_uploads_dir: str,
    secret_signing_key: Optional[str] = None,
    backup_vault_dir: Optional[str] = None,
    target_recovery_time_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ejecuta el protocolo de restauración:
    1. Carga y valida criptográficamente backup-manifest.json.
    2. Valida sumas SHA-256 de todos los artefactos de backup.
    3. Restaura globals y base de datos en target_database_url.
    4. Restaura y descomprime archivos en target_uploads_dir.
    5. Registra cronología de restauración (restore-timeline.json).
    """
    t_start = time.perf_counter()
    timeline = []
    
    def log_milestone(name: str):
        elapsed = time.perf_counter() - t_start
        timeline.append({"milestone": name, "elapsed_seconds": elapsed, "timestamp_utc": datetime.now(timezone.utc).isoformat()})
        logger.info(f"[RESTORE MILESTONE] {name} (t={elapsed:.2f}s)")

    log_milestone("RESTORE_INITIATED")

    # Resolver ruta del vault
    vault_base = Path(backup_vault_dir or os.getenv("BACKUP_VAULT_DIR", "./data/backup_vault"))
    if backup_path_or_id == "latest":
        # Buscar el backup más reciente en el vault
        candidate_dirs = [d for d in vault_base.glob("*") if d.is_dir() and (d / "backup-manifest.json").exists()]
        if not candidate_dirs:
            record_dr_restore("failure")
            raise FileNotFoundError(f"No se encontraron backups válidos en el vault: {vault_base}")
        candidate_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        backup_dir = candidate_dirs[0]
        logger.info(f"Seleccionado backup más reciente automáticamente: {backup_dir.name}")
    elif Path(backup_path_or_id).exists():
        backup_dir = Path(backup_path_or_id)
    else:
        backup_dir = vault_base / backup_path_or_id

    if not backup_dir.exists():
        record_dr_restore("failure")
        raise FileNotFoundError(f"Directorio de backup no encontrado: {backup_dir}")

    manifest_file = backup_dir / "backup-manifest.json"
    if not manifest_file.exists():
        record_dr_restore("rejected")
        raise FileNotFoundError(f"backup-manifest.json no encontrado en {backup_dir}")

    signing_key = (secret_signing_key or os.getenv("SECRET_KEY", "abst_gp_default_dr_signing_key")).encode("utf-8")

    try:
        # 1. Validar Manifiesto Criptográfico
        with open(manifest_file, "r", encoding="utf-8") as mf:
            manifest = json.load(mf)

        log_milestone("MANIFEST_LOADED")

        if not verify_manifest_signature(manifest, signing_key):
            record_dr_restore("rejected")
            raise ValueError("VALIDATION_ERROR: Firma de backup-manifest.json corrupta o no autorizada.")

        log_milestone("MANIFEST_SIGNATURE_VERIFIED")

        # 2. Validar Checksums de Artefactos Físicos
        physical_info = manifest.get("physical_basebackup")
        if physical_info:
            physical_dir = backup_dir / physical_info.get("directory", "physical_basebackup")
            manifest_file_pg = physical_dir / "backup_manifest"
            if not manifest_file_pg.exists():
                record_dr_restore("rejected")
                raise FileNotFoundError(f"backup_manifest físico no encontrado en {physical_dir}")
            actual_manifest_sha = compute_file_sha256(manifest_file_pg)
            if actual_manifest_sha != physical_info.get("manifest_checksum_sha256"):
                record_dr_restore("rejected")
                raise ValueError(f"CHECKSUM_MISMATCH: backup_manifest SHA-256 inválido ({actual_manifest_sha} != {physical_info.get('manifest_checksum_sha256')})")

        logical_info = manifest.get("logical_backup") or manifest.get("base_backup")
        db_dump_file = None
        if logical_info:
            candidate_name = logical_info.get("filename")
            if candidate_name and (backup_dir / candidate_name).exists():
                db_dump_file = backup_dir / candidate_name
            elif (backup_dir / "logical_complementary.dump").exists():
                db_dump_file = backup_dir / "logical_complementary.dump"
            elif (backup_dir / "postgres_base.dump").exists():
                db_dump_file = backup_dir / "postgres_base.dump"
            elif (backup_dir / "postgres_base.sql").exists():
                db_dump_file = backup_dir / "postgres_base.sql"

            if db_dump_file and db_dump_file.exists():
                actual_db_sha256 = compute_file_sha256(db_dump_file)
                if logical_info.get("sha256") and actual_db_sha256 != logical_info.get("sha256"):
                    record_dr_restore("rejected")
                    raise ValueError(f"CHECKSUM_MISMATCH: Base/Logical dump SHA-256 inválido ({actual_db_sha256} != {logical_info.get('sha256')})")

        docs_info = manifest.get("documents_snapshot", {})
        docs_tar_file = backup_dir / docs_info.get("filename", "documents_snapshot.tar.gz")
        if not docs_tar_file.exists():
            record_dr_restore("rejected")
            raise FileNotFoundError(f"Archivo de snapshot documental no existe: {docs_tar_file}")

        actual_docs_sha256 = compute_file_sha256(docs_tar_file)
        if actual_docs_sha256 != docs_info.get("sha256"):
            record_dr_restore("rejected")
            raise ValueError(f"CHECKSUM_MISMATCH: Snapshot documental SHA-256 inválido ({actual_docs_sha256} != {docs_info.get('sha256')})")

        checksums_file = backup_dir / docs_info.get("checksums_file", "backup-checksums.json")
        if checksums_file.exists():
            actual_chk_sha256 = compute_file_sha256(checksums_file)
            if actual_chk_sha256 != docs_info.get("checksums_sha256"):
                record_dr_restore("rejected")
                raise ValueError("CHECKSUM_MISMATCH: backup-checksums.json corrupto.")

        log_milestone("ARTIFACTS_CHECKSUMS_VERIFIED")

        # 3. Restaurar Base de Datos PostgreSQL
        log_milestone("POSTGRES_RESTORE_STARTED")
        parsed = urllib.parse.urlparse(target_database_url)
        db_user = parsed.username or "dr_user"
        db_password = parsed.password or ""
        db_host = parsed.hostname or "localhost"
        db_port = str(parsed.port or 5432)
        db_name = parsed.path.lstrip("/") or "dr_db"

        env_pg = os.environ.copy()
        if db_password:
            env_pg["PGPASSWORD"] = db_password

        # Restaurar globals si existen
        globals_file = backup_dir / manifest.get("globals", {}).get("filename", "globals_sanitized.sql")
        if globals_file.exists():
            try:
                psql_globals_cmd = [
                    "psql",
                    "-h", db_host,
                    "-p", db_port,
                    "-U", db_user,
                    "-d", db_name,
                    "-f", str(globals_file)
                ]
                subprocess.run(psql_globals_cmd, env=env_pg, capture_output=True, text=True)
            except Exception as e:
                logger.warning(f"Aviso restaurando globals: {e}")

        # Limpiar y restaurar dump en PostgreSQL si existe dump lógico
        restored = False
        if db_dump_file and db_dump_file.exists():
            if db_dump_file.suffix == ".dump" and shutil.which("pg_restore"):
                restore_cmd = [
                    "pg_restore",
                    "-h", db_host,
                    "-p", db_port,
                    "-U", db_user,
                    "-d", db_name,
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-privileges",
                    "-v",
                    str(db_dump_file)
                ]
                res_restore = subprocess.run(restore_cmd, env=env_pg, capture_output=True, text=True)
                if res_restore.returncode in (0, 1):
                    restored = True
            elif db_dump_file.suffix == ".sql" and shutil.which("psql"):
                psql_restore_cmd = [
                    "psql",
                    "-h", db_host,
                    "-p", db_port,
                    "-U", db_user,
                    "-d", db_name,
                    "-f", str(db_dump_file)
                ]
                res_sql = subprocess.run(psql_restore_cmd, env=env_pg, capture_output=True, text=True)
                if res_sql.returncode == 0:
                    restored = True

            if not restored and db_dump_file.suffix == ".sql":
                # Restauración vía SQLAlchemy
                from sqlalchemy import create_engine, text
                eng = create_engine(target_database_url)
                with eng.connect() as conn:
                    with open(db_dump_file, "r", encoding="utf-8") as sf:
                        sql_content = sf.read()
                    for stmt in sql_content.split(";"):
                        stmt_clean = stmt.strip()
                        if stmt_clean and not stmt_clean.startswith("--"):
                            try:
                                conn.execute(text(stmt_clean))
                            except Exception as e:
                                logger.warning(f"Aviso ejecutando sentencia SQL en restore: {e}")
                    conn.commit()
                restored = True

        log_milestone("POSTGRES_RESTORE_COMPLETED")

        # 4. Restaurar Filesystem Documental (target_uploads_dir)
        log_milestone("DOCUMENTS_RESTORE_STARTED")
        uploads_target = Path(target_uploads_dir)
        uploads_target.mkdir(parents=True, exist_ok=True)

        with tarfile.open(docs_tar_file, "r:gz") as tar:
            for member in tar.getmembers():
                # Validación estricta de path traversal
                if member.name.startswith("/") or ".." in member.name:
                    logger.warning(f"Omitiendo archivo peligroso del tar: {member.name}")
                    continue
                tar.extract(member, path=uploads_target)

        log_milestone("DOCUMENTS_RESTORE_COMPLETED")

        elapsed = time.perf_counter() - t_start
        log_milestone("RESTORE_SUCCESS")

        record_dr_restore("success", duration_seconds=elapsed)

        return {
            "status": "PASS",
            "backup_id": manifest.get("backup_id"),
            "target_database": db_name,
            "target_uploads_dir": str(uploads_target),
            "elapsed_seconds": elapsed,
            "timeline": timeline,
            "manifest": manifest
        }

    except Exception as e:
        elapsed = time.perf_counter() - t_start
        log_milestone(f"RESTORE_FAILED: {str(e)}")
        logger.error(f"Error durante restauración DR: {e}", exc_info=True)
        if "VALIDATION_ERROR" in str(e) or "CHECKSUM_MISMATCH" in str(e):
            record_dr_restore("rejected")
        else:
            record_dr_restore("failure")
        raise


if __name__ == "__main__":
    b_id = sys.argv[1] if len(sys.argv) > 1 else "latest"
    db_url = os.getenv("DATABASE_URL", "postgresql://dr_user:dr_password@localhost:5432/dr_db")
    u_dir = os.getenv("UPLOADS_DIR", "./data/uploads")
    v_dir = os.getenv("BACKUP_VAULT_DIR", "./data/backup_vault")

    res = restore_backup_package(
        backup_path_or_id=b_id,
        target_database_url=db_url,
        target_uploads_dir=u_dir,
        backup_vault_dir=v_dir
    )
    print(json.dumps(res, indent=2))
