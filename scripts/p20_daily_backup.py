"""
ABAST GP V6 — P20 Automated Daily Backup Runner
Ejecuta el respaldo consistente, cifrado (AES-256-GCM) y firmado (HMAC-SHA256)
de PostgreSQL y documentos, distribuye a discos físicos independientes (C: y D:),
aplica retención estricta (7 diarios + 4 semanales) y valida integridad.
"""

import os
import sys
import json
import time
import shutil
import hashlib
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Set

# Importar despachador de alertas
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "monitoring"))
from p20_alert_dispatcher import AlertDispatcher

DIR_PRIMARY = Path(os.getenv("BACKUP_DIR_PRIMARY", r"D:\BACKUPS_PROYECTOS\ABAST_GP_P19_MIGRATION\backup\automated_daily"))
DIR_SECONDARY = Path(os.getenv("BACKUP_DIR_SECONDARY", r"C:\Users\PC\Documents\AbastLG\ABAST_GP_P19_SECONDARY_CUSTODY\backup\automated_daily"))
LOCK_FILE = DIR_PRIMARY / "backup.lock"

CONTAINER_API = os.getenv("PILOT_CONTAINER_API", "abst_lan_api")
WORKTREE_DIR = Path(__file__).resolve().parent.parent


def acquire_lock() -> bool:
    """Previene ejecuciones concurrentes o solapadas del respaldo."""
    DIR_PRIMARY.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            content = LOCK_FILE.read_text(encoding="utf-8").strip()
            pid, ts = content.split(":")
            # Comprobar si el proceso sigue vivo
            import psutil
            if psutil.pid_exists(int(pid)):
                print(f"[ERROR] Bloqueo activo: otro respaldo ya se encuentra en ejecución (PID {pid}).")
                return False
        except Exception:
            pass  # Lock huerfano

    try:
        LOCK_FILE.write_text(f"{os.getpid()}:{int(time.time())}", encoding="utf-8")
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo crear archivo de cerrojo {LOCK_FILE}: {e}")
        return False


def release_lock():
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def apply_retention_policy(target_dir: Path) -> Dict[str, Any]:
    """
    Aplica política de retención:
    - Conserva los últimos 7 respaldos diarios.
    - Conserva 4 respaldos semanales anteriores.
    - REGLA CRITICA: Nunca elimina la última copia disponible si hay <= 1 respaldo.
    - Nunca toca archivos fuera de automated_daily.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    backups = list(target_dir.glob("pilot_backup_auto_*.tar.enc"))
    if not backups:
        return {"kept": 0, "pruned": 0}

    # Parsear timestamps: pilot_backup_auto_YYYYMMDD_HHMMSS.tar.enc
    parsed_backups = []
    for b in backups:
        parts = b.name.replace(".tar.enc", "").split("_")
        if len(parts) >= 5:
            try:
                date_str = f"{parts[3]}_{parts[4]}"
                dt = datetime.strptime(date_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                parsed_backups.append((dt, b))
            except Exception:
                continue

    # Ordenar del más reciente al más antiguo
    parsed_backups.sort(key=lambda x: x[0], reverse=True)
    total_found = len(parsed_backups)

    if total_found <= 1:
        return {"kept_count": total_found, "pruned_count": 0, "note": "Solo existe 1 respaldo; preservado estrictamente."}

    now = datetime.now(timezone.utc)
    kept_files: Set[Path] = set()

    # 1. Conservar 7 diarios (el más reciente de cada día en los últimos 7 días)
    daily_buckets: Dict[str, Path] = {}
    for dt, b_path in parsed_backups:
        day_key = dt.strftime("%Y-%m-%d")
        if day_key not in daily_buckets:
            daily_buckets[day_key] = b_path

    # Seleccionar hasta 7 días más recientes
    for day_key in sorted(daily_buckets.keys(), reverse=True)[:7]:
        kept_files.add(daily_buckets[day_key])

    # 2. Conservar 4 semanales (1 por semana de las semanas anteriores, hasta 28 días)
    weekly_buckets: Dict[str, Path] = {}
    for dt, b_path in parsed_backups:
        # Semana del año: YYYY-WW
        week_key = dt.strftime("%Y-%W")
        if week_key not in weekly_buckets:
            weekly_buckets[week_key] = b_path

    for week_key in sorted(weekly_buckets.keys(), reverse=True)[:4]:
        kept_files.add(weekly_buckets[week_key])

    # Siempre garantizar que el respaldo más reciente esté protegido
    kept_files.add(parsed_backups[0][1])

    # Podar los no conservados
    pruned_count = 0
    for dt, b_path in parsed_backups:
        if b_path not in kept_files:
            manifest_path = Path(str(b_path) + ".manifest.json")
            try:
                b_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                pruned_count += 1
            except Exception as e:
                print(f"[WARN] Error podando respaldo antiguo {b_path.name}: {e}")

    return {
        "total_before": total_found,
        "kept_count": len(kept_files),
        "pruned_count": pruned_count,
        "kept_files": [f.name for f in kept_files]
    }


def execute_automated_backup() -> Dict[str, Any]:
    alerts = AlertDispatcher()
    t_start = time.time()
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"pilot_backup_auto_{now_ts}.tar.enc"
    manifest_filename = f"{backup_filename}.manifest.json"
    container_tmp_backup = f"/tmp/{backup_filename}"

    print(f"\n[{datetime.now(timezone.utc).isoformat()}] INICIANDO RESPALDO AUTOMATICO DIARIO...")
    print(f" -> Artefacto: {backup_filename}")

    # 1. Ejecutar respaldo dentro del contenedor con backup_lan_pg15.py
    cmd = [
        "docker", "compose", "--env-file", ".env.lan", "-f", "docker-compose.lan.yml",
        "-p", "abst_p17_pilot", "exec", "-T", "api", "python",
        "/app/verification/dr/backup_lan_pg15.py", "backup",
        "--output", container_tmp_backup
    ]
    try:
        proc = subprocess.run(cmd, cwd=str(WORKTREE_DIR), capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            err_msg = f"Fallo al generar respaldo en contenedor: {proc.stderr[:300]}"
            alerts.dispatch("backup", "CRITICAL", err_msg)
            raise RuntimeError(err_msg)

        # Parsear salida JSON del respaldo
        json_start = proc.stdout.find("{")
        if json_start == -1:
            raise ValueError(f"No se detecto bloque JSON en la salida del respaldo: {proc.stdout[:300]}")
        backup_metadata = json.loads(proc.stdout[json_start:])
        backup_sha = backup_metadata.get("backup_sha256")
        hmac_sig = backup_metadata.get("hmac_signature")

    except Exception as e:
        alerts.dispatch("backup", "CRITICAL", f"Error en ejecucion de respaldo: {e}")
        raise

    # 2. Copiar archivos fuera del contenedor a Primaria (D:) y Secundaria (C:)
    DIR_PRIMARY.mkdir(parents=True, exist_ok=True)
    DIR_SECONDARY.mkdir(parents=True, exist_ok=True)

    dest_d_backup = DIR_PRIMARY / backup_filename
    dest_d_manifest = DIR_PRIMARY / manifest_filename
    dest_c_backup = DIR_SECONDARY / backup_filename
    dest_c_manifest = DIR_SECONDARY / manifest_filename

    # docker cp hacia D:
    subprocess.run(["docker", "cp", f"{CONTAINER_API}:{container_tmp_backup}", str(dest_d_backup)], check=True)
    subprocess.run(["docker", "cp", f"{CONTAINER_API}:{container_tmp_backup}.manifest.json", str(dest_d_manifest)], check=True)

    # Copiar a C: (disco fisico independiente)
    shutil.copy2(dest_d_backup, dest_c_backup)
    shutil.copy2(dest_d_manifest, dest_c_manifest)

    # Limpiar /tmp del contenedor
    subprocess.run(["docker", "compose", "--env-file", ".env.lan", "-f", "docker-compose.lan.yml",
                    "-p", "abst_p17_pilot", "exec", "-T", "api", "rm", "-f",
                    container_tmp_backup, f"{container_tmp_backup}.manifest.json"],
                   cwd=str(WORKTREE_DIR), check=False)

    # 3. Verificacion automatica e independiente de SHA-256 en ambos discos
    sha_d = compute_file_sha256(dest_d_backup)
    sha_c = compute_file_sha256(dest_c_backup)

    if sha_d != backup_sha or sha_c != backup_sha:
        err_msg = f"Incoherencia criptografica SHA-256! Origen: {backup_sha}, D: {sha_d}, C: {sha_c}"
        alerts.dispatch("backup", "CRITICAL", err_msg)
        raise ValueError(err_msg)

    # 4. Validar firma HMAC en manifiesto
    manifest_data = json.loads(dest_d_manifest.read_text(encoding="utf-8"))
    assert manifest_data.get("hmac_signature") == hmac_sig, "HMAC signature mismatch in manifest!"

    duration = round(time.time() - t_start, 2)
    print(f" -> Respaldo completado y verificado en {duration}s:")
    print(f"    SHA-256: {backup_sha}")
    print(f"    HMAC:    {hmac_sig}")
    print(f"    Primaria:   {dest_d_backup} (D:)")
    print(f"    Secundaria: {dest_c_backup} (C:)")

    # 5. Aplicar política de retención en D: y C:
    ret_d = apply_retention_policy(DIR_PRIMARY)
    ret_c = apply_retention_policy(DIR_SECONDARY)
    print(f" -> Retención D: {ret_d.get('kept_count')} conservados, {ret_d.get('pruned_count')} podados.")
    print(f" -> Retención C: {ret_c.get('kept_count')} conservados, {ret_c.get('pruned_count')} podados.")

    # 6. Registrar estado de último respaldo exitoso
    success_record = {
        "status": "SUCCESS",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration,
        "backup_file": backup_filename,
        "backup_sha256": backup_sha,
        "hmac_signature": hmac_sig,
        "pg_dump_bytes": backup_metadata.get("pg_dump_bytes"),
        "document_count": backup_metadata.get("document_count"),
        "table_counts": backup_metadata.get("table_counts"),
        "primary_path": str(dest_d_backup),
        "secondary_path": str(dest_c_backup),
        "retention": {"kept_d": ret_d.get("kept_count"), "kept_c": ret_c.get("kept_count")}
    }

    # Guardar en D: y C:
    (DIR_PRIMARY.parent / "last_successful_backup.json").write_text(json.dumps(success_record, indent=2), encoding="utf-8")
    (DIR_SECONDARY.parent / "last_successful_backup.json").write_text(json.dumps(success_record, indent=2), encoding="utf-8")

    # Log histórico append-only
    history_file_d = DIR_PRIMARY.parent / "backup_history.jsonl"
    with open(history_file_d, "a", encoding="utf-8") as f:
        f.write(json.dumps(success_record) + "\n")

    history_file_c = DIR_SECONDARY.parent / "backup_history.jsonl"
    with open(history_file_c, "a", encoding="utf-8") as f:
        f.write(json.dumps(success_record) + "\n")

    # Notificar resolución de alerta si existía
    alerts.resolve("backup", f"Respaldo diario generado ({backup_filename}) y validado exitosamente en C: y D:.")

    return success_record


def main():
    if not acquire_lock():
        sys.exit(1)

    try:
        record = execute_automated_backup()
        print("\n=== RESPALDO AUTOMATICO DIARIO VERIFICADO AL 100% ===")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
