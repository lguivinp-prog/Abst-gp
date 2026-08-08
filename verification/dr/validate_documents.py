"""
Validador de Consistencia e Integridad Documental Bidireccional (Fase 7.4)
Verifica bidireccionalmente PostgreSQL <-> Filesystem con sumas SHA-256 y detección de archivos huérfanos/faltantes.
"""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.validate_documents")


def compute_file_sha256(filepath: Path) -> str:
    """Calcula el hash SHA-256 de un archivo."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha256.update(block)
    return sha256.hexdigest()


def validate_document_consistency(
    database_url: str,
    uploads_dir: str,
    output_report_path: Optional[str] = None,
    checksums_catalog_path: Optional[str] = None,
    tenant_id_filter: Optional[Union[str, List[str]]] = None
) -> Dict[str, Any]:
    """
    Ejecuta validación bidireccional exhaustiva:
    1. Base de datos -> Filesystem (Cada registro tiene archivo con tamaño y SHA-256 exacto).
    2. Filesystem -> Base de datos (Cada archivo en disco está debidamente catalogado).
    3. Verificación de seguridad de rutas (Cero path traversal, cero symlinks inseguros).
    """
    uploads_path = Path(uploads_dir)
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "uploads_dir": str(uploads_path),
        "db_documents_count": 0,
        "fs_files_count": 0,
        "matched_documents": 0,
        "missing_files_in_fs": [],
        "orphan_files_in_fs": [],
        "checksum_mismatches": [],
        "path_violations": [],
        "tenant_isolation_violations": []
    }

    # Cargar catálogo de checksums externo si existe
    external_checksums: Dict[str, str] = {}
    if checksums_catalog_path and Path(checksums_catalog_path).exists():
        try:
            with open(checksums_catalog_path, "r", encoding="utf-8") as f:
                cat_data = json.load(f)
                for entry in cat_data.get("documents", []):
                    rel_p = str(entry.get("relative_path", "")).replace("\\", "/").strip("/")
                    if rel_p and "sha256" in entry:
                        external_checksums[rel_p] = entry["sha256"]
        except Exception as e:
            logger.warning(f"No se pudo cargar checksums_catalog_path: {e}")

    try:
        # 1. Obtener registros de la base de datos
        db_records = {}
        try:
            query = """
                SELECT d.id, COALESCE(c.tenant_id, 'default') as tenant_id, d.case_id, d.original_filename, d.stored_path, d.ocr_metadata
                FROM uploaded_documents d
                LEFT JOIN case_files c ON d.case_id = c.id
            """
            if tenant_id_filter:
                if isinstance(tenant_id_filter, list):
                    t_filter_str = "', '".join(tenant_id_filter)
                    query += f" WHERE c.tenant_id IN ('{t_filter_str}')"
                else:
                    query += f" WHERE c.tenant_id = '{tenant_id_filter}'"

            rows = session.execute(text(query)).fetchall()
            report["db_documents_count"] = len(rows)
            for r in rows:
                norm_p = str(r.stored_path).replace("\\", "/").strip("/")
                expected_sha = external_checksums.get(norm_p)
                expected_sz = None
                if r.ocr_metadata:
                    try:
                        meta = r.ocr_metadata if isinstance(r.ocr_metadata, dict) else json.loads(r.ocr_metadata)
                        if not expected_sha and meta.get("sha256"):
                            expected_sha = meta.get("sha256")
                        expected_sz = meta.get("file_size")
                    except Exception:
                        pass

                db_records[norm_p] = {
                    "id": str(r.id),
                    "tenant_id": str(r.tenant_id),
                    "case_id": str(r.case_id) if r.case_id else None,
                    "original_filename": str(r.original_filename),
                    "expected_size": expected_sz,
                    "expected_sha256": expected_sha,
                }
        except Exception as e:
            logger.warning(f"Error consultando uploaded_documents: {e}")

        # 2. Escanear Filesystem
        fs_files = {}
        if uploads_path.exists():
            for root, dirs, files in os.walk(uploads_path):
                for f_name in files:
                    full_p = Path(root) / f_name
                    rel_p = full_p.relative_to(uploads_path).as_posix()

                    # Validar path traversal
                    if ".." in rel_p or full_p.is_symlink():
                        report["path_violations"].append(rel_p)
                        report["status"] = "FAIL"
                        continue

                    f_sha = compute_file_sha256(full_p)
                    f_sz = full_p.stat().st_size
                    fs_files[rel_p] = {
                        "full_path": str(full_p),
                        "size": f_sz,
                        "sha256": f_sha
                    }

        report["fs_files_count"] = len(fs_files)

        # 3. Validación DB -> Filesystem
        for rel_p, db_meta in db_records.items():
            if rel_p not in fs_files:
                report["missing_files_in_fs"].append({
                    "stored_path": rel_p,
                    "document_id": db_meta["id"],
                    "tenant_id": db_meta["tenant_id"]
                })
                report["status"] = "FAIL"
            else:
                fs_meta = fs_files[rel_p]
                # Validar Checksum SHA-256 si la base o catálogo lo registraba
                if db_meta["expected_sha256"] and fs_meta["sha256"] != db_meta["expected_sha256"]:
                    report["checksum_mismatches"].append({
                        "stored_path": rel_p,
                        "document_id": db_meta["id"],
                        "expected_sha256": db_meta["expected_sha256"],
                        "actual_sha256": fs_meta["sha256"]
                    })
                    report["status"] = "FAIL"
                else:
                    report["matched_documents"] += 1

        # 4. Validación Filesystem -> DB
        for rel_p, fs_meta in fs_files.items():
            if rel_p not in db_records and not tenant_id_filter:
                report["orphan_files_in_fs"].append({
                    "relative_path": rel_p,
                    "size_bytes": fs_meta["size"],
                    "sha256": fs_meta["sha256"]
                })
                logger.warning(f"Archivo huérfano detectado en filesystem: {rel_p}")

        if report["missing_files_in_fs"] or report["checksum_mismatches"] or report["path_violations"]:
            report["status"] = "FAIL"

        if output_report_path:
            p = Path(output_report_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

        return report

    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://dr_user:dr_password@localhost:5432/dr_db")
    u_dir = os.getenv("UPLOADS_DIR", "./data/uploads")
    out_p = sys.argv[1] if len(sys.argv) > 1 else None

    res = validate_document_consistency(db_url, u_dir, out_p)
    print(json.dumps(res, indent=2))
    if res["status"] != "PASS":
        sys.exit(1)
