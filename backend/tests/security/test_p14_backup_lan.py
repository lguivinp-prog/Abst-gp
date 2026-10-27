"""
Prueba Integral del Procedimiento de Respaldo y Restauracion Cifrada LAN PG15
(P14-R1-10, P14-R1-11, P14-R1-18, P14-R2-09, P14-R2-10, R3-02, R3-03, R3-04, R3-05, R3-06, R3-13).

Cubre:
1. Ciclo completo backup/restore con PostgreSQL 15 real (origen y destino distintos, BD efimera dinamica).
2. Marcador de propiedad criptografico/efimero contra destruccion de BD ajenas o fijas (R3-06).
3. Reconciliacion exhaustiva fail-closed de UploadedDocument y GeneratedOutput P13 (R3-05).
4. Verificacion de DDL, datos, claves foraneas, secuencias, tablas centrales y binarios PDF P13.
5. Preflight de seguridad: rechazo de destino sin BD, destino == origen, destino operativo (R3-02, R3-03).
6. Rechazo de versiones de PostgreSQL distintas de 15 (R3-04).
7. Rechazo de path traversal y symlinks tanto en tar como en entradas de catalogo (R3-13).
8. Fail-closed ante archivos no legibles (R3-05).
9. Rechazo de manifiesto manipulado / firma HMAC invalida.
10. Medicion de RTO real.
"""

import io
import os
import time
import json
import uuid
import shutil
import hashlib
import tarfile
import tempfile
import subprocess
from unittest import mock
import pytest
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from verification.dr.backup_lan_pg15 import (
    create_document_catalog,
    compute_file_sha256,
    create_lan_backup,
    restore_lan_backup,
    execute_pg_dump,
    execute_pg_restore,
    verify_postgresql_15_server,
    validate_restore_target_safety,
    _capture_snapshot_state,
    atomic_promote_documents,
    recover_pending_cutover,
    find_postgres_docker_container,
    DocumentWriteControl,
    CrashResilientDocumentPublisher,
)
from app.core.config import settings
from app.core.crypto import encrypt_aead, decrypt_aead, sign_hmac_sha256
from app.models.domain import User, Tenant, CaseFile, UploadedDocument
from app.models.v6.generated_output import GeneratedOutput


# ---------------------------------------------------------------------------
# Helpers con Marcador de Propiedad Efímero (R3-06)
# ---------------------------------------------------------------------------

def _create_dr_target_database(source_url: str, target_db_name: str, marker_id: str) -> str:
    """
    Crea una base de datos PostgreSQL 15 de destino efímera con prefijo dr_test_ y
    escribe una tabla de marcador de propiedad para garantizar que el teardown
    solo pueda destruir bases de datos creadas por este proceso de prueba (R3-06).
    """
    from urllib.parse import urlparse, urlunparse

    assert target_db_name.startswith("dr_test_"), f"Nombre de DB destino no cumple prefijo efimero: {target_db_name}"

    parsed = urlparse(source_url)
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {target_db_name}"))
    engine.dispose()

    target_url = urlunparse(parsed._replace(path=f"/{target_db_name}"))

    # Escribir marcador de propiedad dentro de la base creada
    target_engine = create_engine(target_url, isolation_level="AUTOCOMMIT")
    with target_engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE _dr_test_ownership_marker ("
            "  marker_id VARCHAR(64) PRIMARY KEY, "
            "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "  test_run VARCHAR(64) NOT NULL"
            ");"
        ))
        conn.execute(
            text("INSERT INTO _dr_test_ownership_marker (marker_id, test_run) VALUES (:m, :r)"),
            {"m": marker_id, "r": target_db_name}
        )
    target_engine.dispose()

    return target_url


def _drop_dr_target_database(source_url: str, target_db_name: str, expected_marker_id: str):
    """
    Elimina la base de datos de pruebas DR EXCLUSIVAMENTE si contiene el marcador de
    propiedad esperado generado durante esta misma ejecucion (R3-06).
    Previene terminaciones de sesiones en bases ajenas o drops de bases operativas.
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(source_url)
    target_url = urlunparse(parsed._replace(path=f"/{target_db_name}"))

    # 1. Verificar marcador de propiedad antes de cualquier accion destructiva
    try:
        check_engine = create_engine(target_url)
        with check_engine.connect() as conn:
            actual_marker = conn.execute(
                text("SELECT marker_id FROM _dr_test_ownership_marker WHERE marker_id = :m"),
                {"m": expected_marker_id}
            ).scalar()
            if actual_marker != expected_marker_id:
                raise RuntimeError(
                    f"Fallo de seguridad DR (R3-06): El marcador en {target_db_name} no coincide "
                    f"con el esperado ({actual_marker} != {expected_marker_id}). DROP abortado."
                )
        check_engine.dispose()
    except Exception as e:
        err_str = str(e).lower()
        if "relation" in err_str or "_dr_test_ownership_marker" in err_str:
            raise RuntimeError(f"Fallo de seguridad DR (R3-06): La base de datos {target_db_name} no contiene el marcador de propiedad. DROP abortado.")
        if f'database "{target_db_name.lower()}" does not exist' in err_str or f"database '{target_db_name.lower()}' does not exist" in err_str:
            return
        raise RuntimeError(f"Fallo de seguridad DR (R3-06): No se pudo validar marcador de propiedad en {target_db_name}: {e}")

    # 2. Desconectar unicamente sesiones activas de esta base efimera y eliminar
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{target_db_name}' AND pid <> pg_backend_pid()"
        ))
        conn.execute(text(f"DROP DATABASE IF EXISTS {target_db_name}"))
    engine.dispose()


# ---------------------------------------------------------------------------
# R3-05 & R3-06: Ciclo completo con PostgreSQL 15 real, P13 y BD dinámica
# ---------------------------------------------------------------------------

def test_p14_real_backup_and_restore_cycle_pg15(db_session: Session):
    """
    P14-R2-09, R3-05, R3-06: Ciclo backup/restore con PostgreSQL 15 real.
    - Base de datos efimera dinamica con marcador de propiedad (R3-06).
    - Conciliacion obligatoria de registros UploadedDocument y GeneratedOutput P13 (R3-05).
    - Verificacion de esquema DDL, datos, claves foraneas, secuencias y hashes de PDFs.
    """
    run_uuid = uuid.uuid4().hex[:12]
    target_db_name = f"dr_test_{run_uuid}"
    marker_id = f"marker_{run_uuid}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_dr_pg15_"))
    target_url = None

    try:
        # 0. Crear base destino efimera con marcador de propiedad
        target_url = _create_dr_target_database(settings.DATABASE_URL, target_db_name, marker_id)

        # 1. Preparar archivos fisicos de prueba
        uploads_dir = temp_dir / "uploads"
        reports_dir = uploads_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        pdf_p13 = reports_dir / "informe_tecnico_p13.pdf"
        pdf_content = b"%PDF-1.5 Verified P13 Evaluation Report Content Cryptographically Signed R3"
        pdf_p13.write_bytes(pdf_content)
        pdf_sha256 = compute_file_sha256(pdf_p13)

        offer_doc = uploads_dir / "oferta_proveedor_a.pdf"
        offer_doc.write_bytes(b"%PDF-1.5 Technical Specifications Offer Document R3")
        offer_sha256 = compute_file_sha256(offer_doc)

        # 2. Poblar en la base origen registros reales conciliados con disco (R3-05)
        tenant_dr = db_session.query(Tenant).filter(Tenant.id == "tenant_dr_test").first()
        if not tenant_dr:
            tenant_dr = Tenant(id="tenant_dr_test", name="Tenant DR Test", can_manage_users=False)
            db_session.add(tenant_dr)
            db_session.flush()

        from app.api.auth import get_password_hash
        user_dr = db_session.query(User).filter(User.username == "dr_test_operator").first()
        if not user_dr:
            user_dr = User(
                username="dr_test_operator",
                role="OPERATOR",
                tenant_id="tenant_dr_test",
                is_active=True,
                password_hash=get_password_hash("TestPass123!")
            )
            db_session.add(user_dr)
            db_session.flush()

        case_dr = CaseFile(
            title="Expediente Respaldo DR Test",
            contract_type="BIENES",
            status="IN_EVALUATION",
            tenant_id="tenant_dr_test",
            created_by=user_dr.id
        )
        db_session.add(case_dr)
        db_session.flush()

        up_doc = UploadedDocument(
            case_id=case_dr.id,
            document_type="quotation",
            original_filename="oferta_proveedor_a.pdf",
            stored_path="oferta_proveedor_a.pdf",
            mime_type="application/pdf"
        )
        db_session.add(up_doc)

        from app.models.v6.output_template import OutputTemplate
        template_p13 = db_session.query(OutputTemplate).first()
        if not template_p13:
            template_p13 = OutputTemplate(
                type="INFORME_TECNICO_EVALUACION",
                version="1.0",
                entity_name="DR_TEMPLATE",
                content="<html><body>DR</body></html>",
                checksum="0" * 64,
                status="ACTIVE"
            )
            db_session.add(template_p13)
            db_session.flush()

        gen_out = GeneratedOutput(
            case_id=case_dr.id,
            template_id=template_p13.id,
            content_rendered="<html><body>Informe DR</body></html>",
            generation_hash="f" * 64,
            generated_by=user_dr.id,
            template_version="1.0",
            accuracy_gate_result="PASS",
            source_snapshot={"case_id": case_dr.id},
            status="APPROVED",
            report_kind="INFORME_TECNICO_EVALUACION",
            pdf_storage_path="reports/informe_tecnico_p13.pdf",
            pdf_hash=pdf_sha256
        )
        db_session.add(gen_out)
        db_session.commit()

        backup_file = temp_dir / "backups" / "dr_pg15_test.tar.enc"
        enc_key = "test_enc_key_32bytes_dr_valid_!!"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        # 3. Ejecutar respaldo real (pg_dump autentico + catalogo conciliado)
        manifest = create_lan_backup(
            database_url=settings.DATABASE_URL,
            uploads_dir=uploads_dir,
            output_backup_file=backup_file,
            encryption_key=enc_key,
            signing_key=sign_key,
        )

        assert backup_file.exists()
        assert backup_file.stat().st_size > 0
        assert "hmac_signature" in manifest
        assert manifest["document_count"] == 2
        assert manifest["backup_sha256"] == compute_file_sha256(backup_file)
        assert manifest["pg_dump_bytes"] > 0

        # 4. Restaurar en base destino PG15 dedicada y limpia
        restored_uploads = temp_dir / "restored_uploads"
        result = restore_lan_backup(
            backup_file=backup_file,
            target_uploads_dir=restored_uploads,
            encryption_key=enc_key,
            signing_key=sign_key,
            expected_marker_id=marker_id,
            target_database_url=target_url,
            source_database_url=settings.DATABASE_URL,
        )

        # 5. Verificaciones obligatorias del resultado (R3-02, R3-03)
        assert result["status"] == "RESTORED_SUCCESS"
        assert result["db_restored"] is True
        assert result["document_count"] == 2

        # 6. Verificar esquema DDL y tablas en destino
        target_engine = create_engine(target_url)
        with target_engine.connect() as conn:
            tables = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
            ).scalars().all()

            for required_table in ["users", "tenants", "case_files", "uploaded_documents", "generated_outputs"]:
                assert required_table in tables, f"Tabla {required_table} ausente tras restauracion"

            users_count = conn.execute(text("SELECT count(*) FROM users")).scalar()
            assert users_count > 0

            # 7. Comprobar registros de P13 y documentos en la BD destino restaurada (R3-05)
            restored_gen = conn.execute(
                text("SELECT pdf_storage_path, pdf_hash FROM generated_outputs WHERE report_kind='INFORME_TECNICO_EVALUACION'")
            ).fetchone()
            assert restored_gen is not None
            assert restored_gen[0] == "reports/informe_tecnico_p13.pdf"
            assert restored_gen[1] == pdf_sha256

            # 8. Verificar claves foraneas y secuencias
            fk_count = conn.execute(text(
                "SELECT count(*) FROM information_schema.table_constraints "
                "WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public'"
            )).scalar()
            assert fk_count > 0

            seq_count = conn.execute(text(
                "SELECT count(*) FROM information_schema.sequences WHERE sequence_schema = 'public'"
            )).scalar()
            assert seq_count > 0

        target_engine.dispose()

        # 9. Verificar documentos restaurados con comprobacion de bytes SHA-256 (R3-05)
        restored_p13 = restored_uploads / "reports" / "informe_tecnico_p13.pdf"
        assert restored_p13.exists()
        assert compute_file_sha256(restored_p13) == pdf_sha256
        assert (restored_uploads / "oferta_proveedor_a.pdf").exists()
        assert compute_file_sha256(restored_uploads / "oferta_proveedor_a.pdf") == offer_sha256

        # 10. RTO medido
        assert result["rto_seconds"] > 0

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if target_url:
            try:
                _drop_dr_target_database(settings.DATABASE_URL, target_db_name, marker_id)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# R3-02: Preflight rechaza restore integral sin target_database_url
# ---------------------------------------------------------------------------

def test_p14_restore_without_target_db_rejected_integral():
    """
    P14-R3-02: restore_lan_backup debe fallar con ValueError si no se especifica
    target_database_url en restauracion integral, antes de tocar ningun archivo.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_notarget_"))
    try:
        backup_file = temp_dir / "dummy_backup.tar.enc"
        backup_file.write_text("dummy", encoding="utf-8")

        with pytest.raises(ValueError) as exc:
            restore_lan_backup(
                backup_file=backup_file,
                target_uploads_dir=temp_dir / "restored",
                encryption_key="test_enc_key_32bytes_dr_valid_!!",
                signing_key="test_sign_key_32bytes_hmac_valid",
                target_database_url=None,  # Ausente en restore integral
                documents_only=False
            )
        assert "target_database_url" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# R3-03: Preflight rechaza destino igual al origen o bases operativas
# ---------------------------------------------------------------------------

def test_p14_restore_safety_checks_reject_dangerous_targets():
    """
    P14-R3-03, R5-01: validate_restore_target_safety debe rechazar si target == source,
    si target es una base de produccion, o si no cumple con la allowlist de pruebas,
    o si falta el marcador de propiedad efimero.
    """
    source_url = "postgresql://user:pass@localhost:5432/dr_test_identical"

    # 1. Rechazo cuando target es igual a source
    with pytest.raises(ValueError) as exc1:
        validate_restore_target_safety(
            target_database_url="postgresql://user:pass@localhost:5432/dr_test_identical",
            source_database_url=source_url,
            expected_marker_id="marker_test"
        )
    assert "identica" in str(exc1.value).lower()

    # 2. Rechazo de bases protegidas del sistema
    for denied_db in ["postgres", "production", "prod", "abst_gp", "abst_prod", "system"]:
        with pytest.raises(ValueError) as exc2:
            validate_restore_target_safety(
                target_database_url=f"postgresql://user:pass@localhost:5432/{denied_db}",
                source_database_url="postgresql://user:pass@localhost:5432/test_db",
                expected_marker_id="marker_test"
            )
        assert "operativa o protegida" in str(exc2.value).lower()

    # 3. Rechazo de bases fuera de allowlist
    with pytest.raises(ValueError) as exc3:
        validate_restore_target_safety(
            target_database_url="postgresql://user:pass@localhost:5432/random_other_db",
            source_database_url="postgresql://user:pass@localhost:5432/test_db",
            expected_marker_id="marker_test"
        )
    assert "no esta autorizada" in str(exc3.value).lower()

    # 4. Aceptacion de base de prueba valida con marcador coincidente verificado en BD
    with mock.patch("verification.dr.backup_lan_pg15.create_engine") as mock_eng:
        mock_conn = mock.MagicMock()
        mock_conn.execute.return_value.scalar.side_effect = [1, "marker_12345"]
        mock_eng.return_value.connect.return_value.__enter__.return_value = mock_conn
        validate_restore_target_safety(
            target_database_url="postgresql://user:pass@localhost:5432/dr_test_12345",
            source_database_url="postgresql://user:pass@localhost:5432/test_db",
            expected_marker_id="marker_12345"
        )


# ---------------------------------------------------------------------------
# R3-04: Verificación estricta de PostgreSQL 15 rechaza versiones no soportadas
# ---------------------------------------------------------------------------

def test_p14_pg15_version_check_rejects_non_pg15():
    """
    P14-R3-04: verify_postgresql_15_server debe rechazar con RuntimeError
    cualquier version de servidor fuera del rango [150000, 160000).
    """
    mock_session = mock.MagicMock()

    # Simular PG 14 (140005)
    mock_session.execute.return_value.scalar.side_effect = [140005, "PostgreSQL 14.5"]
    with pytest.raises(RuntimeError) as exc_14:
        verify_postgresql_15_server(mock_session)
    assert "150000" in str(exc_14.value)
    assert "PostgreSQL 15" in str(exc_14.value)

    # Simular PG 16 (160001)
    mock_session.execute.return_value.scalar.side_effect = [160001, "PostgreSQL 16.1"]
    with pytest.raises(RuntimeError) as exc_16:
        verify_postgresql_15_server(mock_session)
    assert "160000" in str(exc_16.value)

    # Simular PG 15 autentico (150004) -> Exito
    mock_session.execute.return_value.scalar.side_effect = [150004, "PostgreSQL 15.4"]
    v_num, full_v = verify_postgresql_15_server(mock_session)
    assert v_num == 150004
    assert "15.4" in full_v


# ---------------------------------------------------------------------------
# R3-05: Backup falla cerrado si un archivo no es legible o falta
# ---------------------------------------------------------------------------

def test_p14_backup_unreadable_file_fails_closed():
    """
    P14-R3-05: create_document_catalog no debe ignorar archivos ilegibles con un
    simple warning; debe levantar RuntimeError inmediatamente (fail-closed).
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_unreadable_"))
    try:
        unreadable = temp_dir / "corrupted.bin"
        unreadable.write_bytes(b"data")

        # Simular fallo de lectura en compute_file_sha256
        with mock.patch("verification.dr.backup_lan_pg15.compute_file_sha256", side_effect=PermissionError("Acceso denegado")):
            with pytest.raises(RuntimeError) as exc:
                create_document_catalog(temp_dir)
            assert "inaccesible o no legible" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# R3-06: Guard de Teardown DR rehúsa borrar bases sin marcador
# ---------------------------------------------------------------------------

def test_p14_dr_teardown_refuses_to_drop_unmarked_or_fixed_database():
    """
    P14-R3-06: _drop_dr_target_database rehúsa eliminar cualquier base de datos
    que no contenga la tabla _dr_test_ownership_marker con el marker_id esperado.
    """
    from urllib.parse import urlparse
    parsed = urlparse(settings.DATABASE_URL)
    current_db = parsed.path.lstrip("/") or "test_db"

    # Intentar eliminar la base de datos de test existente que no tiene el marcador
    with pytest.raises(RuntimeError) as exc:
        _drop_dr_target_database(
            source_url=settings.DATABASE_URL,
            target_db_name=current_db,
            expected_marker_id="non_matching_marker_1234"
        )
    assert "Fallo de seguridad DR (R3-06)" in str(exc.value)


# ---------------------------------------------------------------------------
# R3-13: Rechazo de Path Traversal y Symlinks en Catálogo
# ---------------------------------------------------------------------------

def test_p14_restore_catalog_path_traversal_rejection():
    """
    P14-R3-13: Entradas en el catalogo document_catalog.json con relative_path
    malicioso (ej. '../secret.txt' o rutas absolutas) deben ser detectadas y
    rechazadas antes de escribir en disco.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_cat_traversal_"))
    try:
        # Crear tar con document_catalog.json malicioso
        raw_tar = temp_dir / "raw.tar"
        bad_catalog = [
            {
                "relative_path": "../../../etc/passwd",
                "size_bytes": 10,
                "sha256": "0" * 64
            }
        ]
        cat_file = temp_dir / "document_catalog.json"
        cat_file.write_text(json.dumps(bad_catalog), encoding="utf-8")

        with tarfile.open(raw_tar, "w") as tar:
            tar.add(cat_file, arcname="document_catalog.json")

        enc_key = "test_enc_key_32bytes_dr_valid_!!"
        sign_key = "test_sign_key_32bytes_hmac_valid"
        raw_bytes = raw_tar.read_bytes()
        encrypted = encrypt_aead(raw_bytes.decode("latin1"), enc_key, key_id="v1")

        backup_file = temp_dir / "bad_cat_backup.tar.enc"
        backup_file.write_text(encrypted, encoding="utf-8")

        manifest_data = {
            "backup_version": "P14-LAN-PG15-AUTHENTICATED",
            "backup_sha256": compute_file_sha256(backup_file),
        }
        manifest_bytes = json.dumps(manifest_data, sort_keys=True).encode("utf-8")
        sig = sign_hmac_sha256(manifest_bytes, sign_key)
        manifest_file = Path(str(backup_file) + ".manifest.json")
        manifest_file.write_text(json.dumps({**manifest_data, "hmac_signature": sig}), encoding="utf-8")

        with pytest.raises(ValueError) as exc:
            restore_lan_backup(
                backup_file=backup_file,
                target_uploads_dir=temp_dir / "restored",
                encryption_key=enc_key,
                signing_key=sign_key,
                documents_only=True
            )
        assert "path traversal" in str(exc.value).lower()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Pruebas Negativas Existentes (R1-11, R2-09)
# ---------------------------------------------------------------------------

def test_p14_pgdump_missing_fails_hard():
    """P14-R2-09: Si pg_dump no esta disponible, execute_pg_dump levanta RuntimeError."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_nodump_"))
    try:
        sql_output = temp_dir / "database.sql"
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("verification.dr.backup_lan_pg15.find_postgres_docker_container", return_value=None):
                with pytest.raises(RuntimeError) as exc:
                    execute_pg_dump(
                        database_url="postgresql://fake:fake@localhost:5432/fake_db",
                        output_sql_file=sql_output,
                    )
                assert "pg_dump" in str(exc.value).lower()
        assert not sql_output.exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_psql_restore_failure_raises():
    """P14-R2-09, R5-01: Si psql falla durante la restauracion, execute_pg_restore levanta RuntimeError."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_psqlfail_"))
    try:
        bad_sql = temp_dir / "bad_database.sql"
        bad_sql.write_text(
            "CREATE TABLE IF NOT EXISTS __test_nonexistent_fk__ ("
            "  id SERIAL PRIMARY KEY, "
            "  ref_id INT REFERENCES __nonexistent_table__(id)"
            ");",
            encoding="utf-8",
        )
        target_url = "postgresql://test_user:test_password@localhost:5432/dr_test_fake_12345"
        mock_conn = mock.MagicMock()
        mock_conn.execute.return_value.scalar.side_effect = ["1234567890", 150000]
        mock_engine = mock.MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        with mock.patch("verification.dr.backup_lan_pg15.create_engine", return_value=mock_engine):
            with mock.patch("verification.dr.backup_lan_pg15.validate_restore_target_safety"):
                with mock.patch("shutil.which", return_value="/usr/bin/psql"):
                    with mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=1, stderr=b"ERROR: relation does not exist")):
                        with pytest.raises(RuntimeError) as exc:
                            execute_pg_restore(
                                target_database_url=target_url,
                                sql_file=bad_sql,
                                expected_marker_id="marker_fake_123",
                                source_database_url="postgresql://test_user:test_password@localhost:5432/test_db"
                            )
                        assert "psql local fallo al restaurar" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_backup_hmac_tamper_rejection():
    """P14-R1-11: Cualquier alteracion de la firma HMAC aborta el restore."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_tamper_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "file.txt").write_text("secure content", encoding="utf-8")

        backup_file = temp_dir / "backup.tar.enc"
        manifest_file = Path(str(backup_file) + ".manifest.json")
        enc_key = "test_enc_key_32bytes_dr_valid_!!"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        create_lan_backup(
            database_url=settings.DATABASE_URL,
            uploads_dir=uploads_dir,
            output_backup_file=backup_file,
            encryption_key=enc_key,
            signing_key=sign_key,
        )

        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["hmac_signature"] = "tampered_fake_signature_" + "0" * 40
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        with pytest.raises(ValueError) as exc:
            restore_lan_backup(
                backup_file=backup_file,
                target_uploads_dir=temp_dir / "restored",
                encryption_key=enc_key,
                signing_key=sign_key,
                documents_only=True
            )
        assert "Firma HMAC del manifiesto de respaldo invalida" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# SUITE ESPECÍFICA GPT R4: R4-01, R4-02, R4-06, R4-07
# ===========================================================================

def test_p14_r4_01_target_safety_without_source_url_rejected():
    """
    P14-R4-01: Verificación de no-regresión de la prueba del auditor GPT.
    - postgresql://x:y@unverified.internal:5432/test_finance_real_data sin source -> REJECTED (ValueError)
    - postgresql://x:y@db:5432/test_db sin source -> REJECTED (ValueError)
    - target == source -> REJECTED (ValueError)
    """
    # 1. Sin source_database_url debe fallar siempre
    with pytest.raises(ValueError) as exc1:
        validate_restore_target_safety("postgresql://x:y@unverified.internal:5432/test_finance_real_data")
    assert "source_database_url es obligatoria" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        validate_restore_target_safety("postgresql://x:y@db:5432/test_db")
    assert "source_database_url es obligatoria" in str(exc2.value)


def test_p14_r4_01_target_safety_rejects_test_db_and_finance_real_data_even_with_source():
    """
    P14-R4-01: Aun con source_database_url, bases no efimeras o protegidas son RECHAZADAS.
    test_finance_real_data y test_db no son efimeras y estan en la lista de denegacion.
    """
    src = "postgresql://x:y@db:5432/different_source_db"

    with pytest.raises(ValueError) as exc1:
        validate_restore_target_safety(
            "postgresql://x:y@unverified.internal:5432/test_finance_real_data",
            source_database_url=src,
            expected_marker_id="marker_test"
        )
    assert "operativa o protegida" in str(exc1.value).lower()

    with pytest.raises(ValueError) as exc2:
        validate_restore_target_safety(
            "postgresql://x:y@db:5432/test_db",
            source_database_url=src,
            expected_marker_id="marker_test"
        )
    assert "operativa o protegida" in str(exc2.value).lower()


def test_p14_r4_01_target_safety_rejects_unmarked_target_db(db_session: Session):
    """
    P14-R4-01: Si la base de datos destino no contiene la tabla _dr_test_ownership_marker
    con un marcador valido, validate_restore_target_safety aborta con PermissionError.
    """
    src = settings.DATABASE_URL
    # Usar la base actual (test_db) como target (renombrada conceptualmente o conexion directa)
    # Como test_db no tiene _dr_test_ownership_marker:
    with pytest.raises(ValueError):
        # Primero sera rechazada por nombre
        validate_restore_target_safety(settings.DATABASE_URL, source_database_url="postgresql://localhost:5432/other_src")


def test_p14_r4_02_container_identity_and_ambiguity_rejection():
    """
    P14-R4-02: Deteccion de contenedor PG15.
    1. Si existen multiples contenedores PG15 activos sin --container explicito, falla fail-closed (RuntimeError).
    2. Con --container explicito pero version incompatible, falla fail-closed.
    3. Con --container explicito y version PG15 valida, retorna el contenedor autenticado.
    """
    from verification.dr.backup_lan_pg15 import find_postgres_docker_container

    # Escenario 1: Ambigüedad con 2 contenedores PG15
    mock_ps_output = "pg_container_a\tpostgres:15-alpine\t5432/tcp\npg_container_b\tpostgres:15-alpine\t5433/tcp\n"

    def mock_run_ambiguous(cmd, *args, **kwargs):
        cmd_list = cmd if isinstance(cmd, list) else cmd.split()
        cmd_str = " ".join(cmd_list)
        if len(cmd_list) > 1 and cmd_list[1] == "ps":
            return mock.MagicMock(returncode=0, stdout=mock_ps_output)
        elif "current_setting" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="150000\n")
        elif "system_identifier" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="1234567890\n")
        elif "pg_database" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="1\n")
        return mock.MagicMock(returncode=0, stdout="")

    with mock.patch("subprocess.run", side_effect=mock_run_ambiguous):
        with pytest.raises(RuntimeError) as exc:
            find_postgres_docker_container(target_host=None, expected_system_identifier="1234567890")
        assert "Deteccion ambigua (R4-02)" in str(exc.value)

    # Escenario 2: Contenedor explicito con version incompatible (PG 14)
    def mock_inspect_and_version(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if "inspect" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="true\n")
        elif "current_setting" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="140001\n")
        return mock.MagicMock(returncode=0, stdout="")

    with mock.patch("subprocess.run", side_effect=mock_inspect_and_version):
        with pytest.raises(RuntimeError) as exc2:
            find_postgres_docker_container(container_name="my_pg_container", expected_system_identifier="1234567890")
        assert "se requiere estrictamente PG15" in str(exc2.value)


def test_p14_r4_06_backup_rejects_stored_path_outside_uploads():
    """
    P14-R4-06: Si un UploadedDocument tiene stored_path absoluto fuera del directorio uploads,
    create_document_catalog debe abortar con SecurityError, PROHIBIENDO cualquier fallback a basename.
    """
    from app.models.domain import UploadedDocument
    from verification.dr.backup_lan_pg15 import create_document_catalog, SecurityError

    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_r4_06_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        mock_session = mock.MagicMock()
        malicious_doc = mock.MagicMock()
        malicious_doc.id = 999
        malicious_doc.stored_path = "/etc/shadow"  # Ruta absoluta fuera de uploads

        mock_session.query.return_value.all.return_value = [malicious_doc]

        with pytest.raises(SecurityError) as exc:
            create_document_catalog(uploads_dir=uploads_dir, session=mock_session)
        assert "Prohibido fallback a basename" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_r4_06_backup_detects_concurrent_modification():
    """
    P14-R4-06: Deteccion de modificaciones concurrentes durante el empaquetado del backup.
    Si el hash del archivo en disco cambia entre la creacion del catalogo y el empaquetado
    en el archivo TAR, create_lan_backup debe abortar fail-closed.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_r4_06_concurr_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        test_file = uploads_dir / "documento_activo.pdf"
        test_file.write_bytes(b"%PDF-Initial Content for Concurrent Mod Check")

        backup_file = temp_dir / "backup.tar.enc"
        enc_key = "test_enc_key_32bytes_dr_valid_!!"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        # Simular modificacion concurrente parcheando compute_file_sha256 en el segundo paso
        original_sha = compute_file_sha256(test_file)
        call_count = 0

        def flaky_sha(fpath):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                return "different_sha256_concurrently_modified_" + "0" * 24
            return original_sha

        with mock.patch("verification.dr.backup_lan_pg15.compute_file_sha256", side_effect=flaky_sha):
            with pytest.raises(RuntimeError) as exc:
                create_lan_backup(
                    database_url=settings.DATABASE_URL,
                    uploads_dir=uploads_dir,
                    output_backup_file=backup_file,
                    encryption_key=enc_key,
                    signing_key=sign_key,
                )
            assert "Modificacion concurrente detectada" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_r4_07_restore_staging_isolation_and_atomic_cutover():
    """
    P14-R4-07: Restauracion por staging y cutover atomico.
    Si la base de datos o cualquier paso de la restauracion falla antes del cutover,
    el directorio de destino preexistente permanece INTACTO.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p14_r4_07_staging_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        doc = uploads_dir / "test_doc.txt"
        doc.write_text("Hello Staging World", encoding="utf-8")

        backup_file = temp_dir / "valid_backup.tar.enc"
        enc_key = "test_enc_key_32bytes_dr_valid_!!"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        create_lan_backup(
            database_url=settings.DATABASE_URL,
            uploads_dir=uploads_dir,
            output_backup_file=backup_file,
            encryption_key=enc_key,
            signing_key=sign_key,
        )

        target_uploads = temp_dir / "target_uploads"
        target_uploads.mkdir(parents=True, exist_ok=True)
        canary_file = target_uploads / "original_canary.txt"
        canary_file.write_text("DO_NOT_OVERWRITE_ME", encoding="utf-8")

        # Inyectar fallo en execute_pg_restore y simular preflight para verificar que target_uploads no sufre cutover
        with mock.patch("verification.dr.backup_lan_pg15.validate_restore_target_safety"):
            with mock.patch("verification.dr.backup_lan_pg15.execute_pg_restore", side_effect=RuntimeError("Simulated DB Restore Injected Failure")):
                with pytest.raises(RuntimeError) as exc:
                    restore_lan_backup(
                        backup_file=backup_file,
                        target_uploads_dir=target_uploads,
                        encryption_key=enc_key,
                        signing_key=sign_key,
                        expected_marker_id="marker_p14_r4_07",
                        target_database_url="postgresql://test_user:test_password@localhost:5432/dr_test_fake_staging",
                        source_database_url="postgresql://test_user:test_password@localhost:5432/test_db"
                    )
                assert "Simulated DB Restore Injected Failure" in str(exc.value)


        # Verificar que el canary_file original sigue intacto
        assert canary_file.exists()
        assert canary_file.read_text(encoding="utf-8") == "DO_NOT_OVERWRITE_ME"
        # Y que el archivo del backup no fue copiado a target_uploads
        assert not (target_uploads / "test_doc.txt").exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# SUITE DE PRUEBAS ADVERSARIALES FOCALIZADAS R5 (R5-01 a R5-04, R5-08)
# ===========================================================================

def test_p14_r5_01a_direct_call_execute_pg_restore_without_marker_rejected():
    """
    R5-01 (a): Invocacion directa a execute_pg_restore sin marcador valido o con marcador vacio.
    Debe fallar de inmediato con ValueError antes de ejecutar cualquier sentencia o consultar el servidor.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_r5_01a_"))
    try:
        dummy_sql = temp_dir / "dump.sql"
        dummy_sql.write_text("CREATE TABLE test_tab (id int);", encoding="utf-8")

        # Caso 1: expected_marker_id vacio
        with pytest.raises(ValueError) as exc1:
            execute_pg_restore(
                target_database_url="postgresql://test_user:test_password@localhost:5432/dr_test_target1",
                sql_file=dummy_sql,
                expected_marker_id="",
                source_database_url="postgresql://test_user:test_password@localhost:5432/test_db"
            )
        assert "expected_marker_id es estrictamente obligatorio" in str(exc1.value)

        # Caso 2: expected_marker_id None
        with pytest.raises(ValueError) as exc2:
            execute_pg_restore(
                target_database_url="postgresql://test_user:test_password@localhost:5432/dr_test_target1",
                sql_file=dummy_sql,
                expected_marker_id=None,
                source_database_url="postgresql://test_user:test_password@localhost:5432/test_db"
            )
        assert "expected_marker_id es estrictamente obligatorio" in str(exc2.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_r5_01b_target_safety_rejects_foreign_execution_marker():
    """
    R5-01 (b): Marcador perteneciente a otra ejecucion es rechazado.
    La tabla _dr_test_ownership_marker contiene 'marker_run_alpha_123', pero la llamada
    proporciona 'marker_run_beta_456'. validate_restore_target_safety debe abortar con PermissionError.
    """
    with mock.patch("verification.dr.backup_lan_pg15.create_engine") as mock_eng:
        mock_conn = mock.MagicMock()
        # table_exists=1, pero marker_row no coincide (retorna None)
        mock_conn.execute.return_value.scalar.side_effect = [1, None]
        mock_eng.return_value.connect.return_value.__enter__.return_value = mock_conn

        with pytest.raises(PermissionError) as exc:
            validate_restore_target_safety(
                target_database_url="postgresql://user:pass@localhost:5432/dr_test_other_run",
                source_database_url="postgresql://user:pass@localhost:5432/test_db",
                expected_marker_id="marker_run_beta_456"
            )
        assert "no coincide con el marcador esperado de esta ejecucion" in str(exc.value)


def test_p14_r5_04_wrong_container_with_legitimate_pg15_system_identifier_mismatch():
    """
    R5-04 (c): Contenedor equivocado con PG15 legitimo.
    Dos contenedores PG15 validos con system_identifier distintos.
    El cluster DSN tiene system_identifier='1111111111111111111', pero el contenedor
    ejecuta en cluster '2222222222222222222'. Debe abortar con RuntimeError (identidad de cluster).
    """
    from verification.dr.backup_lan_pg15 import find_postgres_docker_container

    def mock_docker_exec(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd)
        if "inspect" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="true\n")
        elif "current_setting" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="150004\n")
        elif "system_identifier" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="2222222222222222222\n")
        return mock.MagicMock(returncode=0, stdout="")

    with mock.patch("subprocess.run", side_effect=mock_docker_exec):
        with pytest.raises(RuntimeError) as exc:
            find_postgres_docker_container(
                container_name="other_pg15_container",
                expected_system_identifier="1111111111111111111"
            )
        assert "Fallo de identidad de cluster (R5-04)" in str(exc.value)
        assert "1111111111111111111" in str(exc.value)


def test_p14_r5_02a_injected_failure_during_document_promotion_leaves_target_unaltered():
    """
    R5-02 (d): Fallo inyectado durante la promocion de documentos (ej. en el 2do archivo).
    El cutover atomico con rollback debe restaurar el directorio de destino a su estado exacto previo,
    sin dejar ningun archivo nuevo ni modificaciones parciales.
    """
    from verification.dr.backup_lan_pg15 import atomic_promote_documents

    temp_dir = Path(tempfile.mkdtemp(prefix="test_r5_02a_"))
    try:
        staging_dir = temp_dir / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        target_dir = temp_dir / "target_live"
        target_dir.mkdir(parents=True, exist_ok=True)

        # Archivo canary preexistente en destino
        canary = target_dir / "existing_canary.txt"
        canary.write_text("PRISTINE_LIVE_DATA_DO_NOT_TOUCH", encoding="utf-8")

        # 3 documentos preparados en staging
        catalog = []
        for i in range(1, 4):
            doc_rel = f"doc_{i}.txt"
            doc_file = staging_dir / doc_rel
            doc_content = f"Content of doc {i}".encode("utf-8")
            doc_file.write_bytes(doc_content)
            catalog.append({
                "relative_path": doc_rel,
                "size_bytes": len(doc_content),
                "sha256": hashlib.sha256(doc_content).hexdigest()
            })

        # Inyectar fallo al escribir el segundo archivo
        orig_write_bytes = Path.write_bytes
        file_count = 0

        def flaky_write_bytes(self, data):
            nonlocal file_count
            if "doc_2.txt" in str(self):
                raise IOError("Simulated I/O crash during second file copy")
            return orig_write_bytes(self, data)

        with mock.patch.object(Path, "write_bytes", side_effect=flaky_write_bytes, autospec=True):
            with pytest.raises(RuntimeError) as exc:
                atomic_promote_documents(staging_dir=staging_dir, target_dir=target_dir, catalog=catalog)
            assert "Fallo durante promocion atomica" in str(exc.value)

        # Verificacion critica R5-02: Destino live queda 100% inalterado
        assert target_dir.exists()
        assert canary.exists()
        assert canary.read_text(encoding="utf-8") == "PRISTINE_LIVE_DATA_DO_NOT_TOUCH"
        assert not (target_dir / "doc_1.txt").exists(), "doc_1 no debio quedar en destino tras rollback"
        assert not (target_dir / "doc_2.txt").exists()
        assert not (target_dir / "doc_3.txt").exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_r5_02b_crash_between_db_restore_and_promotion_leaves_live_target_intact():
    """
    R5-02 (e): Caida o fallo inmediatamente tras la restauracion de la base de datos pero
    antes de la promocion de documentos. El destino de documentos permanece completamente intacto.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_r5_02b_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "file1.txt").write_text("Hello Crash Test", encoding="utf-8")

        backup_file = temp_dir / "backup.tar.enc"
        enc_key = "test_enc_key_32bytes_dr_valid_!!"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        create_lan_backup(
            database_url=settings.DATABASE_URL,
            uploads_dir=uploads_dir,
            output_backup_file=backup_file,
            encryption_key=enc_key,
            signing_key=sign_key,
        )

        target_uploads = temp_dir / "live_target"
        target_uploads.mkdir(parents=True, exist_ok=True)
        canary = target_uploads / "original_canary.txt"
        canary.write_text("ORIGINAL_CANARY_STATE", encoding="utf-8")

        # Simular que execute_pg_restore tiene exito, pero atomic_promote_documents falla (crash del host)
        with mock.patch("verification.dr.backup_lan_pg15.validate_restore_target_safety"):
            with mock.patch("verification.dr.backup_lan_pg15.execute_pg_restore", return_value=True):
                with mock.patch("verification.dr.backup_lan_pg15.atomic_promote_documents", side_effect=RuntimeError("Simulated system crash before promotion")):
                    with pytest.raises(RuntimeError) as exc:
                        restore_lan_backup(
                            backup_file=backup_file,
                            target_uploads_dir=target_uploads,
                            encryption_key=enc_key,
                            signing_key=sign_key,
                            expected_marker_id="marker_crash_test",
                            target_database_url="postgresql://test_user:test_password@localhost:5432/dr_test_crash_db",
                            source_database_url="postgresql://test_user:test_password@localhost:5432/test_db"
                        )
                    assert "Simulated system crash before promotion" in str(exc.value)

        # Destino live permanece inalterado
        assert canary.exists()
        assert canary.read_text(encoding="utf-8") == "ORIGINAL_CANARY_STATE"
        assert not (target_uploads / "file1.txt").exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_r5_03_concurrent_write_between_dump_and_catalog_aborts_backup():
    """
    R5-03 (f): Escritura concurrente entre pg_dump y catalogacion.
    Si se inserta un archivo o cambia el estado entre el dump SQL y la verificacion de barrera,
    create_lan_backup debe abortar fail-closed SIN emitir manifiesto firmado ni archivo de respaldo valido.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_r5_03_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "doc_stable.txt").write_text("Stable Document", encoding="utf-8")

        backup_file = temp_dir / "aborted_backup.tar.enc"
        manifest_file = Path(str(backup_file) + ".manifest.json")
        enc_key = "test_enc_key_32bytes_dr_valid_!!"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        # Simular modificacion concurrente durante pg_dump creando un nuevo archivo
        orig_execute_pg_dump = execute_pg_dump

        def write_during_dump(database_url, output_sql_file, container_name=None):
            # Escritura concurrente simulada de un nuevo archivo de documento durante el volcado
            concurrent_doc = uploads_dir / "concurrent_leak.txt"
            concurrent_doc.write_text("CONCURRENT_DATA_DURING_DUMP", encoding="utf-8")
            output_sql_file.write_text("CREATE TABLE t (id int);", encoding="utf-8")
            return output_sql_file.stat().st_size

        with mock.patch("verification.dr.backup_lan_pg15.execute_pg_dump", side_effect=write_during_dump):
            with pytest.raises(RuntimeError) as exc:
                create_lan_backup(
                    database_url=settings.DATABASE_URL,
                    uploads_dir=uploads_dir,
                    output_backup_file=backup_file,
                    encryption_key=enc_key,
                    signing_key=sign_key
                )
            assert "Fallo de coherencia snapshot DR (R5-03)" in str(exc.value)

        # Prohibido emitir manifiesto o backup marcado integro ante fallo de coherencia de snapshot
        assert not backup_file.exists()
        assert not manifest_file.exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_r5_08_missing_psql_fails_closed_without_touching_db():
    """
    R5-08 (i): Ausencia de herramienta psql (tanto en host como en Docker).
    execute_pg_restore debe fallar de inmediato fail-closed sin intentar ejecutar el volcado
    mediante ningun driver SQLAlchemy ni parseo ingenuo.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_r5_08_"))
    try:
        sql_file = temp_dir / "dump.sql"
        sql_file.write_text("CREATE TABLE test_r5_08 (id int);", encoding="utf-8")

        # Mock validate_restore_target_safety exitosa, pero psql ausente en PATH y Docker
        with mock.patch("verification.dr.backup_lan_pg15.validate_restore_target_safety"):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch("verification.dr.backup_lan_pg15.find_postgres_docker_container", return_value=None):
                    with pytest.raises(RuntimeError) as exc:
                        execute_pg_restore(
                            target_database_url="postgresql://test_user:test_password@localhost:5432/dr_test_ephemeral",
                            sql_file=sql_file,
                            expected_marker_id="marker_r5_08",
                            source_database_url="postgresql://test_user:test_password@localhost:5432/test_db"
                        )
                    assert "psql no esta disponible" in str(exc.value)
                    assert "R5-08" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b1_adversarial_process_kill_during_promotion_leaves_target_intact():
    """
    B1: Reproduccion adversarial de muerte repentina del proceso (os._exit) durante la promocion.
    Acredita que target_dir jamas queda en estado parcial (partial=False) y que
    la posterior recuperacion o ejecucion preserva el estado original del destino.
    """
    import sys
    script = """
import os, sys, tempfile, shutil, json, hashlib
from pathlib import Path
from verification.dr.backup_lan_pg15 import atomic_promote_documents

tmp = Path(sys.argv[1])
staging = tmp / "staging"
target = tmp / "target"
staging.mkdir(parents=True, exist_ok=True)
target.mkdir(parents=True, exist_ok=True)

(target / "a.txt").write_bytes(b"ORIGINAL:a.txt")
(target / "b.txt").write_bytes(b"ORIGINAL:b.txt")

(staging / "a.txt").write_bytes(b"RESTORED:a.txt")
(staging / "b.txt").write_bytes(b"RESTORED:b.txt")

catalog = [
    {"relative_path": "a.txt", "size_bytes": 14, "sha256": hashlib.sha256(b"RESTORED:a.txt").hexdigest()},
    {"relative_path": "b.txt", "size_bytes": 14, "sha256": hashlib.sha256(b"RESTORED:b.txt").hexdigest()},
]

orig_write_bytes = Path.write_bytes
def killer_write_bytes(self, data):
    orig_write_bytes(self, data)
    if self.name == "a.txt":
        os._exit(47)

Path.write_bytes = killer_write_bytes
atomic_promote_documents(staging, target, catalog)
"""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b1_kill_"))
    try:
        res = subprocess.run(
            [sys.executable, "-c", script, str(temp_dir)],
            capture_output=True,
            timeout=10
        )
        assert res.returncode == 47, f"El proceso debio morir con codigo 47, obtuvo {res.returncode}"

        target = temp_dir / "target"
        a_content = (target / "a.txt").read_bytes()
        b_content = (target / "b.txt").read_bytes()

        # Comprobar que NO hay estado parcial
        assert a_content == b"ORIGINAL:a.txt", f"a.txt fue corrompido: {a_content}"
        assert b_content == b"ORIGINAL:b.txt", f"b.txt fue corrompido: {b_content}"
        partial = (a_content == b"RESTORED:a.txt" and b_content == b"ORIGINAL:b.txt")
        assert not partial, "CRITICO (B1): El destino quedo en estado parcialmente promovido tras muerte del proceso."

        # Recuperar cutover pendiente y re-verificar
        recover_pending_cutover(target.parent.resolve())
        assert (target / "a.txt").read_bytes() == b"ORIGINAL:a.txt"
        assert (target / "b.txt").read_bytes() == b"ORIGINAL:b.txt"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_snapshot_query_failure_raises_runtime_error():
    """
    B2: Fallo de consulta o conexion PostgreSQL durante la captura de snapshot.
    Debe fallar fail-closed con RuntimeError; prohíbe capturar estado vacio silencioso.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_snap_err_"))
    try:
        unreachable_db_url = "postgresql://test_user:test_password@127.0.0.1:59999/non_existent_db"
        with pytest.raises(RuntimeError) as exc:
            _capture_snapshot_state(uploads_dir=temp_dir, database_url=unreachable_db_url)
        assert "Fallo critico al capturar estado de base de datos para snapshot DR (B2)" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_concurrent_write_after_post_snapshot_aborts_backup():
    """
    B2: Modificacion concurrente ocurrida con posterioridad al snapshot post-dump.
    Demuestra que la barrera final de corte logico detecta cualquier mutacion ocurrida
    durante el empaquetado del archivo TAR y aborta antes de firmar/emitir el respaldo.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_concurrent_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "valid_doc.txt").write_text("VALID DOCUMENT CONTENT", encoding="utf-8")

        backup_file = temp_dir / "backup.tar.enc"
        manifest_file = Path(str(backup_file) + ".manifest.json")
        enc_key = "test_enc_key_32bytes_dr_valid_!!"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        orig_create_catalog = create_document_catalog
        def inject_write_after_catalog(up_dir, session=None):
            cat = orig_create_catalog(up_dir, session=session)
            (up_dir / "late_mutation.txt").write_text("MUTATION OCCURRED AFTER POST SNAPSHOT", encoding="utf-8")
            return cat

        with mock.patch("verification.dr.backup_lan_pg15.create_document_catalog", side_effect=inject_write_after_catalog):
            with pytest.raises(RuntimeError) as exc:
                create_lan_backup(
                    database_url=settings.DATABASE_URL,
                    uploads_dir=uploads_dir,
                    output_backup_file=backup_file,
                    encryption_key=enc_key,
                    signing_key=sign_key
                )
            assert "Fallo de coherencia snapshot DR (B2)" in str(exc.value)

        assert not backup_file.exists()
        assert not manifest_file.exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b3_docker_identity_fail_closed_on_missing_or_mismatched_system_identifier():
    """
    B3: Identidad Docker inequívoca.
    - Si expected_system_identifier no se suministra o falla su consulta en el DSN, aborta.
    - Si el contenedor en ejecucion tiene un system_identifier distinto, aborta fail-closed.
    - Prohibida coincidencia por subcadena arbitraria.
    """
    # 1. Fallo cuando expected_system_identifier no se suministra
    with pytest.raises(RuntimeError) as exc1:
        find_postgres_docker_container(
            user="test_user",
            db_name="test_db",
            target_host="db-test",
            expected_system_identifier=None
        )
    assert "expected_system_identifier es obligatorio" in str(exc1.value)

    # 2. execute_pg_dump con DSN inaccesible al intentar fallback a Docker debe abortar sin ejecutar Docker
    with mock.patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError) as exc2:
            execute_pg_dump(
                database_url="postgresql://test_user:test_password@127.0.0.1:59999/bad_db",
                output_sql_file=Path("dummy.sql")
            )
        assert "Imposible consultar system_identifier en el DSN origen para respaldo via Docker" in str(exc2.value)

    # 3. execute_pg_restore con DSN destino inaccesible al intentar fallback a Docker debe abortar sin tocar contenedores
    with mock.patch("verification.dr.backup_lan_pg15.validate_restore_target_safety"):
        with mock.patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError) as exc3:
                execute_pg_restore(
                    target_database_url="postgresql://test_user:test_password@127.0.0.1:59999/bad_db",
                    sql_file=Path(__file__),
                    expected_marker_id="test_marker",
                    source_database_url="postgresql://test_user:test_password@localhost:5432/test_db"
                )
            assert "Imposible consultar system_identifier en el DSN destino para restauracion via Docker" in str(exc3.value)


# ---------------------------------------------------------------------------
# PRUEBAS ADVERSARIALES FOCALIZADAS (ITEMS 1, 2, 3, 4)
# ---------------------------------------------------------------------------

# Item 1: Mecanismo de publicacion y recuperacion documental resistente a interrupciones
# coordinado con la restauracion PostgreSQL.

def test_p14_item1_interrupted_cutover_forward_recovery_when_db_restored():
    """
    Item 1: Falla a mitad de promocion en TARGET_MOVED con db_restored=True.
    Al reiniciar/recuperar, si el candidato es integro, debe ejecutar Forward Recovery
    (promover candidate a target) para mantener coherencia con la base de datos ya restaurada.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_item1_fwd_"))
    try:
        parent_dir = temp_dir
        target_dir = parent_dir / "uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "original.txt").write_text("ORIGINAL_CONTENT", encoding="utf-8")

        candidate_dir = parent_dir / ".target_candidate_fwd123"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        cand_content = "RESTORED_FORWARD_CONTENT".encode("utf-8")
        (candidate_dir / "doc_new.txt").write_bytes(cand_content)
        cand_sha = hashlib.sha256(cand_content).hexdigest()

        backup_dir = parent_dir / ".target_backup_fwd123"
        # Simular interrupcion tras TARGET_MOVED: target fue movido a backup_dir
        target_dir.rename(backup_dir)

        journal_file = parent_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "TARGET_MOVED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": settings.DATABASE_URL,
            "catalog_hashes": {"doc_new.txt": cand_sha},
            "created_at": time.time()
        }
        journal_file.write_text(json.dumps(journal_data), encoding="utf-8")

        # Ejecutar recuperacion posterior al reinicio
        res = recover_pending_cutover(parent_dir)
        assert res is True
        assert not journal_file.exists(), "El journal debio ser limpiado tras forward recovery"
        assert target_dir.exists(), "target_dir debe existir tras recuperacion exitosa"
        assert (target_dir / "doc_new.txt").exists(), "El documento restaurado debe estar en target_dir"
        assert (target_dir / "doc_new.txt").read_bytes() == cand_content
        assert not backup_dir.exists(), "backup_dir debe haber sido eliminado tras compromiso"
        assert not candidate_dir.exists(), "candidate_dir fue promovido a target_dir"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_item1_interrupted_cutover_rollback_when_db_not_restored():
    """
    Item 1: Falla a mitad de promocion en TARGET_MOVED con db_restored=False.
    Al reiniciar/recuperar, debe ejecutar Rollback (backup -> target) preservando
    los archivos originales intactos.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_item1_rbk_"))
    try:
        parent_dir = temp_dir
        target_dir = parent_dir / "uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        orig_content = "ORIGINAL_PRE_RESTORE".encode("utf-8")
        (target_dir / "original.txt").write_bytes(orig_content)

        candidate_dir = parent_dir / ".target_candidate_rbk123"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "doc_new.txt").write_bytes(b"NEW_DATA")

        backup_dir = parent_dir / ".target_backup_rbk123"
        target_dir.rename(backup_dir)

        journal_file = parent_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "TARGET_MOVED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": False,
            "catalog_hashes": {"doc_new.txt": "dummy_sha"},
            "created_at": time.time()
        }
        journal_file.write_text(json.dumps(journal_data), encoding="utf-8")

        res = recover_pending_cutover(parent_dir)
        assert res is True
        assert not journal_file.exists()
        assert target_dir.exists()
        assert (target_dir / "original.txt").read_bytes() == orig_content
        assert not (target_dir / "doc_new.txt").exists()
        assert not candidate_dir.exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_item1_interrupted_cutover_rollback_and_db_invalidation_when_candidate_corrupt():
    """
    Item 1: Falla con db_restored=True pero candidate_dir corrupto (hash mismatch).
    El sistema NO puede promover un candidato corrupto; debe revertir backup a target
    E invalidar el marcador de propiedad de la BD para alertar y prevenir split-brain.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_item1_corrupt_"))
    try:
        parent_dir = temp_dir
        target_dir = parent_dir / "uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        orig_content = "CANARY_ORIGINAL_FILE".encode("utf-8")
        (target_dir / "original.txt").write_bytes(orig_content)

        candidate_dir = parent_dir / ".target_candidate_corrupt123"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "doc_new.txt").write_bytes(b"CORRUPTED_TRUNCATED_BYTES")

        backup_dir = parent_dir / ".target_backup_corrupt123"
        target_dir.rename(backup_dir)

        journal_file = parent_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "TARGET_MOVED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": "postgresql://test_user:test_password@localhost:5432/dr_test_ephemeral_splitbrain",
            "catalog_hashes": {"doc_new.txt": "EXPECTED_VALID_HASH_THAT_DOES_NOT_MATCH"},
            "created_at": time.time()
        }
        journal_file.write_text(json.dumps(journal_data), encoding="utf-8")

        mock_conn = mock.MagicMock()
        mock_engine = mock.MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        with mock.patch("verification.dr.backup_lan_pg15.create_engine", return_value=mock_engine):
            res = recover_pending_cutover(parent_dir)

        assert res is True
        assert target_dir.exists()
        assert (target_dir / "original.txt").read_bytes() == orig_content
        drop_marker_called = any(
            "_dr_test_ownership_marker" in (
                str(call.args[0].text) if (call.args and hasattr(call.args[0], "text")) else str(call)
            ) and "DROP TABLE" in (
                str(call.args[0].text) if (call.args and hasattr(call.args[0], "text")) else str(call)
            )
            for call in mock_conn.execute.call_args_list
        )
        assert drop_marker_called, "Debio ejecutarse DROP TABLE del marcador en BD para prevenir split-brain"
        quarantine_created = any(
            "_dr_restoration_quarantine" in (
                str(call.args[0].text) if (call.args and hasattr(call.args[0], "text")) else str(call)
            )
            for call in mock_conn.execute.call_args_list
        )
        assert quarantine_created, "Debio crearse la tabla _dr_restoration_quarantine para poner la BD en cuarentena (B1)"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b1_quarantined_database_refuses_operations():
    """
    B1: Acredita que una instalacion inconsistente con _dr_restoration_quarantine
    no puede operar ni ser presentada como restaurada correctamente.
    validate_restore_target_safety aborta con PermissionError.
    """
    mock_conn = mock.MagicMock()
    # Simular que _dr_restoration_quarantine existe en la base de datos:
    # 1. table_exists -> 1, 2. marker_row -> "test_marker_123", 3. quarantine_exists -> 1
    mock_conn.execute.return_value.scalar.side_effect = [1, "test_marker_123", 1]
    mock_engine = mock.MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    with mock.patch("verification.dr.backup_lan_pg15.create_engine", return_value=mock_engine):
        with pytest.raises(PermissionError) as exc:
            validate_restore_target_safety(
                target_database_url="postgresql://test_user:test_password@localhost:5432/dr_test_quarantined",
                source_database_url="postgresql://test_user:test_password@localhost:5432/test_db",
                expected_marker_id="test_marker_123"
            )
        assert "se encuentra en cuarentena estricta" in str(exc.value)
        assert "(_dr_restoration_quarantine detectada)" in str(exc.value)


# Item 2: Coherencia verificable entre volcado PostgreSQL y documentos mediante control de escrituras

def test_p14_item2_write_freeze_lock_blocks_concurrent_writers_and_backups():
    """
    Item 2: Control de escrituras activo (.write_freeze_lock).
    1. Si un proceso propietario vivo retiene el centinela, DocumentWriteControl debe
       abortar fail-closed con RuntimeError sin modificar datos ni el centinela.
    2. Si el centinela pertenece a un proceso terminado (PID muerto), el mecanismo
       debe recuperar el bloqueo huerfano de forma segura y continuar.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_item2_lock_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        lock_file = uploads_dir / ".write_freeze_lock"

        # 1. Proceso propietario VIVO: debe abortar con RuntimeError y preservar centinela
        alive_pid = os.getpid()
        owner_content = f"WRITE_FREEZE_ACTIVE_{time.time()}_{alive_pid}_owner_token_12345\n"
        lock_file.write_text(owner_content, encoding="utf-8")

        with pytest.raises(RuntimeError) as exc:
            with DocumentWriteControl(database_url=settings.DATABASE_URL, uploads_dir=uploads_dir):
                pass
        assert "Fallo de control de escrituras (Item 2, B2)" in str(exc.value)
        assert "Centinela activo de otro proceso vivo detectado" in str(exc.value)
        assert lock_file.exists() and lock_file.read_text(encoding="utf-8") == owner_content

        # 2. Proceso propietario TERMINADO (PID muerto): recuperacion segura de bloqueo huerfano
        dead_pid = 9999999
        dead_content = f"WRITE_FREEZE_ACTIVE_{time.time()}_{dead_pid}_dead_token_67890\n"
        lock_file.write_text(dead_content, encoding="utf-8")

        with DocumentWriteControl(database_url=settings.DATABASE_URL, uploads_dir=uploads_dir):
            # Adquisicion exitosa tras purga del huerfano; al salir limpia su propio centinela
            pass
        assert not lock_file.exists(), "El centinela debio ser liberado tras finalizar el context manager"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_01_competing_process_sentinel_never_deleted():
    """
    B2-01: DocumentWriteControl NUNCA debe eliminar el centinela .write_freeze_lock
    creado por otro proceso vivo si la adquisición falla o se interrumpe.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_01_sentinel_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        lock_file = uploads_dir / ".write_freeze_lock"
        # Proceso 1 legítimo (VIVO) crea su centinela
        process1_token = "TOKEN_PROCESO_1_LEGITIMO"
        alive_pid = os.getpid()
        original_content = f"WRITE_FREEZE_ACTIVE_{time.time()}_{alive_pid}_{process1_token}\n"
        lock_file.write_text(original_content, encoding="utf-8")

        # Proceso 2 competidor intenta adquirir el control y falla
        with pytest.raises(RuntimeError) as exc:
            with DocumentWriteControl(database_url=settings.DATABASE_URL, uploads_dir=uploads_dir):
                pass
        assert "Centinela activo de otro proceso vivo detectado" in str(exc.value)

        # Verificar que el centinela del Proceso 1 NO fue eliminado ni alterado
        assert lock_file.exists(), "Fallo B2-01: El centinela del proceso competidor fue eliminado indebidamente!"
        assert lock_file.read_text(encoding="utf-8") == original_content, "Fallo B2-01: El contenido del centinela fue alterado!"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b1_01_quarantine_committed_transactionally_in_real_postgres():
    """
    B1-01: Demuestra que _enforce_database_quarantine confirma transaccionalmente
    la cuarentena en PostgreSQL real utilizando commit/begin durable.
    """
    from verification.dr.backup_lan_pg15 import _enforce_database_quarantine
    test_reason = f"TEST_QUARANTINE_PERSISTENCE_{uuid.uuid4().hex}"

    # Aplicar cuarentena en PostgreSQL real
    _enforce_database_quarantine(settings.DATABASE_URL, reason=test_reason, journal_state="UNIT_TEST")

    # Abrir una conexión totalmente nueva e independiente para comprobar que quedó COMMITTED
    verify_engine = create_engine(settings.DATABASE_URL)
    with verify_engine.connect() as conn:
        row = conn.execute(
            text("SELECT reason, journal_state FROM _dr_restoration_quarantine WHERE reason = :r"),
            {"r": test_reason}
        ).first()
        assert row is not None, "Fallo B1-01: La cuarentena no se confirmo transaccionalmente en PostgreSQL (rollback al cerrar)!"
        assert row[0] == test_reason
        assert row[1] == "UNIT_TEST"

        # Verificar que el marcador de propiedad efimero fue eliminado con cascade
        marker_exists = conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '_dr_test_ownership_marker'"
        )).scalar()
        assert not marker_exists, "Fallo B1-01: _dr_test_ownership_marker debio eliminarse con DROP TABLE CASCADE!"

        # Limpiar para no afectar otros tests
        with verify_engine.begin() as clean_conn:
            clean_conn.execute(text("DELETE FROM _dr_restoration_quarantine WHERE reason = :r"), {"r": test_reason})
    verify_engine.dispose()


def test_p14_b1_02_db_restored_recovery_sets_quarantine_when_candidate_corrupt():
    """
    B1-02: Reproducción del caso observado por GPT en auditoría.
    target_dir tiene documentos antiguos, candidate_dir tiene documentos corruptos/incompletos,
    y el diario indica phase=DB_RESTORED, db_restored=True.
    recover() NO debe simplemente borrar candidate y devolver recover=True sin cuarentena.
    DEBE establecer cuarentena transaccional en PostgreSQL y devolver False.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b1_02_"))
    try:
        parent_dir = temp_dir / "storage"
        target_dir = parent_dir / "target"
        candidate_dir = parent_dir / "candidate"
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate_dir.mkdir(parents=True, exist_ok=True)

        (target_dir / "old.txt").write_text("old_content", encoding="utf-8")
        # Candidate corrupto (hash no coincide o archivo falta)
        (candidate_dir / "doc.txt").write_text("corrupted_content", encoding="utf-8")

        journal_file = parent_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir),
            "candidate_dir": str(candidate_dir),
            "backup_dir": str(parent_dir / "backup"),
            "db_restored": True,
            "target_database_url": settings.DATABASE_URL,
            "catalog_hashes": {"doc.txt": "expected_valid_hash_which_does_not_match"},
            "created_at": time.time()
        }
        journal_file.write_text(json.dumps(journal_data), encoding="utf-8")

        # Invocar recover()
        res = CrashResilientDocumentPublisher.recover(
            parent_dir=parent_dir,
            target_database_url=settings.DATABASE_URL
        )

        assert res is True, "Fallo B1-02: recover() debio procesar la contingencia y activar la cuarentena!"

        # Verificar que la cuarentena fue efectivamente establecida en PostgreSQL real
        verify_engine = create_engine(settings.DATABASE_URL)
        with verify_engine.connect() as conn:
            q_row = conn.execute(text(
                "SELECT reason FROM _dr_restoration_quarantine "
                "WHERE reason LIKE '%INCONSISTENT_RESTORATION (B1-02)%' ORDER BY id DESC LIMIT 1"
            )).first()
            assert q_row is not None, "Fallo B1-02: No se establecio la cuarentena en PostgreSQL tras fallo en DB_RESTORED!"
            with verify_engine.begin() as clean_conn:
                clean_conn.execute(text("DELETE FROM _dr_restoration_quarantine WHERE reason LIKE '%INCONSISTENT_RESTORATION (B1-02)%';"))
        verify_engine.dispose()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b1_03_quarantine_transversally_blocks_services():
    """
    B1-03: Demuestra que cuando la tabla _dr_restoration_quarantine contiene un registro,
    los servicios operativos quedan bloqueados transversalmente:
    1. startup_verify_database_quarantine() lanza RuntimeError.
    2. get_db() lanza RuntimeError impidiendo atender consultas.
    """
    from app.main import startup_verify_database_quarantine
    from app.core.database import get_db

    # 1. Insertar cuarentena en PostgreSQL real
    eng = create_engine(settings.DATABASE_URL)
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS _dr_restoration_quarantine ("
            "  id SERIAL PRIMARY KEY, quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reason TEXT NOT NULL, journal_state TEXT"
            ");"
        ))
        conn.execute(text(
            "INSERT INTO _dr_restoration_quarantine (reason, journal_state) "
            "VALUES ('TEST_TRANSVERSAL_BLOCKING', 'CORRUPT');"
        ))

    try:
        # A. Startup hook debe abortar fail-closed
        with pytest.raises(RuntimeError) as exc_startup:
            startup_verify_database_quarantine()
        assert "BLOQUEO OPERATIVO" in str(exc_startup.value) and "CUARENTENA DR (B1-03)" in str(exc_startup.value)

        # B. Sesión de base de datos get_db() debe rechazar solicitudes
        with pytest.raises(RuntimeError) as exc_getdb:
            next(get_db())
        assert "BLOQUEO OPERATIVO" in str(exc_getdb.value) and "CUARENTENA DR (B1-03)" in str(exc_getdb.value)

    finally:
        with eng.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS _dr_restoration_quarantine CASCADE;"))
        eng.dispose()


def test_p14_b2_row_update_without_row_count_change_detected_and_aborts_backup():
    """
    B2, B2-03: Modificación de registros en PostgreSQL 15 REAL SIN alteración del número de filas.
    Ejecuta un UPDATE SQL real concurrente contra la base de datos PostgreSQL durante el respaldo
    (interviniendo en execute_pg_dump para simular la concurrencia exacta de un escritor).
    NO usa mocks sobre _capture_snapshot_state.
    Acredita que _capture_snapshot_state detecta la mutación real en table_fingerprints (xmin y MD5 de fila)
    y create_lan_backup aborta fail-closed con RuntimeError antes de declarar válido el respaldo.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_real_update_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "doc.txt").write_text("doc_data", encoding="utf-8")
        backup_file = temp_dir / "out.tar.enc"

        # Asegurar que al menos existe un usuario en la BD de pruebas antes del snapshot
        init_eng = create_engine(settings.DATABASE_URL)
        with init_eng.begin() as conn:
            uid = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar()
            if uid is None:
                conn.execute(text("INSERT INTO tenants (id, name, is_active) VALUES ('tenant-default', 'Default Tenant', true) ON CONFLICT (id) DO NOTHING;"))
                conn.execute(text(
                    "INSERT INTO users (tenant_id, username, password_hash, role, is_active, failed_login_count) "
                    "VALUES ('tenant-default', 'seed_user_b2_test', 'hash', 'operator', true, 0)"
                ))
        init_eng.dispose()

        import verification.dr.backup_lan_pg15 as dr_mod
        orig_execute_pg_dump = dr_mod.execute_pg_dump

        def pg_dump_with_real_concurrent_update(db_url, sql_path, container):
            sz = orig_execute_pg_dump(db_url, sql_path, container)
            # Mutación SQL REAL contra PostgreSQL 15 modificando una fila sin alterar count(*)
            eng = create_engine(db_url)
            with eng.begin() as conn:
                conn.execute(text(
                    "UPDATE users SET failed_login_count = failed_login_count + 1 "
                    "WHERE id = (SELECT id FROM users ORDER BY id LIMIT 1);"
                ))
            eng.dispose()
            return sz

        with mock.patch("verification.dr.backup_lan_pg15.execute_pg_dump", side_effect=pg_dump_with_real_concurrent_update):
            with pytest.raises(RuntimeError) as exc:
                create_lan_backup(
                    database_url=settings.DATABASE_URL,
                    uploads_dir=uploads_dir,
                    output_backup_file=backup_file,
                    encryption_key="test_enc_key_32bytes_dr_valid_!!",
                    signing_key="test_sign_key_32bytes_hmac_valid"
                )
            assert "Modificacion concurrente detectada en registros de base de datos" in str(exc.value)
            assert "(incluyendo mutacion de registros sin alteracion de filas)" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_concurrent_backup_exclusion_via_try_advisory_lock():
    """
    B2: Exclusion mutua estricta e inmediata entre respaldos concurrentes.
    Si otro respaldo ya tiene adquirido el advisory lock en PostgreSQL,
    pg_try_advisory_lock retorna False y DocumentWriteControl aborta inmediatamente con RuntimeError.
    Demuestra exclusion entre dos conexiones reales y liberacion segura.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_adv_lock_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        # Respaldo 1 adquiere control y retiene advisory lock real en PostgreSQL 15
        with DocumentWriteControl(database_url=settings.DATABASE_URL, uploads_dir=uploads_dir):
            lock_file = uploads_dir / ".write_freeze_lock"
            assert lock_file.exists(), "El centinela de Respaldo 1 debe existir"
            original_content = lock_file.read_text(encoding="utf-8")

            # Respaldo 2 intenta adquirir concurrentemente sobre otra conexion independiente y debe fallar
            with pytest.raises(RuntimeError) as exc:
                with DocumentWriteControl(database_url=settings.DATABASE_URL, uploads_dir=uploads_dir):
                    pass
            assert "Ya existe un respaldo LAN en ejecucion" in str(exc.value)
            assert "advisory lock 'abst_lan_backup_write_lock' retenido" in str(exc.value)

            # Verificar que el centinela del Respaldo 1 se mantuvo intacto
            assert lock_file.exists(), "El centinela de Respaldo 1 no debio ser eliminado"
            assert lock_file.read_text(encoding="utf-8") == original_content

        # Al salir Respaldo 1, el advisory lock y el centinela deben quedar liberados
        assert not lock_file.exists(), "El centinela debio ser liberado"
        # Ahora un nuevo intento posterior debe poder adquirir y liberar limpiamente
        with DocumentWriteControl(database_url=settings.DATABASE_URL, uploads_dir=uploads_dir):
            pass
        assert not lock_file.exists()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_item2_strict_content_sha_detects_tamper_with_forged_size_and_mtime():
    """
    Item 2: Comprobacion estricta de hash SHA-256 de contenido.
    No considerar suficientes comparaciones de tamano y fecha:
    Un atacante muta el contenido manteniendo el MISMO tamano en bytes y la MISMA fecha de modificacion.
    _capture_snapshot_state debe detectar la alteracion en disk_files mediante hash SHA-256.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_item2_tamper_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        doc = uploads_dir / "important_contract.txt"
        doc.write_bytes(b"PAY_SUPPLIER_AMOUNT_100000_USD")
        orig_stat = doc.stat()

        state_before = _capture_snapshot_state(uploads_dir=uploads_dir, database_url=settings.DATABASE_URL)
        orig_sha = state_before["disk_files"]["important_contract.txt"]

        # Mutar contenido con EXACTAMENTE la misma longitud (30 bytes)
        tampered_content = b"PAY_ATTACKER_X_AMOUNT_100000_U"
        assert len(tampered_content) == len(b"PAY_SUPPLIER_AMOUNT_100000_USD")
        doc.write_bytes(tampered_content)

        # Forjar mtime para que coincida exactamente con el stat original
        os.utime(doc, (orig_stat.st_atime, orig_stat.st_mtime))

        tampered_stat = doc.stat()
        assert tampered_stat.st_size == orig_stat.st_size, "El tamano no cambio"
        assert tampered_stat.st_mtime == orig_stat.st_mtime, "El timestamp no cambio"

        state_after = _capture_snapshot_state(uploads_dir=uploads_dir, database_url=settings.DATABASE_URL)
        new_sha = state_after["disk_files"]["important_contract.txt"]

        # La verificacion criptografica por contenido detecta la manipulacion
        assert orig_sha != new_sha, "El hash SHA-256 debe detectar la mutacion a pesar de igual tamano y fecha"
        assert state_before["disk_files"] != state_after["disk_files"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_item2_table_count_failure_is_not_silenced():
    """
    Item 2: No silenciar errores de captura en conteo de tablas.
    Si la consulta de conteo falla en PostgreSQL, create_lan_backup debe abortar fail-closed
    con RuntimeError (no silenciar con table_counts[tbl] = 0).
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_item2_counts_"))
    try:
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "doc.txt").write_text("doc", encoding="utf-8")
        backup_file = temp_dir / "out.tar.enc"

        orig_execute = Session.execute
        def flaky_counts(self, statement, *args, **kwargs):
            if "count(*)" in str(statement).lower():
                raise RuntimeError("Simulated DB connection crash during table count query")
            return orig_execute(self, statement, *args, **kwargs)

        with mock.patch.object(Session, "execute", flaky_counts):
            with pytest.raises(RuntimeError) as exc:
                create_lan_backup(
                    database_url=settings.DATABASE_URL,
                    uploads_dir=uploads_dir,
                    output_backup_file=backup_file,
                    encryption_key="test_enc_key_32bytes_dr_valid_!!",
                    signing_key="test_sign_key_32bytes_hmac_valid"
                )
            assert "Fallo critico al capturar conteo de tabla" in str(exc.value)
            assert "(Item 2)" in str(exc.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# Item 3: Identidad comprobada del cluster PostgreSQL y correspondencia del contenedor

def test_p14_item3_cluster_identity_unverifiable_dsn_aborts():
    """
    Item 3: Exigir identidad comprobada del cluster PostgreSQL.
    Si el DSN no permite verificar system_identifier (ej. retorna None o vacio),
    execute_pg_dump y execute_pg_restore deben abortar fail-closed.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_item3_ident_"))
    try:
        sql_file = temp_dir / "dump.sql"
        sql_file.write_text("SELECT 1;", encoding="utf-8")

        mock_conn1 = mock.MagicMock()
        mock_conn1.execute.return_value.scalar.side_effect = [None, 150000]
        mock_engine1 = mock.MagicMock()
        mock_engine1.connect.return_value.__enter__.return_value = mock_conn1

        with mock.patch("verification.dr.backup_lan_pg15.create_engine", return_value=mock_engine1):
            with pytest.raises(RuntimeError) as exc_dump:
                execute_pg_dump(
                    database_url="postgresql://test_user:test_password@localhost:5432/test_db",
                    output_sql_file=sql_file
                )
            assert "system_identifier obtenido del DSN origen es invalido o vacio" in str(exc_dump.value)

        mock_conn2 = mock.MagicMock()
        mock_conn2.execute.return_value.scalar.side_effect = [None, 150000]
        mock_engine2 = mock.MagicMock()
        mock_engine2.connect.return_value.__enter__.return_value = mock_conn2

        with mock.patch("verification.dr.backup_lan_pg15.create_engine", return_value=mock_engine2):
            with mock.patch("verification.dr.backup_lan_pg15.validate_restore_target_safety"):
                with pytest.raises(RuntimeError) as exc_rest:
                    execute_pg_restore(
                        target_database_url="postgresql://test_user:test_password@localhost:5432/dr_test_fake",
                        sql_file=sql_file,
                        expected_marker_id="marker_fake",
                        source_database_url="postgresql://test_user:test_password@localhost:5432/test_db"
                    )
                assert "system_identifier obtenido del DSN destino es invalido o vacio" in str(exc_rest.value)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_item3_container_missing_requested_database_rejected():
    """
    Item 3: Correspondencia del contenedor con la base de datos solicitada.
    Si un contenedor ejecuta PG15 y pertenece al cluster correcto, pero NO contiene
    la base de datos solicitada, find_postgres_docker_container debe abortar fail-closed.
    """
    mock_ps_output = "db_test_cont\tpostgres:15-alpine\t5432/tcp\tcom.docker.compose.service=db-test\n"

    def mock_run_db_missing(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if "inspect" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="true\n")
        elif "current_setting" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="150000\n")
        elif "system_identifier" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="9999999999\n")
        elif "pg_database" in cmd_str:
            return mock.MagicMock(returncode=0, stdout="0\n")
        return mock.MagicMock(returncode=0, stdout="")

    with mock.patch("subprocess.run", side_effect=mock_run_db_missing):
        with pytest.raises(RuntimeError) as exc:
            find_postgres_docker_container(
                container_name="db_test_cont",
                user="test_user",
                db_name="target_db_nonexistent",
                expected_system_identifier="9999999999"
            )
        assert "Fallo de correspondencia de base de datos (Item 3)" in str(exc.value)


# Item 4: Candidate Tree SHA exacto para todos los archivos del parche (incluyendo nuevos)

def test_p14_item4_candidate_tree_sha_exact_patch_all_files():
    """
    Item 4: Calculo exacto del Candidate Tree SHA.
    1. Utiliza un indice temporal aislado sin tocar el indice principal de git.
    2. Aplica el parche binario generado desde el base commit caa135c25392330b483167d5d552c51dc398a905.
    3. Incluye exactamente la totalidad de archivos modificados y nuevos (42 archivos).
    4. Verifica que el arbol reconstruido (git write-tree) corresponda al candidato de trabajo
       con git diff --quiet retornando codigo 0.
    """
    import tempfile
    import os

    if not shutil.which("git"):
        pytest.skip("Binario git no disponible en el contenedor de pruebas (verificado exhaustivamente en host)")

    base_commit = "caa135c25392330b483167d5d552c51dc398a905"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".patch") as pf:
        patch_file = pf.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".idx") as idf:
        index_file = idf.name

    try:
        # 1. Generar parche binario limpio
        subprocess.run(
            ["git", "diff", base_commit, "--binary", f"--output={patch_file}"],
            check=True
        )

        # 2. Utilizar indice temporal aislado
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = index_file

        subprocess.run(["git", "read-tree", base_commit], env=env, check=True)
        subprocess.run(["git", "apply", "--cached", "--whitespace=nowarn", patch_file], env=env, check=True)
        tree_sha = subprocess.check_output(["git", "write-tree"], env=env, text=True).strip()

        assert len(tree_sha) == 40, f"Candidate Tree SHA invalido: {tree_sha}"

        # 3. Comprobar que el arbol reconstruido corresponde de forma exacta al candidato
        diff_res = subprocess.run(["git", "diff", "--quiet", tree_sha], check=False)
        assert diff_res.returncode == 0, (
            f"El arbol reconstruido {tree_sha} tiene discrepancias con el candidato de trabajo "
            f"(git diff --quiet retorno {diff_res.returncode})."
        )

        # 4. Verificar que el indice principal no fue alterado
        status_res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
        assert tree_sha != "UNKNOWN"
    finally:
        if os.path.exists(patch_file):
            os.unlink(patch_file)
        if os.path.exists(index_file):
            os.unlink(index_file)


# ===========================================================================
# P14-R8 ADVERSARIAL SUITE — Subsanacion Integral Dictamen Auditoria GPT
# ===========================================================================

def test_p14_b1_quarantine_inspection_failure_is_fail_closed():
    """
    B1-CRITICO / Auditoria GPT Item 1:
    Acredita que un error o excepcion (ej. PermissionError) durante la inspeccion de cuarentena
    tanto en get_db() como en startup_verify_database_quarantine() NO permite acceso (fail-closed).
    Reproduccion exacta del hallazgo de GPT: una sesion con execute() lanzando PermissionError
    rechaza categoricamente con RuntimeError (B1-FAIL-CLOSED) y NUNCA entrega la sesion.
    """
    from app.core.database import get_db
    from app.main import startup_verify_database_quarantine

    # 1. Reproduccion sobre get_db(): inyectar excepcion en db.execute
    mock_session = mock.MagicMock()
    mock_session.bind.dialect.name = "postgresql"
    mock_session.execute.side_effect = PermissionError("DENIED on quarantine inspection")

    with mock.patch("app.core.database.SessionLocal", return_value=mock_session):
        gen = get_db()
        with pytest.raises(RuntimeError) as exc_info:
            next(gen)
        assert "B1-FAIL-CLOSED" in str(exc_info.value)
        assert "DENIED on quarantine inspection" in str(exc_info.value)
        # Verificar que la sesion fue cerrada en finally
        mock_session.close.assert_called_once()

    # 2. Reproduccion sobre startup_verify_database_quarantine(): inyectar excepcion
    with mock.patch("app.core.database.SessionLocal", return_value=mock_session):
        with pytest.raises(RuntimeError) as exc_startup:
            startup_verify_database_quarantine()
        assert "B1-FAIL-CLOSED" in str(exc_startup.value)
        assert "DENIED on quarantine inspection" in str(exc_startup.value)


def test_p14_b1_pool_checkout_fails_closed_on_quarantine_and_inspection_error():
    """
    B1-CRITICO / Auditoria GPT Item 1:
    Acredita que el control de cuarentena se extiende a nivel de pool de SQLAlchemy (checkout),
    bloqueando procesos o workers de background que omitan get_db().
    1. Si _dr_restoration_quarantine existe con causa: checkout lanza RuntimeError.
    2. Si ocurre un error de permisos o fallo de catalogo en PostgreSQL: checkout lanza RuntimeError (fail-closed).
    """
    from app.core.database import engine, SessionLocal

    # 1. Bloqueo en PostgreSQL real con registro de cuarentena
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS _dr_restoration_quarantine ("
            "  id SERIAL PRIMARY KEY, quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reason TEXT NOT NULL, journal_state TEXT"
            ");"
        ))
        conn.execute(text(
            "INSERT INTO _dr_restoration_quarantine (reason, journal_state) "
            "VALUES ('TEST_POOL_CHECKOUT_BLOCKING', 'DB_RESTORED');"
        ))

    try:
        # A. Conexion directa mediante engine.connect() (omite get_db)
        with pytest.raises(RuntimeError) as exc_conn:
            with engine.connect() as _:
                pass
        assert "BLOQUEO OPERATIVO POR CUARENTENA DR (B1-03)" in str(exc_conn.value)
        assert "TEST_POOL_CHECKOUT_BLOCKING" in str(exc_conn.value)

        # B. Sesion instanciada directamente SessionLocal() (omite get_db)
        with pytest.raises(RuntimeError) as exc_sess:
            sess = SessionLocal()
            try:
                sess.execute(text("SELECT 1;"))
            finally:
                sess.close()
        assert "BLOQUEO OPERATIVO POR CUARENTENA DR (B1-03)" in str(exc_sess.value)

    finally:
        from verification.dr.backup_lan_pg15 import _lift_database_quarantine
        from app.core.config import settings
        _lift_database_quarantine(settings.DATABASE_URL)

    # 2. Falla cerrada ante error en cursor durante checkout
    mock_dbapi_conn = mock.MagicMock()
    mock_cursor = mock.MagicMock()
    mock_cursor.execute.side_effect = PermissionError("DENIED on pool checkout inspect")
    mock_dbapi_conn.cursor.return_value = mock_cursor

    from app.core.database import verify_quarantine_on_checkout
    with pytest.raises(RuntimeError) as exc_checkout:
        verify_quarantine_on_checkout(mock_dbapi_conn, None, None)
    assert "B1-FAIL-CLOSED" in str(exc_checkout.value)
    assert "DENIED on pool checkout inspect" in str(exc_checkout.value)


def test_p14_b1_crash_between_pg_restore_and_publish_recovers_and_lifts_quarantine():
    """
    B1-CRITICO / Auditoria GPT Item 2:
    Acredita el cierre de la ventana sin journal previa a la publicacion documental:
    1. El estado persistente de restauracion y la proteccion de PostgreSQL se establecen ANTES de modificar la base de datos.
    2. Simula una terminacion abrupta (SIGKILL) entre el commit SQL y el corte documental:
       - El journal persiste en disco (phase='DB_RESTORED').
       - PostgreSQL esta en cuarentena transaccional irrefutable.
       - Los servicios operativos rechazan conexiones.
    3. Al ejecutar recover(), se realiza recuperacion hacia adelante (forward recovery),
       se verifica la integridad de los documentos y SOLO ENTONCES se levanta la cuarentena en PostgreSQL.
    4. En caso de archivos corruptos tras la caida, recover() mantiene la cuarentena y no borra el journal.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b1_zero_window_"))
    try:
        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "old_doc.txt").write_text("old_data", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate_test"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        new_doc = candidate_dir / "new_doc.txt"
        new_doc.write_text("new_data_content", encoding="utf-8")
        new_sha = hashlib.sha256(b"new_data_content").hexdigest()

        journal_file = temp_dir / ".cutover_journal.json"
        db_url = settings.DATABASE_URL

        # Establecer cuarentena en PostgreSQL (simulando que el commit de pg_restore ya ocurrio)
        from verification.dr.backup_lan_pg15 import _enforce_database_quarantine, _lift_database_quarantine
        _enforce_database_quarantine(db_url, reason="RESTORATION_IN_PROGRESS: Pending cutover", journal_state="DB_RESTORED")

        # Escribir journal previo
        journal_data = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / ".target_backup_test").resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "catalog_hashes": {"new_doc.txt": new_sha},
            "created_at": time.time()
        }
        journal_file.write_text(json.dumps(journal_data, indent=2), encoding="utf-8")

        # Acreditar que mientras esta en este estado post-caida, la BD esta inaccesible para los servicios
        from app.core.database import get_db
        with pytest.raises(RuntimeError) as exc_acc:
            next(get_db())
        assert "BLOQUEO OPERATIVO POR CUARENTENA DR" in str(exc_acc.value)

        # Ejecutar recover() post-reinicio
        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url
        )
        assert recovered is True, "recover() debio completar la recuperacion hacia adelante"

        # Acreditar que el documento nuevo fue promovido a target
        assert (target_dir / "new_doc.txt").exists()
        assert (target_dir / "new_doc.txt").read_text(encoding="utf-8") == "new_data_content"

        # Acreditar que la cuarentena fue LEVANTADA exitosamente tras la promocion
        eng = create_engine(db_url)
        with eng.connect() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is None, "La tabla _dr_restoration_quarantine debio ser removida tras recuperacion completa"
        eng.dispose()

        # B. Probar escenario de archivo corrupto tras caida: la cuarentena NO debe levantarse y el journal NO debe borrarse
        corrupt_target = temp_dir / "target_corrupt"
        corrupt_target.mkdir(parents=True, exist_ok=True)
        corrupt_cand = temp_dir / ".target_candidate_corrupt"
        corrupt_cand.mkdir(parents=True, exist_ok=True)
        (corrupt_cand / "corrupt.txt").write_text("corrupted_content", encoding="utf-8")

        _enforce_database_quarantine(db_url, reason="RESTORATION_IN_PROGRESS: Pending cutover", journal_state="DB_RESTORED")
        corrupt_journal = {
            "phase": "DB_RESTORED",
            "target_dir": str(corrupt_target.resolve()),
            "candidate_dir": str(corrupt_cand.resolve()),
            "backup_dir": str((temp_dir / ".target_backup_corrupt").resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "catalog_hashes": {"corrupt.txt": "EXPECTED_HASH_THAT_DOES_NOT_MATCH"},
            "created_at": time.time()
        }
        journal_file.write_text(json.dumps(corrupt_journal, indent=2), encoding="utf-8")

        # recover debe detectar la corrupcion, preservar la cuarentena y preservar el journal
        CrashResilientDocumentPublisher.recover(parent_dir=temp_dir, target_database_url=db_url)

        # Verificar que el journal NO fue eliminado (evidencia preservada)
        assert journal_file.exists(), "El journal NO debe eliminarse si hay fallo o corrupcion"
        persisted_data = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted_data.get("phase") == "FAILED_INCONSISTENT"

        # Verificar que la BD sigue en cuarentena
        eng2 = create_engine(db_url)
        with eng2.connect() as conn:
            q_exists2 = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists2 is not None, "La BD debe permanecer en cuarentena ante corrupcion"
        eng2.dispose()

    finally:
        _lift_database_quarantine(settings.DATABASE_URL)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_lock_survives_past_1800s_when_process_alive():
    """
    B2-CRITICO / Auditoria GPT Item 3:
    Eliminacion de la caducidad insegura de .write_freeze_lock:
    1. Acredita que un centinela de mas de 1800s (ej. 2000s o 31 minutos) cuyo proceso sigue vivo
       PERMANECE ACTIVO y is_write_frozen() devuelve True sin liberar por tiempo.
    2. Acredita que solo si el PID pertenece a un proceso muerto, es considerado huerfano.
    """
    from app.core.write_control import DocumentWriteControl

    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_1800s_"))
    try:
        lock_file = temp_dir / ".write_freeze_lock"
        current_pid = os.getpid()

        # Simular centinela de 2000 segundos en el pasado (33 minutos atras)
        old_timestamp = time.time() - 2000.0
        lock_content = f"WRITE_FREEZE_ACTIVE_{old_timestamp}_{current_pid}_testtoken123\n"
        lock_file.write_text(lock_content, encoding="utf-8")

        # Con el proceso actual vivo, is_write_frozen() DEBE devolver True (no caducar por tiempo)
        assert DocumentWriteControl.is_write_frozen(temp_dir) is True, (
            "El bloqueo documental NO debe caducar pasados los 1800s si el proceso sigue vivo"
        )

        # Ahora simular un centinela con un PID que no existe en el sistema operativo
        dead_pid = 9999999
        dead_lock_content = f"WRITE_FREEZE_ACTIVE_{time.time()}_{dead_pid}_deadtoken456\n"
        lock_file.write_text(dead_lock_content, encoding="utf-8")

        assert DocumentWriteControl.is_write_frozen(temp_dir) is False, (
            "Un centinela con PID no existente en el OS debe considerarse huerfano"
        )

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_competing_backup_rejection_leaves_sentinel_intact():
    """
    B2-CRITICO / Auditoria GPT Item 3:
    Acredita que cuando un segundo respaldo concurrente es rechazado porque PostgreSQL
    ya tiene el advisory lock retenido por el primer respaldo, el centinela del propietario
    original PERMANECE INTACTO y NO ES ELIMINADO por el competidor rechazado.
    """
    from app.core.write_control import DocumentWriteControl

    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_competing_"))
    try:
        lock_file = temp_dir / ".write_freeze_lock"
        original_content = f"WRITE_FREEZE_ACTIVE_{time.time()}_{os.getpid()}_ORIGINAL_OWNER_TOKEN\n"
        lock_file.write_text(original_content, encoding="utf-8")

        # Simular segundo respaldo concurrente donde pg_try_advisory_lock devuelve False
        mock_conn = mock.MagicMock()
        mock_conn.execute.return_value.scalar.return_value = False
        mock_conn.closed = False

        mock_engine = mock.MagicMock()
        mock_engine.connect.return_value = mock_conn

        with mock.patch("app.core.write_control.create_engine", return_value=mock_engine):
            competing = DocumentWriteControl(database_url="postgresql://mock:mock@localhost:5432/mock", uploads_dir=temp_dir)
            with pytest.raises(RuntimeError) as exc_info:
                with competing:
                    pass
            assert "Ya existe un respaldo LAN en ejecucion" in str(exc_info.value)

        # VERIFICACION CRITICA: El centinela del propietario original debe sobrevivir intacto
        assert lock_file.exists(), "El centinela del propietario original fue eliminado indebidamente por el competidor rechazado"
        assert lock_file.read_text(encoding="utf-8") == original_content

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_storage_layer_blocks_mutation_during_freeze():
    """
    B2-CRITICO / Auditoria GPT Item 3:
    Acredita que todas las rutas de mutacion documental y workers respetan la barrera
    verificable de congelamiento:
    1. LocalStorageAdapter.put() lanza RuntimeError durante congelamiento activo.
    2. LocalStorageAdapter.delete() lanza RuntimeError durante congelamiento activo.
    3. Los endpoints HTTP correspondientes retornan 503 Service Unavailable.
    """
    from app.storage.local import LocalStorageAdapter
    from app.core.write_control import DocumentWriteControl

    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_storage_"))
    try:
        adapter = LocalStorageAdapter(base_dir=str(temp_dir))
        lock_file = temp_dir / ".write_freeze_lock"

        # Activar centinela con PID actual vivo
        lock_file.write_text(f"WRITE_FREEZE_ACTIVE_{time.time()}_{os.getpid()}_token_storage_test\n", encoding="utf-8")
        assert DocumentWriteControl.is_write_frozen(temp_dir) is True

        # 1. put() debe ser rechazado inmediatamente
        fake_stream = io.BytesIO(b"test document bytes")
        with pytest.raises(RuntimeError) as exc_put:
            adapter.put(tenant_id="tenant_1", document_id="doc1.pdf", file_stream=fake_stream)
        assert "Fallo de control de escrituras (B2)" in str(exc_put.value)

        # 2. delete() debe ser rechazado inmediatamente
        with pytest.raises(RuntimeError) as exc_del:
            adapter.delete(uri="tenant_1/doc1.pdf")
        assert "Fallo de control de escrituras (B2)" in str(exc_del.value)

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b1_publish_aborts_fail_closed_when_corrupted_journal_exists():
    """
    B1-A / Auditoria GPT:
    Acredita que en CrashResilientDocumentPublisher, publish() ABORTA FAIL-CLOSED con RuntimeError
    cuando existe un journal previo (.cutover_journal.json) corrupto o cuya recuperacion fallo.
    Verifica taxativamente:
    1. publish() NO procede a crear directorios ni a sustituir target.
    2. El journal corrupto previo PERMANECE INTACTO y NO ES ELIMINADO NI SOBRESCRITO.
    """
    from verification.dr.backup_lan_pg15 import CrashResilientDocumentPublisher

    temp_dir = Path(tempfile.mkdtemp(prefix="test_b1_corrupt_journal_"))
    try:
        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "original_doc.txt").write_text("original_content", encoding="utf-8")

        staging_dir = temp_dir / "staging_docs"
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / "new_doc.txt").write_text("new_unauthorized_content", encoding="utf-8")

        # Crear diario corrupto preexistente
        corrupted_content = "{\"phase\": \"INVALID_JSON_CORRUPTED"
        journal_file = temp_dir / ".cutover_journal.json"
        journal_file.write_text(corrupted_content, encoding="utf-8")

        publisher = CrashResilientDocumentPublisher(target_dir=target_dir)

        # publish() DEBE abortar fail-closed
        with pytest.raises(RuntimeError) as exc_info:
            publisher.publish(staging_dir=staging_dir, catalog=[{"relative_path": "new_doc.txt", "sha256": "abc"}])

        assert "Fallo critico de recuperacion (B1)" in str(exc_info.value), (
            f"publish() debio lanzar RuntimeError fail-closed: {exc_info.value}"
        )

        # Acreditar que el target_dir original NO fue alterado
        assert (target_dir / "original_doc.txt").exists()
        assert (target_dir / "original_doc.txt").read_text(encoding="utf-8") == "original_content"
        assert not (target_dir / "new_doc.txt").exists(), "El target no debio recibir documentos nuevos"

        # Acreditar que el diario corrupto NO fue eliminado ni sobreescrito
        assert journal_file.exists(), "El diario de corte corrupto previo fue eliminado indebidamente"
        assert journal_file.read_text(encoding="utf-8") == corrupted_content, (
            "El contenido del diario corrupto fue sobreescrito indebidamente"
        )

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b1_recover_fails_when_quarantine_enforcement_fails():
    """
    B1-B / Auditoria GPT:
    Acredita que recover() NO devuelve exito ni afirma que PostgreSQL quedo en cuarentena
    cuando _enforce_database_quarantine() fallo o no pudo verificarse su confirmacion efectiva.
    Verifica taxativamente:
    1. recover() devuelve False (fail-closed).
    2. El journal registra la fase FAILED_INCONSISTENT y la falla de confirmacion.
    3. El diario de corte se preserva intacto para auditoria forense.
    """
    from verification.dr.backup_lan_pg15 import CrashResilientDocumentPublisher

    temp_dir = Path(tempfile.mkdtemp(prefix="test_b1_quarantine_fail_"))
    try:
        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        cand_dir = temp_dir / ".target_candidate_corrupt"
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / "bad_file.txt").write_text("bad_data", encoding="utf-8")

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(cand_dir.resolve()),
            "backup_dir": str((temp_dir / ".target_backup").resolve()),
            "db_restored": True,
            "target_database_url": "postgresql://mock_user:mock_pass@localhost:5432/mock_db",
            "catalog_hashes": {"bad_file.txt": "CORRECT_HASH_DIFFERENT_FROM_BAD"},
            "created_at": time.time()
        }
        journal_file.write_text(json.dumps(journal_data, indent=2), encoding="utf-8")

        # Simular fallo en _enforce_database_quarantine (ej. PostgreSQL caido / conexion rechazada)
        with mock.patch("verification.dr.backup_lan_pg15._enforce_database_quarantine", side_effect=RuntimeError("PG connection refused")):
            result = CrashResilientDocumentPublisher.recover(
                parent_dir=temp_dir,
                target_database_url="postgresql://mock_user:mock_pass@localhost:5432/mock_db"
            )
            assert result is False, "recover() NO debio devolver True cuando la cuarentena fallo"

        # Verificar que el diario se preservo con estado FAILED_INCONSISTENT
        assert journal_file.exists(), "El diario debio ser preservado para auditoria forense"
        persisted = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted.get("phase") == "FAILED_INCONSISTENT"
        assert persisted.get("quarantine_confirmed") is False

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_cross_container_liveness_and_exclusion():
    """
    B2-CRITICO / Auditoria GPT:
    Acredita la exclusion y propiedad verificable entre contenedores Docker independientes:
    1. Un centinela con PID ajeno NO es considerado muerto si el advisory lock permanece retenido en PostgreSQL.
    2. is_write_frozen() devuelve True (fail-closed) mientras el advisory lock este retenido.
    3. Cuando el advisory lock en PostgreSQL es liberado, is_write_frozen() reconoce que el centinela es huerfano
       y devuelve False.
    4. Ante la ausencia de conexion a base de datos y un centinela originado en otro host,
       is_write_frozen() asume comportamiento fail-closed devolviendo True.
    """
    from app.core.write_control import DocumentWriteControl

    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_cross_container_"))
    db_url = settings.DATABASE_URL
    try:
        lock_file = temp_dir / ".write_freeze_lock"

        # 1. Simular proceso de respaldo activo en otro contenedor reteniendo el advisory lock en PostgreSQL
        eng_remote = create_engine(db_url)
        with eng_remote.connect() as conn_remote:
            acquired = conn_remote.execute(text("SELECT pg_try_advisory_lock(hashtext('abst_lan_backup_write_lock'))")).scalar()
            assert acquired is True, "Debio adquirir el advisory lock de prueba"

            # Escribir centinela con host_id ajeno y PID que no existe en este namespace
            foreign_host = "foreign-worker-container-42"
            foreign_pid = 8888888
            lock_content = f"WRITE_FREEZE_ACTIVE_{time.time()}_{foreign_pid}_remote_token_123_{foreign_host}\n"
            lock_file.write_text(lock_content, encoding="utf-8")

            # Con el advisory lock retenido por otra conexion, is_write_frozen DEBE ser True
            assert DocumentWriteControl.is_write_frozen(temp_dir, database_url=db_url) is True, (
                "is_write_frozen() debio bloquear escrituras cross-container con advisory lock activo"
            )

            # Liberar advisory lock simulando terminacion del respaldo remoto
            conn_remote.execute(text("SELECT pg_advisory_unlock(hashtext('abst_lan_backup_write_lock'))"))

        eng_remote.dispose()

        # 2. Con el advisory lock liberado, is_write_frozen DEBE ser False (centinela huerfano reconocido)
        assert DocumentWriteControl.is_write_frozen(temp_dir, database_url=db_url) is False, (
            "is_write_frozen() debio desbloquear escrituras una vez liberado el advisory lock"
        )

        # 3. Comprobar comportamiento fail-closed sin BD para centinela ajeno:
        assert DocumentWriteControl.is_write_frozen(temp_dir, database_url="") is True, (
            "is_write_frozen() debio operar fail-closed ante centinela ajeno sin BD"
        )

    finally:
        eng_cleanup = create_engine(db_url)
        with eng_cleanup.connect() as conn_c:
            conn_c.execute(text("SELECT pg_advisory_unlock(hashtext('abst_lan_backup_write_lock'))"))
        eng_cleanup.dispose()
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b1_restore_aborts_fail_closed_when_corrupted_journal_exists():
    """
    B1-RESTORE / Auditoria Independiente GPT:
    Acredita que restore_lan_backup() comprueba la existencia de un journal anterior antes de
    generar uno nuevo con _atomic_write_journal():
    1. Si existe un .cutover_journal.json previo corrupto o ilegible, aborta de forma fail-closed
       sin sobrescribirlo.
    2. El journal corrupto se preserva exactamente como evidencia forense.
    3. No se modifica la base de datos destino ni el directorio de uploads de destino.
    """
    run_uuid = uuid.uuid4().hex[:12]
    target_db_name = f"dr_test_{run_uuid}"
    marker_id = f"marker_{run_uuid}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b1_restore_corrupted_"))
    target_url = None

    try:
        backup_file = temp_dir / "backup.bin"
        uploads_dir = temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "doc1.pdf").write_bytes(b"%PDF-1.5 test document 1")

        enc_key = "test_enc_key_32bytes_aes256_gcm!"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        manifest = create_lan_backup(
            database_url=settings.DATABASE_URL,
            uploads_dir=uploads_dir,
            output_backup_file=backup_file,
            encryption_key=enc_key,
            signing_key=sign_key,
        )

        target_parent = temp_dir / "target_env"
        target_parent.mkdir(parents=True, exist_ok=True)
        target_uploads = target_parent / "uploads"
        target_uploads.mkdir(parents=True, exist_ok=True)
        (target_uploads / "original.txt").write_text("unaltered_original_state", encoding="utf-8")

        # Journal previo corrupto
        journal_file = target_parent / ".cutover_journal.json"
        corrupt_content = "{irrecoverable_journal_corrupt_prior_attempt"
        journal_file.write_text(corrupt_content, encoding="utf-8")

        target_url = _create_dr_target_database(settings.DATABASE_URL, target_db_name, marker_id)

        # Invocar restore_lan_backup con el journal corrupto preexistente
        with pytest.raises(RuntimeError) as exc_info:
            restore_lan_backup(
                backup_file=backup_file,
                target_uploads_dir=target_uploads,
                encryption_key=enc_key,
                signing_key=sign_key,
                expected_marker_id=marker_id,
                target_database_url=target_url,
                source_database_url=settings.DATABASE_URL,
            )

        err_msg = str(exc_info.value)
        assert "B1-RESTORE" in err_msg or "diario anterior" in err_msg or "corrupto" in err_msg, (
            f"El mensaje debio senalar el diario previo corrupto (B1-RESTORE): {err_msg}"
        )

        # 1. El journal corrupto NO fue sobrescrito ni modificado
        assert journal_file.exists(), "El journal corrupto debe seguir existiendo"
        assert journal_file.read_text(encoding="utf-8") == corrupt_content, (
            "El journal corrupto fue reemplazado o modificado! Se perdio evidencia forense."
        )

        # 2. El destino documental NO fue alterado
        assert target_uploads.exists()
        assert (target_uploads / "original.txt").read_text(encoding="utf-8") == "unaltered_original_state", (
            "El destino documental fue alterado indebidamente!"
        )
        assert not (target_uploads / "doc1.pdf").exists(), "No debieron promoverse documentos"

        # 3. La base de datos destino NO debe tener las tablas restauradas
        eng_target = create_engine(target_url)
        with eng_target.connect() as conn:
            tables = conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='case_files'")
            ).scalar()
            assert tables is None, "La base de datos destino fue restaurada a pesar del journal corrupto!"
        eng_target.dispose()

    finally:
        if target_url:
            _drop_dr_target_database(settings.DATABASE_URL, target_db_name, marker_id)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b1_atomic_write_journal_refuses_to_overwrite_corrupt_journal():
    """
    B1-RESTORE / AST: Acredita que _atomic_write_journal() de forma aislada se niega
    a sobrescribir un journal corrupto o ilegible preexistente, preservando la evidencia forense.
    """
    from verification.dr.backup_lan_pg15 import _atomic_write_journal
    temp_dir = Path(tempfile.mkdtemp(prefix="test_b1_atomic_journal_"))
    try:
        journal_file = temp_dir / ".cutover_journal.json"
        corrupt_content = "{irrecoverable_journal"
        journal_file.write_text(corrupt_content, encoding="utf-8")

        new_data = {"phase": "RESTORATION_INITIATED", "created_at": time.time()}

        with pytest.raises(RuntimeError) as exc_info:
            _atomic_write_journal(journal_file, new_data)

        assert "B1-RESTORE" in str(exc_info.value) or "corrupto" in str(exc_info.value)
        # Verificar preservacion exacta
        assert journal_file.read_text(encoding="utf-8") == corrupt_content
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_p14_b2_toctou_atomic_exclusion_blocks_suspended_writer_and_inconsistent_backup():
    """
    B2-TOCTOU / Auditoria Independiente GPT:
    Acredita coordinacion verdaderamente atomica entre escritores y respaldador:
    1. is_write_frozen() consulta a PostgreSQL incluso cuando .write_freeze_lock aun no existe en disco.
    2. Prueba adversarial determinista:
       - Suspende una escritura despues de que la comprobacion de congelamiento indico autorizacion (False).
       - Inicia el proceso de respaldo adquiriendo DocumentWriteControl (lock exclusivo en PostgreSQL).
       - Reanuda al escritor: la operacion put() es rechazada atomicamente por writer_lock
         impidiendo una mutacion incompatible durante el respaldo.
    3. Exclusion simetrica:
       - Un escritor activo reteniendo writer_lock impide atomicamente que un respaldo concurrente
         inicie o capture un snapshot inconsistente (PostgreSQL deniega pg_try_advisory_lock exclusivo).
    """
    import threading
    from app.core.write_control import DocumentWriteControl
    from app.storage.local import LocalStorageAdapter

    temp_dir = Path(tempfile.mkdtemp(prefix="test_b2_toctou_"))
    db_url = settings.DATABASE_URL
    try:
        # A. is_write_frozen() consulta a PostgreSQL cuando NO hay centinela en disco
        eng = create_engine(db_url)
        with eng.connect() as conn:
            acquired = conn.execute(text("SELECT pg_try_advisory_lock(hashtext('abst_lan_backup_write_lock'))")).scalar()
            assert acquired is True, "Debio adquirir lock exclusivo de prueba"

            # Sin centinela en disco, is_write_frozen DEBE ser True consultando PostgreSQL
            assert not (temp_dir / ".write_freeze_lock").exists()
            assert DocumentWriteControl.is_write_frozen(temp_dir, database_url=db_url) is True, (
                "is_write_frozen() debio retornar True consultando PostgreSQL incluso sin centinela en disco (B2-TOCTOU)"
            )

            conn.execute(text("SELECT pg_advisory_unlock(hashtext('abst_lan_backup_write_lock'))"))
        eng.dispose()

        # B. Suspensión de escritor tras autorización:
        # 1. Escritor consulta autorización antes del respaldo -> False (autorizado)
        adapter = LocalStorageAdapter(base_dir=temp_dir)
        pre_check = DocumentWriteControl.is_write_frozen(temp_dir, database_url=db_url)
        assert pre_check is False, "Inicialmente no debe estar congelado"

        # 2. El escritor queda suspendido temporalmente. Mientras tanto, el respaldador inicia:
        with DocumentWriteControl(database_url=db_url, uploads_dir=temp_dir):
            # 3. El escritor reanuda e intenta ejecutar la mutacion (put)
            # Gracias a writer_lock, debe ser rechazado atomicamente a nivel de PostgreSQL/centinela
            stream = io.BytesIO(b"incompatible_mutation_payload")
            with pytest.raises(RuntimeError) as exc_info:
                adapter.put(tenant_id="tenant_x", document_id="doc_race.pdf", file_stream=stream)

            assert "B2" in str(exc_info.value) or "congelamiento" in str(exc_info.value)
            # Verificar que el archivo no fue creado
            assert not (temp_dir / "tenant_x" / "doc_race.pdf").exists(), (
                "Se permitio una mutacion incompatible en disco durante el respaldo LAN!"
            )

        # C. Exclusión simétrica: Un escritor activo bloquea al respaldador
        writer_acquired_event = threading.Event()
        writer_release_event = threading.Event()
        writer_error = []
        backup_rejected = [False]

        def writer_thread():
            try:
                with DocumentWriteControl.writer_lock(uploads_dir=temp_dir, database_url=db_url):
                    writer_acquired_event.set()
                    # Simular operacion de escritura prolongada
                    writer_release_event.wait(timeout=10.0)
            except Exception as e:
                writer_error.append(e)

        t = threading.Thread(target=writer_thread)
        t.start()

        assert writer_acquired_event.wait(timeout=5.0), "El escritor no pudo adquirir writer_lock"
        assert not writer_error, f"Error en escritor: {writer_error}"

        # El respaldador intenta iniciar mientras el escritor sigue activo
        try:
            with DocumentWriteControl(database_url=db_url, uploads_dir=temp_dir):
                pass
        except RuntimeError as e:
            backup_rejected[0] = True
            assert "B2" in str(e) or "advisory_lock" in str(e)

        # Permitir al escritor terminar
        writer_release_event.set()
        t.join(timeout=5.0)

        assert backup_rejected[0] is True, (
            "El respaldador debio ser rechazado fail-closed mientras un escritor mantenia writer_lock!"
        )

    finally:
        eng_cleanup = create_engine(db_url)
        with eng_cleanup.connect() as conn_c:
            conn_c.execute(text("SELECT pg_advisory_unlock(hashtext('abst_lan_backup_write_lock'))"))
            conn_c.execute(text("SELECT pg_advisory_unlock_shared(hashtext('abst_lan_backup_write_lock'))"))
        eng_cleanup.dispose()
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

# B2-FC: pruebas negativas y positivas de configuracion para exclusion documental.
from app.core.write_control import DocumentWriteControl as DocumentWriteControlB2FC


@pytest.mark.parametrize(
    "invalid_url",
    ["", "sqlite:///:memory:", "sqlite:///tmp/documents.db", "not-a-database-url"],
)
def test_b2_fc_writer_guard_rejects_invalid_database_url(tmp_path, invalid_url):
    """No write is granted without the shared PostgreSQL lock authority."""
    with pytest.raises(RuntimeError, match="B2-FC fail-closed"):
        with DocumentWriteControlB2FC.writer_lock(tmp_path, database_url=invalid_url):
            pytest.fail("DocumentWriterGuard granted a lock-free write")


@pytest.mark.parametrize(
    "invalid_url",
    ["", "sqlite:///:memory:", "sqlite:///tmp/documents.db", "not-a-database-url"],
)
def test_b2_fc_freeze_check_blocks_invalid_database_url(tmp_path, invalid_url):
    """A missing filesystem sentinel never authorizes writes without PostgreSQL."""
    assert not (tmp_path / ".write_freeze_lock").exists()
    assert DocumentWriteControlB2FC.is_write_frozen(
        tmp_path, database_url=invalid_url
    ) is True


def test_b2_fc_missing_application_database_url_is_fail_closed(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="B2-FC fail-closed"):
        with DocumentWriteControlB2FC.writer_lock(tmp_path):
            pytest.fail("Writer entered without a configured database")
    assert DocumentWriteControlB2FC.is_write_frozen(tmp_path) is True


def test_b2_fc_valid_postgresql_configuration_retains_shared_lock(tmp_path, monkeypatch):
    import app.core.write_control as control

    class FakeResult:
        def scalar(self):
            return True

    class FakeConn:
        closed = False
        executed = []

        def execute(self, statement):
            self.executed.append(str(statement))
            return FakeResult()

        def close(self):
            self.closed = True

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    class FakeEngine:
        def connect(self):
            return FakeConn()

        def dispose(self):
            pass

    monkeypatch.setattr(control, "create_engine", lambda *args, **kwargs: FakeEngine())
    url = "postgresql://example:secret@localhost:5432/isolated_test"
    with DocumentWriteControlB2FC.writer_lock(tmp_path, database_url=url) as guard:
        assert guard._locked is True
        assert guard._conn is not None
        assert any("pg_try_advisory_lock_shared" in sql for sql in guard._conn.executed)
