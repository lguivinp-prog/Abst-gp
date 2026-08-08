"""
Orquestador y Validador Formal de Gate D: Consistencia Documental, Storage y Vault Restore
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

from app.core.config import settings
from app.models.domain import Tenant, CaseFile, UploadedDocument, AuditLog
from verification.dr.create_backup import create_backup_package
from verification.dr.restore_backup import restore_backup_package
from verification.dr.validate_documents import validate_document_consistency, compute_file_sha256

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.gate_d_drill")


def run_gate_d_formal_drill(
    database_url: str,
    output_dir: str = "/app/artifacts/dr/gate-d",
    base_uploads_dir: str = "/app/data/uploads_dr_gate_d",
    base_vault_dir: str = "/app/data/vault_dr_gate_d"
) -> Dict[str, Any]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    log_file_path = out_path / "execution-log.txt"

    uploads_path = Path(base_uploads_dir)
    vault_path = Path(base_vault_dir)

    if uploads_path.exists():
        shutil.rmtree(uploads_path, ignore_errors=True)
    if vault_path.exists():
        shutil.rmtree(vault_path, ignore_errors=True)

    uploads_path.mkdir(parents=True, exist_ok=True)
    vault_path.mkdir(parents=True, exist_ok=True)

    logs: List[str] = []

    def log(msg: str):
        logger.info(msg)
        logs.append(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

    log("================================================================================")
    log("GATE D: DOCUMENT & STORAGE CONSISTENCY / VAULT RESTORE DRILL")
    log("================================================================================")

    engine = create_engine(database_url, connect_args={"connect_timeout": 10})
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    ts = int(time.time())
    tenant_alpha = f"dr-tenant-alpha-gate-d-{ts}"
    tenant_beta = f"dr-tenant-beta-gate-d-{ts}"
    drill_tenants = [tenant_alpha, tenant_beta]
    backup_id = f"vault-snapshot-gate-d-{ts}"

    doc_files: Dict[str, Path] = {}
    doc_expected_shas: Dict[str, str] = {}
    doc_expected_sizes: Dict[str, int] = {}
    created_doc_ids: List[int] = []

    try:
        # --- T0: Creación de Tenants, Casos y Documentos de Prueba ---
        log("--- [T0] Creando Tenants, Casos y Documentos con Checksums SHA-256 en SSOT ---")

        t_a = Tenant(id=tenant_alpha, name="DR Tenant Alpha (Gate D Consistency)")
        t_b = Tenant(id=tenant_beta, name="DR Tenant Beta (Gate D Multi-Tenant Isolation)")
        db.add_all([t_a, t_b])
        db.commit()

        case_a = CaseFile(
            title="Expediente Licitacion Alpha Gate D",
            contract_type="Bienes",
            tenant_id=tenant_alpha,
            status="CREATED"
        )
        case_b = CaseFile(
            title="Expediente Confidencial Beta Gate D",
            contract_type="Servicios",
            tenant_id=tenant_beta,
            status="CREATED"
        )
        db.add_all([case_a, case_b])
        db.commit()

        # Documentos para Tenant Alpha
        # 1. DOC_A: Válido
        file_a = uploads_path / f"doc_a_{tenant_alpha}.pdf"
        content_a = b"%PDF-1.4 Bases Administrativas Licitacion 001 Alpha 2026 - Oficial Integro"
        file_a.write_bytes(content_a)
        sha_a = hashlib.sha256(content_a).hexdigest()
        size_a = len(content_a)

        doc_a = UploadedDocument(
            case_id=case_a.id,
            document_type="requirement",
            original_filename="Bases_Administrativas_Alpha.pdf",
            stored_path=file_a.name,
            mime_type="application/pdf",
            processing_status="pending",
            ocr_metadata={"sha256": sha_a, "file_size": size_a}
        )

        # 2. DOC_B: Válido
        file_b = uploads_path / f"doc_b_{tenant_alpha}.pdf"
        content_b = b"%PDF-1.4 Oferta Tecnica y Economica Consorcio Proveedor Alpha - Completo"
        file_b.write_bytes(content_b)
        sha_b = hashlib.sha256(content_b).hexdigest()
        size_b = len(content_b)

        doc_b = UploadedDocument(
            case_id=case_a.id,
            document_type="proposal",
            original_filename="Oferta_Tecnica_Alpha.pdf",
            stored_path=file_b.name,
            mime_type="application/pdf",
            processing_status="pending",
            ocr_metadata={"sha256": sha_b, "file_size": size_b}
        )

        # 3. DOC_C: Alterado (Se creará prístino, luego se alterarán sus bytes)
        file_c = uploads_path / f"doc_c_{tenant_alpha}.pdf"
        content_c_pristine = b"%PDF-1.4 Carta de Garantia de Fiel Cumplimiento Alpha Original y Sellada"
        file_c.write_bytes(content_c_pristine)
        sha_c_pristine = hashlib.sha256(content_c_pristine).hexdigest()
        size_c_pristine = len(content_c_pristine)

        doc_c = UploadedDocument(
            case_id=case_a.id,
            document_type="guarantee",
            original_filename="Garantia_Alpha.pdf",
            stored_path=file_c.name,
            mime_type="application/pdf",
            processing_status="pending",
            ocr_metadata={"sha256": sha_c_pristine, "file_size": size_c_pristine}
        )

        # 4. DOC_D: Faltante (Se creará prístino, luego se eliminará físicamente)
        file_d = uploads_path / f"doc_d_{tenant_alpha}.pdf"
        content_d_pristine = b"%PDF-1.4 Cronograma de Entrega e Hitos de Pago Alpha 2026"
        file_d.write_bytes(content_d_pristine)
        sha_d_pristine = hashlib.sha256(content_d_pristine).hexdigest()
        size_d_pristine = len(content_d_pristine)

        doc_d = UploadedDocument(
            case_id=case_a.id,
            document_type="schedule",
            original_filename="Cronograma_Alpha.pdf",
            stored_path=file_d.name,
            mime_type="application/pdf",
            processing_status="pending",
            ocr_metadata={"sha256": sha_d_pristine, "file_size": size_d_pristine}
        )

        # Documento para Tenant Beta (Multi-tenancy isolation check)
        file_beta = uploads_path / f"doc_beta_{tenant_beta}.pdf"
        content_beta = b"%PDF-1.4 Documento Altamente Confidencial Tenant Beta - No Accesible Por Alpha"
        file_beta.write_bytes(content_beta)
        sha_beta = hashlib.sha256(content_beta).hexdigest()
        size_beta = len(content_beta)

        doc_beta = UploadedDocument(
            case_id=case_b.id,
            document_type="confidential",
            original_filename="Documento_Confidencial_Beta.pdf",
            stored_path=file_beta.name,
            mime_type="application/pdf",
            processing_status="pending",
            ocr_metadata={"sha256": sha_beta, "file_size": size_beta}
        )

        db.add_all([doc_a, doc_b, doc_c, doc_d, doc_beta])
        db.commit()

        created_doc_ids = [doc_a.id, doc_b.id, doc_c.id, doc_d.id, doc_beta.id]
        doc_files = {
            "DOC_A": file_a,
            "DOC_B": file_b,
            "DOC_C": file_c,
            "DOC_D": file_d,
            "DOC_BETA": file_beta
        }
        doc_expected_shas = {
            "DOC_A": sha_a,
            "DOC_B": sha_b,
            "DOC_C": sha_c_pristine,
            "DOC_D": sha_d_pristine,
            "DOC_BETA": sha_beta
        }
        doc_expected_sizes = {
            "DOC_A": size_a,
            "DOC_B": size_b,
            "DOC_C": size_c_pristine,
            "DOC_D": size_d_pristine,
            "DOC_BETA": size_beta
        }

        # Registrar auditoría
        audit_entry = AuditLog(
            tenant_id=tenant_alpha,
            user_id=None,
            action="GATE_D_DOCS_INITIALIZED",
            entity_type="document_catalog",
            entity_id=str(case_a.id),
            status="SUCCESS",
            details=json.dumps({
                "documents_count": 4,
                "tenant_alpha": tenant_alpha,
                "tenant_beta": tenant_beta
            })
        )
        db.add(audit_entry)
        db.commit()

        log(f"Documentos creados y registrados en PostgreSQL SSOT:")
        log(f"  - DOC_A (ID {doc_a.id}): SHA-256={sha_a}")
        log(f"  - DOC_B (ID {doc_b.id}): SHA-256={sha_b}")
        log(f"  - DOC_C (ID {doc_c.id}): SHA-256={sha_c_pristine}")
        log(f"  - DOC_D (ID {doc_d.id}): SHA-256={sha_d_pristine}")
        log(f"  - DOC_BETA (ID {doc_beta.id}): SHA-256={sha_beta}")

        # --- T1: Crear Snapshot Prístino en el Vault ---
        log("--- [T1] Creando Snapshot y Respaldo Criptográfico Prístino en el Vault ---")
        backup_pkg = create_backup_package(
            database_url=database_url,
            uploads_dir=str(uploads_path),
            backup_vault_dir=str(vault_path),
            backup_id=backup_id,
            generate_logical_complement=False
        )
        assert backup_pkg["status"] == "PASS", f"Fallo al crear backup en vault: {backup_pkg}"
        log(f"Snapshot en Vault creado exitosamente: {backup_id}")

        # Validación Prístina Inicial
        init_val = validate_document_consistency(
            database_url=database_url,
            uploads_dir=str(uploads_path),
            tenant_id_filter=drill_tenants
        )
        log(f"Validación Inicial Prístina: status={init_val['status']}, matched={init_val['matched_documents']}, missing={len(init_val['missing_files_in_fs'])}, mismatches={len(init_val['checksum_mismatches'])}")
        assert init_val["status"] == "PASS", f"Estado inicial debe ser PASS, obtenido: {init_val}"

        # --- T2: Simulación de Desastre 1 — Documento Faltante (DOC_D Eliminado Físicamente) ---
        log("--- [T2] Simulando Desastre 1: Eliminación Física de DOC_D del Almacenamiento ---")
        file_d.unlink()
        assert not file_d.exists(), "DOC_D debe haber sido eliminado físicamente de disco"

        missing_val = validate_document_consistency(
            database_url=database_url,
            uploads_dir=str(uploads_path),
            tenant_id_filter=drill_tenants
        )
        log(f"Resultado Validación tras eliminar DOC_D: status={missing_val['status']}, missing_count={len(missing_val['missing_files_in_fs'])}")

        missing_detected = (
            missing_val["status"] == "FAIL" and
            len(missing_val["missing_files_in_fs"]) >= 1 and
            any(m["stored_path"] == file_d.name for m in missing_val["missing_files_in_fs"])
        )
        log(f"Detección de Documento Faltante (missing_document_detection): {'PASS' if missing_detected else 'FAIL'}")

        # --- T3: Simulación de Desastre 2 — Modificación / Corrupción de Bytes (DOC_C Alterado) ---
        log("--- [T3] Simulando Desastre 2: Alteración de Bytes y Tampering en DOC_C ---")
        tampered_content = b"%PDF-1.4 TAMPERED_CORRUPTED_BYTES_UNAUTHORIZED_ALTERATION_GATE_D"
        file_c.write_bytes(tampered_content)
        tampered_sha = hashlib.sha256(tampered_content).hexdigest()
        log(f"DOC_C alterado en disco: nuevo SHA-256={tampered_sha} vs esperado={sha_c_pristine}")

        checksum_val = validate_document_consistency(
            database_url=database_url,
            uploads_dir=str(uploads_path),
            tenant_id_filter=drill_tenants
        )
        log(f"Resultado Validación tras alterar DOC_C: status={checksum_val['status']}, mismatches_count={len(checksum_val['checksum_mismatches'])}")

        checksum_mismatch_detected = (
            checksum_val["status"] == "FAIL" and
            len(checksum_val["checksum_mismatches"]) >= 1 and
            any(m["stored_path"] == file_c.name and m["expected_sha256"] == sha_c_pristine for m in checksum_val["checksum_mismatches"])
        )
        log(f"Detección de Checksum Mismatch (checksum_validation): {'PASS' if checksum_mismatch_detected else 'FAIL'}")

        # Guardar evidencia de fallos detectados
        storage_validation_report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "disaster_state_validation": {
                "missing_document_detected": missing_detected,
                "missing_files": missing_val["missing_files_in_fs"],
                "checksum_tampering_detected": checksum_mismatch_detected,
                "checksum_mismatches": checksum_val["checksum_mismatches"]
            }
        }

        # --- T4: Restauración desde el Vault / Snapshot ---
        log("--- [T4] Ejecutando Restauración Documental desde Vault Snapshot ---")
        t_restore_start = time.perf_counter()

        # Restaurar snapshot documental desde el paquete del Vault
        snapshot_tar = vault_path / backup_id / "documents_snapshot.tar.gz"
        assert snapshot_tar.exists(), f"El archivo {snapshot_tar} debe existir en el Vault"

        import tarfile
        with tarfile.open(snapshot_tar, "r:gz") as tar:
            tar.extractall(path=uploads_path)

        restore_duration = time.perf_counter() - t_restore_start
        log(f"Archivos restaurados desde Vault en {restore_duration:.4f}s")

        # Re-validación post-restore
        post_restore_val = validate_document_consistency(
            database_url=database_url,
            uploads_dir=str(uploads_path),
            tenant_id_filter=drill_tenants,
            output_report_path=str(out_path / "document-integrity.json")
        )
        log(f"Validación Post-Restore: status={post_restore_val['status']}, matched={post_restore_val['matched_documents']}, missing={len(post_restore_val['missing_files_in_fs'])}, mismatches={len(post_restore_val['checksum_mismatches'])}")

        # Validaciones de consistencia física individual
        restored_sha_a = compute_file_sha256(file_a)
        restored_sha_b = compute_file_sha256(file_b)
        restored_sha_c = compute_file_sha256(file_c)
        restored_sha_d = compute_file_sha256(file_d)
        restored_sha_beta = compute_file_sha256(file_beta)

        all_shas_match = (
            restored_sha_a == sha_a and
            restored_sha_b == sha_b and
            restored_sha_c == sha_c_pristine and
            restored_sha_d == sha_d_pristine and
            restored_sha_beta == sha_beta
        )
        log(f"Verificación individual SHA-256 Post-Restore:")
        log(f"  - DOC_A: {restored_sha_a == sha_a} ({restored_sha_a})")
        log(f"  - DOC_B: {restored_sha_b == sha_b} ({restored_sha_b})")
        log(f"  - DOC_C: {restored_sha_c == sha_c_pristine} ({restored_sha_c})")
        log(f"  - DOC_D: {restored_sha_d == sha_d_pristine} ({restored_sha_d})")
        log(f"  - DOC_BETA: {restored_sha_beta == sha_beta} ({restored_sha_beta})")

        vault_restore_pass = (
            post_restore_val["status"] == "PASS" and
            len(post_restore_val["missing_files_in_fs"]) == 0 and
            len(post_restore_val["checksum_mismatches"]) == 0 and
            all_shas_match
        )
        log(f"Resultado Restauración Vault (vault_restore): {'PASS' if vault_restore_pass else 'FAIL'}")

        # --- T5: Validación Estricta de Tenant Ownership y Aislamiento ---
        log("--- [T5] Validando Aislamiento Multi-Tenant (Cero Cross-Tenant Access) ---")
        
        # Consulta de documentos del Tenant Alpha
        docs_alpha = db.query(UploadedDocument).join(CaseFile, UploadedDocument.case_id == CaseFile.id).filter(CaseFile.tenant_id == tenant_alpha).all()
        doc_ids_alpha = [d.id for d in docs_alpha]
        log(f"Documentos recuperados para Tenant Alpha: {doc_ids_alpha}")

        # Consulta de documentos del Tenant Beta
        docs_beta = db.query(UploadedDocument).join(CaseFile, UploadedDocument.case_id == CaseFile.id).filter(CaseFile.tenant_id == tenant_beta).all()
        doc_ids_beta = [d.id for d in docs_beta]
        log(f"Documentos recuperados para Tenant Beta: {doc_ids_beta}")

        # Comprobar aislamiento cruzado
        no_cross_tenant = (
            len(docs_alpha) == 4 and
            len(docs_beta) == 1 and
            doc_beta.id not in doc_ids_alpha and
            all(d_id not in doc_ids_beta for d_id in [doc_a.id, doc_b.id, doc_c.id, doc_d.id])
        )
        log(f"Aislamiento Multi-Tenant sin fuga cruzada: {'PASS' if no_cross_tenant else 'FAIL'}")
        tenant_integrity_pass = no_cross_tenant

        # --- T6: Generación de Artefactos Formales ---
        log("--- [T6] Escribiendo Artefactos Formales en artifacts/dr/gate-d/ ---")

        # 1. storage-validation.json
        storage_validation_report["post_restore_validation"] = post_restore_val
        storage_validation_report["status"] = "PASS" if vault_restore_pass else "FAIL"
        with open(out_path / "storage-validation.json", "w", encoding="utf-8") as f:
            json.dump(storage_validation_report, f, indent=2)

        # 2. vault-restore.json
        vault_restore_report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if vault_restore_pass else "FAIL",
            "backup_id": backup_id,
            "restore_duration_seconds": restore_duration,
            "total_documents_restored": len(created_doc_ids),
            "restored_documents": [
                {
                    "name": "DOC_A",
                    "filename": file_a.name,
                    "tenant_id": tenant_alpha,
                    "sha256": restored_sha_a,
                    "expected_sha256": sha_a,
                    "match": (restored_sha_a == sha_a)
                },
                {
                    "name": "DOC_B",
                    "filename": file_b.name,
                    "tenant_id": tenant_alpha,
                    "sha256": restored_sha_b,
                    "expected_sha256": sha_b,
                    "match": (restored_sha_b == sha_b)
                },
                {
                    "name": "DOC_C",
                    "filename": file_c.name,
                    "tenant_id": tenant_alpha,
                    "sha256": restored_sha_c,
                    "expected_sha256": sha_c_pristine,
                    "match": (restored_sha_c == sha_c_pristine)
                },
                {
                    "name": "DOC_D",
                    "filename": file_d.name,
                    "tenant_id": tenant_alpha,
                    "sha256": restored_sha_d,
                    "expected_sha256": sha_d_pristine,
                    "match": (restored_sha_d == sha_d_pristine)
                },
                {
                    "name": "DOC_BETA",
                    "filename": file_beta.name,
                    "tenant_id": tenant_beta,
                    "sha256": restored_sha_beta,
                    "expected_sha256": sha_beta,
                    "match": (restored_sha_beta == sha_beta)
                }
            ]
        }
        with open(out_path / "vault-restore.json", "w", encoding="utf-8") as f:
            json.dump(vault_restore_report, f, indent=2)

        # 3. gate-d-result.json
        gate_status = "PASS" if (
            missing_detected and
            checksum_mismatch_detected and
            vault_restore_pass and
            tenant_integrity_pass
        ) else "FAIL"

        gate_d_result = {
            "gate": "D",
            "status": gate_status,
            "missing_document_detection": "PASS" if missing_detected else "FAIL",
            "checksum_validation": "PASS" if checksum_mismatch_detected else "FAIL",
            "vault_restore": "PASS" if vault_restore_pass else "FAIL",
            "tenant_integrity": "PASS" if tenant_integrity_pass else "FAIL"
        }

        with open(out_path / "gate-d-result.json", "w", encoding="utf-8") as f:
            json.dump(gate_d_result, f, indent=2)

        # 4. execution-log.txt
        log("=== Gate D Drill Finalizado con Éxito ===")
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(logs))

        return gate_d_result

    finally:
        # Limpieza de base de datos
        try:
            db.execute(text(f"DELETE FROM audit_logs WHERE tenant_id IN ('{tenant_alpha}', '{tenant_beta}')"))
            if created_doc_ids:
                db.execute(text(f"DELETE FROM uploaded_documents WHERE id IN ({','.join(map(str, created_doc_ids))})"))
            db.execute(text(f"DELETE FROM case_files WHERE tenant_id IN ('{tenant_alpha}', '{tenant_beta}')"))
            db.execute(text(f"DELETE FROM tenants WHERE id IN ('{tenant_alpha}', '{tenant_beta}')"))
            db.commit()
        except Exception as clean_err:
            logger.warning(f"Error en limpieza DB post-drill: {clean_err}")
        finally:
            db.close()
            engine.dispose()

        # Limpieza de directorios temporales
        shutil.rmtree(uploads_path, ignore_errors=True)
        shutil.rmtree(vault_path, ignore_errors=True)


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://dr_user:dr_password@localhost:5432/dr_db")
    out_d = sys.argv[1] if len(sys.argv) > 1 else "/app/artifacts/dr/gate-d"

    res = run_gate_d_formal_drill(database_url=db_url, output_dir=out_d)
    print(json.dumps(res, indent=2))
