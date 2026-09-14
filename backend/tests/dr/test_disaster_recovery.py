"""
Suite de Pruebas Automatizadas de Disaster Recovery, PITR & RPO/RTO (Fase 7.4)
Cubre los Escenarios A a G, telemetría DR, alertamiento SRE y medición cuantitativa de objetivos de recuperación.
"""

import os
import time
import json
import shutil
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.domain import (
    Tenant, User, CaseFile, UploadedDocument, ProcessingJob,
    ProcessingMetrics, WorkerHeartbeat, AuditLog
)
from app.core.config import settings
from app.core.telemetry import (
    metrics_registry,
    record_dr_backup,
    record_dr_restore,
    record_dr_reconciliation,
)
from app.schemas.alerts import AlertType, AlertSeverity, AlertStatus
from app.services.alert_engine import AlertEngine, global_alert_engine
from app.services.job_recovery_engine import JobRecoveryEngine
from app.services.job_repository import JobRepository


# Fixture de sesión de base de datos
@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="function")
def dr_env(tmp_path):
    """Crea un entorno de almacenamiento temporal para vault y uploads de prueba."""
    uploads_dir = tmp_path / "uploads"
    vault_dir = tmp_path / "vault"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    vault_dir.mkdir(parents=True, exist_ok=True)
    
    return {
        "uploads_dir": str(uploads_dir),
        "vault_dir": str(vault_dir),
        "tmp_path": tmp_path
    }


# ===========================================================================
# ESCENARIO A: PÉRDIDA TOTAL DE POSTGRESQL Y RESTAURACIÓN INTEGRAL
# ===========================================================================
def test_scenario_a_full_postgresql_recovery(db_session, dr_env):
    """
    Escenario A: Pérdida total de la instancia de prueba y reconstrucción
    desde Base Backup físico + Documentos + Replay de integridad.
    """
    from verification.dr.create_backup import create_backup_package
    from verification.dr.restore_backup import restore_backup_package
    from verification.dr.validate_database import validate_database_integrity

    # 1. Crear datos iniciales en la base de datos
    tenant_id = f"dr-tenant-a-{int(time.time())}"
    tenant = Tenant(id=tenant_id, name="DR Tenant Alpha")
    db_session.add(tenant)
    db_session.commit()

    case = CaseFile(
        title="Expediente DR Escenario A",
        contract_type="Bienes",
        tenant_id=tenant_id,
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()

    # Crear documento físico y registro
    doc_content = b"%PDF-1.4 Mock PDF Content for DR Scenario A"
    doc_path = Path(dr_env["uploads_dir"]) / f"doc_scenario_a_{tenant_id}.pdf"
    with open(doc_path, "wb") as f:
        f.write(doc_content)

    doc = UploadedDocument(
        case_id=case.id,
        document_type="requirement",
        original_filename="TDR_Escenario_A.pdf",
        stored_path=doc_path.name,
        mime_type="application/pdf"
    )
    db_session.add(doc)
    db_session.commit()
    case_id = case.id
    doc_id = doc.id

    # 2. Generar Backup Completo
    backup_res = create_backup_package(
        database_url=settings.DATABASE_URL,
        uploads_dir=dr_env["uploads_dir"],
        backup_vault_dir=dr_env["vault_dir"],
        backup_id=f"backup-scenario-a-{int(time.time())}"
    )
    assert backup_res["status"] == "PASS"
    assert Path(backup_res["manifest_path"]).exists()
    assert Path(backup_res["checksums_path"]).exists()

    # Aislamiento de sesión antes de restore (7.4-A.1)
    db_session.flush()
    db_session.commit()
    db_session.close()
    if db_session.bind:
        db_session.bind.dispose()

    # 3. Simular Restauración en entorno destino
    target_uploads = dr_env["tmp_path"] / "restored_uploads_a"
    restore_res = restore_backup_package(
        backup_path_or_id=backup_res["backup_id"],
        target_database_url=settings.DATABASE_URL,
        target_uploads_dir=str(target_uploads),
        backup_vault_dir=dr_env["vault_dir"]
    )
    assert restore_res["status"] == "PASS"

    # Reconectar para validación y limpieza
    engine_a = create_engine(settings.DATABASE_URL)
    SessionA = sessionmaker(bind=engine_a)
    session_a = SessionA()

    # 4. Validar integridad de base de datos restaurada
    val_db = validate_database_integrity(settings.DATABASE_URL)
    assert val_db["status"] == "PASS"
    assert val_db["tables_inventory"]["tenants"] >= 1
    assert val_db["tables_inventory"]["case_files"] >= 1
    assert val_db["tables_inventory"]["uploaded_documents"] >= 1

    # 5. Validar que el archivo físico fue restaurado
    restored_doc_file = target_uploads / doc_path.name
    assert restored_doc_file.exists()
    assert restored_doc_file.read_bytes() == doc_content

    # 6. Limpieza de datos de prueba
    session_a.execute(text(f"DELETE FROM uploaded_documents WHERE id = {doc_id}"))
    session_a.execute(text(f"DELETE FROM case_files WHERE id = {case_id}"))
    session_a.execute(text(f"DELETE FROM tenants WHERE id = '{tenant_id}'"))
    session_a.commit()
    session_a.close()
    engine_a.dispose()


# ===========================================================================
# ESCENARIO B: ELIMINACIÓN LÓGICA ACCIDENTAL (PITR)
# ===========================================================================
def test_scenario_b_logical_deletion_pitr(db_session, dr_env):
    """
    Escenario B: Creación de datos en T1, backup en T2, eliminación accidental en T3,
    y restauración PITR al punto previo a la eliminación.
    """
    from verification.dr.create_backup import create_backup_package
    from verification.dr.restore_backup import restore_backup_package

    # T1: Crear datos válidos
    tenant_id = f"dr-pitr-{int(time.time())}"
    t_obj = Tenant(id=tenant_id, name="PITR Tenant")
    db_session.add(t_obj)
    db_session.commit()

    case_obj = CaseFile(
        title="Expediente PITR Crítico",
        contract_type="Servicios",
        tenant_id=tenant_id,
        status="CREATED"
    )
    db_session.add(case_obj)
    db_session.commit()
    case_id_saved = case_obj.id

    # T2: Backup de estado seguro
    b_id = f"backup-pitr-t2-{int(time.time())}"
    backup_res = create_backup_package(
        database_url=settings.DATABASE_URL,
        uploads_dir=dr_env["uploads_dir"],
        backup_vault_dir=dr_env["vault_dir"],
        backup_id=b_id
    )
    assert backup_res["status"] == "PASS"

    # T3: Inyección de Desastre (Eliminación accidental de expediente)
    db_session.execute(text(f"DELETE FROM case_files WHERE id = {case_id_saved}"))
    db_session.commit()

    # Verificar que el expediente fue eliminado accidentalmente
    deleted_check = db_session.query(CaseFile).filter_by(id=case_id_saved).first()
    assert deleted_check is None

    # T3.5: AISLAMIENTO ESTRICTO DE SESIÓN ANTES DE RESTORE (7.4-A.1)
    db_session.flush()
    db_session.commit()
    db_session.close()
    if db_session.bind:
        db_session.bind.dispose()

    # T4: Restauración PITR al snapshot T2
    restore_res = restore_backup_package(
        backup_path_or_id=b_id,
        target_database_url=settings.DATABASE_URL,
        target_uploads_dir=dr_env["uploads_dir"],
        backup_vault_dir=dr_env["vault_dir"]
    )
    assert restore_res["status"] == "PASS"

    # T4.5: RECONEXIÓN LIMPIA PARA VALIDACIÓN
    engine_b = create_engine(settings.DATABASE_URL)
    SessionB = sessionmaker(bind=engine_b)
    session_b = SessionB()

    # T5: Validar que el expediente eliminado fue restaurado intacto
    restored_case = session_b.query(CaseFile).filter_by(id=case_id_saved).first()
    assert restored_case is not None
    assert restored_case.title == "Expediente PITR Crítico"
    assert restored_case.tenant_id == tenant_id

    # T6: Limpieza
    session_b.execute(text(f"DELETE FROM case_files WHERE id = {case_id_saved}"))
    session_b.execute(text(f"DELETE FROM tenants WHERE id = '{tenant_id}'"))
    session_b.commit()
    session_b.close()
    engine_b.dispose()


# ===========================================================================
# ESCENARIO C: BACKUP CORRUPTO Y FALLBACK SEGURO
# ===========================================================================
def test_scenario_c_corrupted_backup_rejection(db_session, dr_env):
    """
    Escenario C: Corrupción intencional de firma o checksums en un backup.
    El motor de restauración debe rechazarlo inmediatamente y emitir alerta.
    """
    from verification.dr.create_backup import create_backup_package
    from verification.dr.restore_backup import restore_backup_package

    # Crear backup válido
    b_id = f"backup-to-corrupt-{int(time.time())}"
    backup_res = create_backup_package(
        database_url=settings.DATABASE_URL,
        uploads_dir=dr_env["uploads_dir"],
        backup_vault_dir=dr_env["vault_dir"],
        backup_id=b_id
    )
    # Corromper intencionalmente un archivo del backup (físico o manifiesto)
    manifest = backup_res["manifest"]
    if "physical_basebackup" in manifest:
        db_file = Path(backup_res["vault_path"]) / "physical_basebackup" / "backup_manifest"
    elif "base_backup" in manifest:
        db_file = Path(backup_res["vault_path"]) / manifest["base_backup"]["filename"]
    else:
        db_file = Path(backup_res["vault_path"]) / manifest["documents_snapshot"]["filename"]

    with open(db_file, "ab") as f:
        f.write(b"CORRUPTED_BYTES_INJECTED")

    # Intentar restaurar el backup corrupto -> debe fallar con CHECKSUM_MISMATCH / VALIDATION_ERROR
    with pytest.raises(Exception) as exc_info:
        restore_backup_package(
            backup_path_or_id=b_id,
            target_database_url=settings.DATABASE_URL,
            target_uploads_dir=dr_env["uploads_dir"],
            backup_vault_dir=dr_env["vault_dir"]
        )

    assert "CHECKSUM_MISMATCH" in str(exc_info.value) or "VALIDATION_ERROR" in str(exc_info.value)


# ===========================================================================
# ESCENARIO D: PÉRDIDA TOTAL DE REDIS Y RECONSTRUCCIÓN SIN DUPLICADOS
# ===========================================================================
def test_scenario_d_lost_redis_rebuild(db_session, dr_env):
    """
    Escenario D: Pérdida total de Redis. Reconstrucción limpia desde PostgreSQL SSOT
    y reconciliación sin re-ejecución duplicada.
    """
    from verification.dr.rebuild_redis import rebuild_redis_instance
    from verification.dr.reconcile_jobs import reconcile_platform_jobs

    tenant_id = f"dr-redis-{int(time.time())}"
    tenant = Tenant(id=tenant_id, name="Redis Rebuild Tenant")
    db_session.add(tenant)
    db_session.commit()

    case = CaseFile(
        title="Expediente Redis Rebuild",
        contract_type="Bienes",
        tenant_id=tenant_id,
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()

    # Crear un job en estado COMPLETED (READY)
    job_completed = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id=tenant_id,
        user_id=None,
        job_type="OCR_PROCESSING",
        idempotency_key=f"idemp-comp-{int(time.time())}"
    )
    JobRepository.mark_completed(db=db_session, job_id=job_completed.job_id, tenant_id=tenant_id)

    # Crear un job en estado FAILED final
    job_failed = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id=tenant_id,
        user_id=None,
        job_type="DOCUMENT_PARSING",
        idempotency_key=f"idemp-fail-{int(time.time())}"
    )
    JobRepository.mark_failed(
        db=db_session,
        job_id=job_failed.job_id,
        error_message="Error fatal irrecuperable",
        error_category="CORRUPT_INPUT",
        failure_classification="FINAL",
        tenant_id=tenant_id
    )

    # 1. Reconstruir Redis limpio
    redis_res = rebuild_redis_instance(settings.REDIS_URL)
    assert redis_res["status"] == "PASS"
    assert redis_res["final_keys_count"] == 0

    # 2. Reconciliar
    rec_res = reconcile_platform_jobs(settings.DATABASE_URL)
    assert rec_res["status"] == "PASS"

    # 3. Validar que jobs en READY y FAILED_FINAL no fueron modificados ni reintentados
    db_session.refresh(job_completed)
    db_session.refresh(job_failed)
    assert job_completed.status == "READY"
    assert job_failed.status == "FAILED"

    # 4. Limpieza
    db_session.execute(text(f"DELETE FROM processing_jobs WHERE case_id = {case.id}"))
    db_session.execute(text(f"DELETE FROM case_files WHERE id = {case.id}"))
    db_session.execute(text(f"DELETE FROM tenants WHERE id = '{tenant_id}'"))
    db_session.commit()


# ===========================================================================
# ESCENARIO E: WORKER MUERTO DURANTE PROCESSING Y RETRY CON BACKOFF
# ===========================================================================
def test_scenario_e_dead_worker_reconciliation(db_session):
    """
    Escenario E: Worker muere durante PROCESSING (heartbeat estancado).
    JobRecoveryEngine lo reconcilia a QUEUED para reintento seguro con backoff idempotente.
    """
    from verification.dr.reconcile_jobs import reconcile_platform_jobs

    tenant_id = f"dr-dead-worker-{int(time.time())}"
    tenant = Tenant(id=tenant_id, name="Dead Worker Tenant")
    db_session.add(tenant)
    db_session.commit()

    case = CaseFile(
        title="Expediente Dead Worker",
        contract_type="Servicios",
        tenant_id=tenant_id,
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()

    # Crear job en PROCESSING
    job = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id=tenant_id,
        user_id=None,
        job_type="OCR_PROCESSING",
        idempotency_key=f"idemp-dead-{int(time.time())}"
    )
    JobRepository.update_progress(
        db=db_session,
        job_id=job.job_id,
        progress=10,
        status="PROCESSING",
        worker_name="dead_worker_node_1",
        tenant_id=tenant_id
    )
    assert job.status == "PROCESSING"

    # Registrar latido viejo (muerto hace 10 minutos)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    job.last_heartbeat_at = stale_time
    job.started_at = stale_time
    job.created_at = stale_time
    db_session.commit()

    # Reconciliar jobs post-restore
    rec_res = reconcile_platform_jobs(settings.DATABASE_URL)
    assert rec_res["status"] == "PASS"

    # Validar que el job fue recuperado y devuelto a QUEUED con intento incrementado
    db_session.refresh(job)
    assert job.status == "QUEUED"
    assert job.attempt_count == 2
    assert job.failure_classification == "RETRYABLE"

    # Limpieza
    db_session.execute(
        text("DELETE FROM audit_logs WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id},
    )
    db_session.execute(text(f"DELETE FROM processing_jobs WHERE case_id = {case.id}"))
    db_session.execute(text(f"DELETE FROM case_files WHERE id = {case.id}"))
    db_session.execute(
        text("DELETE FROM tenants WHERE id = :tenant_id"),
        {"tenant_id": tenant_id},
    )
    db_session.commit()


# ===========================================================================
# ESCENARIO F: DOCUMENTO FALTANTE Y DETECCIÓN ESTRICTA
# ===========================================================================
def test_scenario_f_missing_document_detection(db_session, dr_env):
    """
    Escenario F: Documento registrado en PostgreSQL pero inexistente en UPLOADS_DIR.
    El validador debe detectar la inconsistencia y marcar status = FAIL.
    """
    from verification.dr.validate_documents import validate_document_consistency

    tenant_id = f"dr-missing-doc-{int(time.time())}"
    tenant = Tenant(id=tenant_id, name="Missing Doc Tenant")
    db_session.add(tenant)
    db_session.commit()

    case = CaseFile(
        title="Expediente Missing Doc",
        contract_type="Servicios",
        tenant_id=tenant_id,
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()

    # Registrar documento en DB sin crearlo físicamente
    missing_doc = UploadedDocument(
        case_id=case.id,
        document_type="proposal",
        original_filename="Missing_Cotizacion.pdf",
        stored_path=f"ghost_file_{tenant_id}.pdf",
        mime_type="application/pdf"
    )
    db_session.add(missing_doc)
    db_session.commit()

    # Validar consistencia documental -> debe detectar missing file
    val_docs = validate_document_consistency(
        database_url=settings.DATABASE_URL,
        uploads_dir=dr_env["uploads_dir"]
    )
    assert val_docs["status"] == "FAIL"
    assert len(val_docs["missing_files_in_fs"]) >= 1
    assert any(m["document_id"] == str(missing_doc.id) for m in val_docs["missing_files_in_fs"])

    # Limpieza
    db_session.execute(text(f"DELETE FROM uploaded_documents WHERE id = {missing_doc.id}"))
    db_session.execute(text(f"DELETE FROM case_files WHERE id = {case.id}"))
    db_session.execute(text(f"DELETE FROM tenants WHERE id = '{tenant_id}'"))
    db_session.commit()


# ===========================================================================
# ESCENARIO G: CONTRATOS Y TIPOS ESTRICTOS EN MONITORING & SRE DASHBOARD
# ===========================================================================
def test_scenario_g_monitoring_and_sre_contracts(db_session):
    """
    Escenario G: Valida que los endpoints del SRE Dashboard retornan contratos
    estrictos sin valores nulos ni tipos inconsistentes.
    """
    tenant_id = f"dr-metrics-{int(time.time())}"
    tenant = Tenant(id=tenant_id, name="Metrics Contract Tenant")
    db_session.add(tenant)
    db_session.commit()

    case = CaseFile(
        title="Expediente Metrics Contract",
        contract_type="Bienes",
        tenant_id=tenant_id,
        status="CREATED"
    )
    db_session.add(case)
    db_session.commit()

    # Insertar métricas sintéticas
    job = JobRepository.create_job(
        db=db_session,
        case_id=case.id,
        tenant_id=tenant_id,
        user_id=None,
        job_type="OCR_PROCESSING",
        idempotency_key=f"idemp-met-{int(time.time())}"
    )
    JobRepository.update_progress(
        db=db_session,
        job_id=job.job_id,
        progress=20,
        status="PROCESSING",
        worker_name="worker_test_1",
        tenant_id=tenant_id
    )
    JobRepository.mark_completed(
        db=db_session,
        job_id=job.job_id,
        tenant_id=tenant_id,
        worker_name="worker_test_1",
        pages_processed=15
    )

    # Validar que processing_metrics tiene tipos estrictos
    metric = db_session.query(ProcessingMetrics).filter_by(job_id=job.job_id).first()
    assert metric is not None
    assert isinstance(metric.queue_time_ms, int)
    assert isinstance(metric.processing_time_ms, int)
    assert isinstance(metric.total_time_ms, int)
    assert metric.success is True
    assert metric.pages_processed == 15

    # Limpieza
    db_session.execute(text(f"DELETE FROM processing_metrics WHERE job_id = '{job.job_id}'"))
    db_session.execute(text(f"DELETE FROM processing_jobs WHERE case_id = {case.id}"))
    db_session.execute(text(f"DELETE FROM case_files WHERE id = {case.id}"))
    db_session.execute(text(f"DELETE FROM tenants WHERE id = '{tenant_id}'"))
    db_session.commit()


# ===========================================================================
# TELEMETRÍA Y ALERTAS DR
# ===========================================================================
def test_dr_telemetry_and_alerting(db_session):
    """
    Valida la correcta emisión de telemetría Prometheus de DR y el despacho
    de alertas DR con deduplicación y registro inmutable en AuditLog.
    """
    # 1. Telemetría Prometheus
    record_dr_backup("success")
    record_dr_restore("success", duration_seconds=12.5)
    record_dr_reconciliation("success")

    sample_backup = metrics_registry.dr_backup_total.get_sample(result="success")
    assert sample_backup >= 1.0

    sample_restore = metrics_registry.dr_restore_total.get_sample(result="success")
    assert sample_restore >= 1.0

    # 2. AlertEngine DR
    alert_engine = AlertEngine()
    tenant_id = f"dr-alert-tenant-{int(time.time())}"

    tenant = Tenant(id=tenant_id, name="DR Alert Tenant")
    db_session.add(tenant)
    db_session.commit()

    alert_event = alert_engine.emit_dr_alert(
        db=db_session,
        alert_type=AlertType.DR_RPO_BREACH,
        severity=AlertSeverity.CRITICAL,
        message="RPO efectivo superó umbral de 5 minutos durante simulacro DR.",
        metric_value=320.0,
    threshold=300.0,
    tenant_id=tenant_id,
    metadata={"scenario": "DRILL_SIMULATION", "secret_token": "should_be_redacted"}
)

    assert alert_event.status == AlertStatus.FIRING
    assert alert_event.alert_type == AlertType.DR_RPO_BREACH
    assert alert_event.metadata.get("secret_token") == "[REDACTED]"

    # Verificar que se registró en AuditLog
    audit_entry = db_session.query(AuditLog).filter_by(
        action="SRE_ALERT_FIRING",
        entity_type="SRE_INCIDENT"
    ).order_by(AuditLog.id.desc()).first()

    assert audit_entry is not None
    assert "DR_RPO_BREACH" in audit_entry.details

    db_session.execute(
        text("DELETE FROM audit_logs WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id},
    )
    db_session.execute(
        text("DELETE FROM tenants WHERE id = :tenant_id"),
        {"tenant_id": tenant_id},
    )
    db_session.commit()

# ===========================================================================
# MEDICIÓN CUANTITATIVA DE RPO Y RTO
# ===========================================================================
def test_dr_rpo_rto_quantitative_measurement():
    """
    Valida el cálculo determinista de RPO y RTO contra los límites de certificación:
    RPO <= 300s (5m), RTO <= 900s (15m).
    """
    from verification.dr.measure_rpo_rto import compute_dr_metrics

    now = datetime.now(timezone.utc)
    t_incident = now
    t_pg_tx = now - timedelta(seconds=120)       # 2 minutos atrás (RPO PG = 120s)
    t_doc = now - timedelta(seconds=180)         # 3 minutos atrás (RPO Doc = 180s)
    t_restore_start = now + timedelta(seconds=10)
    t_e2e_pass = now + timedelta(seconds=240)    # 4 minutos totales (RTO = 240s)

    metrics = compute_dr_metrics(
        incident_declared_time_utc=t_incident.isoformat(),
        latest_recovered_transaction_time_utc=t_pg_tx.isoformat(),
        latest_recovered_document_time_utc=t_doc.isoformat(),
        restore_start_time_utc=t_restore_start.isoformat(),
        e2e_validation_pass_time_utc=t_e2e_pass.isoformat(),
        breakdown_timings={
            "manifest_verification_seconds": 2.5,
            "postgres_restore_seconds": 35.0,
            "wal_replay_seconds": 15.0,
            "document_restore_seconds": 20.0,
            "redis_rebuild_seconds": 1.5,
            "job_reconciliation_seconds": 3.0,
            "worker_startup_seconds": 8.0,
            "e2e_validation_seconds": 145.0
        }
    )

    assert metrics["status"] == "PASS"
    assert metrics["rpo_metrics"]["rpo_effective_seconds"] == 180.0
    assert metrics["rpo_metrics"]["rpo_status"] == "PASS"
    assert metrics["rto_metrics"]["rto_total_seconds"] == 240.0
    assert metrics["rto_metrics"]["rto_status"] == "PASS"


# ===========================================================================
# SUITE DE CERTIFICACIÓN 7.4-A: PHYSICAL BASE BACKUP & PG_VERIFYBACKUP
# ===========================================================================
def test_7_4_a_physical_backup_uses_pg_basebackup(dr_env, monkeypatch):
    """
    Verifica que el physical backup ejecute pg_basebackup y valide con pg_verifybackup.
    """
    from verification.dr.create_backup import create_backup_package
    from unittest.mock import MagicMock

    res = create_backup_package(
        database_url=settings.DATABASE_URL,
        uploads_dir=dr_env["uploads_dir"],
        backup_vault_dir=dr_env["vault_dir"],
        backup_id="test-7-4-a-physical-success",
        secret_signing_key="dr_test_signing_key_secret_12345678"
    )

    assert res["status"] == "PASS"
    manifest = res["manifest"]

    # 1. Validar método physical basebackup
    physical_info = manifest.get("physical_basebackup")
    assert physical_info is not None
    assert physical_info["method"] == "pg_basebackup"
    assert physical_info["format"] == "plain_physical_directory"
    assert physical_info["wal_method"] == "stream"
    assert physical_info["verified_by"] == "pg_verifybackup"
    assert physical_info["verification_status"] == "PASSED"
    assert len(physical_info["manifest_checksum_sha256"]) == 64

    # 2. Validar que los archivos físicos existan en el vault
    vault_path = Path(res["vault_path"])
    assert vault_path.exists()
    assert (vault_path / "physical_basebackup" / "backup_manifest").exists()
    assert (vault_path / "pg-verifybackup.txt").exists()


def test_7_4_a_pg_dump_cannot_be_physical_fallback(dr_env, monkeypatch):
    """
    Verifica que ante fallo de pg_basebackup, el physical backup falle
    y ESTÉ ESTRICTAMENTE PROHIBIDO el fallback a pg_dump.
    """
    from verification.dr import create_backup
    from unittest.mock import patch

    # Simular fallo en pg_basebackup
    with patch("verification.dr.create_backup.execute_pg_basebackup") as mock_basebackup:
        mock_basebackup.side_effect = RuntimeError("PHYSICAL_BASEBACKUP_FAILED: Simulación de fallo en pg_basebackup")
        
        with pytest.raises(RuntimeError) as excinfo:
            create_backup.create_backup_package(
                database_url=settings.DATABASE_URL,
                uploads_dir=dr_env["uploads_dir"],
                backup_vault_dir=dr_env["vault_dir"],
                backup_id="test-7-4-a-fallback-forbidden"
            )

        assert "PHYSICAL_BASEBACKUP_FAILED" in str(excinfo.value)
        # Verificar que no se publicó en vault
        assert not (Path(dr_env["vault_dir"]) / "test-7-4-a-fallback-forbidden").exists()


def test_7_4_a_failure_of_pg_verifybackup_produces_rejection(dr_env, monkeypatch):
    """
    Verifica que si pg_verifybackup detecta corrupción o falla, el backup sea rechazado.
    """
    from verification.dr import create_backup
    from unittest.mock import patch

    with patch("verification.dr.create_backup.execute_pg_verifybackup") as mock_verify:
        mock_verify.side_effect = RuntimeError("PHYSICAL_VERIFYBACKUP_REJECTED: pg_verifybackup detecto checksum invalido")

        with pytest.raises(RuntimeError) as excinfo:
            create_backup.create_backup_package(
                database_url=settings.DATABASE_URL,
                uploads_dir=dr_env["uploads_dir"],
                backup_vault_dir=dr_env["vault_dir"],
                backup_id="test-7-4-a-verify-fail"
            )

        assert "PHYSICAL_VERIFYBACKUP_REJECTED" in str(excinfo.value)
        assert not (Path(dr_env["vault_dir"]) / "test-7-4-a-verify-fail").exists()


def test_7_4_a_postgres_major_different_than_16_fails(dr_env, monkeypatch):
    """
    Verifica que si el servidor PostgreSQL no es versión 16, falle inmediatamente.
    """
    from verification.dr import create_backup
    from unittest.mock import patch

    with patch("verification.dr.create_backup.verify_postgresql_16_server") as mock_version:
        mock_version.side_effect = ValueError("POSTGRESQL_VERSION_MISMATCH: Se requiere PostgreSQL 16")

        with pytest.raises(ValueError) as excinfo:
            create_backup.create_backup_package(
                database_url=settings.DATABASE_URL,
                uploads_dir=dr_env["uploads_dir"],
                backup_vault_dir=dr_env["vault_dir"],
                backup_id="test-7-4-a-pg-version-fail"
            )

        assert "POSTGRESQL_VERSION_MISMATCH" in str(excinfo.value)


def test_7_4_a_hmac_manifest_contains_key_id_without_secrets(dr_env):
    """
    Verifica que el manifiesto criptográfico HMAC contenga key_id y firma,
    pero NUNCA filtre contraseñas, URLs completas ni la clave secreta HMAC.
    """
    from verification.dr.create_backup import create_backup_package

    secret_key = "super_secret_hmac_key_999888777"
    res = create_backup_package(
        database_url=settings.DATABASE_URL,
        uploads_dir=dr_env["uploads_dir"],
        backup_vault_dir=dr_env["vault_dir"],
        backup_id="test-7-4-a-manifest-secrets-check",
        secret_signing_key=secret_key
    )

    manifest = res["manifest"]
    manifest_str = json.dumps(manifest)

    # 1. Validar presencia de key_id y firma
    assert manifest["security"]["key_id"] == "abst_gp_dr_key_v1"
    assert "signature" in manifest["security"]
    assert len(manifest["security"]["signature"]) == 64
    assert manifest["security"]["contains_secrets"] is False

    # 2. Validar que la clave secreta NUNCA aparezca en el manifiesto
    assert secret_key not in manifest_str
    assert "dr_password" not in manifest_str
    assert "PGPASSWORD" not in manifest_str


def test_7_4_a_logical_dump_marked_as_complementary(dr_env):
    """
    Verifica que el dump lógico generado esté explícitamente diferenciado
    como 'complementary_logical_dump' y no como reemplazo de basebackup.
    """
    from verification.dr.create_backup import create_backup_package

    res = create_backup_package(
        database_url=settings.DATABASE_URL,
        uploads_dir=dr_env["uploads_dir"],
        backup_vault_dir=dr_env["vault_dir"],
        backup_id="test-7-4-a-logical-complement",
        generate_logical_complement=True
    )

    manifest = res["manifest"]
    logical_backup = manifest.get("logical_backup")
    if logical_backup:
        assert logical_backup["type"] == "complementary_logical_dump"
        assert logical_backup["is_physical_fallback"] is False

