import os
import time
import uuid
import socket
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

logger = logging.getLogger("app.core.write_control")


def get_current_host_id() -> str:
    """
    Identificador unico de la instancia de ejecucion (contenedor o host).
    En Docker, HOSTNAME contiene el Container ID por defecto.
    """
    return os.environ.get("HOSTNAME") or socket.gethostname() or "unknown_host"


def is_process_alive(pid: int) -> bool:
    """
    Comprueba si un proceso sigue activo en el sistema operativo local.
    Maneja diferencias entre POSIX y Windows sin asumir muerte del proceso
    ante errores de permisos (fail-closed).
    NOTA CRITICA (B2): Solo es valido para procesos dentro del MISMO espacio de nombres PID.
    Entre contenedores independientes, la autoridad de liveness reside en PostgreSQL advisory locks.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError as err:
        # En Windows/POSIX: PermissionError (EPERM / winerror 5) significa que el proceso existe pero no podemos enviarle senal (esta vivo!)
        if isinstance(err, PermissionError) or getattr(err, "winerror", None) == 5:
            return True
        return False
    except Exception:
        # Fail-closed: ante cualquier duda o excepcion inesperada, considerar que sigue vivo
        return True


def _require_postgresql_lock_url(database_url: Optional[str] = None) -> str:
    """Require a PostgreSQL backend before granting document-write access.

    None means resolve application configuration. An explicit empty string is
    invalid and must not silently fall back to a different connection.
    """
    db_url = database_url
    if db_url is None:
        try:
            from app.core.config import settings
            db_url = getattr(settings, "DATABASE_URL", None)
        except Exception:
            db_url = None
        if not db_url:
            db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        raise RuntimeError(
            "B2-FC fail-closed: DATABASE_URL PostgreSQL obligatoria para escrituras documentales."
        )
    try:
        backend = make_url(str(db_url)).get_backend_name()
    except Exception as exc:
        raise RuntimeError(
            "B2-FC fail-closed: DATABASE_URL invalida para bloqueo documental."
        ) from exc
    if backend != "postgresql":
        raise RuntimeError(
            "B2-FC fail-closed: PostgreSQL es obligatorio para la exclusion documental."
        )
    return str(db_url)


class DocumentWriterGuard:
    """
    Guardián de exclusión atómica para operaciones de escritura/eliminación documental (B2-TOCTOU).
    Retiene un bloqueo compartido en PostgreSQL (pg_try_advisory_lock_shared) durante
    TODA la mutación en disco, impidiendo atómicamente que el respaldador inicie en medio
    de una escritura, y garantizando que un escritor sea rechazado atómicamente si el respaldo
    ha adquirido o adquiere el bloqueo exclusivo.
    """
    def __init__(self, uploads_dir: Path, database_url: Optional[str] = None):
        self.uploads_dir = Path(uploads_dir)
        self.database_url = database_url
        self._engine = None
        self._conn = None
        self._locked = False

    def __enter__(self):
        # No permitir ninguna escritura sin autoridad compartida PostgreSQL.
        db_url = _require_postgresql_lock_url(self.database_url)

        # 2. Si hay BD PostgreSQL disponible, adquirir advisory lock compartido
        try:
            self._engine = create_engine(db_url, connect_args={"connect_timeout": 3})
            self._conn = self._engine.connect()
            acquired = self._conn.execute(
                text("SELECT pg_try_advisory_lock_shared(hashtext('abst_lan_backup_write_lock'))")
            ).scalar()
            if not acquired:
                self._cleanup()
                raise RuntimeError(
                    "Fallo de control de escrituras (B2): Repositorio documental en congelamiento por respaldo LAN activo (exclusión exclusiva en BD)."
                )
            self._locked = True
        except RuntimeError:
            raise
        except Exception as e:
            self._cleanup()
            logger.warning(f"Error adquiriendo advisory lock compartido en BD (B2 fail-closed): {e}")
            raise RuntimeError(
                f"Fallo de control de escrituras (B2 fail-closed): No se pudo verificar la exclusión en PostgreSQL: {e}"
            )

        # 3. Verificar estado de congelamiento en disco / centinela
        if DocumentWriteControl.is_write_frozen(self.uploads_dir, database_url=db_url):
            self._cleanup()
            raise RuntimeError(
                "Fallo de control de escrituras (B2): Repositorio documental en congelamiento por respaldo LAN activo."
            )

        return self

    def _cleanup(self):
        if self._conn and not self._conn.closed:
            try:
                if self._locked:
                    self._conn.execute(text("SELECT pg_advisory_unlock_shared(hashtext('abst_lan_backup_write_lock'))"))
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
        self._locked = False
        if self._engine:
            try:
                self._engine.dispose()
            except Exception:
                pass
            self._engine = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()


class DocumentWriteControl:
    """
    Control de exclusion mutua y congelamiento de escrituras documentales durante respaldos LAN (B2, Item 2).
    - Exclusión y propiedad verificable entre contenedores Docker independientes.
    - Autoridad centralizada compartida: PostgreSQL advisory lock 'abst_lan_backup_write_lock'.
    - Liveness cross-container fail-closed: un proceso no visible en el PID namespace local
      NO se asume terminado si el advisory lock permanece retenido en la BD o ante incertidumbre.
    - Prevencion de borrado ajeno: Asigna un token unico de propiedad y verifica que el proceso sea
      el creador legitimo antes de remover el centinela.
    """
    def __init__(self, database_url: str, uploads_dir: Path):
        self.database_url = database_url
        self.uploads_dir = uploads_dir
        self.lock_file = uploads_dir / ".write_freeze_lock"
        self._token = uuid.uuid4().hex
        self._host_id = get_current_host_id()
        self._pid = os.getpid()
        self._file_created = False
        self._engine = None
        self._conn = None

    @classmethod
    def writer_lock(cls, uploads_dir: Path, database_url: Optional[str] = None) -> DocumentWriterGuard:
        """
        Retorna un contexto guardián de escritura con exclusión compartida efectiva (B2-TOCTOU).
        """
        return DocumentWriterGuard(uploads_dir=uploads_dir, database_url=database_url)

    @classmethod
    def _parse_sentinel(cls, lock_file: Path) -> Optional[Dict[str, Any]]:
        """
        Parsea los metadatos del centinela en filesystem.
        Soporta formato extendido cross-container y formato legacy.
        """
        try:
            content = lock_file.read_text(encoding="utf-8").strip()
            if not content:
                return None
            parts = content.split("_")
            if len(parts) >= 5 and parts[0] == "WRITE" and parts[1] == "FREEZE" and parts[2] == "ACTIVE":
                timestamp = float(parts[3])
                pid = int(parts[4])
                token = parts[5] if len(parts) > 5 else ""
                host_id = parts[6] if len(parts) > 6 else ""
                return {
                    "timestamp": timestamp,
                    "pid": pid,
                    "token": token,
                    "host_id": host_id,
                    "raw": content
                }
            return {"raw": content, "timestamp": 0.0, "pid": 0, "token": "", "host_id": ""}
        except Exception as e:
            logger.warning(f"Error parseando centinela {lock_file}: {e}")
            return None

    @classmethod
    def is_write_frozen(cls, uploads_dir: Path, database_url: Optional[str] = None) -> bool:
        """
        Indica si el repositorio documental se encuentra actualmente en congelamiento por respaldo.
        B2-CRITICO / B2-TOCTOU:
        - Si existe base de datos PostgreSQL, consulta inmediatamente la autoridad centralizada compartida
          (PostgreSQL advisory lock). Si el lock exclusivo esta retenido (pg_try_advisory_lock_shared retorna False),
          el respaldo esta activo en algun contenedor -> True de inmediato, INCLUSO SI .write_freeze_lock
          TODAVIA NO EXISTE EN DISCO (cierra la ventana TOCTOU).
        - Si el centinela .write_freeze_lock existe en disco:
          - Si el PID local esta vivo en el OS, devuelve True.
          - Si el PID no es visible localmente (cross-container):
            si el advisory lock en PostgreSQL estaba libre, el centinela es un residuo huerfano -> False.
            si no hay conexion con PostgreSQL o falla de comunicacion: fail-closed -> True.
        - Si no existe centinela y no hay advisory lock exclusivo: False.
        """
        lock = uploads_dir / ".write_freeze_lock"

        # La ausencia de una autoridad PostgreSQL verificable equivale a bloqueo.
        try:
            db_url = _require_postgresql_lock_url(database_url)
        except RuntimeError as exc:
            logger.warning("Control documental B2-FC cerrado: %s", exc)
            return True

        # 1. B2-TOCTOU: Consultar a la autoridad compartida PostgreSQL si hay base de datos configurada
        try:
            eng = create_engine(db_url, connect_args={"connect_timeout": 3})
            with eng.connect() as conn:
                can_share = conn.execute(
                    text("SELECT pg_try_advisory_lock_shared(hashtext('abst_lan_backup_write_lock'))")
                ).scalar()
                if not can_share:
                    # Respaldo exclusivo activo en PostgreSQL en algun contenedor -> Bloqueado inmediatamente
                    eng.dispose()
                    return True
                else:
                    conn.execute(
                        text("SELECT pg_advisory_unlock_shared(hashtext('abst_lan_backup_write_lock'))")
                    )
            eng.dispose()
            # Advisory lock en BD libre: si NO hay centinela en filesystem, el repositorio no esta congelado
            if not lock.exists():
                return False
            # Si hay centinela en filesystem, pero el advisory lock esta libre:
            # Comprobar si el PID local esta vivo. Si no esta vivo localmente, es un centinela huerfano reconocido -> False
            try:
                content = lock.read_text(encoding="utf-8").strip()
                parts = content.split("_")
                pid = int(parts[4]) if len(parts) > 4 else 0
                if pid > 0 and is_process_alive(pid):
                    return True
                # Lock libre en BD y PID no vivo localmente -> huerfano
                return False
            except Exception:
                return False
        except Exception as db_err:
            logger.warning(f"Error comprobando advisory lock en PostgreSQL (B2 fail-closed): {db_err}")
            if lock.exists():
                return True
            return True

    def __enter__(self):
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

        # 1. ADVISORY LOCK PRIMERO: Autoridad centralizada compartida a nivel de base de datos
        # NUNCA tocar ni alterar el centinela en filesystem si otro respaldo ya esta en ejecucion en algun contenedor.
        self._engine = create_engine(self.database_url, connect_args={"connect_timeout": 5})
        self._conn = self._engine.connect()
        acquired = self._conn.execute(
            text("SELECT pg_try_advisory_lock(hashtext('abst_lan_backup_write_lock'))")
        ).scalar()

        if not acquired:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            try:
                self._engine.dispose()
            except Exception:
                pass
            self._engine = None
            raise RuntimeError(
                "Fallo de control de escrituras (Item 2, B2): Ya existe un respaldo LAN en ejecucion en el cluster "
                "(PostgreSQL advisory lock 'abst_lan_backup_write_lock' retenido). Abortando respaldo concurrente fail-closed."
            )

        try:
            # 2. Con el advisory lock retenido exclusivamente:
            # Evaluar centinela preexistente en filesystem
            if self.lock_file.exists():
                try:
                    content = self.lock_file.read_text(encoding="utf-8").strip()
                    parts = content.split("_")
                    pid = int(parts[4]) if len(parts) > 4 else 0
                    if pid > 0 and is_process_alive(pid):
                        raise RuntimeError(
                            "Fallo de control de escrituras (Item 2, B2): Centinela activo de otro proceso vivo detectado "
                            f"en {self.lock_file} (PID {pid}). Respaldo abortado para evitar concurrencia."
                        )
                    else:
                        logger.warning(
                            f"Centinela {self.lock_file} pertenece a sesion no activa (PID {pid}). Removiendo residuo huerfano."
                        )
                        self.lock_file.unlink(missing_ok=True)
                except RuntimeError:
                    raise
                except Exception as e:
                    raise RuntimeError(
                        f"Fallo de control de escrituras (Item 2, B2): Error evaluando centinela existente en {self.lock_file}: {e}"
                    )

            # 3. Creacion atomica del centinela con metadatos cross-container
            sentinel_data = f"WRITE_FREEZE_ACTIVE_{time.time()}_{self._pid}_{self._token}_{self._host_id}\n"
            try:
                with open(self.lock_file, "x", encoding="utf-8") as f:
                    f.write(sentinel_data)
                    f.flush()
                    os.fsync(f.fileno())
                self._file_created = True
            except FileExistsError:
                raise RuntimeError(
                    "Fallo de control de escrituras (Item 2, B2): Creacion concurrente de centinela detectada "
                    f"en {self.lock_file}. Respaldo abortado."
                )
        except Exception:
            try:
                if self._conn and not self._conn.closed:
                    self._conn.execute(text("SELECT pg_advisory_unlock(hashtext('abst_lan_backup_write_lock'))"))
                    self._conn.close()
            except Exception:
                pass
            self._conn = None
            try:
                if self._engine:
                    self._engine.dispose()
            except Exception:
                pass
            self._engine = None
            raise

        logger.info(f"Control de escrituras establecido: advisory lock en PostgreSQL y centinela en {self.lock_file} (host={self._host_id}, pid={self._pid}).")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._conn and not self._conn.closed:
                try:
                    self._conn.execute(text("SELECT pg_advisory_unlock(hashtext('abst_lan_backup_write_lock'))"))
                except Exception:
                    pass
                self._conn.close()
        finally:
            if self._engine:
                self._engine.dispose()
            # B2-01: Solo remover el centinela si este proceso es el propietario acreditado del token
            if self._file_created:
                try:
                    if self.lock_file.exists():
                        content = self.lock_file.read_text(encoding="utf-8")
                        if self._token in content:
                            self.lock_file.unlink(missing_ok=True)
                except Exception:
                    pass
                self._file_created = False
            logger.info("Control de escrituras liberado exitosamente.")
