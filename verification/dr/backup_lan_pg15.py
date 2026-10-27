"""
Generador y Restaurador de Respaldo LAN Compatible con PostgreSQL 15
(P14-R1-10, P14-R1-11, R3-02..R3-05, R3-13, R4-01, R4-02, R4-06, R4-07, R5-01..R5-04, R5-08).

Implementa:
1. Respaldo logico completo PostgreSQL 15 autentico (pg_dump DDL + datos + secuencias + llaves foraneas).
2. Catalogo SHA-256 exhaustivo y conciliado con UploadedDocument y GeneratedOutput.pdf_storage_path (R3-05, R4-06).
3. Fail-closed ante cualquier archivo inaccesible, corrupto, inexistente o con path fuera de root; PROHIBIDO fallback a basename (R4-06).
4. Deteccion de modificaciones concurrentes pre/post pg_dump y durante el empaquetado de respaldo (R4-06, R5-03).
5. Cifrado simetrico autenticado en reposo con AES-256-GCM con clave independiente.
6. Manifiesto firmado criptograficamente con HMAC-SHA256, huella de procedencia y hashes de componentes.
7. Autenticacion de identidad de destino PostgreSQL: origen!=destino, source_url obligatoria, base destino estrictamente efimera (dr_test_*) y presencia obligatoria de marcador de propiedad verificado antes de restaurar (R4-01, R5-01).
8. Identidad autenticada de contenedor Docker: verificacion de cluster (system_identifier) y rechazo de ambiguedad (R4-02, R5-04).
9. Verificacion estricta de PostgreSQL 15: 150000 <= server_version_num < 160000 (R3-04).
10. Ejecucion atomica de psql con -X -v ON_ERROR_STOP=1 --single-transaction; sin parser naive ';\\n' ni fallback a SQLAlchemy (R3-03, R5-08).
11. Confinamiento estricto de rutas contra path traversal y symlinks tanto en tar como en catalogo (R3-13).
12. Restauracion con directorio staging independiente y promocion atomica snapshot-backed; ante fallo, el destino original no es alterado (R4-07, R5-02).
13. Separacion de contrato integral (db_restored=True obligatorio) vs solo-documentos (R3-02).
"""

import os
import sys
import json
import time
import uuid
import shutil
import hashlib
import tarfile
import logging
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.crypto import (
    encrypt_aead,
    decrypt_aead,
    sign_hmac_sha256,
    verify_hmac_sha256,
    validate_and_parse_key
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("abst_gp.dr.backup_lan_pg15")


class SecurityError(Exception):
    """Excepción de seguridad para violaciones de confinamiento de rutas o manipulación."""
    pass

# Bases de datos protegidas/operativas o preexistentes que NUNCA pueden ser destino de restauracion de prueba (R3-03, R4-01, R5-01)
DENIED_TARGET_DATABASES = {
    "postgres", "template0", "template1", "production", "prod", "abst_gp", "abst_prod",
    "main", "system", "test_db", "test_finance_real_data", "finance", "operativa", "default"
}


def compute_file_sha256(filepath: Path) -> str:
    """Calcula el hash SHA-256 de un archivo en bloques de 64KB."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            sha256.update(block)
    return sha256.hexdigest()


def validate_restore_target_safety(
    target_database_url: str,
    source_database_url: Optional[str] = None,
    expected_marker_id: Optional[str] = None,
    manifest: Optional[Dict[str, Any]] = None
) -> None:
    """
    Preflight estricto de seguridad para restauracion DR (R3-03, R4-01, R5-01):
    1. expected_marker_id es ESTRICTAMENTE OBLIGATORIO (identificador de propiedad efimero del run). Prohibido omitirlo.
    2. source_database_url es ESTRICTAMENTE OBLIGATORIA (suministrada explicitamente o extraida del manifest firmado).
    3. La base de destino NO puede ser identica a la de origen en el mismo host y puerto.
    4. Prohibicion absoluta de bases operativas o protegidas (DENIED_TARGET_DATABASES).
    5. Nombres permitidos: EXCLUSIVAMENTE bases de datos efimeras dinamicas generadas para el run (dr_test_<token> con token >= 5 chars).
       Bases preexistentes o no efimeras (test_db, test_finance_real_data, p14_dr_restore_target) son RECHAZADAS.
    6. Verificacion de identidad y marcador de propiedad persistido: La base de datos destino DEBE poseer
       la tabla de verificacion '_dr_test_ownership_marker' con un marcador que coincida exactamente con expected_marker_id.
       Si la tabla o el marcador esperado no existen o no coinciden, ABORTA con PermissionError sin tocar nada.
    """
    if not target_database_url:
        raise ValueError("Fallo de seguridad critico (R4-01, R5-01): target_database_url es obligatoria.")

    effective_source_url = source_database_url or (manifest.get("source_provenance") if manifest else None)
    if not effective_source_url or not str(effective_source_url).strip():
        raise ValueError(
            "Fallo de seguridad critico (R4-01, R5-01): source_database_url es obligatoria para verificar origen y destino "
            "y prevenir sobrescrituras accidentales. Debe proporcionarse explicitamente o extraerse de un manifiesto firmado."
        )

    if not expected_marker_id or not str(expected_marker_id).strip():
        raise ValueError(
            "Fallo de seguridad critico (R5-01): expected_marker_id es estrictamente obligatorio para autenticar "
            "la propiedad de la base de datos destino efimera de esta ejecucion. Prohibido omitir el identificador de marcador."
        )

    parsed_tgt = urlparse(target_database_url)
    tgt_db = parsed_tgt.path.lstrip("/")
    tgt_host = parsed_tgt.hostname or "localhost"
    tgt_port = parsed_tgt.port or 5432

    if not tgt_db:
        raise ValueError("URL de base de datos destino invalida: nombre de base de datos vacio.")

    # 1. Prohibicion de bases protegidas / operativas
    if tgt_db.lower() in DENIED_TARGET_DATABASES:
        raise ValueError(
            f"Fallo de seguridad critico (R4-01, R5-01): La base de datos destino '{tgt_db}' es una base de datos "
            f"operativa o protegida del sistema. Prohibido restaurar copias de prueba sobre {tgt_db}."
        )

    # 2. Allowlist estricta de nombres efimeros dinamicos: dr_test_<token> (min 5 chars)
    # Rechaza test_*, test_db, test_finance_real_data, p14_dr_restore_target
    is_valid_ephemeral = (
        tgt_db.startswith("dr_test_") and
        len(tgt_db[len("dr_test_"):]) >= 5 and
        tgt_db != "dr_test_restore_target"
    )
    if not is_valid_ephemeral:
        raise ValueError(
            f"Fallo de seguridad critico (R4-01, R5-01): La base de datos destino '{tgt_db}' no esta autorizada "
            f"como base de pruebas DR. Solo se permiten nombres efimeros dinamicos con formato 'dr_test_<token>' (minimo 5 caracteres)."
        )

    # 3. Comprobacion de que destino != origen
    parsed_src = urlparse(effective_source_url)
    src_db = parsed_src.path.lstrip("/")
    src_host = parsed_src.hostname or "localhost"
    src_port = parsed_src.port or 5432

    norm_src_host = "127.0.0.1" if src_host in ("localhost", "127.0.0.1") else src_host
    norm_tgt_host = "127.0.0.1" if tgt_host in ("localhost", "127.0.0.1") else tgt_host

    if (norm_src_host == norm_tgt_host) and (src_port == tgt_port) and (src_db == tgt_db):
        raise ValueError(
            f"Fallo de seguridad critico (R4-01, R5-01): La base de datos destino '{tgt_db}' es identica "
            f"a la base de datos de origen. Prohibido restaurar sobre la base operativa de origen."
        )

    # 4. Verificacion OBLIGATORIA de existencia y valor de marcador de propiedad efimero en la BD destino (R4-01, R5-01)
    try:
        chk_engine = create_engine(target_database_url, connect_args={"connect_timeout": 5})
        with chk_engine.connect() as conn:
            # 1. Comprobar existencia del marcador de propiedad efimero (_dr_test_ownership_marker) (R5-01)
            table_exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '_dr_test_ownership_marker'"
            )).scalar()
            if not table_exists:
                raise PermissionError(
                    f"Fallo de seguridad critico (R5-01): La base de datos destino '{tgt_db}' no contiene "
                    f"la tabla de verificacion '_dr_test_ownership_marker'. Prohibido restaurar sobre bases "
                    f"existentes o ajenas sin propiedad efimera verificada."
                )
            marker_row = conn.execute(
                text("SELECT marker_id FROM _dr_test_ownership_marker WHERE marker_id = :m"),
                {"m": expected_marker_id}
            ).scalar()
            if not marker_row:
                raise PermissionError(
                    f"Fallo de seguridad critico (R5-01): El marcador de propiedad en '{tgt_db}' "
                    f"no coincide con el marcador esperado de esta ejecucion ({expected_marker_id})."
                )

            # 2. Comprobar si la base de datos destino esta en cuarentena por fallo previo (B1)
            try:
                quarantine_exists = conn.execute(text(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '_dr_restoration_quarantine'"
                )).scalar()
                if quarantine_exists:
                    raise PermissionError(
                        f"Fallo de seguridad critico (B1): La base de datos destino '{tgt_db}' se encuentra en cuarentena "
                        f"estricta por restauracion previa inconsistente o fallida (_dr_restoration_quarantine detectada). Prohibido operar."
                    )
            except PermissionError:
                raise
            except StopIteration:
                pass
        chk_engine.dispose()
    except (ValueError, PermissionError):
        raise
    except Exception as e:
        err_msg = str(e).lower()
        if "does not exist" in err_msg:
            raise ValueError(f"Fallo de seguridad critico (R4-01, R5-01): La base de datos destino '{tgt_db}' no existe en el servidor.")
        raise RuntimeError(f"Fallo al autenticar la base de datos destino '{tgt_db}': {e}")


def verify_postgresql_15_server(session) -> Tuple[int, str]:
    """
    Verifica que el servidor conectado sea PostgreSQL version 15 (P14-R1-10, P14-R3-04).
    Enforce 150000 <= server_version_num < 160000.
    Falla de forma dura y fail-closed si la version no corresponde a la rama 15 o si no se puede determinar.
    Nunca asume ni simula la version 150000.
    """
    try:
        version_num = session.execute(text("SELECT current_setting('server_version_num')::int")).scalar()
        full_version = session.execute(text("SELECT version()")).scalar() or ""
    except Exception as e:
        raise RuntimeError(f"Error consultando version de PostgreSQL: {e}")

    if version_num is None:
        raise RuntimeError("Fallo de verificacion PostgreSQL (R3-04): server_version_num retorno None.")

    if not (150000 <= int(version_num) < 160000):
        raise RuntimeError(
            f"Fallo de compatibilidad PostgreSQL (R3-04): Se requiere version PostgreSQL 15 (150000 <= server_version_num < 160000). "
            f"Detectada version_num={version_num} ({full_version[:60]})."
        )

    return int(version_num), full_version


def create_document_catalog(uploads_dir: Path, session=None) -> List[Dict[str, Any]]:
    """
    Crea un catalogo exhaustivo SHA-256 de todos los documentos y reportes P13 (R3-05, R4-06).
    - Fail-closed: ante cualquier archivo ilegible o con error de lectura, aborta inmediatamente.
    - Conciliacion obligatoria: si se proporciona sesion de BD, verifica que todos los registros de
      UploadedDocument y GeneratedOutput.pdf_storage_path existan fisicamente en disco y coincidan
      con sus hashes criptograficos.
    - Prohibido fallback a basename para stored_path no encontrado o fuera de uploads (R4-06).
    """
    catalog: List[Dict[str, Any]] = []
    catalog_by_rel: Dict[str, Dict[str, Any]] = {}

    uploads_resolved = uploads_dir.resolve()

    if uploads_dir.exists():
        for root, _, files in os.walk(uploads_dir):
            for file in files:
                if file.startswith(".tmp_") or file == ".write_freeze_lock":
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(uploads_dir).as_posix()
                try:
                    file_size = file_path.stat().st_size
                    file_sha = compute_file_sha256(file_path)
                    entry = {
                        "relative_path": rel_path,
                        "size_bytes": file_size,
                        "sha256": file_sha
                    }
                    catalog.append(entry)
                    catalog_by_rel[rel_path] = entry
                except Exception as e:
                    raise RuntimeError(
                        f"Fallo critico en respaldo DR (R3-05): archivo inaccesible o no legible en disco: {file_path}. Detalle: {e}"
                    )

    # Conciliacion con registros persistidos de BD si hay sesion disponible (R3-05, R4-06)
    if session is not None:
        try:
            # 1. Conciliar UploadedDocument sin fallback a basename (R4-06)
            from app.models.domain import UploadedDocument
            uploaded_docs = session.query(UploadedDocument).all()
            for doc in uploaded_docs:
                if not doc.stored_path:
                    continue
                raw_path = Path(doc.stored_path)
                if raw_path.is_absolute():
                    try:
                        rel_candidate = raw_path.resolve().relative_to(uploads_resolved).as_posix()
                    except ValueError:
                        raise SecurityError(
                            f"Fallo critico de coherencia DR (R4-06): UploadedDocument id={doc.id} tiene stored_path "
                            f"absoluto '{doc.stored_path}' fuera del directorio raiz de uploads. Prohibido fallback a basename."
                        )
                else:
                    rel_candidate = raw_path.as_posix()

                candidate_full = uploads_dir / rel_candidate
                if not candidate_full.exists():
                    raise FileNotFoundError(
                        f"Incoherencia critica en respaldo DR (R4-06): UploadedDocument id={doc.id} "
                        f"(stored_path='{doc.stored_path}') no existe en disco en {candidate_full}. Prohibido fallback a basename."
                    )

                if rel_candidate not in catalog_by_rel:
                    file_size = candidate_full.stat().st_size
                    file_sha = compute_file_sha256(candidate_full)
                    entry = {
                        "relative_path": rel_candidate,
                        "size_bytes": file_size,
                        "sha256": file_sha
                    }
                    catalog.append(entry)
                    catalog_by_rel[rel_candidate] = entry
        except ImportError as e:
            raise RuntimeError(f"Fallo critico en respaldo DR (Item 2): no se pudo importar UploadedDocument: {e}")

        try:
            # 2. Conciliar GeneratedOutput (P13 Technical Reports) sin fallback a basename (R4-06)
            from app.models.v6.generated_output import GeneratedOutput
            generated_outputs = session.query(GeneratedOutput).filter(
                GeneratedOutput.pdf_storage_path.isnot(None)
            ).all()
            for out in generated_outputs:
                if not out.pdf_storage_path:
                    continue
                raw_path = Path(out.pdf_storage_path)
                if raw_path.is_absolute():
                    try:
                        rel_candidate = raw_path.resolve().relative_to(uploads_resolved).as_posix()
                    except ValueError:
                        raise SecurityError(
                            f"Fallo critico de coherencia DR (R4-06): GeneratedOutput id={out.id} tiene pdf_storage_path "
                            f"absoluto '{out.pdf_storage_path}' fuera del directorio raiz de uploads. Prohibido fallback a basename."
                        )
                else:
                    rel_candidate = raw_path.as_posix()

                candidate_full = uploads_dir / rel_candidate
                if not candidate_full.exists():
                    raise FileNotFoundError(
                        f"Incoherencia critica en respaldo DR (R4-06): GeneratedOutput P13 id={out.id} "
                        f"(pdf_storage_path='{out.pdf_storage_path}') no existe en disco en {candidate_full}. Prohibido fallback a basename."
                    )

                disk_sha = compute_file_sha256(candidate_full)
                if out.pdf_hash and disk_sha != out.pdf_hash:
                    raise RuntimeError(
                        f"Incoherencia criptografica en respaldo DR (R3-05): hash del archivo {candidate_full} "
                        f"({disk_sha}) no coincide con GeneratedOutput.pdf_hash ({out.pdf_hash})."
                    )

                if rel_candidate not in catalog_by_rel:
                    entry = {
                        "relative_path": rel_candidate,
                        "size_bytes": candidate_full.stat().st_size,
                        "sha256": disk_sha
                    }
                    catalog.append(entry)
                    catalog_by_rel[rel_candidate] = entry
        except ImportError as e:
            raise RuntimeError(f"Fallo critico en respaldo DR (Item 2): no se pudo importar GeneratedOutput: {e}")

    return catalog


def find_postgres_docker_container(
    user: str = "test_user",
    db_name: str = "test_db",
    target_host: Optional[str] = None,
    container_name: Optional[str] = None,
    expected_system_identifier: Optional[str] = None
) -> str:
    """
    Identifica de forma inequívoca el contenedor Docker de PostgreSQL 15 (R4-02, R5-04, B3).
    - Exige obligatoriamente expected_system_identifier para validar identidad de cluster.
    - Prohíbe autoselección ambigua basada en substrings o versiones sin correspondencia de endpoint.
    - Si se especifica container_name: Comprueba que exista, esté en ejecución, sea PG15 y coincida con el cluster.
    - Si NO se especifica container_name:
      1. Obtiene los contenedores Docker en ejecución con inspección precisa.
      2. Descarta coincidencia por subcadena; requiere igualdad exacta de nombre, etiqueta de servicio compose o formato canónico.
      3. Coteja obligatoriamente version PG15 y system_identifier de pg_control_system() con expected_system_identifier.
      4. Si no existe ninguno que responda al cluster solicitado, ABORTA fail-closed con RuntimeError.
    """
    if not expected_system_identifier or not str(expected_system_identifier).strip() or str(expected_system_identifier).strip() == "None":
        raise RuntimeError(
            "Fallo critico de verificacion de identidad Docker (B3): expected_system_identifier es obligatorio "
            "y no fue provisto. No se permite seleccionar ni operar sobre contenedores Docker sin identificador de cluster autentico."
        )
    expected_sys_str = str(expected_system_identifier).strip()

    # Caso 1: Contenedor explícito solicitado
    if container_name:
        try:
            inspect_res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            if inspect_res.returncode != 0 or inspect_res.stdout.strip() != "true":
                raise RuntimeError(f"Contenedor solicitado '{container_name}' no existe o no se encuentra en ejecucion.")

            # Verificar version 15 real dentro del contenedor
            check_cmd = [
                "docker", "exec", container_name,
                "psql", "-U", user, "-d", "postgres", "-t", "-A",
                "-c", "SELECT current_setting('server_version_num')::int;"
            ]
            v_res = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if v_res.returncode != 0:
                raise RuntimeError(f"No se pudo consultar PostgreSQL en contenedor '{container_name}': {v_res.stderr.strip()}")
            v_num = int(v_res.stdout.strip())
            if not (150000 <= v_num < 160000):
                raise RuntimeError(f"El contenedor '{container_name}' ejecuta version {v_num}, pero se requiere estrictamente PG15.")

            # B3: Verificar obligatoriamente system_identifier del cluster contra el endpoint DSN
            sys_cmd = [
                "docker", "exec", container_name,
                "psql", "-U", user, "-d", "postgres", "-t", "-A",
                "-c", "SELECT system_identifier FROM pg_control_system();"
            ]
            s_res = subprocess.run(sys_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if s_res.returncode != 0:
                raise RuntimeError(f"No se pudo consultar system_identifier en contenedor '{container_name}': {s_res.stderr.strip()}")
            cont_sys_id = s_res.stdout.strip()
            if cont_sys_id != expected_sys_str:
                raise RuntimeError(
                    f"Fallo de identidad de cluster (R5-04) (B3): El contenedor '{container_name}' pertenece a un "
                    f"cluster PostgreSQL distinto (system_identifier={cont_sys_id} != {expected_sys_str})."
                )

            # Item 3: Exigir correspondencia de la base solicitada dentro del contenedor
            if db_name:
                db_chk_cmd = [
                    "docker", "exec", container_name,
                    "psql", "-U", user, "-d", "postgres", "-t", "-A",
                    "-c", f"SELECT 1 FROM pg_database WHERE datname = '{db_name}';"
                ]
                db_res = subprocess.run(db_chk_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if db_res.returncode == 0 and db_res.stdout.strip() != "1":
                    raise RuntimeError(
                        f"Fallo de correspondencia de base de datos (Item 3): El contenedor '{container_name}' "
                        f"no contiene la base de datos solicitada '{db_name}'."
                    )

            logger.info(f"Contenedor explícito verificado con éxito: {container_name} (PG version {v_num}, cluster {cont_sys_id})")
            return container_name
        except Exception as e:
            raise RuntimeError(f"Error autenticando contenedor explicitado '{container_name}' (B3): {e}")

    # Caso 2: Autodetección controlada por endpoint de red sin coincidencias por subcadena
    try:
        res = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Labels}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if res.returncode != 0 or not res.stdout.strip():
            raise RuntimeError("No se pudo listar contenedores Docker en ejecucion.")

        lines = [l.strip() for l in res.stdout.strip().splitlines() if l.strip()]
        candidate_names = []

        host_norm = (target_host or "localhost").lower()

        for line in lines:
            parts = line.split("\t")
            c_name = parts[0]
            c_image = parts[1] if len(parts) > 1 else ""
            c_labels = parts[3] if len(parts) > 3 else ""

            # Coincidencia estricta de identidad (sin substring de libre busqueda)
            is_match = False
            if host_norm in ("localhost", "127.0.0.1", "0.0.0.0"):
                # Si el endpoint es localhost/127.0.0.1, considerar contenedores que expongan PG15
                if "postgres:15" in c_image.lower() or "pg15" in c_image.lower():
                    is_match = True
            else:
                # Nombre exacto
                if c_name.lower() == host_norm:
                    is_match = True
                # Compose service exacto en labels (ej. com.docker.compose.service=db-test)
                elif f"com.docker.compose.service={host_norm}" in c_labels.lower():
                    is_match = True
                # Patron canonico de compose: <project>_<service>_<num> o <project>-<service>-<num>
                elif c_name.lower().endswith(f"_{host_norm}_1") or c_name.lower().endswith(f"-{host_norm}-1") or \
                     f"_{host_norm}_" in c_name.lower() or f"-{host_norm}-" in c_name.lower():
                    # Solo prefijo/sufijo delimitado, no substring general
                    is_match = True

            if is_match:
                candidate_names.append(c_name)

        if not candidate_names:
            raise RuntimeError(
                f"No se detecto ningun contenedor Docker correspondiente de forma estricta al host '{host_norm}' (B3)."
            )

        # Validar version PG15 y system_identifier de cada candidato de forma fail-closed
        verified_containers = []
        for cand in candidate_names:
            try:
                check_cmd = [
                    "docker", "exec", cand,
                    "psql", "-U", user, "-d", "postgres", "-t", "-A",
                    "-c", "SELECT current_setting('server_version_num')::int;"
                ]
                v_res = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if v_res.returncode != 0:
                    continue
                v_num = int(v_res.stdout.strip())
                if not (150000 <= v_num < 160000):
                    continue

                sys_cmd = [
                    "docker", "exec", cand,
                    "psql", "-U", user, "-d", "postgres", "-t", "-A",
                    "-c", "SELECT system_identifier FROM pg_control_system();"
                ]
                s_res = subprocess.run(sys_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if s_res.returncode != 0:
                    continue
                cand_sys_id = s_res.stdout.strip()

                if cand_sys_id == expected_sys_str:
                    # Item 3: Comprobar que el candidato contenga la base solicitada
                    if db_name:
                        db_chk_cmd = [
                            "docker", "exec", cand,
                            "psql", "-U", user, "-d", "postgres", "-t", "-A",
                            "-c", f"SELECT 1 FROM pg_database WHERE datname = '{db_name}';"
                        ]
                        db_res = subprocess.run(db_chk_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                        if db_res.returncode == 0 and db_res.stdout.strip() != "1":
                            continue
                    verified_containers.append(cand)
            except Exception:
                continue

        if len(verified_containers) == 1:
            logger.info(f"Contenedor Docker autodetectado y autenticado: {verified_containers[0]} (cluster={expected_sys_str})")
            return verified_containers[0]
        elif len(verified_containers) > 1:
            raise RuntimeError(
                f"Deteccion ambigua (R4-02) (B3): Se encontraron {len(verified_containers)} contenedores coincidentes "
                f"con el cluster {expected_sys_str} ({verified_containers}). Debe especificar explicitamente --container."
            )
        else:
            raise RuntimeError(
                f"Fallo de identidad de cluster (B3): Ningun contenedor candidato ({candidate_names}) "
                f"coincide con el system_identifier={expected_sys_str} del endpoint DSN."
            )

    except Exception as e:
        raise RuntimeError(f"Fallo en la identificacion inequívoca de contenedor PostgreSQL 15 (B3): {e}")


def execute_pg_dump(database_url: str, output_sql_file: Path, container_name: Optional[str] = None) -> int:
    """
    Ejecuta un dump logico completo de PostgreSQL 15 (DDL + datos + secuencias + constraints).
    Soporta pg_dump directo en host o via contenedor Docker validado (P14-R1-10, P14-R2-07, R3-04, R4-02).
    Falla de forma dura y fail-closed si las herramientas no estan disponibles.
    Exige identidad comprobada de cluster (Item 3).
    """
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/")
    user = parsed.username or "test_user"
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)

    # 0. Item 3: Exigir identidad comprobada del cluster PostgreSQL origen
    expected_system_identifier = None
    try:
        engine = create_engine(database_url, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            expected_system_identifier = str(conn.execute(text("SELECT system_identifier FROM pg_control_system()")).scalar())
            v_num = int(conn.execute(text("SELECT current_setting('server_version_num')::int")).scalar())
        engine.dispose()
    except Exception as e:
        if not shutil.which("pg_dump"):
            raise RuntimeError(
                f"Fallo critico en pg_dump (Item 3): Herramienta pg_dump no disponible. Imposible consultar system_identifier en el DSN origen para respaldo via Docker: {e}. "
                f"Respaldo abortado para evitar volcado de cluster arbitrario."
            )
        raise RuntimeError(
            f"Fallo critico en pg_dump (Item 3): Imposible consultar system_identifier en el DSN origen para respaldo via Docker: {e}. "
            f"Respaldo abortado para evitar volcado de cluster arbitrario."
        )

    if not expected_system_identifier or expected_system_identifier == "None":
        raise RuntimeError("Fallo critico en pg_dump (Item 3): system_identifier obtenido del DSN origen es invalido o vacio.")

    if not (150000 <= v_num < 160000):
        raise RuntimeError(f"Fallo critico en pg_dump (Item 3): Se requiere PostgreSQL 15, detectado {v_num}.")

    # 1. Intentar pg_dump local en host si existe en PATH
    if shutil.which("pg_dump"):
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password
        cmd = [
            "pg_dump",
            "-h", host,
            "-p", port,
            "-U", user,
            "-d", db_name,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges"
        ]
        with open(output_sql_file, "wb") as f_out:
            res = subprocess.run(cmd, env=env, stdout=f_out, stderr=subprocess.PIPE, timeout=120)
            if res.returncode == 0 and output_sql_file.stat().st_size > 0:
                logger.info(f"pg_dump local completado exitosamente: {output_sql_file} ({output_sql_file.stat().st_size} bytes)")
                return output_sql_file.stat().st_size
            else:
                logger.warning(f"pg_dump local fallo ({res.returncode}): {res.stderr.decode('utf-8', errors='ignore')[:200]}")

    # 2. Intentar ejecutar pg_dump dentro del contenedor Docker de PG15 autenticado (R4-02, R5-04, B3)
    docker_container = find_postgres_docker_container(
        user=user,
        db_name=db_name,
        target_host=host,
        container_name=container_name,
        expected_system_identifier=expected_system_identifier
    )
    if docker_container:
        cmd = [
            "docker", "exec", docker_container,
            "pg_dump",
            "-U", user,
            "-d", db_name,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges"
        ]
        with open(output_sql_file, "wb") as f_out:
            res = subprocess.run(cmd, stdout=f_out, stderr=subprocess.PIPE, timeout=120)
            if res.returncode == 0 and output_sql_file.stat().st_size > 0:
                logger.info(f"pg_dump via Docker ({docker_container}) completado exitosamente ({output_sql_file.stat().st_size} bytes)")
                return output_sql_file.stat().st_size
            else:
                logger.error(f"pg_dump docker retorno codigo {res.returncode}: {res.stderr.decode('utf-8', errors='ignore')[:200]}")

    # 3. Fail-closed: Si las herramientas fallan, abortar de inmediato (P14-R2-07)
    raise RuntimeError(
        "Fallo critico en respaldo DR: pg_dump no esta disponible en el PATH ni en Docker, "
        "o fallo durante la ejecucion. No se permite generar copias de seguridad sin un volcado autentico de PostgreSQL 15."
    )


def execute_pg_restore(
    target_database_url: str,
    sql_file: Path,
    expected_marker_id: str,
    source_database_url: str,
    container_name: Optional[str] = None
) -> bool:
    """
    Restaura el archivo SQL en la base de datos destino aislada mediante psql con -X -v ON_ERROR_STOP=1 --single-transaction (R3-03, R4-01, R5-01, R5-08).
    Preflight estricto: origen!=destino, base autorizada para pruebas DR con marcador obligatorio y verificado en BD.
    Exige identidad comprobada de cluster (Item 3).
    Prohibido cualquier fallback a ejecucion ingenua de SQL completo en SQLAlchemy (R5-08).
    """
    # 0. Preflight de seguridad obligatorio y comprobacion de destino con identificador de propiedad (R3-03, R4-01, R5-01)
    validate_restore_target_safety(
        target_database_url=target_database_url,
        source_database_url=source_database_url,
        expected_marker_id=expected_marker_id
    )

    if not sql_file.exists() or sql_file.stat().st_size == 0:
        raise ValueError(f"Archivo de volcado SQL no existe o esta vacio: {sql_file}")

    parsed = urlparse(target_database_url)
    db_name = parsed.path.lstrip("/")
    user = parsed.username or "test_user"
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)

    restore_success = False

    # Item 3: Exigir identidad comprobada del cluster PostgreSQL destino
    expected_system_identifier = None
    try:
        chk_eng = create_engine(target_database_url, connect_args={"connect_timeout": 5})
        with chk_eng.connect() as conn:
            expected_system_identifier = str(conn.execute(text("SELECT system_identifier FROM pg_control_system()")).scalar())
            v_num = int(conn.execute(text("SELECT current_setting('server_version_num')::int")).scalar())
        chk_eng.dispose()
    except Exception as e:
        if not shutil.which("psql"):
            raise RuntimeError(
                f"Fallo critico en execute_pg_restore (Item 3) (R5-08): La herramienta psql no esta disponible en el host local ni en Docker. "
                f"Imposible consultar system_identifier en el DSN destino para restauracion via Docker: {e}. Restauracion abortada para evitar operaciones en cluster arbitrario."
            )
        raise RuntimeError(
            f"Fallo critico en execute_pg_restore (Item 3): Imposible consultar system_identifier en el DSN destino para restauracion via Docker: {e}. Abortando."
        )

    if not expected_system_identifier or expected_system_identifier == "None":
        raise RuntimeError("Fallo critico en execute_pg_restore (Item 3): system_identifier obtenido del DSN destino es invalido o vacio.")

    if not (150000 <= v_num < 160000):
        raise RuntimeError(f"Fallo critico en execute_pg_restore (Item 3): Se requiere PostgreSQL 15, detectado {v_num}.")

    quarantine_snippet = (
        b"\n-- B1: Cuarentena preventiva durante restauracion (se levantara solo tras corte documental verificado)\n"
        b"DROP TABLE IF EXISTS public._dr_test_ownership_marker CASCADE;\n"
        b"CREATE TABLE IF NOT EXISTS public._dr_restoration_quarantine (\n"
        b"  id SERIAL PRIMARY KEY,\n"
        b"  quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n"
        b"  reason TEXT NOT NULL,\n"
        b"  journal_state TEXT\n"
        b");\n"
        b"INSERT INTO public._dr_restoration_quarantine (reason, journal_state) "
        b"VALUES ('RESTORATION_IN_PROGRESS (B1): Base restaurada pendiente de corte documental', 'DB_RESTORED');\n"
    )

    effective_sql_file = sql_file.parent / f".prep_restore_{uuid.uuid4().hex[:6]}.sql"
    with open(effective_sql_file, "wb") as f_out:
        with open(sql_file, "rb") as f_in:
            shutil.copyfileobj(f_in, f_out)
        f_out.write(quarantine_snippet)
        f_out.flush()
        os.fsync(f_out.fileno())

    try:
        # 1. Intentar psql local en host si existe en PATH con transaccion unica y fail-closed (R3-03)
        if shutil.which("psql"):
            env = os.environ.copy()
            if parsed.password:
                env["PGPASSWORD"] = parsed.password
            cmd = [
                "psql",
                "-X",
                "-v", "ON_ERROR_STOP=1",
                "--single-transaction",
                "-h", host,
                "-p", port,
                "-U", user,
                "-d", db_name
            ]
            with open(effective_sql_file, "rb") as f_in:
                res = subprocess.run(cmd, env=env, stdin=f_in, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                if res.returncode == 0:
                    logger.info(f"psql local (--single-transaction) restauro la base de datos {db_name} con exito.")
                    restore_success = True
                else:
                    err_msg = res.stderr.decode('utf-8', errors='ignore')[:400]
                    logger.error(f"psql local fallo con error {res.returncode}: {err_msg}")
                    raise RuntimeError(f"psql local fallo al restaurar {db_name}: {err_msg}")

        # 2. Intentar via Docker exec psql con transaccion unica y fail-closed (R3-03, R4-02, R5-04, B3)
        if not restore_success:
            docker_container = find_postgres_docker_container(
                user=user,
                db_name=db_name,
                target_host=host,
                container_name=container_name,
                expected_system_identifier=expected_system_identifier
            )
            if docker_container:
                cmd = [
                    "docker", "exec", "-i", docker_container,
                    "psql",
                    "-X",
                    "-v", "ON_ERROR_STOP=1",
                    "--single-transaction",
                    "-U", user,
                    "-d", db_name
                ]
                with open(effective_sql_file, "rb") as f_in:
                    res = subprocess.run(cmd, stdin=f_in, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                    if res.returncode == 0:
                        logger.info(f"psql via Docker ({docker_container}) restauro la base de datos {db_name} con exito.")
                        restore_success = True
                    else:
                        err_msg = res.stderr.decode('utf-8', errors='ignore')[:400]
                        logger.error(f"psql docker fallo con error {res.returncode}: {err_msg}")
                        raise RuntimeError(f"psql via Docker fallo al restaurar {db_name}: {err_msg}")

        # 3. R5-08: Eliminacion absoluta de fallback naive a SQLAlchemy text(full_sql)
        if not restore_success:
            raise RuntimeError(
                "Fallo critico en execute_pg_restore (R5-08): La herramienta psql no esta disponible en el host local ni en Docker, "
                "o fallo durante la ejecucion. Esta estrictamente prohibido ejecutar volcados de PostgreSQL mediante drivers o sentencias "
                "SQLAlchemy individuales. La restauracion DR aborta fail-closed sin modificar la base de datos."
            )
    finally:
        effective_sql_file.unlink(missing_ok=True)

    return restore_success


def _capture_snapshot_state(uploads_dir: Path, database_url: str) -> Dict[str, Any]:
    """
    Captura el estado integral de documentos en BD y en disco para verificar coherencia de snapshot (R5-03, B2, Item 2).
    Fail-closed estricto: Cualquier fallo en conexion, consulta SQL o lectura de disco aborta con RuntimeError.
    Prohibido capturar snapshots vacios o silenciar excepciones (B2).
    Verificacion basada EXCLUSIVAMENTE en contenido criptografico SHA-256 (prohibido basarse solo en tamano/fecha) (Item 2).
    Captura huella MD5 exacta de todas las columnas (CAST t.* AS text) y max(xmin) para detectar UPDATE sin cambio de filas (B2).
    """
    state: Dict[str, Any] = {
        "uploaded_docs": [],
        "generated_outputs": [],
        "table_fingerprints": {},
        "disk_files": {}
    }

    try:
        engine = create_engine(database_url, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            rows_ud = conn.execute(text("SELECT id, stored_path FROM uploaded_documents ORDER BY id")).fetchall()
            state["uploaded_docs"] = [(r[0], r[1]) for r in rows_ud]

            rows_go = conn.execute(text("SELECT id, pdf_storage_path, pdf_hash FROM generated_outputs WHERE pdf_storage_path IS NOT NULL ORDER BY id")).fetchall()
            state["generated_outputs"] = [(r[0], r[1], r[2]) for r in rows_go]

            # B2: Huella criptográfica integral de todas las tablas críticas
            # Detecta cualquier mutación/UPDATE de registros incluso SIN cambio en el número de filas
            for tbl in ["users", "tenants", "case_files", "uploaded_documents", "generated_outputs"]:
                try:
                    row_fp = conn.execute(text(
                        f"SELECT count(*), coalesce(max(xmin::text::bigint), 0), "
                        f"md5(coalesce(string_agg(md5(CAST((t.*) AS text)), ',' ORDER BY t.id), '')) "
                        f"FROM {tbl} t;"
                    )).fetchone()
                    if row_fp:
                        state["table_fingerprints"][tbl] = (row_fp[0], row_fp[1], row_fp[2])
                except Exception as tbl_err:
                    raise RuntimeError(f"Fallo critico al capturar huella criptografica de tabla '{tbl}' (B2): {tbl_err}")
        engine.dispose()
    except Exception as e:
        raise RuntimeError(f"Fallo critico al capturar estado de base de datos para snapshot DR (B2) (Item 2): {e}")

    if uploads_dir.exists():
        for root, _, files in os.walk(uploads_dir):
            for file in files:
                if file.startswith(".tmp_") or file == ".write_freeze_lock":
                    continue
                fp = Path(root) / file
                rel = fp.relative_to(uploads_dir).as_posix()
                try:
                    file_sha = compute_file_sha256(fp)
                    state["disk_files"][rel] = file_sha
                except Exception as e:
                    raise RuntimeError(f"Fallo critico al capturar estado de archivo en disco para snapshot DR (B2, Item 2): {fp}: {e}")

    return state


try:
    from app.core.write_control import DocumentWriteControl, is_process_alive
except ImportError:
    try:
        from backend.app.core.write_control import DocumentWriteControl, is_process_alive
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
        from app.core.write_control import DocumentWriteControl, is_process_alive


def create_lan_backup(
    database_url: str,
    uploads_dir: Path,
    output_backup_file: Path,
    encryption_key: str,
    signing_key: str,
    container_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ejecuta un respaldo completo coherente (R3-05, R4-06, R5-03, B2):
    1. Captura de estado previo fail-closed para barrera de snapshot coherente (R5-03, B2).
    2. Dump logico consistente PostgreSQL 15 autentico (pg_dump).
    3. Verificacion de barrera post-dump: aborta si hubo inserciones, modificaciones o eliminaciones de documentos (R5-03, B2).
    4. Snapshot y catalogo SHA-256 conciliado con BD fail-closed sin fallback a basename y verificado contra snapshot post-dump (B2).
    5. Deteccion de modificaciones concurrentes durante el empaquetado del archivo TAR.
    6. Re-validacion estricta de barrera de corte logico previo a cifrado y firma (B2).
    7. Cifrado simetrico autenticado AES-256-GCM.
    8. Manifiesto firmado con HMAC-SHA256 (P14-R1-11).
    """
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        version_num, full_version = verify_postgresql_15_server(session)
    finally:
        session.close()

    temp_dir = output_backup_file.parent / f".tmp_backup_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with DocumentWriteControl(database_url, uploads_dir):
            # 1. R5-03, B2: Captura de estado previo a pg_dump para garantizar snapshot comun coherente
            pre_snapshot = _capture_snapshot_state(uploads_dir, database_url)

            # 2. Dump real de PostgreSQL 15
            sql_dump_path = temp_dir / "database.sql"
            dump_size = execute_pg_dump(database_url, sql_dump_path, container_name)

            # 3. R5-03, B2: Verificacion post-dump: si hubo cualquier cambio concurrente durante el volcado SQL, aborta
            post_snapshot = _capture_snapshot_state(uploads_dir, database_url)
            if pre_snapshot["uploaded_docs"] != post_snapshot["uploaded_docs"] or \
               pre_snapshot["generated_outputs"] != post_snapshot["generated_outputs"] or \
               pre_snapshot.get("table_fingerprints") != post_snapshot.get("table_fingerprints"):
                raise RuntimeError(
                    "Fallo de coherencia snapshot DR (R5-03) (B2): Modificacion concurrente detectada en registros de base de datos "
                    "(incluyendo mutacion de registros sin alteracion de filas) durante la ejecucion de pg_dump. Respaldo abortado para evitar estado incoherente."
                )
            if pre_snapshot["disk_files"] != post_snapshot["disk_files"]:
                raise RuntimeError(
                    "Fallo de coherencia snapshot DR (R5-03) (B2): Modificacion concurrente detectada en archivos en disco "
                    "durante la ejecucion de pg_dump. Respaldo abortado para evitar estado incoherente."
                )

            # 4. Catalogo de documentos con conciliacion fail-closed de BD (R3-05, R4-06)
            session_catalog = Session()
            try:
                catalog = create_document_catalog(uploads_dir, session=session_catalog)
            finally:
                session_catalog.close()

            # B2, Item 2: Validar concordancia estricta de hash SHA-256 entre catalogo generado y el post_snapshot
            catalog_files = {entry["relative_path"]: entry["sha256"] for entry in catalog}
            if catalog_files != post_snapshot["disk_files"]:
                raise RuntimeError(
                    "Fallo de coherencia snapshot DR (B2): Desajuste detectado entre catalogo de documentos "
                    "y el snapshot posterior a pg_dump. Posible mutacion concurrente de archivos."
                )

            catalog_path = temp_dir / "document_catalog.json"
            with open(catalog_path, "w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2)

            # 5. Conteos de tablas principales para comprobacion de consistencia sin silenciar errores (Item 2)
            table_counts = {}
            session_counts = Session()
            try:
                for tbl in ["users", "tenants", "case_files", "uploaded_documents", "generated_outputs"]:
                    try:
                        count = session_counts.execute(text(f"SELECT count(*) FROM {tbl}")).scalar()
                        table_counts[tbl] = count
                    except Exception as e:
                        raise RuntimeError(f"Fallo critico al capturar conteo de tabla '{tbl}' en respaldo DR (Item 2): {e}")
            finally:
                session_counts.close()

            # 6. Empaquetar tar sin cifrar verificando consistencia y detectando modificacion concurrente (R4-06)
            raw_tar_path = temp_dir / "raw_backup.tar"
            with tarfile.open(raw_tar_path, "w") as tar:
                tar.add(sql_dump_path, arcname="database.sql")
                tar.add(catalog_path, arcname="document_catalog.json")
                if uploads_dir.exists():
                    for cat_entry in catalog:
                        src_file = uploads_dir / cat_entry["relative_path"]
                        if not src_file.exists():
                            raise FileNotFoundError(
                                f"Fallo critico en respaldo DR (R4-06): Archivo de catalogo '{src_file}' desaparecido antes de empaquetar."
                            )
                        # Comprobar que el hash actual coincide con el hash del catalogo (deteccion de modificacion concurrente)
                        current_sha = compute_file_sha256(src_file)
                        if current_sha != cat_entry["sha256"]:
                            raise RuntimeError(
                                f"Fallo de coherencia en respaldo DR (R4-06): Modificacion concurrente detectada en '{src_file}'. "
                                f"Hash en catalogo={cat_entry['sha256']}, hash al empaquetar={current_sha}. Respaldo cancelado."
                            )
                        tar.add(src_file, arcname=f"uploads/{cat_entry['relative_path']}")

            # B2: Re-validacion estricta de corte logico antes de cifrar y firmar
            final_barrier = _capture_snapshot_state(uploads_dir, database_url)
            if final_barrier["disk_files"] != post_snapshot["disk_files"] or \
               final_barrier["uploaded_docs"] != post_snapshot["uploaded_docs"] or \
               final_barrier["generated_outputs"] != post_snapshot["generated_outputs"] or \
               final_barrier.get("table_fingerprints") != post_snapshot.get("table_fingerprints"):
                raise RuntimeError(
                    "Fallo de coherencia snapshot DR (B2): Modificacion concurrente de base de datos (incluyendo huellas "
                    "de tablas sin alteracion de conteo) o archivos en disco detectada en corte final antes de cifrar. "
                    "Respaldo abortado para garantizar corte logico estricto."
                )

        # 7. Cifrado AEAD AES-256-GCM
        with open(raw_tar_path, "rb") as f:
            raw_bytes = f.read()

        encrypted_payload = encrypt_aead(raw_bytes.decode("latin1"), encryption_key, key_id="v1")

        output_backup_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_backup_file, "w", encoding="utf-8") as f:
            f.write(encrypted_payload)

        # 8. Generar manifiesto firmado con HMAC-SHA256 (P14-R1-11, R4-01, R4-06)
        backup_sha = compute_file_sha256(output_backup_file)
        parsed_url = urlparse(database_url)
        source_provenance = f"postgresql://{parsed_url.hostname or 'localhost'}:{parsed_url.port or 5432}/{parsed_url.path.lstrip('/')}"

        manifest_data = {
            "backup_version": "P14-LAN-PG15-AUTHENTICATED-R5",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pg_server_version": version_num,
            "pg_dump_bytes": dump_size,
            "source_provenance": source_provenance,
            "document_count": len(catalog),
            "table_counts": table_counts,
            "backup_sha256": backup_sha
        }

        manifest_bytes = json.dumps(manifest_data, sort_keys=True).encode("utf-8")
        signature_hex = sign_hmac_sha256(manifest_bytes, signing_key)

        manifest = {
            **manifest_data,
            "hmac_signature": signature_hex
        }

        manifest_path = Path(str(output_backup_file) + ".manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info(
            f"Respaldo LAN PG15 generado con exito: {output_backup_file} "
            f"(Documentos: {len(catalog)}, Dump: {dump_size} bytes, SHA-256: {backup_sha[:16]}...)"
        )

        return {
            **manifest,
            "status": "BACKUP_SUCCESS",
            "backup_file": str(output_backup_file),
            "manifest_file": str(manifest_path),
            "document_count": len(catalog),
            "manifest": manifest
        }

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def _atomic_write_journal(journal_file: Path, data: Dict[str, Any]) -> None:
    """
    B1-02, B1-RESTORE: Escritura atomica y durable del diario transaccional (.cutover_journal.json).
    Comprueba previamente la integridad del diario anterior si existe, impidiendo
    la sobreescritura de evidencia corrupta o inconsistente irrecuperable.
    Escribe en archivo temporal en el mismo directorio, ejecuta flush() y fsync(),
    reemplaza de forma atomica (os.replace) y sincroniza el directorio padre donde este soportado.
    """
    if journal_file.exists():
        try:
            with open(journal_file, "r", encoding="utf-8") as f_prev:
                prev_data = json.load(f_prev)
        except Exception as e:
            raise RuntimeError(
                f"Fallo de integridad (B1-RESTORE): Intento de sobrescribir diario corrupto preexistente ({e}). "
                "Operacion denegada para preservar evidencia forense irrecuperable."
            )
        if data.get("phase") in ("RESTORATION_INITIATED", "PREPARING"):
            if isinstance(prev_data, dict) and prev_data.get("phase") == "FAILED_INCONSISTENT":
                raise RuntimeError(
                    "Fallo de integridad (B1-RESTORE): No se permite iniciar una nueva operacion sobre un diario en estado FAILED_INCONSISTENT."
                )

    parent_dir = journal_file.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = parent_dir / f"{journal_file.name}.tmp_{uuid.uuid4().hex}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, journal_file)
        try:
            dir_fd = os.open(str(parent_dir), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            pass
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _enforce_database_quarantine(db_url: str, reason: str, journal_state: Optional[str] = None) -> None:
    """
    B1-01: Garantiza la confirmacion transaccional irrefutable de la cuarentena PostgreSQL.
    Utiliza commit verificado ('conn.commit()') en SQLAlchemy 2.x para asegurar que DROP TABLE,
    CREATE TABLE e INSERT se confirmen de forma durable con COMMIT real en PostgreSQL 15 (B1-01).
    """
    if not db_url:
        return
    inv_engine = create_engine(db_url, connect_args={"connect_timeout": 5})
    try:
        with inv_engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public._dr_test_ownership_marker CASCADE;"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS public._dr_restoration_quarantine ("
                "  id SERIAL PRIMARY KEY,"
                "  quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  reason TEXT NOT NULL,"
                "  journal_state TEXT"
                ");"
            ))
            conn.execute(
                text(
                    "INSERT INTO public._dr_restoration_quarantine (reason, journal_state) "
                    "VALUES (:r, :js);"
                ),
                {"r": reason, "js": str(journal_state or "UNKNOWN")}
            )
            if hasattr(conn, "commit"):
                conn.commit()
        logger.warning(f"Coordinacion DR (B1): Cuarentena transaccional confirmada con exito en BD. Marcador invalidado. Causa: {reason}")
    finally:
        inv_engine.dispose()


def _lift_database_quarantine(db_url: Optional[str]) -> None:
    """
    B1: Levanta la cuarentena en PostgreSQL de forma transaccional verificada
    SOLO cuando la promocion y verificacion documental ha concluido exitosamente.
    """
    if not db_url:
        return
    engine = create_engine(db_url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public._dr_restoration_quarantine CASCADE;"))
            if hasattr(conn, "commit"):
                conn.commit()
        logger.info("Coordinacion DR (B1): Cuarentena en base de datos levantada exitosamente tras promocion documental verificada.")
    finally:
        engine.dispose()


class CrashResilientDocumentPublisher:
    """
    Mecanismo de publicacion y recuperacion documental resistente a interrupciones
    coordinado con la restauracion de PostgreSQL (Item 1, R5-02, B1, B1-01, B1-02).
    """
    def __init__(
        self,
        target_dir: Path,
        db_restored: bool = False,
        target_database_url: Optional[str] = None,
        expected_marker_id: Optional[str] = None
    ):
        self.target_dir = target_dir
        self.db_restored = db_restored
        self.target_database_url = target_database_url
        self.expected_marker_id = expected_marker_id

    @classmethod
    def recover(
        cls,
        parent_dir: Path,
        target_database_url: Optional[str] = None,
        expected_marker_id: Optional[str] = None
    ) -> bool:
        journal_file = parent_dir / ".cutover_journal.json"
        if not journal_file.exists():
            return False

        try:
            data = json.loads(journal_file.read_text(encoding="utf-8"))
            target = Path(data.get("target_dir", ""))
            backup = Path(data.get("backup_dir", ""))
            candidate = Path(data.get("candidate_dir", ""))
            phase = data.get("phase", "")
            db_restored = data.get("db_restored", False)
            catalog_hashes = data.get("catalog_hashes", {})
            db_url = target_database_url or data.get("target_database_url")

            logger.warning(
                f"Detectada interrupcion previa en fase '{phase}' (db_restored={db_restored}). "
                f"Iniciando protocolo de recuperacion post-caida coordinado con PostgreSQL (Item 1, B1, B1-02)."
            )

            if phase == "COMMITTED":
                if backup.exists():
                    shutil.rmtree(backup, ignore_errors=True)
                if db_url:
                    _lift_database_quarantine(db_url)
                journal_file.unlink(missing_ok=True)
                return True

            # Si PostgreSQL ya fue restaurado (db_restored=True o phase en DB_RESTORED / RESTORING_DATABASE):
            if db_restored or phase in ("DB_RESTORED", "RESTORING_DATABASE"):
                # Verificar exhaustivamente si candidate_dir es valido contra catalog_hashes
                candidate_valid = False
                if candidate.exists() and catalog_hashes:
                    try:
                        all_ok = True
                        for rel_path, expected_sha in catalog_hashes.items():
                            cand_file = candidate / rel_path
                            if not cand_file.exists() or compute_file_sha256(cand_file) != expected_sha:
                                all_ok = False
                                break
                        if all_ok:
                            candidate_valid = True
                    except Exception:
                        candidate_valid = False

                if candidate_valid:
                    # Recuperacion hacia adelante (Forward recovery):
                    # Promover candidate_dir a target_dir para sincronizar con la BD ya restaurada
                    if target.exists():
                        data["phase"] = "MOVING_TARGET"
                        _atomic_write_journal(journal_file, data)
                        if backup.exists():
                            shutil.rmtree(backup, ignore_errors=True)
                        target.rename(backup)
                    data["phase"] = "TARGET_MOVED"
                    _atomic_write_journal(journal_file, data)
                    candidate.rename(target)
                    data["phase"] = "COMMITTED"
                    _atomic_write_journal(journal_file, data)
                    if backup.exists():
                        shutil.rmtree(backup, ignore_errors=True)
                    if db_url:
                        _lift_database_quarantine(db_url)
                    journal_file.unlink(missing_ok=True)
                    logger.info("Recuperacion hacia adelante post-reinicio exitosa: candidate promovido a target coherente con PostgreSQL y cuarentena levantada.")
                    return True
                else:
                    # B1-02: Candidate ausente, corrupto o incompleto tras caida.
                    # PostgreSQL tiene la version nueva, pero los documentos NO pueden completarse.
                    # DEBE PONERSE LA BASE DE DATOS EN CUARENTENA TRANSACCIONAL OBLIGATORIA (B1-01, B1-02)
                    if not target.exists() and backup.exists():
                        backup.rename(target)
                    if candidate.exists():
                        shutil.rmtree(candidate, ignore_errors=True)
                    quarantine_ok = False
                    if db_url:
                        try:
                            _enforce_database_quarantine(
                                db_url,
                                reason=f"INCONSISTENT_RESTORATION (B1-02): Post-crash recovery in phase '{phase}' with db_restored=True. Candidate invalid/corrupted.",
                                journal_state=phase
                            )
                            # B1-B: Verificar confirmacion efectiva de la cuarentena en PostgreSQL
                            eng_q = create_engine(db_url, connect_args={"connect_timeout": 5})
                            with eng_q.connect() as conn_q:
                                q_exists = conn_q.execute(text("SELECT to_regclass('public._dr_restoration_quarantine');")).scalar()
                                if q_exists is not None:
                                    quarantine_ok = True
                                else:
                                    logger.error("Fallo B1-B: No se pudo verificar la confirmacion efectiva de la tabla de cuarentena en PostgreSQL.")
                            eng_q.dispose()
                        except Exception as db_err:
                            logger.error(f"Fallo critico al activar o verificar cuarentena transaccional en BD tras fallo: {db_err}")
                            quarantine_ok = False

                    # B1: Preservar el diario para permitir auditoria y diagnostico forense (no borrar evidencia)
                    data["phase"] = "FAILED_INCONSISTENT"
                    data["quarantine_confirmed"] = quarantine_ok
                    try:
                        _atomic_write_journal(journal_file, data)
                    except Exception:
                        pass

                    if db_url and not quarantine_ok:
                        logger.error("Fallo critico de recuperacion (B1-B): Fallo la activacion o confirmacion efectiva de cuarentena en BD. Retornando fallo fail-closed.")
                        return False

                    logger.error("Recuperacion procesada: BD asegurada en cuarentena transaccional estricta por restauracion documental inconsistente (B1-02). Diario preservado en FAILED_INCONSISTENT.")
                    return True
            else:
                # db_restored es False: no hubo restore de BD o fallo antes de tocar BD.
                # Revertir limpiamente a target original sin tocar BD.
                if not target.exists() and backup.exists():
                    backup.rename(target)
                if candidate.exists():
                    shutil.rmtree(candidate, ignore_errors=True)
                journal_file.unlink(missing_ok=True)
                return True

        except Exception as e:
            logger.error(f"Error ejecutando recuperacion de cutover pendiente (Item 1, B1): {e}")
            return False

    def publish(self, staging_dir: Path, catalog: List[Dict[str, Any]]) -> None:
        parent_dir = self.target_dir.parent.resolve()
        parent_dir.mkdir(parents=True, exist_ok=True)

        journal_file = parent_dir / ".cutover_journal.json"

        # 1. B1-A: Impedir que publish() continue cuando existe un journal previo cuya recuperacion fallo
        if journal_file.exists():
            # Distinguir expresamente inexistencia de corrupcion o recuperacion fallida
            try:
                journal_raw = journal_file.read_text(encoding="utf-8")
                prior_data = json.loads(journal_raw)
            except Exception as parse_err:
                logger.error(f"Journal previo corrupto o ilegible ({parse_err}). Abortando fail-closed (B1-A).")
                raise RuntimeError(
                    "Fallo critico de recuperacion (B1): Existe un diario de corte anterior (.cutover_journal.json) "
                    "corrupto o irrecuperable. Publicacion documental abortada de forma fail-closed para preservar la evidencia forense."
                )

            prior_phase = prior_data.get("phase", "")
            if prior_phase == "FAILED_INCONSISTENT":
                raise RuntimeError(
                    "Fallo critico de recuperacion (B1): El repositorio documental permanece en estado inconsistente "
                    "o en cuarentena por un corte fallido previo. Publicacion documental abortada de forma fail-closed."
                )

            # Si es la conmutacion documental de una restauracion legitima en curso:
            if prior_phase in ("RESTORATION_INITIATED", "DB_RESTORED") and self.db_restored:
                logger.info("Continuando promocion documental para restauracion activa de base de datos.")
            else:
                logger.warning(f"Detectada transicion documental previa en fase '{prior_phase}'. Ejecutando recover() fail-closed...")
                recovered = self.recover(parent_dir, self.target_database_url, self.expected_marker_id)
                if not recovered or journal_file.exists():
                    raise RuntimeError(
                        "Fallo critico de recuperacion (B1): Existe un diario de corte anterior (.cutover_journal.json) "
                        "cuya recuperacion no fue exitosa o el repositorio permanece en estado inconsistente/cuarentena. "
                        "Publicacion documental abortada de forma fail-closed para preservar la integridad y el diario de evidencia."
                    )

        run_id = uuid.uuid4().hex[:8]
        candidate_dir = parent_dir / f".target_candidate_{run_id}"
        backup_dir = parent_dir / f".target_backup_{run_id}"
        journal_file = parent_dir / ".cutover_journal.json"

        candidate_dir.mkdir(parents=True, exist_ok=True)

        catalog_hashes = {entry["relative_path"]: entry["sha256"] for entry in catalog}

        journal_data = {
            "phase": "PREPARING",
            "target_dir": str(self.target_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": self.db_restored,
            "target_database_url": self.target_database_url,
            "expected_marker_id": self.expected_marker_id,
            "catalog_hashes": catalog_hashes,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        try:
            # 2. Copiar y verificar exhaustivamente en candidate_dir aislado
            for entry in catalog:
                rel_path = Path(entry["relative_path"])
                src_file = staging_dir / rel_path
                dst_file = candidate_dir / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                content = src_file.read_bytes()
                dst_file.write_bytes(content)
                final_sha = hashlib.sha256(content).hexdigest()
                if final_sha != entry["sha256"]:
                    raise ValueError(f"Fallo de integridad en candidato {dst_file}: {final_sha} != {entry['sha256']}")

            journal_data["phase"] = "CANDIDATE_READY"
            _atomic_write_journal(journal_file, journal_data)

            if self.db_restored:
                journal_data["phase"] = "DB_RESTORED"
                _atomic_write_journal(journal_file, journal_data)

            # 3. Conmutacion a nivel de filesystem con persistencia previa de intencion (B1-02)
            target_existed = self.target_dir.exists()
            if target_existed:
                journal_data["phase"] = "MOVING_TARGET"
                _atomic_write_journal(journal_file, journal_data)
                self.target_dir.rename(backup_dir)
                journal_data["phase"] = "TARGET_MOVED"
                _atomic_write_journal(journal_file, journal_data)

            candidate_dir.rename(self.target_dir)
            journal_data["phase"] = "COMMITTED"
            _atomic_write_journal(journal_file, journal_data)

            # 4. Limpieza post-compromiso exitoso
            if target_existed and backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            journal_file.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Fallo durante la preparacion o conmutacion de documentos (B1). Ejecutando reversor: {e}")
            if candidate_dir.exists():
                shutil.rmtree(candidate_dir, ignore_errors=True)
            if backup_dir.exists() and not self.target_dir.exists():
                backup_dir.rename(self.target_dir)
            if self.db_restored and self.target_database_url:
                try:
                    _enforce_database_quarantine(
                        self.target_database_url,
                        reason=f"INCONSISTENT_RESTORATION (B1-01): Document promotion failed during cutover: {e}",
                        journal_state=journal_data.get("phase")
                    )
                except Exception as db_err:
                    logger.error(f"Error colocando BD en cuarentena tras fallo de promocion: {db_err}")
            # B1: Preservar el diario para permitir auditoria y diagnostico forense (no borrar evidencia)
            journal_data["phase"] = "FAILED_INCONSISTENT"
            journal_data["error"] = str(e)
            try:
                _atomic_write_journal(journal_file, journal_data)
            except Exception:
                pass
            raise RuntimeError(f"Fallo durante promocion atomica de documentos (B1): {e}") from e


def recover_pending_cutover(
    parent_dir: Path,
    target_database_url: Optional[str] = None,
    expected_marker_id: Optional[str] = None
) -> bool:
    """
    Recupera el estado de directorios si ocurrio una caida del proceso durante un cutover previo (Item 1, B1).
    Coordina con el estado de PostgreSQL si la base de datos ya fue restaurada.
    """
    return CrashResilientDocumentPublisher.recover(
        parent_dir=parent_dir,
        target_database_url=target_database_url,
        expected_marker_id=expected_marker_id
    )


def atomic_promote_documents(
    staging_dir: Path,
    target_dir: Path,
    catalog: List[Dict[str, Any]],
    db_restored: bool = False,
    target_database_url: Optional[str] = None,
    expected_marker_id: Optional[str] = None
) -> None:
    """
    Promociona de forma transaccional, atomica y recuperable ante muerte del proceso el directorio
    de documentos de staging hacia target_dir utilizando CrashResilientDocumentPublisher (Item 1, R5-02, B1).
    """
    publisher = CrashResilientDocumentPublisher(
        target_dir=target_dir,
        db_restored=db_restored,
        target_database_url=target_database_url,
        expected_marker_id=expected_marker_id
    )
    publisher.publish(staging_dir=staging_dir, catalog=catalog)


def restore_lan_backup(
    backup_file: Path,
    target_uploads_dir: Path,
    encryption_key: str,
    signing_key: str,
    expected_marker_id: Optional[str] = None,
    target_database_url: Optional[str] = None,
    source_database_url: Optional[str] = None,
    container_name: Optional[str] = None,
    documents_only: bool = False
) -> Dict[str, Any]:
    """
    Restaura de forma autenticada el respaldo LAN (P14-R1-10, P14-R1-11, R3-02, R3-03, R3-13, R4-01, R4-07, R5-01, R5-02):
    1. Verifica firma HMAC-SHA256 del manifiesto antes de procesar cualquier dato.
    2. Exige expected_marker_id y target_database_url obligatorios para restauracion integral (R3-02, R5-01).
    3. Preflight estricto de seguridad: target_url es efimera, con ownership marker verificado y distinta de source_url (R4-01, R5-01).
    4. Valida SHA-256 del archivo cifrado.
    5. Descifra con AES-256-GCM.
    6. Extraccion segura en staging con validacion exhaustiva contra path traversal y symlinks (R3-13).
    7. Valida catalogo de documentos: ningun relative_path puede ser absoluto, tener '..' o symlink (R3-13).
    8. Extrae y valida documentos en directorio STAGING independiente sin tocar destino previo (R4-07).
    9. Restaura PostgreSQL 15 real en BD efimera con transaccion atomica y ON_ERROR_STOP=1 (R3-03, R4-01, R5-08).
    10. Promocion atomica crash-safe con snapshot rollback a target_uploads_dir SOLO tras exito comprobado conjunto (R5-02).
    """
    t_start = time.time()

    if not documents_only:
        if not target_database_url:
            raise ValueError(
                "Fallo critico (R3-02): 'target_database_url' es obligatoria para la restauracion integral de respaldo LAN. "
                "No se permite ejecutar restauracion sin base de datos destino autorizada."
            )
        if not expected_marker_id or not str(expected_marker_id).strip():
            raise ValueError(
                "Fallo de seguridad critico (R5-01): 'expected_marker_id' es estrictamente obligatorio para autenticar "
                "la propiedad de la base de datos destino efimera de esta ejecucion."
            )

    if not backup_file.exists():
        raise FileNotFoundError(f"Archivo de respaldo no encontrado: {backup_file}")

    manifest_file = Path(str(backup_file) + ".manifest.json")
    if not manifest_file.exists():
        raise FileNotFoundError(f"Manifiesto de respaldo ausente: {manifest_file}")

    # 1. Validar firma HMAC-SHA256 del manifiesto (P14-R1-11)
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    hmac_signature = manifest.get("hmac_signature")
    if not hmac_signature:
        raise ValueError("El manifiesto no contiene firma HMAC de autenticidad.")

    manifest_to_verify = {k: v for k, v in manifest.items() if k != "hmac_signature"}
    manifest_bytes = json.dumps(manifest_to_verify, sort_keys=True).encode("utf-8")

    if not verify_hmac_sha256(manifest_bytes, hmac_signature, signing_key):
        raise ValueError("Firma HMAC del manifiesto de respaldo invalida o manipulada (P14-R1-11).")

    # Contrato R3-02, R4-01, R5-01: Restauracion integral exige target_database_url y source_database_url real
    effective_source_url = source_database_url or manifest.get("source_provenance")

    # B1-RESTORE: Validacion estricta y recuperacion segura del estado de corte anterior
    # Impedir que un intento previo pendiente, corrupto o en cuarentena sea sobrescrito
    # sin validar su estado y sin alterar la base de datos ni el destino documental.
    parent_dir = target_uploads_dir.resolve().parent
    journal_file = parent_dir / ".cutover_journal.json"
    if journal_file.exists():
        try:
            journal_raw = journal_file.read_text(encoding="utf-8")
            prior_data = json.loads(journal_raw)
        except Exception as parse_err:
            logger.error(f"Fallo critico de recuperacion (B1-RESTORE): Diario previo corrupto o ilegible ({parse_err}). Abortando fail-closed.")
            raise RuntimeError(
                "Fallo critico de recuperacion (B1-RESTORE): Existe un diario anterior (.cutover_journal.json) "
                "corrupto o irrecuperable. Restauracion LAN abortada de forma fail-closed para preservar la evidencia forense sin sobreescritura."
            )

        prior_phase = prior_data.get("phase", "")
        if prior_phase == "FAILED_INCONSISTENT":
            raise RuntimeError(
                "Fallo critico de recuperacion (B1-RESTORE): El repositorio documental permanece en estado inconsistente "
                "o en cuarentena por un corte fallido previo (FAILED_INCONSISTENT). Restauracion LAN abortada de forma fail-closed."
            )

        # Si hay una transicion documental previa pendiente, intentar recuperacion segura antes de continuar
        logger.warning(f"Detectada transicion documental previa en fase '{prior_phase}'. Ejecutando recover() fail-closed...")
        recovered = CrashResilientDocumentPublisher.recover(
            parent_dir=parent_dir,
            target_database_url=target_database_url,
            expected_marker_id=expected_marker_id
        )
        if not recovered or journal_file.exists():
            raise RuntimeError(
                "Fallo critico de recuperacion (B1-RESTORE): Existe un diario de corte anterior (.cutover_journal.json) "
                "cuya recuperacion no fue exitosa o el repositorio permanece en estado inconsistente. "
                "Restauracion LAN abortada de forma fail-closed para preservar la integridad y el diario de evidencia."
            )

    if not documents_only:
        if not effective_source_url:
            raise ValueError(
                "Fallo de seguridad critico (R4-01, R5-01): source_database_url es obligatoria para verificar origen y destino. "
                "Debe suministrarse explicitamente o extraerse de un manifiesto firmado valido."
            )
        # Preflight target safety y marcador de propiedad efimero antes de tocar archivos (R3-03, R4-01, R5-01)
        validate_restore_target_safety(
            target_database_url=target_database_url,
            source_database_url=effective_source_url,
            expected_marker_id=expected_marker_id,
            manifest=manifest
        )

    # 2. Validar hash SHA-256 del archivo cifrado
    actual_file_sha = compute_file_sha256(backup_file)
    if actual_file_sha != manifest.get("backup_sha256"):
        raise ValueError(
            f"Fallo de integridad en archivo cifrado: esperado {manifest.get('backup_sha256')}, actual {actual_file_sha}"
        )

    # 3. Descifrado AEAD
    with open(backup_file, "r", encoding="utf-8") as f:
        encrypted_payload = f.read()

    raw_latin1 = decrypt_aead(encrypted_payload, encryption_key)
    raw_bytes = raw_latin1.encode("latin1")

    temp_dir = backup_file.parent / f".tmp_restore_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_tar = temp_dir / "restored.tar"

    # Directorio de staging aislado para extraccion y cutover atomico (R4-07, R5-02)
    staging_uploads_dir = target_uploads_dir.parent / f".staging_restore_{uuid.uuid4().hex[:8]}"

    try:
        with open(temp_tar, "wb") as f:
            f.write(raw_bytes)

        # 4. Extraccion segura blindada contra path traversal y symlinks en TAR (P14-R1-11)
        temp_extracted = temp_dir / "extracted"
        temp_extracted.mkdir(parents=True, exist_ok=True)
        dest_resolved = temp_extracted.resolve()

        with tarfile.open(temp_tar, "r") as tar:
            for member in tar.getmembers():
                if member.issym() or member.islnk():
                    raise ValueError(f"Intento de enlace simbolico malicioso detectado en tar: {member.name}")
                member_path = Path(member.name)
                if member_path.is_absolute() or any(p == ".." for p in member_path.parts):
                    raise ValueError(f"Intento de path traversal detectado en tar: {member.name}")
                target_path = (temp_extracted / member_path).resolve()
                if not str(target_path).startswith(str(dest_resolved)):
                    raise ValueError(f"Ruta de destino fuera del staging aislada: {member.name}")
                tar.extract(member, path=temp_extracted)

        # 5. Validacion exhaustiva del catalogo de documentos (R3-13)
        catalog_path = temp_extracted / "document_catalog.json"
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        extracted_uploads = temp_extracted / "uploads"
        target_root_resolved = target_uploads_dir.resolve()

        # Validacion previa estricta de cada entrada de catalogo (R3-13)
        for entry in catalog:
            rel_str = entry.get("relative_path", "")
            rel_path = Path(rel_str)

            # A. Comprobacion de formato y traversal
            if not rel_str or rel_path.is_absolute() or rel_path.drive or rel_path.root:
                raise ValueError(f"Path traversal detectado en catalogo (ruta absoluta o con drive): {rel_str}")
            if any(p == ".." for p in rel_path.parts):
                raise ValueError(f"Path traversal detectado en catalogo (componente '..'): {rel_str}")

            # B. Confinamiento de origen extraido en staging
            src = (extracted_uploads / rel_path).resolve()
            if not str(src).startswith(str(extracted_uploads.resolve())):
                raise ValueError(f"Ruta de origen extraida fuera del staging: {rel_str}")
            if src.is_symlink():
                raise ValueError(f"Enlace simbolico no permitido en origen extraido: {rel_str}")
            if not src.exists():
                raise FileNotFoundError(f"Archivo de catalogo faltante en backup: {rel_str}")

            # C. Verificacion SHA-256 en staging antes de escribir
            src_hash = compute_file_sha256(src)
            if src_hash != entry["sha256"]:
                raise ValueError(
                    f"Corrupcion en archivo de respaldo {rel_str}: hash {src_hash} != {entry['sha256']}"
                )

            # D. Confinamiento de destino y prohibicion de symlinks en destino (R3-13)
            dest = (target_uploads_dir / rel_path).resolve()
            try:
                dest.relative_to(target_root_resolved)
            except ValueError:
                raise ValueError(f"Path traversal detectado en destino de catalogo: {rel_str}")

            if os.path.commonpath([str(target_root_resolved), str(dest)]) != str(target_root_resolved):
                raise ValueError(f"Destino de catalogo no confinado dentro de target_uploads_dir: {rel_str}")

            # Verificar que ningun componente del destino sea un symlink preexistente
            cur_check = dest
            while cur_check != target_root_resolved and cur_check.parent != cur_check:
                if cur_check.is_symlink():
                    raise ValueError(f"Destino o directorio intermedio es un enlace simbolico no permitido: {cur_check}")
                cur_check = cur_check.parent

        # 6. Copia y validacion en staging independiente (R4-07)
        staging_uploads_dir.mkdir(parents=True, exist_ok=True)
        for entry in catalog:
            rel_path = Path(entry["relative_path"])
            src = extracted_uploads / rel_path
            staged_file = staging_uploads_dir / rel_path
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            staged_file.write_bytes(src.read_bytes())
            staged_hash = compute_file_sha256(staged_file)
            if staged_hash != entry["sha256"]:
                raise ValueError(f"Fallo en comprobacion de integridad staging para {rel_path}: {staged_hash} != {entry['sha256']}")

        # B1: Zero-Window Journal & Pre-Quarantine:
        # Registrar durablemente el intento y poner el destino en estado de restauracion antes de modificar la BD.
        parent_dir = target_uploads_dir.resolve().parent
        journal_file = parent_dir / ".cutover_journal.json"
        run_id = uuid.uuid4().hex[:8]
        candidate_dir = parent_dir / f".target_candidate_{run_id}"
        backup_dir = parent_dir / f".target_backup_{run_id}"
        catalog_hashes = {entry["relative_path"]: entry["sha256"] for entry in catalog}

        journal_data = {
            "phase": "RESTORATION_INITIATED",
            "target_dir": str(target_uploads_dir.resolve()),
            "candidate_dir": str(candidate_dir.resolve()),
            "backup_dir": str(backup_dir.resolve()),
            "db_restored": False,
            "target_database_url": target_database_url,
            "expected_marker_id": expected_marker_id,
            "catalog_hashes": catalog_hashes,
            "created_at": time.time()
        }
        _atomic_write_journal(journal_file, journal_data)

        # 7. Restaurar base de datos PostgreSQL 15 real en BD efimera autenticada (R3-02, R3-03, R4-01, R5-01, R5-08)
        db_restored = False
        sql_dump_file = temp_extracted / "database.sql"

        if not documents_only:
            if not sql_dump_file.exists():
                raise FileNotFoundError("El respaldo no contiene el archivo de volcado database.sql necesario para restaurar.")
            db_restored = execute_pg_restore(
                target_database_url=target_database_url,
                sql_file=sql_dump_file,
                expected_marker_id=expected_marker_id,
                source_database_url=effective_source_url,
                container_name=container_name
            )
            if not db_restored:
                raise RuntimeError("Fallo critico en execute_pg_restore: la base de datos no fue restaurada.")

            # BD restaurada en cuarentena atomica: actualizar el diario durablemente
            journal_data["phase"] = "DB_RESTORED"
            journal_data["db_restored"] = True
            _atomic_write_journal(journal_file, journal_data)

        # 8. Promocion documental crash-safe coordinada con PostgreSQL (Item 1, R5-02)
        atomic_promote_documents(
            staging_dir=staging_uploads_dir,
            target_dir=target_uploads_dir,
            catalog=catalog,
            db_restored=db_restored,
            target_database_url=target_database_url,
            expected_marker_id=expected_marker_id
        )

        # 9. B1: Levantar la cuarentena de PostgreSQL de forma transaccional verificada
        # SOLO una vez verificada y promovida la version documental esperada
        if db_restored and target_database_url:
            _lift_database_quarantine(target_database_url)

        rto_seconds = round(time.time() - t_start, 2)
        status_code = "DOCUMENTS_ONLY_SUCCESS" if documents_only else "RESTORED_SUCCESS"

        logger.info(
            f"Restauracion LAN PG15 completada exitosamente en {rto_seconds}s ({status_code}): "
            f"{len(catalog)} documentos verificados y promocionados de forma atomica, DB restaurada={db_restored}."
        )

        return {
            "status": status_code,
            "document_count": len(catalog),
            "db_restored": db_restored,
            "manifest": manifest,
            "rto_seconds": rto_seconds
        }
    finally:
        if staging_uploads_dir.exists():
            shutil.rmtree(staging_uploads_dir, ignore_errors=True)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Herramienta de Respaldo y Restauracion LAN PostgreSQL 15")
    subparsers = parser.add_subparsers(dest="action")

    p_bak = subparsers.add_parser("backup", help="Genera un respaldo coherente firmado y cifrado")
    p_bak.add_argument("--db-url", default=os.getenv("DATABASE_URL", "postgresql://test_user:test_password@localhost:5432/test_db"))
    p_bak.add_argument("--uploads-dir", default=os.getenv("UPLOADS_DIR", "./data/uploads"))
    p_bak.add_argument("--output", default="./data/backups/lan_pg15_latest.tar.enc")
    p_bak.add_argument("--container", default=None, help="Nombre del contenedor Docker de PG15")

    p_res = subparsers.add_parser("restore", help="Restaura un respaldo verificando integridad HMAC")
    p_res.add_argument("--backup-file", required=True)
    p_res.add_argument("--target-uploads", default="./data/uploads_restored")
    p_res.add_argument("--target-db-url", default=None, help="URL de base de datos destino aislada")
    p_res.add_argument("--expected-marker", default=None, help="Marcador de propiedad efimero obligatorio para validar la base destino (R5-01)")
    p_res.add_argument("--source-db-url", default=None, help="URL de base de datos origen para validacion de seguridad")
    p_res.add_argument("--container", default=None, help="Nombre del contenedor Docker de PG15")
    p_res.add_argument("--documents-only", action="store_true", default=False, help="Modo exclusivo de documentos sin restaurar BD")

    args = parser.parse_args()

    enc_key = os.getenv("BACKUP_ENCRYPTION_KEY", getattr(settings, "BACKUP_ENCRYPTION_KEY", "test_backup_enc_key_32bytes_!!"))
    sign_key = os.getenv("BACKUP_SIGNING_KEY", getattr(settings, "BACKUP_SIGNING_KEY", "test_backup_sign_key_32bytes_!!"))

    if args.action == "backup":
        res = create_lan_backup(
            database_url=args.db_url,
            uploads_dir=Path(args.uploads_dir),
            output_backup_file=Path(args.output),
            encryption_key=enc_key,
            signing_key=sign_key,
            container_name=args.container
        )
        print(json.dumps(res, indent=2))

    elif args.action == "restore":
        res = restore_lan_backup(
            backup_file=Path(args.backup_file),
            target_uploads_dir=Path(args.target_uploads),
            encryption_key=enc_key,
            signing_key=sign_key,
            expected_marker_id=args.expected_marker,
            target_database_url=args.target_db_url,
            source_database_url=args.source_db_url,
            container_name=args.container,
            documents_only=args.documents_only
        )
        print(json.dumps(res, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
