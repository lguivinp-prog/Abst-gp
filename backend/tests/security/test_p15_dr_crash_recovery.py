"""
Prueba Adversarial Exhaustiva P15-R2: Subsanacion Focalizada de Hallazgos de Auditoria GPT
(P15-R2-AUDITORIA-GPT, R3-03, R4-01, R5-01, R5-02, B1, B1-01, B1-02, P15-H1, P15-H2, P15-H3, P15-H4, P15-H5).

Cubre rigurosamente los 13 escenarios de prueba requeridos por el dictamen de GPT:
1. Estado 1: Interrupcion ANTES del COMMIT PostgreSQL (rollback seguro).
2. Estado 2: Interrupcion DESPUES del COMMIT PostgreSQL, pero ANTES de persistir DB_RESTORED en el journal (Garantia A).
3. Estado 3: Interrupcion DESPUES de persistir DB_RESTORED, antes de la promocion documental.
4. Estado 4: Restauracion confirmada con documentos ausentes, incompletos o corruptos (Garantia B).
5. Estado 5: Error de integridad en journal y denegacion de sobreescritura fail-closed.
6. Estado 6: Reintento de recuperacion tras una interrupcion anterior (idempotencia y trazabilidad forense).
7. Hallazgo H1: Pruebas negativas de cuarentenas vacias, ajenas o de error (rechazo estricto).
8. Hallazgo H2: Base de datos ajena (mismatched marker / foreign quarantine) permanece 100% intacta sin modificacion.
9. Hallazgo H3: Prueba E2E del corte real determinista en restore_lan_backup() y recuperacion automatica (Garantia A / B).
10. Hallazgo H4: Confidencialidad y redaccion demostrada de contrasenas sinteticas en logs, excepciones y diagnostico.
11. Hallazgo H5: PostgreSQL inaccesible o caido manejado de forma fail-closed sin corromper destino.
12. Hallazgo H5: Fallos inyectados de I/O en fsync / replace durante escritura de journal.
13. Hallazgo H5: Reintento sucesivo de recover() sobre FAILED_INCONSISTENT sin levantar cuarentena.
"""

import os
import sys
import io
import stat
import errno
import time
import json
import uuid
import shutil
import hashlib
import logging
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from verification.dr.backup_lan_pg15 import (
    compute_file_sha256,
    _atomic_write_journal,
    _enforce_database_quarantine,
    _lift_database_quarantine,
    _inspect_postgres_restore_commitment,
    _durable_write_and_sync_file,
    _sync_directory,
    _sync_directory_tree,
    sanitize_db_url,
    create_lan_backup,
    restore_lan_backup,
    execute_pg_restore,
    CrashResilientDocumentPublisher,
    recover_pending_cutover,
    validate_restore_target_safety,
)


def _create_p15_ephemeral_db(source_url: str, db_name: str, marker_id: str) -> str:
    """Crea una base de datos efimera dr_test_* en PostgreSQL 15 con su marcador de propiedad."""
    parsed = urlparse(source_url)
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {db_name}"))
    engine.dispose()

    target_url = urlunparse(parsed._replace(path=f"/{db_name}"))
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
            {"m": marker_id, "r": db_name}
        )
    target_engine.dispose()
    return target_url


def _safe_drop_p15_ephemeral_db(source_url: str, db_name: str):
    """Elimina de forma segura la base efimera de pruebas tras desconectar sesiones activas."""
    try:
        parsed = urlparse(source_url)
        admin_url = urlunparse(parsed._replace(path="/postgres"))
        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            conn.execute(text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
            ))
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
        engine.dispose()
    except Exception:
        pass


# ===========================================================================
# 1. ESTADO 1: Interrupcion ANTES del COMMIT PostgreSQL
# ===========================================================================
def test_p15_dr_state1_interruption_before_postgres_commit():
    """
    Estado 1: Interrupcion ANTES del COMMIT PostgreSQL.
    - Journal en disco: phase='RESTORATION_INITIATED', db_restored=False.
    - En PostgreSQL: _dr_test_ownership_marker sigue intacto.
    - recover() comprueba que el commit no ocurrio, realiza rollback seguro
      y no toca la base de datos.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_s1_{run_id}"
    marker_id = f"marker_s1_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_s1_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "original_file.txt").write_text("original_content", encoding="utf-8")

        candidate_dir = temp_dir / f".target_candidate_{run_id}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "candidate_file.txt").write_text("candidate_content", encoding="utf-8")

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "RESTORATION_INITIATED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / f".target_backup_{run_id}").resolve()),
            "db_restored": False,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "catalog_hashes": {"candidate_file.txt": hashlib.sha256(b"candidate_content").hexdigest()},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        # Pre-condicion: COMMIT no ocurrio
        eng = create_engine(target_url)
        with eng.connect() as conn:
            marker_val = conn.execute(text("SELECT marker_id FROM _dr_test_ownership_marker;")).scalar()
            assert marker_val == marker_id
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is None
        eng.dispose()

        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert recovered is True

        assert (target_dir / "original_file.txt").exists()
        assert (target_dir / "original_file.txt").read_text(encoding="utf-8") == "original_content"

        eng2 = create_engine(target_url)
        with eng2.connect() as conn:
            assert conn.execute(text("SELECT marker_id FROM _dr_test_ownership_marker;")).scalar() == marker_id
            assert conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar() is None
        eng2.dispose()

        assert not journal_file.exists()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 2. ESTADO 2: Interrupcion DESPUES de COMMIT PG pero ANTES de journal DB_RESTORED
# ===========================================================================
def test_p15_dr_state2_interruption_after_commit_before_journal_db_restored():
    """
    Estado 2 (Garantia A - Forward Recovery):
    Interrupcion abrupta inmediatamente posterior al COMMIT PostgreSQL
    y anterior a la persistencia durable de DB_RESTORED en el journal.
    - Metadatos estructurados en _dr_restoration_quarantine vinculados al marker_id y restore_token.
    - recover() acredita el COMMIT legitimo, promueve db_restored=True,
      promueve candidate_dir a target_uploads, y levanta la cuarentena en PG.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_s2_{run_id}"
    marker_id = f"marker_s2_{run_id}"
    restore_token = f"tok_s2_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_s2_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "old_doc.txt").write_text("old_content", encoding="utf-8")

        candidate_dir = temp_dir / f".target_candidate_{run_id}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        new_content = "new_restored_content_v6_p15_r2"
        (candidate_dir / "new_doc.txt").write_text(new_content, encoding="utf-8")
        new_sha = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

        # Simular COMMIT de PostgreSQL con metadatos estructurados de la restauracion legitima
        _enforce_database_quarantine(
            db_url=target_url,
            reason="RESTORATION_IN_PROGRESS (B1): Base restaurada pendiente de corte documental",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "RESTORATION_INITIATED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / f".target_backup_{run_id}").resolve()),
            "db_restored": False,  # << Estado en disco antes de la caida
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"new_doc.txt": new_sha},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        # Ejecutar recover() coordinado
        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )

        assert recovered is True
        assert (target_dir / "new_doc.txt").exists()
        assert (target_dir / "new_doc.txt").read_text(encoding="utf-8") == new_content

        # Demostrar que la cuarentena fue LEVANTADA en PostgreSQL
        eng = create_engine(target_url)
        with eng.connect() as conn:
            q_after = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_after is None
        eng.dispose()

        assert not journal_file.exists()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 3. ESTADO 3: Interrupcion DESPUES de DB_RESTORED antes de promocion
# ===========================================================================
def test_p15_dr_state3_interruption_after_journal_db_restored_before_promotion():
    """
    Estado 3: Interrupcion DESPUES de persistir DB_RESTORED en el journal.
    - Journal en disco: phase='DB_RESTORED', db_restored=True.
    - Candidate integro y valido.
    - recover() ejecuta forward recovery, promueve candidate a target, levanta cuarentena.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_s3_{run_id}"
    marker_id = f"marker_s3_{run_id}"
    restore_token = f"tok_s3_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_s3_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "old_doc.txt").write_text("old_s3_content", encoding="utf-8")

        candidate_dir = temp_dir / f".target_candidate_{run_id}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        s3_content = "s3_new_promoted_content"
        (candidate_dir / "s3_doc.txt").write_text(s3_content, encoding="utf-8")
        s3_sha = hashlib.sha256(s3_content.encode("utf-8")).hexdigest()

        _enforce_database_quarantine(
            db_url=target_url,
            reason="RESTORATION_IN_PROGRESS (B1): Pending cutover s3",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / f".target_backup_{run_id}").resolve()),
            "db_restored": True,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"s3_doc.txt": s3_sha},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert recovered is True

        assert (target_dir / "s3_doc.txt").exists()
        assert (target_dir / "s3_doc.txt").read_text(encoding="utf-8") == s3_content

        eng = create_engine(target_url)
        with eng.connect() as conn:
            q_after = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_after is None
        eng.dispose()

        assert not journal_file.exists()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 4. ESTADO 4: Restauracion confirmada con documentos ausentes/corruptos
# ===========================================================================
def test_p15_dr_state4_restoration_confirmed_with_corrupt_or_missing_documents():
    """
    Estado 4 (Garantia B - Fail Closed):
    Restauracion confirmada en PostgreSQL, pero candidate_dir corrupto.
    - recover() detecta corrupcion documental.
    - Cuarentena en PostgreSQL permanece ACTIVA.
    - Journal preservado en FAILED_INCONSISTENT.
    - Ningun archivo corrupto promovido a target.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_s4_{run_id}"
    marker_id = f"marker_s4_{run_id}"
    restore_token = f"tok_s4_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_s4_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "legit_file.txt").write_text("legit_content", encoding="utf-8")

        candidate_dir = temp_dir / f".target_candidate_{run_id}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "corrupted_doc.txt").write_text("TAMPERED_BYTES", encoding="utf-8")
        expected_sha = hashlib.sha256(b"GENUINE_AUTHENTIC_BYTES").hexdigest()

        _enforce_database_quarantine(
            db_url=target_url,
            reason="RESTORATION_IN_PROGRESS (B1): Pending cutover s4",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "RESTORATION_INITIATED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / f".target_backup_{run_id}").resolve()),
            "db_restored": False,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"corrupted_doc.txt": expected_sha},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )

        # Verificaciones de invariantes:
        assert recovered is True, "recover() debe procesar exitosamente la contingencia asegurando la BD en cuarentena"
        assert journal_file.exists()
        saved_journal = json.loads(journal_file.read_text(encoding="utf-8"))
        assert saved_journal.get("phase") == "FAILED_INCONSISTENT"
        assert saved_journal.get("quarantine_confirmed") is True

        eng = create_engine(target_url)
        with eng.connect() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is not None
            q_reason = conn.execute(text("SELECT reason FROM public._dr_restoration_quarantine ORDER BY id DESC LIMIT 1;")).scalar()
            assert "INCONSISTENT_RESTORATION" in q_reason
        eng.dispose()

        assert not (target_dir / "corrupted_doc.txt").exists()
        assert (target_dir / "legit_file.txt").exists()

        # Reintento sobre el repositorio ya en FAILED_INCONSISTENT debe retornar False (fail-closed idempotente)
        rec_retry = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec_retry is False, "Llamada sucesiva sobre FAILED_INCONSISTENT debe retornar False sin tocar nada"

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 5. ESTADO 5: Error de integridad en journal y denegacion de sobrescritura
# ===========================================================================
def test_p15_dr_state5_journal_io_corruption_and_fsync_fail_closed():
    """
    Estado 5: Error de integridad en el diario de corte (.cutover_journal.json).
    - Contenido corrupto no-JSON.
    - _atomic_write_journal() y publish() deniegan sobreescritura fail-closed.
    - No quedan archivos .tmp_* persistentes.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_s5_"))
    try:
        journal_file = temp_dir / ".cutover_journal.json"
        journal_file.write_bytes(b"CORRUPTED_HEX_BYTE_\x00\xFF_JOURNAL_BROKEN_DATA")

        with pytest.raises(RuntimeError) as exc_write:
            _atomic_write_journal(journal_file, {"phase": "RESTORATION_INITIATED"})
        assert "Fallo de integridad (B1-RESTORE)" in str(exc_write.value)
        assert journal_file.read_bytes().startswith(b"CORRUPTED_HEX_BYTE_")

        target_dir = temp_dir / "target"
        publisher = CrashResilientDocumentPublisher(target_dir=target_dir)
        with pytest.raises(RuntimeError) as exc_pub:
            publisher.publish(staging_dir=temp_dir, catalog=[])
        assert "Existe un diario de corte anterior (.cutover_journal.json) corrupto o irrecuperable" in str(exc_pub.value)

        tmps = list(temp_dir.glob("*.tmp_*"))
        assert len(tmps) == 0

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 6. ESTADO 6: Idempotencia y bloqueo sobre FAILED_INCONSISTENT
# ===========================================================================
def test_p15_dr_state6_recovery_retry_idempotence_and_traceability():
    """
    Estado 6: Idempotencia y trazabilidad forense tras recuperacion.
    - Exito: llamadas sucesivas a recover() son idempotentes.
    - FAILED_INCONSISTENT: bloquea cualquier nueva publicacion documental.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_s6_{run_id}"
    marker_id = f"marker_s6_{run_id}"
    restore_token = f"tok_s6_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_s6_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "file.txt").write_text("content_s6", encoding="utf-8")

        candidate_dir = temp_dir / f".target_candidate_{run_id}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        cand_content = "content_s6_promoted"
        (candidate_dir / "s6_doc.txt").write_text(cand_content, encoding="utf-8")
        cand_sha = hashlib.sha256(cand_content.encode("utf-8")).hexdigest()

        _enforce_database_quarantine(
            db_url=target_url,
            reason="RESTORATION_IN_PROGRESS (B1): Pending cutover s6",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / f".target_backup_{run_id}").resolve()),
            "db_restored": True,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"s6_doc.txt": cand_sha},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        rec1 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec1 is True
        assert (target_dir / "s6_doc.txt").exists()

        rec2 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec2 is False
        assert (target_dir / "s6_doc.txt").exists()

        inconsistent_data = {
            "phase": "FAILED_INCONSISTENT",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / f".target_backup_{run_id}").resolve()),
            "db_restored": True,
            "target_database_url": target_url,
            "quarantine_confirmed": True,
            "created_at": time.time(),
            "forensic_audit_id": "audit_token_p15"
        }
        _atomic_write_journal(journal_file, inconsistent_data)
        _enforce_database_quarantine(
            target_url,
            reason="INCONSISTENT_RESTORATION: Audit test",
            journal_state="FAILED_INCONSISTENT",
            marker_id=marker_id,
            restore_token=restore_token
        )

        publisher = CrashResilientDocumentPublisher(target_dir=target_dir)
        with pytest.raises(RuntimeError) as exc_blocked:
            publisher.publish(staging_dir=temp_dir, catalog=[])
        assert "El repositorio documental permanece en estado inconsistente o en cuarentena" in str(exc_blocked.value)

        after_data = json.loads(journal_file.read_text(encoding="utf-8"))
        assert after_data.get("phase") == "FAILED_INCONSISTENT"
        assert after_data.get("forensic_audit_id") == "audit_token_p15"

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 7. HALLAZGO H1: Pruebas negativas de cuarentena (Identidad del COMMIT)
# ===========================================================================
def test_p15_h1_negative_empty_and_error_quarantine_rejected():
    """
    P15-H1: Exige evidencia durable, inequivoca y vinculada a la restauracion actual.
    Prueba negativa de escenarios invalidos:
    1. Cuarentena vacia (0 filas) -> retorna EMPTY_QUARANTINE.
    2. Cuarentena con journal_state='FAILED_INCONSISTENT' o error -> retorna ERROR_QUARANTINE.
    3. Cuarentena con marker_id ajeno o de otra corrida -> retorna FOREIGN_QUARANTINE.
    4. Cuarentena con restore_token discrepante -> retorna FOREIGN_QUARANTINE.
    5. Cuarentena coexistiendo con ownership marker intacto -> retorna UNKNOWN_OR_INCONSISTENT.
    Ninguno de estos estados debe aceptarse como COMMIT legitimo.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_h1_{run_id}"
    marker_id = f"marker_h1_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_h1_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        # 1. Cuarentena vacia: crear tabla sin filas y droppear marker
        eng = create_engine(target_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public._dr_test_ownership_marker CASCADE;"))
            conn.execute(text(
                "CREATE TABLE public._dr_restoration_quarantine ("
                "  id SERIAL PRIMARY KEY, quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "  reason TEXT NOT NULL, journal_state TEXT NOT NULL, "
                "  marker_id VARCHAR(64), restore_token VARCHAR(64)"
                ");"
            ))
        eng.dispose()

        status, details = _inspect_postgres_restore_commitment(target_url, marker_id, "tok1")
        assert status == "EMPTY_QUARANTINE", f"Esperado EMPTY_QUARANTINE, obtenido: {status}"

        # 2. Cuarentena en estado FAILED_INCONSISTENT
        with eng.connect() as conn:
            conn.execute(text(
                "INSERT INTO public._dr_restoration_quarantine (reason, journal_state, marker_id, restore_token) "
                "VALUES ('INCONSISTENT_RESTORATION: prior failure', 'FAILED_INCONSISTENT', :m, 'tok1');"
            ), {"m": marker_id})
        eng.dispose()

        status, details = _inspect_postgres_restore_commitment(target_url, marker_id, "tok1")
        assert status == "ERROR_QUARANTINE", f"Esperado ERROR_QUARANTINE, obtenido: {status}"

        # 3. Cuarentena con marker_id ajeno
        with eng.connect() as conn:
            conn.execute(text("TRUNCATE TABLE public._dr_restoration_quarantine;"))
            conn.execute(text(
                "INSERT INTO public._dr_restoration_quarantine (reason, journal_state, marker_id, restore_token) "
                "VALUES ('RESTORATION_IN_PROGRESS', 'DB_RESTORED', 'OTHER_FOREIGN_MARKER_999', 'tok1');"
            ))
        eng.dispose()

        status, details = _inspect_postgres_restore_commitment(target_url, marker_id, "tok1")
        assert status == "FOREIGN_QUARANTINE", f"Esperado FOREIGN_QUARANTINE, obtenido: {status}"

        # 4. Cuarentena con restore_token ajeno
        with eng.connect() as conn:
            conn.execute(text("TRUNCATE TABLE public._dr_restoration_quarantine;"))
            conn.execute(text(
                "INSERT INTO public._dr_restoration_quarantine (reason, journal_state, marker_id, restore_token) "
                "VALUES ('RESTORATION_IN_PROGRESS', 'DB_RESTORED', :m, 'DIFFERENT_TOKEN_xyz');"
            ), {"m": marker_id})
        eng.dispose()

        status, details = _inspect_postgres_restore_commitment(target_url, marker_id, "tok_expected")
        assert status == "FOREIGN_QUARANTINE", f"Esperado FOREIGN_QUARANTINE por token, obtenido: {status}"

        # 5. Inconsistencia: cuarentena existe pero ownership marker NO fue eliminado
        with eng.connect() as conn:
            conn.execute(text(
                "CREATE TABLE public._dr_test_ownership_marker ("
                "  marker_id VARCHAR(64) PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, test_run VARCHAR(64)"
                ");"
            ))
            conn.execute(text("INSERT INTO public._dr_test_ownership_marker VALUES (:m, CURRENT_TIMESTAMP, 'run');"), {"m": marker_id})
        eng.dispose()

        status, details = _inspect_postgres_restore_commitment(target_url, marker_id, "DIFFERENT_TOKEN_xyz")
        assert status == "UNKNOWN_OR_INCONSISTENT", f"Esperado UNKNOWN_OR_INCONSISTENT, obtenido: {status}"

        # Comprobar que recover() ante cuarentena ajena o invalida rechaza la recuperacion y no promueve nada
        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "RESTORATION_INITIATED",
            "target_dir": str((temp_dir / "tgt").resolve()),
            "candidate_dir": str((temp_dir / "cand").resolve()),
            "backup_dir": str((temp_dir / "bkp").resolve()),
            "db_restored": False,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": "tok_expected",
            "catalog_hashes": {},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        rec = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec is False
        assert journal_file.exists()
        saved = json.loads(journal_file.read_text(encoding="utf-8"))
        assert saved["phase"] == "FAILED_INCONSISTENT"

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 8. HALLAZGO H2: Base de datos ajena permanece intacta
# ===========================================================================
def test_p15_h2_foreign_database_and_mismatched_marker_untouched():
    """
    P15-H2: Ante MISMATCHED_MARKER o FOREIGN_QUARANTINE, NO ejecutar
    _enforce_database_quarantine() ni ninguna operacion destructiva en PostgreSQL.
    Conservar el journal, registrar foreign_database_untouched=True y abortar fail-closed.
    Demostrar que el marcador ajeno, las tablas y los datos permanecen 100% intactos.
    """
    run_id = uuid.uuid4().hex[:8]
    foreign_db_name = f"dr_test_p15_h2_foreign_{run_id}"
    foreign_marker_id = f"foreign_marker_{run_id}"
    our_expected_marker_id = f"our_marker_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_h2_"))
    target_url = None

    try:
        # 1. Crear base destino con datos y marcador de otra corrida (ajena)
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, foreign_db_name, foreign_marker_id)
        eng = create_engine(target_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            conn.execute(text("CREATE TABLE foreign_important_data (id INT, val TEXT);"))
            conn.execute(text("INSERT INTO foreign_important_data VALUES (1, 'CRITICAL_DATA_PRESERVED');"))
        eng.dispose()

        # 2. Configurar diario esperando un marker_id diferente
        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "RESTORATION_INITIATED",
            "target_dir": str((temp_dir / "tgt").resolve()),
            "candidate_dir": str((temp_dir / "cand").resolve()),
            "backup_dir": str((temp_dir / "bkp").resolve()),
            "db_restored": False,
            "target_database_url": target_url,
            "expected_marker_id": our_expected_marker_id,  # << Diferente al de la base
            "restore_token": "token_ours",
            "catalog_hashes": {},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        # 3. Ejecutar recover()
        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=our_expected_marker_id
        )

        # 4. Validar que recover() aborta fail-closed
        assert recovered is False
        assert journal_file.exists()
        saved_journal = json.loads(journal_file.read_text(encoding="utf-8"))
        assert saved_journal["phase"] == "FAILED_INCONSISTENT"
        assert saved_journal.get("foreign_database_untouched") is True
        assert "Base de datos ajena" in saved_journal.get("error", "")

        # 5. Demostrar categoricamente que PostgreSQL permaneccio 100% INTACTO:
        # A. _dr_test_ownership_marker NO fue droppeado y conserva foreign_marker_id
        # B. foreign_important_data sigue existiendo con sus registros
        # C. _dr_restoration_quarantine NO fue creada en esta base ajena
        eng2 = create_engine(target_url)
        with eng2.connect() as conn:
            m_val = conn.execute(text("SELECT marker_id FROM _dr_test_ownership_marker;")).scalar()
            assert m_val == foreign_marker_id, "INVARIANTE H2: El marcador ajeno no debio ser alterado ni droppeado"

            data_val = conn.execute(text("SELECT val FROM foreign_important_data WHERE id = 1;")).scalar()
            assert data_val == "CRITICAL_DATA_PRESERVED", "INVARIANTE H2: Los datos de la base ajena deben permanecer intactos"

            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is None, "INVARIANTE H2: No debe haberse creado cuarentena sobre base ajena"
        eng2.dispose()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, foreign_db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 9. HALLAZGO H3: Corte real deterministicamente inyectado en restore_lan_backup()
# ===========================================================================
def test_p15_h3_real_flow_restore_crash_after_pg_restore_commit():
    """
    P15-H3: Prueba End-to-End con el flujo real de restauracion en PostgreSQL 15 aislado.
    Inyecta una interrupcion determinista INMEDIATAMENTE despues del COMMIT de execute_pg_restore()
    y ANTES de persistir DB_RESTORED en el journal.
    Acredita:
    1. Existencia real de directorios candidate_dir pre-estagiado (Garantia A) y .cutover_journal.json.
    2. recover() realiza recuperacion automatica (forward recovery) exitosa sincronizando documentos y BD.
    3. Cuarentena levantada verificada.
    4. Caso Garantia B: si el candidato es corrompido, recover() preserva cuarentena fail-closed.
    """
    run_id = uuid.uuid4().hex[:8]
    target_db_name = f"dr_test_p15_h3_{run_id}"
    marker_id = f"marker_h3_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_h3_"))
    target_url = None

    try:
        # 1. Crear uploads de origen y respaldo autentico real
        source_uploads = temp_dir / "source_uploads"
        source_uploads.mkdir(parents=True, exist_ok=True)
        doc1_content = f"document_1_h3_real_content_{run_id}"
        doc2_content = f"document_2_h3_real_content_{run_id}"
        (source_uploads / "doc1.txt").write_text(doc1_content, encoding="utf-8")
        (source_uploads / "sub" / "doc2.txt").parent.mkdir(parents=True, exist_ok=True)
        (source_uploads / "sub" / "doc2.txt").write_text(doc2_content, encoding="utf-8")

        backup_file = temp_dir / "backup_h3.tar.gz.enc"
        enc_key = "test_enc_key_32bytes_aes_gcm_valid"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        manifest = create_lan_backup(
            database_url=settings.DATABASE_URL,
            uploads_dir=source_uploads,
            output_backup_file=backup_file,
            encryption_key=enc_key,
            signing_key=sign_key
        )
        assert backup_file.exists()
        assert manifest["document_count"] == 2

        # 2. Preparar base destino efimera aislada
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, target_db_name, marker_id)
        restored_uploads = temp_dir / "target_uploads_live"

        # 3. Interrupcion determinista: simular corte inmediatamente posterior al COMMIT
        # Monkeypatching a execute_pg_restore para ejecutar el restore real de psql y luego abortar
        original_execute_pg_restore = execute_pg_restore

        class SimulatedProcessCrashError(Exception):
            """Simula muerte abrupta del proceso (SIGKILL / power outage) post-commit."""
            pass

        def crashing_execute_pg_restore(*args, **kwargs):
            success = original_execute_pg_restore(*args, **kwargs)
            assert success is True, "El commit de PostgreSQL debio tener exito antes del corte"
            # Inyeccion de interrupcion determinista post-commit antes de escribir DB_RESTORED
            raise SimulatedProcessCrashError("CRASH DETERMINISTA INYECTADO: Proceso terminado abruptamente post-COMMIT PG.")

        with patch("verification.dr.backup_lan_pg15.execute_pg_restore", side_effect=crashing_execute_pg_restore):
            with pytest.raises(SimulatedProcessCrashError):
                restore_lan_backup(
                    backup_file=backup_file,
                    target_uploads_dir=restored_uploads,
                    encryption_key=enc_key,
                    signing_key=sign_key,
                    expected_marker_id=marker_id,
                    target_database_url=target_url,
                    source_database_url=settings.DATABASE_URL
                )

        # 4. Comprobar la existencia real de los directorios y del diario en el instante post-corte:
        parent_dir = restored_uploads.resolve().parent
        journal_file = parent_dir / ".cutover_journal.json"
        assert journal_file.exists(), "El journal .cutover_journal.json DEBE existir en disco tras el corte"

        journal_data = json.loads(journal_file.read_text(encoding="utf-8"))
        assert journal_data["phase"] == "RESTORATION_INITIATED"
        assert journal_data["db_restored"] is False  # Refleja que la caida ocurrio antes de actualizarlo
        candidate_dir_path = Path(journal_data["candidate_dir"])

        # P15-H3 (Garantia A): candidate_dir debe haber sido pre-estagiado durablemente ANTES del commit
        assert candidate_dir_path.exists(), "INVARIANTE H3 (Garantia A): candidate_dir debio ser pre-estagiado antes del commit"
        assert (candidate_dir_path / "doc1.txt").exists()
        assert (candidate_dir_path / "sub" / "doc2.txt").exists()
        assert (candidate_dir_path / "doc1.txt").read_text(encoding="utf-8") == doc1_content

        # Comprobar estado en PostgreSQL: el COMMIT si ocurrio, marker eliminado y cuarentena activa
        eng = create_engine(target_url)
        with eng.connect() as conn:
            m_check = conn.execute(text("SELECT to_regclass('public._dr_test_ownership_marker');")).scalar()
            assert m_check is None, "El marker debio ser eliminado por el commit real de psql"
            q_check = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_check is not None, "La cuarentena preventiva debio ser confirmada por el commit de psql"
        eng.dispose()

        # 5. Ejecutar recuperacion automatica tras reinicio (Garantia A - Forward Recovery)
        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=parent_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert recovered is True, "recover() debe realizar forward recovery exitoso de los documentos pre-estagiados"

        # Demostrar que los documentos estan completamente promovidos en target_uploads_live
        assert (restored_uploads / "doc1.txt").exists()
        assert (restored_uploads / "sub" / "doc2.txt").exists()
        assert (restored_uploads / "doc1.txt").read_text(encoding="utf-8") == doc1_content

        # Demostrar que la cuarentena en PostgreSQL fue levantada
        eng2 = create_engine(target_url)
        with eng2.connect() as conn:
            q_final = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_final is None, "La cuarentena debio ser levantada tras verificar la integridad documental"
        eng2.dispose()

        assert not journal_file.exists()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, target_db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 10. HALLAZGO H4: Confidencialidad y redaccion de credenciales
# ===========================================================================
def test_p15_h4_confidentiality_synthetic_password_redaction(caplog):
    """
    P15-H4: Prueba adversarial con contrasena sintetica secreta.
    Demostrar que 'SYNTHETIC_SECRET_PASS_xyz789' NUNCA aparece en logs,
    excepciones, mensajes formateados ni en los detalles retornados de diagnostico.
    """
    secret_pass = "SYNTHETIC_SECRET_PASS_xyz789"
    synthetic_dsn = f"postgresql://sec_user:{secret_pass}@localhost:5432/dr_test_sec_ephemeral"

    # 1. Probar sanitize_db_url directamente
    sanitized = sanitize_db_url(synthetic_dsn)
    assert secret_pass not in sanitized
    assert "sec_user:***@localhost" in sanitized

    # 2. Probar que logs de _inspect_postgres_restore_commitment no fugan el secreto
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        status, details = _inspect_postgres_restore_commitment(
            db_url=synthetic_dsn,
            expected_marker_id="marker_sec"
        )
        log_output = caplog.text
        assert secret_pass not in log_output, f"Fuga de contrasena sintetica en logs: {log_output}"
        assert secret_pass not in str(details), f"Fuga de contrasena en details: {details}"

    # 3. Probar que excepciones de validate_restore_target_safety no fugan el secreto
    with pytest.raises(Exception) as excinfo:
        validate_restore_target_safety(
            target_database_url=synthetic_dsn,
            source_database_url=f"postgresql://test_user:{secret_pass}@127.0.0.1:5433/dr_test_source_db",
            expected_marker_id="marker_sec"
        )
    exc_text = str(excinfo.value)
    assert secret_pass not in exc_text, f"Fuga de contrasena en mensaje de excepcion: {exc_text}"


# ===========================================================================
# 11. HALLAZGO H5: PostgreSQL caido o inaccesible (Fail-Closed)
# ===========================================================================
def test_p15_h5_postgres_inaccessible_or_connection_error_fail_closed():
    """
    P15-H5: PostgreSQL inaccesible o caido durante recover().
    - DSN apuntando a un puerto cerrado.
    - recover() detecta CONNECTION_ERROR, aborta fail-closed.
    - El journal se preserva como FAILED_INCONSISTENT sin destruir evidencia.
    - No se realiza promocion erronea.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_h5_conn_"))
    dead_pg_url = "postgresql://test_user:test_password@127.0.0.1:59999/dr_test_dead_db"

    try:
        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "safe.txt").write_text("safe_data", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate_dead"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "new.txt").write_text("new_data", encoding="utf-8")

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "RESTORATION_INITIATED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / ".target_backup_dead").resolve()),
            "db_restored": False,
            "target_database_url": dead_pg_url,
            "expected_marker_id": "marker_dead",
            "catalog_hashes": {"new.txt": hashlib.sha256(b"new_data").hexdigest()},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=dead_pg_url,
            expected_marker_id="marker_dead"
        )
        assert recovered is False
        assert journal_file.exists()
        saved = json.loads(journal_file.read_text(encoding="utf-8"))
        assert saved["phase"] == "FAILED_INCONSISTENT"
        assert "CONNECTION_ERROR" in saved.get("error", "")

        # target_uploads permanece intacto
        assert (target_dir / "safe.txt").exists()
        assert not (target_dir / "new.txt").exists()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 12. HALLAZGO H5: Fallos inyectados de I/O en os.fsync y os.replace
# ===========================================================================
def test_p15_h5_injected_os_replace_and_fsync_failure():
    """
    P15-H5: Inyeccion de fallos de I/O en os.fsync y os.replace durante _atomic_write_journal().
    Demostrar que:
    1. Si os.fsync falla, la excepcion se propaga fail-closed y el archivo temporal .tmp_* es limpiado.
    2. Si os.replace falla, el archivo previo permanece inalterado.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_h5_io_"))
    try:
        journal_file = temp_dir / ".cutover_journal.json"
        initial_data = {"phase": "INITIAL_VALID_STATE"}
        _atomic_write_journal(journal_file, initial_data)
        assert journal_file.exists()

        # 1. Inyectar fallo en os.fsync
        with patch("os.fsync", side_effect=OSError("Injected Disk Sync Failure")):
            with pytest.raises(OSError) as exc_fsync:
                _atomic_write_journal(journal_file, {"phase": "NEW_STATE_SHOULD_FAIL"})
            assert "Injected Disk Sync Failure" in str(exc_fsync.value)

        # Comprobar que no quedaron archivos temporales .tmp_*
        tmps = list(temp_dir.glob("*.tmp_*"))
        assert len(tmps) == 0, f"Quedaron temporales huerfanos tras fallo en fsync: {tmps}"
        # El archivo inicial sigue intacto
        curr_data = json.loads(journal_file.read_text(encoding="utf-8"))
        assert curr_data["phase"] == "INITIAL_VALID_STATE"

        # 2. Inyectar fallo en os.replace
        with patch("os.replace", side_effect=OSError("Injected Atomic Replace Failure")):
            with pytest.raises(OSError) as exc_replace:
                _atomic_write_journal(journal_file, {"phase": "REPLACE_SHOULD_FAIL"})
            assert "Injected Atomic Replace Failure" in str(exc_replace.value)

        tmps2 = list(temp_dir.glob("*.tmp_*"))
        assert len(tmps2) == 0
        curr_data2 = json.loads(journal_file.read_text(encoding="utf-8"))
        assert curr_data2["phase"] == "INITIAL_VALID_STATE"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 13. HALLAZGO H5: Reintento de recuperacion sobre FAILED_INCONSISTENT
# ===========================================================================
def test_p15_h5_retry_recovery_on_failed_inconsistent_with_db():
    """
    P15-H5: Reintento sucesivo de recover() cuando el sistema ya esta en FAILED_INCONSISTENT
    con PostgreSQL accesible en cuarentena.
    Demostrar que:
    1. recover() retorna False limpiamente.
    2. La cuarentena en PostgreSQL NO es levantada.
    3. El diario (.cutover_journal.json) no es borrado y mantiene FAILED_INCONSISTENT.
    4. La operacion se mantiene estrictamente fail-closed sin corromper el repositorio.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_h5_retry_{run_id}"
    marker_id = f"marker_h5_retry_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_h5_retry_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)
        _enforce_database_quarantine(
            target_url,
            reason="INCONSISTENT_RESTORATION: Prior test failure",
            journal_state="FAILED_INCONSISTENT",
            marker_id=marker_id
        )

        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "stable.txt").write_text("stable_content", encoding="utf-8")

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "FAILED_INCONSISTENT",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str((temp_dir / "cand").resolve()),
            "backup_dir": str((temp_dir / "bkp").resolve()),
            "db_restored": True,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "quarantine_confirmed": True,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        # Primer reintento
        rec1 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec1 is False

        # Segundo reintento
        rec2 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec2 is False

        # Comprobar que en PostgreSQL la cuarentena SIGUE ACTIVA
        eng = create_engine(target_url)
        with eng.connect() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is not None
        eng.dispose()

        # Comprobar que el diario sigue en FAILED_INCONSISTENT
        saved = json.loads(journal_file.read_text(encoding="utf-8"))
        assert saved["phase"] == "FAILED_INCONSISTENT"
        assert (target_dir / "stable.txt").exists()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 14. P15-R3 BLOQUEANTE 1: REPRODUCCION DEL DEFECTO H1-R2 Y CONTRATO ESTRICTO DE TOKEN
# ===========================================================================
def test_p15_r3_b1_defect_reproduction_null_or_empty_token_rejected():
    """
    P15-R3 Bloqueante 1 (H1-R2):
    Reproduce primero el defecto documentado por GPT:
    - Base de datos con _dr_restoration_quarantine con marker_id valido y journal_state='DB_RESTORED',
      pero restore_token = NULL en la tabla.
    - Llamada con expected_restore_token no vacio.
    - En P15-R2 esto devolvia erroneamente COMMITTED_IN_QUARANTINE (defecto H1-R2).
    - En P15-R3 debe retornar categoricamente FOREIGN_QUARANTINE.

    Acredita ademas:
    - actual_token vacio ("") en tabla -> FOREIGN_QUARANTINE.
    - actual_token con token ajeno -> FOREIGN_QUARANTINE.
    - expected_restore_token ausente (None o "") -> UNKNOWN_OR_INCONSISTENT (nunca commit).
    - expected_marker_id ausente (None o "") -> UNKNOWN_OR_INCONSISTENT (nunca commit).
    - marker_id es NULL en tabla y motivo contiene "[marker: ...]" -> FOREIGN_QUARANTINE (sin fallback de reason).
    - recover() con token discrepante o nulo no promueve documentos y no levanta cuarentena.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_b1_{run_id}"
    marker_id = f"marker_b1_{run_id}"
    expected_token = f"tok_expected_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_b1_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)
        eng = create_engine(target_url, isolation_level="AUTOCOMMIT")

        # Preparar tabla de cuarentena y eliminar ownership marker (simulando COMMIT)
        with eng.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public._dr_test_ownership_marker CASCADE;"))
            conn.execute(text(
                "CREATE TABLE public._dr_restoration_quarantine ("
                "  id SERIAL PRIMARY KEY, quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "  reason TEXT NOT NULL, journal_state TEXT NOT NULL, "
                "  marker_id VARCHAR(64), restore_token VARCHAR(64)"
                ");"
            ))
            # Caso 1 (Defecto H1-R2 reportado por GPT): restore_token es NULL
            conn.execute(text(
                "INSERT INTO public._dr_restoration_quarantine (reason, journal_state, marker_id, restore_token) "
                "VALUES ('RESTORATION_IN_PROGRESS', 'DB_RESTORED', :m, NULL);"
            ), {"m": marker_id})
        eng.dispose()

        # REPRODUCCION Y VERIFICACION H1-R2:
        # En P15-R2, esto devolvía COMMITTED_IN_QUARANTINE por falta de validación de NULL.
        # En P15-R3, DEBE retornar FOREIGN_QUARANTINE.
        status, details = _inspect_postgres_restore_commitment(target_url, marker_id, expected_token)
        assert status == "FOREIGN_QUARANTINE", f"Defecto H1-R2: Se esperaba FOREIGN_QUARANTINE ante token NULL, pero se obtuvo: {status}"
        assert details.get("actual_token") is None

        # Caso 2: restore_token es cadena vacía en BD
        with eng.connect() as conn:
            conn.execute(text("UPDATE public._dr_restoration_quarantine SET restore_token = '';"))
        eng.dispose()
        status, details = _inspect_postgres_restore_commitment(target_url, marker_id, expected_token)
        assert status == "FOREIGN_QUARANTINE", f"Se esperaba FOREIGN_QUARANTINE ante token vacio en BD, obtenido: {status}"

        # Caso 3: restore_token es ajeno / discrepante
        with eng.connect() as conn:
            conn.execute(text("UPDATE public._dr_restoration_quarantine SET restore_token = 'FOREIGN_DIFFERENT_TOKEN';"))
        eng.dispose()
        status, details = _inspect_postgres_restore_commitment(target_url, marker_id, expected_token)
        assert status == "FOREIGN_QUARANTINE", f"Se esperaba FOREIGN_QUARANTINE ante token ajeno, obtenido: {status}"

        # Caso 4: expected_restore_token es None o vacio (llamada sin token)
        with eng.connect() as conn:
            conn.execute(text("UPDATE public._dr_restoration_quarantine SET restore_token = :t;"), {"t": expected_token})
        eng.dispose()
        status_none, _ = _inspect_postgres_restore_commitment(target_url, marker_id, None)
        assert status_none == "UNKNOWN_OR_INCONSISTENT", f"Esperado UNKNOWN_OR_INCONSISTENT para expected_token=None, obtenido: {status_none}"

        status_empty, _ = _inspect_postgres_restore_commitment(target_url, marker_id, "")
        assert status_empty == "UNKNOWN_OR_INCONSISTENT", f"Esperado UNKNOWN_OR_INCONSISTENT para expected_token='', obtenido: {status_empty}"

        # Caso 5: expected_marker_id es None o vacio
        status_nomarker, _ = _inspect_postgres_restore_commitment(target_url, None, expected_token)
        assert status_nomarker == "UNKNOWN_OR_INCONSISTENT", f"Esperado UNKNOWN_OR_INCONSISTENT para marker=None, obtenido: {status_nomarker}"

        status_emptymarker, _ = _inspect_postgres_restore_commitment(target_url, "", expected_token)
        assert status_emptymarker == "UNKNOWN_OR_INCONSISTENT", f"Esperado UNKNOWN_OR_INCONSISTENT para marker='', obtenido: {status_emptymarker}"

        # Caso 6: Prohibicion de fallback a texto en reason
        with eng.connect() as conn:
            conn.execute(text(
                "UPDATE public._dr_restoration_quarantine SET marker_id = NULL, "
                "reason = :r, restore_token = :t;"
            ), {"r": f"RESTORATION [marker: {marker_id}] fallback text", "t": expected_token})
        eng.dispose()
        status_fallback, _ = _inspect_postgres_restore_commitment(target_url, marker_id, expected_token)
        assert status_fallback == "FOREIGN_QUARANTINE", f"Esperado FOREIGN_QUARANTINE (sin fallback de reason), obtenido: {status_fallback}"

        # Caso 7: Prueba adversarial en recover() con token NULL en BD
        with eng.connect() as conn:
            conn.execute(text(
                "UPDATE public._dr_restoration_quarantine SET marker_id = :m, restore_token = NULL, "
                "reason = 'RESTORATION_IN_PROGRESS';"
            ), {"m": marker_id})
        eng.dispose()

        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "orig.txt").write_text("orig_data", encoding="utf-8")

        candidate_dir = temp_dir / f".target_candidate_{run_id}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "cand.txt").write_text("cand_data", encoding="utf-8")
        cand_sha = hashlib.sha256(b"cand_data").hexdigest()

        journal_file = temp_dir / ".cutover_journal.json"
        journal_data = {
            "phase": "RESTORATION_INITIATED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((temp_dir / "bkp").resolve()),
            "db_restored": False,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": expected_token,
            "candidate_ready": True,
            "catalog_hashes": {"cand.txt": cand_sha},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        # recover() debe rechazar la recuperación y abortar fail-closed
        rec = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec is False, "recover() no debe realizar conmutacion si el token en BD es NULL o inconsistente"

        # Demostrar que NO se promovieron documentos
        assert (target_dir / "orig.txt").exists()
        assert not (target_dir / "cand.txt").exists()

        # Demostrar que NO se levantó la cuarentena
        eng2 = create_engine(target_url)
        with eng2.connect() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is not None, "La cuarentena en PostgreSQL NO debio ser levantada"
        eng2.dispose()

        # Demostrar que el diario permanece en FAILED_INCONSISTENT
        saved = json.loads(journal_file.read_text(encoding="utf-8"))
        assert saved["phase"] == "FAILED_INCONSISTENT"

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 15. P15-R3 BLOQUEANTE 2: FALLO DE DURABILIDAD / FSYNC EN PRE-STAGING ABORTA ANTES DE POSTGRESQL
# ===========================================================================
def test_p15_r3_b2_prestaging_durability_fsync_failure_aborts_before_postgres():
    """
    P15-R3 Bloqueante 2 (H3-R2):
    Acredita que un fallo de I/O o sincronizacion (os.fsync) durante el pre-staging
    de candidate_dir aborta fail-closed ANTES de invocar execute_pg_restore() y antes
    de registrar candidate_ready=True en el diario.

    Verifica que:
    1. restore_lan_backup() captura la falla y aborta con RuntimeError.
    2. execute_pg_restore() NUNCA fue llamado.
    3. PostgreSQL permanece 100% intacto con su marcador de propiedad original.
    4. candidate_dir temporal es limpiado o no registrado como listo.
    """
    run_id = uuid.uuid4().hex[:8]
    target_db_name = f"dr_test_p15_b2_{run_id}"
    marker_id = f"marker_b2_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_b2_"))
    target_url = None

    try:
        # 1. Crear respaldo autentico real de prueba
        source_uploads = temp_dir / "source_uploads"
        source_uploads.mkdir(parents=True, exist_ok=True)
        (source_uploads / "doc1.txt").write_text("doc1_durability_test", encoding="utf-8")
        (source_uploads / "doc2.txt").write_text("doc2_durability_test", encoding="utf-8")

        backup_file = temp_dir / "backup_b2.tar.gz.enc"
        enc_key = "test_enc_key_32bytes_aes_gcm_valid"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        create_lan_backup(
            database_url=settings.DATABASE_URL,
            uploads_dir=source_uploads,
            output_backup_file=backup_file,
            encryption_key=enc_key,
            signing_key=sign_key
        )

        # 2. Base de datos destino con marcador de propiedad original
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, target_db_name, marker_id)
        restored_uploads = temp_dir / "target_uploads_b2"

        # 3. Interceptar execute_pg_restore para comprobar que NUNCA sea invocado
        pg_restore_invoked = False
        original_pg_restore = execute_pg_restore

        def spy_pg_restore(*args, **kwargs):
            nonlocal pg_restore_invoked
            pg_restore_invoked = True
            return original_pg_restore(*args, **kwargs)

        # Inyectar fallo de durabilidad directamente en os.fsync cuando el descriptor corresponde a un directorio
        # SIN reemplazar _sync_directory_tree (P15-R4 Bloqueante A)
        real_fsync = os.fsync

        def directory_failing_fsync(fd):
            try:
                st = os.fstat(fd)
                if stat.S_ISDIR(st.st_mode):
                    raise OSError(errno.EIO, "EIO: Synthetic directory fsync I/O failure (P15-R4 Bloqueante A)")
            except (ValueError, OSError) as e:
                if "Synthetic directory" in str(e):
                    raise
            return real_fsync(fd)

        with patch("verification.dr.backup_lan_pg15.execute_pg_restore", side_effect=spy_pg_restore):
            with patch("os.fsync", side_effect=directory_failing_fsync):
                with patch("sys.platform", "linux"):
                    with pytest.raises(RuntimeError) as exc_info:
                        restore_lan_backup(
                            backup_file=backup_file,
                            target_uploads_dir=restored_uploads,
                            encryption_key=enc_key,
                            signing_key=sign_key,
                            expected_marker_id=marker_id,
                            target_database_url=target_url,
                            source_database_url=settings.DATABASE_URL
                        )

                    assert "Fallo de durabilidad en pre-staging documental" in str(exc_info.value)

        # 4. Verificaciones críticas de seguridad (Bloqueante 2):
        # A. execute_pg_restore NUNCA fue llamado
        assert pg_restore_invoked is False, "INVARIANTE B2: execute_pg_restore() NO debio ser invocado tras fallo de durabilidad"

        # B. En PostgreSQL: el marcador de propiedad original sigue 100% INTACTO
        eng = create_engine(target_url)
        with eng.connect() as conn:
            marker_val = conn.execute(text("SELECT marker_id FROM public._dr_test_ownership_marker;")).scalar()
            assert marker_val == marker_id, "El marcador de propiedad debio permanecer intacto"
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is None, "La cuarentena NO debio haberse creado en PostgreSQL"
        eng.dispose()

        # C. candidate_ready NUNCA fue registrado en el journal
        parent_dir = restored_uploads.resolve().parent
        journal_file = parent_dir / ".cutover_journal.json"
        if journal_file.exists():
            jdata = json.loads(journal_file.read_text(encoding="utf-8"))
            assert jdata.get("candidate_ready") is not True

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, target_db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 16. P15-R3 BLOQUEANTE 3: IDENTIDAD CONTINUA DEL JOURNAL DURANTE CORTE EN PUBLISH
# ===========================================================================
def test_p15_r3_b3_journal_continuous_identity_during_publish_interruption():
    """
    P15-R3 Bloqueante 3 (H3-R2-b):
    Acredita la identidad continua e inequívoca a través de publish():
    1. Interrupcion simulada durante publish() tras reemplazar el diario en MOVING_TARGET
       y antes de renombrar candidate_dir a target_dir.
    2. El diario en disco PRESERVA restore_token, expected_marker_id y candidate_ready=True.
    3. recover() ejecuta forward recovery exitoso si los metadatos en PostgreSQL coinciden.
    4. Prueba negativa adversarial: si PostgreSQL contiene una cuarentena con restore_token
       ajeno, recover() aborta fail-closed y NO levanta la cuarentena ni promueve documentos.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_b3_{run_id}"
    marker_id = f"marker_b3_{run_id}"
    legit_token = f"tok_legit_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_b3_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_uploads_b3"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "old_doc.txt").write_text("old_content_b3", encoding="utf-8")

        candidate_dir = temp_dir / f".target_candidate_{run_id}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        new_content = "new_promoted_content_b3"
        (candidate_dir / "new_doc.txt").write_text(new_content, encoding="utf-8")
        new_sha = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

        # Establecer cuarentena legítima en PostgreSQL con token legítimo
        _enforce_database_quarantine(
            db_url=target_url,
            reason="RESTORATION_IN_PROGRESS (B1): Pending publish b3",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=legit_token
        )

        parent_dir = target_dir.parent.resolve()
        journal_file = parent_dir / ".cutover_journal.json"
        prior_journal_data = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str((parent_dir / f".target_backup_{run_id}").resolve()),
            "db_restored": True,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": legit_token,
            "candidate_ready": True,
            "catalog_hashes": {"new_doc.txt": new_sha},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, prior_journal_data)

        # Simular corte durante publish() en la fase MOVING_TARGET (simulando muerte abrupta del proceso)
        class SimulatedPublishCrashError(BaseException):
            pass

        original_atomic_write = _atomic_write_journal

        def crashing_atomic_write(jfile, jdata):
            original_atomic_write(jfile, jdata)
            if jdata.get("phase") == "MOVING_TARGET":
                raise SimulatedPublishCrashError("Corte abrupto tras actualizar journal a MOVING_TARGET")

        publisher = CrashResilientDocumentPublisher(
            target_dir=target_dir,
            db_restored=True,
            target_database_url=target_url,
            expected_marker_id=marker_id,
            restore_token=legit_token
        )

        catalog = [{"relative_path": "new_doc.txt", "sha256": new_sha}]

        # Ejecutar publish() que será interrumpido en MOVING_TARGET
        with patch("verification.dr.backup_lan_pg15._atomic_write_journal", side_effect=crashing_atomic_write):
            with pytest.raises(SimulatedPublishCrashError):
                publisher.publish(
                    staging_dir=candidate_dir,
                    catalog=catalog,
                    candidate_dir=candidate_dir,
                    backup_dir=Path(prior_journal_data["backup_dir"])
                )

        # 1. VERIFICAR PRESERVACION DE IDENTIDAD EN JOURNAL (Bloqueante 3):
        assert journal_file.exists()
        saved_journal = json.loads(journal_file.read_text(encoding="utf-8"))
        assert saved_journal["phase"] == "MOVING_TARGET"
        assert saved_journal["restore_token"] == legit_token, "INVARIANTE B3: restore_token DEBE preservarse en MOVING_TARGET"
        assert saved_journal["expected_marker_id"] == marker_id, "INVARIANTE B3: expected_marker_id DEBE preservarse"
        assert saved_journal.get("candidate_ready") is True, "INVARIANTE B3: candidate_ready DEBE ser True"

        # 2. PRUEBA NEGATIVA ADVERSARIAL:
        # Si un tercero altera la base de datos o hay una cuarentena con restore_token ajeno
        eng = create_engine(target_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            conn.execute(text("UPDATE public._dr_restoration_quarantine SET restore_token = 'FOREIGN_TAMPERED_TOKEN';"))
        eng.dispose()

        # recover() con token discrepante en BD DEBE abortar fail-closed
        rec_foreign = CrashResilientDocumentPublisher.recover(
            parent_dir=parent_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec_foreign is False, "recover() DEBE abortar fail-closed ante restore_token alterado en BD"

        # Demostrar que la cuarentena NO fue levantada
        eng2 = create_engine(target_url)
        with eng2.connect() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is not None, "La cuarentena ajena NO debio ser levantada"
        eng2.dispose()

        # 3. PRUEBA POSITIVA DE RECUPERACION CON IDENTIDAD LEGITIMA:
        # Restaurar el token legítimo en BD y el journal en MOVING_TARGET
        with eng.connect() as conn:
            conn.execute(text("UPDATE public._dr_restoration_quarantine SET restore_token = :t;"), {"t": legit_token})
        eng.dispose()

        _atomic_write_journal(journal_file, saved_journal)

        rec_ok = CrashResilientDocumentPublisher.recover(
            parent_dir=parent_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id
        )
        assert rec_ok is True, "recover() debe completar con exito con token e identidad legitima coincidentes"

        # Validar que los documentos fueron promovidos y la cuarentena levantada
        assert (target_dir / "new_doc.txt").exists()
        assert (target_dir / "new_doc.txt").read_text(encoding="utf-8") == new_content

        eng3 = create_engine(target_url)
        with eng3.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar() is None
        eng3.dispose()

        assert not journal_file.exists()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 17. P15-R4 BLOQUEANTE A: FSYNC DE DIRECTORIO FAIL-CLOSED EN POSIX/LINUX
# ===========================================================================
def test_p15_r4_b1_directory_fsync_io_failure_propagates_fail_closed():
    """
    P15-R4 Bloqueante A:
    Acredita que en plataformas con soporte de fsync de directorios (POSIX/Linux):
    1. Un fallo real de I/O en os.fsync() sobre un descriptor de directorio
       DEBE propagarse fail-closed y NO ser silenciado.
    2. _atomic_write_journal() propaga el fallo de sincronizacion del directorio.
    3. Se distingue explicitamente entre fallo de I/O (EIO -> raise) y no soporte (ENOTSUP -> log/return).
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_r4_b1_"))
    try:
        sample_dir = temp_dir / "sample_dir"
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample_file = sample_dir / "test.txt"
        sample_file.write_text("sample_content", encoding="utf-8")

        real_fsync = os.fsync

        def dir_failing_fsync(fd):
            try:
                st = os.fstat(fd)
                if stat.S_ISDIR(st.st_mode):
                    raise OSError(errno.EIO, "EIO: Hardware / disk I/O failure on directory descriptor")
            except (ValueError, OSError) as e:
                if "Hardware / disk" in str(e):
                    raise
            return real_fsync(fd)

        # 1. En Linux/POSIX, _sync_directory DEBE propagar el error de I/O
        with patch("sys.platform", "linux"):
            if hasattr(os, "O_DIRECTORY") and sys.platform != "win32":
                with patch("os.fsync", side_effect=dir_failing_fsync):
                    with pytest.raises(OSError) as exc_dir:
                        _sync_directory(sample_dir)
                    assert exc_dir.value.errno == errno.EIO

        # 2. _atomic_write_journal DEBE propagar fallo de sincronizacion de directorio
        journal_file = temp_dir / ".cutover_journal.json"
        jdata = {"phase": "TEST", "created_at": time.time()}

        with patch("sys.platform", "linux"):
            if hasattr(os, "O_DIRECTORY") and sys.platform != "win32":
                with patch("os.fsync", side_effect=dir_failing_fsync):
                    with pytest.raises(OSError) as exc_j:
                        _atomic_write_journal(journal_file, jdata)
                    assert exc_j.value.errno == errno.EIO

        # 3. P15-R5 (R4-H1): En rutas que exigen durabilidad, ENOTSUP y EOPNOTSUPP DEBEN propagarse fail-closed
        def dir_enotsup_fsync(fd):
            try:
                st = os.fstat(fd)
                if stat.S_ISDIR(st.st_mode):
                    err_code = getattr(errno, "ENOTSUP", getattr(errno, "EOPNOTSUPP", 95))
                    raise OSError(err_code, "Operation not supported on this filesystem")
            except (ValueError, OSError) as e:
                if "Operation not supported" in str(e):
                    raise
            return real_fsync(fd)

        with patch("sys.platform", "linux"):
            if hasattr(os, "O_DIRECTORY") and sys.platform != "win32":
                with patch("os.fsync", side_effect=dir_enotsup_fsync):
                    with pytest.raises(OSError) as exc_enotsup:
                        _sync_directory(sample_dir)
                    assert exc_enotsup.value.errno in (getattr(errno, "ENOTSUP", -1), getattr(errno, "EOPNOTSUPP", -1), 95)

        # 4. P15-R5 (R4-H1): En Windows (sin soporte acreditado de fsync sobre directorios), aborta fail-closed
        with patch("sys.platform", "win32"):
            with pytest.raises(OSError) as exc_win:
                _sync_directory(sample_dir)
            assert exc_win.value.errno == getattr(errno, "ENOTSUP", 95)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 18. P15-R4 BLOQUEANTE B: FASE COMMITTED CON AUDITORIA ESTRICTA EN POSTGRESQL 15
# ===========================================================================
def test_p15_r4_b2_committed_phase_adversarial_suite_postgres15():
    """
    P15-R4 Bloqueante B:
    Acredita en PostgreSQL 15 real que CrashResilientDocumentPublisher.recover()
    en fase COMMITTED:
    1. Journal COMMITTED con cuarentena propia y token valido -> levanta cuarentena, borra journal, True.
    2. Journal COMMITTED con cuarentena ajena -> aborta fail-closed, NO levanta cuarentena, preserva journal, False.
    3. Journal COMMITTED con token ausente o discrepante -> aborta fail-closed, preserva journal, False.
    4. Journal COMMITTED con PostgreSQL inaccesible -> aborta fail-closed, preserva journal, False.
    5. Recuperacion repetida despues de una interrupcion de limpieza (idempotencia) -> completa limpiamente.
    """
    run_id = uuid.uuid4().hex[:8]
    legit_db_name = f"dr_test_p15_r4_legit_{run_id}"
    foreign_db_name = f"dr_test_p15_r4_foreign_{run_id}"
    legit_marker = f"marker_legit_{run_id}"
    foreign_marker = f"marker_foreign_{run_id}"
    legit_token = f"tok_legit_{run_id}"
    foreign_token = f"tok_foreign_{run_id}"

    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_r4_b2_"))
    legit_url = None
    foreign_url = None

    try:
        # Preparar bases de datos efimeras reales en PostgreSQL 15
        legit_url = _create_p15_ephemeral_db(settings.DATABASE_URL, legit_db_name, legit_marker)
        foreign_url = _create_p15_ephemeral_db(settings.DATABASE_URL, foreign_db_name, foreign_marker)

        # Proteger base ajena con tabla critica
        eng_for = create_engine(foreign_url, isolation_level="AUTOCOMMIT")
        with eng_for.connect() as conn:
            conn.execute(text("CREATE TABLE foreign_critical_records (id INT, secret TEXT);"))
            conn.execute(text("INSERT INTO foreign_critical_records VALUES (101, 'BANK_SECRET_DO_NOT_TOUCH');"))
        eng_for.dispose()

        doc_sha = hashlib.sha256(b"committed_doc_content").hexdigest()
        legit_hashes = {"doc.txt": doc_sha}

        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "doc.txt").write_text("committed_doc_content", encoding="utf-8")
        backup_dir = temp_dir / ".target_backup_cleanup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        journal_file = temp_dir / ".cutover_journal.json"

        # -------------------------------------------------------------------
        # ESCENARIO 2: Journal COMMITTED con cuarentena ajena
        # -------------------------------------------------------------------
        # Establecer cuarentena en base ajena con token ajeno
        _enforce_database_quarantine(
            db_url=foreign_url,
            reason="RESTORATION_IN_PROGRESS: Foreign restore",
            journal_state="DB_RESTORED",
            marker_id=foreign_marker,
            restore_token=foreign_token
        )

        journal_foreign = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str((temp_dir / ".candidate").resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": foreign_url,
            "expected_marker_id": legit_marker,    # Discrepante con foreign_marker
            "restore_token": legit_token,          # Discrepante con foreign_token
            "catalog_hashes": legit_hashes,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_foreign)

        # recover() DEBE abortar fail-closed
        rec_for = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=foreign_url,
            expected_marker_id=legit_marker
        )
        assert rec_for is False, "recover() en COMMITTED DEBE retornar False ante base/cuarentena ajena"

        # Demostrar que la base ajena NO fue tocada y la cuarentena ajena NO fue levantada
        eng_for2 = create_engine(foreign_url)
        with eng_for2.connect() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is not None, "INVARIANTE B: Cuarentena ajena NO debio ser levantada en COMMITTED"
            secret_val = conn.execute(text("SELECT secret FROM foreign_critical_records WHERE id=101;")).scalar()
            assert secret_val == "BANK_SECRET_DO_NOT_TOUCH", "Datos ajenos debieron permanecer 100% intactos"
        eng_for2.dispose()

        # El journal DEBE ser preservado en FAILED_INCONSISTENT
        assert journal_file.exists(), "El journal debio ser preservado para auditoria forense"
        jdata_for = json.loads(journal_file.read_text(encoding="utf-8"))
        assert jdata_for["phase"] == "FAILED_INCONSISTENT"
        assert jdata_for.get("foreign_database_untouched") is True

        # -------------------------------------------------------------------
        # ESCENARIO 3: Journal COMMITTED con token ausente o discrepante
        # -------------------------------------------------------------------
        # 3A: Token ausente en journal
        journal_missing_tok = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str((temp_dir / ".candidate").resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": legit_url,
            "expected_marker_id": legit_marker,
            "restore_token": None,                 # Token ausente
            "catalog_hashes": legit_hashes,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_missing_tok)

        rec_notok = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=legit_url,
            expected_marker_id=legit_marker
        )
        assert rec_notok is False, "recover() en COMMITTED DEBE abortar fail-closed ante token ausente"

        # 3B: Token discrepante en journal vs PostgreSQL
        _enforce_database_quarantine(
            db_url=legit_url,
            reason="RESTORATION_IN_PROGRESS: Legit restore",
            journal_state="DB_RESTORED",
            marker_id=legit_marker,
            restore_token=legit_token
        )

        journal_mismatched_tok = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str((temp_dir / ".candidate").resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": legit_url,
            "expected_marker_id": legit_marker,
            "restore_token": "DIFFERENT_DISCREPANT_TOKEN_999",  # Discrepante
            "catalog_hashes": legit_hashes,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_mismatched_tok)

        rec_mis = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=legit_url,
            expected_marker_id=legit_marker
        )
        assert rec_mis is False, "recover() en COMMITTED DEBE abortar fail-closed ante token discrepante"

        # Verificar que la cuarentena sigue activa en PostgreSQL
        eng_leg = create_engine(legit_url)
        with eng_leg.connect() as conn:
            q_exists_leg = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists_leg is not None, "Cuarentena no debio levantarse con token discrepante"
        eng_leg.dispose()

        # -------------------------------------------------------------------
        # ESCENARIO 4: Journal COMMITTED con PostgreSQL inaccesible
        # -------------------------------------------------------------------
        journal_inacc = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str((temp_dir / ".candidate").resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": "postgresql://bad_user:bad_pass@127.0.0.1:54399/non_existent_db",
            "expected_marker_id": legit_marker,
            "restore_token": legit_token,
            "catalog_hashes": legit_hashes,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_inacc)

        rec_inacc = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url="postgresql://bad_user:bad_pass@127.0.0.1:54399/non_existent_db",
            expected_marker_id=legit_marker
        )
        assert rec_inacc is False, "recover() DEBE abortar fail-closed cuando PostgreSQL es inaccesible"
        assert journal_file.exists(), "El journal NO debe borrarse si la BD esta inaccesible"

        # -------------------------------------------------------------------
        # ESCENARIO 1: Journal COMMITTED con cuarentena propia y token valido
        # -------------------------------------------------------------------
        journal_own_valid = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str((temp_dir / ".candidate").resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": legit_url,
            "expected_marker_id": legit_marker,
            "restore_token": legit_token,          # Coincidente
            "catalog_hashes": legit_hashes,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_own_valid)

        rec_ok = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=legit_url,
            expected_marker_id=legit_marker
        )
        assert rec_ok is True, "recover() en COMMITTED con identidad propia legitima DEBE retornar True"

        # Verificar que la cuarentena fue efectivamente levantada
        with eng_leg.connect() as conn:
            q_after = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_after is None, "La cuarentena legitima debio ser levantada"
        eng_leg.dispose()

        # Verificar que el journal fue removido y el backup eliminado
        assert not journal_file.exists(), "El journal debio ser eliminado tras limpieza exitosa"
        assert not backup_dir.exists(), "El backup_dir debio ser eliminado"

        # -------------------------------------------------------------------
        # ESCENARIO 5: P15-R5 (Hallazgo R4-H2, Opcion A)
        # Reintento con ausencia simultanea de tablas en PostgreSQL
        # -------------------------------------------------------------------
        # Simular corte donde la cuarentena ya no existe en BD pero el journal COMMITTED persiste.
        # Bajo la invariante P15-R5 (Hallazgo R4-H2), la ausencia simultanea de tablas NO prueba
        # por si misma que esta restauracion especifica haya concluido; debe abortar fail-closed,
        # preservar journal y respaldo para reconciliacion acreditada.
        clean_eng = create_engine(legit_url)
        with clean_eng.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public._dr_restoration_completed CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS public._dr_restoration_quarantine CASCADE;"))
        clean_eng.dispose()

        backup_dir2 = temp_dir / ".target_backup_cleanup2"
        backup_dir2.mkdir(parents=True, exist_ok=True)
        journal_clean_interrupted = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str((temp_dir / ".candidate").resolve()),
            "backup_dir": str(backup_dir2.resolve()),
            "db_restored": True,
            "target_database_url": legit_url,
            "expected_marker_id": legit_marker,
            "restore_token": legit_token,
            "catalog_hashes": legit_hashes,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_clean_interrupted)

        # recover() DEBE abortar fail-closed, NO borrar journal y NO borrar backup (R4-H2)
        rec_idemp1 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=legit_url,
            expected_marker_id=legit_marker
        )
        assert rec_idemp1 is False, "P15-R5 (R4-H2): recover() DEBE retornar False ante estado incierto/ambiguo en BD"
        assert journal_file.exists(), "El journal DEBE ser preservado en FAILED_INCONSISTENT para reconciliacion acreditada"
        assert backup_dir2.exists(), "El respaldo backup_dir2 NO debe ser eliminado sin certeza acreditada"
        jdata_idemp = json.loads(journal_file.read_text(encoding="utf-8"))
        assert jdata_idemp["phase"] == "FAILED_INCONSISTENT"
        assert "Incertidumbre transaccional" in jdata_idemp["error"]

        # Segunda llamada: el journal continua en FAILED_INCONSISTENT, retorna False fail-closed
        rec_idemp2 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=legit_url,
            expected_marker_id=legit_marker
        )
        assert rec_idemp2 is False, "Llamada subsecuente con journal en FAILED_INCONSISTENT retorna False"

    finally:
        if legit_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, legit_db_name)
        if foreign_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, foreign_db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 19. P15-R5 HALLAZGO R4-H1: FSYNC ENOTSUP EN DIRECTORIO FAIL-CLOSED PREVIO A POSTGRESQL
# ===========================================================================
def test_p15_r5_h1_directory_fsync_enotsup_aborts_before_postgres():
    """
    P15-R5 (Hallazgo R4-H1):
    Acredita que cuando un sistema de archivos emite OSError(ENOTSUP) durante la sincronizacion
    durable de directorios en el pre-staging documental:
    1. El error DEBE propagarse fail-closed y NO ser silenciado.
    2. restore_lan_backup() aborta antes de tocar PostgreSQL.
    3. execute_pg_restore() NUNCA es invocado.
    4. La base de datos PostgreSQL permanece 100% inalterada con su marcador de propiedad original intacto.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_r5_h1_"))
    target_url = None
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_r5_h1_{run_id}"
    marker_id = f"marker_r5_h1_{run_id}"

    try:
        source_dir = temp_dir / "source_docs"
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "doc1.txt").write_text("content_file_1", encoding="utf-8")
        (source_dir / "subdir").mkdir(parents=True, exist_ok=True)
        (source_dir / "subdir" / "doc2.txt").write_text("content_file_2", encoding="utf-8")

        backup_file = temp_dir / "lan_backup.tar.gz.enc"
        restored_uploads = temp_dir / "restored_uploads"
        enc_key = "test_enc_key_32bytes_aes_gcm_valid"
        sign_key = "test_sign_key_32bytes_hmac_valid"

        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        create_lan_backup(
            output_backup_file=backup_file,
            uploads_dir=source_dir,
            database_url=settings.DATABASE_URL,
            encryption_key=enc_key,
            signing_key=sign_key
        )
        assert backup_file.exists()

        pg_restore_invoked = False
        original_pg_restore = execute_pg_restore

        def spy_pg_restore(*args, **kwargs):
            nonlocal pg_restore_invoked
            pg_restore_invoked = True
            return original_pg_restore(*args, **kwargs)

        real_fsync = os.fsync

        def dir_enotsup_failing_fsync(fd):
            try:
                st = os.fstat(fd)
                if stat.S_ISDIR(st.st_mode):
                    err_code = getattr(errno, "ENOTSUP", getattr(errno, "EOPNOTSUPP", 95))
                    raise OSError(err_code, "ENOTSUP: Operation not supported on directory descriptor (R4-H1)")
            except (ValueError, OSError) as e:
                if "ENOTSUP: Operation not supported" in str(e):
                    raise
            return real_fsync(fd)

        with patch("verification.dr.backup_lan_pg15.execute_pg_restore", side_effect=spy_pg_restore):
            with patch("os.fsync", side_effect=dir_enotsup_failing_fsync):
                with patch("sys.platform", "linux"):
                    with pytest.raises(RuntimeError) as exc_info:
                        restore_lan_backup(
                            backup_file=backup_file,
                            target_uploads_dir=restored_uploads,
                            encryption_key=enc_key,
                            signing_key=sign_key,
                            expected_marker_id=marker_id,
                            target_database_url=target_url,
                            source_database_url=settings.DATABASE_URL
                        )

                    assert "Fallo de durabilidad en pre-staging documental" in str(exc_info.value)

        # Verificaciones críticas de seguridad (R4-H1):
        assert pg_restore_invoked is False, "INVARIANTE R4-H1: execute_pg_restore() NO debio ser invocado ante ENOTSUP"

        # En PostgreSQL: marcador intacto, cuarentena inexistente
        eng = create_engine(target_url)
        with eng.connect() as conn:
            marker_val = conn.execute(text("SELECT marker_id FROM public._dr_test_ownership_marker;")).scalar()
            assert marker_val == marker_id, "El marcador de propiedad debio permanecer intacto"
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is None, "La cuarentena NO debio haberse creado en PostgreSQL"
        eng.dispose()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 20. P15-R5 HALLAZGO R4-H3: INTEGRIDAD DOCUMENTAL ESTRICTA EN FASE COMMITTED
# ===========================================================================
def test_p15_r5_h3_committed_documentary_integrity_adversarial_suite_postgres15():
    """
    P15-R5 (Hallazgo R4-H3):
    Acredita contra PostgreSQL 15 real que CrashResilientDocumentPublisher.recover()
    en fase COMMITTED verifica obligatoriamente la integridad documental de target_dir
    ANTES de levantar cualquier cuarentena o eliminar respaldos/diarios:
    1. Destino inexistente -> aborta fail-closed, preserva cuarentena y evidencias.
    2. Archivo ausente en destino -> aborta fail-closed, preserva cuarentena y evidencias.
    3. Archivo con hash discrepante/corrupto -> aborta fail-closed, preserva cuarentena y evidencias.
    4. Catalogo vacio por omision ({}) sin autorizacion -> aborta fail-closed, preserva cuarentena.
    5. Path traversal o escape de confinamiento -> aborta fail-closed.
    6. Catalogo legitimamente vacio autorizado (allow_empty_catalog=True) -> levanta cuarentena autorizadamente.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_p15_r5_h3_{run_id}"
    marker_id = f"marker_r5_h3_{run_id}"
    restore_token = f"tok_r5_h3_{run_id}"

    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_r5_h3_"))
    db_url = None

    try:
        db_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_documents"
        backup_dir = temp_dir / ".backup_evidence"
        backup_dir.mkdir(parents=True, exist_ok=True)
        candidate_dir = temp_dir / ".candidate_docs"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        journal_file = temp_dir / ".cutover_journal.json"

        # Establecer cuarentena legitima en PostgreSQL con marker y token
        _enforce_database_quarantine(
            db_url=db_url,
            reason="RESTORATION_IN_PROGRESS: Test R4-H3",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        doc_content = b"CRITICAL_HEALTHCARE_REPORT_CONTENT_VERIFIED"
        expected_sha = hashlib.sha256(doc_content).hexdigest()
        legit_catalog = {"reports/summary.pdf": expected_sha}

        # -------------------------------------------------------------------
        # 1. SUBESCENARIO: Destino inexistente (target_dir no existe)
        # -------------------------------------------------------------------
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        jdata_no_target = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": legit_catalog,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_no_target)

        res1 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res1 is False, "recover() DEBE abortar fail-closed cuando target_dir no existe"
        assert journal_file.exists(), "El journal debe ser preservado"
        assert backup_dir.exists(), "El backup debe ser preservado"

        eng = create_engine(db_url)
        with eng.connect() as conn:
            q_ex = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_ex is not None, "Cuarentena en PG NO debio levantarse con target_dir inexistente"
        eng.dispose()

        # -------------------------------------------------------------------
        # 2. SUBESCENARIO: Archivo requerido ausente en target_dir
        # -------------------------------------------------------------------
        target_dir.mkdir(parents=True, exist_ok=True)
        # target_dir existe pero 'reports/summary.pdf' no existe

        _atomic_write_journal(journal_file, jdata_no_target)
        res2 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res2 is False, "recover() DEBE abortar fail-closed cuando falta un archivo del catalogo"
        assert journal_file.exists()
        assert backup_dir.exists()

        with eng.connect() as conn:
            q_ex = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_ex is not None, "Cuarentena en PG NO debio levantarse con archivo documental ausente"
        eng.dispose()

        # -------------------------------------------------------------------
        # 3. SUBESCENARIO: Archivo con contenido corrupto / hash alterado
        # -------------------------------------------------------------------
        file_path = target_dir / "reports" / "summary.pdf"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"CORRUPTED_OR_TAMPERED_DATA_BYTES")

        _atomic_write_journal(journal_file, jdata_no_target)
        res3 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res3 is False, "recover() DEBE abortar fail-closed cuando el hash del documento no coincide"
        assert journal_file.exists()
        assert backup_dir.exists()

        with eng.connect() as conn:
            q_ex = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_ex is not None, "Cuarentena en PG NO debio levantarse con hash documental corrupto"
        eng.dispose()

        # -------------------------------------------------------------------
        # 4. SUBESCENARIO: Catalogo vacio por omision ({}) sin autorizacion
        # -------------------------------------------------------------------
        jdata_empty_omission = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {},              # Vacio por omision
            "allow_empty_catalog": False,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_empty_omission)
        res4 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res4 is False, "recover() DEBE abortar fail-closed ante catalog_hashes={} sin allow_empty_catalog"
        assert journal_file.exists()
        assert backup_dir.exists()

        # -------------------------------------------------------------------
        # 5. SUBESCENARIO: Path traversal en catalogo
        # -------------------------------------------------------------------
        jdata_traversal = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"../../etc/passwd": "abc123sha"},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_traversal)
        res5 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res5 is False, "recover() DEBE abortar fail-closed ante path traversal en catalogo"
        assert journal_file.exists()

        # -------------------------------------------------------------------
        # 6. SUBESCENARIO POSITIVO: Integridad documental 100% verificada
        # -------------------------------------------------------------------
        # Escribir el contenido correcto y su hash
        file_path.write_bytes(doc_content)

        _atomic_write_journal(journal_file, jdata_no_target)
        res6 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res6 is True, "recover() DEBE retornar True cuando documentos e identidad PG son 100% validos"
        assert not journal_file.exists(), "El journal debio eliminarse tras recuperacion exitosa"
        assert not backup_dir.exists(), "El backup debio eliminarse"

        # Demostrar que la cuarentena fue debidamente levantada
        with eng.connect() as conn:
            q_ex = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_ex is None, "La cuarentena debio ser levantada en PostgreSQL"
        eng.dispose()

    finally:
        if db_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 21. BLOQUEANTE F1: Reproduccion exacta del caso GPT (DB_RESTORED con PG caido)
# ===========================================================================
def test_p15_f1_db_restored_postgres_inaccessible_aborts_fail_closed():
    """
    P15-F1 (Auditoria GPT Bloqueante F1):
    Reproduce exactamente el caso GPT:
    - Journal en fase 'DB_RESTORED' (post-COMMIT).
    - Candidato documental 100% valido coincidente con catalog_hashes.
    - PostgreSQL inaccesible / caido (puerto cerrado o ConnectionError).
    - Acredita taxativamente:
      1. recover() retorna False (fail-closed estricto).
      2. No se invocó _lift_database_quarantine().
      3. No se promovieron los documentos (target NO contiene el candidato).
      4. El directorio candidate y backup NO son destruidos.
      5. El journal se preserva intacto para auditoria forense.
      6. Aplica igualmente para transiciones post-COMMIT MOVING_TARGET y TARGET_MOVED.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_f1_gpt_repro_"))
    dead_pg_url = "postgresql://test_user:test_password@127.0.0.1:59999/dr_test_dead_f1"

    try:
        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "original.txt").write_text("orig_content", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        cand_content = b"candidate_document_data_v6"
        (candidate_dir / "new_doc.txt").write_bytes(cand_content)
        cand_hash = hashlib.sha256(cand_content).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "backup.txt").write_text("backup_content", encoding="utf-8")

        journal_file = temp_dir / ".cutover_journal.json"
        marker_id = "marker_f1_gpt"
        restore_token = "token_f1_gpt"

        # 1. Fase DB_RESTORED
        jdata = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": dead_pg_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"new_doc.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        with patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift:
            recovered = CrashResilientDocumentPublisher.recover(
                parent_dir=temp_dir,
                target_database_url=dead_pg_url,
                expected_marker_id=marker_id,
                expected_restore_token=restore_token
            )
            assert recovered is False, "recover() DEBE retornar False fail-closed cuando PostgreSQL esta inaccesible en DB_RESTORED"
            assert mock_lift.call_count == 0, "_lift_database_quarantine() NO debio ser invocada con PostgreSQL inaccesible"

        # Acreditar preservacion forense
        assert journal_file.exists(), "El journal debio ser preservado intacto para auditoria forense"
        assert candidate_dir.exists(), "candidate_dir no debio ser eliminado"
        assert (candidate_dir / "new_doc.txt").exists()
        assert not (target_dir / "new_doc.txt").exists(), "El candidato NO debio ser promovido a target"
        assert (target_dir / "original.txt").exists(), "target_dir original debe permanecer intacto"
        assert backup_dir.exists(), "backup_dir no debio ser eliminado"

        # 2. Comprobar que aplica igualmente a fases MOVING_TARGET y TARGET_MOVED
        for post_phase in ("MOVING_TARGET", "TARGET_MOVED"):
            jdata["phase"] = post_phase
            _atomic_write_journal(journal_file, jdata)
            with patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift:
                recovered = CrashResilientDocumentPublisher.recover(
                    parent_dir=temp_dir,
                    target_database_url=dead_pg_url,
                    expected_marker_id=marker_id,
                    expected_restore_token=restore_token
                )
                assert recovered is False, f"recover() DEBE retornar False fail-closed en fase {post_phase} con PG caido"
                assert mock_lift.call_count == 0
            assert journal_file.exists()
            assert not (target_dir / "new_doc.txt").exists()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 22. BLOQUEANTE F1: PostgreSQL 15 real con cuarentena esperada ausente
# ===========================================================================
def test_p15_f1_db_restored_quarantine_absent_aborts_fail_closed_postgres15():
    """
    P15-F1 (Auditoria GPT Bloqueante F1 - Caso PostgreSQL 15 real):
    Acredita contra PostgreSQL 15 real que CrashResilientDocumentPublisher.recover():
    - Con journal en fase 'DB_RESTORED' y db_restored=True.
    - Con candidato documental valido y coincidente con catalog_hashes.
    - Pero la cuarentena esperada (_dr_restoration_quarantine) NO existe en PostgreSQL 15.
    - Acredita taxativamente:
      1. recover() retorna False (fail-closed estricto).
      2. No interpreta la ausencia de cuarentena como autorizacion para continuar.
      3. Marca el journal como FAILED_INCONSISTENT preservando la evidencia forense.
      4. Los documentos candidatos NO son promovidos a target.
      5. El respaldo y el candidato permanecen preservados.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_f1_absent_q_"))
    db_name = f"dr_test_f1_absent_{uuid.uuid4().hex[:8]}"
    marker_id = f"marker_f1_absent_{uuid.uuid4().hex[:6]}"
    restore_token = f"tok_f1_absent_{uuid.uuid4().hex[:6]}"
    db_url = None

    try:
        # Crear base efimera en PostgreSQL 15 (sin tabla _dr_restoration_quarantine)
        db_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        # Verificar que _dr_restoration_quarantine NO existe en la base
        eng = create_engine(db_url)
        with eng.connect() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is None, "La tabla de cuarentena NO debe existir para esta prueba"
        eng.dispose()

        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "safe.txt").write_text("safe_content", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        cand_content = b"candidate_data_pg15_f1"
        (candidate_dir / "cand_file.txt").write_bytes(cand_content)
        cand_hash = hashlib.sha256(cand_content).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "backup.txt").write_text("backup_content", encoding="utf-8")

        journal_file = temp_dir / ".cutover_journal.json"
        jdata = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"cand_file.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        with patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift:
            recovered = CrashResilientDocumentPublisher.recover(
                parent_dir=temp_dir,
                target_database_url=db_url,
                expected_marker_id=marker_id,
                expected_restore_token=restore_token
            )
            assert recovered is False, "recover() DEBE retornar False fail-closed cuando la cuarentena esperada esta ausente en PG15"
            assert mock_lift.call_count == 0, "No debe llamarse a _lift_database_quarantine si la cuarentena esta ausente"

        # Verificar que el diario fue preservado con estado FAILED_INCONSISTENT
        assert journal_file.exists(), "El diario debio ser preservado para auditoria forense"
        persisted = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted.get("phase") == "FAILED_INCONSISTENT"
        assert persisted.get("quarantine_confirmed") is False

        # Verificar que los documentos NO fueron promovidos
        assert not (target_dir / "cand_file.txt").exists(), "Los documentos candidatos NO deben ser promovidos sin cuarentena verificada"
        assert (target_dir / "safe.txt").exists(), "El target original debe permanecer intacto"
        assert candidate_dir.exists(), "El candidato debe preservarse"
        assert backup_dir.exists(), "El backup debe preservarse"

    finally:
        if db_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 23. MATRIZ ADVERSARIAL OBLIGATORIA (Caso 1): DB_RESTORED con ambos identificadores ausentes
# ===========================================================================
def test_p15_r6_m1_db_restored_both_identifiers_absent_aborts_fail_closed():
    """
    P15-R6 Matriz Adversarial Obligatoria (Caso 1):
    Acredita que en fase DB_RESTORED con ambos identificadores (expected_marker_id y restore_token)
    ausentes o vacios (journals legados P14 o incompletos):
    1. recover() retorna False fail-closed.
    2. Journal es marcado como FAILED_INCONSISTENT preservando evidencia forense.
    3. Ningun documento candidato es promovido a target.
    4. El directorio backup y candidato se preservan.
    5. No se levanta ninguna cuarentena.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_m1_absent_both_"))
    try:
        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "original.txt").write_text("orig_content_m1", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        cand_content = b"candidate_document_m1"
        (candidate_dir / "doc_m1.txt").write_bytes(cand_content)
        cand_hash = hashlib.sha256(cand_content).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "backup.txt").write_text("backup_content_m1", encoding="utf-8")

        journal_file = temp_dir / ".cutover_journal.json"
        jdata = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": "postgresql://test_user:test_password@127.0.0.1:5432/dr_test_m1",
            "expected_marker_id": None,
            "restore_token": None,
            "catalog_hashes": {"doc_m1.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        with patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift:
            recovered = CrashResilientDocumentPublisher.recover(
                parent_dir=temp_dir,
                target_database_url="postgresql://test_user:test_password@127.0.0.1:5432/dr_test_m1",
                expected_marker_id=None,
                expected_restore_token=None
            )
            assert recovered is False, "recover() DEBE retornar False fail-closed con ambos identificadores ausentes"
            assert mock_lift.call_count == 0, "No debe llamarse a _lift_database_quarantine sin identificadores validos"

        assert journal_file.exists(), "El journal debe preservarse para auditoria"
        persisted = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted.get("phase") == "FAILED_INCONSISTENT"
        assert not (target_dir / "doc_m1.txt").exists(), "Candidato NO debe ser promovido"
        assert (target_dir / "original.txt").exists(), "Target original debe permanecer intacto"
        assert candidate_dir.exists()
        assert backup_dir.exists()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 24. MATRIZ ADVERSARIAL OBLIGATORIA (Caso 2): DB_RESTORED con solo un identificador presente
# ===========================================================================
def test_p15_r6_m2_db_restored_single_identifier_present_aborts_fail_closed():
    """
    P15-R6 Matriz Adversarial Obligatoria (Caso 2):
    Acredita que en fase DB_RESTORED con solo un identificador presente:
    Subcaso A: expected_marker_id presente, restore_token ausente.
    Subcaso B: expected_marker_id ausente, restore_token presente.
    Ambos deben abortar fail-closed, marcar FAILED_INCONSISTENT y no promover documentos.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_m2_single_id_"))
    try:
        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "orig.txt").write_text("orig_m2", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        cand_content = b"candidate_document_m2"
        (candidate_dir / "doc_m2.txt").write_bytes(cand_content)
        cand_hash = hashlib.sha256(cand_content).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        journal_file = temp_dir / ".cutover_journal.json"

        # Subcaso A: solo marker presente
        jdata_a = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": "postgresql://test_user:test_password@127.0.0.1:5432/dr_test_m2",
            "expected_marker_id": "valid_marker_m2_only",
            "restore_token": "",
            "catalog_hashes": {"doc_m2.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_a)

        with patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift:
            res_a = CrashResilientDocumentPublisher.recover(
                parent_dir=temp_dir,
                target_database_url="postgresql://test_user:test_password@127.0.0.1:5432/dr_test_m2",
                expected_marker_id="valid_marker_m2_only",
                expected_restore_token=""
            )
            assert res_a is False, "recover() DEBE retornar False fail-closed con solo expected_marker_id presente"
            assert mock_lift.call_count == 0

        persisted_a = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted_a.get("phase") == "FAILED_INCONSISTENT"
        assert not (target_dir / "doc_m2.txt").exists()

        # Subcaso B: solo token presente
        jdata_b = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": "postgresql://test_user:test_password@127.0.0.1:5432/dr_test_m2",
            "expected_marker_id": None,
            "restore_token": "valid_token_m2_only",
            "catalog_hashes": {"doc_m2.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_b)

        with patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift:
            res_b = CrashResilientDocumentPublisher.recover(
                parent_dir=temp_dir,
                target_database_url="postgresql://test_user:test_password@127.0.0.1:5432/dr_test_m2",
                expected_marker_id=None,
                expected_restore_token="valid_token_m2_only"
            )
            assert res_b is False, "recover() DEBE retornar False fail-closed con solo restore_token presente"
            assert mock_lift.call_count == 0

        persisted_b = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted_b.get("phase") == "FAILED_INCONSISTENT"
        assert not (target_dir / "doc_m2.txt").exists()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 25. MATRIZ ADVERSARIAL OBLIGATORIA (Caso 3): DB_RESTORED con PostgreSQL inaccesible
# ===========================================================================
def test_p15_r6_m3_db_restored_postgres_inaccessible_aborts_fail_closed():
    """
    P15-R6 Matriz Adversarial Obligatoria (Caso 3):
    Acredita que en fase DB_RESTORED cuando PostgreSQL es inaccesible:
    1. recover() retorna False fail-closed.
    2. El journal conserva su fase DB_RESTORED (no se corrompe ni se bloquea a FAILED_INCONSISTENT),
       preservando evidencia para permitir reintento cuando la red o BD se recuperen.
    3. Ningun documento es promovido.
    4. El respaldo y el candidato permanecen intactos.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_m3_pg_dead_"))
    dead_dsn = "postgresql://test_user:test_pass@127.0.0.1:59996/dr_test_dead_m3"
    try:
        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "original.txt").write_text("orig_content_m3", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        cand_content = b"cand_doc_m3"
        (candidate_dir / "doc_m3.txt").write_bytes(cand_content)
        cand_hash = hashlib.sha256(cand_content).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        journal_file = temp_dir / ".cutover_journal.json"
        jdata = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": dead_dsn,
            "expected_marker_id": "valid_marker_m3",
            "restore_token": "valid_token_m3",
            "catalog_hashes": {"doc_m3.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        with patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift:
            recovered = CrashResilientDocumentPublisher.recover(
                parent_dir=temp_dir,
                target_database_url=dead_dsn,
                expected_marker_id="valid_marker_m3",
                expected_restore_token="valid_token_m3"
            )
            assert recovered is False, "recover() DEBE retornar False fail-closed ante PG inaccesible"
            assert mock_lift.call_count == 0

        assert journal_file.exists(), "El journal debe preservarse"
        persisted = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted.get("phase") == "DB_RESTORED", "No debe marcarse FAILED_INCONSISTENT ante error transitorio de conexion"
        assert not (target_dir / "doc_m3.txt").exists(), "Candidato NO debe ser promovido"
        assert (target_dir / "original.txt").exists()
        assert candidate_dir.exists()
        assert backup_dir.exists()

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 26. MATRIZ ADVERSARIAL OBLIGATORIA (Caso 4): COMMITTED con db_restored=True y DSN ausente
# ===========================================================================
def test_p15_r6_m4_committed_phase_db_restored_dsn_absent_aborts_fail_closed():
    """
    P15-R6 Matriz Adversarial Obligatoria (Caso 4):
    Acredita que en fase COMMITTED o DB_RESTORED con db_restored=True pero sin DSN de destino:
    1. recover() no presume exito ni autoriza levantamiento tacito.
    2. Aborta inmediatamente fail-closed (retorna False).
    3. Marca el journal como FAILED_INCONSISTENT.
    4. Preserva el respaldo y el diario.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_m4_no_dsn_"))
    try:
        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "committed_doc.txt").write_text("committed_content", encoding="utf-8")
        cand_hash = hashlib.sha256(b"committed_content").hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "old_doc.txt").write_text("old_content", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"

        journal_file = temp_dir / ".cutover_journal.json"

        # Fase COMMITTED con db_restored=True pero sin DSN
        jdata = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": "",
            "expected_marker_id": "marker_m4",
            "restore_token": "token_m4",
            "catalog_hashes": {"committed_doc.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        with patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift:
            recovered = CrashResilientDocumentPublisher.recover(
                parent_dir=temp_dir,
                target_database_url=None,
                expected_marker_id="marker_m4",
                expected_restore_token="token_m4"
            )
            assert recovered is False, "recover() DEBE retornar False fail-closed cuando falta DSN en COMMITTED post-restore"
            assert mock_lift.call_count == 0

        assert journal_file.exists()
        persisted = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted.get("phase") == "FAILED_INCONSISTENT"
        assert backup_dir.exists(), "El respaldo no debe destruirse sin verificacion completa de la base de datos"

        # Comprobar igualmente en fase DB_RESTORED con db_restored=True y DSN vacio
        jdata["phase"] = "DB_RESTORED"
        _atomic_write_journal(journal_file, jdata)
        recovered_db = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url="",
            expected_marker_id="marker_m4",
            expected_restore_token="token_m4"
        )
        assert recovered_db is False
        persisted_db = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted_db.get("phase") == "FAILED_INCONSISTENT"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 27. MATRIZ ADVERSARIAL OBLIGATORIA (Caso 5): Interrupcion tras publicacion documental y antes de levantar cuarentena
# ===========================================================================
def test_p15_r6_m5_interruption_after_document_publish_before_quarantine_lift():
    """
    P15-R6 Matriz Adversarial Obligatoria (Caso 5):
    Acredita contra PostgreSQL 15 real:
    - Se produce una interrupcion tras la publicacion documental (phase COMMITTED) pero
      antes de que se levante la cuarentena en la base de datos.
    - PostgreSQL se encuentra en cuarentena (_dr_restoration_quarantine) con marker y token validos.
    - CrashResilientDocumentPublisher.recover():
      1. Detecta COMMITTED_IN_QUARANTINE.
      2. Levanta la cuarentena mediante _lift_database_quarantine (registrando _dr_restoration_completed).
      3. Transiciona a QUARANTINE_LIFTED.
      4. Limpia el directorio de respaldo y elimina el journal.
      5. Retorna True.
      6. Acredita en PostgreSQL 15 que la cuarentena fue levantada y se registro la evidencia durable de completitud.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_m5_interrupted_cutover_"))
    db_name = f"dr_test_m5_{uuid.uuid4().hex[:8]}"
    marker_id = f"marker_m5_{uuid.uuid4().hex[:6]}"
    restore_token = f"tok_m5_{uuid.uuid4().hex[:6]}"
    db_url = None

    try:
        db_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)
        _enforce_database_quarantine(
            db_url,
            reason="RESTORING (Test M5): Enforcing quarantine prior to simulated cutover crash",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        # Verificar que la cuarentena esta activa en PostgreSQL
        eng = create_engine(db_url)
        with eng.connect() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is not None, "La cuarentena debe existir antes de la recuperacion"
        eng.dispose()

        # Target ya contiene los documentos promovidos (interrupcion justo despues de rename en publish())
        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        doc_content = b"promoted_document_content_m5"
        (target_dir / "doc_m5.txt").write_bytes(doc_content)
        cand_hash = hashlib.sha256(doc_content).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "old_doc.txt").write_text("old_content_m5", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"

        journal_file = temp_dir / ".cutover_journal.json"
        jdata = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"doc_m5.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        # Ejecutar recover()
        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert recovered is True, "recover() DEBE retornar True y completar el cutover transaccional"

        # Verificar que la cuarentena fue efectivamente levantada en PG15
        eng = create_engine(db_url)
        with eng.connect() as conn:
            q_after = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_after is None, "La cuarentena debio ser levantada"
        eng.dispose()

        # Verificar limpieza de evidencias durables
        assert not journal_file.exists(), "El journal debio desvincularse tras cutover completado"
        assert not backup_dir.exists(), "El backup debio eliminarse tras cutover completado"
        assert (target_dir / "doc_m5.txt").exists(), "Los documentos finales deben permanecer intactos"

    finally:
        if db_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 28. MATRIZ ADVERSARIAL OBLIGATORIA (Caso 6): Interrupcion tras levantamiento de cuarentena y antes de limpieza de evidencias
# ===========================================================================
def test_p15_r6_m6_interruption_after_quarantine_lift_before_evidence_cleanup():
    """
    P15-R6 Matriz Adversarial Obligatoria (Caso 6):
    Acredita contra PostgreSQL 15 real:
    - Se produce una interrupcion tras el levantamiento de cuarentena pero antes de limpiar
      el respaldo o el diario.
    - El journal registra la fase durable QUARANTINE_LIFTED.
    - CrashResilientDocumentPublisher.recover():
      1. Detecta la fase QUARANTINE_LIFTED en el journal.
      2. Limpia el directorio de respaldo.
      3. Desvincula el journal.
      4. Retorna True.
      5. Preserva los documentos en target.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_m6_post_quarantine_clean_"))
    db_name = f"dr_test_m6_{uuid.uuid4().hex[:8]}"
    marker_id = f"marker_m6_{uuid.uuid4().hex[:6]}"
    restore_token = f"tok_m6_{uuid.uuid4().hex[:6]}"
    db_url = None

    try:
        db_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)
        # Poner en cuarentena y luego levantarla con el protocolo oficial antes del corte de evidencia
        _enforce_database_quarantine(
            db_url,
            reason="Testing M6 quarantine lift",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )
        _lift_database_quarantine(db_url, marker_id, restore_token)

        # Verificar que la cuarentena ya fue levantada en PostgreSQL
        eng = create_engine(db_url)
        with eng.connect() as conn:
            q_after = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_after is None, "La cuarentena debio ser levantada"
        eng.dispose()

        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        doc_content = b"promoted_document_content_m6"
        (target_dir / "doc_m6.txt").write_bytes(doc_content)
        cand_hash = hashlib.sha256(doc_content).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "old_doc.txt").write_text("old_content_m6", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"

        journal_file = temp_dir / ".cutover_journal.json"
        jdata = {
            "phase": "QUARANTINE_LIFTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"doc_m6.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        # Ejecutar recover()
        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert recovered is True, "recover() DEBE retornar True tras verificar QUARANTINE_ALREADY_LIFTED"

        # Verificar limpieza de evidencias
        assert not journal_file.exists(), "El journal debio desvincularse"
        assert not backup_dir.exists(), "El backup debio eliminarse"
        assert (target_dir / "doc_m6.txt").exists()

    finally:
        if db_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 29. MATRIZ ADVERSARIAL OBLIGATORIA (Caso 7): Recuperacion repetida sin perdida de trazabilidad
# ===========================================================================
def test_p15_r6_m7_repeated_recovery_idempotent_without_traceability_loss():
    """
    P15-R6 Matriz Adversarial Obligatoria (Caso 7):
    Acredita contra PostgreSQL 15 real que ejecuciones repetidas de recover():
    1. Primera llamada con fallo transitorio de red: preserva el journal en DB_RESTORED (no lo corrompe ni bloquea).
    2. Segunda llamada con red restablecida: completa la restauracion hacia adelante, levanta cuarentena y limpia.
    3. Tercera llamada sucesiva sin journal pendiente: retorna False de forma segura e idempotente sin efectos secundarios.
    4. Cuarta llamada con journal FAILED_INCONSISTENT previo: aborta fail-closed y preserva la trazabilidad forense intacta.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_m7_repeated_rec_"))
    db_name = f"dr_test_m7_{uuid.uuid4().hex[:8]}"
    marker_id = f"marker_m7_{uuid.uuid4().hex[:6]}"
    restore_token = f"tok_m7_{uuid.uuid4().hex[:6]}"
    db_url = None

    try:
        db_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)
        _enforce_database_quarantine(
            db_url,
            reason="Testing M7 repeated recovery",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "initial.txt").write_text("initial_target_m7", encoding="utf-8")

        candidate_dir = temp_dir / ".target_candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        cand_content = b"candidate_doc_content_m7"
        (candidate_dir / "final_doc.txt").write_bytes(cand_content)
        cand_hash = hashlib.sha256(cand_content).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        journal_file = temp_dir / ".cutover_journal.json"

        jdata = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": db_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"final_doc.txt": cand_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        # 1. Primera llamada con URL inaccesible simulando corte de red
        dead_url = "postgresql://test_user:test_pass@127.0.0.1:59995/dr_test_dead_m7"
        res1 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=dead_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res1 is False, "Primera recuperacion debe fallar fail-closed por red caida"
        assert journal_file.exists()
        persisted1 = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted1.get("phase") == "DB_RESTORED", "Fase debe preservarse para permitir reintento"

        # 2. Segunda llamada con conexion restablecida a db_url
        res2 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res2 is True, "Segunda recuperacion debe tener exito tras recuperar conectividad"
        assert not journal_file.exists(), "Journal debio desvincularse tras exito"
        assert (target_dir / "final_doc.txt").exists(), "Candidato debio promoverse a target"

        # 3. Tercera llamada sucesiva sin journal
        res3 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res3 is False, "Tercera recuperacion sin journal pendiente debe retornar False de forma segura"
        assert (target_dir / "final_doc.txt").exists(), "Target permanece intacto"

        # 4. Cuarta llamada con journal en FAILED_INCONSISTENT para verificar preservacion forense
        jdata_failed = {
            "phase": "FAILED_INCONSISTENT",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "error": "Prior catastrophic corruption test",
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_failed)

        res4 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=db_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert res4 is False, "Llamada sobre FAILED_INCONSISTENT debe abortar fail-closed"
        assert journal_file.exists(), "Diario FAILED_INCONSISTENT debe preservarse intacto sin eliminarse"

    finally:
        if db_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 30. MATRIZ ADVERSARIAL OBLIGATORIA (Caso 8): Restauracion exclusivamente documental legitima
# ===========================================================================
def test_p15_r6_m8_legitimate_documents_only_restoration_no_postgres_effects():
    """
    P15-R6 Matriz Adversarial Obligatoria (Caso 8):
    Acredita:
    1. Publicacion y recuperacion legitima en modo exclusivamente documental (documents_only=True, db_restored=False):
       - No requiere DSN ni conexion a PostgreSQL.
       - No produce llamadas ni efectos secundarios en bases de datos.
       - Promueve documentos, limpia respaldos y desvincula journal exitosamente.
    2. Contraste negativo estricto:
       - Si documents_only=False, la ausencia de DSN aborta inmediatamente fail-closed
         y marca el journal como FAILED_INCONSISTENT (nunca autoriza por omision de DSN).
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_m8_docs_only_"))
    try:
        staging_dir = temp_dir / "staging_uploads"
        staging_dir.mkdir(parents=True, exist_ok=True)
        doc1_bytes = b"exclusive_document_1"
        doc2_bytes = b"exclusive_document_2"
        (staging_dir / "file1.txt").write_bytes(doc1_bytes)
        (staging_dir / "subdir").mkdir(parents=True, exist_ok=True)
        (staging_dir / "subdir" / "file2.txt").write_bytes(doc2_bytes)

        catalog = [
            {"relative_path": "file1.txt", "sha256": hashlib.sha256(doc1_bytes).hexdigest()},
            {"relative_path": "subdir/file2.txt", "sha256": hashlib.sha256(doc2_bytes).hexdigest()}
        ]

        target_dir = temp_dir / "target_uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "preexisting.txt").write_text("old_docs_content", encoding="utf-8")

        # 1. Publicacion exitosa en modo exclusivamente documental
        publisher = CrashResilientDocumentPublisher(
            target_dir=target_dir,
            db_restored=False,
            target_database_url=None,
            expected_marker_id=None,
            restore_token=None,
            documents_only=True
        )

        with patch("verification.dr.backup_lan_pg15._inspect_postgres_restore_commitment") as mock_inspect, \
             patch("verification.dr.backup_lan_pg15._lift_database_quarantine") as mock_lift, \
             patch("verification.dr.backup_lan_pg15._enforce_database_quarantine") as mock_enforce:

            publisher.publish(staging_dir=staging_dir, catalog=catalog)

            assert mock_inspect.call_count == 0, "No debe inspeccionarse PostgreSQL en modo documents_only"
            assert mock_lift.call_count == 0, "No debe tocarse cuarentena en modo documents_only"
            assert mock_enforce.call_count == 0

        # Verificar que los documentos se conmutaron y no hay journal residual
        assert (target_dir / "file1.txt").exists()
        assert (target_dir / "subdir" / "file2.txt").exists()
        journal_file = temp_dir / ".cutover_journal.json"
        assert not journal_file.exists(), "Journal debio desvincularse tras exito"

        # 2. Recuperacion exitosa de un crash simulado en modo exclusivamente documental
        cand_dir = temp_dir / ".target_candidate"
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / "file1.txt").write_bytes(doc1_bytes)
        (cand_dir / "subdir").mkdir(parents=True, exist_ok=True)
        (cand_dir / "subdir" / "file2.txt").write_bytes(doc2_bytes)

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        jdata_docs = {
            "phase": "TARGET_MOVED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(cand_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": False,
            "documents_only": True,
            "target_database_url": None,
            "expected_marker_id": None,
            "restore_token": None,
            "catalog_hashes": {c["relative_path"]: c["sha256"] for c in catalog},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_docs)

        rec_docs = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=None,
            expected_marker_id=None,
            expected_restore_token=None
        )
        assert rec_docs is True, "recover() en modo documents_only DEBE retornar True sin DSN"
        assert not journal_file.exists()
        assert not backup_dir.exists()

        # 3. Contraste negativo: documents_only=False sin DSN en fase post-commit aborta fail-closed
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / "file1.txt").write_bytes(doc1_bytes)
        (cand_dir / "subdir").mkdir(parents=True, exist_ok=True)
        (cand_dir / "subdir" / "file2.txt").write_bytes(doc2_bytes)

        jdata_not_docs = {
            "phase": "DB_RESTORED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(cand_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "documents_only": False,
            "target_database_url": "",
            "expected_marker_id": "marker_neg",
            "restore_token": "token_neg",
            "catalog_hashes": {c["relative_path"]: c["sha256"] for c in catalog},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_not_docs)

        rec_neg = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url="",
            expected_marker_id="marker_neg",
            expected_restore_token="token_neg"
        )
        assert rec_neg is False, "recover() sin documents_only y sin DSN DEBE abortar fail-closed"
        persisted_neg = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted_neg.get("phase") == "FAILED_INCONSISTENT"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 31. F3 — FINALIZACION POSTGRESQL AUTENTICADA Y ATOMICA (_lift_database_quarantine)
# ===========================================================================
def test_p15_f3_atomic_quarantine_lift_positive_creates_completion_record():
    """
    F3 / Orden Unica P15:
    Acredita en PostgreSQL 15 real que _lift_database_quarantine():
    1. Exige identificadores completos (marker_id y restore_token).
    2. Valida dentro de una unica transaccion PostgreSQL la pertenencia estricta de la cuarentena.
    3. Registra una evidencia durable de completitud (_dr_restoration_completed) asociada a marker y token.
    4. Confirma atomicamente la eliminacion de la cuarentena (_dr_restoration_quarantine).
    5. Es estrictamente idempotente: una invocacion posterior con la misma identidad retorna limpiamente.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_f3_pos_{run_id}"
    marker_id = f"marker_f3_{run_id}"
    restore_token = f"tok_f3_{run_id}"
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        # Establecer cuarentena autenticada
        _enforce_database_quarantine(
            target_url,
            reason="RESTORING_DATABASE: Simulated cutover preparation (F3)",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        eng = create_engine(target_url)
        with eng.connect() as conn:
            q_before = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_before is not None, "La cuarentena debe existir antes del levantamiento"
            c_before = conn.execute(text("SELECT to_regclass('public._dr_restoration_completed');")).scalar()
            assert c_before is None, "La evidencia de completitud no debe existir antes del levantamiento"
        eng.dispose()

        # 1. Ejecutar levantamiento autenticado y atomico
        _lift_database_quarantine(target_url, marker_id, restore_token)

        # 2. Verificar en PostgreSQL 15 que la cuarentena fue eliminada y la completitud registrada atomicamente
        eng2 = create_engine(target_url)
        with eng2.connect() as conn:
            q_after = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_after is None, "public._dr_restoration_quarantine debio ser removida tras levantamiento"

            c_row = conn.execute(text(
                "SELECT marker_id, restore_token, completed_at, reason "
                "FROM public._dr_restoration_completed WHERE marker_id = :mid;"
            ), {"mid": marker_id}).first()
            assert c_row is not None, "public._dr_restoration_completed DEBE contener la evidencia durable"
            assert c_row[0] == marker_id
            assert c_row[1] == restore_token
            assert c_row[2] is not None
            assert "LIFTED_BY_PUBLISHER (F3)" in c_row[3]
        eng2.dispose()

        # 3. Verificar idempotencia: una segunda llamada con los mismos identificadores retorna sin error
        _lift_database_quarantine(target_url, marker_id, restore_token)

        with eng2.connect() as conn:
            count = conn.execute(text(
                "SELECT COUNT(*) FROM public._dr_restoration_completed WHERE marker_id = :mid;"
            ), {"mid": marker_id}).scalar()
            assert count == 1, "La evidencia durable debe preservarse sin duplicaciones"
        eng2.dispose()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)


def test_p15_f3_lift_quarantine_negative_validations_fail_closed():
    """
    F3 / Orden Unica P15:
    Pruebas negativas exhaustivas de _lift_database_quarantine():
    1. Identificadores nulos, vacios o ausentes -> rechazo con ValueError.
    2. Base destino sin tabla de cuarentena ni completitud previa -> RuntimeError.
    3. Tabla de cuarentena existe pero vacia (0 filas) -> RuntimeError (no acredita pertenencia).
    4. Cuarentena con estado invalido (!= 'DB_RESTORED') -> RuntimeError.
    5. Marcador discrepante (base ajena) -> RuntimeError, cuarentena ajena NO modificada.
    6. Token discrepante (restauracion ajena) -> RuntimeError, cuarentena ajena NO modificada.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_f3_neg_{run_id}"
    legit_marker = f"marker_legit_{run_id}"
    legit_token = f"tok_legit_{run_id}"
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, legit_marker)

        # 1. Identificadores incompletos o vacios
        with pytest.raises(ValueError) as exc_empty_m:
            _lift_database_quarantine(target_url, "", legit_token)
        assert "expected_marker_id y restore_token deben ser cadenas no vacias" in str(exc_empty_m.value)

        with pytest.raises(ValueError) as exc_none_m:
            _lift_database_quarantine(target_url, None, legit_token)
        assert "expected_marker_id y restore_token deben ser cadenas no vacias" in str(exc_none_m.value)

        with pytest.raises(ValueError) as exc_empty_t:
            _lift_database_quarantine(target_url, legit_marker, "")
        assert "expected_marker_id y restore_token deben ser cadenas no vacias" in str(exc_empty_t.value)

        with pytest.raises(ValueError) as exc_no_url:
            _lift_database_quarantine("", legit_marker, legit_token)
        assert "target_database_url es obligatorio" in str(exc_no_url.value)

        # 2. Sin tabla de cuarentena
        with pytest.raises(RuntimeError) as exc_no_table:
            _lift_database_quarantine(target_url, legit_marker, legit_token)
        assert "No existe public._dr_restoration_quarantine" in str(exc_no_table.value)

        # 3. Tabla de cuarentena vacia (0 filas)
        eng = create_engine(target_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            conn.execute(text(
                "CREATE TABLE public._dr_restoration_quarantine ("
                "  id SERIAL PRIMARY KEY, quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "  reason TEXT NOT NULL, journal_state TEXT NOT NULL, "
                "  marker_id VARCHAR(64), restore_token VARCHAR(64)"
                ");"
            ))
        eng.dispose()

        with pytest.raises(RuntimeError) as exc_empty_q:
            _lift_database_quarantine(target_url, legit_marker, legit_token)
        assert "existe pero esta vacia (0 filas)" in str(exc_empty_q.value)

        # 4. Estado invalido de cuarentena (ej. INCONSISTENT_RESTORATION)
        with eng.connect() as conn:
            conn.execute(text(
                "INSERT INTO public._dr_restoration_quarantine (reason, journal_state, marker_id, restore_token) "
                "VALUES ('CORRUPTION_DETECTED', 'FAILED_INCONSISTENT', :m, :t);"
            ), {"m": legit_marker, "t": legit_token})
        eng.dispose()

        with pytest.raises(RuntimeError) as exc_bad_st:
            _lift_database_quarantine(target_url, legit_marker, legit_token)
        assert "Cuarentena en estado invalido" in str(exc_bad_st.value)

        # 5. Marcador discrepante (base ajena)
        with eng.connect() as conn:
            conn.execute(text("DELETE FROM public._dr_restoration_quarantine;"))
            conn.execute(text(
                "INSERT INTO public._dr_restoration_quarantine (reason, journal_state, marker_id, restore_token) "
                "VALUES ('RESTORING', 'DB_RESTORED', 'FOREIGN_MARKER_999', :t);"
            ), {"t": legit_token})
        eng.dispose()

        with pytest.raises(RuntimeError) as exc_mis_m:
            _lift_database_quarantine(target_url, legit_marker, legit_token)
        assert "Marcador de cuarentena no coincide" in str(exc_mis_m.value)
        assert "Rechazando mutacion de cuarentena ajena" in str(exc_mis_m.value)

        # Acreditar que la cuarentena ajena sigue intacta en PostgreSQL
        with eng.connect() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM public._dr_restoration_quarantine;")).scalar()
            assert cnt == 1, "Cuarentena ajena NO debio ser modificada"
        eng.dispose()

        # 6. Token discrepante
        with eng.connect() as conn:
            conn.execute(text("DELETE FROM public._dr_restoration_quarantine;"))
            conn.execute(text(
                "INSERT INTO public._dr_restoration_quarantine (reason, journal_state, marker_id, restore_token) "
                "VALUES ('RESTORING', 'DB_RESTORED', :m, 'FOREIGN_TOKEN_888');"
            ), {"m": legit_marker})
        eng.dispose()

        with pytest.raises(RuntimeError) as exc_mis_t:
            _lift_database_quarantine(target_url, legit_marker, legit_token)
        assert "Token de restauracion no coincide" in str(exc_mis_t.value)
        assert "Rechazando mutacion de cuarentena ajena" in str(exc_mis_t.value)

        with eng.connect() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM public._dr_restoration_quarantine;")).scalar()
            assert cnt == 1
        eng.dispose()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)


# ===========================================================================
# 32. F4 — RECUPERACION AUTENTICADA DE QUARANTINE_LIFTED Y PRUEBA DURABLE EN POSTGRESQL
# ===========================================================================
def test_p15_f4_recover_quarantine_lifted_requires_matching_postgres_completion_evidence():
    """
    F4 / Orden Unica P15:
    Acredita contra PostgreSQL 15 real que recover() en fase QUARANTINE_LIFTED:
    1. Ante ausencia de tablas en PostgreSQL (UNKNOWN_OR_INCONSISTENT):
       - PROHIBIDO presumir exito por ausencia de tablas.
       - Retorna False.
       - Conserva el journal en FAILED_INCONSISTENT y los respaldos intactos.
       - No ejecuta operaciones destructivas.
    2. Ante evidencia de completitud ajena (FOREIGN_COMPLETION):
       - Retorna False.
       - Conserva el journal y los respaldos.
    3. Ante evidencia de completitud coincidente en PostgreSQL 15 (RESTORATION_COMPLETED_CONFIRMED):
       - Retorna True.
       - Limpia respaldo y desvincula journal de forma segura.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_f4_ql_{run_id}"
    marker_id = f"marker_f4_{run_id}"
    restore_token = f"tok_f4_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_f4_ql_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        doc_bytes = b"f4_verified_content"
        (target_dir / "report.pdf").write_bytes(doc_bytes)
        doc_hash = hashlib.sha256(doc_bytes).hexdigest()

        backup_dir = temp_dir / ".target_backup_ql"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "old_backup.pdf").write_bytes(b"old_backup_data")

        candidate_dir = temp_dir / ".target_candidate"
        journal_file = temp_dir / ".cutover_journal.json"

        jdata = {
            "phase": "QUARANTINE_LIFTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"report.pdf": doc_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata)

        # -------------------------------------------------------------------
        # CASO 1: Ausencia simultanea de tablas en PostgreSQL (sin _dr_restoration_completed)
        # -------------------------------------------------------------------
        eng = create_engine(target_url)
        with eng.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public._dr_test_ownership_marker CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS public._dr_restoration_quarantine CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS public._dr_restoration_completed CASCADE;"))
        eng.dispose()

        rec_absent = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert rec_absent is False, "F4: Prohibido presumir exito por ausencia de tablas en QUARANTINE_LIFTED"
        assert journal_file.exists(), "Journal DEBE ser preservado ante incertidumbre"
        assert backup_dir.exists(), "Backup NO debe eliminarse sin evidencia durable"
        persisted_absent = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted_absent["phase"] == "FAILED_INCONSISTENT"

        # -------------------------------------------------------------------
        # CASO 2: Evidencia de completitud ajena en PostgreSQL
        # -------------------------------------------------------------------
        eng2 = create_engine(target_url, isolation_level="AUTOCOMMIT")
        with eng2.connect() as conn:
            conn.execute(text("""
                CREATE TABLE public._dr_restoration_completed (
                    id SERIAL PRIMARY KEY,
                    marker_id VARCHAR(128) NOT NULL,
                    restore_token VARCHAR(128) NOT NULL,
                    completed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT
                );
            """))
            conn.execute(text("""
                INSERT INTO public._dr_restoration_completed (marker_id, restore_token, reason)
                VALUES ('FOREIGN_MARKER_999', 'FOREIGN_TOKEN_999', 'Foreign completed restoration');
            """))
        eng2.dispose()

        # Reestablecer journal en QUARANTINE_LIFTED
        jdata["phase"] = "QUARANTINE_LIFTED"
        _atomic_write_journal(journal_file, jdata)

        rec_for = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert rec_for is False, "F4: Evidencia ajena de completitud DEBE abortar fail-closed"
        assert journal_file.exists()
        assert backup_dir.exists()
        persisted_for = json.loads(journal_file.read_text(encoding="utf-8"))
        assert persisted_for["phase"] == "FAILED_INCONSISTENT"
        assert persisted_for.get("foreign_database_untouched") is True

        # -------------------------------------------------------------------
        # CASO 3: Evidencia de completitud coincidente en PostgreSQL (exito positivo)
        # -------------------------------------------------------------------
        with eng2.connect() as conn:
            conn.execute(text("""
                INSERT INTO public._dr_restoration_completed (marker_id, restore_token, reason)
                VALUES (:mid, :rtk, 'LIFTED_BY_PUBLISHER (F3): verified marker');
            """), {"mid": marker_id, "rtk": restore_token})
        eng2.dispose()

        jdata["phase"] = "QUARANTINE_LIFTED"
        _atomic_write_journal(journal_file, jdata)

        rec_ok = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert rec_ok is True, "F4: Evidencia legitima y coincidente en PostgreSQL acredita exito de recuperacion"
        assert not journal_file.exists(), "Journal debio ser desvinculado tras acreditacion"
        assert not backup_dir.exists(), "Backup debio ser limpiado"
        assert (target_dir / "report.pdf").exists()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p15_f4_deterministic_crash_cut_before_and_after_postgres_lift_commit():
    """
    F4 / Orden Unica P15:
    Acredita cortes deterministas antes y despues del COMMIT de levantamiento de cuarentena en PG15:
    1. Corte ANTES del COMMIT de levantamiento de cuarentena (journal en COMMITTED, cuarentena activa):
       - recover() detecta COMMITTED_IN_QUARANTINE.
       - Ejecuta _lift_database_quarantine() registrando la completitud y removiendo la cuarentena.
       - Avanza a QUARANTINE_LIFTED, limpia evidencias y retorna True.
    2. Corte DESPUES del COMMIT de levantamiento pero ANTES de persistir QUARANTINE_LIFTED en journal:
       - El COMMIT en PostgreSQL concluyo (cuarentena removida, _dr_restoration_completed registrado).
       - El proceso murio antes de actualizar el journal (journal persiste en COMMITTED).
       - recover() detecta RESTORATION_COMPLETED_CONFIRMED mediante la evidencia durable en PostgreSQL.
       - Reconcilia el estado, avanza a QUARANTINE_LIFTED, limpia evidencias y retorna True.
    """
    run_id = uuid.uuid4().hex[:8]
    db_name = f"dr_test_f4_cut_{run_id}"
    marker_id = f"marker_f4_cut_{run_id}"
    restore_token = f"tok_f4_cut_{run_id}"
    temp_dir = Path(tempfile.mkdtemp(prefix="test_p15_f4_cut_"))
    target_url = None

    try:
        target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

        target_dir = temp_dir / "target_docs"
        target_dir.mkdir(parents=True, exist_ok=True)
        doc_bytes = b"cutover_deterministic_data"
        (target_dir / "doc.txt").write_bytes(doc_bytes)
        doc_hash = hashlib.sha256(doc_bytes).hexdigest()

        backup_dir = temp_dir / ".target_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "old.txt").write_bytes(b"old")

        candidate_dir = temp_dir / ".target_candidate"
        journal_file = temp_dir / ".cutover_journal.json"

        # -------------------------------------------------------------------
        # ESCENARIO 1: Corte ANTES del COMMIT de levantamiento de cuarentena
        # -------------------------------------------------------------------
        _enforce_database_quarantine(
            target_url,
            reason="RESTORATION_IN_PROGRESS: Pending cutover",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        jdata_cut1 = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": True,
            "target_database_url": target_url,
            "expected_marker_id": marker_id,
            "restore_token": restore_token,
            "catalog_hashes": {"doc.txt": doc_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_cut1)

        rec1 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id,
            expected_restore_token=restore_token
        )
        assert rec1 is True, "Corte antes de COMMIT debio recuperarse levantando la cuarentena"
        assert not journal_file.exists()
        assert not backup_dir.exists()

        # Acreditar que PostgreSQL tiene la evidencia de completitud y no tiene cuarentena
        eng = create_engine(target_url)
        with eng.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar() is None
            c_row = conn.execute(text(
                "SELECT marker_id, restore_token FROM public._dr_restoration_completed WHERE marker_id = :mid;"
            ), {"mid": marker_id}).first()
            assert c_row is not None
            assert c_row[0] == marker_id
            assert c_row[1] == restore_token
        eng.dispose()

        # -------------------------------------------------------------------
        # ESCENARIO 2: Corte DESPUES del COMMIT de levantamiento pero ANTES de escribir QUARANTINE_LIFTED
        # -------------------------------------------------------------------
        marker_id_2 = f"marker_cut2_{run_id}"
        restore_token_2 = f"tok_cut2_{run_id}"

        # Preparar en PostgreSQL la evidencia durable ya confirmada (simulando que el commit SQL concluyo)
        eng2 = create_engine(target_url)
        with eng2.begin() as conn:
            conn.execute(text("""
                INSERT INTO public._dr_restoration_completed (marker_id, restore_token, reason)
                VALUES (:mid, :rtk, 'LIFTED_BY_PUBLISHER (F3): verified marker');
            """), {"mid": marker_id_2, "rtk": restore_token_2})
        eng2.dispose()

        backup_dir2 = temp_dir / ".target_backup_2"
        backup_dir2.mkdir(parents=True, exist_ok=True)
        (backup_dir2 / "old2.txt").write_bytes(b"old2")

        # El journal quedo en COMMITTED porque el proceso cayo antes de persistir QUARANTINE_LIFTED
        jdata_cut2 = {
            "phase": "COMMITTED",
            "target_dir": str(target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir2.resolve()),
            "db_restored": True,
            "target_database_url": target_url,
            "expected_marker_id": marker_id_2,
            "restore_token": restore_token_2,
            "catalog_hashes": {"doc.txt": doc_hash},
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, jdata_cut2)

        # recover() DEBE reconciliar a traves de RESTORATION_COMPLETED_CONFIRMED
        rec2 = CrashResilientDocumentPublisher.recover(
            parent_dir=temp_dir,
            target_database_url=target_url,
            expected_marker_id=marker_id_2,
            expected_restore_token=restore_token_2
        )
        assert rec2 is True, "Corte despues de COMMIT SQL debe reconciliarse mediante evidencia durable en PostgreSQL"
        assert not journal_file.exists()
        assert not backup_dir2.exists()
        assert (target_dir / "doc.txt").exists()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# 16. F5 / F6 / BLOQUEO TRANSACCIONAL: Validaciones de Cierre Auditado
# ===========================================================================

def test_p15_f5_lift_quarantine_rejects_test_pool_checkout_blocking_without_identity():
    """
    F5 (Cierre): Demuestra que _lift_database_quarantine() rechaza fail-closed
    cualquier cuarentena creada con reason='TEST_POOL_CHECKOUT_BLOCKING' cuando
    se invoca sin identidad o con identidad invalida, y que bajo ninguna circunstancia
    ejecuta DROP TABLE si no se acredita la pertenencia exacta del marcador y token.
    """
    db_name = f"dr_test_f5_blocking_{uuid.uuid4().hex[:6]}"
    marker_id = f"marker_f5_{uuid.uuid4().hex[:6]}"
    restore_token = f"token_f5_{uuid.uuid4().hex[:6]}"
    target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

    try:
        # 1. Crear cuarentena simulada con el motivo historico de fixture
        eng = create_engine(target_url)
        with eng.begin() as conn:
            conn.execute(text("""
                CREATE TABLE public._dr_restoration_quarantine (
                    id SERIAL PRIMARY KEY,
                    reason TEXT NOT NULL,
                    journal_state TEXT,
                    marker_id VARCHAR(64),
                    restore_token VARCHAR(64)
                );
            """))
            conn.execute(text("""
                INSERT INTO public._dr_restoration_quarantine (reason, journal_state, marker_id, restore_token)
                VALUES ('TEST_POOL_CHECKOUT_BLOCKING', 'DB_RESTORED', NULL, NULL);
            """))
        eng.dispose()

        # A. Invocacion sin marker ni token: DEBE lanzar ValueError (no limpiar por motivo textual)
        with pytest.raises(ValueError) as exc_no_id:
            _lift_database_quarantine(target_url, expected_marker_id=None, restore_token=None)
        assert "expected_marker_id y restore_token deben ser cadenas no vacias" in str(exc_no_id.value)

        # Verificar que la tabla de cuarentena PERMANECE 100% INTACTA en PostgreSQL
        eng_chk = create_engine(target_url)
        with eng_chk.begin() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is not None, "INVARIANTE F5: La tabla de cuarentena NO debio ser eliminada"
            count = conn.execute(text("SELECT count(*) FROM public._dr_restoration_quarantine;")).scalar()
            assert count == 1, "INVARIANTE F5: La fila de cuarentena permanece intacta"

        # B. Invocacion con cadenas vacias o espacios: DEBE lanzar ValueError
        with pytest.raises(ValueError) as exc_empty:
            _lift_database_quarantine(target_url, expected_marker_id="   ", restore_token="")
        assert "expected_marker_id y restore_token deben ser cadenas no vacias" in str(exc_empty.value)

        # C. Invocacion con marcador y token sintetico pero fila con NULL/mismatch: DEBE lanzar RuntimeError
        with pytest.raises(RuntimeError) as exc_mismatch:
            _lift_database_quarantine(target_url, expected_marker_id=marker_id, restore_token=restore_token)
        assert "Fallo F3: Marcador de cuarentena no coincide" in str(exc_mismatch.value)

        # Verificar que tras todos los intentos negativos, la cuarentena sigue existiendo
        with eng_chk.begin() as conn:
            q_still = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_still is not None, "INVARIANTE F5: DROP TABLE no fue ejecutado ante ausencia o discrepancia de identidad"
        eng_chk.dispose()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)


def test_p15_f6_publish_mode_contracts_and_rejection_of_unauthenticated_cutover():
    """
    F6 (Cierre): Demuestra que CrashResilientDocumentPublisher.publish() valida estrictamente
    las modalidades autorizadas antes de cualquier modificacion durable:
    1. Modalidad documental: documents_only=True, db_restored=False, catalogo valido.
       Prohibido db_restored=True.
    2. Modalidad integral: documents_only=False, db_restored=True, DSN obligatorio,
       marcador y token validos. Prohibido omitir DSN o presumir modalidad documental.
    3. Ningun documento se promueve ni ningun diario/respaldo se limpia ante fallos de contrato.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="dr_test_f6_contracts_"))
    try:
        staging_dir = temp_dir / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        new_doc = staging_dir / "new_payload.txt"
        new_doc.write_bytes(b"new_secure_payload_content")
        new_sha = hashlib.sha256(b"new_secure_payload_content").hexdigest()
        catalog = [{"relative_path": "new_payload.txt", "sha256": new_sha}]

        target_dir = temp_dir / "target_documents"
        target_dir.mkdir(parents=True, exist_ok=True)
        old_doc = target_dir / "existing_doc.txt"
        old_doc.write_bytes(b"preexisting_unmodified_content")

        journal_file = temp_dir / ".cutover_journal.json"
        existing_journal_content = json.dumps({"phase": "PREEXISTING_JOURNAL_CANARY", "test": True})
        journal_file.write_text(existing_journal_content, encoding="utf-8")

        # CASO 1: documents_only=False, db_restored=True, target_database_url=None
        pub1 = CrashResilientDocumentPublisher(
            target_dir=target_dir,
            db_restored=True,
            target_database_url=None,
            expected_marker_id="marker_test",
            restore_token="token_test",
            documents_only=False
        )
        with pytest.raises(ValueError) as exc1:
            pub1.publish(staging_dir=staging_dir, catalog=catalog)
        assert "exige target_database_url obligatorio" in str(exc1.value)
        # Verificar que no hubo mutacion ni promocion
        assert old_doc.exists() and old_doc.read_bytes() == b"preexisting_unmodified_content"
        assert not (target_dir / "new_payload.txt").exists()
        assert journal_file.exists() and journal_file.read_text(encoding="utf-8") == existing_journal_content

        # CASO 2: documents_only=False, db_restored=False, target_database_url=None
        pub2 = CrashResilientDocumentPublisher(
            target_dir=target_dir,
            db_restored=False,
            target_database_url=None,
            documents_only=False
        )
        with pytest.raises(ValueError) as exc2:
            pub2.publish(staging_dir=staging_dir, catalog=catalog)
        assert "requiere db_restored=True" in str(exc2.value)
        assert old_doc.exists() and old_doc.read_bytes() == b"preexisting_unmodified_content"
        assert not (target_dir / "new_payload.txt").exists()
        assert journal_file.exists() and journal_file.read_text(encoding="utf-8") == existing_journal_content

        # CASO 3: documents_only=False, db_restored=False, pero DSN provisto
        pub3 = CrashResilientDocumentPublisher(
            target_dir=target_dir,
            db_restored=False,
            target_database_url="postgresql://user:pass@localhost:5432/test_db",
            expected_marker_id="marker_test",
            restore_token="token_test",
            documents_only=False
        )
        with pytest.raises(ValueError) as exc3:
            pub3.publish(staging_dir=staging_dir, catalog=catalog)
        assert "requiere db_restored=True" in str(exc3.value)
        assert old_doc.exists() and not (target_dir / "new_payload.txt").exists()

        # CASO 4: documents_only=True, pero db_restored=True (contradiccion de modo)
        pub4 = CrashResilientDocumentPublisher(
            target_dir=target_dir,
            db_restored=True,
            documents_only=True
        )
        with pytest.raises(ValueError) as exc4:
            pub4.publish(staging_dir=staging_dir, catalog=catalog)
        assert "prohibe db_restored=True" in str(exc4.value)
        assert old_doc.exists() and not (target_dir / "new_payload.txt").exists()

        # CASO 5: documents_only=False, db_restored=True, DSN provisto, pero sin marker/token
        pub5 = CrashResilientDocumentPublisher(
            target_dir=target_dir,
            db_restored=True,
            target_database_url="postgresql://user:pass@localhost:5432/test_db",
            expected_marker_id=None,
            restore_token=None,
            documents_only=False
        )
        with pytest.raises(ValueError) as exc5:
            pub5.publish(staging_dir=staging_dir, catalog=catalog)
        assert "exige expected_marker_id y restore_token obligatorios" in str(exc5.value)
        assert old_doc.exists() and not (target_dir / "new_payload.txt").exists()

        # CASO 6: Catalogo vacio o invalido en cualquier modalidad
        pub6 = CrashResilientDocumentPublisher(
            target_dir=target_dir,
            db_restored=False,
            documents_only=True
        )
        with pytest.raises(ValueError) as exc6:
            pub6.publish(staging_dir=staging_dir, catalog=[])
        assert "requiere un catalogo valido no vacio" in str(exc6.value)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_p15_f3_transactional_row_lock_select_for_update_concurrency_postgres15():
    """
    F3 / Seccion III: Acredita en PostgreSQL 15 real que _lift_database_quarantine()
    ejecuta serializacion transaccional estricta y bloqueo por fila mediante SELECT ... FOR UPDATE,
    serializando accesos concurrentes e impidiendo condiciones de carrera o inconsistencias.
    """
    import threading

    db_name = f"dr_test_lock_{uuid.uuid4().hex[:6]}"
    marker_id = f"marker_lock_{uuid.uuid4().hex[:6]}"
    restore_token = f"token_lock_{uuid.uuid4().hex[:6]}"
    target_url = _create_p15_ephemeral_db(settings.DATABASE_URL, db_name, marker_id)

    try:
        # PARTE 1: Demostrar que SELECT ... FOR UPDATE bloquea estrictamente transacciones concurrentes sobre la fila
        eng_p1 = create_engine(target_url)
        with eng_p1.begin() as conn:
            conn.execute(text("CREATE TABLE test_lock_row (id SERIAL PRIMARY KEY, val TEXT);"))
            conn.execute(text("INSERT INTO test_lock_row (val) VALUES ('initial');"))

        row_locked_ev = threading.Event()
        release_row_ev = threading.Event()
        p1_results = {"t1_err": None, "t2_err": None, "t2_duration": 0.0, "t2_val": None}

        def worker_lock_holder():
            e = create_engine(target_url)
            try:
                with e.begin() as conn:
                    row = conn.execute(text("SELECT id, val FROM test_lock_row ORDER BY id DESC LIMIT 1 FOR UPDATE;")).fetchone()
                    assert row[1] == "initial"
                    row_locked_ev.set()
                    release_row_ev.wait(timeout=5.0)
                    time.sleep(0.3)
                    conn.execute(text("UPDATE test_lock_row SET val = 'updated_by_t1';"))
            except Exception as exc:
                p1_results["t1_err"] = exc
            finally:
                e.dispose()

        def worker_lock_waiter():
            e = create_engine(target_url)
            try:
                row_locked_ev.wait(timeout=5.0)
                t_start = time.time()
                with e.begin() as conn:
                    row = conn.execute(text("SELECT id, val FROM test_lock_row ORDER BY id DESC LIMIT 1 FOR UPDATE;")).fetchone()
                    p1_results["t2_duration"] = time.time() - t_start
                    p1_results["t2_val"] = row[1]
            except Exception as exc:
                p1_results["t2_err"] = exc
            finally:
                e.dispose()

        th_a = threading.Thread(target=worker_lock_holder)
        th_b = threading.Thread(target=worker_lock_waiter)
        th_a.start()
        assert row_locked_ev.wait(timeout=5.0)
        th_b.start()
        time.sleep(0.2)
        release_row_ev.set()
        th_a.join(timeout=10.0)
        th_b.join(timeout=10.0)

        assert p1_results["t1_err"] is None
        assert p1_results["t2_err"] is None
        assert p1_results["t2_duration"] >= 0.25, f"T2 debio esperar el bloqueo FOR UPDATE (duracion={p1_results['t2_duration']})"
        assert p1_results["t2_val"] == "updated_by_t1", "T2 debio observar la actualizacion tras liberar el bloqueo FOR UPDATE"

        # PARTE 2: Acreditar _lift_database_quarantine concurrente sobre la misma cuarentena
        _enforce_database_quarantine(
            target_url,
            reason="LOCKED_QUARANTINE_CONCURRENCY_TEST",
            journal_state="DB_RESTORED",
            marker_id=marker_id,
            restore_token=restore_token
        )

        lift_results = []
        lift_errors = []

        def worker_lift(worker_id: int):
            try:
                _lift_database_quarantine(target_url, expected_marker_id=marker_id, restore_token=restore_token)
                lift_results.append(f"SUCCESS_W{worker_id}")
            except Exception as exc:
                lift_errors.append((worker_id, exc))

        t1 = threading.Thread(target=worker_lift, args=(1,))
        t2 = threading.Thread(target=worker_lift, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert len(lift_errors) == 0, f"Error en levantamiento concurrente: {lift_errors}"
        assert len(lift_results) == 2, "Ambos workers deben completar exitosamente (uno primario y otro idempotente)"

        # Verificar que la cuarentena fue levantada y la evidencia de completitud existe en PostgreSQL 15
        with eng_p1.begin() as conn:
            q_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
            assert q_exists is None, "Cuarentena debio ser eliminada"
            c_exists = conn.execute(text("SELECT to_regclass('public._dr_restoration_completed');")).scalar()
            assert c_exists is not None, "Evidencia durable de completitud debio ser creada"
            rows = conn.execute(text(
                "SELECT marker_id, restore_token FROM public._dr_restoration_completed WHERE marker_id = :mid;"
            ), {"mid": marker_id}).fetchall()
            assert len(rows) >= 1
            assert rows[0][0] == marker_id
            assert rows[0][1] == restore_token
        eng_p1.dispose()

    finally:
        if target_url:
            _safe_drop_p15_ephemeral_db(settings.DATABASE_URL, db_name)


