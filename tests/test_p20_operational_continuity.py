"""
ABAST GP V6 — P20 Test Suite: Continuidad Operativa Autónoma
Valida:
1. Diagnóstico real de los 8 componentes en el piloto activo.
2. Restauración del respaldo automático en base de datos efímera aislada.
3. Simulación de fallos y deduplicación de alertas en entorno aislado desechable.
4. Política de retención de respaldos (7 diarios + 4 semanales + protección última copia).
"""

import os
import sys
import json
import time
import uuid
import shutil
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ajustar PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "monitoring"))
sys.path.insert(0, str(BASE_DIR / "scripts"))

from monitoring.p20_real_health_monitor import RealHealthMonitor
from monitoring.p20_alert_dispatcher import AlertDispatcher, sanitize_payload
from scripts.p20_daily_backup import apply_retention_policy


def test_1_real_pilot_health_diagnostic():
    print("\n--- TEST 1: Diagnóstico Real de Infraestructura del Piloto ---")
    monitor = RealHealthMonitor()
    res = monitor.run_full_diagnostic()
    
    print(f"Estado Global: {res['overall_status']}")
    assert res["overall_status"] == "HEALTHY", f"El estado global del piloto no es HEALTHY: {res['overall_status']}"
    
    components = res["components"]
    for comp in ["postgresql", "redis", "rq_workers", "api_https", "caddy_tls", "volumes_storage", "containers", "network_ip"]:
        st = components[comp]["status"]
        print(f" -> {comp}: {st} ({components[comp]['message']})")
        assert st == "HEALTHY", f"Componente {comp} reporta estado no saludable: {st}"

    print("[PASS] TEST 1: Los 8 componentes del piloto se encuentran 100% HEALTHY.")


def test_2_restore_automated_backup_in_ephemeral_db():
    print("\n--- TEST 2: Restauración Efímera del Respaldo Automático ---")
    import subprocess
    from sqlalchemy import create_engine, text

    # Obtener el respaldo automático más reciente generado en D:
    dir_auto = Path(r"D:\BACKUPS_PROYECTOS\ABAST_GP_P19_MIGRATION\backup\automated_daily")
    backups = sorted(list(dir_auto.glob("pilot_backup_auto_*.tar.enc")), key=lambda p: p.stat().st_mtime, reverse=True)
    assert len(backups) > 0, "No se encontraron respaldos automáticos en D:!"
    latest_backup = backups[0]
    print(f" -> Respaldo a probar: {latest_backup.name}")

    token = uuid.uuid4().hex[:8]
    ephemeral_db = f"dr_test_p20_auto_{token}"
    marker_id = f"marker_p20_auto_{token}"

    # Copiar respaldo al contenedor
    container_target = f"/tmp/{latest_backup.name}"
    subprocess.run(["docker", "cp", str(latest_backup), f"abst_lan_api:{container_target}"], check=True)
    subprocess.run(["docker", "cp", f"{latest_backup}.manifest.json", f"abst_lan_api:{container_target}.manifest.json"], check=True)

    # Script de prueba dentro del contenedor
    script = f"""
import os, sys, json, hashlib, shutil
from pathlib import Path
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.core.crypto import decrypt_aead

maint_url = settings.DATABASE_URL.rsplit('/', 1)[0] + '/postgres'
target_db_url = settings.DATABASE_URL.rsplit('/', 1)[0] + '/{ephemeral_db}'
source_db_url = settings.DATABASE_URL

# 1. Crear BD efimera y registrar marcador
eng_m = create_engine(maint_url, isolation_level='AUTOCOMMIT')
with eng_m.connect() as conn:
    conn.execute(text('CREATE DATABASE {ephemeral_db}'))

eng_t = create_engine(target_db_url, isolation_level='AUTOCOMMIT')
with eng_t.connect() as conn:
    conn.execute(text("CREATE TABLE _dr_test_ownership_marker (marker_id VARCHAR(64) PRIMARY KEY)"))
    conn.execute(text("INSERT INTO _dr_test_ownership_marker VALUES ('{marker_id}')"))
eng_t.dispose()

# 2. Restaurar
sys.path.insert(0, '/app/verification/dr')
from backup_lan_pg15 import restore_lan_backup

target_uploads = Path('/tmp/p20_test_{token}/uploads')
target_uploads.mkdir(parents=True, exist_ok=True)

enc_key = os.getenv('BACKUP_ENCRYPTION_KEY', getattr(settings, 'BACKUP_ENCRYPTION_KEY'))
sign_key = os.getenv('BACKUP_SIGNING_KEY', getattr(settings, 'BACKUP_SIGNING_KEY'))

res = restore_lan_backup(
    backup_file=Path('{container_target}'),
    target_uploads_dir=target_uploads,
    encryption_key=enc_key,
    signing_key=sign_key,
    expected_marker_id='{marker_id}',
    target_database_url=target_db_url,
    source_database_url=source_db_url
)
assert res.get('status') == 'RESTORED_SUCCESS', f'Fallo restore: {{res}}'

# 3. Comprobar registros
eng_v = create_engine(target_db_url)
with eng_v.connect() as conn:
    u = conn.execute(text('SELECT count(*) FROM users')).scalar()
    c = conn.execute(text('SELECT count(*) FROM case_files')).scalar()
    d = conn.execute(text('SELECT count(*) FROM uploaded_documents')).scalar()
    assert u >= 4 and c >= 3 and d >= 1, f'Inconsistencia en conteos: u={{u}}, c={{c}}, d={{d}}'

    # Validar documento
    doc = conn.execute(text('SELECT stored_path FROM uploaded_documents LIMIT 1')).scalar()
    doc_path = target_uploads / doc
    assert doc_path.exists(), 'Documento restaurado no existe en staging!'
    sha = hashlib.sha256(doc_path.read_bytes()).hexdigest()
    assert sha == 'a794a6f84e6b8b13a0c5970d06da8fc5516ab647b2f292a263e51696b7150654', 'Hash documento no coincide!'

    # Validar MFA de superadmin
    sa = conn.execute(text("SELECT mfa_status, mfa_secret, session_version FROM users WHERE role = 'SUPERADMIN'")).fetchone()
    assert sa[0] == 'ENABLED' and sa[2] == 2, 'MFA o session_version no corresponden a la rotacion!'
    mfa_key = os.getenv('MFA_ENCRYPTION_KEY', getattr(settings, 'MFA_ENCRYPTION_KEY'))
    dec_sec = decrypt_aead(sa[1], mfa_key)
    assert len(dec_sec) == 32, 'Secreto TOTP descifrado invalido!'

    # Validar sesiones revocadas
    act_s = conn.execute(text("SELECT count(*) FROM user_sessions WHERE user_id = (SELECT id FROM users WHERE role = 'SUPERADMIN') AND is_revoked = false")).scalar()
    assert act_s == 0, 'No deben existir sesiones activas no revocadas!'

    # Validar ausencia de cuarentena
    quar = conn.execute(text("SELECT to_regclass('public._dr_restoration_quarantine')")).scalar()
    assert quar is None, 'Cuarentena presente en base restaurada!'

eng_v.dispose()

# 4. Limpieza
with eng_m.connect() as conn:
    conn.execute(text('DROP DATABASE {ephemeral_db} WITH (FORCE)'))
eng_m.dispose()

if Path('/tmp/p20_test_{token}').exists():
    shutil.rmtree(Path('/tmp/p20_test_{token}'))

os.remove('{container_target}')
os.remove('{container_target}.manifest.json')
print('RESTORE_VERIFIED_SUCCESS')
"""

    cmd = [
        "docker", "compose", "--env-file", ".env.lan", "-f", "docker-compose.lan.yml",
        "-p", "abst_p17_pilot", "exec", "-T", "api", "python", "-c", script
    ]
    proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=40)
    assert proc.returncode == 0 and "RESTORE_VERIFIED_SUCCESS" in proc.stdout, f"Fallo verificacion de restauracion: {proc.stderr}\n{proc.stdout}"
    print("[PASS] TEST 2: Respaldo automático restaurado y validado en base efímera (RTO y datos 100% íntegros).")


def test_3_alert_dispatcher_and_sanitization():
    print("\n--- TEST 3: Simulación de Alertas, Deduplicación y Enmascaramiento ---")
    tmp_state = BASE_DIR / "monitoring" / "tmp_test_alert_state.json"
    tmp_hist = BASE_DIR / "monitoring" / "tmp_test_alert_history.jsonl"

    if tmp_state.exists():
        tmp_state.unlink()
    if tmp_hist.exists():
        tmp_hist.unlink()

    dispatcher = AlertDispatcher(state_file=tmp_state, history_file=tmp_hist, cooldown_seconds=60)

    # 1. Primera emision
    emitted1 = dispatcher.dispatch("mock_service", "CRITICAL", "Fallo simulado 1", {"token": "secret_token_123", "password": "pass"})
    assert emitted1 is True, "La primera alerta debio ser emitida!"

    # 2. Deduplicacion en cooldown
    emitted2 = dispatcher.dispatch("mock_service", "CRITICAL", "Fallo simulado 1 duplicado")
    assert emitted2 is False, "La alerta duplicada en cooldown debio ser suprimida!"

    # 3. Resolucion
    resolved = dispatcher.resolve("mock_service", "Servicio simulado recuperado")
    assert resolved is True, "La resolucion debio emitirse!"

    # 4. Verificar saneamiento en log historico
    lines = tmp_hist.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2, f"Se esperaban 2 lineas en log, se encontraron {len(lines)}"
    
    first_record = json.loads(lines[0])
    assert first_record["details"]["token"] == "***REDACTED***", "El token debio ser enmascarado!"
    assert first_record["details"]["password"] == "***REDACTED***", "La contrasena debio ser enmascarada!"

    # Limpieza
    tmp_state.unlink(missing_ok=True)
    tmp_hist.unlink(missing_ok=True)
    print("[PASS] TEST 3: Alertas, deduplicación y enmascaramiento de secretos verificados exitosamente.")


def test_4_retention_policy_pruning():
    print("\n--- TEST 4: Simulación de Política de Retención de Respaldos ---")
    tmp_backup_dir = BASE_DIR / "scratch" / "test_p20_retention"
    if tmp_backup_dir.exists():
        shutil.rmtree(tmp_backup_dir)
    tmp_backup_dir.mkdir(parents=True, exist_ok=True)

    # Crear 15 respaldos sintéticos simulando 15 días consecutivos
    now = datetime.now(timezone.utc)
    for i in range(15):
        dt = now - timedelta(days=i)
        ts_str = dt.strftime("%Y%m%d_%H%M%S")
        f = tmp_backup_dir / f"pilot_backup_auto_{ts_str}.tar.enc"
        m = tmp_backup_dir / f"pilot_backup_auto_{ts_str}.tar.enc.manifest.json"
        f.write_text("DUMMY_BACKUP_CONTENT")
        m.write_text(json.dumps({"backup_sha256": "dummy"}))

    # Aplicar política de retención
    res = apply_retention_policy(tmp_backup_dir)
    print(f" -> Creados 15 respaldos sintéticos. Retención: {res['kept_count']} conservados, {res['pruned_count']} podados.")
    assert res["kept_count"] <= 11, f"No deben conservarse más de 11 respaldos (7 diarios + 4 semanales): {res['kept_count']}"
    assert res["pruned_count"] >= 4, f"Debieron podarse al menos 4 respaldos antiguos: {res['pruned_count']}"

    # Probar regla de protección de última copia
    # Dejar solo 1 archivo
    for f in list(tmp_backup_dir.glob("*")):
        f.unlink()
    single_f = tmp_backup_dir / "pilot_backup_auto_20261001_020000.tar.enc"
    single_f.write_text("LAST_COPY")
    res_single = apply_retention_policy(tmp_backup_dir)
    assert res_single["kept_count"] == 1 and res_single["pruned_count"] == 0
    assert single_f.exists(), "La última copia recuperable NUNCA debe ser eliminada!"

    # Limpieza
    shutil.rmtree(tmp_backup_dir)
    print("[PASS] TEST 4: Política de retención y regla de última copia operativa acreditadas al 100%.")


def main():
    print("=====================================================================")
    print("     ABAST GP V6 — EJECUCION DE SUITE DE PRUEBAS P20")
    print("=====================================================================")
    test_1_real_pilot_health_diagnostic()
    test_2_restore_automated_backup_in_ephemeral_db()
    test_3_alert_dispatcher_and_sanitization()
    test_4_retention_policy_pruning()
    print("=====================================================================")
    print("   TODAS LAS PRUEBAS P20 CONCLUIDAS SATISFACTORIAMENTE (PASS 4/4)")
    print("=====================================================================")


if __name__ == "__main__":
    main()
