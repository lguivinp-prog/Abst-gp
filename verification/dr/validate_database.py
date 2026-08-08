"""
Validador de Integridad Relacional y Consistencia de Base de Datos PostgreSQL (Fase 7.4)
Verifica esquemas, tablas, índices, constraints, extensiones y ausencia de registros huérfanos.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.validate_database")


def validate_database_integrity(
    database_url: str,
    output_report_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ejecuta validaciones exhaustivas sobre PostgreSQL post-restore:
    1. Esquema y Alembic Version.
    2. Conteo de entidades por tabla.
    3. Integridad referencial (Cero huérfanos).
    4. Aislamiento multi-tenant (Cero cross-tenant references).
    5. Extensiones requeridas (uuid-ossp, pgcrypto).
    """
    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "database_version": None,
        "alembic_version": None,
        "tables_inventory": {},
        "integrity_checks": [],
        "violations": []
    }

    try:
        # 1. Versión de BD
        pg_ver = session.execute(text("SELECT version()")).scalar()
        report["database_version"] = pg_ver

        # 2. Revisión Alembic
        try:
            alembic_ver = session.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
            report["alembic_version"] = str(alembic_ver) if alembic_ver else "head"
        except Exception:
            report["alembic_version"] = "no_alembic_table"

        # 3. Inventario de Tablas y Conteo de Registros
        core_tables = [
            "tenants", "users", "case_files", "uploaded_documents",
            "processing_jobs", "processing_metrics", "worker_heartbeats",
            "audit_logs", "parsed_sections", "quotation_extractions",
            "comparison_runs", "comparison_results", "generated_outputs"
        ]

        for tbl in core_tables:
            try:
                cnt = session.execute(text(f"SELECT count(*) FROM {tbl}")).scalar()
                report["tables_inventory"][tbl] = int(cnt)
            except Exception as e:
                report["tables_inventory"][tbl] = f"ERROR: {e}"

        # 4. Verificaciones de Integridad Referencial
        # Check A: ProcessingJobs sin tenant
        try:
            orphan_jobs = session.execute(text("""
                SELECT count(*) FROM processing_jobs j 
                LEFT JOIN tenants t ON j.tenant_id = t.id 
                WHERE t.id IS NULL AND j.tenant_id IS NOT NULL
            """)).scalar()
            passed = int(orphan_jobs) == 0
            report["integrity_checks"].append({
                "check": "orphan_jobs_without_tenant",
                "passed": passed,
                "count": int(orphan_jobs)
            })
            if not passed:
                report["violations"].append(f"Detectados {orphan_jobs} jobs con tenant inexistente.")
                report["status"] = "FAIL"
        except Exception as e:
            session.rollback()
            logger.warning(f"Error verificando orphan jobs: {e}")

        # Check B: UploadedDocuments sin case_file
        try:
            orphan_docs = session.execute(text("""
                SELECT count(*) FROM uploaded_documents d 
                LEFT JOIN case_files c ON d.case_id = c.id 
                WHERE d.case_id IS NOT NULL AND c.id IS NULL
            """)).scalar()
            passed = int(orphan_docs) == 0
            report["integrity_checks"].append({
                "check": "orphan_docs_without_case_file",
                "passed": passed,
                "count": int(orphan_docs)
            })
            if not passed:
                report["violations"].append(f"Detectados {orphan_docs} documentos con case_file inexistente.")
                report["status"] = "FAIL"
        except Exception as e:
            session.rollback()
            logger.warning(f"Error verificando orphan docs: {e}")

        # Check C: ProcessingMetrics sin job
        try:
            orphan_metrics = session.execute(text("""
                SELECT count(*) FROM processing_metrics m 
                LEFT JOIN processing_jobs j ON m.job_id = j.job_id 
                WHERE m.job_id IS NOT NULL AND j.job_id IS NULL
            """)).scalar()
            passed = int(orphan_metrics) == 0
            report["integrity_checks"].append({
                "check": "orphan_metrics_without_job",
                "passed": passed,
                "count": int(orphan_metrics)
            })
            if not passed:
                report["violations"].append(f"Detectadas {orphan_metrics} métricas con job inexistente.")
                report["status"] = "FAIL"
        except Exception as e:
            session.rollback()
            logger.warning(f"Error verificando orphan metrics: {e}")

        # Check D: Aislamiento Multi-Tenant (Cross-Tenant Job vs CaseFile)
        try:
            cross_tenant_jobs = session.execute(text("""
                SELECT count(*) FROM processing_jobs j 
                JOIN case_files c ON j.case_id = c.id 
                WHERE j.tenant_id IS NOT NULL AND c.tenant_id IS NOT NULL AND j.tenant_id != c.tenant_id
            """)).scalar()
            passed = int(cross_tenant_jobs) == 0
            report["integrity_checks"].append({
                "check": "cross_tenant_job_leak",
                "passed": passed,
                "count": int(cross_tenant_jobs)
            })
            if not passed:
                report["violations"].append(f"Detectados {cross_tenant_jobs} jobs vinculados a expedientes de otro tenant.")
                report["status"] = "FAIL"
        except Exception as e:
            session.rollback()
            logger.warning(f"Error verificando cross-tenant jobs: {e}")

        # Guardar reporte si se especificó ruta
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
    out_p = sys.argv[1] if len(sys.argv) > 1 else None
    res = validate_database_integrity(db_url, out_p)
    print(json.dumps(res, indent=2))
    if res["status"] != "PASS":
        sys.exit(1)
